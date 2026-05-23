from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from open_composer.research.kernel.datamodel import ResearchDataModel


@dataclass(frozen=True)
class MetricSummary(ResearchDataModel):
    name: str
    status: Literal["ok", "warning", "blocked", "missing"] = "missing"
    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    path: str | None = None


@dataclass(frozen=True)
class EvaluationBundle(ResearchDataModel):
    strategy_name: str
    status: Literal["ok", "warning", "blocked"] = "warning"
    performance: MetricSummary = field(default_factory=lambda: MetricSummary(name="performance"))
    factor: MetricSummary = field(default_factory=lambda: MetricSummary(name="factor"))
    execution: MetricSummary = field(default_factory=lambda: MetricSummary(name="execution"))
    data: MetricSummary = field(default_factory=lambda: MetricSummary(name="data"))
    alternative_data: MetricSummary = field(
        default_factory=lambda: MetricSummary(name="alternative_data")
    )
    promotion: MetricSummary = field(default_factory=lambda: MetricSummary(name="promotion"))
    paper_readiness: MetricSummary = field(
        default_factory=lambda: MetricSummary(name="paper_readiness")
    )
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
