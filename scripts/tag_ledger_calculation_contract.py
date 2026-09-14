#!/usr/bin/env python3
"""Back-fill ``calculation_contract`` on existing experiment-ledger rows.

One-off companion to ``loop.PORTFOLIO_RETURNS_CONTRACT`` (2026-09-14). New rows
carry the field at write time; this script labels the rows written before the
field existed, so a reader can tell which return formula stands behind each
row's metrics without re-running anything. Idempotent: rows that already carry
the field are left untouched. A timestamped backup of the ledger is written
next to it before any change.

Rules (history in ``reports/research/control/step13-2026-09-09-progress.md``,
2026-09-10 entries):

* Rows produced through ``returns_from_weight_schedule`` -- every
  ``run_experiment`` row (recognised by its ``tearsheet_path`` /
  ``mlflow_run_id`` / ``test_years`` keys), the Step 13 Track M grid
  (``step13_m*``) and the Group B F1 script (``groupb_f1_*``) -- get
  ``portfolio_returns.constant_weight_daily.v1`` when recorded before
  2026-09-10 02:02 UTC and ``portfolio_returns.buy_and_hold_drift.v2`` after.
  The boundary is the moment the pre-fix Step 13 grid rows were purged and
  re-run under the fixed formula (mtime of the executor's backup
  ``/tmp/experiments.jsonl.bak_pre_fix_purge``), not the later commit time of
  ``30879b4``; the Step 13 report states every M0/M0b/M1 row is post-fix.
* Rows from scripts with their own return math get ``script_local:<script>``:
  ``groupb_f3_*``, ``groupb_f5_*``, ``step13_p_rt_hourly_*``.
* Anything else gets ``unspecified`` and is listed on stdout.

Usage::

    uv run python scripts/tag_ledger_calculation_contract.py --dry-run
    uv run python scripts/tag_ledger_calculation_contract.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

LEDGER_PATH = Path("reports/research/ledger/experiments.jsonl")
FIX_BOUNDARY = "2026-09-10T02:02:00+00:00"
V1 = "portfolio_returns.constant_weight_daily.v1"
V2 = "portfolio_returns.buy_and_hold_drift.v2"
KERNEL_ROW_KEYS = ("tearsheet_path", "mlflow_run_id", "test_years")
WEIGHT_SCHEDULE_PREFIXES = ("step13_m", "groupb_f1_")
SCRIPT_LOCAL_PREFIXES = {
    "groupb_f3_": "script_local:evaluate_groupb_f3_qqq_intraday_momentum.py",
    "groupb_f5_": "script_local:evaluate_groupb_f5_beta_router_reference.py",
    "step13_p_rt_hourly_": "script_local:evaluate_reversal_trend_hourly.py",
}


def contract_for(record: dict[str, object]) -> str:
    experiment_id = str(record.get("experiment_id", ""))
    recorded_at = str(record.get("recorded_at", ""))
    uses_weight_schedule = any(
        key in record for key in KERNEL_ROW_KEYS
    ) or experiment_id.startswith(WEIGHT_SCHEDULE_PREFIXES)
    if uses_weight_schedule:
        return V1 if recorded_at < FIX_BOUNDARY else V2
    for prefix, contract in SCRIPT_LOCAL_PREFIXES.items():
        if experiment_id.startswith(prefix):
            return contract
    return "unspecified"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument(
        "--dry-run", action="store_true", help="print the assignment, write nothing"
    )
    args = parser.parse_args()
    if not args.ledger.exists():
        print(f"no ledger at {args.ledger}")
        return 1
    lines = args.ledger.read_text().splitlines()
    records: list[dict[str, object] | None] = [
        json.loads(line) if line.strip() else None for line in lines
    ]
    counts: Counter[str] = Counter()
    changed = 0
    for record in records:
        if record is None:
            continue
        if "calculation_contract" in record:
            counts[f"already: {record['calculation_contract']}"] += 1
            continue
        contract = contract_for(record)
        record["calculation_contract"] = contract
        counts[contract] += 1
        changed += 1
        recorded = str(record.get("recorded_at", ""))[:19]
        print(f"{record.get('experiment_id', '?'):70} {recorded}  {contract}")
    print()
    for key, count in sorted(counts.items()):
        print(f"{count:4d}  {key}")
    if args.dry_run or changed == 0:
        print(
            f"\n{'dry run: ' if args.dry_run else ''}{changed} row(s) would change"
            if args.dry_run
            else "\nnothing to do"
        )
        return 0
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = args.ledger.with_name(f"{args.ledger.name}.bak-{stamp}")
    backup.write_text("\n".join(lines) + "\n")
    args.ledger.write_text(
        "".join(json.dumps(record, default=str) + "\n" for record in records if record is not None)
    )
    print(f"\ntagged {changed} row(s); backup at {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
