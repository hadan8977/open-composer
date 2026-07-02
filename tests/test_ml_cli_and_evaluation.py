from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.ml_backend.evaluation import _comparison_status
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
    assert payload["oos_start_index"] > 0
    assert payload["evaluation_window_bars"] == payload["ml"]["bars"]
    assert payload["evaluation_window_bars"] == payload["baseline"]["bars"]
    assert payload["oos_prediction_count"] > 20
    assert payload["ml"]["signals"] >= 1
    assert payload["baseline"]["signals"] >= 1


def test_strategy_train_cli_rejects_non_model_spec(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.chdir(sample_workspace)
    spec_path = _write_syn_ml_spec(sample_workspace, model=False)
    runner = CliRunner()

    result = runner.invoke(app, ["strategy", "train", str(spec_path)])

    assert result.exit_code != 0
    assert "requires StrategySpec.model" in result.output


def test_strategy_explain_cli_writes_structured_advisory_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(sample_workspace)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec_path = _write_syn_ml_spec(sample_workspace)
    runner = CliRunner()

    result = runner.invoke(app, ["strategy", "explain", str(spec_path), "--llm", "--top-n", "3"])

    assert result.exit_code == 0, result.output
    out_dir = sample_workspace / "reports" / "research" / "ml" / "syn_daily_ml_probe"
    payload = json.loads((out_dir / "explain.json").read_text(encoding="utf-8"))
    assert payload["llm_status"] == "missing_api_key_fallback_to_deterministic"
    assert payload["promotion_impact"] == "none_advisory_only"
    assert payload["paper_order_impact"] == "none"
    assert len(payload["feature_importance"]) <= 3
    trace_rows = [
        json.loads(line)
        for line in (out_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert trace_rows[-1]["operation"] == "strategy_explain"
    assert trace_rows[-1]["input_hash"]
    assert trace_rows[-1]["prompt_hash"]


def test_strategy_explain_cli_rejects_non_model_spec(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.chdir(sample_workspace)
    spec_path = _write_syn_ml_spec(sample_workspace, model=False)
    runner = CliRunner()

    result = runner.invoke(app, ["strategy", "explain", str(spec_path)])

    assert result.exit_code != 0
    assert "requires StrategySpec.model" in result.output


def test_ml_comparison_status_handles_negative_baseline_sharpe() -> None:
    status, reason = _comparison_status(-0.20, -0.40)
    assert status == "ok"
    assert "beats baseline" in reason

    status, reason = _comparison_status(-0.45, -0.40)
    assert status == "warning"
    assert "within" in reason

    status, reason = _comparison_status(-0.70, -0.40)
    assert status == "blocked"
    assert "trails baseline" in reason
