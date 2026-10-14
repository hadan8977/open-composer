from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.cli import app
from open_composer.engines.backtest_engine import backtest_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.cost_sensitivity import run_cost_grid


def test_cost_config_defaults_preserve_backtest_result(sample_workspace: Path) -> None:
    spec = load_strategy_spec(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )
    frame = load_ohlcv_for_spec(spec, sample_workspace)
    baseline = backtest_frame(spec, frame, root=sample_workspace, run_id_value="baseline")
    raw = spec.model_dump(mode="json")
    raw["costs"] = {
        **raw["costs"],
        "impact_model": "linear",
        "impact_eta": 0.0,
        "impact_gamma": 0.0,
    }
    explicit = StrategySpec.model_validate(raw)
    candidate = backtest_frame(explicit, frame, root=sample_workspace, run_id_value="explicit")

    assert candidate.run.total_return_pct == pytest.approx(baseline.run.total_return_pct)
    assert candidate.run.sharpe_ratio == pytest.approx(baseline.run.sharpe_ratio)


def test_cost_grid_writes_json_and_markdown(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    report = run_cost_grid(
        spec_path,
        commission_grid=[0.0],
        slippage_grid=[0.0, 5.0],
        impact_models=["linear", "sqrt"],
        root=sample_workspace,
    )

    assert len(report.results) == 4
    assert report.results[0].impact_model == "linear"
    assert (sample_workspace / "reports" / "cost_grid" / "fixture_pullback_15m.json").exists()
    assert (sample_workspace / "reports" / "cost_grid" / "fixture_pullback_15m.md").exists()


def test_cost_grid_cli_command(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "cost-grid",
            str(sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"),
            "--commission",
            "0",
            "--slippage",
            "0",
            "--impact-model",
            "linear",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Cost Grid" in result.output
    payload = json.loads(
        (sample_workspace / "reports" / "cost_grid" / "fixture_pullback_15m.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(payload["results"]) == 1
    assert payload["results"][0]["impact_model"] == "linear"


def test_registered_cost_grid_preserves_native_diagnostics_and_preflights_before_data(
    sample_workspace: Path, monkeypatch
) -> None:
    from open_composer.research.iteration_dossier import require_iteration_execution_gate
    from tests.test_iteration_dossier import (
        test_lightweight_exemption_reaches_ok_through_the_real_execution_gate,
    )

    test_lightweight_exemption_reaches_ok_through_the_real_execution_gate(sample_workspace)
    path = sample_workspace / "strategy_specs/drafts/step10_lightweight_fixture_r1.yaml"
    calls = []
    monkeypatch.setattr(
        "open_composer.research.cost_sensitivity.load_ohlcv_for_spec",
        lambda *args: calls.append("data") or object(),
    )

    def no_calculation(spec, frame, *, root, native_control, **kwargs):
        result = require_iteration_execution_gate(spec, root, native_control=native_control)
        assert result.info["native_execution_control"]["promotion_eligible"] is False
        calls.append(native_control.purpose)
        return SimpleNamespace(
            run=SimpleNamespace(total_return_pct=0.0, sharpe_ratio=0.0, signals=0, trades=0)
        )

    monkeypatch.setattr("open_composer.research.cost_sensitivity.backtest_frame", no_calculation)
    report = run_cost_grid(
        path,
        commission_grid=[0.02],
        slippage_grid=[7.5],
        impact_models=["sqrt", "almgren_chriss"],
        root=sample_workspace,
    )
    assert calls == ["data", "cost_grid", "cost_grid"]
    assert report.selectable_candidate is False and report.promotion_eligible is False
    calls.clear()
    with pytest.raises(ValueError):
        run_cost_grid(
            path,
            commission_grid=[0.02],
            slippage_grid=[7.5],
            impact_models=["linear", "invalid_model"],
            root=sample_workspace,
        )
    assert calls == []
