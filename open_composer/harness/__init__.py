"""Harness — runtime-enforced workflow gates for Open Composer strategies."""

from __future__ import annotations

from open_composer.harness.gates import GATE_REGISTRY, GateResult, gate, run_gate, run_gates
from open_composer.harness.runs import append_run, evidence_for, query_runs
from open_composer.harness.stages import STAGE_REQUIREMENTS, check_stage, gates_for_stage

__all__ = [
    "GATE_REGISTRY",
    "STAGE_REQUIREMENTS",
    "GateResult",
    "append_run",
    "check_stage",
    "evidence_for",
    "gate",
    "gates_for_stage",
    "query_runs",
    "run_gate",
    "run_gates",
]
