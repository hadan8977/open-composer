"""H-20260916-07 follow-up: point-in-time FINRA daily short-VOLUME-ratio features.

Card: ``reports/research/hypotheses/H-20260916-07-finra-short-interest-avoid-list.md``
Input: ``data/raw/finra_short_volume/parsed.parquet`` (written by
``scripts/collect_finra_short_volume.py``).
Output: ``data/features/short_volume/{year}.parquet`` -- one row per
``(symbol, trade_date)``, the same key shape every other library under
``data/features/`` uses.

The construct (why a ratio, not a raw share count)
----------------------------------------------------
``scripts/collect_finra_short_volume.py``'s docstring explains why this is a
different measurement from the one card H-20260916-07 already refuted and
from the raw-share-count reading ``collect_finra_short_interest.py``
deliberately declined: the literature (Boehmer, Jones and Zhang) works with
the SHORT VOLUME RATIO -- short volume divided by that day's reported total
volume -- as a daily flow, and with that ratio's own trailing distribution,
not with the share count in isolation. This module computes, for every
``(symbol, trade_date)``:

``short_volume_ratio``
    ``short_volume / total_volume`` for the latest FINRA file visible by
    ``trade_date`` (see "Point-in-time rule" below). Both volumes come from
    FINRA's own consolidated (``CNMS``) file and are **off-exchange (TRF /
    ADF / ORF -reported) volume only** -- not full consolidated-tape volume;
    see the collector's docstring. Null when that day's ``total_volume`` is
    not positive (a ratio with no denominator is not a measurement).
``short_volume_ratio_mean_{5,21,60}`` / ``_zscore_{5,21,60}``
    Trailing mean and z-score of ``short_volume_ratio`` over the symbol's own
    prior 5/21/60 US equity **sessions** (calendar sessions, not "however
    many raw rows happen to exist" -- see "Gap handling" below), computed
    with DuckDB window functions and the same warm-up guard
    ``open_composer.research.features.daily_features.build_daily_features``
    uses (``rn >= window`` before a window is populated at all, else NULL --
    matches pandas' ``rolling(window).std()`` default ``min_periods=window``).
    The z-score's denominator is a sample standard deviation over the same
    window; a null or non-positive standard deviation (fewer than two real
    observations in the window) yields a null z-score, never a
    division-by-zero or a spuriously large number.

Point-in-time rule (the only visibility rule in this file)
-------------------------------------------------------------
A FINRA daily short-volume file for trade date ``d`` is usable starting the
**next US equity session after d**, per the publication evidence recorded in
``collect_finra_short_volume.py`` (FINRA posts by ~18:00 ET the same evening,
after that session's own regular trading hours have already closed, so no
session on ``d`` itself could ever have reacted to it). Concretely: a feature
row keyed ``(symbol, trade_date=t)`` uses the FINRA record whose own
``trade_date`` is ``t``'s immediately preceding US equity session, never
``t`` itself and never anything later. This is a fixed one-session shift
(unlike the bimonthly short-interest snapshot's variable staleness), computed
once as a ``(observation_date -> feature_date)`` map via
``open_composer.market_calendar.next_us_equity_session`` and joined by exact
session equality -- there is no "latest available as of" fallback here,
which is deliberate (see "Gap handling").

Gap handling (an explicit design choice, recorded per the task's own rule
that a silent hole becomes a fake signal)
-------------------------------------------------------------------------
The grid this module computes over is the **full cross product of the PIT
universe symbol union and every US equity session in the build window** --
not just the ``(symbol, trade_date)`` pairs that happen to exist in the raw
archive. This means:

* A trade date whose raw file failed to download (a collector-side gap) is
  simply **absent** from the raw table, so every symbol's row for the
  following session's ``short_volume_ratio`` is **NULL** -- not carried
  forward from the last good day, and not silently skipped when computing
  the 5/21/60-session rolling stats (DuckDB's window frame spans exactly N
  *calendar* grid rows regardless of how many are non-null, so a gap
  genuinely shrinks the effective sample inside the window rather than
  quietly compacting the window to N *available* rows).
* Symbols with no FINRA short-volume footprint at all in a given period (an
  ETF/OTC name FINRA's TRF/ADF/ORF feed never carried, or a name not yet
  admitted to the PIT universe) get an all-null row rather than being
  dropped from the grid, so a downstream consumer can distinguish
  "covered, this session is a genuine gap" from "never covered" by checking
  ``record_present`` -- but note this module cannot itself tell "not yet
  IPO'd" apart from "FINRA never reports this symbol"; both look identical
  (an all-null run). A consumer needing that distinction must cross-reference
  ``data/features/daily`` for the symbol's own trading history.
* This is a heavier, more literal construction than
  ``scripts/build_daily_features.py``'s (whose row extent is implicitly
  bounded by whatever the source price archive actually contains for a
  symbol); it is deliberate here because the task requires gaps to surface as
  explicit nulls rather than as absent rows, and the FINRA short-volume feed
  alone cannot tell us a symbol's true listing window the way a price archive
  can. Recorded, not silently absorbed -- the same discipline
  ``build_daily_features.py``'s own docstring uses for its 2-year lookback
  compromise.

Universe restriction
---------------------
``--universe-root`` takes the same contract as ``scripts/build_daily_features.py``:
a PIT universe panel directory whose **symbol union across all history**
(``open_composer.research.features.universe.universe_union_symbols``) bounds
the feature set. This is the flat union, not the per-session top-N cohort
``scripts/build_short_interest_features.py`` uses -- the task specifies this
module's contract should match ``build_daily_features.py``'s, and the two are
genuinely different (the flat union is a superset of any month's own PIT
cohort, cheaper to compute and index against, and is what
``build_daily_features.py`` already uses to decide "worth computing a row
for" for every other daily-archive-scale feature table in this repo).

Per-year, per-batch execution
-------------------------------
Each target year is built (and may be skipped if already built, absent
``--force``) independently, mirroring ``build_daily_features.py``'s
per-year loop: a ``year-1..year`` DuckDB window supplies enough trailing
history to warm up the 60-session rolling stats without scanning the whole
archive, and the frame is written and discarded before the next year starts
so peak resident memory stays bounded to roughly two years of
(universe union x sessions) rather than the full ~8-year archive.

Usage::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/build_short_volume_features.py --years 2026 \\
        --memory-limit 700MB
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.market_calendar import (  # noqa: E402
    next_us_equity_session,
    us_equity_session_dates,
)
from open_composer.research.features.universe import universe_union_symbols  # noqa: E402

PARSED_PATH = ROOT / "data" / "raw" / "finra_short_volume" / "parsed.parquet"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
SHORT_VOLUME_ROOT = ROOT / "data" / "features" / "short_volume"
DUCKDB_TMP = ROOT / "data" / "_duckdb_tmp"

DEFAULT_MEMORY_LIMIT = "700MB"
#: FINRA's free daily short-volume archive starts 2018-08-01 (see the
#: collector's module docstring); 2018 is therefore the first year with any
#: real coverage, even though it only covers August onward.
DEFAULT_START_YEAR = 2018
#: Extra prior calendar year of raw history scanned per target year, purely
#: to warm up the 60-session trailing window -- same role as
#: ``build_daily_features.py``'s ``LOOKBACK_YEARS``.
LOOKBACK_YEARS = 1

ROLLING_WINDOWS: tuple[int, ...] = (5, 21, 60)

#: Non-key factor columns, in table order. The multiple-testing denominator
#: for any screen built on this table.
FEATURE_COLUMNS: tuple[str, ...] = (
    "short_volume_ratio",
    *(
        name
        for window in ROLLING_WINDOWS
        for name in (f"short_volume_ratio_mean_{window}", f"short_volume_ratio_zscore_{window}")
    ),
)

#: Point-in-time provenance and raw inputs, kept alongside the factors so a
#: report can quote coverage without reopening the raw archive.
METADATA_COLUMNS: tuple[str, ...] = (
    "observation_date",
    "publication_date",
    "visible_date",
    "short_volume",
    "short_exempt_volume",
    "total_volume",
    "market_facilities",
    *(f"short_volume_ratio_std_{window}" for window in ROLLING_WINDOWS),
    "record_present",
)


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _guard(min_rows: int, expr: str) -> str:
    """NULL until the window has truly seen ``min_rows`` calendar grid rows
    for this symbol -- see ``build_daily_features.py``'s identical helper and
    the module docstring's "Gap handling" section for why this is keyed on
    calendar position (``rn``), not on how many of those rows are non-null.
    """
    return f"CASE WHEN rn >= {min_rows} THEN {expr} ELSE NULL END"


def _session_shift_frame(start: date, end: date) -> pd.DataFrame:
    """``(obs_date, feature_date)`` for every US equity session in
    ``[start, end]``, where ``feature_date`` is the next session after
    ``obs_date`` -- the fixed one-session publication-lag map (see module
    docstring). Sessions are exchange sessions, so weekends/holidays are
    already excluded on both sides.
    """
    sessions = us_equity_session_dates(start, end)
    return pd.DataFrame(
        {
            "obs_date": [pd.Timestamp(day) for day in sessions],
            "feature_date": [pd.Timestamp(next_us_equity_session(day)) for day in sessions],
        }
    )


def build_year(
    year: int,
    *,
    universe_symbols: list[str],
    as_of: date,
    memory_limit: str,
) -> pd.DataFrame:
    """One year of the feature table, built and returned as a single frame."""
    window_start = date(year - LOOKBACK_YEARS, 1, 1)
    window_end = min(date(year, 12, 31), as_of)
    if window_start > window_end:
        return pd.DataFrame()
    shift = _session_shift_frame(window_start, window_end)
    if shift.empty:
        return pd.DataFrame()

    connection = duckdb.connect()
    try:
        connection.execute(f"SET memory_limit='{memory_limit}'")
        connection.execute("SET threads=2")
        connection.execute("SET preserve_insertion_order=false")
        DUCKDB_TMP.mkdir(parents=True, exist_ok=True)
        connection.execute(f"SET temp_directory='{DUCKDB_TMP}'")
        connection.register("_universe_symbols", pd.DataFrame({"symbol": universe_symbols}))
        connection.register("_sessions", pd.DataFrame({"trade_date": shift["obs_date"]}))
        connection.register("_session_shift", shift)

        window_selects = ",\n".join(
            f"    {_guard(window, f'AVG(short_volume_ratio) OVER w{window}')} "
            f"AS short_volume_ratio_mean_{window},\n"
            f"    {_guard(window, f'STDDEV_SAMP(short_volume_ratio) OVER w{window}')} "
            f"AS short_volume_ratio_std_{window}"
            for window in ROLLING_WINDOWS
        )
        window_defs = ",\n".join(
            f"        w{window} AS (PARTITION BY symbol ORDER BY trade_date "
            f"ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW)"
            for window in ROLLING_WINDOWS
        )
        zscore_selects = ",\n".join(
            f"    CASE WHEN short_volume_ratio_std_{window} > 0 THEN "
            f"(short_volume_ratio - short_volume_ratio_mean_{window}) "
            f"/ short_volume_ratio_std_{window} END AS short_volume_ratio_zscore_{window}"
            for window in ROLLING_WINDOWS
        )

        query = f"""
            WITH grid AS (
                SELECT u.symbol, s.trade_date
                FROM _universe_symbols u
                CROSS JOIN _sessions s
            ),
            raw AS (
                SELECT
                    symbol, trade_date, publication_date, visible_date,
                    short_volume, short_exempt_volume, total_volume, market_facilities,
                    CASE WHEN total_volume > 0 THEN short_volume / total_volume END
                        AS short_volume_ratio
                FROM read_parquet('{PARSED_PATH.as_posix()}')
                WHERE trade_date BETWEEN '{window_start.isoformat()}' AND '{window_end.isoformat()}'
                  AND symbol IN (SELECT symbol FROM _universe_symbols)
            ),
            joined AS (
                SELECT
                    grid.symbol, grid.trade_date,
                    raw.publication_date, raw.visible_date,
                    raw.short_volume, raw.short_exempt_volume, raw.total_volume,
                    raw.market_facilities, raw.short_volume_ratio
                FROM grid
                LEFT JOIN raw ON raw.symbol = grid.symbol AND raw.trade_date = grid.trade_date
            ),
            numbered AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_date) AS rn
                FROM joined
            ),
            stats AS (
                SELECT
                    numbered.*,
{window_selects}
                FROM numbered
                WINDOW
{window_defs}
            ),
            scored AS (
                SELECT
                    stats.*,
{zscore_selects}
                FROM stats
            )
            SELECT
                scored.symbol,
                shift.feature_date AS trade_date,
                scored.trade_date AS observation_date,
                scored.publication_date,
                scored.visible_date,
                scored.short_volume,
                scored.short_exempt_volume,
                scored.total_volume,
                scored.market_facilities,
                scored.short_volume_ratio,
                scored.short_volume_ratio_mean_5,
                scored.short_volume_ratio_std_5,
                scored.short_volume_ratio_zscore_5,
                scored.short_volume_ratio_mean_21,
                scored.short_volume_ratio_std_21,
                scored.short_volume_ratio_zscore_21,
                scored.short_volume_ratio_mean_60,
                scored.short_volume_ratio_std_60,
                scored.short_volume_ratio_zscore_60,
                (scored.short_volume_ratio IS NOT NULL) AS record_present
            FROM scored
            JOIN _session_shift shift ON shift.obs_date = scored.trade_date
            WHERE shift.feature_date >= '{date(year, 1, 1).isoformat()}'
              AND shift.feature_date <= '{date(year, 12, 31).isoformat()}'
            ORDER BY trade_date, symbol
        """
        frame = connection.execute(query).fetchdf()
    finally:
        connection.close()

    if frame.empty:
        return frame
    for column in ("trade_date", "observation_date", "publication_date", "visible_date"):
        frame[column] = pd.to_datetime(frame[column])
    columns = ["symbol", "trade_date", *FEATURE_COLUMNS, *METADATA_COLUMNS]
    return frame[columns].sort_values(["trade_date", "symbol"], ignore_index=True)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument(
        "--years",
        type=int,
        nargs="*",
        default=None,
        help="restrict to these target years (default: start-year..end-year)",
    )
    parser.add_argument(
        "--universe-root",
        type=Path,
        default=UNIVERSE_ROOT,
        help="PIT universe panel dir whose symbol union bounds the feature set",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=SHORT_VOLUME_ROOT,
        help="where {year}.parquet feature files go (default data/features/short_volume)",
    )
    parser.add_argument("--memory-limit", default=DEFAULT_MEMORY_LIMIT)
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="last feature date, YYYY-MM-DD (default: today). Sessions after this date "
        "get no row, rather than a row that is stale only because the future has not "
        "happened yet.",
    )
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not PARSED_PATH.exists():
        raise SystemExit(
            f"no parsed FINRA short-volume archive at {PARSED_PATH}; run "
            "scripts/collect_finra_short_volume.py --stage download then --stage parse"
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    target_years = args.years if args.years else list(range(args.start_year, args.end_year + 1))

    universe_symbols = sorted(universe_union_symbols(Path(args.universe_root)))
    log(f"PIT universe union ({args.universe_root}): {len(universe_symbols):,} symbols")
    log(f"target years: {target_years}, as_of={as_of}")

    written: list[str] = []
    coverage: dict[str, float] = {}
    for year in target_years:
        target = out_dir / f"{year}.parquet"
        if target.exists() and not args.force:
            log(f"{year}: already built")
            written.append(str(target))
            continue
        started = time.monotonic()
        frame = build_year(
            year,
            universe_symbols=universe_symbols,
            as_of=as_of,
            memory_limit=args.memory_limit,
        )
        elapsed = time.monotonic() - started
        if frame.empty:
            log(f"{year}: no rows (out of range or before any coverage)")
            continue
        temporary = target.with_suffix(".parquet.part")
        frame.to_parquet(temporary, index=False, compression="zstd")
        temporary.replace(target)
        written.append(str(target))
        coverage[str(year)] = float(frame["record_present"].mean())
        log(
            f"{year}: {len(frame):,} rows, {frame['symbol'].nunique():,} symbols, "
            f"record present {coverage[str(year)]:.2%}, {elapsed:.1f}s"
        )
        del frame
        gc.collect()

    manifest = {
        "card": "H-20260916-07",
        "built_at": datetime.now().astimezone().isoformat(),
        "as_of": as_of.isoformat(),
        "source_parsed_archive": str(PARSED_PATH.relative_to(ROOT)),
        "universe_root": str(Path(args.universe_root)),
        "visibility_rule": "next_us_equity_session(trade_date), fixed one-session lag "
        "(no forward fill; see module docstring 'Gap handling')",
        "rolling_windows_sessions": list(ROLLING_WINDOWS),
        "short_volume_ratio_denominator": "FINRA CNMS total_volume "
        "(off-exchange TRF/ADF/ORF-reported volume, not full consolidated-tape volume)",
        "feature_columns": list(FEATURE_COLUMNS),
        "metadata_columns": list(METADATA_COLUMNS),
        "coverage_share_record_present": coverage,
        "years": written,
    }
    (out_dir / "_build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    log(f"wrote {out_dir / '_build_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
