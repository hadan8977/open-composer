"""Memory-capped research launches: Job Objects on Windows, run_capped.sh on Linux."""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path


def memory_bytes(value: str) -> int:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMG]?)", value.upper())
    if not match:
        raise ValueError(f"Invalid memory limit {value!r}")
    return math.ceil(float(match[1]) * 1024 ** " KMG".index(match[2]))


def budget(root: Path) -> dict:
    return json.loads((root / "config/memory-budget.json").read_text(encoding="utf-8"))


def capped_command(root: Path, argv: list[str], mem: str, *, wait_min: int = 0) -> list[str]:
    if os.name == "nt":
        launcher = [sys.executable, str(root / "scripts/run_capped.py"), "--root", str(root)]
    else:
        launcher = [str(root / "scripts/run_capped.sh")]
    return [*launcher, "--mem", mem, "--wait-min", str(wait_min), "--", *argv]


def admission(root: Path, mem: str = "900M") -> dict:
    """Free physical and commit memory must cover the job's start headroom plus the reserve."""
    from open_composer.research.windows_runtime import global_memory

    cfg, mb = budget(root), math.ceil(memory_bytes(mem) / 1048576)
    state = global_memory()
    state["required_mb"] = min(mb, cfg["heavy_job_mb"]) + cfg["reserve_mb"]
    state["required_commit_mb"] = min(mb, cfg["oc_max_mb"]) + cfg["reserve_mb"]
    state["admitted"] = (
        state["available_mb"] >= state["required_mb"]
        and state["available_commit_mb"] >= state["required_commit_mb"]
    )
    return state


def capped_process(argv: list[str], *, root: Path, mem: str, **kwargs):
    """Start argv in its own memory-capped Job Object if the machine has headroom."""
    from open_composer.research.windows_runtime import WindowsProcess

    limit = memory_bytes(mem)
    if limit > budget(root)["job_max_mb"] * 1048576:
        raise ValueError("Research job exceeds the configured local job limit")
    if not admission(root, mem)["admitted"]:
        raise MemoryError("Native research admission refused: physical/commit headroom")
    return WindowsProcess(argv, memory_bytes=limit, **kwargs)


def native_process(command: list[str], default_root: Path, **kwargs):
    """Run a capped_command() directly, so the caller owns the job (no wrapper process)."""
    root, mem, argv = default_root, "900M", command
    if len(command) > 1 and Path(command[1]).name == "run_capped.py":
        end = command.index("--")
        options = dict(zip(command[2:end:2], command[3:end:2], strict=True))
        root, mem, argv = Path(options["--root"]), options["--mem"], command[end + 1 :]
    if argv[:2] == ["env", "-C"]:  # provider adapters bind their working directory this way
        kwargs["cwd"], argv = argv[2], argv[3:]
    kwargs.setdefault("cwd", root)
    kwargs["env"] = {**(kwargs.get("env") or os.environ), "PYTHONUTF8": "1"}
    return capped_process(argv, root=root, mem=mem, **kwargs)
