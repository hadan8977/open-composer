from __future__ import annotations

import pandas as pd
import pytest

from open_composer.research.kernel.resample import (
    DEFAULT_MIN_BAR_COVERAGE,
    ResampleError,
    resample_rth_bars,
)


def _minute_bars(
    timestamps: pd.DatetimeIndex, *, base: float = 100.0, volume: float = 1000.0
) -> pd.DataFrame:
    count = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [base + index * 0.01 for index in range(count)],
            "high": [base + index * 0.01 + 0.05 for index in range(count)],
            "low": [base + index * 0.01 - 0.05 for index in range(count)],
            "close": [base + index * 0.01 + 0.02 for index in range(count)],
            "volume": [volume + index for index in range(count)],
            "vwap": [base + index * 0.01 + 0.01 for index in range(count)],
        }
    )


def test_rejects_a_daily_target() -> None:
    timestamps = pd.date_range("2026-08-24 13:30", periods=390, freq="1min", tz="UTC")
    frame = _minute_bars(timestamps)
    with pytest.raises(ResampleError, match="daily"):
        resample_rth_bars(frame, target_minutes=1440)


def test_extended_hours_rows_are_dropped_not_averaged_in() -> None:
    # 2026-08-24 is a Monday RTH session (13:30-20:00 UTC = 09:30-16:00 ET, EDT).
    premarket = pd.date_range("2026-08-24 08:00", periods=30, freq="1min", tz="UTC")
    rth = pd.date_range("2026-08-24 13:30", periods=390, freq="1min", tz="UTC")
    postmarket = pd.date_range("2026-08-24 20:00", periods=30, freq="1min", tz="UTC")
    frame = pd.concat(
        [
            _minute_bars(premarket, base=1.0),  # wildly different level
            _minute_bars(rth, base=100.0),
            _minute_bars(postmarket, base=9999.0),  # wildly different level
        ],
        ignore_index=True,
    )
    out = resample_rth_bars(frame, target_minutes=30)
    assert out["timestamp"].min() == pd.Timestamp("2026-08-24 13:30", tz="UTC")
    assert out["timestamp"].max() == pd.Timestamp("2026-08-24 19:30", tz="UTC")
    assert len(out) == 13  # 6.5 RTH hours / 30 minutes
    assert (out["open"] < 200).all()  # premarket/postmarket levels never leak in


def test_bars_are_anchored_at_the_930_open_not_clock_hours() -> None:
    timestamps = pd.date_range("2026-08-24 13:30", periods=390, freq="1min", tz="UTC")
    frame = _minute_bars(timestamps)
    hourly = resample_rth_bars(frame, target_minutes=60)
    # 09:30 ET anchor -> bucket starts at :30 past the hour, not on the hour.
    assert all(ts.tz_convert("America/New_York").minute == 30 for ts in hourly["timestamp"])


def test_vwap_is_volume_weighted_not_arithmetic_mean() -> None:
    timestamps = pd.date_range("2026-08-24 13:30", periods=5, freq="1min", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * 5,
            "high": [100.0] * 5,
            "low": [100.0] * 5,
            "close": [100.0] * 5,
            # One massive-volume bar at a very different price should dominate VWAP
            # but would be invisible to a naive arithmetic mean of vwap values.
            "volume": [10.0, 10.0, 1_000_000.0, 10.0, 10.0],
            "vwap": [100.0, 100.0, 200.0, 100.0, 100.0],
        }
    )
    out = resample_rth_bars(frame, target_minutes=5)
    arithmetic_mean = frame["vwap"].mean()
    assert out.iloc[0]["vwap"] > arithmetic_mean + 50  # pulled hard toward 200
    manual_vwap = (frame["vwap"] * frame["volume"]).sum() / frame["volume"].sum()
    assert out.iloc[0]["vwap"] == pytest.approx(manual_vwap)


def test_half_day_session_truncates_at_early_close() -> None:
    # 2026-11-27 is the day after Thanksgiving: an early close at 13:00 ET.
    # November is standard time (EST, UTC-5), so 09:30 ET = 14:30 UTC -- unlike
    # the other fixtures in this file, which fall in daylight time (EDT, UTC-4).
    timestamps = pd.date_range("2026-11-27 14:30", periods=210, freq="1min", tz="UTC")
    frame = _minute_bars(timestamps)
    out = resample_rth_bars(frame, target_minutes=30)
    # 09:30-13:00 ET is 3.5 hours = 7 bars of 30 minutes, not 13.
    assert len(out) == 7
    # Start-labelled: the last bucket start is 12:30 ET (17:30 UTC), not the
    # 13:00 ET close itself.
    assert out["timestamp"].max() == pd.Timestamp("2026-11-27 17:30", tz="UTC")


def test_low_coverage_buckets_are_dropped_not_filled_forward() -> None:
    timestamps = pd.date_range("2026-08-24 13:30", periods=390, freq="1min", tz="UTC")
    frame = _minute_bars(timestamps)
    # Gut the third 5-minute bucket (13:40-13:45) down to one bar out of five.
    gutted = frame.drop(frame.index[11:15])
    out = resample_rth_bars(gutted, target_minutes=5, min_bar_coverage=DEFAULT_MIN_BAR_COVERAGE)
    assert pd.Timestamp("2026-08-24 13:40", tz="UTC") not in set(out["timestamp"])
    assert out["coverage_ratio"].min() >= DEFAULT_MIN_BAR_COVERAGE


def test_full_coverage_buckets_report_ratio_one() -> None:
    timestamps = pd.date_range("2026-08-24 13:30", periods=390, freq="1min", tz="UTC")
    frame = _minute_bars(timestamps)
    out = resample_rth_bars(frame, target_minutes=15)
    assert (out["coverage_ratio"] == 1.0).all()
    assert (out["bar_count"] == out["expected_bar_count"]).all()


def test_quality_report_is_attached_and_reflects_input_gaps() -> None:
    timestamps = pd.date_range("2026-08-24 13:30", periods=390, freq="1min", tz="UTC")
    frame = _minute_bars(timestamps).drop(index=200).reset_index(drop=True)
    out = resample_rth_bars(frame, target_minutes=30)
    quality = out.attrs["resample_quality"]
    assert quality["missing_interior_bar_count"] == 1


def test_missing_required_column_raises() -> None:
    timestamps = pd.date_range("2026-08-24 13:30", periods=5, freq="1min", tz="UTC")
    frame = _minute_bars(timestamps).drop(columns=["volume"])
    with pytest.raises(ResampleError, match="volume"):
        resample_rth_bars(frame, target_minutes=5)


def test_no_rth_rows_raises() -> None:
    premarket = pd.date_range("2026-08-24 08:00", periods=30, freq="1min", tz="UTC")
    frame = _minute_bars(premarket)
    with pytest.raises(ResampleError, match="regular trading hours"):
        resample_rth_bars(frame, target_minutes=5)
