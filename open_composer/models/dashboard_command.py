from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DashboardPaperAction = Literal[
    "paper.status.refresh",
    "paper.monitor.refresh",
    "paper.sync.orders",
    "paper.sync.account",
    "paper.kill_switch.enable",
    "paper.kill_switch.clear",
]
DashboardStrategyAction = Literal[
    "strategy.draft",
    "strategy.workflow.verify",
    "strategy.validate",
    "strategy.capabilities.refresh",
    "strategy.approve",
    "strategy.activate.manual",
    "strategy.activate.paper_auto",
    "strategy.backtest.rerun",
    "strategy.scan.rerun",
    "strategy.disable",
]
DashboardSystemAction = Literal[
    "system.prepare_workspace",
    "system.readiness.refresh",
]
DashboardCommandAction = DashboardPaperAction | DashboardStrategyAction | DashboardSystemAction
DashboardCommandStatus = Literal["planned", "executed", "blocked"]


class DashboardCommandStrategyBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    lifecycle: str
    execution_mode: str
    broker: str
    source_path: str
    spec_hash: str


class DashboardCommandPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    action: DashboardCommandAction
    status: DashboardCommandStatus = "planned"
    requested_by: str = "dashboard"
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str = ""
    paper_only: bool = True
    real_money_allowed: bool = False
    confirmation_required: bool = True
    confirmation_phrase: str = "CONFIRM PAPER COMMAND"
    data_source: Literal["keep", "sample", "alpaca", "longbridge"] = "keep"
    idea: str = ""
    use_llm: bool = False
    cli_args: list[str] = Field(default_factory=list)
    target_strategy_bindings: list[DashboardCommandStrategyBinding] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    plan_path: str | None = None
    audit_event_path: str = "reports/dashboard/commands/events.jsonl"


class DashboardCommandEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    action: DashboardCommandAction
    status: Literal["planned", "executed", "blocked"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor: str = "dashboard"
    reason: str = ""
    plan_path: str | None = None
    result_path: str | None = None
    message: str = ""


class DashboardCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    action: DashboardCommandAction
    status: Literal["executed", "blocked"]
    executed_by: str = "dashboard"
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message: str
    output_paths: list[str] = Field(default_factory=list)
    result_path: str | None = None
