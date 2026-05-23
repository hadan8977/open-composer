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
ProjectStepStatus = Literal["ok", "warning", "blocked", "failed", "skipped"]
QueueCommandKind = Literal[
    "continue",
    "advice",
    "stop",
    "llm_factor_eval",
    "materialize",
    "approve",
    "activate_manual",
    "activate_paper",
    "disable",
]
QueueCommandVia = Literal["dashboard", "cli", "api", "agent"]
TraceAgent = Literal["codex", "claude_code", "cli", "system", "dashboard"]


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
    gate_summary: dict[str, Any] = Field(default_factory=dict)
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


class ProjectStepEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_name: str
    status: ProjectStepStatus = "ok"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    blocked_items: list[str] = Field(default_factory=list)
    warning_items: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("step_name")
    @classmethod
    def validate_step_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("step_name is required")
        return normalized


class ProjectBlockerSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger: str = "blocked"
    failed_step: str = "unknown"
    root_blockers: list[str] = Field(default_factory=list)
    next_minimal_actions: list[str] = Field(default_factory=list)
    do_not_repeat: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StrategyProjectRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    round: int = Field(ge=1)
    status: ProjectRunStatus = "warning"
    task_type: str = "strategy_optimization"
    worker_provider: str = "project_queue"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    changed_paths: list[str] = Field(default_factory=list)
    step_events: list[ProjectStepEvent] = Field(default_factory=list)
    blocker_summary: ProjectBlockerSummary | None = None
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


class QueueCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    id: str
    from_actor: str = Field(default="user", alias="from")
    via: QueueCommandVia = "cli"
    kind: QueueCommandKind
    body: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    consumed_at: datetime | None = None

    @field_validator("id")
    @classmethod
    def validate_command_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("q_"):
            raise ValueError("queue command id must start with q_")
        return normalized


class TraceEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    span_id: str
    parent_span_id: str | None = None
    agent: TraceAgent = "system"
    operation: str
    queue_command_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("span_id")
    @classmethod
    def validate_span_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("sp_"):
            raise ValueError("trace span_id must start with sp_")
        return normalized
