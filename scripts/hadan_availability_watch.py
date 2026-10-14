#!/usr/bin/env python3
"""Bounded, read-only Hadan probe. Cached availability never authorizes dispatch."""

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
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"ready", "paused", "hard_off", "over_limit", "offline", "unknown"}
USAGE_LIMIT_BYTES = 50 * (1 << 30)


def usage_bytes(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= (1 << 63) - 1 else None


def timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except ValueError:
        return None


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def safe_probe(payload: object) -> dict:
    """Whitelist typed fields; never retain contract, terminal output or errors."""
    payload = payload if isinstance(payload, dict) else {}
    remote = payload.get("remote")
    worker = remote.get("worker_status") if isinstance(remote, dict) else None
    worker = worker if isinstance(worker, dict) else {}
    status = worker.get("status")
    usage = usage_bytes(worker.get("usage_bytes"))
    updated = timestamp(worker.get("updated_at_utc"))
    return {
        "online": True if worker else None,
        "preflight_ok": payload.get("ok") is True,
        "worker_status": status if isinstance(status, str) and status in STATUSES else "unknown",
        "usage_ok": worker.get("usage_ok") is True,
        "usage_bytes": usage,
        "usage_gib": usage / (1 << 30) if usage is not None else None,
        "root_ok": isinstance(worker.get("root"), str)
        and worker["root"].casefold() == r"C:\paseo".casefold(),
        "paused": worker.get("paused") if type(worker.get("paused")) is bool else None,
        "hard_off": worker.get("hard_off") if type(worker.get("hard_off")) is bool else None,
        "worker_updated_at_utc": iso(updated) if updated else None,
    }


def probe_child() -> None:
    permission = authorization(read_json(ROOT / "reports/research/control/owner-compute-hold.json"))
    if not permission["observation_allowed"]:
        print(json.dumps({"probe_result": "failed", "reason": permission["reason"]}))
        return
    sys.path.insert(0, str(ROOT))
    from open_composer.remote.windows_worker import worker_preflight

    try:
        payload = safe_probe(worker_preflight(ROOT, remote=True))
        payload["probe_result"] = "completed"
    except Exception:
        # Exceptions may contain relay offers, terminal scrollback or credentials.
        payload = safe_probe({})
        payload["probe_result"] = "failed"
    print(json.dumps(payload, allow_nan=False))


def run_probe(timeout_seconds: float) -> dict:
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--probe-child"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        return {"probe_result": "timeout"}
    try:
        payload = json.loads(output) if len(output) <= 8192 and process.returncode == 0 else {}
        return payload if isinstance(payload, dict) else {"probe_result": "failed"}
    except json.JSONDecodeError:
        return {"probe_result": "failed"}


def summarize(probe: dict, now: datetime, config: dict) -> dict:
    """Revalidate even child output before persistence or a recovery event."""
    updated = timestamp(probe.get("worker_updated_at_utc"))
    fresh = (
        updated is not None
        and -30 <= (now - updated).total_seconds() <= config["freshness_seconds"]
    )
    usage = usage_bytes(probe.get("usage_bytes"))
    worker_status = probe.get("worker_status")
    worker_status = (
        worker_status if isinstance(worker_status, str) and worker_status in STATUSES else "unknown"
    )
    result = probe.get("probe_result")
    result = (
        result
        if isinstance(result, str) and result in {"completed", "failed", "timeout"}
        else "failed"
    )
    ready = (
        result == "completed"
        and probe.get("online") is True
        and probe.get("preflight_ok") is True
        and worker_status == "ready"
        and probe.get("usage_ok") is True
        and usage is not None
        and usage < USAGE_LIMIT_BYTES
        and probe.get("root_ok") is True
        and probe.get("paused") is False
        and probe.get("hard_off") is False
        and fresh
    )
    status = worker_status
    if result != "completed":
        status = "unknown"
        reason = "probe_timeout" if result == "timeout" else "probe_failed"
    elif probe.get("hard_off") is True:
        status, reason = "hard_off", "owner_hard_off"
    elif probe.get("paused") is True:
        status, reason = "paused", "owner_paused"
    elif usage is not None and usage >= USAGE_LIMIT_BYTES:
        status, reason = "over_limit", "usage_at_or_above_50_gib"
    elif worker_status != "ready":
        reason = "worker_not_ready"
    elif ready:
        reason = "fresh_remote_preflight_ready"
    else:
        status, reason = "unknown", "readiness_not_verified"
    return {
        "status": status,
        "reason": reason,
        "online": probe.get("online") if type(probe.get("online")) is bool else None,
        "ready_as_of_probe": ready,
        "worker_status": worker_status,
        "usage_ok": probe.get("usage_ok") is True,
        "usage_bytes": usage,
        "usage_gib": usage / (1 << 30) if usage is not None else None,
        "worker_updated_at_utc": iso(updated) if updated else None,
        "preflight_ok": probe.get("preflight_ok") is True,
        "probe_result": result,
        "observed_at_utc": iso(now),
        "fresh_until_utc": iso(updated + timedelta(seconds=config["freshness_seconds"]))
        if updated
        else None,
        "dispatch_requires_fresh_preflight": True,
        "training_allowed": False,
        "automatic_dispatch": False,
    }


def read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def authorization(hold: dict) -> dict:
    """Resolve only this observer's permissions, without granting task admission."""
    hadan = hold.get("hadan")
    hadan = hadan if isinstance(hadan, dict) else {}
    monitoring = hadan.get("availability_monitoring")
    monitoring = monitoring if isinstance(monitoring, dict) else {}
    training = hold.get("training")
    training = training if isinstance(training, dict) else {}
    active_scope = hold.get("research_paused") is False
    observation = active_scope and monitoring.get("authorized") is True
    research = active_scope and hadan.get("research_allowed") is True
    if hold.get("research_paused") is True:
        reason = "owner_research_paused"
    elif not active_scope:
        reason = "owner_authorization_unknown"
    elif not observation:
        reason = "availability_observation_not_authorized"
    else:
        reason = "availability_observation_authorized"
    return {
        "observation_allowed": observation,
        "research_authorized": research,
        "training_authorized": research and training.get("training_allowed") is True,
        "reason": reason,
    }


def interval_minutes(now: datetime, config: dict) -> int:
    local = now.astimezone(ZoneInfo(config["timezone"]))
    daytime = (
        local.weekday() in config["priority_weekdays"]
        and config["priority_start_hour"] <= local.hour < config["priority_end_hour"]
    )
    return config["priority_interval_minutes"] if daytime else config["other_interval_minutes"]


def watch(root: Path, config: dict, *, now: datetime | None = None, probe=run_probe) -> dict:
    fixed_now = now
    now = now or datetime.now(UTC)
    paths = {}
    for key in ("state_path", "event_path", "lock_path"):
        path = (root / config[key]).resolve()
        path.relative_to(root.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        paths[key] = path
    with paths["lock_path"].open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"action": "overlap_skipped"}
        permission = authorization(
            read_json(root / "reports/research/control/owner-compute-hold.json")
        )
        if not permission["observation_allowed"]:
            return {
                "action": "authorization_skipped",
                **permission,
                "ready_as_of_probe": False,
                "training_allowed": False,
                "coordination_requested": False,
                "automatic_dispatch": False,
            }
        previous = read_json(paths["state_path"])
        last = timestamp(previous.get("observed_at_utc"))
        interval = interval_minutes(now, config)
        if last and 0 <= (now - last).total_seconds() < interval * 60:
            return {
                "action": "not_due",
                "next_probe_at_utc": iso(last + timedelta(minutes=interval)),
            }
        result = probe(config["probe_timeout_seconds"])
        current = summarize(result, fixed_now or datetime.now(UTC), config)
        current.update({"schema_version": 1, "endpoint": "hadan", "interval_minutes": interval})
        recovery = current["ready_as_of_probe"] and previous.get("ready_as_of_probe") is not True
        # Owner permissions may change while the bounded probe is running.
        permission = authorization(
            read_json(root / "reports/research/control/owner-compute-hold.json")
        )
        admitted = permission["research_authorized"]
        training_authorized = permission["training_authorized"]
        current["observation_allowed"] = permission["observation_allowed"]
        current["research_authorized"] = admitted
        current["training_authorized"] = training_authorized
        current["training_allowed"] = bool(
            permission["observation_allowed"]
            and training_authorized
            and current["ready_as_of_probe"]
        )
        newly_training_ready = (
            current["training_allowed"] and previous.get("training_allowed") is not True
        )
        current["coordination_requested"] = bool(
            permission["observation_allowed"] and admitted and (recovery or newly_training_ready)
        )
        current["coordination_scope"] = (
            "already_authorized_research_including_training"
            if training_authorized
            else "already_authorized_nontraining_tasks_only"
            if admitted
            else "availability_observation_only"
        )
        changed = any(
            previous.get(key) != current[key]
            for key in (
                "status",
                "reason",
                "online",
                "ready_as_of_probe",
                "worker_status",
                "observation_allowed",
                "research_authorized",
                "training_authorized",
                "training_allowed",
                "coordination_scope",
            )
        )
        temporary = paths["state_path"].with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(current, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        temporary.replace(paths["state_path"])
        if changed:
            event = {
                key: current[key]
                for key in (
                    "observed_at_utc",
                    "status",
                    "reason",
                    "ready_as_of_probe",
                    "training_authorized",
                    "training_allowed",
                    "coordination_requested",
                )
            }
            with paths["event_path"].open("a", encoding="utf-8") as events:
                events.write(json.dumps(event, allow_nan=False) + "\n")
        return {"action": "probed", **current}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "config/hadan-availability-watch.json"
    )
    parser.add_argument("--probe-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe_child:
        probe_child()
        return
    config = read_json(args.config)
    if not 1 <= config.get("probe_timeout_seconds", 0) <= 45:
        raise SystemExit("probe_timeout_seconds must be between 1 and 45")
    if not 1 <= config.get("freshness_seconds", 0) <= 300:
        raise SystemExit("freshness_seconds must be between 1 and 300")
    for key in ("priority_interval_minutes", "other_interval_minutes"):
        if not 1 <= config.get(key, 0) <= 1440:
            raise SystemExit("probe intervals must be between 1 and 1440 minutes")
    print(json.dumps(watch(ROOT, config), allow_nan=False))


if __name__ == "__main__":
    main()
