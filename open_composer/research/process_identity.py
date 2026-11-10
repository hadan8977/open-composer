"""Linux process identities; legacy PID/wall clock records are never upgraded."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def identity(pid: int) -> dict:
    stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {
        "pid": pid,
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "start_ticks": int(stat[19]),
        "pgid": int(stat[2]),
    }


def group_exit_state(saved: dict) -> str:
    """Only prove exited after observing the saved group empty; never signal it.

    Once its leader is gone, membership can no longer establish the original
    group's identity. Any surviving/reused membership or unreadable process is
    therefore uncertainty, even when the leader PID itself has disappeared.
    """
    # Only a session/group leader owns its group. A nonleader identity names
    # one process; its shared parent's group is not a task-owned descendant set.
    if saved["pid"] != saved["pgid"]:
        return "exited"
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit() or int(entry.name) == saved["pid"]:
                continue
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            except FileNotFoundError:
                continue
            if int(fields[2]) == saved["pgid"]:
                return "unknown"
        # Detect a leader PID reused during the group observation.
        leader = Path(f"/proc/{saved['pid']}/stat")
        if leader.exists():
            fields = leader.read_text().rsplit(")", 1)[1].split()
            if fields[0] != "Z" or int(fields[19]) != saved["start_ticks"]:
                return "unknown"
        return "exited"
    except (OSError, ValueError, IndexError):
        return "unknown"


def process_state(saved: dict) -> str:
    if not all(k in saved for k in ("pid", "boot_id", "start_ticks", "pgid")):
        return "legacy_unknown"
    if not all(
        isinstance(saved[k], int) and not isinstance(saved[k], bool) and saved[k] > 0
        for k in ("pid", "start_ticks", "pgid")
    ):
        return "unknown"
    if saved["boot_id"] != Path("/proc/sys/kernel/random/boot_id").read_text().strip():
        return "identity_mismatch"
    try:
        current = identity(int(saved["pid"]))
    except (FileNotFoundError, ProcessLookupError):
        return group_exit_state(saved)
    except (OSError, ValueError):
        return "unknown"
    if any(saved[k] != current[k] for k in current):
        return "identity_mismatch"
    try:
        stat = Path(f"/proc/{saved['pid']}/stat").read_text().rsplit(")", 1)[1].split()
    except FileNotFoundError:
        return group_exit_state(saved)
    return group_exit_state(saved) if stat[0] == "Z" else "running"


def legacy_terminal_received(record: Path, *, proc: Path | None = None) -> bool:
    """Receive one failed PID-only phase; never upgrade its launch identity.

    A phase-local legacy-terminal-reception.json binds the original record,
    current boot and an exact stopped-scope evidence summary. PGID=PID is an
    explicit inference from the old launcher's start_new_session=True.
    """
    proc = Path("/proc") if proc is None else proc

    def small(path: Path) -> bytes:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Terminal evidence must be an ordinary local file")
        with path.open("rb") as stream:
            value = stream.read(65537)
        if len(value) > 65536:
            raise ValueError("Terminal evidence exceeds 64 KiB")
        return value

    try:
        raw = small(record)
        original = json.loads(raw)
        if not isinstance(original, dict) or any(
            key in original for key in ("boot_id", "start_ticks", "pgid")
        ):
            return False
        pid = original.get("pid")
        if type(pid) is not int or pid <= 0:
            return False
        receipt = json.loads(small(record.with_name("legacy-terminal-reception.json")))
        if not isinstance(receipt, dict) or not (
            type(receipt.get("schema_version")) is int
            and receipt["schema_version"] == 1
            and receipt.get("kind") == "legacy_terminal_reception"
            and receipt.get("process_sha256") == hashlib.sha256(raw).hexdigest()
            and receipt.get("received_boot_id")
            == (proc / "sys/kernel/random/boot_id").read_text().strip()
            and type(receipt.get("pid")) is int
            and type(receipt.get("pgid")) is int
            and receipt["pid"] == receipt["pgid"] == pid
            and receipt.get("pgid_basis") == "launcher_start_new_session"
        ):
            return False
        scope = receipt.get("stopped_scope")
        name = receipt.get("evidence_path")
        summary = receipt.get("evidence_summary")
        if not (
            isinstance(scope, str)
            and scope.endswith(".scope")
            and not any(c in scope for c in "/\n\r\0")
            and isinstance(name, str)
            and name not in ("", ".", "..")
            and Path(name).name == name
            and isinstance(summary, str)
            and summary.strip()
            and scope in summary
        ):
            return False
        evidence = small(record.parent / name)
        if receipt.get("evidence_sha256") != hashlib.sha256(evidence).hexdigest():
            return False
        if summary not in evidence.decode("utf-8"):
            return False
        # An absent leader is insufficient: an old group can retain children.
        if (proc / str(pid)).exists():
            return False
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            except FileNotFoundError:
                continue  # another process exited during the observation
            if int(fields[2]) == pid:
                return False
        return not (proc / str(pid)).exists()
    except (OSError, ValueError, TypeError, IndexError, KeyError):
        return False


def signal_group(saved: dict, signum: int) -> bool:
    if process_state(saved) != "running" or saved["pgid"] != saved["pid"]:
        return False
    os.killpg(saved["pgid"], signum)
    return True


def group_members(saved: dict) -> list[dict]:
    """Capture members while the original leader still proves the group identity."""
    if process_state(saved) != "running":
        return []
    members = []
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            member = identity(int(path.parent.name))
            if member["pgid"] == saved["pgid"]:
                members.append(member)
        except (OSError, ValueError):
            continue
    return members


def signal_members(members: list[dict], signum: int) -> None:
    for member in members:
        try:
            if process_state(member) == "running":
                os.kill(member["pid"], signum)
        except ProcessLookupError:
            pass
