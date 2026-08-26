from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from open_composer.compiler.spec_to_pine import compile_pine, compile_pine_strategy
from open_composer.engines.backtest_engine import backtest_frame, run_backtest
from open_composer.engines.scanner_engine import run_scan
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec


def test_backtest_writes_report_and_signal_log(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    artifacts = run_backtest(spec_path, root=sample_workspace)
    assert artifacts.run.bars > 0
    assert artifacts.run.report_path is not None
    assert artifacts.run.signal_log_path is not None
    assert Path(artifacts.run.report_path).exists()
    assert Path(artifacts.run.signal_log_path).exists()
    assert artifacts.run.assumptions[0] == "Signals are confirmed on bar close."
    assert artifacts.run.data_sanity is not None
    assert artifacts.run.data_sanity.status == "warning"
    assert artifacts.run.data_sanity.evidence_level == "E0_sample_smoke"
    assert artifacts.run.buy_hold_return_pct is not None
    assert artifacts.run.alpha_vs_buy_hold_pct is not None
    assert artifacts.run.annualized_return_pct is not None
    assert artifacts.run.sharpe_ratio is not None
    assert artifacts.run.annualized_volatility_pct is not None
    assert artifacts.run.max_drawdown_pct is not None
    assert artifacts.run.execution_reality is not None
    report_text = Path(artifacts.run.report_path).read_text(encoding="utf-8")
    assert "## Data Sanity" in report_text
    assert "## Execution Reality" in report_text
    assert "- Evidence level: `E0_sample_smoke`" in report_text
    assert "sample data is workflow smoke-test evidence only" in report_text
    assert "- Buy and hold return:" in report_text
    assert "- Alpha vs buy and hold:" in report_text
    assert "- Annualized return:" in report_text
    assert "- Sharpe ratio:" in report_text
    assert "- Max drawdown:" in report_text
    assert "- Sortino ratio:" in report_text
    assert "- Max bar participation:" in report_text


def test_backtest_passes_refresh_data_to_adapter(
    sample_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    observed: dict[str, bool] = {}

    def fake_load_ohlcv_for_spec(_spec, _root, refresh: bool = False):  # noqa: ANN001
        observed["refresh"] = refresh
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC"),
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 104.0, 105.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [100.0, 101.0, 102.0, 103.0, 104.0],
                "volume": [1_000_000] * 5,
            }
        )

    monkeypatch.setattr(
        "open_composer.engines.backtest_engine.load_ohlcv_for_spec",
        fake_load_ohlcv_for_spec,
    )

    artifacts = run_backtest(spec_path, root=sample_workspace, refresh_data=True)

    assert observed["refresh"] is True
    assert artifacts.run.bars == 5


def test_backtest_models_commission_and_slippage(sample_workspace: Path) -> None:
    source_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    no_cost = run_backtest(source_path, root=sample_workspace)
    raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    raw["name"] = "fixture_pullback_15m_costed"
    raw["costs"] = {"commission_pct": 0.1, "slippage_bps": 5}
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m_costed.yaml"
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    costed = run_backtest(spec_path, root=sample_workspace)

    assert costed.run.total_fees > 0
    assert costed.run.end_equity < no_cost.run.end_equity
    assert any("Commission is 0.1% per fill." in item for item in costed.run.assumptions)
    assert any("Slippage is 5 bps per fill." in item for item in costed.run.assumptions)
    assert all(trade.entry_fee >= 0 and trade.exit_fee >= 0 for trade in costed.trades)
    assert costed.run.report_path is not None
    assert "- Total fees:" in Path(costed.run.report_path).read_text(encoding="utf-8")


def test_backtest_flags_execution_reality_for_low_liquidity() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC"),
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            "volume": [10] * 5,
        }
    )
    spec = StrategySpec.model_validate(
        {
            "name": "low_liquidity_test",
            "description": "Low liquidity execution reality fixture.",
            "timeframe": "daily",
            "universe": ["AAA"],
            "lifecycle": "draft",
            "entry": {"all": ["close > 0"], "any": []},
            "exit": {"all": [], "any": ["close > 0"]},
            "risk": {"max_position_weight": 1.0},
            "costs": {"commission_pct": 0.0, "slippage_bps": 0.0},
            "execution": {
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "data": {"source": "sample", "symbol": "AAA"},
        }
    )

    artifacts = backtest_frame(spec, frame)

    assert artifacts.run.execution_reality is not None
    assert artifacts.run.execution_reality.status == "blocked"
    assert artifacts.run.execution_reality.max_bar_participation_pct is not None
    assert any("block threshold" in item for item in artifacts.run.execution_reality.warnings)


def test_backtest_oos_warmup_can_trigger_first_evaluation_open_entry() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC"),
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            "volume": [1_000_000] * 5,
        }
    )
    spec = StrategySpec.model_validate(
        {
            "name": "warmup_entry_test",
            "description": "Warmup entry boundary test.",
            "timeframe": "daily",
            "universe": ["AAA"],
            "lifecycle": "draft",
            "entry": {"all": ["close > 0"], "any": []},
            "exit": {"all": [], "any": ["close < 0"]},
            "risk": {"max_position_weight": 1.0},
            "costs": {"commission_pct": 0.0, "slippage_bps": 0.0},
            "execution": {
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "data": {"source": "sample", "symbol": "AAA"},
        }
    )

    artifacts = backtest_frame(spec, frame, evaluation_start_index=2)

    assert artifacts.signals[0].timestamp == frame["timestamp"].iloc[1].to_pydatetime()
    assert artifacts.signals[0].action == "entry"
    assert artifacts.run.bars == 3
    assert artifacts.run.buy_hold_return_pct == pytest.approx(artifacts.run.total_return_pct)


def test_backtest_supports_short_only_direction() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC"),
            "open": [100.0, 100.0, 95.0, 90.0, 90.0],
            "high": [101.0, 101.0, 96.0, 91.0, 91.0],
            "low": [99.0, 99.0, 94.0, 89.0, 89.0],
            "close": [100.0, 100.0, 95.0, 90.0, 90.0],
            "volume": [1_000_000] * 5,
        }
    )
    spec = StrategySpec.model_validate(
        {
            "name": "short_only_test",
            "description": "Short-only reference semantics.",
            "timeframe": "daily",
            "universe": ["AAA"],
            "lifecycle": "draft",
            "position_direction": "short_only",
            "entry": {"all": ["close >= 100"], "any": []},
            "exit": {"all": [], "any": ["close <= 95"]},
            "risk": {"max_position_weight": 1.0},
            "costs": {"commission_pct": 0.0, "slippage_bps": 0.0},
            "execution": {
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "data": {"source": "sample", "symbol": "AAA"},
        }
    )

    artifacts = backtest_frame(spec, frame)

    assert [signal.side for signal in artifacts.signals] == ["sell", "buy"]
    assert artifacts.trades[0].direction == "short"
    assert artifacts.trades[0].pnl > 0
    assert artifacts.run.total_return_pct > 0
    assert any("Short-only backtest" in item for item in artifacts.run.assumptions)


def test_backtest_supports_long_short_direction_flips() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC"),
            "open": [100.0, 100.0, 100.0, 120.0, 115.0, 110.0],
            "high": [102.0, 111.0, 116.0, 121.0, 116.0, 111.0],
            "low": [99.0, 99.0, 99.0, 99.0, 94.0, 89.0],
            "close": [101.0, 110.0, 115.0, 100.0, 95.0, 90.0],
            "volume": [1_000_000] * 6,
        }
    )
    spec = StrategySpec.model_validate(
        {
            "name": "long_short_test",
            "description": "Long-short reference semantics.",
            "timeframe": "daily",
            "universe": ["AAA"],
            "lifecycle": "draft",
            "position_direction": "long_short",
            "entry": {"all": ["close >= 105"], "any": []},
            "exit": {"all": [], "any": ["close <= 100"]},
            "risk": {"max_trades_per_day": 2, "max_position_weight": 1.0},
            "costs": {"commission_pct": 0.0, "slippage_bps": 0.0},
            "execution": {
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "data": {"source": "sample", "symbol": "AAA"},
        }
    )

    artifacts = backtest_frame(spec, frame)

    assert [trade.direction for trade in artifacts.trades] == ["long"]
    assert [signal.side for signal in artifacts.signals] == ["buy", "sell", "sell"]
    assert artifacts.trades[0].pnl > 0
    assert artifacts.run.total_return_pct > 0
    assert any("Long-short backtest" in item for item in artifacts.run.assumptions)


def test_scan_writes_latest_signal_log(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    signals = run_scan(spec_path, root=sample_workspace)
    assert isinstance(signals, list)
    assert list((sample_workspace / "signal_logs").glob("scan-*.jsonl"))


def test_pine_export_contains_alerts_and_confirmed_bar(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    path = compile_pine(spec_path, root=sample_workspace)
    text = path.read_text(encoding="utf-8")
    assert "//@version=6" in text
    assert "alertcondition" in text
    assert "barstate.isconfirmed" in text
    assert (sample_workspace / "reports" / "parity" / "fixture_pullback_15m-checklist.md").exists()


def test_pine_strategy_export_uses_strategy_tester_orders(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    path = compile_pine_strategy(spec_path, root=sample_workspace)
    text = path.read_text(encoding="utf-8")
    assert path.name == "fixture_pullback_15m.strategy.pine"
    assert "//@version=6" in text
    assert 'strategy("Fixture Pullback 15M Strategy"' in text
    assert 'strategy.entry("Long", strategy.long' in text
    assert 'strategy.close("Long"' in text
    assert "barstate.isconfirmed" in text
    assert "tradesToday < 3" in text
    assert "strategy.percent_of_equity" in text
    assert (
        sample_workspace / "reports" / "parity" / "fixture_pullback_15m-strategy-checklist.md"
    ).exists()


def test_pine_strategy_export_uses_short_orders_for_short_specs(sample_workspace: Path) -> None:
    source_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    raw["name"] = "qqq_short_only"
    raw["position_direction"] = "short_only"
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_short_only.yaml"
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    path = compile_pine_strategy(spec_path, root=sample_workspace)
    text = path.read_text(encoding="utf-8")

    assert 'strategy.entry("Short", strategy.short' in text
    assert 'strategy.close("Short"' in text


def test_pine_strategy_export_uses_long_short_orders(sample_workspace: Path) -> None:
    source_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    raw["name"] = "qqq_long_short"
    raw["position_direction"] = "long_short"
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_long_short.yaml"
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    path = compile_pine_strategy(spec_path, root=sample_workspace)
    text = path.read_text(encoding="utf-8")

    assert 'strategy.entry("Long", strategy.long' in text
    assert 'strategy.entry("Short", strategy.short' in text
    assert 'strategy.close("Long"' in text
    assert 'strategy.close("Short"' in text


def test_pine_export_preserves_any_semantics(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    spec = load_strategy_spec(spec_path)
    from open_composer.compiler.spec_to_pine import render_pine

    text = render_pine(spec)
    assert "(ta.rsi(close, 3) > 82) or (close < ta.ema(close, 5))" in text
