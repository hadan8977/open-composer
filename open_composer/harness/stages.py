"""Harness stage requirements — maps workflow stages to required gate names."""

from __future__ import annotations

from pathlib import Path

from open_composer.harness.gates import run_gates
from open_composer.research.kernel.gates import GateResult, GateStatus

STAGE_REQUIREMENTS: dict[str, list[str]] = {
    "draft": [
        "spec_validation",
        "expression_safety",
    ],
    "research": [
        "spec_validation",
        "expression_safety",
        "leakage_check",
        "research_capability_evaluation",
        "reference_backtest",
        "factor_lab",
        "alternative_data",
    ],
    "promotion": [
        "spec_validation",
        "expression_safety",
        "leakage_check",
        "research_capability_evaluation",
        "reference_backtest",
        "factor_lab",
        "alternative_data",
        "harness_artifacts",
        "promotion_report",
    ],
    "paper_ready": [
        "spec_validation",
        "expression_safety",
        "leakage_check",
        "capability_evaluation",
        "reference_backtest",
        "factor_lab",
        "alternative_data",
        "harness_artifacts",
        "promotion_report",
        "paper_readiness",
    ],
}


def gates_for_stage(stage: str) -> list[str]:
    """Return the gate names required for the given lifecycle stage."""
    if stage not in STAGE_REQUIREMENTS:
        available = ", ".join(sorted(STAGE_REQUIREMENTS))
        msg = f"Unknown stage {stage!r}. Available stages: {available}"
        raise ValueError(msg)
    return list(STAGE_REQUIREMENTS[stage])


def check_stage(
    stage: str,
    spec_path: Path,
    root: Path,
) -> tuple[GateStatus, list[GateResult]]:
    """Run all gates for a stage and return the aggregate status and gate results.

    Returns:
        (status, results) where status is "ok", "warning", or "blocked".
    """
    gate_names = gates_for_stage(stage)
    results = run_gates(gate_names, spec_path, root)
    blocked = [r for r in results if r.status == "blocked"]
    warnings = [r for r in results if r.status == "warning"]
    status: GateStatus = "blocked" if blocked else "warning" if warnings else "ok"
    return status, results
