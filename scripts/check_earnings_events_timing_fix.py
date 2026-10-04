"""T-20261004-52 acceptance checks for the rebuilt ``data/features/earnings_events``.

(a) For every accession in both the backup (old, double-shifted) and the new table:
    ``old - new`` must equal exactly what the old bug produces -- the new time read as
    US/Eastern wall-clock and converted to UTC (+4 h in EDT, +5 h in EST). Rows that do
    not match are listed with a reason.
(b) A seeded random sample of accessions is fetched again from the EDGAR filing-index
    page (separate fetch, fresh client) and compared with the new table.
(c) Row count and accession set against the backup; added/removed accessions listed.

Usage::

    ./.venv/bin/python scripts/check_earnings_events_timing_fix.py \\
        --backup data/live/backup-features-20261004/earnings_events \\
        --out reports/research/program/earnings-events-timing-fix-2026-10-04/checks.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from scripts.build_earnings_events import (
    _EASTERN,
    ARCHIVES_BASE,
    SecClient,
    eastern_wallclock_to_utc_iso,
    parse_accepted,
)

ROOT = Path(__file__).resolve().parents[1]
NEW_DIR = ROOT / "data" / "features" / "earnings_events"


def load(directory: Path) -> pd.DataFrame:
    parts = [pd.read_parquet(path) for path in sorted(directory.glob("[0-9]*.parquet"))]
    return pd.concat(parts, ignore_index=True)


def old_bug_offset_hours(new_utc: pd.Timestamp) -> float:
    """Hours the old builder added: true instant read as Eastern wall-clock, to UTC."""

    naive = new_utc.tz_localize(None).to_pydatetime()
    shifted = naive.replace(tzinfo=_EASTERN).astimezone(UTC)
    return (shifted - naive.replace(tzinfo=UTC)).total_seconds() / 3600.0


def check_shift(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    merged = old[["accession", "ticker", "acceptance_utc"]].merge(
        new[["accession", "ticker", "acceptance_utc", "acceptance_source"]],
        on=["accession", "ticker"],
        suffixes=("_old", "_new"),
    )
    old_ts = pd.to_datetime(merged["acceptance_utc_old"], utc=True)
    new_ts = pd.to_datetime(merged["acceptance_utc_new"], utc=True)
    merged["diff_h"] = (old_ts - new_ts).dt.total_seconds() / 3600.0
    merged["expected_h"] = [old_bug_offset_hours(ts) for ts in new_ts]
    merged["ok"] = (merged["diff_h"] - merged["expected_h"]).abs() < 1e-9
    bad = merged[~merged["ok"]]
    reasons = []
    for row in bad.itertuples():
        if row.acceptance_source != "edgar_index":
            reason = f"acceptance_source={row.acceptance_source}"
        elif row.diff_h in (4.0, 5.0):
            reason = "diff is 4/5 h but DST wall-clock edge (near a switch hour)"
        else:
            reason = "diff is not 4 h / 5 h: index time disagrees with the API value"
        reasons.append(
            {
                "accession": row.accession,
                "ticker": row.ticker,
                "old": row.acceptance_utc_old,
                "new": row.acceptance_utc_new,
                "diff_h": row.diff_h,
                "expected_h": row.expected_h,
                "reason": reason,
            }
        )
    return {
        "compared": int(len(merged)),
        "matching": int(merged["ok"].sum()),
        "share_matching": float(merged["ok"].mean()) if len(merged) else None,
        "diff_hours_counts": {
            str(k): int(v) for k, v in merged["diff_h"].round(4).value_counts().items()
        },
        "mismatches": reasons,
    }


def check_index_sample(new: pd.DataFrame, *, n: int, seed: int) -> dict:
    rng = random.Random(seed)
    accessions = sorted(new["accession"])
    sample = rng.sample(accessions, n)
    by_acc = new.set_index("accession")
    client = SecClient(min_interval=0.25)
    results = []
    try:
        for accession in sample:
            row = by_acc.loc[accession]
            cik = str(int(row["cik"]))
            url = (
                ARCHIVES_BASE.format(cik=cik, accession_nodash=accession.replace("-", ""))
                + f"{accession}-index.htm"
            )
            status, content = client.get(url)
            accepted = (
                parse_accepted(content.decode("utf-8", errors="replace")) if status == 200 else None
            )
            fetched_utc = eastern_wallclock_to_utc_iso(accepted)
            results.append(
                {
                    "accession": accession,
                    "ticker": row["ticker"],
                    "index_accepted_et": accepted,
                    "index_utc": fetched_utc,
                    "table_utc": row["acceptance_utc"],
                    "acceptance_source": row["acceptance_source"],
                    "match": fetched_utc is not None and fetched_utc == row["acceptance_utc"],
                }
            )
    finally:
        client.close()
    return {
        "seed": seed,
        "n": n,
        "matched": sum(r["match"] for r in results),
        "rows": results,
    }


def check_sets(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    old_set, new_set = set(old["accession"]), set(new["accession"])
    added = new[new["accession"].isin(new_set - old_set)]
    removed = old[old["accession"].isin(old_set - new_set)]
    return {
        "old_rows": int(len(old)),
        "new_rows": int(len(new)),
        "old_unique_accessions": len(old_set),
        "new_unique_accessions": len(new_set),
        "duplicate_accessions_old": int(len(old) - len(old_set)),
        "duplicate_accessions_new": int(len(new) - len(new_set)),
        "added": [
            {"accession": r.accession, "ticker": r.ticker, "acceptance_utc": r.acceptance_utc}
            for r in added.itertuples()
        ],
        "removed": [
            {"accession": r.accession, "ticker": r.ticker, "acceptance_utc": r.acceptance_utc}
            for r in removed.itertuples()
        ],
        "source_counts": {
            str(k): int(v) for k, v in new["acceptance_source"].value_counts().items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20261004)
    args = parser.parse_args(argv)

    old, new = load(args.backup), load(NEW_DIR)
    sets = check_sets(old, new)
    shift = check_shift(old, new)
    sample = check_index_sample(new, n=args.sample, seed=args.seed)
    checks = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "a_old_minus_new": shift,
        "b_index_sample": sample,
        "c_row_and_accession_sets": sets,
        "pass_a": shift["share_matching"] is not None and shift["share_matching"] >= 0.995,
        "pass_b": sample["matched"] == sample["n"],
        "pass_c": not sets["removed"]
        and sets["duplicate_accessions_new"] == sets["duplicate_accessions_old"],
        "dst_boundary_note": (
            "'expected' replays the old builder (Eastern wall-clock of the true instant "
            "localized and converted again), so it differs from 'DST at the true instant' "
            "only in the hours around the 03-09/11-02 style switches."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n")
    print(
        f"a: {shift['matching']}/{shift['compared']} ({shift['share_matching']:.4%}) "
        f"b: {sample['matched']}/{sample['n']} "
        f"c: old {sets['old_rows']} new {sets['new_rows']} "
        f"added {len(sets['added'])} removed {len(sets['removed'])}"
    )
    return 0 if checks["pass_a"] and checks["pass_b"] and checks["pass_c"] else 1


if __name__ == "__main__":
    sys.exit(main())
