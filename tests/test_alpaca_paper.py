from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from open_composer.adapters.broker import alpaca_paper
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import load_strategy_spec


def _active_paper_spec(sample_workspace: Path) -> Path:
    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    raw = yaml.safe_load(draft.read_text(encoding="utf-8"))
    raw["lifecycle"] = "active"
    raw["execution"]["mode"] = "paper_auto"
    raw["execution"]["broker"] = "alpaca_paper"
    active = sample_workspace / "strategy_specs" / "active" / "qqq_pullback_15m.yaml"
    active.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return active


def test_paper_submit_is_idempotent(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    spec = load_strategy_spec(_active_paper_spec(sample_workspace))
    signal = Signal(
        id="sig_test",
        run_id="run",
        strategy_name=spec.name,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        timestamp="2026-01-02T15:45:00Z",
        action="entry",
        side="buy",
        source="scan",
        price=100.0,
        conditions=[],
        lifecycle="active",
        execution_mode="paper_auto",
        fill_assumption="next_bar_open",
    )
    calls = {"count": 0}

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(equity="10000")

    def fake_submit(client, signal_arg, qty, client_order_id):
        calls["count"] += 1
        return SimpleNamespace(id="order_1", status="accepted")

    monkeypatch.setattr(alpaca_paper, "_submit_market_order", fake_submit)
    first = alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=MockClient())
    second = alpaca_paper.submit_paper_order(signal, spec, sample_workspace, client=MockClient())
    assert first.id == "order_1"
    assert second.signal_id == signal.id
    assert calls["count"] == 1


def test_paper_sync_writes_mock_orders(sample_workspace: Path) -> None:
    class MockClient:
        def get_orders(self) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(
                    id="order_1",
                    client_order_id="oc-sig_test",
                    symbol="QQQ",
                    side="buy",
                    qty="1",
                    status="accepted",
                )
            ]

    path = alpaca_paper.sync_paper_orders(sample_workspace, client=MockClient())
    assert path.exists()


def test_trading_client_uses_configured_paper_base_url(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_API_BASE_URL", "https://paper-api.alpaca.markets/v2")

    captured = {}

    class MockTradingClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("alpaca.trading.client.TradingClient", MockTradingClient)
    alpaca_paper._trading_client()

    assert captured["api_key"] == "key"
    assert captured["secret_key"] == "secret"
    assert captured["paper"] is True
    assert captured["url_override"] == "https://paper-api.alpaca.markets"
