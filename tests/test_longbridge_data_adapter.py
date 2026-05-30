from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from open_composer.adapters.data import fetch_ohlcv
from open_composer.adapters.data.comparison import compare_ohlcv_sources
from open_composer.adapters.data.longbridge import (
    LongbridgeDataError,
    fetch_longbridge_bars,
    longbridge_cache_path,
    longbridge_materialized_history_path,
    missing_longbridge_credentials,
)
from open_composer.research.metadata import frame_data_profile


def test_longbridge_fetch_uses_cache_and_writes_manifest(sample_workspace: Path) -> None:
    cache = longbridge_cache_path(sample_workspace, "QQQ", "15m")
    sample = sample_workspace / "data" / "sample" / "qqq_15m.csv"
    cache.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")

    frame = fetch_longbridge_bars(
        sample_workspace,
        "QQQ",
        "15m",
        None,
        None,
        feed=None,
        use_cache=True,
    )

    manifest = (
        sample_workspace / "data" / "cache" / "manifests" / "qqq_15m_longbridge_nasdaq_basic.json"
    )
    assert len(frame) > 0
    assert manifest.exists()
    assert "longbridge" in manifest.read_text(encoding="utf-8")


def test_longbridge_ignores_alpaca_only_feed_alias_for_provenance(
    sample_workspace: Path,
) -> None:
    cache = sample_workspace / "data" / "cache" / "qqq_15m_longbridge_iex.csv"
    sample = sample_workspace / "data" / "sample" / "qqq_15m.csv"
    cache.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")

    frame = fetch_ohlcv(
        sample_workspace,
        "QQQ",
        "15m",
        None,
        None,
        source="longbridge",
        feed="iex",
        use_cache=True,
        allow_fallback=False,
    )

    assert frame.attrs["data_source_feed"] == "nasdaq_basic"
    assert frame.attrs["data_source_path"].endswith("qqq_15m_longbridge_nasdaq_basic.csv")
    assert longbridge_cache_path(sample_workspace, "QQQ", "15m").exists()


def test_data_profile_prefers_frame_provenance_over_requested_feed(
    sample_workspace: Path,
) -> None:
    cache = longbridge_cache_path(sample_workspace, "QQQ", "15m")
    sample = sample_workspace / "data" / "sample" / "qqq_15m.csv"
    cache.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    frame = fetch_ohlcv(
        sample_workspace,
        "QQQ",
        "15m",
        None,
        None,
        source="longbridge",
        feed="iex",
        use_cache=True,
        allow_fallback=False,
    )

    profile = frame_data_profile(
        frame,
        symbol="QQQ",
        timeframe="15m",
        provider="longbridge",
        feed="iex",
        source_mode=frame.attrs.get("data_source_mode"),
    )

    assert profile["feed"] == "nasdaq_basic"
    assert "iex_feed_not_full_market_sip" not in profile["warnings"]


def test_longbridge_daily_fetch_uses_materialized_history_with_date_filter(
    sample_workspace: Path,
) -> None:
    history = longbridge_materialized_history_path(sample_workspace, "QQQ", "daily")
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2024-01-02T05:00:00+00:00,100,101,99,100.5,1000",
                "2024-01-03T05:00:00+00:00,101,102,100,101.5,1100",
                "2024-01-04T05:00:00+00:00,102,103,101,102.5,1200",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    frame = fetch_longbridge_bars(
        sample_workspace,
        "QQQ",
        "daily",
        datetime.fromisoformat("2024-01-03T00:00:00+00:00"),
        datetime.fromisoformat("2024-01-04T23:59:59+00:00"),
        feed=None,
        use_cache=True,
    )

    assert list(frame["close"]) == [101.5, 102.5]
    assert frame.attrs["data_source_mode"] == "materialized_history_cache"
    manifest = (
        sample_workspace / "data" / "cache" / "manifests" / "qqq_daily_longbridge_nasdaq_basic.json"
    )
    assert "materialized_history_cache" in manifest.read_text(encoding="utf-8")


def test_longbridge_missing_credentials_requires_access_token(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "app-key")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "secret")
    monkeypatch.delenv("LONGBRIDGE_ACCESS_TOKEN", raising=False)

    assert missing_longbridge_credentials(sample_workspace) == ["LONGBRIDGE_ACCESS_TOKEN"]


def test_longbridge_live_fetch_uses_official_sdk_methods(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "app-key")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "secret")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "token")
    captured = {}

    class MockConfig:
        @staticmethod
        def from_apikey(app_key, app_secret, access_token, **kwargs):
            captured["credentials"] = (app_key, app_secret, access_token, kwargs)
            return object()

    class MockQuoteContext:
        def __init__(self, config) -> None:
            captured["config"] = config

        def candlesticks(self, symbol, period, count, adjust_type, trade_sessions):
            captured["candlesticks"] = (symbol, period, count, adjust_type, trade_sessions)
            return [
                SimpleNamespace(
                    timestamp=datetime.fromisoformat("2026-01-02T09:30:00+00:00"),
                    open=1,
                    high=2,
                    low=1,
                    close=2,
                    volume=100,
                )
            ]

    class MockPeriod:
        Min_15 = "Min_15"

    class MockAdjustType:
        ForwardAdjust = "ForwardAdjust"
        NoAdjust = "NoAdjust"

    class MockTradeSessions:
        Intraday = "Intraday"
        All = "All"

    monkeypatch.setattr("longbridge.openapi.Config", MockConfig)
    monkeypatch.setattr("longbridge.openapi.QuoteContext", MockQuoteContext)
    monkeypatch.setattr("longbridge.openapi.Period", MockPeriod)
    monkeypatch.setattr("longbridge.openapi.AdjustType", MockAdjustType)
    monkeypatch.setattr("longbridge.openapi.TradeSessions", MockTradeSessions)

    frame = fetch_longbridge_bars(
        sample_workspace,
        "QQQ",
        "15m",
        None,
        None,
        use_cache=False,
        count=7,
    )

    assert captured["credentials"] == (
        "app-key",
        "secret",
        "token",
        {"enable_print_quote_packages": False},
    )
    assert captured["candlesticks"] == ("QQQ.US", "Min_15", 7, "ForwardAdjust", "Intraday")
    assert frame["close"].iloc[-1] == 2


def test_longbridge_date_range_fetch_pages_by_offset(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "app-key")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "secret")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "token")
    monkeypatch.setenv("LONGBRIDGE_MAX_HISTORY_PAGES", "3")
    calls = []

    class MockConfig:
        @staticmethod
        def from_apikey(*_args, **_kwargs):
            return object()

    class MockQuoteContext:
        def __init__(self, _config) -> None:
            pass

        def history_candlesticks_by_offset(
            self,
            symbol,
            period,
            adjust_type,
            forward,
            count,
            time,
            trade_sessions,
        ):
            calls.append((symbol, period, adjust_type, forward, count, time, trade_sessions))
            if len(calls) == 1:
                return [
                    SimpleNamespace(
                        timestamp=datetime.fromisoformat("2026-01-02T14:30:00+00:00"),
                        open=1,
                        high=2,
                        low=1,
                        close=2,
                        volume=100,
                    ),
                    SimpleNamespace(
                        timestamp=datetime.fromisoformat("2026-01-02T14:31:00+00:00"),
                        open=2,
                        high=3,
                        low=2,
                        close=3,
                        volume=200,
                    ),
                ]
            return [
                SimpleNamespace(
                    timestamp=datetime.fromisoformat("2026-01-02T14:32:00+00:00"),
                    open=3,
                    high=4,
                    low=3,
                    close=4,
                    volume=300,
                )
            ]

    class MockPeriod:
        Min_1 = "Min_1"

    class MockAdjustType:
        ForwardAdjust = "ForwardAdjust"
        NoAdjust = "NoAdjust"

    class MockTradeSessions:
        Intraday = "Intraday"
        All = "All"

    monkeypatch.setattr("longbridge.openapi.Config", MockConfig)
    monkeypatch.setattr("longbridge.openapi.QuoteContext", MockQuoteContext)
    monkeypatch.setattr("longbridge.openapi.Period", MockPeriod)
    monkeypatch.setattr("longbridge.openapi.AdjustType", MockAdjustType)
    monkeypatch.setattr("longbridge.openapi.TradeSessions", MockTradeSessions)

    frame = fetch_longbridge_bars(
        sample_workspace,
        "QQQ",
        "1m",
        datetime.fromisoformat("2026-01-02T14:30:00+00:00"),
        datetime.fromisoformat("2026-01-02T14:32:00+00:00"),
        use_cache=False,
        count=2,
    )

    assert len(calls) == 2
    assert calls[0][3] is True
    assert list(frame["close"]) == [2, 3, 4]


def test_longbridge_live_fetch_requires_valid_count(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "app-key")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "secret")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "token")

    try:
        fetch_longbridge_bars(
            sample_workspace,
            "QQQ",
            "15m",
            None,
            None,
            use_cache=False,
            count=1001,
        )
    except LongbridgeDataError as exc:
        assert "between 1 and 1000" in str(exc)
    else:
        raise AssertionError("expected LongbridgeDataError")


def test_longbridge_unsupported_timeframe_fails_before_fallback(sample_workspace: Path) -> None:
    try:
        fetch_ohlcv(
            sample_workspace,
            "QQQ",
            "30m",
            None,
            None,
            source="longbridge",
            feed=None,
            use_cache=False,
        )
    except ValueError as exc:
        assert "unsupported longbridge timeframe: 30m" in str(exc)
    else:
        raise AssertionError("expected unsupported timeframe ValueError")


def test_ohlcv_comparison_writes_reports(sample_workspace: Path) -> None:
    alpaca_cache = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    longbridge_cache = longbridge_cache_path(sample_workspace, "QQQ", "15m")
    sample = sample_workspace / "data" / "sample" / "qqq_15m.csv"
    alpaca_cache.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    longbridge_lines = sample.read_text(encoding="utf-8").splitlines()
    longbridge_lines[-1] = "2026-01-02T11:00:00-05:00,101.00,101.40,100.80,101.80,1075000"
    longbridge_cache.write_text("\n".join(longbridge_lines) + "\n", encoding="utf-8")

    report = compare_ohlcv_sources(
        sample_workspace,
        "QQQ",
        "15m",
        left_source="alpaca",
        right_source="longbridge",
        left_feed="iex",
        right_feed=None,
    )

    assert report.matched_rows > 0
    assert report.max_abs_close_diff > 0
    assert report.max_abs_close_diff_bps > 0
    assert report.matched_coverage_pct > 0
    assert report.left_manifest_path
    assert report.right_manifest_path
    assert report.right_feed == "nasdaq_basic"
    assert any("Alpaca IEX" in caveat for caveat in report.caveats)
    assert any("Longbridge free US market data" in caveat for caveat in report.caveats)
    assert Path(report.report_json_path).exists()
    assert Path(report.report_markdown_path).exists()
    payload = json.loads(Path(report.report_json_path).read_text(encoding="utf-8"))
    markdown = Path(report.report_markdown_path).read_text(encoding="utf-8")
    assert payload["max_abs_close_diff_bps"] == report.max_abs_close_diff_bps
    assert payload["left_manifest_path"] == report.left_manifest_path
    assert "Matched coverage" in markdown
    assert "Caveats" in markdown
