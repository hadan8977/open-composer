from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from open_composer.engines.backtest_engine import run_backtest
from open_composer.models.options import OptionOverlaySpec, OptionsOverlaySpec, OptionsSpec
from open_composer.research.options_overlay import (
    backtest_option_overlay,
    optimize_option_overlays,
)
from open_composer.research.options_research import (
    build_options_overlay_report,
    build_options_research_report,
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


def test_options_overlay_report_is_observation_only(sample_workspace: Path) -> None:
    overlay_path = sample_workspace / "strategy_specs" / "options" / "qqq_put_overlay.yaml"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay = OptionsOverlaySpec(
        name="qqq_put_overlay",
        base_strategy="strategy_specs/active/qqq_router.yaml",
        overlay_type="protective_put",
        delta_target=-0.25,
        max_premium_pct=1.0,
    )
    overlay_path.write_text(yaml.safe_dump(overlay.model_dump(mode="json")), encoding="utf-8")

    result = build_options_overlay_report(overlay_path, sample_workspace)

    assert result.execution_substate == "observation_only"
    assert result.paper_ready_pass is False
    payload = yaml.safe_load(result.json_path.read_text(encoding="utf-8"))
    assert payload["required_artifacts"] == [
        "options_chain_source_cards",
        "greeks_profile",
        "roll_schedule",
        "iv_stress_report",
        "overlay_cost_report",
        "assignment_risk_note",
    ]


def test_options_primary_report_is_observation_only(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "options" / "spx_put_spread.yaml"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec = OptionsSpec(
        name="spx_put_spread",
        underlying="SPX",
        strategy_type="put_spread",
        expiry_target="weekly",
        delta_target_long=-0.30,
        delta_target_short=-0.15,
        max_position_pct=0.05,
    )
    spec_path.write_text(yaml.safe_dump(spec.model_dump(mode="json")), encoding="utf-8")

    result = build_options_research_report(spec_path, sample_workspace)

    assert result.execution_substate == "observation_only"
    assert result.paper_ready_pass is False
    payload = yaml.safe_load(result.json_path.read_text(encoding="utf-8"))
    assert payload["required_artifacts"] == [
        "options_chain_source_cards",
        "greeks_profile",
        "contract_selection_log",
        "expiry_ladder",
        "iv_stress_report",
        "assignment_risk_note",
    ]
