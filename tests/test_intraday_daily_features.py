"""Tests for open_composer.research.features.intraday_daily."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.features.intraday_daily import (
    INTRADAY_DAILY_COLUMNS,
    build_intraday_daily_features,
    minute_root_for_year,
    minute_shard_paths,
)

ET = "America/New_York"


def _et_bar(date: str, hhmm: str, **fields: float) -> dict[str, object]:
    ts = pd.Timestamp(f"{date} {hhmm}:00", tz=ET).tz_convert("UTC")
    return {"timestamp": ts, **fields}


def _write_shard(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


@pytest.fixture
def synthetic_minute_shard(tmp_path: Path) -> Path:
    rows: list[dict[str, object]] = []
    # AAA day 1 (2024-01-02, EST, no DST ambiguity): 5 regular-session bars +
    # 1 pre-market bar that must be excluded by the regular-session filter.
    day1 = [
        _et_bar(
            "2024-01-02",
            "08:00",
            symbol="AAA",
            open=999,
            high=999,
            low=999,
            close=999,
            volume=50,
            trade_count=1,
            vwap=999,
        ),
        _et_bar(
            "2024-01-02",
            "09:30",
            symbol="AAA",
            open=100,
            high=101,
            low=100,
            close=101,
            volume=1000,
            trade_count=10,
            vwap=100.5,
        ),
        _et_bar(
            "2024-01-02",
            "09:45",
            symbol="AAA",
            open=101,
            high=102,
            low=101,
            close=102,
            volume=2000,
            trade_count=20,
            vwap=101.5,
        ),
        _et_bar(
            "2024-01-02",
            "12:00",
            symbol="AAA",
            open=102,
            high=103,
            low=102,
            close=103,
            volume=500,
            trade_count=5,
            vwap=102.5,
        ),
        _et_bar(
            "2024-01-02",
            "15:45",
            symbol="AAA",
            open=103,
            high=105,
            low=103,
            close=105,
            volume=3000,
            trade_count=30,
            vwap=104.0,
        ),
        _et_bar(
            "2024-01-02",
            "15:59",
            symbol="AAA",
            open=105,
            high=105,
            low=104,
            close=104,
            volume=1000,
            trade_count=10,
            vwap=104.5,
        ),
    ]
    # AAA day 2: overnight return links to day 1's session close (104).
    day2 = [
        _et_bar(
            "2024-01-03",
            "09:30",
            symbol="AAA",
            open=106,
            high=107,
            low=106,
            close=107,
            volume=1000,
            trade_count=10,
            vwap=106.5,
        ),
        _et_bar(
            "2024-01-03",
            "15:59",
            symbol="AAA",
            open=107,
            high=108,
            low=107,
            close=108,
            volume=1000,
            trade_count=10,
            vwap=107.5,
        ),
    ]
    # BBB: single regular-session bar in one day -- realized vol/skew must be
    # NULL (not crash) with only one minute observation (no LAG partner).
    bbb = [
        _et_bar(
            "2024-01-02",
            "09:30",
            symbol="BBB",
            open=50,
            high=51,
            low=49,
            close=50,
            volume=200,
            trade_count=2,
            vwap=50.0,
        ),
    ]
    rows.extend(day1 + day2 + bbb)
    path = tmp_path / "shard-0000.parquet"
    _write_shard(path, rows)
    return path


def _row(frame: pd.DataFrame, symbol: str, date: str) -> pd.Series:
    match = frame.loc[(frame["symbol"] == symbol) & (frame["trade_date"] == pd.Timestamp(date))]
    assert len(match) == 1, f"expected exactly one row for {symbol}/{date}, got {len(match)}"
    return match.iloc[0]


def test_output_columns_and_row_count(synthetic_minute_shard: Path) -> None:
    frame = build_intraday_daily_features(
        [str(synthetic_minute_shard)], ["AAA", "BBB"], memory_limit="512MB"
    )
    assert list(frame.columns) == list(INTRADAY_DAILY_COLUMNS)
    # AAA has 2 trading days, BBB has 1 -- 3 rows total.
    assert len(frame) == 3


def test_premarket_bar_is_excluded_from_session_open_and_high(
    synthetic_minute_shard: Path,
) -> None:
    frame = build_intraday_daily_features([str(synthetic_minute_shard)], ["AAA", "BBB"])
    row = _row(frame, "AAA", "2024-01-02")
    # If the 08:00 pre-market bar (close=999) leaked in, intraday_return and
    # intraday_amplitude would be wildly different from these hand-computed
    # regular-session-only values.
    assert row["intraday_return"] == pytest.approx(104.0 / 100.0 - 1.0)
    assert row["intraday_amplitude"] == pytest.approx((105.0 - 100.0) / 100.0)


def test_volume_share_and_amihud_match_hand_computation(synthetic_minute_shard: Path) -> None:
    frame = build_intraday_daily_features([str(synthetic_minute_shard)], ["AAA", "BBB"])
    row = _row(frame, "AAA", "2024-01-02")

    total_volume = 1000 + 2000 + 500 + 3000 + 1000
    opening_volume = 1000 + 2000  # 09:30 and 09:45, both < 10:00
    closing_volume = 3000 + 1000  # 15:45 and 15:59, both >= 15:30
    assert row["open_30min_volume_share"] == pytest.approx(opening_volume / total_volume)
    assert row["close_30min_volume_share"] == pytest.approx(closing_volume / total_volume)
    assert row["trade_count"] == 10 + 20 + 5 + 30 + 10

    dollar_volume = 101 * 1000 + 102 * 2000 + 103 * 500 + 105 * 3000 + 104 * 1000
    expected_amihud = abs(104.0 / 100.0 - 1.0) / dollar_volume
    assert row["amihud_intraday"] == pytest.approx(expected_amihud)

    vwap_dollar_volume = 100.5 * 1000 + 101.5 * 2000 + 102.5 * 500 + 104.0 * 3000 + 104.5 * 1000
    day_vwap = vwap_dollar_volume / total_volume
    assert row["vwap_deviation"] == pytest.approx(104.0 / day_vwap - 1.0)


def test_realized_vol_matches_sample_stddev_of_one_minute_log_returns(
    synthetic_minute_shard: Path,
) -> None:
    frame = build_intraday_daily_features([str(synthetic_minute_shard)], ["AAA", "BBB"])
    row = _row(frame, "AAA", "2024-01-02")
    closes = [101, 102, 103, 105, 104]
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    expected_stddev = float(np.std(log_returns, ddof=1))
    assert row["intraday_realized_vol"] == pytest.approx(expected_stddev, rel=1e-9)
    assert math.isfinite(row["intraday_skew"])


def test_first_trading_day_has_null_overnight_return(synthetic_minute_shard: Path) -> None:
    frame = build_intraday_daily_features([str(synthetic_minute_shard)], ["AAA", "BBB"])
    row = _row(frame, "AAA", "2024-01-02")
    assert pd.isna(row["overnight_return"])


def test_second_trading_day_overnight_return_uses_prior_session_close(
    synthetic_minute_shard: Path,
) -> None:
    frame = build_intraday_daily_features([str(synthetic_minute_shard)], ["AAA", "BBB"])
    row = _row(frame, "AAA", "2024-01-03")
    assert row["overnight_return"] == pytest.approx(106.0 / 104.0 - 1.0)


def test_single_bar_day_yields_null_realized_vol_and_skew_not_a_crash(
    synthetic_minute_shard: Path,
) -> None:
    frame = build_intraday_daily_features([str(synthetic_minute_shard)], ["AAA", "BBB"])
    row = _row(frame, "BBB", "2024-01-02")
    assert pd.isna(row["intraday_realized_vol"])
    assert pd.isna(row["intraday_skew"])
    assert row["intraday_return"] == pytest.approx(50.0 / 50.0 - 1.0)


def test_universe_restriction_drops_symbols_outside_the_requested_set(
    synthetic_minute_shard: Path,
) -> None:
    frame = build_intraday_daily_features([str(synthetic_minute_shard)], ["AAA"])
    assert set(frame["symbol"]) == {"AAA"}


def test_duplicate_bars_across_two_shards_are_deduplicated_not_double_counted(
    tmp_path: Path, synthetic_minute_shard: Path
) -> None:
    # Simulate the 2023 legacy+month-sharded overlap: the same AAA day-1 bars
    # appear again verbatim in a second shard file.
    original = pd.read_parquet(synthetic_minute_shard)
    duplicate_path = tmp_path / "dup" / "shard-0000.parquet"
    _write_shard(duplicate_path, original.to_dict("records"))

    single = build_intraday_daily_features([str(synthetic_minute_shard)], ["AAA", "BBB"])
    doubled_input = build_intraday_daily_features(
        [str(synthetic_minute_shard), str(duplicate_path)], ["AAA", "BBB"]
    )
    single_row = _row(single, "AAA", "2024-01-02")
    dedup_row = _row(doubled_input, "AAA", "2024-01-02")
    assert dedup_row["trade_count"] == single_row["trade_count"]
    assert dedup_row["amihud_intraday"] == pytest.approx(single_row["amihud_intraday"])


def test_empty_minute_paths_returns_empty_frame_with_correct_columns() -> None:
    frame = build_intraday_daily_features([], ["AAA"])
    assert list(frame.columns) == list(INTRADAY_DAILY_COLUMNS)
    assert len(frame) == 0


def test_empty_universe_symbols_returns_empty_frame(synthetic_minute_shard: Path) -> None:
    frame = build_intraday_daily_features([str(synthetic_minute_shard)], [])
    assert len(frame) == 0


def test_minute_root_for_year_splits_at_2022_2023(tmp_path: Path) -> None:
    sip_root = tmp_path / "sip" / "minute"
    sip_hist_root = tmp_path / "sip-hist" / "minute"
    assert minute_root_for_year(2022, sip_root=sip_root, sip_hist_root=sip_hist_root) == (
        sip_hist_root
    )
    assert minute_root_for_year(2023, sip_root=sip_root, sip_hist_root=sip_hist_root) == sip_root


def test_minute_shard_paths_collects_both_legacy_and_month_sharded_layouts(
    tmp_path: Path,
) -> None:
    year_dir = tmp_path / "2023"
    (year_dir / "01").mkdir(parents=True)
    legacy = year_dir / "shard-0000.parquet"
    legacy.write_bytes(b"")
    month_sharded = year_dir / "01" / "shard-0001.parquet"
    month_sharded.write_bytes(b"")

    paths = minute_shard_paths(tmp_path, 2023)
    assert str(legacy) in paths
    assert str(month_sharded) in paths


def test_minute_shard_paths_returns_empty_list_for_missing_year(tmp_path: Path) -> None:
    assert minute_shard_paths(tmp_path, 1999) == []
