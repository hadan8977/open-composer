"""Step 11 Wave A 3.2: build the point-in-time liquidity universe.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.2. Writes
``data/features/universe/{year}.parquet`` (columns: month_end, symbol,
adv_rank, dollar_adv, close) from the full ``data/sip/daily/`` archive, then
caches Alpaca asset metadata (``data/features/universe/_asset_metadata.parquet``)
and drops symbols flagged as probable funds/ETFs.

Usage::

    uv run python scripts/build_feature_universe.py
    uv run python scripts/build_feature_universe.py --refresh-asset-metadata
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.features.asset_metadata import (  # noqa: E402
    DEFAULT_CACHE_PATH,
    load_or_fetch_asset_metadata,
)
from open_composer.research.features.universe import (  # noqa: E402
    build_pit_universe_panel,
    exclude_funds_and_etfs,
    write_universe_by_year,
)

DAILY_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")
OUT_DIR = ROOT / "data" / "features" / "universe"
ASSET_METADATA_PATH = ROOT / DEFAULT_CACHE_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-n", type=int, default=1500)
    parser.add_argument(
        "--no-top-n-cap",
        action="store_true",
        help="admit every symbol above --min-dollar-adv regardless of rank (broad universe)",
    )
    parser.add_argument(
        "--min-dollar-adv",
        type=float,
        default=None,
        help="trailing dollar-ADV floor in USD (e.g. 1e6); combine with --no-top-n-cap",
    )
    parser.add_argument("--adv-lookback-days", type=int, default=60)
    parser.add_argument("--min-close", type=float, default=5.0)
    parser.add_argument(
        "--include-delisted-root",
        type=Path,
        default=None,
        help=(
            "second bars root in {root}/{year}/*.parquet layout, e.g. "
            "data/sip-delisted/by_year (see scripts/repartition_delisted_by_year.py)"
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help="where {year}.parquet files go (default data/features/universe)",
    )
    parser.add_argument("--memory-limit", default="2GB")
    parser.add_argument("--refresh-asset-metadata", action="store_true")
    args = parser.parse_args()

    load_dotenv(dotenv_path=ROOT / ".env")

    globs: list[str] = [DAILY_GLOB]
    if args.include_delisted_root is not None:
        delisted_glob = str(args.include_delisted_root / "*" / "*.parquet")
        if not any(Path(args.include_delisted_root).glob("*/*.parquet")):
            raise SystemExit(f"no parquet files under {args.include_delisted_root}")
        globs.append(delisted_glob)
    top_n = None if args.no_top_n_cap else args.top_n
    if top_n is None and args.min_dollar_adv is None:
        raise SystemExit("--no-top-n-cap requires --min-dollar-adv")
    out_dir = Path(args.out_dir)

    started = time.monotonic()
    print(
        f"building PIT universe panel from {globs} (top_n={top_n}, "
        f"min_dollar_adv={args.min_dollar_adv}, min_close={args.min_close}) ...",
        flush=True,
    )
    panel = build_pit_universe_panel(
        globs if len(globs) > 1 else globs[0],
        adv_lookback_days=args.adv_lookback_days,
        top_n=top_n,
        min_close=args.min_close,
        min_dollar_adv=args.min_dollar_adv,
        memory_limit=args.memory_limit,
        temp_directory=str(ROOT / "data" / "_duckdb_tmp"),
    )
    raw_rows = len(panel)
    raw_symbols = panel["symbol"].nunique()
    print(f"raw panel: {raw_rows} rows, {raw_symbols} distinct symbols", flush=True)

    print("loading/fetching Alpaca asset metadata for ETF/fund exclusion ...", flush=True)
    metadata = load_or_fetch_asset_metadata(
        ASSET_METADATA_PATH, refresh=args.refresh_asset_metadata
    )
    fund_count = int(metadata["is_probable_fund_or_etf"].sum())
    print(
        f"asset metadata: {len(metadata)} symbols, {fund_count} flagged fund/ETF",
        flush=True,
    )

    filtered = exclude_funds_and_etfs(panel, metadata)
    dropped_rows = raw_rows - len(filtered)
    dropped_symbols = raw_symbols - filtered["symbol"].nunique()
    print(
        f"after ETF/fund exclusion: {len(filtered)} rows ({dropped_rows} dropped), "
        f"{filtered['symbol'].nunique()} distinct symbols ({dropped_symbols} dropped)",
        flush=True,
    )

    written = write_universe_by_year(filtered, out_dir)
    elapsed = time.monotonic() - started
    summary = {
        "globs": globs,
        "top_n": top_n,
        "min_dollar_adv": args.min_dollar_adv,
        "min_close": args.min_close,
        "raw_rows": raw_rows,
        "raw_symbols": raw_symbols,
        "asset_metadata_symbols": len(metadata),
        "asset_metadata_fund_count": fund_count,
        "filtered_rows": len(filtered),
        "filtered_symbols": filtered["symbol"].nunique(),
        "years_written": sorted(written),
        "out_dir": str(out_dir),
        "elapsed_seconds": round(elapsed, 1),
    }
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
