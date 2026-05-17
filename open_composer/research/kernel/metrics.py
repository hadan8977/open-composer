from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MetricSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["ok", "warning", "blocked", "missing"] = "missing"
    metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    path: str | None = None


class EvaluationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    status: Literal["ok", "warning", "blocked"] = "warning"
    performance: MetricSummary = Field(default_factory=lambda: MetricSummary(name="performance"))
    factor: MetricSummary = Field(default_factory=lambda: MetricSummary(name="factor"))
    execution: MetricSummary = Field(default_factory=lambda: MetricSummary(name="execution"))
    data: MetricSummary = Field(default_factory=lambda: MetricSummary(name="data"))
    alternative_data: MetricSummary = Field(
        default_factory=lambda: MetricSummary(name="alternative_data")
    )
    promotion: MetricSummary = Field(default_factory=lambda: MetricSummary(name="promotion"))
    paper_readiness: MetricSummary = Field(
        default_factory=lambda: MetricSummary(name="paper_readiness")
    )
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
