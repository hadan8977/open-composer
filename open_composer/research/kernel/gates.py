from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

GateStatus = Literal["ok", "warning", "blocked"]


@dataclass(frozen=True)
class GateResult:
    name: str
    status: GateStatus
    message: str = ""
    evidence: object | None = None
    details: dict[str, object] = field(default_factory=dict)

    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return asdict(self)


def summarize_gates(gates: list[GateResult]) -> dict[str, object]:
    blocked = [gate.name for gate in gates if gate.status == "blocked"]
    warnings = [gate.name for gate in gates if gate.status == "warning"]
    status: GateStatus = "blocked" if blocked else "warning" if warnings else "ok"
    return {
        "workflow_pass": status != "blocked",
        "research_pass": status == "ok",
        "llm_contribution_pass": None,
        "paper_ready_pass": status == "ok",
        "status": status,
        "blocked_checks": blocked,
        "warning_checks": warnings,
        "gates": [gate.model_dump(mode="json") for gate in gates],
    }
