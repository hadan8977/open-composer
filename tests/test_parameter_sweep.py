from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.parameter_sweep import parse_sweep_parameters, run_parameter_sweep


def test_parameter_sweep_runs_grid_and_writes_ranked_reports(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    parameters = parse_sweep_parameters(
        [
            "risk.stop_loss_pct=0.8,1.2",
            "costs.slippage_bps=0,5",
        ]
    )

    result = run_parameter_sweep(
        spec_path,
        parameters,
        sample_workspace,
        min_signals=1,
        max_candidates=4,
        top_n=4,
        write_top=2,
    )

    assert len(result.candidates) == 4
    assert [candidate.rank for candidate in result.candidates] == [1, 2, 3, 4]
    assert result.report_path.exists()
    assert result.json_path.exists()
    assert len(result.written_specs) == 2
    assert all(path.exists() for path in result.written_specs)

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["candidate_count"] == 4
    assert payload["parameters"] == {
        "costs.slippage_bps": ["0", "5"],
        "risk.stop_loss_pct": ["0.8", "1.2"],
    }
    assert payload["candidates"][0]["rank"] == 1
    assert payload["candidates"][0]["metrics"]["signals"] >= 1
    assert "buy_hold_return_pct" in payload["candidates"][0]["metrics"]
    assert "alpha_vs_buy_hold_pct" in payload["candidates"][0]["metrics"]
    assert "quality_flags" in payload["candidates"][0]
    assert payload["trial_count"] == 4
    assert payload["search_space"]["family"] == "parameter_sweep"
    assert payload["stability"]["trial_count"] == 4
    assert "neighbor_success_rate" in payload["stability"]
    assert payload["stability"]["rank_correlation_train_oos"] is None
    assert payload["stability"]["top_decile_oos_retention"] is None
    assert payload["dsr_inputs"]["trial_count"] == 4
    assert payload["selection_bias_note"]
    assert payload["research_manifest"]["spec_hash"]
    assert payload["trial_ledger"]["trial_count"] == 4
    assert (
        payload["trial_ledger"]["trials"][0]["candidate_name"]
        == payload["candidates"][0]["strategy_name"]
    )
    assert payload["research_run_index_record"]["kind"] == "parameter_sweep"
    assert payload["research_run_index_record"]["trial_count"] == 4
    index_path = sample_workspace / "reports" / "research" / "index.jsonl"
    assert index_path.exists()
    index_rows = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines()]
    assert index_rows[0]["kind"] == "parameter_sweep"
    assert "stability" in payload["candidates"][0]
    assert "in-sample research evidence" in result.report_path.read_text(encoding="utf-8")
    assert "Buy/Hold" in result.report_path.read_text(encoding="utf-8")
    assert "## Stability" in result.report_path.read_text(encoding="utf-8")

    best_spec = yaml.safe_load(result.written_specs[0].read_text(encoding="utf-8"))
    assert best_spec["lifecycle"] == "draft"
    assert best_spec["execution"]["mode"] == "manual_signal"
    assert best_spec["execution"]["broker"] == "none"
    assert best_spec["notes"]["parameter_sweep"]["params"]


def test_parameter_sweep_can_vary_expression_paths(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    parameters = parse_sweep_parameters(
        [
            "entry.all.0=close > ema(close, 5)|close > ema(close, 8)",
        ]
    )

    result = run_parameter_sweep(
        spec_path,
        parameters,
        sample_workspace,
        max_candidates=2,
        write_top=0,
    )

    expressions = {candidate.spec.entry.all[0] for candidate in result.candidates}
    assert expressions == {"close > ema(close, 5)", "close > ema(close, 8)"}
    assert not result.written_specs


def test_parameter_sweep_rejects_execution_paths(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    parameters = parse_sweep_parameters(["execution.mode=paper_auto,manual_signal"])

    with pytest.raises(ValueError, match="unsupported sweep path"):
        run_parameter_sweep(spec_path, parameters, sample_workspace)


def test_parameter_sweep_enforces_candidate_cap(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    parameters = parse_sweep_parameters(
        [
            "risk.stop_loss_pct=0.8,1.0,1.2",
            "costs.slippage_bps=0,5",
        ]
    )

    with pytest.raises(ValueError, match="would create 6 candidates"):
        run_parameter_sweep(spec_path, parameters, sample_workspace, max_candidates=5)


def test_parameter_sweep_cli_writes_reports(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "strategy",
            "parameter-sweep",
            str(sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"),
            "--param",
            "risk.take_profit_pct=1.5,2.0",
            "--param",
            "costs.commission_pct=0,0.01",
            "--max-candidates",
            "4",
            "--write-top",
            "1",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "parameter sweep complete" in result.output
    assert (
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-parameter-sweep.md"
    ).exists()
    assert (
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-parameter-sweep.json"
    ).exists()
    payload = json.loads(
        (
            sample_workspace / "reports" / "research" / "fixture_pullback_15m-parameter-sweep.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["candidate_set"]["family"] == "parameter_sweep"
    assert payload["candidate_set"]["candidate_count"] == 4
    assert payload["selection_decision"]["status"] == "warning"
    assert "selection_is_in_sample_only" in payload["selection_decision"]["promotion_blockers"]
