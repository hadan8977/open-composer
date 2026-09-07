"""Step 11 Wave A 3.3.3: forward-return label table.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.3 item 3.

**Per-year, bounded-lookahead execution**: mirrors the fix applied to
``scripts/build_daily_features.py`` after that script's single, full-11-year
``fetchdf()`` grew past 2GB RSS and pushed the box's swap toward exhaustion
(see that script's module docstring for the full incident writeup). Labels
need *forward*-looking data (``LEAD(close, h)``, max horizon 21 trading days)
rather than daily_features.py's trailing windows (up to 252 trading days), so
the bounded glob here is ``[year, year + 1]`` (clamped to the last archive
year) instead of ``[year - 1, year]`` -- otherwise the same idea: compute one
target year at a time, keep only that year's rows, discard the rest before
moving on.

Usage::

    uv run python scripts/build_labels.py
    uv run python scripts/build_labels.py --years 2024 2025 2026
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

from open_composer.research.features.labels import build_labels  # noqa: E402
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

DAILY_ROOT = ROOT / "data" / "sip" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
OUT_DIR = ROOT / "data" / "features" / "labels"
DUCKDB_TMP = ROOT / "data" / "_duckdb_tmp"

#: One archive year of look-ahead comfortably covers the largest horizon
#: (21 trading days ~= 1 calendar month), same reasoning as
#: build_daily_features.py's LOOKBACK_YEARS but pointed forward in time.
LOOKAHEAD_YEARS = 1


def _available_archive_years() -> list[int]:
    return sorted(int(p.name) for p in DAILY_ROOT.iterdir() if p.is_dir() and p.name.isdigit())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizons", type=int, nargs="*", default=[5, 10, 21])
    parser.add_argument("--memory-limit", default="1.2GB")
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
    last_archive_year = archive_years[-1]
    target_years = args.years if args.years else archive_years
    print(f"archive years available: {archive_years}", flush=True)
    print(f"target years this run: {target_years}", flush=True)

    summary: dict[str, object] = {}
    for year in target_years:
        window_years = [y for y in (year, year + LOOKAHEAD_YEARS) if y <= last_archive_year]
        window_years = sorted(set(window_years))
        glob_paths = [str(DAILY_ROOT / str(y) / "*.parquet") for y in window_years]

        started = time.monotonic()
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: scanning {window_years} ...",
            flush=True,
        )
        windowed_frame = build_labels(
            glob_paths,
            universe_symbols,
            horizons=tuple(args.horizons),
            memory_limit=args.memory_limit,
            temp_directory=str(DUCKDB_TMP),
        )
        year_frame = windowed_frame.loc[windowed_frame["trade_date"].dt.year == year].copy()
        del windowed_frame
        gc.collect()
        elapsed = time.monotonic() - started
        print(f"{year}: {len(year_frame)} rows, {elapsed:.1f}s", flush=True)

        out_path = OUT_DIR / f"{year}.parquet"
        tmp_path = out_path.with_suffix(".parquet.tmp")
        year_frame.sort_values(["symbol", "trade_date"]).to_parquet(tmp_path, index=False)
        tmp_path.replace(out_path)
        summary[str(year)] = {"rows": len(year_frame), "elapsed_seconds": round(elapsed, 1)}
        del year_frame
        gc.collect()

    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
