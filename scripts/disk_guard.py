"""Keep the root partition healthy with registered, verified actions (config/disk-policy.yaml).

Why: the root partition also carries the owner's live service /opt/quantcheck, and a full
disk kills it (/opt/gdrive-agent/README.md). On 2026-10-02 it reached 96%. Rules and the
escalation ladder are in docs/runbook-disk.zh.md.

Subcommands:
    status                  usage, managed paths, holds, unregistered large dirs
                            (writes reports/ops/disk-status.json)
    run [--force] [--dry-run] [--all]
                            act only at or above thresholds.act_pct (or --force) and stop
                            at target_pct; --all (daily hygiene) clears every eligible item.
                            Order: caches -> old /tmp entries -> expired backups (archive to
                            Drive, verify, delete) -> warm datasets (emergency only)
    archive PATH --remote REL
                            upload to Drive and verify, no deletion

Safety rules enforced in code, not only in the policy file:
* a path is deleted only if it is under an allowed root, outside every protected path,
  not a symlink, and not in use by a running process (cwd or open file);
* backups and warm datasets are deleted only after `gdrive upload --wait` succeeded and
  `rclone check --one-way` reported 0 differences; a held task blocks deletion;
* every action is appended to reports/ops/disk-ledger.jsonl.

Cron (the lock file makes overlapping runs exit at once):
    17 * * * *  ... scripts/disk_guard.py run          (threshold-driven)
    40 6 * * *  ... scripts/disk_guard.py run --all    (daily hygiene, then status)
"""

from __future__ import annotations

import argparse
import fcntl
import fnmatch
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/disk-policy.yaml"
LEDGER_PATH = ROOT / "reports/ops/disk-ledger.jsonl"
STATUS_PATH = ROOT / "reports/ops/disk-status.json"
QUEUE_PATH = ROOT / "reports/research/control/autonomous-queue.md"
LOCK_PATH = Path("/tmp/open-composer-disk-guard.lock")
SUSPICIOUS = re.compile(r"(tmp|temp|backup|bak|old|copy|failed|dup|scratch)", re.I)
DONE_PREFIXES = ("done", "cancelled")


# ----------------------------------------------------------------------------- basics
def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def disk_usage(path: str = "/") -> dict[str, float]:
    """Usage the way `df` reports it: used / (used + available to non-root)."""
    st = os.statvfs(path)
    total = st.f_blocks * st.f_frsize
    used = (st.f_blocks - st.f_bfree) * st.f_frsize
    avail = st.f_bavail * st.f_frsize
    return {
        "total_gb": total / 1e9,
        "used_gb": used / 1e9,
        "free_gb": avail / 1e9,
        "pct": 100.0 * used / (used + avail) if used + avail else 0.0,
    }


def du_bytes(path: Path, timeout: int = 900) -> int:
    if not path.exists():
        return 0
    out = subprocess.run(
        ["du", "-sb", "--", str(path)], capture_output=True, text=True, timeout=timeout
    )
    try:
        return int(out.stdout.split()[0])
    except (IndexError, ValueError):
        return 0


def ledger(record: dict[str, Any], path: Path | None = None) -> None:
    path = path or LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps({"ts": now_utc(), **record}, sort_keys=True) + "\n")


def absolute(p: str | Path) -> Path:
    q = Path(p)
    return q if q.is_absolute() else ROOT / q


# ----------------------------------------------------------------------------- safety
def _under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def safe_to_delete(path: Path, policy: dict[str, Any]) -> tuple[bool, str]:
    """Allowed root, not protected, not a symlink, not an allowed root itself."""
    if path.is_symlink():
        return False, "symlink (never followed or deleted)"
    if not path.exists():
        return False, "missing"
    real = Path(os.path.realpath(path))
    roots = [Path(os.path.realpath(r)) for r in policy.get("allowed_roots", [])]
    if not any(_under(real, r) and real != r for r in roots):
        return False, "outside allowed roots"
    for prot in policy.get("protected", []):
        pr = Path(os.path.realpath(absolute(prot)))
        if _under(real, pr) or _under(pr, real):
            return False, f"protected ({prot})"
    return True, "ok"


def in_use(path: Path, proc: Path = Path("/proc")) -> list[int]:
    """PIDs whose cwd or an open file lies under ``path``."""
    real = os.path.realpath(path)
    prefix = real.rstrip("/") + "/"
    pids: list[int] = []
    for entry in proc.iterdir() if proc.exists() else []:
        if not entry.name.isdigit():
            continue
        targets: list[str] = []
        try:
            targets.append(os.readlink(entry / "cwd"))
        except OSError:
            pass
        try:
            for fd in (entry / "fd").iterdir():
                try:
                    targets.append(os.readlink(fd))
                except OSError:
                    continue
        except OSError:
            pass
        if any(t == real or t.startswith(prefix) for t in targets):
            pids.append(int(entry.name))
    return pids


def newest_mtime(path: Path, cap: int = 200_000) -> float:
    """Newest mtime/ctime in a tree (entry itself included); stops after ``cap`` entries."""
    try:
        st = path.lstat()
    except OSError:
        return time.time()
    newest = max(st.st_mtime, st.st_ctime)
    if path.is_dir() and not path.is_symlink():
        n = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for name in dirnames + filenames:
                n += 1
                if n > cap:
                    return time.time()  # too big to judge: treat as fresh
                try:
                    s = os.lstat(os.path.join(dirpath, name))
                except OSError:
                    continue
                newest = max(newest, s.st_mtime, s.st_ctime)
    return newest


def task_status(task_id: str, queue_text: str) -> str | None:
    """Status line of ``### <task_id> ...`` in the autonomous queue, without the prefix."""
    m = re.search(rf"^### {re.escape(task_id)}\b.*?$", queue_text, flags=re.M)
    if not m:
        return None
    after = queue_text[m.end() :]
    nxt = re.search(r"^### ", after, flags=re.M)
    block = after[: nxt.start()] if nxt else after
    s = re.search(r"^- status:\s*(.+)$", block, flags=re.M)
    return s.group(1).strip() if s else None


def held(task_id: str | None, queue_text: str) -> bool:
    if not task_id:
        return False
    status = task_status(task_id, queue_text)
    return status is None or not status.startswith(DONE_PREFIXES)


# ----------------------------------------------------------------------------- items
@dataclass
class Item:
    kind: str  # cache | tmp | backup | warm
    path: Path
    name: str = ""
    command: list[str] | None = None
    env: dict[str, str] = field(default_factory=dict)
    remote: str | None = None
    verify: str = "hash"
    expired: bool = False
    hold_task: str | None = None
    owner: str = ""
    symlink_to: Path | None = None


def tmp_candidates(spec: dict[str, Any], policy: dict[str, Any], now: float) -> list[Item]:
    base = Path(spec.get("path", "/tmp"))
    age = float(spec.get("max_age_days", policy["thresholds"].get("tmp_max_age_days", 7)))
    keep = spec.get("keep_patterns", [])
    archive = spec.get("archive_patterns", [])
    prefix = policy["drive"]["archive_prefix"]
    out = []
    for entry in sorted(base.iterdir()) if base.exists() else []:
        if any(fnmatch.fnmatch(entry.name, pat) for pat in keep):
            continue
        if entry.is_symlink():
            continue
        if now - newest_mtime(entry) < age * 86400:
            continue
        # anything named like a backup goes to Drive (and is verified) before deletion
        remote = (
            f"{prefix}/tmp/{entry.name}"
            if any(fnmatch.fnmatch(entry.name, pat) for pat in archive)
            else None
        )
        out.append(Item(kind="tmp", path=entry, name=f"tmp:{entry.name}", remote=remote))
    return out


def path_matches(rel: str, pattern: str) -> bool:
    """Match a repo-relative path.  ``prefix/**/name`` means: a basename matching ``name``
    at any depth under ``prefix/`` (plain fnmatch would let ``*`` run across ``/``, so
    ``data/**/_*_tmp`` would also hit ``data/research/equity_book/duck_tmp``)."""
    if "**/" in pattern:
        prefix, name = pattern.split("**/", 1)
        if "/" in name:
            raise ValueError(f"unsupported pattern {pattern!r}: use prefix/**/basename")
        return rel.startswith(prefix) and fnmatch.fnmatchcase(rel.rsplit("/", 1)[-1], name)
    return fnmatch.fnmatchcase(rel, pattern)


def find_dirs(pattern: str, base: Path | None = None, max_depth: int = 3) -> list[Path]:
    """Directories under ``base`` (default ``data/``, depth <= ``max_depth``) whose
    repo-relative path matches ``pattern`` (see ``path_matches``).  Symlinks are never
    followed, so the read-only Drive mount behind ``data/sip-hist`` is never walked."""
    base = base or ROOT / "data"
    out: list[Path] = []
    base_depth = len(base.parts)
    for dirpath, dirnames, _ in os.walk(base, followlinks=False):
        depth = len(Path(dirpath).parts) - base_depth
        keep = []
        for d in dirnames:
            full = Path(dirpath) / d
            if full.is_symlink():
                continue
            rel = full.relative_to(ROOT).as_posix()
            if path_matches(rel, pattern):
                out.append(full)
            elif depth + 1 < max_depth:
                keep.append(d)
        dirnames[:] = keep
    return sorted(out)


def backup_items(policy: dict[str, Any], now: float) -> list[Item]:
    max_age = float(policy["thresholds"].get("backup_max_age_days", 7))
    prefix = policy["drive"]["archive_prefix"]
    seen: set[Path] = set()
    out: list[Item] = []
    for spec in policy.get("backups", []):
        paths = [absolute(spec["path"])] if "path" in spec else find_dirs(spec["glob"])
        for p in paths:
            if p in seen or not p.exists() or p.is_symlink():
                continue
            seen.add(p)
            # age = newest mtime/ctime anywhere in the tree, so a backup still being
            # written (or just copied with preserved mtimes) is never expired
            expired = bool(spec.get("expired")) or now - newest_mtime(p) >= max_age * 86400
            rel = p.relative_to(ROOT).as_posix() if _under(p, ROOT) else p.name
            out.append(
                Item(
                    kind="backup",
                    path=p,
                    name=rel,
                    remote=f"{prefix}/{rel}",
                    expired=expired,
                    hold_task=spec.get("hold_task"),
                    owner=spec.get("owner", ""),
                )
            )
    return out


def warm_items(policy: dict[str, Any], year_now: int) -> list[Item]:
    out = []
    mount = Path(policy["drive"]["mount_root"])
    for spec in policy.get("warm", []):
        back = int(spec.get("years_back_min", 2))
        for year in range(2000, year_now - back + 1):
            p = absolute(spec["path"].format(year=year))
            if not p.exists() or p.is_symlink():
                continue
            remote = spec["remote"].format(year=year)
            out.append(
                Item(
                    kind="warm",
                    path=p,
                    name=p.relative_to(ROOT).as_posix(),
                    remote=remote,
                    verify=spec.get("verify", "size-only"),
                    expired=True,
                    symlink_to=mount / remote,
                )
            )
    return out


# ----------------------------------------------------------------------------- actions
def run_cmd(
    cmd: list[str], env: dict[str, str] | None = None, timeout: int = 3600
) -> tuple[int, str]:
    e = dict(os.environ)
    e["PATH"] = f"{Path.home()}/.local/bin:" + e.get("PATH", "")
    e.update(env or {})
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=e)
        return r.returncode, (r.stdout + r.stderr)[-2000:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 99, str(exc)


def upload_strategy(path: Path) -> str:
    """A 1:1 mirror strategy, so `rclone check` can compare file by file (gdrive's automatic
    choice would tar-pack trees of many small files)."""
    n = total = 0
    for dirpath, _, filenames in os.walk(path, followlinks=False):
        for name in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                continue
            n += 1
    return "direct-large" if n and total / n >= 64 * 1024**2 else "direct-small"


def upload_and_verify(item: Item, policy: dict[str, Any], dry: bool) -> tuple[bool, str]:
    remote_rel = item.remote or ""
    if dry:
        return True, f"dry-run: would upload {item.path} -> {remote_rel} and verify ({item.verify})"
    code, out = run_cmd(
        [
            "gdrive",
            "--json",
            "upload",
            str(item.path),
            "--remote",
            remote_rel,
            "--wait",
            "--strategy",
            upload_strategy(item.path),
        ],
        timeout=6 * 3600,
    )
    if code != 0:
        return False, f"upload failed ({code}): {out[-400:]}"
    # rclone checks a single file against its parent directory on the remote
    dst = posixpath.dirname(remote_rel) if item.path.is_file() else remote_rel
    check = [
        "rclone",
        "check",
        str(item.path),
        f"{policy['drive']['remote_root']}/{dst}",
        "--one-way",
        "--checkers",
        "16",
    ]
    if item.verify == "size-only":
        check.append("--size-only")
    code, out = run_cmd(check, timeout=6 * 3600)
    # exact zero: "10 differences found" must not pass as "0 differences found"
    if code != 0 or not re.search(r"\b0 differences found", out):
        return False, f"verify failed ({code}): {out[-400:]}"
    return True, out.strip().splitlines()[-1] if out.strip() else "verified"


def delete_path(item: Item, policy: dict[str, Any], dry: bool) -> tuple[bool, str, int]:
    ok, why = safe_to_delete(item.path, policy)
    if not ok:
        return False, why, 0
    pids = in_use(item.path)
    if pids:
        return False, f"in use by pids {pids[:5]}", 0
    size = du_bytes(item.path)
    if dry:
        return True, "dry-run", size
    if item.path.is_dir():
        shutil.rmtree(item.path)
    else:
        item.path.unlink()
    if item.symlink_to is not None:
        item.path.symlink_to(item.symlink_to)
    return True, "deleted", size


# ----------------------------------------------------------------------------- commands
def cmd_status(policy: dict[str, Any], write: bool = True) -> dict[str, Any]:
    now = time.time()
    queue = QUEUE_PATH.read_text() if QUEUE_PATH.exists() else ""
    u = disk_usage("/")
    managed = []
    for spec in policy.get("caches", []):
        p = Path(spec["path"])
        managed.append(
            {"kind": "cache", "name": spec["name"], "path": str(p), "bytes": du_bytes(p, 300)}
        )
    for it in backup_items(policy, now):
        managed.append(
            {
                "kind": "backup",
                "name": it.name,
                "bytes": du_bytes(it.path, 300),
                "expired": it.expired,
                "hold_task": it.hold_task,
                "held": held(it.hold_task, queue),
                "owner": it.owner,
            }
        )
    # report only: large consumers this tool never cleans (owner tools, system, the repo)
    watch = [{"path": w, "bytes": du_bytes(Path(w), 600)} for w in policy.get("watch", [])]
    registered = {absolute(h).resolve() for h in policy.get("hot", [])}
    registered |= {absolute(b["path"]).resolve() for b in policy.get("backups", []) if "path" in b}
    unregistered = []
    limit = float(policy["thresholds"].get("report_unregistered_gb", 1.0)) * 1e9
    data = ROOT / "data"

    def has_registered_inside(q: Path) -> bool:
        return any(_under(r, q) and r != q for r in registered)

    for p in sorted(data.iterdir()) if data.exists() else []:
        if p.is_symlink() or not p.is_dir():
            continue
        rp = p.resolve()
        # a parent of registered paths (data/sip holds minute/ and daily/): check the rest
        tops = (
            [q for q in sorted(p.iterdir()) if q.is_dir() and not q.is_symlink()]
            if rp not in registered and has_registered_inside(rp)
            else [p]
        )
        for q in tops:
            rq = q.resolve()
            if rq in registered or has_registered_inside(rq):
                continue
            b = du_bytes(q, 600)
            if b >= limit:
                unregistered.append({"path": q.relative_to(ROOT).as_posix(), "bytes": b})
        for q in sorted(p.iterdir()):
            if q.is_dir() and not q.is_symlink() and SUSPICIOUS.search(q.name):
                if q.resolve() in registered or any(
                    it["name"] == q.relative_to(ROOT).as_posix() for it in managed
                ):
                    continue
                b = du_bytes(q, 600)
                if b >= limit:
                    unregistered.append(
                        {
                            "path": q.relative_to(ROOT).as_posix(),
                            "bytes": b,
                            "why": "suspicious name",
                        }
                    )
    status = {
        "generated_at": now_utc(),
        "usage": u,
        "thresholds": policy["thresholds"],
        "managed": managed,
        "watch": watch,
        "unregistered_large": unregistered,
        "state": (
            "emergency"
            if u["pct"] >= policy["thresholds"]["emergency_pct"]
            else "act"
            if u["pct"] >= policy["thresholds"]["act_pct"]
            else "ok"
        ),
    }
    if write:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(status, indent=1, sort_keys=True) + "\n")
    return status


def cmd_run(policy: dict[str, Any], force: bool, dry: bool, all_items: bool = False) -> int:
    th = policy["thresholds"]
    u = disk_usage("/")
    print(
        f"{now_utc()} usage {u['pct']:.1f}% free {u['free_gb']:.1f} GB "
        f"(act {th['act_pct']}%, target {th['target_pct']}%)"
    )
    if u["pct"] < th["act_pct"] and not (force or all_items):
        return 0
    queue = QUEUE_PATH.read_text() if QUEUE_PATH.exists() else ""
    now = time.time()

    def done() -> bool:
        # --all (daily hygiene) clears every eligible cache, tmp entry and expired backup
        return not dry and not all_items and disk_usage("/")["pct"] <= th["target_pct"]

    # 1. caches by command
    for spec in policy.get("caches", []):
        if done():
            break
        if spec.get("command"):
            before = du_bytes(Path(spec["path"]), 300)
            floor = float(spec.get("clean_above_gb", 1.0))
            if all_items and before < floor * 1e9 and disk_usage("/")["pct"] < th["act_pct"]:
                # daily hygiene leaves small caches alone (no daily purge and re-download)
                print(f"cache {spec['name']}: {before / 1e9:.2f} GB < {floor} GB, kept")
                continue
            if dry:
                print(
                    f"dry-run cache {spec['name']}: {' '.join(spec['command'])} "
                    f"({before / 1e9:.2f} GB)"
                )
                continue
            # bounded: a cache lock held by a long job must not stall the guard
            code, out = run_cmd(spec["command"], spec.get("env"), int(spec.get("timeout_s", 900)))
            after = du_bytes(Path(spec["path"]), 300)
            ledger(
                {
                    "action": "cache_clean",
                    "name": spec["name"],
                    "command": spec["command"],
                    "exit": code,
                    "bytes_freed": max(0, before - after),
                }
            )
            print(f"cache {spec['name']}: exit {code}, freed {(before - after) / 1e9:.2f} GB")
    # 2. old /tmp entries
    for spec in policy.get("caches", []):
        if spec.get("command") or done():
            continue
        for it in tmp_candidates(spec, policy, now):
            if done():
                break
            note = None
            if it.remote:
                ok, note = upload_and_verify(it, policy, dry)
                if not ok:
                    ledger({"action": "archive_failed", "path": str(it.path), "note": note})
                    print(f"tmp {it.path}: NOT deleted, {note}")
                    continue
            ok, why, size = delete_path(it, policy, dry)
            if ok and not dry:
                rec = {"action": "delete_tmp", "path": str(it.path), "bytes_freed": size}
                if it.remote:
                    rec.update(remote=it.remote, verification=note)
                ledger(rec)
            print(
                f"tmp {it.path}: {why} ({size / 1e9:.2f} GB)"
                + (f" archived {it.remote}" if it.remote else "")
            )
    # 3. expired backups: archive, verify, delete
    for it in backup_items(policy, now):
        if done():
            break
        if not it.expired:
            continue
        if held(it.hold_task, queue):
            print(f"backup {it.name}: held by {it.hold_task}")
            continue
        ok, why = safe_to_delete(it.path, policy)
        if not ok:
            print(f"backup {it.name}: skipped ({why})")
            continue
        ok, note = upload_and_verify(it, policy, dry)
        if not ok:
            ledger({"action": "archive_failed", "path": it.name, "note": note})
            print(f"backup {it.name}: NOT deleted, {note}")
            continue
        ok, why, size = delete_path(it, policy, dry)
        if ok and not dry:
            ledger(
                {
                    "action": "delete_verified_backup",
                    "path": it.name,
                    "remote": it.remote,
                    "verification": note,
                    "bytes_freed": size,
                    "owner": it.owner,
                }
            )
        print(f"backup {it.name}: {why} ({size / 1e9:.2f} GB) remote {it.remote}")
    # 4. warm datasets, emergency only (a dry run lists them anyway)
    if dry or disk_usage("/")["pct"] >= th["emergency_pct"]:
        for it in warm_items(policy, datetime.now(UTC).year):
            if done():
                break
            ok, note = upload_and_verify(it, policy, dry)
            if not ok:
                ledger({"action": "archive_failed", "path": it.name, "note": note})
                print(f"warm {it.name}: NOT deleted, {note}")
                continue
            ok, why, size = delete_path(it, policy, dry)
            if ok and not dry:
                ledger(
                    {
                        "action": "delete_verified_warm",
                        "path": it.name,
                        "remote": it.remote,
                        "verification": note,
                        "bytes_freed": size,
                        "symlink": str(it.symlink_to),
                    }
                )
            print(f"warm {it.name}: {why} ({size / 1e9:.2f} GB)")
    u2 = disk_usage("/")
    print(f"{now_utc()} after: usage {u2['pct']:.1f}% free {u2['free_gb']:.1f} GB")
    if not dry:
        cmd_status(policy)
    return 0 if dry or u2["pct"] < th["emergency_pct"] else 3


def cmd_archive(policy: dict[str, Any], path: str, remote: str) -> int:
    it = Item(kind="backup", path=absolute(path), name=path, remote=remote)
    ok, note = upload_and_verify(it, policy, dry=False)
    ledger(
        {
            "action": "archive_only" if ok else "archive_failed",
            "path": path,
            "remote": remote,
            "note": note,
        }
    )
    print(note)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    r = sub.add_parser("run")
    r.add_argument("--force", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument(
        "--all", action="store_true", help="daily hygiene: ignore the target, clear all eligible"
    )
    a = sub.add_parser("archive")
    a.add_argument("path")
    a.add_argument("--remote", required=True)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)  # cron log shows progress as it happens
    policy = load_policy()
    LOCK_PATH.touch(exist_ok=True)
    with LOCK_PATH.open() as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another disk_guard run holds the lock; exiting")
            return 0
        if args.cmd == "status":
            s = cmd_status(policy)
            u = s["usage"]
            print(
                f"{s['generated_at']} {s['state']}: {u['pct']:.1f}% used, "
                f"{u['free_gb']:.1f} GB free; "
                f"unregistered large dirs: {len(s['unregistered_large'])}"
            )
            return 0
        if args.cmd == "run":
            return cmd_run(policy, args.force, args.dry_run, args.all)
        return cmd_archive(policy, args.path, args.remote)


if __name__ == "__main__":
    sys.exit(main())
