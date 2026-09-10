"""Step 13-F 3.3: build ``data/features/osap_price/{year}.parquet``.

docs/plan-step-13f-open-factor-library-import-and-screening-2026-09-09.zh.md
section 3.3. Same per-year, per-symbol-batch, resumable shape as
``build_alpha158_features.py`` / ``build_alpha101_alpha191_features.py``,
with two OSAP-specific differences:

* ``LOOKBACK_YEARS = 6`` (not 1): the longest OSAP window is
  ``momseason_2_5``'s ``month_return(60)``, a ``LAG(close, 21*61=1281)`` --
  about 5.1 years of trading days -- so a 1-year lookback (fine for
  ``daily_features.py``'s 252-day max window) would silently truncate
  this column's coverage for most of every processed year, not just the
  archive's very first year.
* ``momvol`` is cross-sectional (needs every symbol's ``dolvol_63`` for a
  given date, not just one batch), so :func:`add_momvol_cross_sectional`
  is applied exactly once per year, after every symbol batch has been
  computed and concatenated -- never per-batch.

Usage (foreground smoke test)::

    uv run python scripts/build_osap_price_features.py --years 2026 --symbol-batch-size 50

Usage (the real multi-year backfill; run detached + capped)::

    nohup ./scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/build_osap_price_features.py \
        > /tmp/build_osap_price.log 2>&1 &
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
from open_composer.research.features.osap_price import (  # noqa: E402
    DEFAULT_MARKET_SYMBOL,
    OSAP_PRICE_COLUMNS,
    PER_SYMBOL_COLUMNS,
    add_momvol_cross_sectional,
    build_osap_price_features,
)
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

DAILY_ROOT = ROOT / "data" / "sip" / "daily"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
OSAP_OUT = ROOT / "data" / "features" / "osap_price"
DUCKDB_TMP = ROOT / "data" / "_duckdb_tmp"
ALL_YEARS = list(range(2016, 2027))
LOOKBACK_YEARS = 6
DEFAULT_SYMBOL_BATCH_SIZE = 300

SOURCE_LIBRARY = (
    "Chen & Zimmermann Open Source Asset Pricing (OpenSourceAP/CrossSection "
    "SignalDoc.csv), CRSP-price/volume-only signal subset, reimplemented as "
    "daily rolling proxies (originals are monthly). See "
    "reports/harness/source_cards/step13f_open_factor_libraries.jsonl, claim "
    "osap_crsp_only_signals."
)
FORMULA_VERSION = "step13f-2026-09-10-v1"
SKIPPED = [
    {
        "id": "betatail_252",
        "reason": (
            "OSAP BetaTailRisk; the plan marks this one explicitly optional "
            "(可选) and it is not implemented this round"
        ),
    }
]


def _available_archive_years() -> list[int]:
    return sorted(int(p.name) for p in DAILY_ROOT.iterdir() if p.is_dir() and p.name.isdigit())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="*", default=None)
    parser.add_argument("--memory-limit", default="1.2GB")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--symbol-batch-size", type=int, default=DEFAULT_SYMBOL_BATCH_SIZE)
    parser.add_argument("--market-symbol", default=DEFAULT_MARKET_SYMBOL)
    args = parser.parse_args()

    OSAP_OUT.mkdir(parents=True, exist_ok=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] loading universe union symbols ...", flush=True)
    universe_symbols = sorted(universe_union_symbols(UNIVERSE_ROOT))
    print(f"universe union: {len(universe_symbols)} symbols", flush=True)

    archive_years = _available_archive_years()
    first_archive_year = archive_years[0]
    target_years = [y for y in (args.years or ALL_YEARS) if y in archive_years]
    print(f"target years this run: {target_years}", flush=True)

    summary: dict[str, object] = {}
    for year in target_years:
        out_path = OSAP_OUT / f"{year}.parquet"
        if out_path.exists() and not args.force:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {year}: already done, skipping", flush=True
            )
            summary[str(year)] = "skipped_existing"
            continue

        # Full range (not just the two endpoints): a symbol's per-batch
        # ROW_NUMBER()/LAG chain must see every intervening year's rows or
        # every rolling window silently treats year-LOOKBACK_YEARS as if it
        # were immediately followed by year, corrupting every offset.
        window_years = sorted(
            {y for y in range(year - LOOKBACK_YEARS, year + 1) if y >= first_archive_year}
        )
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

        scratch = OSAP_OUT / "_scratch" / str(year)
        scratch.mkdir(parents=True, exist_ok=True)
        frames: list[pd.DataFrame] = []
        for batch_index, batch_symbols in enumerate(symbol_batches):
            batch_path = scratch / f"batch-{batch_index:03d}.parquet"
            if batch_path.exists() and not args.force:
                frames.append(pd.read_parquet(batch_path))
                continue
            batch_started = time.monotonic()
            batch = build_osap_price_features(
                glob_paths,
                batch_symbols,
                market_symbol=args.market_symbol,
                memory_limit=args.memory_limit,
                temp_directory=str(DUCKDB_TMP),
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

        # momvol is cross-sectional -- compute it once, now, over the whole
        # year's universe, not per batch.
        frame = add_momvol_cross_sectional(frame)
        assert list(frame.columns) == ["symbol", "trade_date", *OSAP_PRICE_COLUMNS]

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
            OSAP_OUT,
            table="osap_price",
            source_library=SOURCE_LIBRARY,
            formula_version=FORMULA_VERSION,
            columns=["symbol", "trade_date", *OSAP_PRICE_COLUMNS],
            skipped=SKIPPED,
            rows_by_year={str(year): rows},
            build_seconds_by_year={str(year): round(elapsed, 1)},
            notes=(
                "24 of the ~20 plan-sketched columns implemented (momseason_2_5's "
                "month_return(60) needs ~5.1 years of lookback -- LOOKBACK_YEARS=6 "
                "-- so it and residualmom_252_21/pricedelay_rsq/coskew_252 "
                "(504-row guard) are only fully covered once at least that much "
                f"prior history exists; {PER_SYMBOL_COLUMNS[-2]}/"
                f"{PER_SYMBOL_COLUMNS[-1]} are private helper columns dropped "
                "before this table is written, not part of OSAP_PRICE_COLUMNS)."
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
