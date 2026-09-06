"""Step 11 Wave A 3.3.1: minute-bar-derived daily aggregates.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.3 item 1. One row
per (symbol, trading day), computed entirely from 1-minute SIP bars, restricted
to the regular session (09:30-16:00 America/New_York) and to the union of
symbols that ever appeared in the PIT universe (``universe.py``).

**Two data roots, read separately then concatenated at the year level, never
merged as directories** (project safety boundary): years 2016-2022 live under
``data/sip-hist/minute/``, years 2023-2026 under ``data/sip/minute/`` --
:func:`minute_root_for_year` is the single place that routing decision is
made. There is no calendar-year overlap between the two roots, so "read
separately, concatenate" degenerates to "pick the one right root per year";
no row-level de-duplication is ever needed *across* roots.

**Within** ``data/sip/minute/2023/`` specifically there IS a same-root overlap:
that year alone has both the retired whole-year shard layout
(``data/sip/minute/2023/shard-*.parquet``, 317 files) and the current
month-sharded layout (``data/sip/minute/2023/{month}/shard-*.parquet``,
9612 files) from two different fetch invocations covering the same bars --
this is the exact situation ``open_composer.adapters.data.sip_parquet``'s
loader docstring warns about ("rows are de-duplicated on (symbol,
timestamp)"). :func:`minute_shard_paths` collects both layouts for whichever
year has them, and the aggregation query's ``dedup`` CTE
(``GROUP BY symbol, timestamp`` with ``ANY_VALUE`` before the daily
aggregation) collapses duplicate minute bars before they can double-count
volume/trade_count or distort realized volatility. No other year has this
overlap (checked against the real archive on 2026-09-06: legacy-layout file
count is 0 for every year except 2023's 317).

Memory: the raw minute-bar volume for the full active universe across 11
years is far larger than this 3.8GB box's RAM (roughly 60GB of parquet across
both roots). This module never materializes raw minute rows into pandas --
the entire de-dup + daily aggregation runs as one DuckDB query per year, with
``memory_limit`` capped and a spill ``temp_directory`` set, so DuckDB's own
out-of-core hash/window execution carries the memory risk instead of a Python
process. The output (one row per symbol per trading day) is small regardless
of how much raw data fed it.

**Implementation choices not fully pinned by the plan text** (decided and
recorded here, not tried-until-passing):

* "日内收益偏度" (intraday return skew) is the skewness of the day's
  *1-minute* log returns (the same distribution ``intraday_realized_vol``'s
  standard deviation is taken over), not some skew of a single scalar
  open-to-close return (which is not a distribution and has no skew). This
  keeps both moments defined over the same underlying sample.
* "|收益|/成交额 (Amihud 日值)" is computed from the day's own open-to-close
  intraday return (``abs(intraday_return) / dollar_volume``), not a
  close-to-close return that would require reaching into the previous day's
  *official daily-archive* close. A separate, standard close-to-close 21-day
  rolling Amihud is computed later directly from ``data/sip/daily/`` in
  ``daily_features.py``'s liquidity block -- the two are deliberately
  different measurements sharing one name in the plan's prose, and both are
  kept because they answer different questions (intraday-only impact here,
  multi-day price-impact-of-flow there).
* "收盘价相对全天VWAP的偏离" uses Alpaca's own per-minute ``vwap`` field
  (intra-bar VWAP, more accurate than a close-only proxy) volume-weighted
  across the session to build the day's VWAP, rather than approximating VWAP
  from minute closes alone.
* Only regular-session bars count everywhere in this table (including the
  plain "成交笔数" trade-count column) for internal consistency with the
  session-relative features (30-minute volume shares, VWAP deviation) that
  are only meaningful against the same regular-session sample.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import duckdb
import pandas as pd

#: 2016-2022 backfill root vs. 2023-2026 live root -- see module docstring.
LEGACY_ROOT_LAST_YEAR = 2022
DEFAULT_MEMORY_LIMIT = "2GB"
REGULAR_SESSION_START = "09:30:00"
REGULAR_SESSION_END = "16:00:00"
OPENING_WINDOW_END = "10:00:00"
CLOSING_WINDOW_START = "15:30:00"

INTRADAY_DAILY_COLUMNS = (
    "symbol",
    "trade_date",
    "overnight_return",
    "intraday_return",
    "intraday_realized_vol",
    "intraday_amplitude",
    "open_30min_volume_share",
    "close_30min_volume_share",
    "vwap_deviation",
    "intraday_skew",
    "trade_count",
    "amihud_intraday",
)


def minute_root_for_year(year: int, *, sip_root: Path, sip_hist_root: Path) -> Path:
    """Which archive root holds ``year``'s minute bars -- see module docstring."""
    return sip_hist_root if year <= LEGACY_ROOT_LAST_YEAR else sip_root


def minute_shard_paths(minute_root: Path, year: int) -> list[str]:
    """Every minute shard file for ``year`` under ``minute_root``, covering
    both the legacy whole-year layout and the current month-sharded layout
    (whichever exist -- most years only have the latter).
    """
    year_dir = minute_root / str(year)
    if not year_dir.is_dir():
        return []
    legacy = sorted(str(path) for path in year_dir.glob("shard-*.parquet"))
    month_sharded = sorted(str(path) for path in year_dir.glob("*/shard-*.parquet"))
    return legacy + month_sharded


def build_intraday_daily_features(
    minute_paths: list[str],
    universe_symbols: Iterable[str],
    *,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_directory: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Run the full dedup -> regular-session-filter -> daily-aggregate ->
    overnight-return pipeline for exactly the shard files in ``minute_paths``
    (already resolved to one year/root by the caller) and exactly the symbols
    in ``universe_symbols``. Returns a frame with
    :data:`INTRADAY_DAILY_COLUMNS`, one row per (symbol, trade_date), sorted.

    Returns an empty frame (correct columns, zero rows) when ``minute_paths``
    is empty, rather than raising -- a year with no minute shards yet (e.g.
    the archive has not caught up) is a legitimate, recordable state.
    """
    symbols = sorted({symbol.upper() for symbol in universe_symbols})
    if not minute_paths or not symbols:
        return pd.DataFrame(columns=list(INTRADAY_DAILY_COLUMNS))

    owns_connection = con is None
    connection = con or duckdb.connect()
    try:
        connection.execute(f"SET memory_limit='{memory_limit}'")
        # This box is 3.8GB total; DuckDB's default thread count (one per
        # CPU core, 6 here) multiplies per-thread hash-table/window-buffer
        # memory and was observed to hit "failed to pin block" OOM on a full
        # calendar year of minute shards even with memory_limit=2GB and a
        # spill directory configured. Two threads plus dropping
        # insertion-order preservation (irrelevant here -- the query ends
        # with an explicit ORDER BY) noticeably lowers peak RSS.
        connection.execute("SET threads=2")
        connection.execute("SET preserve_insertion_order=false")
        if temp_directory is not None:
            Path(temp_directory).mkdir(parents=True, exist_ok=True)
            connection.execute(f"SET temp_directory='{temp_directory}'")
        connection.register("_universe_symbols", pd.DataFrame({"symbol": symbols}))
        query = f"""
            WITH raw AS (
                SELECT symbol, timestamp, open, high, low, close, volume, trade_count, vwap
                FROM read_parquet({minute_paths!r})
                WHERE symbol IN (SELECT symbol FROM _universe_symbols)
            ),
            dedup AS (
                -- Collapses the 2023 legacy/month-sharded overlap (and any
                -- other accidental duplicate fetch) before it can double-
                -- count volume or distort realized volatility. Values are
                -- expected to be identical across duplicate rows for the
                -- same (symbol, timestamp); ANY_VALUE picks one arbitrarily,
                -- matching the pandas loader's drop_duplicates(keep="first").
                SELECT
                    symbol,
                    timestamp,
                    ANY_VALUE(open) AS open,
                    ANY_VALUE(high) AS high,
                    ANY_VALUE(low) AS low,
                    ANY_VALUE(close) AS close,
                    ANY_VALUE(volume) AS volume,
                    ANY_VALUE(trade_count) AS trade_count,
                    ANY_VALUE(vwap) AS vwap
                FROM raw
                GROUP BY symbol, timestamp
            ),
            timed AS (
                SELECT
                    symbol,
                    timestamp,
                    CAST((timestamp AT TIME ZONE 'America/New_York') AS DATE) AS trade_date,
                    (timestamp AT TIME ZONE 'America/New_York')::TIME AS et_time,
                    open, high, low, close, volume, trade_count, vwap
                FROM dedup
            ),
            session_bars AS (
                SELECT
                    *,
                    ln(close / NULLIF(
                        LAG(close) OVER (PARTITION BY symbol, trade_date ORDER BY timestamp),
                        0
                    )) AS minute_log_return
                FROM timed
                WHERE et_time >= TIME '{REGULAR_SESSION_START}'
                  AND et_time < TIME '{REGULAR_SESSION_END}'
            ),
            ordered AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY symbol, trade_date ORDER BY timestamp
                    ) AS rn_asc,
                    ROW_NUMBER() OVER (
                        PARTITION BY symbol, trade_date ORDER BY timestamp DESC
                    ) AS rn_desc
                FROM session_bars
            ),
            daily AS (
                SELECT
                    symbol,
                    trade_date,
                    MAX(CASE WHEN rn_asc = 1 THEN open END) AS session_open,
                    MAX(CASE WHEN rn_desc = 1 THEN close END) AS session_close,
                    MAX(high) AS session_high,
                    MIN(low) AS session_low,
                    STDDEV_SAMP(minute_log_return) AS intraday_realized_vol,
                    SKEWNESS(minute_log_return) AS intraday_skew,
                    SUM(trade_count) AS trade_count,
                    SUM(volume) AS total_volume,
                    SUM(close * volume) AS dollar_volume,
                    SUM(vwap * volume) AS vwap_dollar_volume,
                    SUM(CASE WHEN et_time < TIME '{OPENING_WINDOW_END}' THEN volume ELSE 0 END)
                        AS opening_volume,
                    SUM(CASE WHEN et_time >= TIME '{CLOSING_WINDOW_START}' THEN volume ELSE 0 END)
                        AS closing_volume
                FROM ordered
                GROUP BY symbol, trade_date
            ),
            with_overnight AS (
                SELECT
                    *,
                    LAG(session_close) OVER (PARTITION BY symbol ORDER BY trade_date) AS prev_close
                FROM daily
            )
            SELECT
                symbol,
                trade_date,
                (session_open / NULLIF(prev_close, 0) - 1.0) AS overnight_return,
                (session_close / NULLIF(session_open, 0) - 1.0) AS intraday_return,
                intraday_realized_vol,
                ((session_high - session_low) / NULLIF(session_open, 0)) AS intraday_amplitude,
                (opening_volume / NULLIF(total_volume, 0)) AS open_30min_volume_share,
                (closing_volume / NULLIF(total_volume, 0)) AS close_30min_volume_share,
                (session_close / NULLIF(vwap_dollar_volume / NULLIF(total_volume, 0), 0) - 1.0)
                    AS vwap_deviation,
                intraday_skew,
                trade_count,
                (ABS(session_close / NULLIF(session_open, 0) - 1.0) / NULLIF(dollar_volume, 0))
                    AS amihud_intraday
            FROM with_overnight
            ORDER BY symbol, trade_date
        """
        frame = connection.execute(query).fetchdf()
    finally:
        if owns_connection:
            connection.close()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame[list(INTRADAY_DAILY_COLUMNS)]
