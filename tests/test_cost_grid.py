from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.cli import app
from open_composer.engines.backtest_engine import backtest_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.cost_sensitivity import run_cost_grid


def test_cost_config_defaults_preserve_backtest_result(sample_workspace: Path) -> None:
    spec = load_strategy_spec(
        sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
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
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"

    report = run_cost_grid(
        spec_path,
        commission_grid=[0.0],
        slippage_grid=[0.0, 5.0],
        impact_models=["linear", "sqrt"],
        root=sample_workspace,
    )

    assert len(report.results) == 4
    assert report.results[0].impact_model == "linear"
    assert (sample_workspace / "reports" / "cost_grid" / "qqq_pullback_15m.json").exists()
    assert (sample_workspace / "reports" / "cost_grid" / "qqq_pullback_15m.md").exists()


def test_cost_grid_cli_command(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "cost-grid",
            str(sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"),
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
        (sample_workspace / "reports" / "cost_grid" / "qqq_pullback_15m.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(payload["results"]) == 1
    assert payload["results"][0]["impact_model"] == "linear"
