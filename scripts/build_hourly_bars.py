"""Build ``data/bars/hourly/{year}.parquet`` from the SIP minute archive.

Plan: ``docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md``
section 2 (A3) + section 4 step 3. Regular-session 1h bars (09:30-anchored,
see ``open_composer/research/bars/hourly.py``) for 2024-01 onward, universe =
each month's PIT top-200 dollar-ADV cohort (``data/features/universe``,
itself already a PIT panel) plus the fixed reference set {SPY, QQQ, IWM,
TQQQ}.

**Disclosed design choice**: this uses each month's *own* end-of-month ADV
ranking to decide that same month's bar-building coverage, not the prior
month's shifted-forward cohort. For a raw-bar-*availability* decision (which
symbols are worth building hourly bars for at all) rather than a trading
signal or portfolio-construction decision, this is a data-engineering
coverage choice, not a backtest look-ahead leak -- but "PIT" is explicitly in
the plan's own wording for this universe, so this note exists so the later
evaluation script (``scripts/evaluate_reversal_trend_hourly.py``) can decide
whether it needs its own stricter, shifted-cohort universe filter on top of
whatever bars exist here.

DuckDB ``memory_limit=1.5GB``, ``threads=2``, one (year, month) query at a
time -- "per symbol-month": the natural unit is one month's shard scan
filtered to that month's whole symbol list (one pass over that month's
shards), never one single-symbol query per month (which would rescan the
same shard files 200+ times over).

Checkpointed per (year, month) under ``data/bars/hourly/_checkpoints/`` so a
capped/killed run resumes without re-fetching already-built months. A year's
final ``data/bars/hourly/{year}.parquet`` + its ``MANIFEST.json`` entry are
(re)written once every month currently present in the source minute archive
for that year has a checkpoint -- never from just the months a single
invocation happened to process, which would silently write a falsely
"complete" year file for a year that is really still in progress.

Usage::

    ./scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_hourly_bars.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from open_composer.research.bars.hourly import OUTPUT_COLUMNS, resample_regular_session_hourly
from open_composer.research.features.universe import load_universe_panel

REPO_ROOT = Path(__file__).resolve().parents[1]
MINUTE_ROOT = REPO_ROOT / "data" / "sip" / "minute"
UNIVERSE_ROOT = REPO_ROOT / "data" / "features" / "universe"
OUT_ROOT = REPO_ROOT / "data" / "bars" / "hourly"
CHECKPOINT_ROOT = OUT_ROOT / "_checkpoints"

FIXED_SYMBOLS = ("SPY", "QQQ", "IWM", "TQQQ")
TOP_N_ADV = 200
MEMORY_LIMIT = "1.5GB"
THREADS = 2
START_YEAR_MONTH = (2024, 1)


def _available_year_months() -> list[tuple[int, int]]:
    """(year, month) pairs actually present under ``data/sip/minute``, restricted
    to >= :data:`START_YEAR_MONTH`.
    """
    pairs: list[tuple[int, int]] = []
    if not MINUTE_ROOT.is_dir():
        return pairs
    for year_dir in sorted(MINUTE_ROOT.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year = int(year_dir.name)
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            month = int(month_dir.name)
            if (year, month) >= START_YEAR_MONTH:
                pairs.append((year, month))
    return sorted(pairs)


def _month_universe(year: int, month: int) -> list[str]:
    """This month's PIT top-:data:`TOP_N_ADV` dollar-ADV cohort plus the fixed
    reference set. ``month_end`` is each symbol's own last trade date within
    the month, not one shared date (``universe.py`` docstring), so group by
    year-month period rather than filtering on an exact date.
    """
    panel = load_universe_panel(UNIVERSE_ROOT, years=[year])
    period = panel["month_end"].dt.to_period("M")
    target = pd.Period(year=year, month=month, freq="M")
    cohort = panel.loc[(period == target) & (panel["adv_rank"] <= TOP_N_ADV)]
    symbols = set(cohort["symbol"].unique()) | set(FIXED_SYMBOLS)
    return sorted(symbols)


def _fetch_month_minute_bars(year: int, month: int, symbols: list[str]) -> pd.DataFrame:
    shard_glob = str(MINUTE_ROOT / str(year) / f"{month:02d}" / "shard-*.parquet")
    con = duckdb.connect()
    try:
        con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
        con.execute(f"SET threads={THREADS}")
        placeholders = ", ".join("?" for _ in symbols)
        query = f"""
            SELECT symbol, timestamp, open, high, low, close, volume, trade_count, vwap
            FROM read_parquet(?)
            WHERE symbol IN ({placeholders})
        """
        return con.execute(query, [shard_glob, *symbols]).fetchdf()
    finally:
        con.close()


def _checkpoint_path(year: int, month: int) -> Path:
    return CHECKPOINT_ROOT / f"{year}-{month:02d}.parquet"


def _build_month(year: int, month: int, *, force: bool = False) -> Path:
    path = _checkpoint_path(year, month)
    if path.is_file() and not force:
        return path
    symbols = _month_universe(year, month)
    if not symbols:
        raise RuntimeError(f"no universe symbols resolved for {year}-{month:02d}")
    minute_bars = _fetch_month_minute_bars(year, month, symbols)
    hourly = resample_regular_session_hourly(minute_bars)
    CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".parquet.tmp")
    hourly.to_parquet(tmp_path, index=False)
    tmp_path.replace(path)
    return path


def _finalize_year(year: int, months_in_source: list[int]) -> dict | None:
    """Write ``data/bars/hourly/{year}.parquet`` only if every month the
    source minute archive currently has for ``year`` is checkpointed --
    never from a subset, which would silently mislabel a partial year as
    complete.
    """
    checkpoints = [_checkpoint_path(year, month) for month in months_in_source]
    if not checkpoints or not all(path.is_file() for path in checkpoints):
        return None
    frames = [pd.read_parquet(path) for path in checkpoints]
    combined = (
        pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_COLUMNS)
    )
    combined = combined.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(
        drop=True
    )
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = OUT_ROOT / f"{year}.parquet"
    tmp_path = out_path.with_suffix(".parquet.tmp")
    combined.to_parquet(tmp_path, index=False)
    tmp_path.replace(out_path)
    return {
        "months": months_in_source,
        "row_count": int(len(combined)),
        "symbol_count": int(combined["symbol"].nunique()) if not combined.empty else 0,
        "path": str(out_path.relative_to(REPO_ROOT)),
    }


def _write_manifest(new_entries: dict[int, dict]) -> None:
    """Merge ``new_entries`` into the existing ``MANIFEST.json`` (if any)
    rather than overwrite it -- a run that only touches some years must not
    erase previously recorded years.
    """
    manifest_path = OUT_ROOT / "MANIFEST.json"
    manifest: dict = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
    years = manifest.get("years", {})
    years.update({str(year): entry for year, entry in new_entries.items()})
    manifest.update(
        {
            "built_at": datetime.now(UTC).isoformat(),
            "universe": f"data/features/universe top-{TOP_N_ADV} dollar ADV per month + "
            f"{list(FIXED_SYMBOLS)}",
            "session": "09:30-16:00 America/New_York, 09:30-anchored, 6x60min + 1x30min buckets",
            "source": "data/sip/minute/{year}/{month}/shard-*.parquet",
            "start_year_month": f"{START_YEAR_MONTH[0]}-{START_YEAR_MONTH[1]:02d}",
            "years": dict(sorted(years.items(), key=lambda kv: int(kv[0]))),
        }
    )
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=START_YEAR_MONTH[0])
    parser.add_argument("--end-year", type=int, default=None, help="default: latest available")
    parser.add_argument("--force", action="store_true", help="rebuild months even if checkpointed")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    all_pairs = _available_year_months()
    if not all_pairs:
        print(
            f"no minute-archive months found >= {START_YEAR_MONTH} under {MINUTE_ROOT}",
            file=sys.stderr,
        )
        return 1

    full_by_year: dict[int, list[int]] = {}
    for year, month in all_pairs:
        full_by_year.setdefault(year, []).append(month)

    end_year = args.end_year or all_pairs[-1][0]
    pairs = [(year, month) for (year, month) in all_pairs if args.start_year <= year <= end_year]
    if not pairs:
        print(
            f"no months in range start_year={args.start_year} end_year={end_year}", file=sys.stderr
        )
        return 1

    for year, month in pairs:
        started = time.time()
        path = _build_month(year, month, force=args.force)
        elapsed = time.time() - started
        rows = len(pd.read_parquet(path, columns=["symbol"]))
        print(
            f"[{year}-{month:02d}] checkpoint ready: {rows} rows ({elapsed:.1f}s) -> {path}",
            flush=True,
        )

    new_entries: dict[int, dict] = {}
    for year in sorted({year for year, _ in pairs}):
        entry = _finalize_year(year, sorted(full_by_year[year]))
        if entry is not None:
            new_entries[year] = entry
            print(
                f"[{year}] finalized: {entry['row_count']} rows, "
                f"{entry['symbol_count']} symbols -> {entry['path']}",
                flush=True,
            )
        else:
            print(f"[{year}] not finalized yet (missing checkpoints)", flush=True)

    if new_entries:
        _write_manifest(new_entries)
        print(f"MANIFEST.json updated for years: {sorted(new_entries)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
