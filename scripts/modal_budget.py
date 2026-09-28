"""Spend guard for Modal jobs: refuse any launch whose worst case could exceed the monthly cap.

Why this exists (2026-09-28): the owner granted Modal's $30/month free credit for
factor replication and model training, with the instruction not to overspend.
The workspace spend limit is set in Modal's dashboard (not reachable from the
CLI), so this is the second, local guard:

* worst case of a job = timeout x (cores x CPU rate + GiB x memory rate + GPU rate);
* Modal's billing report only covers completed hourly intervals, so jobs started
  in the last few hours are counted from this ledger at their worst case;
* a launch is allowed only if billed + unbilled worst cases + the new worst case
  stays under the cap ($25, leaving $5 of the $30 credit as margin).

Usage:
    python scripts/modal_budget.py status
    python scripts/modal_budget.py check --job NAME --cpu 8 --memory-gib 32 \
        --timeout-min 120 [--gpu T4] [--count 3]

`--count` (default 1) multiplies the worst case, for launches that fan out to
that many parallel containers (e.g. `scripts/modal_run.py --shards N`) -- each
shard is billed independently, so N shards cost N times one shard's worst case.

`check` exits 0 and appends a ledger row when allowed, exits 2 when refused.
Every Modal function must set `timeout=` equal to the `--timeout-min` it was checked with.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
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


def unbilled_worst_case(rows: list[dict[str, Any]], now: datetime) -> float:
    total = 0.0
    for row in rows:
        started = datetime.fromisoformat(row["at"])
        if now - started <= UNBILLED_LOOKBACK + timedelta(minutes=row["timeout_min"]):
            total += row["worst_case_usd"]
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
    check = sub.add_parser("check")
    check.add_argument("--job", required=True)
    check.add_argument("--cpu", type=float, required=True)
    check.add_argument("--memory-gib", type=float, required=True)
    check.add_argument("--timeout-min", type=float, required=True)
    check.add_argument("--gpu", choices=sorted(GPU_PER_HOUR))
    check.add_argument("--count", type=int, default=1)
    args = parser.parse_args(argv)

    now = datetime.now(UTC)
    rows = read_ledger()
    billed = billed_this_month()
    unbilled = unbilled_worst_case(rows, now)
    if args.cmd == "status":
        print(json.dumps(decide(billed, unbilled, 0.0), indent=2))
        return 0

    cost = worst_case_usd(args.cpu, args.memory_gib, args.timeout_min, args.gpu, args.count)
    verdict = decide(billed, unbilled, cost)
    print(json.dumps({"job": args.job, "count": args.count, **verdict}, indent=2))
    if not verdict["allowed"]:
        return 2
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
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
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
