"""Tests for open_composer.research.bars.hourly.resample_regular_session_hourly.

Plan: docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md
section 2 (A3). Fixtures build minute bars with explicit, hand-computed UTC
timestamps (never via tz_localize/tz_convert on a local-time range) so the
DST-boundary tests are an independent check of the function's timezone
handling, not a comparison of pandas' tz machinery against itself.

Known fixed offsets used below (US Eastern, 2024 DST calendar: spring-forward
2024-03-10, fall-back 2024-11-03):
  2024-01-02 (winter)                 EST, UTC = ET + 5h
  2024-03-08 (before spring-forward)  EST, UTC = ET + 5h
  2024-03-11 (after spring-forward)   EDT, UTC = ET + 4h
  2024-11-01 (before fall-back)       EDT, UTC = ET + 4h
  2024-11-04 (after fall-back)        EST, UTC = ET + 5h
"""

from __future__ import annotations

import pandas as pd
import pytest

from open_composer.research.bars.hourly import (
    OUTPUT_COLUMNS,
    resample_regular_session_hourly,
)


def _minute_bars(
    symbol: str,
    date: str,
    utc_start_hour: int,
    utc_start_minute: int,
    n_minutes: int,
    *,
    start_price: float = 100.0,
    volume: float = 100.0,
    trade_count: float = 5.0,
) -> pd.DataFrame:
    """``n_minutes`` consecutive 1-minute bars starting at the given UTC
    hour:minute on ``date``, deterministic prices so aggregates are hand-
    predictable: open[i]=price+i*0.01, high=open+0.05, low=open-0.05,
    close=open+0.02, constant volume/trade_count, vwap=open+0.01.
    """
    start = pd.Timestamp(date, tz="UTC") + pd.Timedelta(
        hours=utc_start_hour, minutes=utc_start_minute
    )
    timestamps = [start + pd.Timedelta(minutes=i) for i in range(n_minutes)]
    opens = [start_price + i * 0.01 for i in range(n_minutes)]
    return pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": timestamps,
            "open": opens,
            "high": [o + 0.05 for o in opens],
            "low": [o - 0.05 for o in opens],
            "close": [o + 0.02 for o in opens],
            "volume": volume,
            "trade_count": trade_count,
            "vwap": [o + 0.01 for o in opens],
        }
    )


def test_full_regular_session_produces_seven_buckets_with_correct_utc_boundaries() -> None:
    # 2024-01-02 is EST (UTC = ET+5): 09:30 ET = 14:30 UTC, session is 390
    # minutes (14:30..20:59 UTC), i.e. exactly the regular session.
    bars = _minute_bars("AAA", "2024-01-02", 14, 30, 390)
    result = resample_regular_session_hourly(bars)

    assert list(result.columns) == list(OUTPUT_COLUMNS)
    assert len(result) == 7
    expected_starts = [
        pd.Timestamp("2024-01-02 14:30", tz="UTC"),
        pd.Timestamp("2024-01-02 15:30", tz="UTC"),
        pd.Timestamp("2024-01-02 16:30", tz="UTC"),
        pd.Timestamp("2024-01-02 17:30", tz="UTC"),
        pd.Timestamp("2024-01-02 18:30", tz="UTC"),
        pd.Timestamp("2024-01-02 19:30", tz="UTC"),
        pd.Timestamp("2024-01-02 20:30", tz="UTC"),  # trailing half-hour bucket
    ]
    assert list(result["timestamp"]) == expected_starts
    # First six buckets are full hours (60 minute bars each), the last is the
    # 30-minute 15:30-16:00 ET bucket.
    assert list(result["minute_bar_count"]) == [60, 60, 60, 60, 60, 60, 30]

    first = result.iloc[0]
    # open = first minute's open (100.0), close = 60th minute's close
    # (open[59] + 0.02 = 100.59 + 0.02).
    assert first["open"] == pytest.approx(100.0)
    assert first["close"] == pytest.approx(100.59 + 0.02)
    assert first["high"] == pytest.approx(100.59 + 0.05)
    assert first["low"] == pytest.approx(100.0 - 0.05)
    assert first["volume"] == pytest.approx(60 * 100.0)
    assert first["trade_count"] == pytest.approx(60 * 5.0)

    last = result.iloc[-1]
    assert last["minute_bar_count"] == 30


def test_premarket_and_postmarket_minutes_are_excluded() -> None:
    # Premarket: 2024-01-02 09:00-10:29 UTC (= 04:00-05:29 ET).
    premarket = _minute_bars("AAA", "2024-01-02", 9, 0, 90, start_price=50.0)
    # Regular session, one full bucket (09:30-10:30 ET = 14:30-15:30 UTC).
    regular = _minute_bars("AAA", "2024-01-02", 14, 30, 60, start_price=100.0)
    # Postmarket: starting exactly at 16:00 ET (= 21:00 UTC) must be excluded
    # (the session filter is a half-open [09:30, 16:00) interval).
    postmarket = _minute_bars("AAA", "2024-01-02", 21, 0, 60, start_price=200.0)

    bars = pd.concat([premarket, regular, postmarket], ignore_index=True)
    result = resample_regular_session_hourly(bars)

    assert len(result) == 1
    assert result.iloc[0]["timestamp"] == pd.Timestamp("2024-01-02 14:30", tz="UTC")
    assert result.iloc[0]["open"] == pytest.approx(100.0)


def test_half_day_produces_only_the_buckets_that_have_data() -> None:
    # Only 09:30-13:00 ET present (14:30-18:00 UTC, 210 minutes) -- an early
    # close, or simply a data gap. No bucket should be fabricated beyond it.
    bars = _minute_bars("AAA", "2024-01-02", 14, 30, 210)
    result = resample_regular_session_hourly(bars)
    assert len(result) == 4
    assert list(result["minute_bar_count"]) == [60, 60, 60, 30]


def test_unsorted_input_still_resolves_open_and_close_chronologically() -> None:
    bars = _minute_bars("AAA", "2024-01-02", 14, 30, 60)
    shuffled = bars.sample(frac=1.0, random_state=3).reset_index(drop=True)
    result = resample_regular_session_hourly(shuffled)
    assert len(result) == 1
    # open must be minute 0's open (100.0), not whatever row happened to be
    # first after shuffling.
    assert result.iloc[0]["open"] == pytest.approx(100.0)
    assert result.iloc[0]["close"] == pytest.approx(100.59 + 0.02)


def test_multiple_symbols_are_independent() -> None:
    a = _minute_bars("AAA", "2024-01-02", 14, 30, 60, start_price=100.0)
    b = _minute_bars("BBB", "2024-01-02", 14, 30, 60, start_price=9000.0)
    combined = pd.concat([a, b], ignore_index=True)
    result = resample_regular_session_hourly(combined)
    assert len(result) == 2
    by_symbol = result.set_index("symbol")
    assert by_symbol.loc["AAA", "open"] == pytest.approx(100.0)
    assert by_symbol.loc["BBB", "open"] == pytest.approx(9000.0)


def test_dst_spring_forward_shifts_the_utc_bucket_boundary() -> None:
    # Before spring-forward (2024-03-08, EST, UTC=ET+5): 09:30 ET = 14:30 UTC.
    before = _minute_bars("AAA", "2024-03-08", 14, 30, 60)
    result_before = resample_regular_session_hourly(before)
    assert result_before.iloc[0]["timestamp"] == pd.Timestamp("2024-03-08 14:30", tz="UTC")

    # After spring-forward (2024-03-11, EDT, UTC=ET+4): 09:30 ET = 13:30 UTC.
    after = _minute_bars("AAA", "2024-03-11", 13, 30, 60)
    result_after = resample_regular_session_hourly(after)
    assert result_after.iloc[0]["timestamp"] == pd.Timestamp("2024-03-11 13:30", tz="UTC")


def test_dst_fall_back_shifts_the_utc_bucket_boundary() -> None:
    # Before fall-back (2024-11-01, EDT, UTC=ET+4): 09:30 ET = 13:30 UTC.
    before = _minute_bars("AAA", "2024-11-01", 13, 30, 60)
    result_before = resample_regular_session_hourly(before)
    assert result_before.iloc[0]["timestamp"] == pd.Timestamp("2024-11-01 13:30", tz="UTC")

    # After fall-back (2024-11-04, EST, UTC=ET+5): 09:30 ET = 14:30 UTC.
    after = _minute_bars("AAA", "2024-11-04", 14, 30, 60)
    result_after = resample_regular_session_hourly(after)
    assert result_after.iloc[0]["timestamp"] == pd.Timestamp("2024-11-04 14:30", tz="UTC")


def test_naive_timestamps_are_assumed_utc() -> None:
    bars = _minute_bars("AAA", "2024-01-02", 14, 30, 60)
    bars["timestamp"] = bars["timestamp"].dt.tz_localize(None)
    result = resample_regular_session_hourly(bars)
    assert len(result) == 1
    assert result.iloc[0]["timestamp"] == pd.Timestamp("2024-01-02 14:30", tz="UTC")


def test_vwap_is_volume_weighted_and_nan_when_bucket_volume_is_zero() -> None:
    bars = _minute_bars("AAA", "2024-01-02", 14, 30, 2, volume=0.0)
    # both minutes have volume 0 -> sum(volume*vwap)/sum(volume) is 0/0
    result = resample_regular_session_hourly(bars)
    assert len(result) == 1
    assert pd.isna(result.iloc[0]["vwap"])

    weighted = pd.DataFrame(
        {
            "symbol": "AAA",
            "timestamp": [
                pd.Timestamp("2024-01-02 14:30", tz="UTC"),
                pd.Timestamp("2024-01-02 14:31", tz="UTC"),
            ],
            "open": [100.0, 110.0],
            "high": [100.0, 110.0],
            "low": [100.0, 110.0],
            "close": [100.0, 110.0],
            "volume": [10.0, 30.0],
            "trade_count": [1.0, 1.0],
            "vwap": [100.0, 110.0],
        }
    )
    result2 = resample_regular_session_hourly(weighted)
    expected_vwap = (10.0 * 100.0 + 30.0 * 110.0) / (10.0 + 30.0)
    assert result2.iloc[0]["vwap"] == pytest.approx(expected_vwap)


def test_missing_required_column_raises() -> None:
    bars = _minute_bars("AAA", "2024-01-02", 14, 30, 5).drop(columns=["vwap"])
    with pytest.raises(ValueError, match="missing required columns"):
        resample_regular_session_hourly(bars)


def test_empty_input_returns_empty_frame_with_output_columns() -> None:
    bars = _minute_bars("AAA", "2024-01-02", 14, 30, 5).iloc[0:0]
    result = resample_regular_session_hourly(bars)
    assert result.empty
    assert list(result.columns) == list(OUTPUT_COLUMNS)


def test_all_rows_outside_session_returns_empty_frame() -> None:
    bars = _minute_bars("AAA", "2024-01-02", 9, 0, 30)  # 04:00-04:29 ET, premarket
    result = resample_regular_session_hourly(bars)
    assert result.empty
    assert list(result.columns) == list(OUTPUT_COLUMNS)
