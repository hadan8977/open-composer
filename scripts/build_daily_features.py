"""Step 11 Wave A 3.3.2: daily feature table (phase 1: daily-archive-only
columns; phase 2 joins in the intraday-derived rolling means once
``data/features/intraday_daily/`` is available for a year).

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.3 item 2.

Usage::

    uv run python scripts/build_daily_features.py
    uv run python scripts/build_daily_features.py --skip-intraday-join
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.features.daily_features import (  # noqa: E402
    build_daily_features,
    join_intraday_rolling_features,
)
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

DAILY_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
INTRADAY_ROOT = ROOT / "data" / "features" / "intraday_daily"
OUT_DIR = ROOT / "data" / "features" / "daily"
DUCKDB_TMP = ROOT / "data" / "_duckdb_tmp"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="2GB")
    parser.add_argument(
        "--skip-intraday-join",
        action="store_true",
        help="write daily-only columns even for years with an intraday_daily parquet ready",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] loading universe union symbols ...", flush=True)
    universe_symbols = sorted(universe_union_symbols(UNIVERSE_ROOT))
    print(f"universe union: {len(universe_symbols)} symbols", flush=True)

    started = time.monotonic()
    frame = build_daily_features(
        DAILY_GLOB,
        universe_symbols,
        memory_limit=args.memory_limit,
        temp_directory=str(DUCKDB_TMP),
    )
    elapsed = time.monotonic() - started
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] daily-only features: {len(frame)} rows, "
        f"{frame['symbol'].nunique()} symbols, {elapsed:.1f}s",
        flush=True,
    )

    summary: dict[str, object] = {}
    for year, year_frame in frame.groupby(frame["trade_date"].dt.year):
        year = int(year)
        joined_this_year = False
        intraday_path = INTRADAY_ROOT / f"{year}.parquet"
        if not args.skip_intraday_join and intraday_path.exists():
            import pandas as pd

            intraday_frame = pd.read_parquet(intraday_path)
            year_frame = join_intraday_rolling_features(year_frame, intraday_frame)
            joined_this_year = True
        out_path = OUT_DIR / f"{year}.parquet"
        tmp_path = out_path.with_suffix(".parquet.tmp")
        year_frame.sort_values(["symbol", "trade_date"]).to_parquet(tmp_path, index=False)
        tmp_path.replace(out_path)
        summary[str(year)] = {
            "rows": len(year_frame),
            "columns": len(year_frame.columns),
            "intraday_joined": joined_this_year,
        }
        print(
            f"{year}: {len(year_frame)} rows, {len(year_frame.columns)} columns, "
            f"intraday_joined={joined_this_year}",
            flush=True,
        )

    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
