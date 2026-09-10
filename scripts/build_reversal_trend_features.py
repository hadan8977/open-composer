"""Step 13-P scope addition, Track F part A1: build
``data/features/reversal_trend/{year}.parquet``.

docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md
section A1. Same per-year, per-symbol-batch, resumable shape as
``build_alpha158_features.py``/``build_alpha101_alpha191_features.py``.
``LOOKBACK_YEARS = 1`` (not OSAP's 6): this table's indicators are recursive
EMA/RMA filters with no hard N-row warm-up, and the state machine's longest
cross-bar memory (``arm_max_bars``/``bull_cooldown`` etc.) is a few dozen
bars, not months -- see ``reversal_trend_daily.py``'s module docstring.

Usage (foreground smoke test)::

    uv run python scripts/build_reversal_trend_features.py --years 2026 --symbol-batch-size 50

Usage (the real multi-year backfill; run detached + capped)::

    nohup ./scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/build_reversal_trend_features.py \
        > /tmp/build_reversal_trend.log 2>&1 &
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

from open_composer.research.features.manifest import write_feature_table_manifest  # noqa: E402
from open_composer.research.features.reversal_trend_daily import (  # noqa: E402
    REVERSAL_TREND_COLUMNS,
    build_reversal_trend_features,
)
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

DAILY_ROOT = ROOT / "data" / "sip" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
OUT_ROOT = ROOT / "data" / "features" / "reversal_trend"
ALL_YEARS = list(range(2016, 2027))
LOOKBACK_YEARS = 1
DEFAULT_SYMBOL_BATCH_SIZE = 300

SOURCE_LIBRARY = (
    "User-provided Pine script docs/inputs/pine/reversal_trend_0522.pine, ported to "
    "Python by the Track P agent (open_composer/research/pine_port/reversal_trend.py, "
    "compute_reversal_trend -- reused here, not reimplemented) per "
    "docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md "
    "section 1; this table adds the daily-factor derived columns section A1 lists."
)
FORMULA_VERSION = "step13p-2026-09-10-v1"


def _available_archive_years() -> list[int]:
    return sorted(int(p.name) for p in DAILY_ROOT.iterdir() if p.is_dir() and p.name.isdigit())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="*", default=None)
    parser.add_argument("--memory-limit", default="1.2GB")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--symbol-batch-size", type=int, default=DEFAULT_SYMBOL_BATCH_SIZE)
    args = parser.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] loading universe union symbols ...", flush=True)
    universe_symbols = sorted(universe_union_symbols(UNIVERSE_ROOT))
    print(f"universe union: {len(universe_symbols)} symbols", flush=True)

    archive_years = _available_archive_years()
    first_archive_year = archive_years[0]
    target_years = [y for y in (args.years or ALL_YEARS) if y in archive_years]
    print(f"target years this run: {target_years}", flush=True)

    summary: dict[str, object] = {}
    for year in target_years:
        out_path = OUT_ROOT / f"{year}.parquet"
        if out_path.exists() and not args.force:
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

        scratch = OUT_ROOT / "_scratch" / str(year)
        scratch.mkdir(parents=True, exist_ok=True)
        frames: list[pd.DataFrame] = []
        for batch_index, batch_symbols in enumerate(symbol_batches):
            batch_path = scratch / f"batch-{batch_index:03d}.parquet"
            if batch_path.exists() and not args.force:
                frames.append(pd.read_parquet(batch_path))
                continue
            batch_started = time.monotonic()
            batch = build_reversal_trend_features(
                glob_paths, batch_symbols, memory_limit=args.memory_limit
            )
            if batch.empty:
                continue
            batch = batch.loc[batch["trade_date"].dt.year == year].copy()
            batch.to_parquet(batch_path, index=False)
            frames.append(batch)
            del batch
            gc.collect()
            print(
                f"  [{time.strftime('%Y-%m-%d %H:%M:%S')}] {year} batch "
                f"{batch_index + 1}/{len(symbol_batches)}: {time.monotonic() - batch_started:.0f}s",
                flush=True,
            )

        frame = pd.concat(frames, ignore_index=True).sort_values(["symbol", "trade_date"])
        del frames
        gc.collect()

        tmp_path = out_path.with_suffix(".parquet.tmp")
        frame.to_parquet(tmp_path, index=False)
        tmp_path.replace(out_path)
        rows = len(frame)
        del frame
        gc.collect()

        for path in scratch.glob("batch-*.parquet"):
            path.unlink()
        scratch.rmdir()

        elapsed = time.monotonic() - started
        write_feature_table_manifest(
            OUT_ROOT,
            table="reversal_trend",
            source_library=SOURCE_LIBRARY,
            formula_version=FORMULA_VERSION,
            columns=["symbol", "trade_date", *REVERSAL_TREND_COLUMNS],
            skipped=[],
            rows_by_year={str(year): rows},
            build_seconds_by_year={str(year): round(elapsed, 1)},
            notes=(
                "All 25 plan-listed columns implemented (plan's own count, '约 24 "
                "列', is approximate); state machine/indicators are Track P's "
                "compute_reversal_trend, reused not reimplemented. 4 signal "
                "columns (rt_bull_signal/rt_recl_signal/rt_bear_signal/"
                "rt_recs_signal) are event-study-only; the other 21 are "
                "screened by 3.5's rank-IC (see reversal_trend_daily.py's "
                "module docstring for the os_active/ob_active judgment call)."
            ),
        )
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: done -- {rows} rows, "
            f"{elapsed / 60:.1f}min",
            flush=True,
        )
        summary[str(year)] = {"rows": rows, "elapsed_minutes": round(elapsed / 60, 1)}

    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
