from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.models.dashboard_command import DashboardCommandAction

RemoteRiskLevel = Literal["green", "yellow", "red"]
RemoteJobStatus = Literal["queued", "running", "executed", "blocked", "failed", "timed_out"]

GREEN_ACTIONS: set[str] = {
    "paper.status.refresh",
    "system.readiness.refresh",
    "strategy.validate",
    "strategy.capabilities.refresh",
}
YELLOW_ACTIONS: set[str] = {
    "paper.monitor.refresh",
    "paper.sync.orders",
    "paper.sync.account",
    "system.prepare_workspace",
    "strategy.draft",
    "strategy.workflow.verify",
    "strategy.backtest.rerun",
    "strategy.scan.rerun",
}
RED_ACTIONS: set[str] = {
    "paper.kill_switch.enable",
    "paper.kill_switch.clear",
    "strategy.approve",
    "strategy.activate.manual",
    "strategy.activate.paper_auto",
    "strategy.disable",
}

REMOTE_COMMAND_TIMEOUT_SECONDS = 900
REMOTE_STRATEGY_DOUBLE_CONFIRMATION = "CONFIRM REMOTE STRATEGY MUTATION"
REMOTE_PAPER_DOUBLE_CONFIRMATION = "CONFIRM REMOTE PAPER CONTROL"


def remote_risk_level(action: DashboardCommandAction | str) -> RemoteRiskLevel:
    action_text = str(action)
    if action_text in RED_ACTIONS:
        return "red"
    if action_text in YELLOW_ACTIONS:
        return "yellow"
    if action_text in GREEN_ACTIONS:
        return "green"
    raise ValueError(f"unsupported remote dashboard action: {action_text}")


def remote_backup_required(action: DashboardCommandAction | str) -> bool:
    return remote_risk_level(action) in {"yellow", "red"}


def remote_double_confirmation_phrase(action: DashboardCommandAction | str) -> str | None:
    if remote_risk_level(action) != "red":
        return None
    if str(action).startswith("paper."):
        return REMOTE_PAPER_DOUBLE_CONFIRMATION
    return REMOTE_STRATEGY_DOUBLE_CONFIRMATION


class RemoteCommandMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: RemoteRiskLevel
    backup_required: bool
    double_confirmation_required: bool
    double_confirmation_phrase: str | None = None
    job_timeout_seconds: int = REMOTE_COMMAND_TIMEOUT_SECONDS


class RemoteCommandRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_path: str
    confirm: str
    double_confirm: str = ""
    executed_by: str = "dashboard"
    request_id: str | None = None
    timeout_seconds: int = Field(default=REMOTE_COMMAND_TIMEOUT_SECONDS, ge=1, le=7200)


class RemoteCommandRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: RemoteJobStatus
    action: DashboardCommandAction
    command_id: str
    job_path: str
    log_path: str
    events_path: str
    risk_level: RemoteRiskLevel
    backup_required: bool
    backup_manifest_path: str | None = None
    message: str


class RemoteJobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    command_id: str | None = None
    action: DashboardCommandAction | None = None
    status: RemoteJobStatus
    actor: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message: str = ""
    request_id: str | None = None
    backup_manifest_path: str | None = None
    result_path: str | None = None


class RemoteJobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    command_id: str
    action: DashboardCommandAction
    status: RemoteJobStatus = "queued"
    actor: str
    request_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    timeout_seconds: int = REMOTE_COMMAND_TIMEOUT_SECONDS
    risk_level: RemoteRiskLevel
    plan_path: str
    request_path: str
    job_path: str
    log_path: str
    events_path: str
    result_path: str | None = None
    backup_manifest_path: str | None = None
    output_paths: list[str] = Field(default_factory=list)
    message: str = "Queued remote dashboard command job."
    error: str | None = None


class RemoteDoctorCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["ok", "warning", "blocked"]
    message: str


class RemoteDoctorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["ok", "warning", "blocked"]
    ready: bool
    checks: list[RemoteDoctorCheck]
