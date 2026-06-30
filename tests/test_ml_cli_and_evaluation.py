from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from tests.test_ml_backend_training import _write_syn_ml_spec


def test_strategy_train_cli_writes_ml_training_report(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(sample_workspace)
    spec_path = _write_syn_ml_spec(sample_workspace)
    runner = CliRunner()

    result = runner.invoke(app, ["strategy", "train", str(spec_path)])

    assert result.exit_code == 0, result.output
    payload_path = (
        sample_workspace / "reports" / "research" / "ml" / "syn_daily_ml_probe" / "training.json"
    )
    assert payload_path.exists()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["fold_count"] > 1
    assert payload["prediction_count"] > 20


def test_strategy_backtest_walk_forward_cli_writes_comparison(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(sample_workspace)
    spec_path = _write_syn_ml_spec(sample_workspace)
    runner = CliRunner()

    result = runner.invoke(app, ["strategy", "backtest-walk-forward", str(spec_path)])

    assert result.exit_code == 0, result.output
    payload_path = (
        sample_workspace
        / "reports"
        / "research"
        / "ml"
        / "syn_daily_ml_probe"
        / "ml_vs_baseline.json"
    )
    assert payload_path.exists()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["status"] in {"ok", "warning", "blocked"}
    assert payload["ml"]["signals"] >= 1
    assert payload["baseline"]["signals"] >= 1


def test_strategy_train_cli_rejects_non_model_spec(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.chdir(sample_workspace)
    spec_path = _write_syn_ml_spec(sample_workspace, model=False)
    runner = CliRunner()

    result = runner.invoke(app, ["strategy", "train", str(spec_path)])

    assert result.exit_code != 0
    assert "requires StrategySpec.model" in result.output
