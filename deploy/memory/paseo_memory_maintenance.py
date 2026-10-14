#!/usr/bin/env python3
"""Keep Paseo's idle memory footprint bounded without deleting agent history.

2026-10-07 (owner: open-composer must always leave the owner >=500 MB free): background
agents -- scheduled rounds and child agents, recognised by their Paseo labels -- are
archived after --background-idle-hours (2 h in the unit drop-in), top-level sessions keep
--idle-hours (24 h). Source: open-composer deploy/memory/paseo_memory_maintenance.py.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ARCHIVABLE_STATUSES = {"idle", "error"}
KEEP_LABEL = "memory.keep"
BACKGROUND_LABELS = ("paseo.parent-agent-id", "paseo.schedule-id")
# Only processes that live in an agent's own cgroup are reaped. A process merely
# carrying PASEO_AGENT_ID in its environment can belong to another service: on
# 2026-10-07 the owner's pm2-managed "part1" server and tunnel (pm2-root.service)
# matched an archived agent and would have been terminated.
AGENT_CGROUP_MARKERS = (
    "/paseo-daemon.service",
    "/oc.slice/oc-agents.slice/",
    "/oc.slice/oc-interactive.slice/",
)
TRUE_VALUES = {"1", "true", "yes", "on"}


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.lower() in TRUE_VALUES


def is_background(record: dict[str, Any]) -> bool:
    labels = record.get("labels")
    return isinstance(labels, dict) and any(key in labels for key in BACKGROUND_LABELS)


def should_archive(
    record: dict[str, Any], cutoff: datetime, background_cutoff: datetime | None = None
) -> bool:
    if record.get("archivedAt") or record.get("internal"):
        return False
    if str(record.get("lastStatus", "")).lower() not in ARCHIVABLE_STATUSES:
        return False
    labels = record.get("labels")
    if isinstance(labels, dict) and is_truthy(labels.get(KEEP_LABEL)):
        return False
    activity = parse_timestamp(
        record.get("lastActivityAt") or record.get("updatedAt") or record.get("createdAt")
    )
    if background_cutoff is not None and is_background(record):
        cutoff = max(cutoff, background_cutoff)
    return activity is not None and activity <= cutoff


def load_records(agents_dir: Path) -> dict[str, tuple[dict[str, Any], Path]]:
    records: dict[str, tuple[dict[str, Any], Path]] = {}
    for path in agents_dir.glob("*/*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        agent_id = record.get("id")
        if not isinstance(agent_id, str) or not agent_id:
            continue
        previous = records.get(agent_id)
        if previous is None or path.stat().st_mtime > previous[1].stat().st_mtime:
            records[agent_id] = (record, path)
    return records


def run_paseo(paseo_bin: str, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [paseo_bin, *args],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def list_visible_agent_ids(paseo_bin: str) -> set[str]:
    result = run_paseo(paseo_bin, "agent", "ls", "--global", "--json")
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"failed to list agents: {message}")
    try:
        agents = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("agent list returned invalid JSON") from exc
    if not isinstance(agents, list):
        raise RuntimeError("agent list returned an unexpected payload")
    return {
        str(agent["id"])
        for agent in agents
        if isinstance(agent, dict) and isinstance(agent.get("id"), str)
    }


def archive_idle_agents(
    records: dict[str, tuple[dict[str, Any], Path]],
    visible_agent_ids: set[str],
    cutoff: datetime,
    paseo_bin: str,
    dry_run: bool,
    background_cutoff: datetime | None = None,
) -> tuple[int, int]:
    candidates = sorted(
        (
            record
            for agent_id, (record, _path) in records.items()
            if agent_id in visible_agent_ids and should_archive(record, cutoff, background_cutoff)
        ),
        key=lambda record: str(record.get("lastActivityAt") or record.get("updatedAt") or ""),
    )
    archived = 0
    failures = 0
    for record in candidates:
        agent_id = str(record["id"])
        status = str(record.get("lastStatus", "")).lower()
        activity = record.get("lastActivityAt") or record.get("updatedAt")
        if dry_run:
            print(f"would archive agent={agent_id} status={status} last_activity={activity}")
            continue

        # Recheck through the daemon. The archive command itself also refuses a
        # running agent because this script never passes --force.
        inspected = run_paseo(paseo_bin, "agent", "inspect", agent_id, "--json")
        if inspected.returncode:
            failures += 1
            print(f"inspect failed agent={agent_id}: {inspected.stderr.strip()}", file=sys.stderr)
            continue
        try:
            live = json.loads(inspected.stdout)
        except json.JSONDecodeError:
            failures += 1
            print(f"inspect returned invalid JSON agent={agent_id}", file=sys.stderr)
            continue
        if live.get("Archived") or str(live.get("Status", "")).lower() not in ARCHIVABLE_STATUSES:
            print(f"skip changed agent={agent_id} status={live.get('Status')}")
            continue

        result = run_paseo(paseo_bin, "agent", "archive", agent_id, "--json", timeout=180)
        if result.returncode:
            failures += 1
            message = result.stderr.strip() or result.stdout.strip()
            print(f"archive failed agent={agent_id}: {message}", file=sys.stderr)
            continue
        archived += 1
        record["archivedAt"] = datetime.now(UTC).isoformat()
        print(f"archived agent={agent_id} status={status} last_activity={activity}")
    return archived, failures


def read_agent_id(pid: int) -> str | None:
    try:
        entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return None
    for entry in entries:
        if entry.startswith(b"PASEO_AGENT_ID="):
            return entry.partition(b"=")[2].decode("utf-8", errors="replace") or None
    return None


def in_agent_cgroup(pid: int) -> bool:
    try:
        cgroup = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return False
    return any(marker in cgroup for marker in AGENT_CGROUP_MARKERS)


def process_age_seconds(pid: int) -> float | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields = raw[raw.rfind(")") + 2 :].split()
        start_ticks = int(fields[19])
        uptime = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        return max(0.0, uptime - start_ticks / os.sysconf("SC_CLK_TCK"))
    except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError, IndexError):
        return None


def reap_archived_processes(
    records: dict[str, tuple[dict[str, Any], Path]],
    grace_seconds: float,
    paseo_bin: str,
    dry_run: bool,
) -> tuple[int, int]:
    now = datetime.now(UTC)
    archived_ids = {
        agent_id for agent_id, (record, _path) in records.items() if record.get("archivedAt")
    }
    groups: dict[int, dict[str, Any]] = {}
    for proc_path in Path("/proc").glob("[0-9]*"):
        pid = int(proc_path.name)
        agent_id = read_agent_id(pid)
        if agent_id not in archived_ids or not in_agent_cgroup(pid):
            continue
        age = process_age_seconds(pid)
        if age is None:
            continue
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            continue
        group = groups.setdefault(pgid, {"agent_ids": set(), "youngest_age": age, "pids": []})
        group["agent_ids"].add(agent_id)
        group["youngest_age"] = min(group["youngest_age"], age)
        group["pids"].append(pid)

    reaped = 0
    failures = 0
    own_pgid = os.getpgrp()
    for pgid, group in sorted(groups.items()):
        agent_ids = group["agent_ids"]
        if pgid in {1, own_pgid} or len(agent_ids) != 1:
            continue
        if group["youngest_age"] < grace_seconds:
            continue
        agent_id = next(iter(agent_ids))
        archived_at = parse_timestamp(records[agent_id][0].get("archivedAt"))
        if archived_at is None or (now - archived_at).total_seconds() < grace_seconds:
            continue
        # An archived agent can be opened again while this scan is running.
        # Recheck through the daemon immediately before terminating its group.
        inspected = run_paseo(paseo_bin, "agent", "inspect", agent_id, "--json")
        if inspected.returncode:
            # A missing/temporarily unavailable record is not enough evidence
            # to kill a process; leave it for the next maintenance pass.
            continue
        try:
            live = json.loads(inspected.stdout)
        except json.JSONDecodeError:
            continue
        if not live.get("Archived"):
            continue
        age_minutes = int(group["youngest_age"] // 60)
        if dry_run:
            print(
                f"would terminate archived process group agent={agent_id} "
                f"pgid={pgid} age_minutes={age_minutes}"
            )
            continue
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError) as exc:
            failures += 1
            print(f"terminate failed agent={agent_id} pgid={pgid}: {exc}", file=sys.stderr)
            continue
        reaped += 1
        print(f"terminated archived process group agent={agent_id} pgid={pgid}")
    return reaped, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=Path("/root/.paseo/agents"))
    parser.add_argument("--paseo-bin", default="/root/.hermes/node/bin/paseo")
    parser.add_argument("--idle-hours", type=float, default=24.0)
    parser.add_argument("--background-idle-hours", type=float, default=None)
    parser.add_argument("--archived-process-grace-minutes", type=float, default=30.0)
    parser.add_argument(
        "--lock-file", type=Path, default=Path("/run/lock/paseo-memory-maintenance.lock")
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.idle_hours < 1 or args.archived_process_grace_minutes < 5:
        parser.error("idle hours must be >= 1 and process grace must be >= 5 minutes")
    if args.background_idle_hours is not None and args.background_idle_hours < 1:
        parser.error("background idle hours must be >= 1")

    args.lock_file.parent.mkdir(parents=True, exist_ok=True)
    with args.lock_file.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another Paseo memory maintenance run is active")
            return 0

        records = load_records(args.agents_dir)
        try:
            visible_agent_ids = list_visible_agent_ids(args.paseo_bin)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=args.idle_hours)
        background_cutoff = (
            None
            if args.background_idle_hours is None
            else now - timedelta(hours=args.background_idle_hours)
        )
        archived, archive_failures = archive_idle_agents(
            records,
            visible_agent_ids,
            cutoff,
            args.paseo_bin,
            args.dry_run,
            background_cutoff,
        )
        reaped, reap_failures = reap_archived_processes(
            records,
            args.archived_process_grace_minutes * 60,
            args.paseo_bin,
            args.dry_run,
        )
        failures = archive_failures + reap_failures
        print(
            f"summary archived={archived} reaped_groups={reaped} "
            f"failures={failures} dry_run={args.dry_run}"
        )
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
