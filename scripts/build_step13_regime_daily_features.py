"""Step 13 Track M: builds ``data/features/regime_daily/{year}.parquet``.

docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md
section 3.1's five regime columns, **one row per trade_date** (a
market-level/cross-sectional table, not per-symbol -- unlike
``data/features/daily/{year}.parquet``, which this script reads from but
does not resemble in shape):

* ``spy_ret_20``: SPY's 20-trading-day close-to-close return.
* ``spy_gap_200sma``: SPY close / its own trailing 200-day SMA - 1.
* ``vix_close``: CBOE VIX close, from the already-fetched
  ``data/research/cboe_vix_term_structure_20260814/raw/VIX_History.csv``
  (plan: "vix_close（data/ 里已有 CBOE 指数则用...)"). Falls back to
  ``spy_vol_21`` (SPY's trailing 21-day realized vol, annualized and scaled
  to VIX-like "vol points" for rough continuity, i.e. multiplied by 100)
  for any *individual* date that file lacks, and for the *whole* series
  if its aggregate coverage over this table's date range is worse than
  95% -- the plan's own documented contingency ("没有则 spy_vol_21
  代替，并在报告里说明"). Every row also carries ``vix_close_source`` so a
  report can say honestly which one was used. Not dead code in practice:
  ``VIX_HISTORY_CSV`` is a point-in-time research snapshot (fetched
  2026-08-14, per its own directory name) that structurally cannot cover
  trade dates after that, so every date past it falls back per-row until
  the file is refreshed (found 2026-09-10 when it first blocked a real
  M1 run: 16 dates, 2026-08-14..2026-09-04, fell back).
* ``cs_dispersion_21``: cross-sectional (sample) standard deviation of
  ``ret_21`` across every symbol with a row on that ``trade_date`` in
  ``data/features/daily/`` -- i.e. the same PIT-universe-union population
  ``loop.py``'s own module docstring already documents as this kernel's
  established cross-sectional scope convention (not a new choice made
  here).
* ``breadth_50d``: fraction of that same population with
  ``close > trailing_50_session_SMA(close)`` on that date (``NULL`` -- not
  0 -- for a symbol/date without 50 prior sessions in the table, so a
  symbol's first ~50 sessions do not silently count as "below its own
  SMA").

Usage::

    ./scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/build_step13_regime_daily_features.py

DuckDB is capped at 1.5GB (plan section 6: "DuckDB memory_limit <= 1.5GB,
threads=2"), reading only the four columns (``symbol, trade_date, close,
ret_21``) this script actually needs from the daily feature table, never
the full ~48-column panel.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.adapters.data.sip_parquet import load_sip_bars  # noqa: E402

DAILY_FEATURES_ROOT = ROOT / "data" / "features" / "daily"
OUT_ROOT = ROOT / "data" / "features" / "regime_daily"
VIX_HISTORY_CSV = (
    ROOT / "data" / "research" / "cboe_vix_term_structure_20260814" / "raw" / "VIX_History.csv"
)
#: Matches every other kernel script's SIP-archive start date
#: (scripts/run_b3_grid.py, scripts/run_baseline_chain.py, etc.).
DATA_START = "2016-01-04"
DUCKDB_MEMORY_LIMIT = "1.5GB"
MIN_VIX_COVERAGE = 0.95
SMA_200_WINDOW = 200
SMA_50_WINDOW = 50
RET_20_WINDOW = 20
REALIZED_VOL_WINDOW = 21
ANNUALIZATION_SESSIONS = 252


def spy_close_series() -> pd.Series:
    """SPY's raw daily close, indexed by naive midnight Timestamp (SIP's
    tz-aware time-of-day collapsed away) -- same construction as
    ``benchmark_returns.daily_returns_on_naive_dates`` up to the point that
    function converts to returns; this needs the raw close level for the
    200-day SMA gap, not a return series.
    """
    frame = load_sip_bars("SPY", frequency="daily", start=DATA_START)
    rows = frame.loc[frame["symbol"] == "SPY"].copy()
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True)
    rows = rows.sort_values("timestamp")
    rows["trade_date"] = rows["timestamp"].dt.date.astype(str)
    rows = rows.drop_duplicates("trade_date", keep="last")
    return pd.Series(
        pd.to_numeric(rows["close"], errors="raise").to_numpy(),
        index=pd.DatetimeIndex(rows["trade_date"]),
        name="close",
    ).sort_index()


def vix_close_series() -> pd.Series | None:
    """CBOE VIX daily close from the already-fetched research CSV, or
    ``None`` if that file does not exist at all (a coverage shortfall,
    as opposed to complete absence, is handled by the caller instead --
    it needs SPY's own date index to measure coverage against).
    """
    if not VIX_HISTORY_CSV.is_file():
        return None
    frame = pd.read_csv(VIX_HISTORY_CSV)
    frame["trade_date"] = pd.to_datetime(frame["DATE"], format="%m/%d/%Y")
    frame = frame.sort_values("trade_date").drop_duplicates("trade_date", keep="last")
    return pd.Series(
        pd.to_numeric(frame["CLOSE"], errors="coerce").to_numpy(),
        index=pd.DatetimeIndex(frame["trade_date"]),
        name="vix_close",
    )


def build_spy_derived_columns() -> pd.DataFrame:
    """``trade_date, spy_ret_20, spy_gap_200sma, vix_close,
    vix_close_source`` -- one row per SPY trading day.
    """
    close = spy_close_series()
    spy_ret_20 = close.pct_change(RET_20_WINDOW)
    spy_sma_200 = close.rolling(SMA_200_WINDOW, min_periods=SMA_200_WINDOW).mean()
    spy_gap_200sma = close / spy_sma_200 - 1.0

    frame = pd.DataFrame(
        {
            "trade_date": close.index,
            "spy_ret_20": spy_ret_20.to_numpy(),
            "spy_gap_200sma": spy_gap_200sma.to_numpy(),
        }
    )

    vix = vix_close_series()
    coverage = float(vix.reindex(close.index).notna().mean()) if vix is not None else 0.0
    # Plan section 3.1's documented contingency: fall back to SPY's own
    # realized vol, scaled to roughly VIX-like "vol points" (x100) only for
    # continuity of units in a report table -- this is explicitly not a
    # VIX-equivalent measure, just a same-direction regime proxy.
    daily_returns = close.pct_change()
    realized_vol = daily_returns.rolling(
        REALIZED_VOL_WINDOW, min_periods=REALIZED_VOL_WINDOW
    ).std() * (ANNUALIZATION_SESSIONS**0.5)
    fallback_vix = realized_vol * 100.0
    if vix is not None and coverage >= MIN_VIX_COVERAGE:
        # 2026-09-10 fix: VIX_HISTORY_CSV is a point-in-time research
        # snapshot (its own directory name is dated 20260814) -- it will
        # structurally never cover trade dates after its fetch date, and
        # that gap only grows as "today" keeps advancing past it. The
        # original code chose ONE source for the *entire* series based on
        # aggregate coverage (>=95% here), which correctly picks
        # "cboe_vix_history" overall but then left every date past the
        # snapshot's cutoff as a silent NaN -- exactly the individually
        # recent, actively-scored dates a live M1/M2 run needs most. Now
        # aggregate coverage still decides whether the real series is
        # trustworthy at all, but each *individual* missing date -- not
        # just a globally-poor-coverage series -- gets the same documented
        # per-row fallback rather than staying NaN.
        aligned_vix = vix.reindex(close.index)
        missing = aligned_vix.isna()
        frame["vix_close"] = aligned_vix.where(~missing, fallback_vix).to_numpy()
        frame["vix_close_source"] = pd.Series("cboe_vix_history", index=close.index, dtype="object")
        frame.loc[missing.to_numpy(), "vix_close_source"] = (
            f"spy_vol_21_fallback_row_gap_coverage_{coverage:.2%}"
        )
    else:
        frame["vix_close"] = fallback_vix.to_numpy()
        frame["vix_close_source"] = (
            "spy_vol_21_fallback_no_vix_file"
            if vix is None
            else f"spy_vol_21_fallback_coverage_{coverage:.2%}"
        )
    return frame


def build_universe_breadth_and_dispersion(memory_limit: str = DUCKDB_MEMORY_LIMIT) -> pd.DataFrame:
    """``trade_date, cs_dispersion_21, breadth_50d`` -- one row per
    trade_date present in ``data/features/daily/``, computed entirely in
    DuckDB from just the four columns this needs.
    """
    con = duckdb.connect()
    try:
        con.execute(f"SET memory_limit='{memory_limit}'")
        con.execute("SET threads=2")
        con.execute("SET preserve_insertion_order=false")
        con.execute("SET enable_progress_bar=false")
        temp_dir = ROOT / "data" / "_duckdb_tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        con.execute(f"SET temp_directory='{temp_dir}'")
        glob = str(DAILY_FEATURES_ROOT / "*.parquet")
        query = f"""
            WITH base AS (
                SELECT symbol, trade_date, close, ret_21
                FROM read_parquet({glob!r}, union_by_name=true)
            ),
            with_sma AS (
                SELECT
                    trade_date,
                    ret_21,
                    close,
                    AVG(close) OVER (
                        PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN {SMA_50_WINDOW - 1} PRECEDING AND CURRENT ROW
                    ) AS sma_50,
                    COUNT(*) OVER (
                        PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN {SMA_50_WINDOW - 1} PRECEDING AND CURRENT ROW
                    ) AS sma_50_window_count
                FROM base
            )
            SELECT
                trade_date,
                STDDEV_SAMP(ret_21) AS cs_dispersion_21,
                AVG(
                    CASE
                        WHEN sma_50_window_count < {SMA_50_WINDOW} THEN NULL
                        WHEN close > sma_50 THEN 1.0
                        ELSE 0.0
                    END
                ) AS breadth_50d
            FROM with_sma
            GROUP BY trade_date
            ORDER BY trade_date
        """
        frame = con.execute(query).fetchdf()
    finally:
        con.close()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame


def build_regime_daily_table(memory_limit: str = DUCKDB_MEMORY_LIMIT) -> pd.DataFrame:
    spy_frame = build_spy_derived_columns()
    universe_frame = build_universe_breadth_and_dispersion(memory_limit=memory_limit)
    merged = universe_frame.merge(spy_frame, on="trade_date", how="left")
    return merged.sort_values("trade_date").reset_index(drop=True)


def write_regime_daily_by_year(frame: pd.DataFrame, out_root: Path = OUT_ROOT) -> dict[int, Path]:
    out_root.mkdir(parents=True, exist_ok=True)
    written: dict[int, Path] = {}
    years = sorted(int(year) for year in frame["trade_date"].dt.year.unique())
    for year in years:
        year_frame = frame.loc[frame["trade_date"].dt.year == year].reset_index(drop=True)
        path = out_root / f"{year}.parquet"
        year_frame.to_parquet(path, index=False)
        written[year] = path
    return written


def main() -> int:
    print("computing SPY-derived + universe breadth/dispersion columns ...", flush=True)
    frame = build_regime_daily_table()
    missing_spy = int(frame["spy_ret_20"].isna().sum())
    if missing_spy:
        print(
            f"note: {missing_spy}/{len(frame)} trade_date rows have no SPY-derived columns "
            "(before SPY's own SIP history starts or before its 200-session SMA warms up)",
            flush=True,
        )
    vix_sources = frame["vix_close_source"].value_counts().to_dict()
    print(f"vix_close_source counts: {vix_sources}", flush=True)
    written = write_regime_daily_by_year(frame)
    for year, path in sorted(written.items()):
        print(f"wrote {path} ({int((frame['trade_date'].dt.year == year).sum())} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
