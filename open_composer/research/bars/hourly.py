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
    """
    missing = [column for column in REQUIRED_COLUMNS if column not in minute_bars.columns]
    if missing:
        raise ValueError(f"minute_bars is missing required columns: {missing}")
    if minute_bars.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    timestamp = minute_bars["timestamp"]
    if timestamp.dt.tz is None:
        timestamp = timestamp.dt.tz_localize("UTC")
    local_ts = timestamp.dt.tz_convert(SESSION_TZ)
    minute_of_day = local_ts.dt.hour * 60 + local_ts.dt.minute

    in_session = (minute_of_day >= SESSION_OPEN_MINUTE) & (minute_of_day < SESSION_CLOSE_MINUTE)
    if not in_session.any():
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    frame = minute_bars.loc[in_session].copy()
    local_ts = local_ts.loc[in_session]
    minute_of_day = minute_of_day.loc[in_session]

    frame["_session_date"] = local_ts.dt.tz_localize(None).dt.normalize()
    bucket_index = (minute_of_day - SESSION_OPEN_MINUTE) // BUCKET_MINUTES
    frame["_bucket_index"] = np.minimum(bucket_index, BUCKET_COUNT - 1).astype(np.int64)
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

    bucket_offset_minutes = SESSION_OPEN_MINUTE + BUCKET_MINUTES * grouped["_bucket_index"]
    local_bucket_start = grouped["_session_date"] + pd.to_timedelta(bucket_offset_minutes, unit="m")
    grouped["timestamp"] = local_bucket_start.dt.tz_localize(SESSION_TZ).dt.tz_convert("UTC")

    grouped = grouped.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
    return grouped[list(OUTPUT_COLUMNS)]
