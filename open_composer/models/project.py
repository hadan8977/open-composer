from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProjectState = Literal[
    "idea",
    "draft",
    "researching",
    "iterating",
    "candidate",
    "paper_review",
    "active_paper",
    "retired",
    "blocked",
]
ProjectEvidenceStatus = Literal["ok", "warning", "blocked", "not_applicable", "unknown"]
ProjectAction = Literal[
    "continue_iteration",
    "stop_iteration",
    "archive",
    "request_paper_review",
]
ProjectIterationMode = Literal["auto_continue_until_stop", "notify_and_wait"]
ProjectPaperStatus = Literal["not_requested", "review_requested", "active", "blocked", "disabled"]
ProjectRunStatus = Literal["ok", "warning", "blocked", "failed"]


class ProjectGateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_pass: bool | None = None
    research_pass: bool | None = None
    llm_contribution_pass: bool | None = None
    paper_ready_pass: bool | None = None
    status: Literal["ok", "warning", "blocked", "unknown"] = "unknown"
    blocked_checks: list[str] = Field(default_factory=list)
    warning_checks: list[str] = Field(default_factory=list)


class ProjectEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProjectEvidenceStatus = "unknown"
    summary: str = "No evidence has been linked yet."
    artifact_path: str | None = None
    blockers: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None

    @field_validator("artifact_path")
    @classmethod
    def normalize_artifact_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ProjectEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_quality: ProjectEvidenceItem = Field(default_factory=ProjectEvidenceItem)
    execution_reality: ProjectEvidenceItem = Field(default_factory=ProjectEvidenceItem)
    alt_llm_evidence: ProjectEvidenceItem = Field(
        default_factory=lambda: ProjectEvidenceItem(
            status="unknown",
            summary="Alternative-data and LLM contribution evidence has not been assessed.",
        )
    )


class ProjectIteration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_rounds: int = Field(default=5, ge=1, le=50)
    current_round: int = Field(default=0, ge=0)
    mode: ProjectIterationMode = "auto_continue_until_stop"
    stop_conditions: list[str] = Field(
        default_factory=lambda: [
            "target_met",
            "max_rounds_reached",
            "no_material_improvement",
            "overfit_risk_high",
            "data_or_execution_blocked",
            "worker_failed",
        ]
    )
    stop_reason: str | None = None
    user_requested_stop: bool = False


class ProjectPaperState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProjectPaperStatus = "not_requested"
    readiness_report_path: str | None = None
    activated_at: datetime | None = None
    last_event_at: datetime | None = None


class StrategyProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    project_id: str
    name: str
    state: ProjectState = "idea"
    thesis: str = ""
    current_spec_path: str | None = None
    latest_run_path: str | None = None
    gate_summary: ProjectGateSummary = Field(default_factory=ProjectGateSummary)
    evidence: ProjectEvidence = Field(default_factory=ProjectEvidence)
    blockers: list[str] = Field(default_factory=list)
    next_action: str = "create_or_link_strategy_spec"
    iteration: ProjectIteration = Field(default_factory=ProjectIteration)
    paper: ProjectPaperState = Field(default_factory=ProjectPaperState)
    archived: bool = False
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("project_id is required")
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
        if any(char not in allowed for char in normalized):
            raise ValueError("project_id must be lowercase slug text")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("project name is required")
        return normalized


class StrategyProjectRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    round: int = Field(ge=1)
    status: ProjectRunStatus = "warning"
    task_type: str = "strategy_optimization"
    worker_provider: str = "agent_request"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    changed_paths: list[str] = Field(default_factory=list)
    worker_claim: dict[str, Any] = Field(default_factory=dict)
    verified: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    next_action: str = ""


class StrategyProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    thesis: str
    idea: str = ""
    template_id: str | None = None
    requested_by: str = "dashboard"
    current_spec_path: str | None = None
    max_rounds: int = Field(default=5, ge=1, le=50)
    use_llm: bool = False
    tags: list[str] = Field(default_factory=list)
