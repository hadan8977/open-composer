from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.models.execution_backend import ExecutionBackend


class PaperOrderRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    signal_id: str
    client_order_id: str
    strategy_name: str
    strategy_id: str | None = None
    version_id: str | None = None
    spec_hash: str | None = None
    strategy_backend: ExecutionBackend = "python_reference"
    execution_backend: ExecutionBackend = "python_reference"
    execution_policy_id: str | None = None
    execution_policy_hash: str | None = None
    order_style: str | None = None
    time_in_force: str | None = None
    authorization_id: str | None = None
    authorization_hash: str | None = None
    authorization_kind: Literal["canary", "full"] | None = None
    signal_record_hash: str | None = None
    signal_log_path: str | None = None
    order_intent_id: str | None = None
    order_intent_hash: str | None = None
    initial_broker_receipt_path: str | None = None
    initial_broker_receipt_hash: str | None = None
    broker_state_hash: str | None = None
    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    reference_price: float | None = None
    estimated_notional: float | None = None
    requested_target_weight: float | None = None
    effective_target_weight: float | None = None
    pretrade_position_qty: float | None = None
    target_position_qty: float | None = None
    canary_position_limit_usd: float | None = None
    risk_effect: Literal["increase", "reduce"] | None = None
    status: str
    paper: bool = True
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PaperOrderIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    client_order_id: str
    signal_id: str
    signal_record_hash: str
    signal_log_path: str
    strategy_name: str
    version_id: str
    spec_hash: str
    execution_policy_id: str
    execution_policy_hash: str
    order_style: str
    time_in_force: str
    authorization_id: str
    authorization_hash: str
    authorization_kind: Literal["canary", "full"] | None = None
    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    reference_price: float | None = None
    estimated_notional: float | None = None
    requested_target_weight: float | None = None
    effective_target_weight: float | None = None
    pretrade_position_qty: float | None = None
    target_position_qty: float | None = None
    canary_position_limit_usd: float | None = None
    risk_effect: Literal["increase", "reduce"] | None = None
    reserved_at: datetime | None = None
    paper: bool = True
    state: Literal["prepared"] = "prepared"


class PaperKillSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_version: Literal[2] = 2
    sequence: int = 0
    previous_event_hash: str | None = None
    event_id: str = ""
    enabled: bool = False
    reason: str = ""
    updated_by: str = "system"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PaperAccountSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    equity: float | None = None
    cash: float | None = None
    buying_power: float | None = None
    portfolio_value: float | None = None
    broker_account_id_hash: str | None = None
    status: str = ""
    paper: bool = True


class PaperPositionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    qty: float
    market_value: float | None = None
    cost_basis: float | None = None
    unrealized_pl: float | None = None
    unrealized_plpc: float | None = None
    current_price: float | None = None
    side: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    paper: bool = True


class PaperReconciliationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["info", "warning", "error"]
    code: str
    symbol: str | None = None
    message: str


class PaperReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["ok", "warning", "error"] = "ok"
    order_count: int = 0
    position_count: int = 0
    open_order_count: int = 0
    filled_order_count: int = 0
    issue_count: int = 0
    issues: list[PaperReconciliationIssue] = Field(default_factory=list)
    report_json_path: str | None = None
    report_markdown_path: str | None = None


class PaperAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    source_path: str | None = None


class PaperAlertReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["ok", "warning", "error"] = "ok"
    alert_count: int = 0
    alerts: list[PaperAlert] = Field(default_factory=list)
    report_json_path: str | None = None
    report_markdown_path: str | None = None


class PaperMonitorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["ok", "warning", "error"] = "ok"
    sync_broker: bool = False
    sync_status: Literal["skipped", "ok", "error"] = "skipped"
    sync_error: str = ""
    sync_output_paths: list[str] = Field(default_factory=list)
    reconciliation_status: str = "unknown"
    reconciliation_issue_count: int = 0
    alert_status: str = "unknown"
    alert_count: int = 0
    status_path: str
    reconciliation_report_path: str | None = None
    alert_report_path: str | None = None
    report_json_path: str | None = None
    report_markdown_path: str | None = None


class PaperStatusSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kill_switch: PaperKillSwitch = Field(default_factory=PaperKillSwitch)
    active_paper_auto_strategies: list[str] = Field(default_factory=list)
    order_status_counts: dict[str, int] = Field(default_factory=dict)
    open_order_count: int = 0
    account_equity: float | None = None
    account_cash: float | None = None
    account_buying_power: float | None = None
    account_portfolio_value: float | None = None
    account_snapshot_at: datetime | None = None
    position_count: int = 0
    total_position_market_value: float = 0.0
    total_unrealized_pl: float = 0.0
    positions_snapshot_at: datetime | None = None
    reconciliation_status: str = "unknown"
    reconciliation_issue_count: int = 0
    reconciliation_report_path: str | None = None
    alert_status: str = "unknown"
    alert_count: int = 0
    alert_report_path: str | None = None
    last_order_at: datetime | None = None
    notes: list[str] = Field(default_factory=list)
