"""Spend guard for Modal jobs: refuse any launch whose worst case could exceed the monthly cap.

Why this exists (2026-09-28): the owner granted Modal's $30/month free credit for
factor replication and model training, with the instruction not to overspend.
The workspace spend limit is set in Modal's dashboard (not reachable from the
CLI), so this is the second, local guard:

* worst case of a job = timeout x (cores x CPU rate + GiB x memory rate + GPU rate);
* Modal's billing report only covers completed hourly intervals, so jobs started
  in the last few hours are counted from this ledger at their worst case, or at
  a verified completed usage upper bound within the original reservation horizon;
* a launch is allowed only if billed + unbilled worst cases + the new worst case
  stays under the cap ($25, leaving $5 of the $30 credit as margin).

Usage:
    python scripts/modal_budget.py status
    python scripts/modal_budget.py check --job NAME --cpu 8 --memory-gib 32 \
        --timeout-min 120 [--gpu T4] [--count 3]
    python scripts/modal_budget.py settle --evidence ROOT_REVIEWED_TERMINAL_JSON

`--count` (default 1) multiplies the worst case, for launches that fan out to
that many parallel containers (e.g. `scripts/modal_run.py --shards N`) -- each
shard is billed independently, so N shards cost N times one shard's worst case.

`check` exits 0 and appends a ledger row when allowed, exits 2 when refused.
Every Modal function must set `timeout=` equal to the `--timeout-min` it was checked with.
`settle` is offline and appends a typed zero-cost event; the original reservation
remains intact. New launches still require the normal billing-backed `check`.
Ledger decisions and appends share the ledger's own sidecar lock, independently
of any caller's outer allocation lock.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "reports" / "research" / "control" / "modal-ledger.jsonl"
MONTHLY_CAP_USD = 25.0
UNBILLED_LOOKBACK = timedelta(hours=3)

# `modal billing rates`, read 2026-09-28. Per hour; a core is a physical core (2 vCPU).
CPU_PER_CORE_HOUR = 0.0473
MEMORY_PER_GIB_HOUR = 0.008
GPU_PER_HOUR = {
    "T4": 0.59,
    "L4": 0.80,
    "A10G": 1.10,
    "L40S": 1.95,
    "A100-40GB": 2.10,
    "A100-80GB": 2.50,
    "H100": 3.95,
}


def worst_case_usd(
    cpu: float, memory_gib: float, timeout_min: float, gpu: str | None, count: int = 1
) -> float:
    hourly = cpu * CPU_PER_CORE_HOUR + memory_gib * MEMORY_PER_GIB_HOUR
    if gpu:
        hourly += GPU_PER_HOUR[gpu]
    return round(hourly * timeout_min / 60.0 * count, 4)


def _cost(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace("$", "").replace(",", "").strip() or 0)
        except ValueError:
            return 0.0
    return 0.0


def billed_this_month() -> float:
    """Sum of Modal's reported cost for the current month (complete intervals only)."""
    proc = subprocess.run(
        ["modal", "billing", "report", "--for", "this month", "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    rows = json.loads(proc.stdout or "[]")
    if isinstance(rows, dict):
        rows = rows.get("rows") or rows.get("data") or []
    total = 0.0
    for row in rows:
        for key in ("cost", "Cost"):
            if key in row:
                total += _cost(row[key])
                break
    return round(total, 4)


def read_ledger(path: Path = LEDGER) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


@contextmanager
def ledger_lock(path: Path) -> Iterator[None]:
    """Serialize ledger readers/writers without reacquiring a caller's outer flock."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _append_ledger(row: dict[str, Any]) -> None:
    """Persist the reservation/event before releasing the ledger lock or granting a launch."""
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


SETTLEMENT = "completed_reservation_settlement"


def reservation_sha256(row: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _bound_json(binding: dict[str, Any]) -> dict[str, Any]:
    path = ROOT / binding["path"]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("changed terminal evidence binding")
    return json.loads(raw)


def _finite_nonnegative(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("numeric completed bound required")
    if not math.isfinite(value) or value < 0:
        raise ValueError("invalid completed bound")
    return float(value)


def _aware_time(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("timezone required for terminal evidence")
    return result


def completed_settlement(
    rows: list[dict[str, Any]], evidence_binding: dict[str, Any], now: datetime
) -> dict[str, Any]:
    """Price a Root-reviewed, hash-bound stopped job without editing its reservation."""
    evidence = _bound_json(evidence_binding)
    if (
        evidence.get("schema_version") != 1
        or evidence.get("event_type") != "completed_reservation_terminal_evidence"
        or evidence.get("reviewer") != "/root"
        or evidence.get("verdict") != "accept_completed_reservation_billing_upper_bound"
    ):
        raise ValueError("Root reviewed terminal evidence required")
    original_binding = evidence["reservation"]
    originals = [
        row
        for row in rows
        if row.get("event_type") != SETTLEMENT
        and reservation_sha256(row) == original_binding["canonical_sha256"]
    ]
    if len(originals) != 1:
        raise ValueError("unique exact original reservation required")
    original = originals[0]
    if any(original[k] != original_binding[k] for k in ("job", "at")):
        raise ValueError("wrong original job or timestamp")
    provider = _bound_json(evidence["provider_observation"])
    runtime = _bound_json(evidence["runtime_receipt"])
    operator = _bound_json(evidence["operator_receipt"])
    driver = evidence["driver_log"]
    driver_raw = (ROOT / driver["path"]).read_bytes()
    if (
        hashlib.sha256(driver_raw).hexdigest() != driver["sha256"]
        or driver["sha256"] != operator["driver_log_sha256"]
        or set(
            re.findall(
                r"https://modal\.com/apps/[^/\s]+/[^/\s]+/(ap-[A-Za-z0-9]+)", driver_raw.decode()
            )
        )
        != {evidence["app_id"]}
    ):
        raise ValueError("operator driver does not bind the exact stopped app")
    provider_rows = [r for r in provider["actual_cli_rows"] if r["app_id"] == evidence["app_id"]]
    if provider.get("app") != evidence["app_id"] or len(provider_rows) != 1:
        raise ValueError("exact provider app observation required")
    app = provider_rows[0]
    if app["state"] != "stopped" or str(app["tasks"]) != "0":
        raise ValueError("active job cannot settle")
    created, stopped = _aware_time(app["created_at"]), _aware_time(app["stopped_at"])
    observed = _aware_time(provider["utc"])
    if not (_aware_time(original["at"]) <= created <= stopped <= observed <= now):
        raise ValueError("invalid provider terminal clock")
    if (
        runtime["run_id"] != original["job"]
        or operator["run_id"] != original["job"]
        or runtime["runtime_manifest_sha256"] != operator["runtime_manifest_sha256"]
        or not runtime["runtime_manifest_sha256"]
        or runtime["status"]
        not in ("complete", "completed", "complete_admitted_scope", "failed_retained")
        or not isinstance(operator["driver_returncode"], int)
    ):
        raise ValueError("native terminal receipts do not bind original job")
    declared = runtime["resources_declared"]
    gpu = "A10" if original["gpu"] == "A10G" else original["gpu"]
    if (
        declared["cpu_limit"] != original["cpu"]
        or declared["memory_limit_MiB"] != original["memory_gib"] * 1024
        or declared["gpu"] != gpu
        or declared["max_containers"] != original.get("count", 1)
        or declared["timeout_seconds"] != original["timeout_min"] * 60
        or declared["retries"] != 0
    ):
        raise ValueError("native resources differ from reservation")
    upper = _finite_nonnegative(evidence["completed_wall_seconds_upper_bound"])
    observed_upper = max(
        (stopped - created).total_seconds(),
        _finite_nonnegative(runtime["wall_seconds"]),
        _finite_nonnegative(operator["operator_wall_seconds"]),
    )
    if upper < observed_upper or upper > original["timeout_min"] * 60:
        raise ValueError("completed upper bound below observed usage or above reservation")
    expected = worst_case_usd(
        original["cpu"],
        original["memory_gib"],
        original["timeout_min"],
        original["gpu"],
        original.get("count", 1),
    )
    if original["worst_case_usd"] != expected:
        raise ValueError("original reservation pricing differs")
    hourly = original["cpu"] * CPU_PER_CORE_HOUR + original["memory_gib"] * MEMORY_PER_GIB_HOUR
    hourly += GPU_PER_HOUR.get(original["gpu"], 0.0)
    cost = math.ceil(hourly * upper / 3600 * original.get("count", 1) * 10000) / 10000
    if cost > original["worst_case_usd"]:
        raise ValueError("completed price exceeds original reservation")
    return {
        "event_type": SETTLEMENT,
        "at": now.isoformat(),
        "job": original["job"],
        "timeout_min": original["timeout_min"],
        "worst_case_usd": 0.0,
        "reservation": original_binding,
        "terminal_evidence": evidence_binding,
        "completed_wall_seconds_upper_bound": upper,
        "completed_usage_upper_usd": cost,
    }


def _settled_costs(rows: list[dict[str, Any]], now: datetime) -> dict[str, float]:
    settled = {}
    seen = set()
    for event in rows:
        if event.get("event_type") != SETTLEMENT:
            continue
        key = event["reservation"]["canonical_sha256"]
        originals = [
            r for r in rows if r.get("event_type") != SETTLEMENT and reservation_sha256(r) == key
        ]
        if len(originals) != 1 or any(
            originals[0][k] != event["reservation"][k] for k in ("job", "at")
        ):
            raise ValueError("settlement lacks exact original reservation")
        if key in seen or event["worst_case_usd"] != 0:
            raise ValueError("duplicate or nonzero completed settlement")
        seen.add(key)
        original = originals[0]
        if now - _aware_time(original["at"]) > UNBILLED_LOOKBACK + timedelta(
            minutes=original["timeout_min"]
        ):
            continue  # Keep old ledger history; expired reservations need no archived receipts.
        recorded_at = _aware_time(event["at"])
        if recorded_at > now:
            raise ValueError("future completed settlement")
        verified = completed_settlement(rows, event["terminal_evidence"], recorded_at)
        if any(event[k] != verified[k] for k in verified):
            raise ValueError("tampered completed settlement")
        settled[key] = event["completed_usage_upper_usd"]
    return settled


def unbilled_worst_case(rows: list[dict[str, Any]], now: datetime) -> float:
    total = 0.0
    settled = _settled_costs(rows, now)
    for row in rows:
        if row.get("event_type") == SETTLEMENT:
            continue
        started = datetime.fromisoformat(row["at"])
        if now - started <= UNBILLED_LOOKBACK + timedelta(minutes=row["timeout_min"]):
            key = reservation_sha256(row) if settled else ""
            total += settled.get(key, row["worst_case_usd"])
    return round(total, 4)


def decide(
    billed: float, unbilled: float, new_cost: float, cap: float = MONTHLY_CAP_USD
) -> dict[str, Any]:
    projected = round(billed + unbilled + new_cost, 4)
    return {
        "allowed": projected <= cap,
        "billed_usd": billed,
        "unbilled_worst_case_usd": unbilled,
        "job_worst_case_usd": new_cost,
        "projected_usd": projected,
        "cap_usd": cap,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    settle = sub.add_parser("settle")
    settle.add_argument("--evidence", type=Path, required=True)
    check = sub.add_parser("check")
    check.add_argument("--job", required=True)
    check.add_argument("--cpu", type=float, required=True)
    check.add_argument("--memory-gib", type=float, required=True)
    check.add_argument("--timeout-min", type=float, required=True)
    check.add_argument("--gpu", choices=sorted(GPU_PER_HOUR))
    check.add_argument("--count", type=int, default=1)
    args = parser.parse_args(argv)

    # The slow provider read is outside the critical section. Recent launches
    # remain conservatively covered by their reservations, re-read under lock.
    billed = None if args.cmd == "settle" else billed_this_month()
    with ledger_lock(LEDGER):
        return _ledger_command(args, billed)


def _ledger_command(args: argparse.Namespace, billed: float | None) -> int:
    now = datetime.now(UTC)
    rows = read_ledger(LEDGER)
    if args.cmd == "settle":
        _settled_costs(rows, now)
        path = args.evidence.resolve()
        binding = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        event = completed_settlement(rows, binding, now)
        previous = [
            r
            for r in rows
            if r.get("event_type") == SETTLEMENT and r["reservation"] == event["reservation"]
        ]
        if previous:
            if any(previous[0][k] != event[k] for k in event if k != "at"):
                raise ValueError("conflicting settlement already recorded")
            print(json.dumps({"idempotent": True, **previous[0]}, indent=2))
            return 0
        _append_ledger(event)
        print(json.dumps(event, indent=2))
        return 0
    assert billed is not None
    unbilled = unbilled_worst_case(rows, now)
    if args.cmd == "status":
        print(json.dumps(decide(billed, unbilled, 0.0), indent=2))
        return 0

    cost = worst_case_usd(args.cpu, args.memory_gib, args.timeout_min, args.gpu, args.count)
    verdict = decide(billed, unbilled, cost)
    if not verdict["allowed"]:
        print(json.dumps({"job": args.job, "count": args.count, **verdict}, indent=2))
        return 2
    row = {
        "at": now.isoformat(),
        "job": args.job,
        "cpu": args.cpu,
        "memory_gib": args.memory_gib,
        "gpu": args.gpu,
        "timeout_min": args.timeout_min,
        "count": args.count,
        "worst_case_usd": cost,
        "billed_before_usd": billed,
    }
    _append_ledger(row)
    print(json.dumps({"job": args.job, "count": args.count, **verdict}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
