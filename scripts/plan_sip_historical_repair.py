"""Plan RAW SIP backfill on the dates observed in the supplemental daily archive."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
from receive_recent_minutes import atomic_json

NEW_YORK = ZoneInfo("America/New_York")


def jobs_for(dates_by_symbol, timeframe, batch_size, label):
    symbols = sorted(dates_by_symbol)
    for offset in range(0, len(symbols), batch_size):
        batch = symbols[offset : offset + batch_size]
        dates = {symbol: sorted(dates_by_symbol[symbol]) for symbol in batch}
        first = min(days[0] for days in dates.values())
        last = max(days[-1] for days in dates.values())
        yield {
            "name": f"{label}-{offset // batch_size:04d}",
            "timeframe": timeframe,
            "start": datetime.combine(first, time.min, NEW_YORK).isoformat(),
            "end_exclusive": datetime.combine(
                last + timedelta(days=1), time.min, NEW_YORK
            ).isoformat(),
            "symbols": batch,
            "dates": {symbol: [day.isoformat() for day in days] for symbol, days in dates.items()},
        }


def plan_year(source, out, year, through):
    shards = sorted((source / str(year)).glob("*.parquet"))
    table = ds.dataset([str(path) for path in shards], format="parquet").to_table(
        columns=["symbol", "timestamp"], use_threads=False
    )
    local = pc.cast(table["timestamp"], pa.timestamp("ns", tz="America/New_York"))
    days = pc.cast(pc.local_timestamp(local), pa.date32()).to_pylist()
    daily = defaultdict(set)
    monthly = defaultdict(lambda: defaultdict(set))
    for symbol, day in zip(table["symbol"].to_pylist(), days, strict=True):
        if day <= through:
            daily[symbol].add(day)
            monthly[day.month][symbol].add(day)
    jobs = list(jobs_for(daily, "1Day", 180, f"supplement-daily-{year}"))
    for month, by_symbol in sorted(monthly.items(), reverse=True):
        jobs.extend(jobs_for(by_symbol, "1Min", 32, f"supplement-minute-{year}-{month:02d}"))
    atomic_json(out / f"{year}.json", {"source": str(source), "year": year, "jobs": jobs})
    return len(jobs), len(daily), sum(map(len, daily.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supplement", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--through", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    for year in range(args.through.year, 2015, -1):
        print(year, *plan_year(args.supplement, args.out, year, args.through), flush=True)


if __name__ == "__main__":
    main()
