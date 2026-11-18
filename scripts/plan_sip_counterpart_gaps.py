"""Plan missing daily/minute counterparts from completed local coverage indexes."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import duckdb
from plan_sip_historical_repair import jobs_for
from receive_recent_minutes import atomic_json


def plan_month(conn, coverage, daily, supplemental):
    year = coverage.stem[:4]
    tables = [
        [str(p) for p in sorted((root / year).glob("*.parquet"))] for root in (daily, supplemental)
    ]
    rows = conn.execute(
        """
        WITH coverage AS (
            SELECT symbol, date_et, has_daily, minute_rows
            FROM read_parquet(?) WHERE has_daily <> (minute_rows > 0)
        ), source_daily AS (
            SELECT symbol, CAST(timezone('America/New_York', timestamp) AS DATE) AS date_et,
                   max(volume) AS volume
            FROM read_parquet(?, union_by_name = true)
            GROUP BY 1, 2
        ), supplemental AS (
            SELECT symbol, CAST(timezone('America/New_York', timestamp) AS DATE) AS date_et
            FROM read_parquet(?, union_by_name = true)
        )
        SELECT coverage.symbol, coverage.date_et, coverage.has_daily
        FROM coverage
        LEFT JOIN source_daily USING (symbol, date_et)
        ANTI JOIN supplemental USING (symbol, date_et)
        WHERE NOT coverage.has_daily OR source_daily.volume > 0
    """,
        [str(coverage), *tables],
    ).fetchall()
    missing = {"1Min": defaultdict(set), "1Day": defaultdict(set)}
    for symbol, day, has_daily in rows:
        missing["1Min" if has_daily else "1Day"][symbol].add(day)
    jobs = []
    for timeframe, symbols in missing.items():
        jobs.extend(
            jobs_for(
                symbols,
                timeframe,
                32 if timeframe == "1Min" else 180,
                f"counterpart-{coverage.stem}-{timeframe}",
            )
        )
    return jobs, {key: sum(map(len, value.values())) for key, value in missing.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("original", "recent", "daily", "recent-daily", "supplemental", "out"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    args = parser.parse_args()
    coverage_paths = {path.stem: (path, args.daily) for path in args.original.glob("*.parquet")}
    coverage_paths.update(
        {path.stem: (path, args.recent_daily) for path in args.recent.glob("*.parquet")}
    )
    jobs, months = [], []
    with duckdb.connect(config={"memory_limit": "350MB", "threads": 1}) as conn:
        for month, (path, daily) in sorted(coverage_paths.items(), reverse=True):
            generated, counts = plan_month(conn, path, daily, args.supplemental)
            jobs.extend(generated)
            months.append({"month": month, "symbol_days": counts, "jobs": len(generated)})
    atomic_json(args.out, {"jobs": jobs, "months": months})
    print(f"{len(months)} months, {len(jobs)} query batches", flush=True)


if __name__ == "__main__":
    main()
