from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.market_calendar import expected_us_equity_rth_bar_starts
from open_composer.research.minute_momentum_feasibility import (
    _resample_frame,
    _timeframe_summary,
    compute_minute_quality,
    resample_us_equity_rth,
    run_minute_momentum_feasibility,
)


def test_resample_frame_anchors_hour_bars_to_session_open() -> None:
    timestamps = pd.date_range("2026-01-02T14:30:00Z", periods=13, freq="30min")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": range(13),
            "high": range(1, 14),
            "low": range(13),
            "close": range(1, 14),
            "volume": [1] * 13,
        }
    )

    result = _resample_frame(frame, "1h")

    local = pd.to_datetime(result["timestamp"], utc=True).dt.tz_convert("America/New_York")
    assert list(local.dt.strftime("%H:%M")) == [
        "09:30",
        "10:30",
        "11:30",
        "12:30",
        "13:30",
        "14:30",
        "15:30",
    ]
    assert result.iloc[0]["open"] == 0
    assert result.iloc[0]["close"] == 2


def test_compute_minute_quality_detects_extended_hours_and_zero_volume() -> None:
    frame = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-02T13:00:00Z",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 0,
            },
            {
                "timestamp": "2026-01-02T14:30:00Z",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 10,
            },
            {
                "timestamp": "2026-01-02T14:45:00Z",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 20,
            },
            {
                "timestamp": "2026-01-02T21:30:00Z",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 30,
            },
        ]
    )

    quality = compute_minute_quality(frame, "15m")

    assert quality["extended_hours_present"] is True
    assert quality["extended_hours_ratio"] == 0.5
    assert quality["zero_volume_ratio"] == 0.25
    assert quality["rth_days"] == 1
    assert quality["timestamp_label"] == "start"
    assert quality["rth_gap_rate"] == 0.0


def test_compute_minute_quality_uses_grid_gaps_instead_of_daily_row_counts() -> None:
    expected = sorted(expected_us_equity_rth_bar_starts(pd.Timestamp("2026-01-02").date(), 15))
    missing = expected[2]
    frame = _ohlcv_frame(
        [*[timestamp for timestamp in expected if timestamp != missing], expected[1]]
    )

    quality = compute_minute_quality(frame, "15m")

    assert quality["rth_interior_expected_bars"] == 26
    assert quality["rth_matched_bars"] == 25
    assert quality["rth_missing_interior_bars"] == 1
    assert quality["rth_duplicate_bars"] == 1
    assert quality["rth_gap_rate"] == round(1 / 26, 6)
    assert quality["session_grid_quality_status"] == "degraded"


def test_session_aware_resampler_excludes_holidays_and_post_early_close() -> None:
    frame = _ohlcv_frame(
        [
            "2026-07-03T13:30:00Z",  # Holiday.
            "2026-11-27T17:30:00Z",  # 12:30 ET, final early-close bucket.
            "2026-11-27T18:00:00Z",  # Early-close boundary, not an RTH start.
        ]
    )

    result = resample_us_equity_rth(frame, "30m")

    assert list(result["timestamp"]) == [pd.Timestamp("2026-11-27T17:30:00Z")]


def test_timeframe_summary_requires_panel_coverage_not_one_symbol_history() -> None:
    rows = [
        {
            "symbol": "QQQ",
            "timeframe": "15m",
            "status": "ok",
            "history_months": 24.0,
            "go": True,
        },
        {
            "symbol": "SPY",
            "timeframe": "15m",
            "status": "ok",
            "history_months": 6.0,
            "go": False,
        },
    ]

    strict = _timeframe_summary(rows)["15m"]
    explicit_half_coverage = _timeframe_summary(rows, 0.5)["15m"]

    assert strict["max_history_months"] == 24.0
    assert strict["min_history_months"] == 6.0
    assert strict["qualifying_symbols"] == 1
    assert strict["required_symbols"] == 2
    assert strict["go"] is False
    assert explicit_half_coverage["required_symbols"] == 1
    assert explicit_half_coverage["go"] is True


def test_minute_feasibility_uses_isolated_research_output(
    sample_workspace: Path, monkeypatch
) -> None:
    # This test's cache fixture is named for the iex feed explicitly; declare
    # that rather than relying on data_feed()'s global default (config.py
    # defaults ALPACA_DATA_FEED to "sip" as of Step 10 section 3.3).
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    cache_path = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _write_cache(cache_path, periods=30)

    result = run_minute_momentum_feasibility(
        sample_workspace,
        symbols=["QQQ"],
        representative_symbols=["QQQ"],
        timeframes=["15m"],
        report_date="20260710",
    )

    row = result.payload["rows"][0]
    assert row["status"] == "ok"
    assert row["source_mode"] == "cache_copy"
    assert row["path"].startswith("data/research/alpaca_minute/")
    assert (sample_workspace / row["path"]).exists()
    assert result.json_path.exists()
    assert result.markdown_path.exists()
    assert result.manifest_path.exists()


def test_minute_feasibility_missing_cache_records_error_without_fallback(
    sample_workspace: Path,
) -> None:
    result = run_minute_momentum_feasibility(
        sample_workspace,
        symbols=["MISSING"],
        representative_symbols=["MISSING"],
        timeframes=["15m"],
        report_date="20260710",
    )

    row = result.payload["rows"][0]
    assert row["status"] == "error"
    assert row["go"] is False
    assert "missing Alpaca cache" in row["error"]
    assert not list((sample_workspace / "data" / "research" / "alpaca_minute").glob("*.csv"))


def test_minute_feasibility_long_history_with_interior_gaps_is_no_go(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    # See test_minute_feasibility_uses_isolated_research_output's comment:
    # this fixture is an iex-named cache file, independent of the global
    # data_feed() default.
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    cache_path = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    first = expected_us_equity_rth_bar_starts(pd.Timestamp("2024-01-02").date(), 15)
    last = expected_us_equity_rth_bar_starts(pd.Timestamp("2025-10-01").date(), 15)
    _ohlcv_frame(sorted(first | last)).to_csv(cache_path, index=False)

    strict = run_minute_momentum_feasibility(
        sample_workspace,
        symbols=["QQQ"],
        representative_symbols=["QQQ"],
        timeframes=["15m"],
        report_date="20260711",
    ).payload["rows"][0]
    tolerant = run_minute_momentum_feasibility(
        sample_workspace,
        symbols=["QQQ"],
        representative_symbols=["QQQ"],
        timeframes=["15m"],
        max_rth_gap_rate=1.0,
        report_date="20260712",
    ).payload["rows"][0]

    assert strict["history_months"] >= 18.0
    assert strict["rth_gap_rate"] > 0.0
    assert strict["rth_duplicate_bars"] == 0
    assert strict["off_session_bars"] == 0
    assert strict["off_grid_bars"] == 0
    assert strict["rth_missing_boundary_bars"] == 0
    assert strict["rth_days"] == 2
    assert strict["grid_go"] is False
    assert strict["go"] is False
    assert "rth_gap_rate>0.0" in strict["go_reason"]
    assert tolerant["grid_go"] is True
    assert tolerant["go"] is True


def test_minute_feasibility_cli_writes_report(sample_workspace: Path, monkeypatch) -> None:
    # See test_minute_feasibility_uses_isolated_research_output's comment:
    # this fixture is an iex-named cache file, independent of the global
    # data_feed() default.
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    cache_path = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _write_cache(cache_path, periods=30)

    result = CliRunner().invoke(
        app,
        [
            "data",
            "minute-momentum-feasibility",
            "--symbols",
            "QQQ",
            "--representative-symbols",
            "QQQ",
            "--timeframes",
            "15m",
            "--report-date",
            "20260710",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(
        (
            sample_workspace
            / "reports"
            / "research"
            / "control"
            / "minute-momentum-feasibility-20260710.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["rows"][0]["symbol"] == "QQQ"


def _write_cache(path: Path, *, periods: int) -> None:
    timestamps = pd.date_range("2026-01-02T14:30:00Z", periods=periods, freq="15min")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100 + idx for idx in range(periods)],
            "high": [101 + idx for idx in range(periods)],
            "low": [99 + idx for idx in range(periods)],
            "close": [100.5 + idx for idx in range(periods)],
            "volume": [1000] * periods,
        }
    )
    frame.to_csv(path, index=False)


def _ohlcv_frame(timestamps: list[object]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100] * len(timestamps),
            "high": [101] * len(timestamps),
            "low": [99] * len(timestamps),
            "close": [100.5] * len(timestamps),
            "volume": [1000] * len(timestamps),
        }
    )
