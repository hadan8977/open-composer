"""Step 11 Wave A 3.3.1: minute-bar-derived daily feature table, one parquet
per year, 2016-2026.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.3 item 1: "这是本轮
最重的一次性计算...先启动它再做别的,用等待循环盯. 估计数小时". Processes one
calendar year at a time (resumable: a year whose output parquet already
exists is skipped unless ``--force``), routes 2016-2022 to
``data/sip-hist/minute/`` and 2023-2026 to ``data/sip/minute/`` (see
``intraday_daily.minute_root_for_year``), and restricts every query to the
PIT universe's full-history symbol union (``data/features/universe/``, built
by ``build_feature_universe.py`` -- run that first).

Usage (foreground, for one year / a smoke test)::

    uv run python scripts/build_intraday_daily_features.py --years 2026

Usage (the real multi-year backfill; intended to run under nohup)::

    nohup uv run python scripts/build_intraday_daily_features.py \
        > /tmp/build_intraday_daily.log 2>&1 &
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.features.intraday_daily import (  # noqa: E402
    build_intraday_daily_features,
    minute_root_for_year,
    minute_shard_paths,
)
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

SIP_ROOT = ROOT / "data" / "sip" / "minute"
SIP_HIST_ROOT = ROOT / "data" / "sip-hist" / "minute"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
OUT_DIR = ROOT / "data" / "features" / "intraday_daily"
DUCKDB_TMP = ROOT / "data" / "_duckdb_tmp"
ALL_YEARS = list(range(2016, 2027))
#: This box is 3.8GB total. A full calendar year x full universe (~2700
#: symbols) DuckDB query OOM'd even with memory_limit=2GB + threads=2 (see
#: intraday_daily.py's comment). Splitting the universe into symbol batches
#: keeps each query's working set to roughly BATCH/len(universe) of a year's
#: minute data -- overnight-return correctness (a per-symbol LAG across
#: trade_date) is unaffected because every batch still sees a symbol's FULL
#: year of history, just fewer symbols at once. The cost is re-scanning the
#: same shard files once per batch (I/O, not memory) -- acceptable, this box
#: has 87G free disk and hours to spend, not spare RAM.
DEFAULT_SYMBOL_BATCH_SIZE = 300


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years", type=int, nargs="*", default=None, help="default: 2016..2026 inclusive"
    )
    parser.add_argument("--memory-limit", default="1.5GB")
    parser.add_argument("--force", action="store_true", help="recompute even if output exists")
    parser.add_argument("--symbol-batch-size", type=int, default=DEFAULT_SYMBOL_BATCH_SIZE)
    args = parser.parse_args()

    years = args.years or ALL_YEARS
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] loading universe union symbols ...", flush=True)
    universe_symbols = sorted(universe_union_symbols(UNIVERSE_ROOT))
    print(f"universe union: {len(universe_symbols)} symbols", flush=True)

    summary: dict[str, object] = {}
    for year in years:
        out_path = OUT_DIR / f"{year}.parquet"
        if out_path.exists() and not args.force:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: already done, skipping", flush=True
            )
            summary[str(year)] = "skipped_existing"
            continue

        root = minute_root_for_year(year, sip_root=SIP_ROOT, sip_hist_root=SIP_HIST_ROOT)
        paths = minute_shard_paths(root, year)
        started = time.monotonic()
        symbol_batches = [
            universe_symbols[i : i + args.symbol_batch_size]
            for i in range(0, len(universe_symbols), args.symbol_batch_size)
        ]
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: root={root} "
            f"shard_count={len(paths)} batches={len(symbol_batches)} starting ...",
            flush=True,
        )
        if not paths:
            print(f"{year}: no shards found under {root / str(year)}, skipping", flush=True)
            summary[str(year)] = "no_shards"
            continue

        scratch_dir = OUT_DIR / "_scratch" / str(year)
        scratch_dir.mkdir(parents=True, exist_ok=True)
        batch_frames: list[pd.DataFrame] = []
        for batch_index, batch_symbols in enumerate(symbol_batches):
            batch_path = scratch_dir / f"batch-{batch_index:03d}.parquet"
            if batch_path.exists() and not args.force:
                batch_frames.append(pd.read_parquet(batch_path))
                continue
            batch_started = time.monotonic()
            batch_frame = build_intraday_daily_features(
                paths,
                batch_symbols,
                memory_limit=args.memory_limit,
                temp_directory=str(DUCKDB_TMP),
            )
            batch_frame.to_parquet(batch_path, index=False)
            batch_frames.append(batch_frame)
            print(
                f"  [{time.strftime('%Y-%m-%d %H:%M:%S')}] {year} batch {batch_index + 1}/"
                f"{len(symbol_batches)}: {len(batch_frame)} rows, "
                f"{time.monotonic() - batch_started:.0f}s",
                flush=True,
            )

        frame = pd.concat(batch_frames, ignore_index=True).sort_values(["symbol", "trade_date"])
        tmp_path = out_path.with_suffix(".parquet.tmp")
        frame.to_parquet(tmp_path, index=False)
        tmp_path.replace(out_path)
        for path in scratch_dir.glob("batch-*.parquet"):
            path.unlink()
        scratch_dir.rmdir()
        elapsed = time.monotonic() - started
        row_count = len(frame)
        symbol_count = frame["symbol"].nunique() if row_count else 0
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: done -- {row_count} rows, "
            f"{symbol_count} symbols, {elapsed / 60:.1f}min",
            flush=True,
        )
        summary[str(year)] = {
            "rows": row_count,
            "symbols": symbol_count,
            "elapsed_minutes": round(elapsed / 60, 1),
            "shard_count": len(paths),
        }

    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
