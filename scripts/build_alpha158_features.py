"""Step 13-F 3.1: build ``data/features/alpha158/{year}.parquet``.

docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md
section 3.1. One row per (symbol, trade_date), 154 Alpha158 columns (see
``open_composer/research/features/alpha158.py`` for the "154, not 158"
scope note), restricted to the PIT universe's full-history symbol union.

Per-year, per-symbol-batch, resumable -- same shape as
``build_intraday_daily_features.py``: each (year, symbol-batch) is written
to a scratch parquet first, so a killed/OOM'd run resumes from the last
finished batch instead of recomputing the whole year. ``[year-1, year]`` is
scanned per target year (same reasoning as ``build_daily_features.py``: the
longest window here is 60 days, comfortably inside one prior year of
history) and only the target year's rows are kept before writing.

Usage (foreground, one year, small batch for a smoke test)::

    uv run python scripts/build_alpha158_features.py --years 2026 --symbol-batch-size 50

Usage (the real multi-year backfill; intended to run capped + backgrounded)::

    ./scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/build_alpha158_features.py > /tmp/build_alpha158.log 2>&1 &

**2026-09-18 broad-universe rerun**: ``--universe-root``/``--out-dir``/
``--extra-daily-root`` (same names, same defaults-unchanged contract as
``build_daily_features.py``) let this same builder target
``data/features/alpha158_broad`` off ``data/features/universe_broad`` (9,191
symbols) with ``data/sip-delisted/by_year`` folded in so backfilled delisted
names are included::

    nohup setsid ./scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/build_alpha158_features.py \
        --universe-root data/features/universe_broad \
        --out-dir data/features/alpha158_broad \
        --extra-daily-root data/sip-delisted/by_year \
        --memory-limit 800MB > logs/alpha158_broad.log 2>&1 &
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

from open_composer.research.features.alpha158 import (  # noqa: E402
    DEFAULT_WINDOWS,
    alpha158_columns,
    build_alpha158_features,
)
from open_composer.research.features.manifest import write_feature_table_manifest  # noqa: E402
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

DAILY_ROOT = ROOT / "data" / "sip" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
OUT_DIR = ROOT / "data" / "features" / "alpha158"
DUCKDB_TMP = ROOT / "data" / "_duckdb_tmp"
ALL_YEARS = list(range(2016, 2027))
LOOKBACK_YEARS = 1
DEFAULT_SYMBOL_BATCH_SIZE = 300
SOURCE_LIBRARY = (
    "microsoft/qlib (MIT) -- qlib/contrib/data/loader.py Alpha158DL "
    "(reports/harness/source_cards/step13f_open_factor_libraries.jsonl: "
    "qlib_alpha158_definition_2026-09-09)"
)
FORMULA_VERSION = "step13f-2026-09-09-v1"


def _available_archive_years() -> list[int]:
    return sorted(int(p.name) for p in DAILY_ROOT.iterdir() if p.is_dir() and p.name.isdigit())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years", type=int, nargs="*", default=None, help="default: every archive year"
    )
    parser.add_argument("--memory-limit", default="1.2GB")
    parser.add_argument("--force", action="store_true", help="recompute even if output exists")
    parser.add_argument("--symbol-batch-size", type=int, default=DEFAULT_SYMBOL_BATCH_SIZE)
    parser.add_argument(
        "--universe-root",
        type=Path,
        default=UNIVERSE_ROOT,
        help="PIT universe panel dir whose symbol union bounds the feature set",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help="where {year}.parquet feature files go (default data/features/alpha158)",
    )
    parser.add_argument(
        "--extra-daily-root",
        type=Path,
        default=None,
        help=(
            "second bars root in {root}/{year}/*.parquet layout scanned next to "
            "data/sip/daily (e.g. data/sip-delisted/by_year for backfilled delisted names)"
        ),
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    universe_root = Path(args.universe_root)
    extra_root = Path(args.extra_daily_root) if args.extra_daily_root is not None else None
    if extra_root is not None and not any(extra_root.glob("*/*.parquet")):
        raise SystemExit(f"no parquet files under {extra_root}")

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] loading universe union symbols ...", flush=True)
    universe_symbols = sorted(universe_union_symbols(universe_root))
    print(f"universe union: {len(universe_symbols)} symbols", flush=True)

    archive_years = _available_archive_years()
    first_archive_year = archive_years[0]
    target_years = args.years or ALL_YEARS
    target_years = [y for y in target_years if y in archive_years]
    print(f"archive years available: {archive_years}", flush=True)
    print(f"target years this run: {target_years}", flush=True)

    columns = alpha158_columns(DEFAULT_WINDOWS)
    summary: dict[str, object] = {}
    for year in target_years:
        out_path = out_dir / f"{year}.parquet"
        if out_path.exists() and not args.force:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: already done, skipping", flush=True
            )
            summary[str(year)] = "skipped_existing"
            continue

        window_years = sorted({y for y in (year - LOOKBACK_YEARS, year) if y >= first_archive_year})
        glob_paths = [str(DAILY_ROOT / str(y) / "*.parquet") for y in window_years]
        if extra_root is not None:
            glob_paths += [
                str(extra_root / str(y) / "*.parquet")
                for y in window_years
                if (extra_root / str(y)).is_dir()
            ]

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

        scratch_dir = out_dir / "_scratch" / str(year)
        scratch_dir.mkdir(parents=True, exist_ok=True)
        batch_frames: list[pd.DataFrame] = []
        for batch_index, batch_symbols in enumerate(symbol_batches):
            batch_path = scratch_dir / f"batch-{batch_index:03d}.parquet"
            if batch_path.exists() and not args.force:
                batch_frames.append(pd.read_parquet(batch_path))
                continue
            batch_started = time.monotonic()
            batch_frame = build_alpha158_features(
                glob_paths,
                batch_symbols,
                memory_limit=args.memory_limit,
                temp_directory=str(DUCKDB_TMP),
            )
            batch_frame = batch_frame.loc[batch_frame["trade_date"].dt.year == year].copy()
            batch_frame.to_parquet(batch_path, index=False)
            batch_frames.append(batch_frame)
            del batch_frame
            gc.collect()
            print(
                f"  [{time.strftime('%Y-%m-%d %H:%M:%S')}] {year} batch "
                f"{batch_index + 1}/{len(symbol_batches)}: "
                f"{time.monotonic() - batch_started:.0f}s",
                flush=True,
            )

        frame = pd.concat(batch_frames, ignore_index=True).sort_values(["symbol", "trade_date"])
        del batch_frames
        gc.collect()
        tmp_path = out_path.with_suffix(".parquet.tmp")
        frame.to_parquet(tmp_path, index=False)
        tmp_path.replace(out_path)
        row_count = len(frame)
        elapsed = time.monotonic() - started
        del frame
        gc.collect()

        for path in scratch_dir.glob("batch-*.parquet"):
            path.unlink()
        scratch_dir.rmdir()

        write_feature_table_manifest(
            out_dir,
            table="alpha158",
            source_library=SOURCE_LIBRARY,
            formula_version=FORMULA_VERSION,
            columns=["symbol", "trade_date"] + columns,
            skipped=[],
            rows_by_year={str(year): row_count},
            build_seconds_by_year={str(year): round(elapsed, 1)},
            notes=(
                "154 feature columns (9 K-bar + 29 rolling groups x windows "
                "{5,10,20,30,60}); Qlib's nominal 158 also includes 4 non-rolling "
                "PRICE features (OPEN0/HIGH0/LOW0/VWAP0) not in the plan's "
                "section 3.1 formula list -- omitted, see module docstring."
            ),
        )
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: done -- {row_count} rows, "
            f"{len(columns)} feature columns, {elapsed / 60:.1f}min",
            flush=True,
        )
        summary[str(year)] = {"rows": row_count, "elapsed_minutes": round(elapsed / 60, 1)}

    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
