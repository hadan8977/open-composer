"""Estimate and record Modal usage; the owner authorizes existing credits freely.

Use `status` for usage and `check --job NAME --cpu N --memory-gib N
--timeout-min N [--gpu T4] [--count N]` before a launch: it records the job's
worst-case cost in the ledger. Function timeouts match the estimate.

There is no local monthly spending cap. Tell the owner when more credits are
needed; do not change payment settings or recharge automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from open_composer.research.file_lock import lock_file

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "reports" / "research" / "control" / "modal-ledger.jsonl"
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


def modal_cli() -> str:
    """Find the installed CLI even when a finite service has a minimal PATH."""
    executable = shutil.which("modal")
    if executable:
        return executable
    for candidate in (
        Path(sys.executable).with_name("modal.exe" if os.name == "nt" else "modal"),
        Path.home() / ".local/share/uv/tools/modal/bin/modal",
    ):
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError("Installed Modal CLI unavailable; configure its executable in PATH")


def billed_this_month() -> float:
    """Sum of Modal's reported cost for the current month (complete intervals only)."""
    proc = subprocess.run(
        [modal_cli(), "billing", "report", "--for", "this month", "--json"],
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
    """Serialize ledger and manifest writers across processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".lock").open("a", encoding="utf-8") as lock:
        lock_file(lock)
        yield


def unbilled_worst_case(rows: list[dict[str, Any]], now: datetime) -> float:
    """Reservations recent enough that Modal's billing report may not include them yet."""
    total = 0.0
    for row in rows:
        started = datetime.fromisoformat(row["at"])
        if now - started <= UNBILLED_LOOKBACK + timedelta(minutes=row["timeout_min"]):
            total += row["worst_case_usd"]
    return round(total, 4)


def decide(billed: float, unbilled: float, new_cost: float) -> dict[str, Any]:
    return {
        "allowed": True,
        "billed_usd": billed,
        "unbilled_worst_case_usd": unbilled,
        "job_worst_case_usd": new_cost,
        "projected_usd": round(billed + unbilled + new_cost, 4),
        "cap_usd": None,
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

    billed = billed_this_month()  # slow provider read, outside the lock
    with ledger_lock(LEDGER):
        now = datetime.now(UTC)
        unbilled = unbilled_worst_case(read_ledger(LEDGER), now)
        if args.cmd == "status":
            print(json.dumps(decide(billed, unbilled, 0.0), indent=2))
            return 0
        cost = worst_case_usd(args.cpu, args.memory_gib, args.timeout_min, args.gpu, args.count)
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
        with LEDGER.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(row) + "\n")
    print(
        json.dumps(
            {"job": args.job, "count": args.count, **decide(billed, unbilled, cost)}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
