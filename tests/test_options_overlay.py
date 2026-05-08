from __future__ import annotations

from pathlib import Path

import pytest

from open_composer.engines.backtest_engine import run_backtest
from open_composer.models.options import OptionOverlaySpec
from open_composer.research.options_overlay import (
    backtest_option_overlay,
    optimize_option_overlays,
)


def test_option_overlay_backtest_uses_whole_contracts(sample_workspace: Path) -> None:
    equity_artifacts = run_backtest(
        sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
        root=sample_workspace,
    )
    overlay = OptionOverlaySpec(
        name="qqq_overlay_test",
        underlying_strategy="qqq_pullback_15m",
        symbol="QQQ",
        overlay_type="long_call",
        dte=30,
        long_moneyness_pct=0,
        implied_volatility=0.35,
        spread_pct=0.08,
        max_premium_weight=0.03,
    )

    run, trades = backtest_option_overlay(
        overlay,
        equity_artifacts.trades,
        underlying_total_return_pct=equity_artifacts.run.total_return_pct,
        underlying_trades=equity_artifacts.run.trades,
    )

    assert run.trades == len(trades)
    assert run.total_return_pct != 0
    assert run.underlying_total_return_pct == equity_artifacts.run.total_return_pct
    assert all(trade.contracts >= 1 for trade in trades)
    assert "Black-Scholes approximation" in " ".join(run.assumptions)


def test_options_optimizer_writes_specs_and_report(sample_workspace: Path) -> None:
    result = optimize_option_overlays(
        [sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"],
        sample_workspace,
    )

    assert result.report_path.exists()
    assert result.selected_spec_paths
    assert all(path.exists() for path in result.selected_spec_paths)
    assert "Underlying equity return" in result.report_path.read_text(encoding="utf-8")
    assert list((sample_workspace / "reports" / "options").glob("*.md"))


def test_option_overlay_spec_rejects_invalid_short_leg() -> None:
    with pytest.raises(ValueError):
        OptionOverlaySpec(
            name="bad_spread",
            underlying_strategy="qqq_pullback_15m",
            symbol="QQQ",
            overlay_type="debit_call_spread",
            dte=30,
            long_moneyness_pct=5,
            short_moneyness_pct=2,
            implied_volatility=0.35,
            spread_pct=0.08,
            max_premium_weight=0.03,
        )
