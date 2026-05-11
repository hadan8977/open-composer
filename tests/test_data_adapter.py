from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from open_composer.adapters.data import fetch_ohlcv, load_ohlcv_for_spec
from open_composer.adapters.data.alpaca import fetch_alpaca_bars
from open_composer.models.strategy_spec import StrategySpec


def test_alpaca_fetch_uses_cache_without_credentials(sample_workspace: Path) -> None:
    cache = sample_workspace / "data" / "cache" / "qqq_15m_iex.csv"
    sample = sample_workspace / "data" / "sample" / "qqq_15m.csv"
    cache.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    frame = fetch_alpaca_bars(sample_workspace, "QQQ", "15m", None, None, "iex")
    assert len(frame) > 0
    assert frame["close"].iloc[-1] > 0


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
