from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.research.pdr_ml_gate_evaluation import (
    _acceptance_gate,
    evaluate_pdr_router_ml_gate,
)
from tests.test_pdr_router_parity import ROOT

SPEC_PATH = ROOT / "strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter1.yaml"
PREDICTION_PATH = (
    ROOT
    / "reports/research/ml/nasdaq_tqqq_pdr_router_mlgate_iter1"
    / "pdr_mlgate_oos_predictions_h10_t2_p70.json"
)


def _metrics(
    *,
    annualized: float = 35.0,
    sharpe: float = 1.2,
    maxdd: float = -35.0,
    total: float = 100.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        annualized_return_pct=annualized,
        sharpe_ratio=sharpe,
        max_drawdown_pct=maxdd,
        total_return_pct=total,
    )


def test_pdr_ml_gate_acceptance_requires_all_six_gates() -> None:
    baseline = _metrics(maxdd=-40.0)
    gated = _metrics(maxdd=-35.0)
    walk_forward = [{"gated_beats_tqqq": True} for _ in range(4)] + [
        {"gated_beats_tqqq": False} for _ in range(2)
    ]
    crisis = [{"name": name, "gated_beats_tqqq": True} for name in ("a", "b", "c")]
    current_oos = {
        "gated": {
            "sharpe_ratio": 1.8,
            "total_return_pct": 180.0,
            "benchmark_buy_hold_return_pct": 100.0,
        }
    }

    accepted = _acceptance_gate(baseline, gated, walk_forward, crisis, current_oos)
    rejected = _acceptance_gate(
        baseline,
        _metrics(sharpe=1.0, maxdd=-35.0),
        walk_forward,
        crisis,
        current_oos,
    )

    assert accepted["ml_gate_beats_fixed_route"] is True
    assert rejected["ml_gate_beats_fixed_route"] is False
    assert rejected["failed_gates"] == ["full_window_sharpe_at_least_1_1"]


def test_pdr_ml_gate_evaluation_writes_acceptance_report_when_artifacts_exist() -> None:
    if not SPEC_PATH.exists() or not PREDICTION_PATH.exists():
        pytest.skip("local Step 7.R draft spec or R.1 prediction artifact is absent")

    payload = evaluate_pdr_router_ml_gate(
        SPEC_PATH,
        root=ROOT,
        data_source="longbridge",
        start="2012-01-03",
        end="2026-05-22",
        report_date="test",
    )

    assert payload["report_type"] == "pdr_router_ml_gate_eval"
    assert payload["search_space"]["candidate_count"] == 12
    assert "ml_gate_beats_fixed_route" in payload["acceptance_gate"]
    assert payload["pass_status"]["paper_ready_pass"] is False
    assert payload["attribution"]["non_hard_stress_state_or_weight_changes"] == 0
    assert Path(payload["artifact_paths"]["json"]).exists()
    assert Path(payload["artifact_paths"]["markdown"]).exists()
