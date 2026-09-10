"""Step 13-F 3.2: build ``data/features/alpha101/{year}.parquet`` and
``data/features/alpha191/{year}.parquet`` together (one shared OHLCV+vwap
scan per symbol batch feeds both tables, since both are cheap wide-panel
pivots of the exact same input columns).

docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md
section 3.2. Same per-year, per-symbol-batch, resumable shape as
``build_alpha158_features.py``.

Usage (foreground smoke test)::

    uv run python scripts/build_alpha101_alpha191_features.py --years 2026 --symbol-batch-size 50

Usage (the real multi-year backfill; run detached + capped)::

    nohup ./scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/build_alpha101_alpha191_features.py \
        > /tmp/build_alpha101_alpha191.log 2>&1 &
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

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.research.features.alpha101 import (  # noqa: E402
    ALPHA101_COLUMNS,
    alpha101_skipped_ids,
    compute_alpha101,
)
from open_composer.research.features.alpha191 import (  # noqa: E402
    ALPHA191_COLUMNS,
    alpha191_skipped_ids,
    compute_alpha191,
)
from open_composer.research.features.manifest import write_feature_table_manifest  # noqa: E402
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

DAILY_ROOT = ROOT / "data" / "sip" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
ALPHA101_OUT = ROOT / "data" / "features" / "alpha101"
ALPHA191_OUT = ROOT / "data" / "features" / "alpha191"
DUCKDB_TMP = ROOT / "data" / "_duckdb_tmp"
ALL_YEARS = list(range(2016, 2027))
LOOKBACK_YEARS = 1
DEFAULT_SYMBOL_BATCH_SIZE = 300

ALPHA101_SOURCE = (
    "Kakushadze (2016) 101 Formulaic Alphas, arXiv 1601.00991; pandas fallback "
    "spot-checked against yli188/WorldQuant_alpha101_code (no LICENSE, not "
    "vendored). See reports/harness/source_cards/step13f_open_factor_libraries.jsonl"
)
ALPHA191_SOURCE = (
    "Guotai Junan 2017 Alpha191 research report; pandas fallback spot-checked "
    "against Daic115/alpha191 (no LICENSE, not vendored; 3 formula corrections "
    "documented in alpha191.py's module docstring). See "
    "reports/harness/source_cards/step13f_open_factor_libraries.jsonl"
)
FORMULA_VERSION = "step13f-2026-09-10-v1"


def _load_ohlcv_vwap_batch(
    glob_paths: list[str], batch_symbols: list[str], memory_limit: str
) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        con.execute(f"SET memory_limit='{memory_limit}'")
        con.execute("SET threads=2")
        con.execute("SET preserve_insertion_order=false")
        con.execute(f"SET temp_directory='{DUCKDB_TMP}'")
        con.register("_batch_symbols", pd.DataFrame({"symbol": batch_symbols}))
        query = f"""
            SELECT symbol, CAST(timestamp AS DATE) AS trade_date,
                   open, high, low, close, volume, vwap
            FROM read_parquet({glob_paths!r})
            WHERE symbol IN (SELECT symbol FROM _batch_symbols)
            ORDER BY symbol, trade_date
        """
        raw = con.execute(query).fetchdf()
    finally:
        con.close()
    if not raw.empty:
        raw["trade_date"] = pd.to_datetime(raw["trade_date"])
    return raw


def _available_archive_years() -> list[int]:
    return sorted(int(p.name) for p in DAILY_ROOT.iterdir() if p.is_dir() and p.name.isdigit())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="*", default=None)
    parser.add_argument("--memory-limit", default="1.2GB")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--symbol-batch-size", type=int, default=DEFAULT_SYMBOL_BATCH_SIZE)
    args = parser.parse_args()

    ALPHA101_OUT.mkdir(parents=True, exist_ok=True)
    ALPHA191_OUT.mkdir(parents=True, exist_ok=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] loading universe union symbols ...", flush=True)
    universe_symbols = sorted(universe_union_symbols(UNIVERSE_ROOT))
    print(f"universe union: {len(universe_symbols)} symbols", flush=True)

    archive_years = _available_archive_years()
    first_archive_year = archive_years[0]
    target_years = [y for y in (args.years or ALL_YEARS) if y in archive_years]
    print(f"target years this run: {target_years}", flush=True)

    summary: dict[str, object] = {}
    for year in target_years:
        out_101 = ALPHA101_OUT / f"{year}.parquet"
        out_191 = ALPHA191_OUT / f"{year}.parquet"
        if out_101.exists() and out_191.exists() and not args.force:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: already done, skipping", flush=True
            )
            summary[str(year)] = "skipped_existing"
            continue

        window_years = sorted({y for y in (year - LOOKBACK_YEARS, year) if y >= first_archive_year})
        glob_paths = [str(DAILY_ROOT / str(y) / "*.parquet") for y in window_years]
        symbol_batches = [
            universe_symbols[i : i + args.symbol_batch_size]
            for i in range(0, len(universe_symbols), args.symbol_batch_size)
        ]
        started = time.monotonic()
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: scanning {window_years}, "
            f"{len(symbol_batches)} symbol batches ...",
            flush=True,
        )

        scratch_101 = ALPHA101_OUT / "_scratch" / str(year)
        scratch_191 = ALPHA191_OUT / "_scratch" / str(year)
        scratch_101.mkdir(parents=True, exist_ok=True)
        scratch_191.mkdir(parents=True, exist_ok=True)
        frames_101: list[pd.DataFrame] = []
        frames_191: list[pd.DataFrame] = []
        for batch_index, batch_symbols in enumerate(symbol_batches):
            path_101 = scratch_101 / f"batch-{batch_index:03d}.parquet"
            path_191 = scratch_191 / f"batch-{batch_index:03d}.parquet"
            if path_101.exists() and path_191.exists() and not args.force:
                frames_101.append(pd.read_parquet(path_101))
                frames_191.append(pd.read_parquet(path_191))
                continue
            batch_started = time.monotonic()
            raw = _load_ohlcv_vwap_batch(glob_paths, batch_symbols, args.memory_limit)
            if raw.empty:
                continue
            batch_101 = compute_alpha101(raw)
            batch_101 = batch_101.loc[batch_101["trade_date"].dt.year == year].copy()
            batch_101.to_parquet(path_101, index=False)
            frames_101.append(batch_101)

            batch_191 = compute_alpha191(raw)
            batch_191 = batch_191.loc[batch_191["trade_date"].dt.year == year].copy()
            batch_191.to_parquet(path_191, index=False)
            frames_191.append(batch_191)

            del raw, batch_101, batch_191
            gc.collect()
            print(
                f"  [{time.strftime('%Y-%m-%d %H:%M:%S')}] {year} batch "
                f"{batch_index + 1}/{len(symbol_batches)}: {time.monotonic() - batch_started:.0f}s",
                flush=True,
            )

        frame_101 = pd.concat(frames_101, ignore_index=True).sort_values(["symbol", "trade_date"])
        frame_191 = pd.concat(frames_191, ignore_index=True).sort_values(["symbol", "trade_date"])
        del frames_101, frames_191
        gc.collect()

        tmp_101 = out_101.with_suffix(".parquet.tmp")
        frame_101.to_parquet(tmp_101, index=False)
        tmp_101.replace(out_101)
        rows_101 = len(frame_101)
        del frame_101
        gc.collect()

        tmp_191 = out_191.with_suffix(".parquet.tmp")
        frame_191.to_parquet(tmp_191, index=False)
        tmp_191.replace(out_191)
        rows_191 = len(frame_191)
        del frame_191
        gc.collect()

        for path in scratch_101.glob("batch-*.parquet"):
            path.unlink()
        scratch_101.rmdir()
        for path in scratch_191.glob("batch-*.parquet"):
            path.unlink()
        scratch_191.rmdir()

        elapsed = time.monotonic() - started
        write_feature_table_manifest(
            ALPHA101_OUT,
            table="alpha101",
            source_library=ALPHA101_SOURCE,
            formula_version=FORMULA_VERSION,
            columns=["symbol", "trade_date", *ALPHA101_COLUMNS],
            skipped=alpha101_skipped_ids(),
            rows_by_year={str(year): rows_101},
            build_seconds_by_year={str(year): round(elapsed, 1)},
            notes="20 of 101 ids implemented this round; see alpha101_skipped_ids() for the rest.",
        )
        write_feature_table_manifest(
            ALPHA191_OUT,
            table="alpha191",
            source_library=ALPHA191_SOURCE,
            formula_version=FORMULA_VERSION,
            columns=["symbol", "trade_date", *ALPHA191_COLUMNS],
            skipped=alpha191_skipped_ids(),
            rows_by_year={str(year): rows_191},
            build_seconds_by_year={str(year): round(elapsed, 1)},
            notes="20 of 191 ids implemented this round; see alpha191_skipped_ids() for the rest.",
        )
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: done -- alpha101 {rows_101} rows, "
            f"alpha191 {rows_191} rows, {elapsed / 60:.1f}min",
            flush=True,
        )
        summary[str(year)] = {
            "alpha101_rows": rows_101,
            "alpha191_rows": rows_191,
            "elapsed_minutes": round(elapsed / 60, 1),
        }

    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
