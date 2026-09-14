"""Regular-session 1h bars anchored at 09:30 America/New_York.

Plan: ``docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md``
section 2 (A3): "1 小时 bar = 常规时段 09:30-16:00 America/New_York，按 09:30
锚定（09:30, 10:30, …, 14:30, 15:30-16:00 为 30 分钟 bar）". The regular US
equity session is 09:30-16:00 local; anchoring the first bucket at 09:30 and
stepping every 60 minutes gives six full-hour buckets (09:30, 10:30, 11:30,
12:30, 13:30, 14:30) plus a final 30-minute bucket (15:30-16:00), since
09:30 + 6.5h = 16:00 is not a multiple of 60 minutes past 09:30. Pre/post
market minute bars (anything outside [09:30, 16:00) local) are dropped, never
folded into the first/last bucket.

This module is the pure, DuckDB-free aggregation core (input: an already-
fetched minute-bars DataFrame in memory) so it is unit-testable on small
synthetic frames without touching the parquet archive or a DuckDB connection.
``scripts/build_hourly_bars.py`` owns the DuckDB-based, memory-capped reads
from ``data/sip/minute/`` and calls this function per (year, month) chunk.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
)

OUTPUT_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
    "minute_bar_count",
)

SESSION_TZ = "America/New_York"
SESSION_OPEN_MINUTE = 9 * 60 + 30  # 09:30
SESSION_CLOSE_MINUTE = 16 * 60  # 16:00 (exclusive)
BUCKET_MINUTES = 60
BUCKET_COUNT = 7  # 6 full hours + the trailing 15:30-16:00 half hour
SESSION_LENGTH_MINUTES = SESSION_CLOSE_MINUTE - SESSION_OPEN_MINUTE  # 390

#: Step 14 (``docs/plan-step-14-timeframe-agnostic-bar-cycle-runner-2026-09-11.zh.md``
#: section 1, ``ArchiveBarSource``): bucket length in minutes for every
#: intraday ``StrategyTimeframe`` this module aggregates to. ``daily``/
#: ``weekly`` are deliberately absent -- daily bars come from the SIP daily
#: archive directly (no minute aggregation needed) and weekly has no
#: session-anchoring requirement yet (out of scope for this generalization,
#: see ``open_composer.execution.bar_source``). ``1m`` is included for
#: uniformity (a session-filtered identity aggregation that just drops
#: pre/post-market minutes) even though the source is already 1-minute bars
#: -- this is what lets every intraday timeframe share one code path.
TIMEFRAME_BUCKET_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
}

#: :data:`OUTPUT_COLUMNS` plus ``bar_close_ts`` (the bucket's *close* in
#: UTC), :func:`aggregate_regular_session`'s own return schema.
#: :func:`resample_regular_session_hourly` drops the extra column before
#: returning, so its own :data:`OUTPUT_COLUMNS` contract is unchanged.
AGGREGATE_OUTPUT_COLUMNS = (*OUTPUT_COLUMNS, "bar_close_ts")


def _bucket_count(bucket_minutes: int) -> int:
    """Ceil-division bucket count for one session (390 minutes) split into
    ``bucket_minutes``-long buckets -- the session's last bucket is whatever
    is left over (0 when ``bucket_minutes`` divides 390 evenly: 1/5/15/30;
    30 min for 60; 150 min for 240), never a partial bucket dropped or a
    fabricated extra one.
    """
    return -(-SESSION_LENGTH_MINUTES // bucket_minutes)


def resample_regular_session_hourly(minute_bars: pd.DataFrame) -> pd.DataFrame:
    """Aggregate minute bars into 09:30-anchored regular-session 1h buckets.

    Parameters
    ----------
    minute_bars:
        Columns :data:`REQUIRED_COLUMNS` (the SIP minute-shard schema).
        ``timestamp`` must be UTC (naive timestamps are assumed already UTC
        and localized as such); row order does not matter, this function
        sorts internally.

    Returns
    -------
    One row per (symbol, session date, hourly bucket) that had at least one
    contributing minute bar, columns :data:`OUTPUT_COLUMNS`, sorted by
    ``(symbol, timestamp)``. ``timestamp`` is the bucket's *start*, in UTC.
    ``open``/``close`` come from the chronologically first/last minute bar in
    the bucket; ``high``/``low`` are the bucket max/min; ``volume``/
    ``trade_count`` are summed; ``vwap`` is the volume-weighted average of the
    per-minute vwaps (``sum(volume*vwap)/sum(volume)``, NaN if the bucket's
    total volume is zero). ``minute_bar_count`` is a data-quality diagnostic
    (a full first-six-buckets hour has 60, the trailing bucket has 30; a
    lower count flags a trading halt, a thin/illiquid symbol, or a half day).
    Buckets with no minute bars at all are simply absent, never fabricated.

    Step 14: a thin wrapper over :func:`aggregate_regular_session` with
    ``timeframe="1h"``, kept as its own function so every existing caller
    (``scripts/build_hourly_bars.py`` and this module's own prior callers)
    keeps an unchanged import path and an unchanged output schema (no
    ``bar_close_ts`` column) -- see that function for the generalization and
    ``tests/test_hourly_bars.py`` for the bar-for-bar equivalence proof.
    """
    aggregated = aggregate_regular_session(minute_bars, "1h")
    if aggregated.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return aggregated.loc[:, list(OUTPUT_COLUMNS)]


def aggregate_regular_session(minute_bars: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Generalization of :func:`resample_regular_session_hourly` to any
    intraday timeframe in :data:`TIMEFRAME_BUCKET_MINUTES` (Step 14 plan
    section 1, ``ArchiveBarSource``: "分钟聚合到 5m/15m/30m/1h/4h 时复用
    ...hourly.py 的 09:30 ET 锚定与 DST 处理"). Bucket ``i`` spans local
    minutes ``[09:30 + i*B, min(09:30 + (i+1)*B, 16:00))`` for bucket length
    ``B`` -- every bucket is exactly ``B`` minutes except the session's own
    last one, which is whatever is left before 16:00 (see
    :func:`_bucket_count`). For ``timeframe="1h"`` this is *exactly* the
    original 6x60min + 1x30min scheme (``resample_regular_session_hourly``
    now calls this function with ``timeframe="1h"`` and is bar-for-bar
    identical to its pre-Step-14 self).

    DST handling is unchanged from the original 1h-only implementation: each
    minute bar's own UTC ``timestamp`` is converted to ``America/New_York``
    independently (``Series.dt.tz_convert``), so a bar's local minute-of-day
    -- and therefore its bucket -- is always correct across a spring-forward
    or fall-back transition without any special-cased date logic. Bucket
    start/close boundaries (09:30-16:00 local) never coincide with a DST
    transition instant (those happen at 02:00 local), so localizing a
    bucket's naive local start/close via ``tz_localize(SESSION_TZ)`` is never
    ambiguous or nonexistent.

    Parameters
    ----------
    minute_bars:
        Same contract as :func:`resample_regular_session_hourly` (columns
        :data:`REQUIRED_COLUMNS`, UTC timestamps, any row order).
    timeframe:
        One of :data:`TIMEFRAME_BUCKET_MINUTES`'s keys; anything else raises
        ``ValueError``.

    Returns
    -------
    One row per (symbol, session date, bucket) with at least one
    contributing minute bar, columns :data:`AGGREGATE_OUTPUT_COLUMNS`
    (:data:`OUTPUT_COLUMNS` plus ``bar_close_ts``, the bucket's *close* in
    UTC), sorted by ``(symbol, timestamp)``. Every OHLCV/``vwap``/
    ``minute_bar_count`` aggregation rule is identical to
    :func:`resample_regular_session_hourly`'s. ``timestamp`` remains the
    bucket's *start* -- do not confuse it with ``bar_close_ts``, added for
    ``open_composer.execution.bar_source.BarSource``'s point-in-time
    contract (a bar is never available before its own close).
    """
    if timeframe not in TIMEFRAME_BUCKET_MINUTES:
        supported = ", ".join(sorted(TIMEFRAME_BUCKET_MINUTES))
        raise ValueError(
            f"aggregate_regular_session: unsupported timeframe {timeframe!r}; "
            f"supported: {supported}"
        )
    bucket_minutes = TIMEFRAME_BUCKET_MINUTES[timeframe]
    bucket_count = _bucket_count(bucket_minutes)

    missing = [column for column in REQUIRED_COLUMNS if column not in minute_bars.columns]
    if missing:
        raise ValueError(f"minute_bars is missing required columns: {missing}")
    if minute_bars.empty:
        return pd.DataFrame(columns=AGGREGATE_OUTPUT_COLUMNS)

    timestamp = minute_bars["timestamp"]
    if timestamp.dt.tz is None:
        timestamp = timestamp.dt.tz_localize("UTC")
    local_ts = timestamp.dt.tz_convert(SESSION_TZ)
    minute_of_day = local_ts.dt.hour * 60 + local_ts.dt.minute

    in_session = (minute_of_day >= SESSION_OPEN_MINUTE) & (minute_of_day < SESSION_CLOSE_MINUTE)
    if not in_session.any():
        return pd.DataFrame(columns=AGGREGATE_OUTPUT_COLUMNS)

    frame = minute_bars.loc[in_session].copy()
    local_ts = local_ts.loc[in_session]
    minute_of_day = minute_of_day.loc[in_session]

    frame["_session_date"] = local_ts.dt.tz_localize(None).dt.normalize()
    bucket_index = (minute_of_day - SESSION_OPEN_MINUTE) // bucket_minutes
    frame["_bucket_index"] = np.minimum(bucket_index, bucket_count - 1).astype(np.int64)
    frame["_dollar_volume"] = frame["volume"] * frame["vwap"]

    frame = frame.sort_values(["symbol", "timestamp"], kind="mergesort")
    grouped = frame.groupby(["symbol", "_session_date", "_bucket_index"], sort=False).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        trade_count=("trade_count", "sum"),
        _dollar_volume=("_dollar_volume", "sum"),
        minute_bar_count=("close", "size"),
    )
    grouped = grouped.reset_index()

    volume_denominator = grouped["volume"].where(grouped["volume"] != 0)
    grouped["vwap"] = grouped["_dollar_volume"] / volume_denominator

    bucket_start_offset = SESSION_OPEN_MINUTE + bucket_minutes * grouped["_bucket_index"]
    bucket_close_offset = np.minimum(bucket_start_offset + bucket_minutes, SESSION_CLOSE_MINUTE)
    local_bucket_start = grouped["_session_date"] + pd.to_timedelta(bucket_start_offset, unit="m")
    local_bucket_close = grouped["_session_date"] + pd.to_timedelta(bucket_close_offset, unit="m")
    grouped["timestamp"] = local_bucket_start.dt.tz_localize(SESSION_TZ).dt.tz_convert("UTC")
    grouped["bar_close_ts"] = local_bucket_close.dt.tz_localize(SESSION_TZ).dt.tz_convert("UTC")

    grouped = grouped.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
    return grouped[list(AGGREGATE_OUTPUT_COLUMNS)]
