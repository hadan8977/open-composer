"""Step 11 Wave A 3.3.2: daily feature table (phase 1: daily-archive-only
columns; phase 2 joins in the intraday-derived rolling means once
``data/features/intraday_daily/`` is available for a year).

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.3 item 2.

**Per-year, bounded-lookback execution (real memory incident, fixed
2026-09-07)**: the first real run against the full universe union (2,721
symbols) scanned all 11 archive years (``data/sip/daily/*/*.parquet``) in one
``read_parquet(...)`` and pulled the entire multi-year result into a single
pandas ``DataFrame`` via one ``fetchdf()`` call. On this 3.8GB box that grew
past 2GB RSS and pushed system swap to within ~500MB of exhaustion while the
coordinator's minute-bar backfill was running concurrently -- the run was
killed before it produced any output. ``build_daily_features``'s internal
``memory_limit``/``threads=2`` PRAGMAs only bound DuckDB's own execution
buffers, not the size of the final pandas object a single ``fetchdf()`` call
materializes, so lowering that setting alone would not have fixed this. The
fix here restricts the *input* glob per target year to ``[year-1, year]``
(``[year]`` alone for the first archive year) and calls
``build_daily_features`` once per target year, keeping only that year's rows
before writing and discarding the frame -- peak resident data is bounded to
~2 years of the universe union instead of all 11.

**Correctness note on the 2-year window (recorded, not silently absorbed)**:
every windowed column's warm-up guard (``daily_features.py``'s ``_guard``,
keyed on a per-symbol row number) now starts counting from the first row of
``year-1`` instead of the symbol's true first archive row. For a symbol that
has traded continuously since before ``year-1``, this is a no-op (it already
has far more than the ~253 rows the longest window needs by the time
``year-1`` ends). It only changes behavior for a symbol whose *true* history
starts inside ``year-1`` itself close to the boundary -- an edge case already
present in the single-query form for every symbol's real first year, just
possibly shifted by up to one calendar year for symbols admitted to the
universe partway through the archive. No column ever fabricates a value from
too little history either way (the guard still nulls short windows); the
only change is a handful of additional true-but-conservatively-dropped rows
at a small number of (symbol, year) boundaries. Full-precision would require
scanning the complete history once via a single ``CREATE TEMP TABLE`` and
fetching per year from that -- a larger refactor left as a follow-up if this
turns out to matter for the baseline chain's results.

Usage::

    uv run python scripts/build_daily_features.py
    uv run python scripts/build_daily_features.py --skip-intraday-join
    uv run python scripts/build_daily_features.py --years 2024 2025 2026
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from open_composer.research.features.daily_features import (  # noqa: E402
    build_daily_features,
    join_intraday_rolling_features,
)
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

DAILY_ROOT = ROOT / "data" / "sip" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
INTRADAY_ROOT = ROOT / "data" / "features" / "intraday_daily"
OUT_DIR = ROOT / "data" / "features" / "daily"
DUCKDB_TMP = ROOT / "data" / "_duckdb_tmp"

#: How many prior archive years to include in each target year's scan, so
#: every 252(+)-day trailing window has enough real history behind it (see
#: module docstring's correctness note).
LOOKBACK_YEARS = 1


def _available_archive_years() -> list[int]:
    return sorted(int(p.name) for p in DAILY_ROOT.iterdir() if p.is_dir() and p.name.isdigit())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-limit", default="1.2GB")
    parser.add_argument(
        "--skip-intraday-join",
        action="store_true",
        help="write daily-only columns even for years with an intraday_daily parquet ready",
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="*",
        default=None,
        help="restrict to these target years (default: every year under data/sip/daily/)",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] loading universe union symbols ...", flush=True)
    universe_symbols = sorted(universe_union_symbols(UNIVERSE_ROOT))
    print(f"universe union: {len(universe_symbols)} symbols", flush=True)

    archive_years = _available_archive_years()
    first_archive_year = archive_years[0]
    target_years = args.years if args.years else archive_years
    print(f"archive years available: {archive_years}", flush=True)
    print(f"target years this run: {target_years}", flush=True)

    summary: dict[str, object] = {}
    for year in target_years:
        window_years = [y for y in (year - LOOKBACK_YEARS, year) if y >= first_archive_year]
        window_years = sorted(set(window_years))
        glob_paths = [str(DAILY_ROOT / str(y) / "*.parquet") for y in window_years]

        started = time.monotonic()
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: scanning {window_years} ...",
            flush=True,
        )
        windowed_frame = build_daily_features(
            glob_paths,
            universe_symbols,
            memory_limit=args.memory_limit,
            temp_directory=str(DUCKDB_TMP),
        )
        year_frame = windowed_frame.loc[windowed_frame["trade_date"].dt.year == year].copy()
        del windowed_frame
        gc.collect()
        elapsed = time.monotonic() - started
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: daily-only features "
            f"{len(year_frame)} rows, {year_frame['symbol'].nunique()} symbols, {elapsed:.1f}s",
            flush=True,
        )

        joined_this_year = False
        intraday_path = INTRADAY_ROOT / f"{year}.parquet"
        if not args.skip_intraday_join and intraday_path.exists():
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
            "elapsed_seconds": round(elapsed, 1),
        }
        print(
            f"{year}: {len(year_frame)} rows, {len(year_frame.columns)} columns, "
            f"intraday_joined={joined_this_year}",
            flush=True,
        )
        del year_frame
        gc.collect()

    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
