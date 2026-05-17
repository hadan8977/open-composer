from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GateStatus = Literal["ok", "warning", "blocked"]


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: GateStatus
    message: str = ""
    evidence: object | None = None


class ResearchGateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_pass: bool = False
    research_pass: bool = False
    llm_contribution_pass: bool | None = None
    paper_ready_pass: bool = False
    status: GateStatus = "warning"
    blocked_checks: list[str] = Field(default_factory=list)
    warning_checks: list[str] = Field(default_factory=list)
    gates: list[GateResult] = Field(default_factory=list)


def summarize_gates(gates: list[GateResult]) -> ResearchGateSummary:
    blocked = [gate.name for gate in gates if gate.status == "blocked"]
    warnings = [gate.name for gate in gates if gate.status == "warning"]
    status: GateStatus = "blocked" if blocked else "warning" if warnings else "ok"
    return ResearchGateSummary(
        workflow_pass=status != "blocked",
        research_pass=status == "ok",
        paper_ready_pass=status == "ok",
        status=status,
        blocked_checks=blocked,
        warning_checks=warnings,
        gates=gates,
    )
