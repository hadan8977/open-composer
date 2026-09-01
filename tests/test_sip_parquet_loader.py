from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from open_composer.adapters.data.sip_parquet import (
    ACQUISITION_TIER,
    DATA_SOURCE_MODE,
    SipParquetError,
    _candidate_shards,
    available_sip_years,
    clear_sip_index_cache,
    default_sip_root,
    load_sip_bars,
)

REAL_DAILY = default_sip_root() / "daily"
REAL_MINUTE = default_sip_root() / "minute"

requires_real_daily = pytest.mark.skipif(
    not REAL_DAILY.is_dir(),
    reason="local SIP daily archive (data/sip/daily) is not present",
)
requires_real_minute = pytest.mark.skipif(
    not REAL_MINUTE.is_dir(),
    reason="local SIP minute archive (data/sip/minute) is not present",
)


def _bars(symbol: str, timestamps: pd.DatetimeIndex, *, base: float = 100.0) -> pd.DataFrame:
    count = len(timestamps)
    return pd.DataFrame(
        {
            "symbol": [symbol] * count,
            "timestamp": timestamps,
            "open": [base + index for index in range(count)],
            "high": [base + index + 1.0 for index in range(count)],
            "low": [base + index - 1.0 for index in range(count)],
            "close": [base + index + 0.5 for index in range(count)],
            "volume": [1000.0 + index for index in range(count)],
            "trade_count": [10.0 + index for index in range(count)],
            "vwap": [base + index + 0.25 for index in range(count)],
        }
    )


def _write_shard(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, compression="zstd", index=False)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_sip_index_cache()
    yield
    clear_sip_index_cache()


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    """A miniature SIP archive exercising both minute layouts."""
    root = tmp_path / "sip"

    daily_2023 = pd.bdate_range("2023-01-02", "2023-01-31", tz="UTC")
    daily_2024 = pd.bdate_range("2024-01-01", "2024-01-31", tz="UTC")
    _write_shard(
        root / "daily" / "2023" / "shard-0000.parquet",
        pd.concat([_bars("AAA", daily_2023), _bars("QQQ", daily_2023, base=300.0)]),
    )
    _write_shard(
        root / "daily" / "2024" / "shard-0000.parquet",
        pd.concat([_bars("AAA", daily_2024), _bars("QQQ", daily_2024, base=400.0)]),
    )
    # A shard holding only later-alphabet symbols; footer pruning must skip it.
    _write_shard(
        root / "daily" / "2023" / "shard-0001.parquet",
        _bars("ZZZ", daily_2023, base=10.0),
    )
    # Empty marker written by the fetcher for a genuinely empty window.
    _write_shard(
        root / "daily" / "2023" / "shard-0002.parquet",
        pd.DataFrame(columns=["symbol", "timestamp"]),
    )

    # Legacy whole-year minute layout: January and February.
    jan = pd.date_range("2023-01-03 14:30", periods=30, freq="1min", tz="UTC")
    feb = pd.date_range("2023-02-01 14:30", periods=30, freq="1min", tz="UTC")
    _write_shard(
        root / "minute" / "2023" / "shard-0000.parquet",
        pd.concat([_bars("AAA", jan), _bars("AAA", feb)]),
    )
    # Current year/month layout: February (overlapping the whole-year shard) and March.
    mar = pd.date_range("2023-03-01 14:30", periods=30, freq="1min", tz="UTC")
    _write_shard(
        root / "minute" / "2023" / "02" / "shard-0007.parquet",
        _bars("AAA", feb),
    )
    _write_shard(
        root / "minute" / "2023" / "03" / "shard-0007.parquet",
        _bars("AAA", mar),
    )
    return root


def test_time_range_slicing_is_inclusive_on_both_ends(archive: Path) -> None:
    frame = load_sip_bars(
        "AAA",
        frequency="daily",
        start="2023-01-10",
        end="2023-01-20",
        root=archive,
    )
    assert frame["timestamp"].min() == pd.Timestamp("2023-01-10", tz="UTC")
    assert frame["timestamp"].max() == pd.Timestamp("2023-01-20", tz="UTC")
    assert len(frame) == len(pd.bdate_range("2023-01-10", "2023-01-20"))
    assert frame["timestamp"].is_monotonic_increasing


def test_range_crossing_year_directories(archive: Path) -> None:
    frame = load_sip_bars(
        "AAA",
        frequency="daily",
        start="2023-01-25",
        end="2024-01-05",
        root=archive,
    )
    years = set(frame["timestamp"].dt.year)
    assert years == {2023, 2024}


def test_unbounded_range_returns_whole_archive(archive: Path) -> None:
    frame = load_sip_bars("AAA", frequency="daily", root=archive)
    assert set(frame["timestamp"].dt.year) == {2023, 2024}


def test_missing_symbol_raises_clear_error(archive: Path) -> None:
    with pytest.raises(SipParquetError) as excinfo:
        load_sip_bars("NOSUCH", frequency="daily", root=archive)
    message = str(excinfo.value)
    assert "NOSUCH" in message
    assert "daily" in message


def test_symbol_present_but_outside_window_raises(archive: Path) -> None:
    with pytest.raises(SipParquetError) as excinfo:
        load_sip_bars(
            "AAA",
            frequency="daily",
            start="2019-01-01",
            end="2019-12-31",
            root=archive,
        )
    assert "2019" in str(excinfo.value)


def test_allow_missing_returns_partial_frame(archive: Path) -> None:
    frame = load_sip_bars(
        ["AAA", "NOSUCH"],
        frequency="daily",
        root=archive,
        allow_missing=True,
    )
    assert set(frame["symbol"]) == {"AAA"}
    assert frame.attrs["data_source_missing_symbols"] == ["NOSUCH"]


def test_daily_and_minute_are_never_mixed(archive: Path) -> None:
    daily = load_sip_bars("AAA", frequency="daily", root=archive)
    minute = load_sip_bars("AAA", frequency="minute", root=archive)

    daily_stamps = set(daily["timestamp"])
    minute_stamps = set(minute["timestamp"])
    assert daily_stamps & minute_stamps == set()
    # Daily bars are midnight-anchored; minute bars carry intraday clock times.
    assert {stamp.minute for stamp in daily_stamps} == {0}
    assert len({stamp.minute for stamp in minute_stamps}) > 1
    assert daily.attrs["data_source_frequency"] == "daily"
    assert minute.attrs["data_source_frequency"] == "minute"


def test_symbol_only_in_daily_is_not_served_from_minute(archive: Path) -> None:
    load_sip_bars("QQQ", frequency="daily", root=archive)
    with pytest.raises(SipParquetError):
        load_sip_bars("QQQ", frequency="minute", root=archive)


def test_unsupported_frequency_is_rejected(archive: Path) -> None:
    with pytest.raises(SipParquetError) as excinfo:
        load_sip_bars("AAA", frequency="hourly", root=archive)
    assert "hourly" in str(excinfo.value)


def test_both_minute_layouts_are_read(archive: Path) -> None:
    frame = load_sip_bars("AAA", frequency="minute", root=archive)
    months = sorted(set(frame["timestamp"].dt.month))
    # January comes only from the whole-year shard, March only from the
    # year/month shard, February from both.
    assert months == [1, 2, 3]
    assert frame.attrs["data_source_shard_count"] == 3


def test_overlapping_minute_layouts_are_deduplicated(archive: Path) -> None:
    frame = load_sip_bars(
        "AAA",
        frequency="minute",
        start="2023-02-01",
        end="2023-02-28",
        root=archive,
    )
    assert not frame.duplicated(subset=["symbol", "timestamp"]).any()
    assert len(frame) == 30


def test_month_directories_are_pruned_by_range(archive: Path) -> None:
    frame = load_sip_bars(
        "AAA",
        frequency="minute",
        start="2023-03-01",
        end="2023-03-31",
        root=archive,
    )
    assert set(frame["timestamp"].dt.month) == {3}

    candidates = _candidate_shards(
        archive / "minute",
        pd.Timestamp("2023-03-01", tz="UTC"),
        pd.Timestamp("2023-03-31", tz="UTC"),
    )
    month_dirs = sorted({path.parent.name for path in candidates if path.parent.name != "2023"})
    # Only March's month shard survives pruning; the whole-year shard is still a
    # candidate because it spans the entire calendar year.
    assert month_dirs == ["03"]
    assert any(path.parent.name == "2023" for path in candidates)


def test_provenance_attributes(archive: Path) -> None:
    frame = load_sip_bars("AAA", frequency="daily", root=archive)
    assert frame.attrs["data_source_mode"] == DATA_SOURCE_MODE == "sip_parquet"
    assert frame.attrs["acquisition_tier"] == ACQUISITION_TIER == "research_strict"
    assert frame.attrs["data_source_provider"] == "alpaca"
    assert frame.attrs["data_source_feed"] == "sip"
    assert frame.attrs["data_source_adjustment"] == "all"
    assert frame.attrs["data_source_symbols"] == ["AAA"]
    assert frame.attrs["data_source_path"].endswith("daily")


def test_multi_symbol_frame_is_grouped_and_sorted(archive: Path) -> None:
    frame = load_sip_bars(["qqq", "AAA"], frequency="daily", root=archive)
    assert list(frame["symbol"].unique()) == ["AAA", "QQQ"]
    for _symbol, group in frame.groupby("symbol"):
        assert group["timestamp"].is_monotonic_increasing


def test_blank_symbol_is_rejected(archive: Path) -> None:
    with pytest.raises(SipParquetError):
        load_sip_bars("  ", frequency="daily", root=archive)


def test_start_after_end_is_rejected(archive: Path) -> None:
    with pytest.raises(SipParquetError):
        load_sip_bars(
            "AAA",
            frequency="daily",
            start="2024-01-01",
            end="2023-01-01",
            root=archive,
        )


def test_missing_archive_directory_reports_path(tmp_path: Path) -> None:
    with pytest.raises(SipParquetError) as excinfo:
        load_sip_bars("AAA", frequency="daily", root=tmp_path / "absent")
    assert "absent" in str(excinfo.value)


def test_naive_datetimes_are_treated_as_utc(archive: Path) -> None:
    from datetime import datetime

    frame = load_sip_bars(
        "AAA",
        frequency="daily",
        start=datetime(2023, 1, 10),
        end=datetime(2023, 1, 12),
        root=archive,
    )
    assert frame["timestamp"].min() == pd.Timestamp("2023-01-10", tz="UTC")
    assert frame["timestamp"].max() == pd.Timestamp("2023-01-12", tz="UTC")


def test_available_sip_years(archive: Path) -> None:
    assert available_sip_years("daily", root=archive) == [2023, 2024]
    assert available_sip_years("minute", root=archive) == [2023]


@requires_real_daily
def test_real_archive_daily_qqq_window() -> None:
    frame = load_sip_bars("QQQ", frequency="daily", start="2022-01-01", end="2022-12-31")
    assert 240 <= len(frame) <= 256
    assert frame["timestamp"].is_monotonic_increasing
    assert not frame.duplicated(subset=["symbol", "timestamp"]).any()
    assert frame["close"].gt(0).all()
    assert frame.attrs["data_source_mode"] == "sip_parquet"
    assert frame.attrs["acquisition_tier"] == "research_strict"


@requires_real_minute
def test_real_archive_minute_is_partial_but_finer_than_daily() -> None:
    """The minute tape is still being fetched, so assert shape, not row counts."""
    years = available_sip_years("minute")
    if not years:
        pytest.skip("no minute years fetched yet")
    frame = load_sip_bars(
        "QQQ",
        frequency="minute",
        start=f"{years[0]}-01-01",
        end=f"{years[0]}-12-31",
        root=None,
        allow_missing=True,
    )
    if frame.empty:
        pytest.skip("minute coverage for QQQ has not been fetched yet")
    assert not frame.duplicated(subset=["symbol", "timestamp"]).any()
    assert frame["timestamp"].is_monotonic_increasing
    assert len({stamp.minute for stamp in frame["timestamp"]}) > 1
    daily = load_sip_bars(
        "QQQ",
        frequency="daily",
        start=f"{years[0]}-01-01",
        end=f"{years[0]}-12-31",
    )
    assert len(frame) > len(daily)
    assert set(frame["timestamp"]) & set(daily["timestamp"]) == set()
