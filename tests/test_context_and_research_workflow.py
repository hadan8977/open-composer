from __future__ import annotations

from pathlib import Path
from shutil import copyfile
from types import SimpleNamespace

import yaml

from open_composer.adapters.broker import alpaca_paper
from open_composer.adapters.events import fetch_capability_events
from open_composer.capabilities import evaluate_capabilities
from open_composer.context import build_signal_context
from open_composer.engines.backtest_engine import run_backtest
from open_composer.engines.scanner_engine import run_scan
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research import draft_strategy_from_idea, optimize_strategy


def test_signal_context_excludes_future_records(sample_workspace: Path) -> None:
    fetch_capability_events("sec", sample_workspace, ["QQQ"], offline=True)
    fetch_capability_events("alpha_vantage", sample_workspace, ["QQQ"], offline=True)
    fetch_capability_events("fred", sample_workspace, None, offline=True)
    artifacts = run_backtest(
        sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
        root=sample_workspace,
    )
    context = build_signal_context(artifacts.signals[0].id, sample_workspace)
    assert context.events
    assert context.macro
    assert all(event.published_at <= artifacts.signals[0].timestamp for event in context.events)


def test_natural_language_to_context_to_paper_mock(sample_workspace: Path, monkeypatch) -> None:
    idea = (
        "Create a QQQ 15m pullback strategy with SEC filings, FRED macro, "
        "Alpha Vantage news, GDELT broad events, and Alpaca Paper later."
    )
    spec_path = draft_strategy_from_idea(idea, sample_workspace)
    spec = load_strategy_spec(spec_path)
    assert "events.sec_filings" in spec.required_capabilities
    assert all(evaluation.passed for evaluation in evaluate_capabilities(sample_workspace))

    fetch_capability_events("sec", sample_workspace, ["QQQ"], offline=True)
    fetch_capability_events("alpha_vantage", sample_workspace, ["QQQ"], offline=True)
    fetch_capability_events("gdelt", sample_workspace, ["QQQ"], offline=True)
    fetch_capability_events("fred", sample_workspace, None, offline=True)

    artifacts = run_backtest(spec_path, root=sample_workspace)
    assert artifacts.signals
    latest_signals = run_scan(spec_path, root=sample_workspace)
    assert latest_signals
    context = build_signal_context(latest_signals[0].id, sample_workspace)
    assert context.news

    active_spec_path = sample_workspace / "strategy_specs" / "active" / f"{spec.name}.yaml"
    copyfile(spec_path, active_spec_path)
    raw = yaml.safe_load(active_spec_path.read_text(encoding="utf-8"))
    raw["lifecycle"] = "active"
    raw["execution"]["mode"] = "paper_auto"
    raw["execution"]["broker"] = "alpaca_paper"
    active_spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active_spec = load_strategy_spec(active_spec_path)

    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")

    def fake_submit(client, signal_arg, qty, client_order_id):
        return SimpleNamespace(id="paper_order_1", status="accepted")

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(equity="10000")

    monkeypatch.setattr(alpaca_paper, "_submit_market_order", fake_submit)
    order = alpaca_paper.submit_paper_order(
        latest_signals[0], active_spec, sample_workspace, client=MockClient()
    )
    assert order.paper
    assert order.client_order_id == f"oc-{latest_signals[0].id}"


def test_chinese_memory_storage_prompt_optimizes_and_scans(sample_workspace: Path) -> None:
    idea = "针对最近的内存存储的动能做一个日内的策略，先手动实盘，模拟盘可以自动交易"
    spec_path = draft_strategy_from_idea(idea, sample_workspace)
    spec = load_strategy_spec(spec_path)
    assert spec.name == "memory_storage_momentum_15m"
    assert spec.primary_symbol == "MU"
    assert "market.memory_storage_sample" in spec.required_capabilities

    result = optimize_strategy(spec_path, sample_workspace, min_return_pct=1.0, min_signals=1)
    assert result.best_artifacts.run.total_return_pct >= 1.0
    assert result.best_artifacts.run.signals >= 1
    assert result.report_path.exists()

    fetch_capability_events("sec", sample_workspace, ["MU"], offline=True)
    fetch_capability_events("alpha_vantage", sample_workspace, ["MU"], offline=True)
    fetch_capability_events("gdelt", sample_workspace, ["MU"], offline=True)
    fetch_capability_events("fred", sample_workspace, None, offline=True)
    latest_signals = run_scan(result.best_spec_path, root=sample_workspace)
    context = build_signal_context(latest_signals[0].id, sample_workspace)
    assert context.events
    assert context.news
    assert context.macro
