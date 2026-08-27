from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.kernel import GateResult
from open_composer.research.promotion import _build_pass_summary, build_promotion_report
from tests.test_ml_backend_training import _write_syn_ml_spec


@pytest.mark.slow
def test_promotion_report_adds_ml_baseline_gate(
    sample_workspace: Path,
    preregister_iteration_dossier,
) -> None:
    spec_path = _write_syn_ml_spec(sample_workspace)
    preregister_iteration_dossier(spec_path, candidate_count=1)

    result = build_promotion_report(
        spec_path,
        sample_workspace,
        walk_forward_folds=1,
        cost_slippage_bps=[5],
    )

    gate = next(item for item in result.checks if item.name == "ml_beats_linear_baseline")
    overfit_gate = next(item for item in result.checks if item.name == "ml_overfit_risk")
    assert gate.status in {"ok", "warning", "blocked"}
    assert overfit_gate.status in {"ok", "warning", "blocked"}
    comparison_path = (
        sample_workspace
        / "reports"
        / "research"
        / "ml"
        / "syn_daily_ml_probe"
        / "ml_vs_baseline.json"
    )
    assert comparison_path.exists()
    payload = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert payload["evaluation_window_bars"] == payload["ml"]["bars"]
    assert payload["evaluation_window_bars"] == payload["baseline"]["bars"]
    assert payload["ml"]["signals"] >= 1
    assert payload["baseline"]["signals"] >= 1
    overfit_path = (
        sample_workspace
        / "reports"
        / "research"
        / "ml"
        / "syn_daily_ml_probe"
        / "ml-overfit-risk.json"
    )
    assert overfit_path.exists()


@pytest.mark.slow
def test_ml_promotion_uses_stitched_oos_and_training_folds(
    sample_workspace: Path,
    preregister_iteration_dossier,
) -> None:
    spec_path = _write_syn_ml_spec(sample_workspace)
    preregister_iteration_dossier(spec_path, candidate_count=1)

    result = build_promotion_report(
        spec_path,
        sample_workspace,
        walk_forward_folds=1,
        cost_slippage_bps=[5],
    )

    in_sample = next(item for item in result.checks if item.name == "in_sample")
    oos = next(item for item in result.checks if item.name == "out_of_sample")
    walk_forward = next(item for item in result.checks if item.name == "walk_forward")

    assert in_sample.details["evidence_kind"] == "ml_purged_stitched_full_window"
    assert oos.status in {"ok", "warning"}
    assert oos.details["evidence_kind"] == "ml_purged_stitched_oos"
    assert oos.details["prediction_count"] > 0
    assert oos.details["fold_count"] > 0
    assert walk_forward.status in {"ok", "warning"}
    assert walk_forward.details["validation_policy"] == "ml_purged_embargo_walk_forward"
    assert walk_forward.details["purged"] is True
    assert walk_forward.details["embargo_bars"] == 5
    assert walk_forward.details["fold_count"] > 0
    assert walk_forward.details["folds"]


@pytest.mark.slow
def test_ml_promotion_blocks_without_training_folds(
    sample_workspace: Path,
    preregister_iteration_dossier,
) -> None:
    spec_path = _write_syn_ml_spec(sample_workspace)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["model"]["training"]["window_bars"] = 10_000
    raw["model"]["training"]["test_window_bars"] = 5_000
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    preregister_iteration_dossier(spec_path, candidate_count=1)

    result = build_promotion_report(
        spec_path,
        sample_workspace,
        walk_forward_folds=1,
        cost_slippage_bps=[5],
    )

    oos = next(item for item in result.checks if item.name == "out_of_sample")
    walk_forward = next(item for item in result.checks if item.name == "walk_forward")

    assert oos.status == "blocked"
    assert oos.details["fold_count"] == 0
    assert oos.details["prediction_count"] == 0
    assert walk_forward.status == "blocked"
    assert walk_forward.details["fold_count"] == 0
    assert walk_forward.details["prediction_count"] == 0


@pytest.mark.slow
def test_non_ml_promotion_keeps_generic_oos_and_walk_forward(
    sample_workspace: Path,
    preregister_iteration_dossier,
) -> None:
    spec_path = _write_syn_ml_spec(sample_workspace, model=False)
    preregister_iteration_dossier(spec_path, candidate_count=1)

    result = build_promotion_report(
        spec_path,
        sample_workspace,
        walk_forward_folds=1,
        cost_slippage_bps=[5],
    )

    in_sample = next(item for item in result.checks if item.name == "in_sample")
    oos = next(item for item in result.checks if item.name == "out_of_sample")
    walk_forward = next(item for item in result.checks if item.name == "walk_forward")

    assert "evidence_kind" not in in_sample.details
    assert "evidence_kind" not in oos.details
    assert walk_forward.details["validation_policy"] == "sequential_walk_forward"


def test_ml_baseline_gate_blocks_research_pass(sample_workspace: Path) -> None:
    spec_path = _write_syn_ml_spec(sample_workspace)
    spec = load_strategy_spec(spec_path)

    summary = _build_pass_summary(
        spec,
        ready=False,
        checks=[
            GateResult("in_sample", "ok", "ok"),
            GateResult("out_of_sample", "ok", "ok"),
            GateResult("walk_forward", "ok", "ok"),
            GateResult("ml_beats_linear_baseline", "blocked", "ML did not beat baseline"),
        ],
        root=sample_workspace,
    )

    assert summary["research_pass"] == "fail"
    assert "ml_beats_linear_baseline" in summary["research_reason"]
