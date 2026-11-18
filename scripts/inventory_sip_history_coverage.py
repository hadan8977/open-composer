"""Index observed symbol-days and gaps in the local original SIP archive."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

NEW_YORK = ZoneInfo("America/New_York")


def next_month(day):
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def count_month(conn, source, out, day, cutoff, minute_override=None, daily_override=None):
    minute_root = (
        (minute_override / str(day.year))
        if minute_override
        else source / ("sip-hist" if day.year <= 2022 else "sip") / "minute" / str(day.year)
    )
    minute_files = sorted(
        [*minute_root.glob("*.parquet"), *(minute_root / f"{day.month:02d}").glob("*.parquet")]
    )
    daily_files = sorted(
        ((daily_override or source / "sip/daily") / str(day.year)).glob("*.parquet")
    )
    first = datetime.combine(day, time.min, NEW_YORK)
    stop = datetime.combine(min(next_month(day), cutoff + timedelta(days=1)), time.min, NEW_YORK)
    observed = (
        """
        SELECT symbol, CAST(timezone('America/New_York', timestamp) AS DATE) AS date_et,
               count(*) AS minute_rows
        FROM read_parquet(?, union_by_name = true)
        WHERE timestamp >= ? AND timestamp < ?
        GROUP BY 1, 2
    """
        if minute_files
        else "SELECT ''::VARCHAR AS symbol, NULL::DATE AS date_et, "
        "0::BIGINT AS minute_rows WHERE false"
    )
    params = [[str(p) for p in minute_files], first, stop] if minute_files else []
    temp = out.with_suffix(".partial")
    destination = temp.resolve().as_posix().replace("'", "''")
    conn.execute(
        f"""
        COPY (
        WITH observed AS ({observed}), daily AS (
            SELECT DISTINCT symbol, CAST(timezone('America/New_York', timestamp) AS DATE) AS date_et
            FROM read_parquet(?, union_by_name = true)
            WHERE timestamp >= ? AND timestamp < ?
        )
        SELECT coalesce(daily.symbol, observed.symbol) AS symbol,
               coalesce(daily.date_et, observed.date_et) AS date_et,
               daily.symbol IS NOT NULL AS has_daily,
               coalesce(observed.minute_rows, 0) AS minute_rows
        FROM daily FULL JOIN observed USING (symbol, date_et)
        ) TO '{destination}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """,
        [*params, [str(p) for p in daily_files], first, stop],
    )
    rows = conn.fetchone()[0]
    temp.replace(out)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--through", type=date.fromisoformat, required=True)
    parser.add_argument("--from-month", type=date.fromisoformat, default=date(2016, 1, 1))
    parser.add_argument("--minute-root", type=Path)
    parser.add_argument("--daily-root", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    day = args.from_month
    while day <= args.through:
        path = args.out / f"{day:%Y-%m}.parquet"
        if not path.exists():
            with duckdb.connect(
                config={
                    "memory_limit": "500MB",
                    "threads": 1,
                    "preserve_insertion_order": False,
                    "temp_directory": str(args.out / "spill"),
                }
            ) as conn:
                rows = count_month(
                    conn, args.source, path, day, args.through, args.minute_root, args.daily_root
                )
                print(day.isoformat(), rows, flush=True)
        day = next_month(day)


if __name__ == "__main__":
    main()
