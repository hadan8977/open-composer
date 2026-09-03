from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from open_composer.adapters.data import fetch_ohlcv, load_ohlcv_for_spec
from open_composer.adapters.data.alpaca import AlpacaDataError, fetch_alpaca_bars
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.router_common import load_daily_dataset


def test_alpaca_fetch_uses_cache_without_credentials(sample_workspace: Path) -> None:
    cache = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    sample = sample_workspace / "data" / "sample" / "qqq_15m.csv"
    cache.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    frame = fetch_alpaca_bars(sample_workspace, "QQQ", "15m", None, None, "iex")
    assert len(frame) > 0
    assert frame["close"].iloc[-1] > 0


def test_alpaca_fetch_filters_cache_when_window_is_supplied(sample_workspace: Path) -> None:
    cache = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    sample = sample_workspace / "data" / "sample" / "qqq_15m.csv"
    cache.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")

    frame = fetch_alpaca_bars(
        sample_workspace,
        "QQQ",
        "15m",
        datetime(2026, 1, 2, 15, tzinfo=UTC),
        datetime(2026, 1, 2, 16, tzinfo=UTC),
        "iex",
    )

    assert len(frame) > 0
    assert frame["timestamp"].min() >= __import__("pandas").Timestamp("2026-01-02T15:00:00Z")
    assert frame["timestamp"].max() <= __import__("pandas").Timestamp("2026-01-02T16:00:00Z")


def test_alpaca_daily_fetch_resamples_intraday_cache_when_daily_cache_is_short(
    sample_workspace: Path,
) -> None:
    cache = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2026-01-02T14:30:00Z,100,101,99,100.5,1000",
                "2026-01-02T14:45:00Z,100.5,102,100,101.5,1100",
                "2026-01-05T14:30:00Z,102,103,101,102.5,1200",
                "2026-01-05T14:45:00Z,102.5,104,102,103.5,1300",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    frame = fetch_alpaca_bars(
        sample_workspace,
        "QQQ",
        "daily",
        datetime(2026, 1, 2, tzinfo=UTC),
        datetime(2026, 1, 5, 23, tzinfo=UTC),
        "iex",
    )

    assert list(frame["close"]) == [101.5, 103.5]
    assert frame.attrs["data_source_mode"] == "cache_resampled"
    manifest = sample_workspace / "data" / "cache" / "manifests" / "qqq_daily_alpaca_iex.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["source_mode"] == "cache_resampled"
    assert payload["request_params"]["resampled_from"] == "qqq_15m_iex.csv"


def test_alpaca_fetch_refreshes_when_cache_does_not_cover_requested_window(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    cache = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    cache.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2026-01-02T15:00:00Z,1,2,1,2,100",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class MockClient:
        def __init__(self, **kwargs) -> None:
            pass

        def get_stock_bars(self, request) -> SimpleNamespace:
            return SimpleNamespace(
                df=SimpleNamespace(
                    reset_index=lambda: __import__("pandas").DataFrame(
                        [
                            {
                                "symbol": "QQQ",
                                "timestamp": "2026-01-03T15:00:00Z",
                                "open": 2,
                                "high": 3,
                                "low": 2,
                                "close": 3,
                                "volume": 200,
                            }
                        ]
                    )
                )
            )

    monkeypatch.setattr("alpaca.data.historical.StockHistoricalDataClient", MockClient)

    frame = fetch_alpaca_bars(
        sample_workspace,
        "QQQ",
        "15m",
        datetime(2026, 1, 2, 15, tzinfo=UTC),
        datetime(2026, 1, 3, 16, tzinfo=UTC),
        "iex",
    )

    assert frame["timestamp"].max() == __import__("pandas").Timestamp("2026-01-03T15:00:00Z")
    assert frame.attrs["data_source_mode"] == "live_fetch"


def test_alpaca_fetch_can_refresh_with_credentials(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    captured = {}

    class MockClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def get_stock_bars(self, request) -> SimpleNamespace:
            return SimpleNamespace(
                df=SimpleNamespace(
                    reset_index=lambda: __import__("pandas").DataFrame(
                        [
                            {
                                "symbol": "QQQ",
                                "timestamp": "2026-01-02T09:30:00Z",
                                "open": 1,
                                "high": 2,
                                "low": 1,
                                "close": 2,
                                "volume": 100,
                            }
                        ]
                    )
                )
            )

    monkeypatch.setattr("alpaca.data.historical.StockHistoricalDataClient", MockClient)
    frame = fetch_alpaca_bars(
        sample_workspace,
        "QQQ",
        "15m",
        None,
        None,
        "iex",
        use_cache=False,
    )

    assert captured["api_key"] == "key"
    assert captured["secret_key"] == "secret"
    assert frame["close"].iloc[-1] == 2


def test_alpaca_fetch_binds_adjustment_to_request_cache_and_manifest(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    from alpaca.data.enums import Adjustment

    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    captured = {}

    class MockClient:
        def __init__(self, **kwargs) -> None:
            pass

        def get_stock_bars(self, request) -> SimpleNamespace:
            captured["adjustment"] = request.adjustment
            return SimpleNamespace(
                df=SimpleNamespace(
                    reset_index=lambda: pd.DataFrame(
                        [
                            {
                                "symbol": "SOXS",
                                "timestamp": "2026-01-02T05:00:00Z",
                                "open": 40,
                                "high": 42,
                                "low": 39,
                                "close": 41,
                                "volume": 100,
                            }
                        ]
                    )
                )
            )

    monkeypatch.setattr("alpaca.data.historical.StockHistoricalDataClient", MockClient)

    frame = fetch_alpaca_bars(
        sample_workspace,
        "SOXS",
        "daily",
        None,
        None,
        "iex",
        use_cache=False,
        adjustment="all",
    )

    assert captured["adjustment"] == Adjustment.ALL
    assert frame.attrs["data_source_adjustment"] == "all"
    assert (sample_workspace / "data" / "cache" / "soxs_daily_iex_all.csv").is_file()
    manifest = sample_workspace / "data" / "cache" / "manifests" / "soxs_daily_alpaca_iex_all.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["adjustment"] == "all"
    assert payload["cache_path"].endswith("soxs_daily_iex_all.csv")


def test_alpaca_fetch_rejects_unknown_adjustment(sample_workspace: Path) -> None:
    try:
        fetch_alpaca_bars(
            sample_workspace,
            "QQQ",
            "daily",
            None,
            None,
            "iex",
            adjustment="total_return_guess",
        )
    except AlpacaDataError as exc:
        assert "unsupported Alpaca adjustment" in str(exc)
    else:
        raise AssertionError("unknown Alpaca adjustment unexpectedly accepted")


def test_daily_router_requests_all_adjusted_alpaca_bars(sample_workspace: Path) -> None:
    calls: list[dict] = []
    timestamps = pd.date_range("2026-01-02", periods=40, freq="B", tz="UTC")

    def fake_fetcher(**kwargs):
        calls.append(kwargs)
        frame = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": range(100, 140),
                "high": range(101, 141),
                "low": range(99, 139),
                "close": range(100, 140),
                "volume": [1000] * 40,
            }
        )
        frame.attrs.update(
            {
                "data_source_provider": "alpaca",
                "data_source_feed": "iex",
                "data_source_mode": "live_fetch",
                "data_source_adjustment": kwargs["adjustment"],
            }
        )
        return frame

    spec = StrategySpec(
        name="adjusted_daily_router",
        description="Verify daily router adjustment binding.",
        timeframe="daily",
        universe=["QQQ", "TQQQ"],
        lifecycle="draft",
        entry={"all": ["close > ema(close, 5)"]},
        exit={"any": ["close < ema(close, 5)"]},
        risk={"max_trades_per_day": 1},
        execution={"mode": "manual_signal", "broker": "none"},
        data={"source": "alpaca", "symbol": "QQQ", "feed": "iex"},
        data_assumptions={"source": "alpaca", "adjusted": True},
    )

    dataset = load_daily_dataset(
        spec=spec,
        root=sample_workspace,
        symbols=spec.universe,
        data_source="alpaca",
        feed="iex",
        start=None,
        end=None,
        fetcher=fake_fetcher,
    )

    assert calls
    assert {call["adjustment"] for call in calls} == {"all"}
    assert dataset.data_profile["adjustment"] == "all"


def test_fetch_ohlcv_uses_local_fallback_without_credentials(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    frame = fetch_ohlcv(
        sample_workspace,
        "QQQ",
        "1h",
        None,
        None,
        source="alpaca",
        feed="iex",
        use_cache=False,
    )

    assert len(frame) > 0
    assert frame["timestamp"].iloc[0].tzinfo is not None
    manifest = sample_workspace / "data" / "cache" / "manifests" / "qqq_1h_alpaca_iex.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["source_mode"] == "sample_fallback"
    assert "workflow validation" in payload["caveats"][1]


def test_fetch_ohlcv_can_disable_fallback_without_credentials(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)

    try:
        fetch_ohlcv(
            sample_workspace,
            "QQQ",
            "1h",
            None,
            None,
            source="alpaca",
            feed="iex",
            use_cache=False,
            allow_fallback=False,
        )
    except Exception as exc:
        assert "authentication" in str(exc).lower()
    else:
        raise AssertionError("strict fetch unexpectedly fell back to local sample data")


def test_fetch_ohlcv_supports_expanded_alpaca_timeframe_fallback(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)

    frame = fetch_ohlcv(
        sample_workspace,
        "QQQ",
        "30m",
        None,
        None,
        source="alpaca",
        feed="iex",
        use_cache=False,
    )

    assert len(frame) > 0
    manifest = sample_workspace / "data" / "cache" / "manifests" / "qqq_30m_alpaca_iex.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["source_mode"] == "sample_fallback"


def test_load_ohlcv_for_alpaca_spec_uses_local_fallback_without_credentials(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    spec = StrategySpec(
        name="qqq_alpaca_fallback",
        description="fallback coverage",
        timeframe="1h",
        universe=["QQQ"],
        lifecycle="draft",
        entry={"all": ["close > ema(close, 5)"]},
        exit={"any": ["close < ema(close, 5)"]},
        risk={"max_trades_per_day": 1},
        execution={"mode": "manual_signal", "broker": "none"},
        data={"source": "alpaca", "symbol": "QQQ", "feed": "iex"},
    )

    frame = load_ohlcv_for_spec(spec, sample_workspace, refresh=True)

    assert len(frame) > 0
    assert frame["timestamp"].iloc[0].tzinfo is not None


def _write_sip_daily_shard(sip_root: Path, year: int, rows: pd.DataFrame) -> None:
    path = sip_root / "daily" / str(year) / "shard-0000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(path, compression="zstd", index=False)


def _sip_bars(symbol: str, timestamps: pd.DatetimeIndex, *, base: float = 100.0) -> pd.DataFrame:
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


def test_fetch_ohlcv_sip_parquet_returns_single_symbol_frame_with_provenance(
    sample_workspace: Path,
) -> None:
    from open_composer.adapters.data.sip_parquet import clear_sip_index_cache

    clear_sip_index_cache()
    sip_root = sample_workspace / "data" / "sip"
    timestamps = pd.bdate_range("2023-01-02", "2023-01-31", tz="UTC")
    _write_sip_daily_shard(sip_root, 2023, _sip_bars("QQQ", timestamps, base=300.0))

    frame = fetch_ohlcv(
        root=sample_workspace,
        symbol="QQQ",
        timeframe="daily",
        start=None,
        end=None,
        source="sip_parquet",
    )

    assert "symbol" not in frame.columns
    assert list(frame.columns) == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trade_count",
        "vwap",
    ]
    assert len(frame) == len(timestamps)
    assert frame.attrs["data_source_mode"] == "sip_parquet"
    assert frame.attrs["data_source_adjustment"] == "all"
    assert frame.attrs["acquisition_tier"] == "research_strict"
    clear_sip_index_cache()


def test_fetch_ohlcv_sip_parquet_rejects_non_daily_timeframe(sample_workspace: Path) -> None:
    try:
        fetch_ohlcv(
            root=sample_workspace,
            symbol="QQQ",
            timeframe="1m",
            start=None,
            end=None,
            source="sip_parquet",
        )
        raise AssertionError("expected ValueError for an unsupported sip_parquet timeframe")
    except ValueError as exc:
        assert "sip_parquet" in str(exc)


def test_load_ohlcv_for_spec_dispatches_to_sip_parquet_via_data_path(
    sample_workspace: Path,
) -> None:
    from open_composer.adapters.data.sip_parquet import clear_sip_index_cache

    clear_sip_index_cache()
    sip_root = sample_workspace / "data" / "sip"
    timestamps = pd.bdate_range("2024-01-01", "2024-01-31", tz="UTC")
    _write_sip_daily_shard(sip_root, 2024, _sip_bars("QQQ", timestamps, base=400.0))

    spec = StrategySpec(
        name="sip_path_dispatch",
        description="SIP data.path dispatch coverage",
        timeframe="daily",
        universe=["QQQ"],
        lifecycle="draft",
        entry={"all": ["close > ema(close, 5)"]},
        exit={"any": ["close < ema(close, 5)"]},
        risk={"max_trades_per_day": 1},
        execution={"mode": "manual_signal", "broker": "none"},
        data={"source": "alpaca", "symbol": "QQQ", "path": "data/sip/daily"},
    )

    frame = load_ohlcv_for_spec(spec, sample_workspace)

    assert len(frame) == len(timestamps)
    assert frame.attrs["data_source_mode"] == "sip_parquet"
    clear_sip_index_cache()
