from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ResearchMode = Literal["playground", "audited"]
ExperimentStatus = Literal["running", "ok", "warning", "blocked", "failed"]
TrialDecisionStatus = Literal["kept", "pruned", "rejected", "failed"]


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    kind: str
    sha256: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    producer: str = ""


class ExperimentTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trial_id: str
    run_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    decision: TrialDecisionStatus = "kept"
    decision_reason: str = ""


class ExperimentRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    name: str
    research_mode: ResearchMode = "audited"
    kind: str
    strategy_name: str
    source_spec_path: str | None = None
    spec_hash: str | None = None
    dataset_hash: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    status: ExperimentStatus = "running"
    gate_status: str = "warning"
    params: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    parent_run_id: str | None = None
    trials: list[ExperimentTrial] = Field(default_factory=list)
    backfilled: bool = False
