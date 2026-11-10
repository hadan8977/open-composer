"""Small Paseo adapter for the owner's Windows research worker."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXPECTED_ROOT = r"C:\paseo"
EXPECTED_SCRATCH = r"C:\paseo\scratch"
MAX_USAGE_BYTES = 50 * (1 << 30)
_OFFER_RE = re.compile(r"https://app\.paseo\.sh/#offer=[^\s'\"<>]+")
_CONTROL_NAME = "oc-worker-control"


@dataclass(frozen=True)
class WorkerCommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _redact(text: str) -> str:
    return _OFFER_RE.sub("https://app.paseo.sh/#offer=[redacted]", text)


def load_worker_contract(root: Path) -> dict[str, Any]:
    path = root / "config" / "windows-paseo-worker.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("transport") != "paseo-relay":
        raise ValueError("Windows worker must use paseo-relay")
    if str(contract.get("remote_root", "")).casefold() != EXPECTED_ROOT.casefold():
        raise ValueError(f"Windows worker root must be {EXPECTED_ROOT}")
    if contract.get("max_usage_gib") != 50:
        raise ValueError("Windows worker limit must be 50 GiB")
    return contract


def _offer_path(contract: dict[str, Any]) -> Path:
    return Path(os.path.expanduser(str(contract["offer_file"]))).resolve()


def _wrapper_path(root: Path, contract: dict[str, Any]) -> Path:
    path = (root / str(contract["wrapper"])).resolve()
    path.relative_to(root.resolve())
    return path


def _state_path() -> Path:
    return Path.home() / ".config/open-composer/paseo-windows-worker-state.json"


def _terminal_id() -> str | None:
    try:
        return str(json.loads(_state_path().read_text()).get("terminal_id"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def _save_terminal(terminal_id: str, workspace_id: str) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"terminal_id": terminal_id, "workspace_id": workspace_id}) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def run_worker_command(
    root: Path, args: list[str] | tuple[str, ...], *, timeout: float = 30
) -> WorkerCommandResult:
    """Run the saved wrapper; callers cannot replace its endpoint."""

    contract = load_worker_contract(root)
    wrapper = _wrapper_path(root, contract)
    command = tuple(map(str, args))
    if any(
        arg in {"--host", "--home"}
        or arg.startswith(("--host=", "--home="))
        or "https://app.paseo.sh/#offer=" in arg
        for arg in command
    ):
        raise ValueError("Windows worker endpoint is fixed by the wrapper")
    if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
        raise FileNotFoundError(wrapper)
    try:
        result = subprocess.run(
            [str(wrapper), *command],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env={
                key: value
                for key, value in os.environ.items()
                if key not in {"PASEO_HOST", "PASEO_HOME"}
            },
        )
        return WorkerCommandResult(
            command, result.returncode, _redact(result.stdout), _redact(result.stderr)
        )
    except subprocess.TimeoutExpired as exc:
        return WorkerCommandResult(command, 124, str(exc.stdout or ""), str(exc.stderr or ""))


def _json_command(root: Path, args: list[str]) -> tuple[WorkerCommandResult, Any | None]:
    result = run_worker_command(root, [*args, "--json"])
    if not result.ok:
        return result, None
    try:
        return result, json.loads(result.stdout)
    except json.JSONDecodeError:
        return result, None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_task_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Check the small set of transfer facts needed before a remote task."""

    contract = load_worker_contract(root)
    job_id = str(manifest.get("job_id", ""))
    scratch = str(manifest.get("remote_scratch", ""))
    if not job_id or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for char in job_id
    ):
        raise ValueError("invalid job_id")
    if scratch.casefold() != f"{EXPECTED_SCRATCH}\\{job_id}".casefold():
        raise ValueError("remote_scratch must stay under C:\\paseo\\scratch")
    if manifest.get("remote_root", "").casefold() != EXPECTED_ROOT.casefold():
        raise ValueError(f"remote_root must be {EXPECTED_ROOT}")
    if not manifest.get("cleanup", {}).get("required"):
        raise ValueError("cleanup.required must be true")
    checked = []
    for item in manifest.get("inputs", []):
        local = str(item.get("local_path", ""))
        if not local or Path(local).is_absolute() or ".." in Path(local).parts:
            raise ValueError("input paths must be project-relative")
        path = (root / local).resolve()
        path.relative_to(root.resolve())
        if not path.is_file():
            raise ValueError(f"missing input: {local}")
        if int(item.get("bytes", -1)) != path.stat().st_size or str(
            item.get("sha256", "")
        ).lower() != _sha256(path):
            raise ValueError(f"input hash/size mismatch: {local}")
        checked.append({"local_path": local, "bytes": path.stat().st_size, "sha256": _sha256(path)})
    if not checked:
        raise ValueError("manifest inputs are empty")
    footprint = manifest.get("expected_added_bytes")
    if "expected_added_bytes" in manifest:
        if type(footprint) is not int or footprint < sum(item["bytes"] for item in checked):
            raise ValueError("expected_added_bytes must be integer peak bytes including all inputs")
        if footprint >= MAX_USAGE_BYTES:
            raise ValueError("expected_added_bytes must be strictly below 50 GiB")
    return {
        "ok": True,
        "job_id": job_id,
        "remote_root": EXPECTED_ROOT,
        "remote_scratch": scratch,
        "inputs": checked,
        "usage_limit_gib": contract["max_usage_gib"],
        "expected_added_bytes": footprint,
        "dynamic_headroom_checked": False,
    }


def read_worker_status(root: Path, *, timeout: float = 30) -> dict[str, Any]:
    """Read worker status through the reusable C:\\paseo control terminal."""

    contract = load_worker_contract(root)
    terminal_id = _terminal_id()
    if not terminal_id:
        created_result, created = _json_command(
            root,
            [
                "terminal",
                "create",
                "--workspace",
                str(contract["workspace_id"]),
                "--cwd",
                EXPECTED_ROOT,
                "--name",
                _CONTROL_NAME,
            ],
        )
        if not created_result.ok or not isinstance(created, dict):
            raise RuntimeError(created_result.stderr or "cannot create Paseo control terminal")
        terminal_id = str(created["id"])
        _save_terminal(terminal_id, str(contract["workspace_id"]))
    marker = f"OC_STATUS_{uuid.uuid4().hex}"
    begin_marker, end_marker = f"{marker}_BEGIN", f"{marker}_END"
    command = (
        "powershell -NoProfile -Command "
        f"\"Write-Output '{begin_marker}'; "
        f"& 'C:\\paseo\\open-composer-worker.ps1' status; Write-Output '{end_marker}'\""
    )
    sent = run_worker_command(
        root, ["terminal", "send-keys", terminal_id, command, "Enter"], timeout=timeout
    )
    if not sent.ok:
        _state_path().unlink(missing_ok=True)
        raise RuntimeError(sent.stderr or "control terminal is unavailable")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, captured = _json_command(root, ["terminal", "capture", terminal_id])
        if isinstance(captured, dict):
            lines = [str(line).strip() for line in captured.get("lines", [])]
            # The terminal echoes the command before it runs. Only standalone
            # delimiters enclose this invocation's response, never scrollback.
            if begin_marker in lines:
                begin = lines.index(begin_marker)
                if end_marker in lines[begin + 1 :]:
                    end = lines.index(end_marker, begin + 1)
                    payload = json.loads("\n".join(lines[begin + 1 : end]))
                    if not isinstance(payload, dict) or "status" not in payload:
                        raise ValueError("worker returned no current status object")
                    return payload
        time.sleep(0.5)
    raise TimeoutError("timed out waiting for worker status")


def worker_preflight(root: Path, *, remote: bool = False) -> dict[str, Any]:
    contract = load_worker_contract(root)
    offer = _offer_path(contract)
    checks = [
        {"name": "wrapper", "ok": _wrapper_path(root, contract).is_file()},
        {
            "name": "offer_file",
            "ok": offer.is_file() and stat.S_IMODE(offer.stat().st_mode) == 0o600,
        },
        {
            "name": "fixed_root",
            "ok": contract["remote_root"].casefold() == EXPECTED_ROOT.casefold(),
        },
        {"name": "usage_limit", "ok": contract["max_usage_gib"] == 50},
    ]
    remote_payload: dict[str, Any] = {}
    if remote:
        status = read_worker_status(root)
        _, workspaces = _json_command(root, ["workspace", "ls"])
        matches = [
            row
            for row in (workspaces if isinstance(workspaces, list) else [])
            if isinstance(row, dict)
            and row.get("workspaceId") == contract.get("workspace_id")
            and isinstance(row.get("cwd"), str)
            and row["cwd"].casefold() == EXPECTED_ROOT.casefold()
        ]
        usage = status.get("usage_bytes")
        checks.extend(
            [
                {
                    "name": "remote_worker_status",
                    "ok": status.get("status") == "ready"
                    and status.get("usage_ok") is True
                    and status.get("paused") is False
                    and status.get("hard_off") is False,
                },
                {
                    "name": "remote_worker_root",
                    "ok": isinstance(status.get("root"), str)
                    and status["root"].casefold() == EXPECTED_ROOT.casefold(),
                },
                {
                    "name": "remote_worker_usage",
                    "ok": type(usage) is int and 0 <= usage < MAX_USAGE_BYTES,
                },
                {"name": "remote_workspace", "ok": len(matches) == 1, "matches": matches},
            ]
        )
        remote_payload = {"worker_status": status, "workspaces": workspaces}
    return {
        "ok": all(check["ok"] for check in checks),
        "contract": contract,
        "checks": checks,
        "remote": remote_payload,
    }
