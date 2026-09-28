#!/usr/bin/env python3
"""Generic Modal runner: ship allowlisted code, sync data, run, fetch results.

Why this exists (2026-09-28): this box has 3.9 GB RAM and no GPU. Panel-scale
factor builds, model training, and batch backtests either don't fit or run
one-at-a-time for hours. The owner approved Modal's $30/month free credit for
that class of job. This script is the one door all of those jobs go through:
budget check -> allowlisted code upload -> data volume sync -> run with
threads matched to the requested cores -> results copied back -> actual cost
logged.

Usage:
    python3 scripts/modal_run.py --job NAME --cpu 4 --memory-gib 16 \\
        --timeout-min 60 [--gpu T4] \\
        [--data data/sip/daily ...] --out reports/research/iterations/<id> \\
        [--fetch-to reports/research/control/scratch/<id>] [--shards N] \\
        -- uv run python scripts/<script>.py <args>

`--out` is the path (relative to the repo root) that the command is expected
to write to *inside the container* -- for most of this repo's scripts that is
the same fixed `reports/research/iterations/<iter_id>` directory they always
write to, so ordinarily `--out` is also where you want the result to land
locally. Pass `--fetch-to` when you want the container's output landed
somewhere else locally (e.g. a scratch parity check that must not overwrite a
committed iteration).

`{shard}` / `{nshards}` inside the command tokens are substituted per shard
before it runs (0-indexed shard, then the total shard count) -- e.g. a batch
script that partitions its own candidate list by `--shard {shard} --nshards
{nshards}`. With `--shards N > 1`, N containers run in parallel
(`Function.starmap`); each shard's own copy of `--out` is fetched to
`<local-out>/shard_<i>/`, and a failure in one shard is reported, never
silently dropped.

Every launch calls `scripts/modal_budget.py check` first, with the worst case
multiplied by `--shards` (`--count`) since each shard is billed
independently; exit code 2 there aborts before anything is uploaded.

Code is shipped by allowlist, never a full repo copy: `open_composer/`,
`scripts/`, `strategy_specs/`, `capabilities/`, `config/` (excluding any
`*.yaml`/`*.yml` that is not `*.yaml.example`/`*.yml.example`, and excluding
any filename that looks like a secret/token/credential/key file),
`pyproject.toml`, `uv.lock`, plus `--extra-dir` for anything else the target
script imports. `.env*`, `data/`, `reports/`, `logs/`, `.git/`, `*.pem`,
`*.key`, and `~/.modal.toml` are never shipped. Every shipped text file is
scanned for secret-looking values before upload (real values, not just code
that names an env var -- see `scan_file_for_secrets`); a match aborts the
whole launch with no upload.

`--data` paths (files or directories, relative to the repo root -- market
data under `data/`, but also e.g. a small `reports/research/iterations/<id>/
candidate-manifest.json` an iteration script reads before it will run) are
synced to the `oc-data` Modal volume under that same relative path, and each
one is symlinked back at the identical path inside the container
(`/root/repo/<relpath>` -> the volume mount), so the target script's own
relative paths resolve unchanged with no code edits. A path is skipped if its
recursive (size, mtime) map already matches
`reports/research/control/modal-data-manifest.json` -- i.e. this is
directory-level (or single-file), not per-file, incremental sync. Volume
storage is billed at $0.09/GiB-month outside this script's own accounting;
delete stale data with `modal volume rm oc-data <path> -r` when a campaign
ends.

Container threads (`POLARS_MAX_THREADS`, `OMP_NUM_THREADS`,
`MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `NUMEXPR_MAX_THREADS`,
`OC_NUM_THREADS`) are all set to `2 * cpu`, because the container reports the
Modal host's full core count via `os.cpu_count()` regardless of the `--cpu`
requested.

stdout/stderr from every shard is saved to `logs/modal-<job>-<UTC
stamp>.log`. After the run, actual wall time and a cost estimate (measured
wall time, not the worst-case timeout) are appended to
`reports/research/control/modal-ledger-actuals.jsonl`, keyed to the same
`--job` name and timestamp as the pre-launch ledger row in
`modal-ledger.jsonl`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import modal_budget  # noqa: E402

APP_TEMPLATE = ROOT / "scripts" / "modal_app.py"
MANIFEST_PATH = ROOT / "reports/research/control/modal-data-manifest.json"
LEDGER_ACTUALS_PATH = ROOT / "reports/research/control/modal-ledger-actuals.jsonl"

# ---------------------------------------------------------------------------
# Allowlist + secret scan (pure; no network, safe to unit test)
# ---------------------------------------------------------------------------

ALLOW_TOP_DIRS = ["open_composer", "scripts", "strategy_specs", "capabilities", "config"]
ALWAYS_FILES = ["pyproject.toml", "uv.lock"]
EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
}
EXCLUDE_FILE_SUFFIXES = {".pyc", ".pyo"}
EXCLUDE_FILE_GLOBS = {".env", ".env.local"}
KEY_SECRET_TOKEN_NAME_RE = re.compile(r"(secret|token|credential|private[-_]?key)", re.IGNORECASE)

# Keyword scan for real secret values shipped in code/config. Naming an env
# var (e.g. `os.environ["ALPACA_API_KEY"]`) is fine and common; an *assigned
# literal value* is not. `-----BEGIN ... PRIVATE KEY-----` headers are never
# safe (checked separately, see `_PRIVATE_KEY_HEADER_RE`).
SECRET_KEYWORDS = ["APCA", "ALPACA_", "DEEPSEEK", "sk-", "api_key"]
SAFE_LINE_MARKERS = (
    "os.environ",
    "os.getenv",
    "getenv(",
    "ENV[",
    "process.env",
    ".env(",
    "environ.get",
)
# For each keyword, only a *quoted value assigned right after it* counts --
# `KEYWORD... = "value"` or `"KEYWORD...": "value"` -- not the keyword
# appearing anywhere on the line. This is what actually distinguishes an
# assigned secret from the many merely-descriptive strings this repo's own
# code contains, e.g. a `"provider": "alpaca_sip_daily_archive+..."` value, or
# a status tag like `"delayed30_offensive_alpaca_order_support"`, or English
# prose that happens to contain "sk-" (as in "risk-adjusted") -- none of
# those have an assignment operator directly after the keyword. The captured
# value additionally has to contain a digit: real keys/tokens mix letters and
# digits, readable snake_case status labels usually don't.
_SECRET_ASSIGN_PATTERNS: dict[str, re.Pattern[str]] = {
    kw: re.compile(
        re.escape(kw) + r"""[A-Za-z0-9_]*\s*[:=]\s*['"]([A-Za-z0-9_\-/+]{16,})['"]""",
        re.IGNORECASE,
    )
    for kw in SECRET_KEYWORDS
}


def _looks_like_secret_value(value: str) -> bool:
    return any(c.isdigit() for c in value)


TEXT_SUFFIXES = {
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".txt",
    ".toml",
    ".cfg",
    ".ini",
    ".sh",
    ".example",
}


def config_file_allowed(path: Path) -> bool:
    """`config/` only: drop non-`.example` yaml and key/secret/token-named files."""
    name = path.name
    if KEY_SECRET_TOKEN_NAME_RE.search(name):
        return False
    if name.endswith((".yaml", ".yml")) and not name.endswith((".yaml.example", ".yml.example")):
        return False
    return True


def _excluded(path: Path) -> bool:
    if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
        return True
    if path.suffix in EXCLUDE_FILE_SUFFIXES:
        return True
    return path.name in EXCLUDE_FILE_GLOBS


def iter_allowlisted_files(root: Path, extra_dirs: list[str] | None = None) -> list[Path]:
    """Every file that would be shipped to Modal, in allowlist order."""
    files: list[Path] = []
    for top in [*ALLOW_TOP_DIRS, *(extra_dirs or [])]:
        base = root / top
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_dir() or _excluded(p):
                continue
            if top == "config" and not config_file_allowed(p):
                continue
            files.append(p)
    for name in ALWAYS_FILES:
        p = root / name
        if p.is_file():
            files.append(p)
    # de-dupe (an --extra-dir could overlap an allow-listed dir) and sort
    return sorted(set(files))


_PRIVATE_KEY_HEADER_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def scan_file_for_secrets(path: Path) -> list[str]:
    """Return human-readable violations; [] if the file looks clean."""
    if path.suffix not in TEXT_SUFFIXES and path.name not in ALWAYS_FILES:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    violations: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _PRIVATE_KEY_HEADER_RE.search(line):
            violations.append(f"{path}:{lineno}: private key header")
            continue
        if any(marker in line for marker in SAFE_LINE_MARKERS):
            continue
        for kw, pattern in _SECRET_ASSIGN_PATTERNS.items():
            m = pattern.search(line)
            if m and _looks_like_secret_value(m.group(1)):
                violations.append(f"{path}:{lineno}: possible secret value near {kw!r}")
                break
    return violations


def scan_for_secrets(paths: list[Path]) -> list[str]:
    violations: list[str] = []
    for p in paths:
        violations.extend(scan_file_for_secrets(p))
    return violations


# ---------------------------------------------------------------------------
# Command substitution (pure)
# ---------------------------------------------------------------------------


def substitute_command(argv: list[str], shard: int, nshards: int) -> list[str]:
    return [tok.replace("{shard}", str(shard)).replace("{nshards}", str(nshards)) for tok in argv]


# ---------------------------------------------------------------------------
# Data manifest / incremental sync (stat scan is pure; upload is not)
# ---------------------------------------------------------------------------


def scan_dir_stat(path: Path) -> dict[str, list[float]]:
    """relpath (within `path`) -> [size, mtime] for every file under it."""
    out: dict[str, list[float]] = {}
    if path.is_file():
        st = path.stat()
        return {path.name: [float(st.st_size), st.st_mtime]}
    for p in sorted(path.rglob("*")):
        if p.is_dir() or _excluded(p):
            continue
        st = p.stat()
        out[str(p.relative_to(path))] = [float(st.st_size), st.st_mtime]
    return out


def needs_sync(local_stat: dict[str, list[float]], manifest_entry: Any) -> bool:
    """True unless the manifest already has an identical (size, mtime) map."""
    return manifest_entry != local_stat


def read_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(manifest: dict[str, Any], path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def sync_data(data_paths: list[str], manifest_path: Path = MANIFEST_PATH) -> list[str]:
    """Upload each stale `--data` path to the `oc-data` volume; return the ones synced.

    The volume mirrors the repo layout: a `--data` path lands at the same
    relative path inside the volume, so the container can symlink
    `/root/repo/<relpath>` straight to it (see `scripts/modal_app.py`).
    """
    manifest = read_manifest(manifest_path)
    synced: list[str] = []
    for rel in data_paths:
        local = ROOT / rel
        if not local.exists():
            raise SystemExit(f"--data path not found: {rel}")
        stat = scan_dir_stat(local)
        if not needs_sync(stat, manifest.get(rel)):
            continue
        # No trailing slash: `modal volume put` then mirrors `local`'s content (file
        # or directory) directly at `rel`, matching the container-side symlink target.
        subprocess.run(
            ["modal", "volume", "put", "oc-data", str(local), rel, "-f"],
            check=True,
        )
        manifest[rel] = stat
        synced.append(rel)
    write_manifest(manifest, manifest_path)
    return synced


# ---------------------------------------------------------------------------
# Staging (impure: copies files to a temp dir)
# ---------------------------------------------------------------------------


def stage_code(dest_dir: Path, extra_dirs: list[str] | None = None) -> list[Path]:
    files = iter_allowlisted_files(ROOT, extra_dirs)
    violations = scan_for_secrets(files)
    if violations:
        raise SystemExit(
            "refusing to ship: possible secret(s) found in allowlisted files:\n"
            + "\n".join(violations)
        )
    for f in files:
        rel = f.relative_to(ROOT)
        out = dest_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
    return files


# ---------------------------------------------------------------------------
# CLI / orchestration
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    if "--" not in argv:
        raise SystemExit("usage: modal_run.py --job NAME ... -- <command>")
    split = argv.index("--")
    own_argv, command = argv[:split], argv[split + 1 :]
    if not command:
        raise SystemExit("no command given after --")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--job", required=True)
    parser.add_argument("--cpu", type=float, required=True)
    parser.add_argument("--memory-gib", type=float, required=True)
    parser.add_argument("--timeout-min", type=float, required=True)
    parser.add_argument("--gpu", choices=sorted(modal_budget.GPU_PER_HOUR))
    parser.add_argument("--data", action="append", default=[])
    parser.add_argument("--out", required=True)
    parser.add_argument("--fetch-to", default=None)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--extra-dir", action="append", default=[])
    ns = parser.parse_args(own_argv)
    if ns.shards < 1:
        raise SystemExit("--shards must be >= 1")
    return ns, command


def check_budget(ns: argparse.Namespace) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "modal_budget.py"),
        "check",
        "--job",
        ns.job,
        "--cpu",
        str(ns.cpu),
        "--memory-gib",
        str(ns.memory_gib),
        "--timeout-min",
        str(ns.timeout_min),
        "--count",
        str(ns.shards),
    ]
    if ns.gpu:
        cmd += ["--gpu", ns.gpu]
    proc = subprocess.run(cmd)
    if proc.returncode == 2:
        raise SystemExit(f"modal_budget refused job {ns.job!r} -- see output above")
    if proc.returncode != 0:
        raise SystemExit(f"modal_budget check exited {proc.returncode} unexpectedly")


def append_actuals(row: dict[str, Any], path: Path = LEDGER_ACTUALS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def main(argv: list[str] | None = None) -> int:
    ns, command = parse_args(argv if argv is not None else sys.argv[1:])
    check_budget(ns)

    local_dest = ROOT / (ns.fetch_to or ns.out)
    local_dest.mkdir(parents=True, exist_ok=True)

    synced = sync_data(ns.data) if ns.data else []

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = ROOT / "logs" / f"modal-{ns.job}-{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    threads = max(1, int(2 * ns.cpu))
    shard_commands = [
        {"argv": substitute_command(command, i, ns.shards), "out_rel": ns.out}
        for i in range(ns.shards)
    ]

    with tempfile.TemporaryDirectory(prefix="oc-modal-stage-") as tmp:
        stage_dir = Path(tmp)
        shipped = stage_code(stage_dir, ns.extra_dir)
        env = dict(os.environ)
        env.update(
            {
                "OC_JOB": ns.job,
                "OC_CPU": str(ns.cpu),
                "OC_MEMORY_GIB": str(ns.memory_gib),
                "OC_TIMEOUT_MIN": str(ns.timeout_min),
                "OC_GPU": ns.gpu or "",
                "OC_STAGE_DIR": str(stage_dir),
                "OC_THREADS": str(threads),
                "OC_DATA_DIRS": json.dumps(ns.data),
                "OC_OUT_DIR": str(local_dest.resolve()),
                "OC_LOG_PATH": str(log_path),
                "OC_SHARD_COMMANDS": json.dumps(shard_commands),
            }
        )
        print(
            f"[modal_run] job={ns.job} shipping {len(shipped)} files, "
            f"synced data paths: {synced or 'none'}",
            file=sys.stderr,
        )
        t0 = time.time()
        proc = subprocess.run(["modal", "run", str(APP_TEMPLATE)], cwd=str(ROOT), env=env)
        wall_seconds = time.time() - t0

    shards_path = local_dest / "_modal_shards.json"
    shard_summary = json.loads(shards_path.read_text()) if shards_path.exists() else []
    failed = [s for s in shard_summary if s.get("returncode") != 0]

    actual_cost = modal_budget.worst_case_usd(
        ns.cpu, ns.memory_gib, wall_seconds / 60.0, ns.gpu, count=ns.shards
    )
    append_actuals(
        {
            "at": datetime.now(UTC).isoformat(),
            "job": ns.job,
            "wall_seconds": round(wall_seconds, 1),
            "shards": ns.shards,
            "actual_cost_usd_estimate": actual_cost,
            "modal_run_exit_code": proc.returncode,
            "shards_failed": len(failed),
        }
    )

    ok = proc.returncode == 0 and not failed
    if proc.returncode != 0:
        print(f"[modal_run] `modal run` exited {proc.returncode}", file=sys.stderr)
    if failed:
        print(
            f"[modal_run] {len(failed)}/{len(shard_summary)} shard(s) failed: {failed}",
            file=sys.stderr,
        )
    print(
        f"[modal_run] wall={wall_seconds:.1f}s actual_cost_usd~={actual_cost} "
        f"log={log_path} out={local_dest}",
        file=sys.stderr,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
