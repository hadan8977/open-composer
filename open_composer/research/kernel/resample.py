"""RTH-only, volume-weighted intraday resampling for the SIP minute archive.

Addresses pitfall items 9-14 in ``docs/data-layer-pitfalls-and-capabilities.zh.md``:
extended-hours contamination, arithmetic-mean VWAP, hour-bar misalignment with the
09:30 session open, missing-minute coverage that is invisible in the schema, half
days, and (by construction -- this module only ever accepts minute input) never
synthesizing a daily bar from intraday data.

Bar bucketing is done by elapsed minutes since that session's 09:30 open rather
than a pandas ``resample`` origin, since the latter is fragile across the DST
transitions minute data spans (spring/fall clock changes mid-archive); computing
each timestamp's New York local time-of-day per row is DST-safe because the
timezone conversion happens per timestamp, not per fixed UTC offset.

Coverage classification (which sessions are "quality", which bars are missing,
duplicate, or off-grid) reuses ``open_composer.market_calendar.
validate_us_equity_bar_grid`` rather than re-deriving it -- that function already
handles half days, boundary-session dropping, and off-session/off-grid detection.
"""

from __future__ import annotations

from datetime import time, timedelta
from typing import Any

import pandas as pd

from open_composer.market_calendar import (
    NEW_YORK,
    us_equity_session_close,
    validate_us_equity_bar_grid,
)

#: Only intraday targets. Synthesizing a daily bar from minute data drops the
#: opening/closing auction prints that a real daily bar carries (pitfall #14);
#: daily bars must come from the SIP daily archive, never from this function.
SUPPORTED_TARGET_MINUTES = (5, 15, 30, 60)

#: A bucket with fewer than this fraction of its expected 1-minute bars is not
#: usable -- schema alone cannot distinguish "quiet session" from "gap", so a
#: coverage floor is the only defense (pitfall #12).
DEFAULT_MIN_BAR_COVERAGE = 0.8


class ResampleError(RuntimeError):
    """Raised when minute bars cannot be safely resampled to the target frequency."""


def _minutes_since_open(timestamp: pd.Timestamp) -> int | None:
    """Minutes elapsed since that session's 09:30 open, or None outside RTH."""
    local = timestamp.tz_convert(NEW_YORK)
    close = us_equity_session_close(local.date())
    if close is None:
        return None
    local_time = local.time().replace(tzinfo=None)
    if not (time(9, 30) <= local_time < close):
        return None
    open_minutes = 9 * 60 + 30
    local_minutes = local_time.hour * 60 + local_time.minute
    return local_minutes - open_minutes


def resample_rth_bars(
    frame: pd.DataFrame,
    *,
    target_minutes: int,
    min_bar_coverage: float = DEFAULT_MIN_BAR_COVERAGE,
) -> pd.DataFrame:
    """Resample RTH-filtered 1-minute SIP bars to ``target_minutes``-minute bars.

    ``frame`` must be single-symbol minute bars with columns
    ``timestamp, open, high, low, close, volume`` (``vwap``/``trade_count``
    optional, from ``open_composer.adapters.data.sip_parquet.load_sip_bars``).
    Extended-hours rows are dropped before bucketing, not averaged in.

    Returns a frame with columns ``timestamp, open, high, low, close, volume,
    vwap, bar_count, expected_bar_count, coverage_ratio`` where ``timestamp`` is
    the bucket's start (matching ``market_calendar.expected_us_equity_rth_bar_
    starts``'s start-labelled convention), sorted ascending. Buckets below
    ``min_bar_coverage`` are dropped, not filled forward -- a partially-covered
    bucket cannot be told apart from a fully-covered one once it is silently
    kept, which is exactly the schema-invisibility problem this module exists
    to avoid. ``frame.attrs["resample_quality"]`` carries the full
    ``validate_us_equity_bar_grid`` report on the RTH-filtered *input* minute
    timestamps, for a coverage audit independent of the target frequency.
    """
    if target_minutes not in SUPPORTED_TARGET_MINUTES:
        raise ResampleError(
            f"target_minutes must be one of {SUPPORTED_TARGET_MINUTES}; got {target_minutes} "
            "(daily bars must come from the SIP daily archive, never from minute resampling)"
        )
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ResampleError(f"input frame is missing columns: {sorted(missing)}")

    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    working = working.sort_values("timestamp").drop_duplicates(subset="timestamp")
    if "vwap" not in working.columns:
        working["vwap"] = working["close"]

    elapsed = working["timestamp"].map(_minutes_since_open)
    rth = working.loc[elapsed.notna()].copy()
    rth["elapsed_minutes"] = elapsed.loc[elapsed.notna()].astype(int)
    if rth.empty:
        raise ResampleError("no rows fall inside regular trading hours")

    quality_report = validate_us_equity_bar_grid(rth["timestamp"], timeframe_minutes=1)

    rth["session_date"] = rth["timestamp"].dt.tz_convert(NEW_YORK).dt.date
    rth["bucket_index"] = rth["elapsed_minutes"] // target_minutes
    rth["dollar_volume"] = rth["vwap"] * rth["volume"]

    rows: list[dict[str, Any]] = []
    for (session_date, bucket_index), group in rth.groupby(
        ["session_date", "bucket_index"], sort=True
    ):
        group = group.sort_values("timestamp")
        bucket_start_minutes = int(bucket_index) * target_minutes
        bucket_start_local = pd.Timestamp.combine(session_date, time(9, 30)) + timedelta(
            minutes=bucket_start_minutes
        )
        bucket_start = pd.Timestamp(bucket_start_local, tz=NEW_YORK).tz_convert("UTC")

        close_time = us_equity_session_close(session_date)
        session_close_minutes = close_time.hour * 60 + close_time.minute - (9 * 60 + 30)
        expected_bar_count = min(target_minutes, session_close_minutes - bucket_start_minutes)
        actual_bar_count = len(group)
        coverage_ratio = actual_bar_count / expected_bar_count if expected_bar_count > 0 else 0.0
        if coverage_ratio < min_bar_coverage:
            continue

        total_volume = float(group["volume"].sum())
        vwap = (
            float(group["dollar_volume"].sum()) / total_volume
            if total_volume > 0
            else float(group["vwap"].mean())
        )
        row = {
            "timestamp": bucket_start,
            "open": float(group["open"].iloc[0]),
            "high": float(group["high"].max()),
            "low": float(group["low"].min()),
            "close": float(group["close"].iloc[-1]),
            "volume": total_volume,
            "vwap": vwap,
            "bar_count": actual_bar_count,
            "expected_bar_count": expected_bar_count,
            "coverage_ratio": round(coverage_ratio, 6),
        }
        if "trade_count" in group.columns:
            row["trade_count"] = float(group["trade_count"].sum())
        rows.append(row)

    if not rows:
        raise ResampleError(
            f"no bucket met the {min_bar_coverage:.0%} coverage floor at "
            f"target_minutes={target_minutes}"
        )
    result = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    result.attrs["resample_quality"] = quality_report
    result.attrs["target_minutes"] = target_minutes
    result.attrs["min_bar_coverage"] = min_bar_coverage
    return result
