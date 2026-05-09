from __future__ import annotations

from pathlib import Path

from open_composer.compiler.spec_to_pine import compile_pine, compile_pine_strategy
from open_composer.engines.backtest_engine import run_backtest
from open_composer.engines.scanner_engine import run_scan
from open_composer.models.strategy_spec import load_strategy_spec


def test_backtest_writes_report_and_signal_log(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    artifacts = run_backtest(spec_path, root=sample_workspace)
    assert artifacts.run.bars > 0
    assert artifacts.run.report_path is not None
    assert artifacts.run.signal_log_path is not None
    assert Path(artifacts.run.report_path).exists()
    assert Path(artifacts.run.signal_log_path).exists()
    assert artifacts.run.assumptions[0] == "Signals are confirmed on bar close."


def test_scan_writes_latest_signal_log(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    signals = run_scan(spec_path, root=sample_workspace)
    assert isinstance(signals, list)
    assert list((sample_workspace / "signal_logs").glob("scan-*.jsonl"))


def test_pine_export_contains_alerts_and_confirmed_bar(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    path = compile_pine(spec_path, root=sample_workspace)
    text = path.read_text(encoding="utf-8")
    assert "//@version=6" in text
    assert "alertcondition" in text
    assert "barstate.isconfirmed" in text
    assert (sample_workspace / "reports" / "parity" / "qqq_pullback_15m-checklist.md").exists()


def test_pine_strategy_export_uses_strategy_tester_orders(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    path = compile_pine_strategy(spec_path, root=sample_workspace)
    text = path.read_text(encoding="utf-8")
    assert path.name == "qqq_pullback_15m.strategy.pine"
    assert "//@version=6" in text
    assert 'strategy("Qqq Pullback 15M Strategy"' in text
    assert 'strategy.entry("Long", strategy.long' in text
    assert 'strategy.close("Long"' in text
    assert "barstate.isconfirmed" in text
    assert "tradesToday < 3" in text
    assert "strategy.percent_of_equity" in text
    assert (
        sample_workspace / "reports" / "parity" / "qqq_pullback_15m-strategy-checklist.md"
    ).exists()


def test_pine_export_preserves_any_semantics(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    spec = load_strategy_spec(spec_path)
    from open_composer.compiler.spec_to_pine import render_pine

    text = render_pine(spec)
    assert "(ta.rsi(close, 3) > 82) or (close < ta.ema(close, 5))" in text
