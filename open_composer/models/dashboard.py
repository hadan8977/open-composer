from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.models.execution_backend import BackendStatus, ExecutionBackend

Lifecycle = Literal["draft", "approved", "active", "retired"]
CapabilityStatus = Literal["supported", "partial", "blocked", "unsupported"]
PaperReadinessStatus = Literal["ok", "warning", "blocked"]
ModelRole = Literal["pure_quant", "quant_review", "quant_scan", "quant_orchestrator"]
RiskTier = Literal["stable", "moderate", "high"]
RunKind = Literal["backtest", "scan", "paper", "unknown"]
AuditKind = Literal["journal", "paper_order", "paper_kill_switch", "dashboard_command"]


class DashboardCapabilityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str
    status: CapabilityStatus
    reasons: list[str] = Field(default_factory=list)


class DashboardCustomDataBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_name: str
    source: str
    path: str
    field: str
    record_count: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    point_in_time_status: Literal["complete", "partial", "missing"] = "missing"
    replay_warnings: list[str] = Field(default_factory=list)


class DashboardVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    strategy_name: str
    version_id: str
    primary_lifecycle: Lifecycle
    lifecycles: list[Lifecycle] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)
    primary_path: str
    content_hash: str
    parent_version_id: str | None = None
    created_by: str = "unknown"
    created_at: datetime
    modified_at: datetime
    first_seen_at: datetime
    symbol: str
    timeframe: str
    universe: list[str] = Field(default_factory=list)
    factor_names: list[str] = Field(default_factory=list)
    llm_feature_factor_names: list[str] = Field(default_factory=list)
    feature_packet_factor_names: list[str] = Field(default_factory=list)
    backend: ExecutionBackend = "python_reference"
    backend_status: BackendStatus = "supported"
    backend_reasons: list[str] = Field(default_factory=list)
    execution_mode: str
    broker: str
    data_source: str
    llm_review_enabled: bool
    llm_review_model: str | None = None
    model_role: ModelRole
    model_role_reasons: list[str] = Field(default_factory=list)
    risk_tier: RiskTier
    risk_reasons: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    compatibility: list[DashboardCapabilityFinding] = Field(default_factory=list)
    note: str = ""


class DashboardStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    strategy_name: str
    current_version_id: str | None = None
    version_ids: list[str] = Field(default_factory=list)
    version_count: int = 0
    source_paths: list[str] = Field(default_factory=list)
    lifecycle: Lifecycle
    lifecycle_counts: dict[str, int] = Field(default_factory=dict)
    symbol: str
    timeframe: str
    universe: list[str] = Field(default_factory=list)
    universe_size: int = 0
    factor_names: list[str] = Field(default_factory=list)
    factor_count: int = 0
    llm_feature_factor_names: list[str] = Field(default_factory=list)
    feature_packet_factor_names: list[str] = Field(default_factory=list)
    backend: ExecutionBackend = "python_reference"
    backend_status: BackendStatus = "supported"
    backend_reasons: list[str] = Field(default_factory=list)
    execution_mode: str
    broker: str
    data_source: str
    llm_review_enabled: bool
    llm_review_model: str | None = None
    model_role: ModelRole
    model_role_reasons: list[str] = Field(default_factory=list)
    risk_tier: RiskTier
    risk_reasons: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    compatibility: dict[str, CapabilityStatus] = Field(default_factory=dict)
    compatibility_reasons: dict[str, list[str]] = Field(default_factory=dict)


class DashboardRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    strategy_id: str
    strategy_name: str
    version_id: str | None = None
    version_binding: str = "derived_latest_snapshot"
    spec_hash: str | None = None
    strategy_backend: ExecutionBackend = "python_reference"
    execution_backend: ExecutionBackend = "python_reference"
    kind: RunKind = "unknown"
    source_path: str
    report_path: str | None = None
    signal_log_path: str | None = None
    backend_plan_path: str | None = None
    paper_readiness_report_path: str | None = None
    custom_data_bindings: list[DashboardCustomDataBinding] = Field(default_factory=list)
    symbol: str
    timeframe: str
    bars: int | None = None
    signals: int = 0
    trades: int | None = None
    start_equity: float | None = None
    end_equity: float | None = None
    total_return_pct: float | None = None
    annualized_return_pct: float | None = None
    sharpe_ratio: float | None = None
    total_fees: float | None = None
    assumptions: list[str] = Field(default_factory=list)
    first_signal_at: datetime | None = None
    last_signal_at: datetime | None = None


class DashboardSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    run_id: str
    strategy_id: str
    strategy_name: str
    version_id: str | None = None
    spec_hash: str | None = None
    strategy_backend: ExecutionBackend = "python_reference"
    execution_backend: ExecutionBackend = "python_reference"
    symbol: str
    timeframe: str
    timestamp: datetime
    action: str
    side: str
    source: str
    price: float
    execution_mode: str
    fill_assumption: str
    lifecycle: str
    conditions: list[str] = Field(default_factory=list)
    log_path: str
    review_path: str | None = None
    context_path: str | None = None


class DashboardReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    strategy_id: str
    strategy_name: str
    verdict: str
    confidence: float
    model: str
    created_at: datetime
    timestamp: str
    action_suggestion: str
    path: str
    context_path: str | None = None


class DashboardContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    symbol: str
    generated_at: datetime
    event_count: int = 0
    macro_count: int = 0
    news_count: int = 0
    notes: list[str] = Field(default_factory=list)
    path: str


class DashboardJournalEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    signal_id: str
    action: str
    notes: str = ""
    outcome: str = ""
    created_at: datetime
    path: str


class DashboardOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    signal_id: str
    strategy_name: str
    strategy_id: str | None = None
    version_id: str | None = None
    spec_hash: str | None = None
    strategy_backend: ExecutionBackend = "python_reference"
    execution_backend: ExecutionBackend = "python_reference"
    symbol: str
    side: str
    qty: float
    status: str
    paper: bool = True
    submitted_at: datetime
    path: str


class DashboardPaperPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    qty: float
    market_value: float | None = None
    cost_basis: float | None = None
    unrealized_pl: float | None = None
    unrealized_plpc: float | None = None
    current_price: float | None = None
    side: str = ""
    updated_at: datetime
    paper: bool = True
    path: str


class DashboardPaperReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: PaperReadinessStatus
    message: str
    suggested_actions: list[str] = Field(default_factory=list)


class DashboardPaperReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    strategy_id: str
    status: PaperReadinessStatus
    ready: bool
    generated_at: datetime
    path: str
    report_markdown_path: str | None = None
    blocking_checks: list[str] = Field(default_factory=list)
    warning_checks: list[str] = Field(default_factory=list)
    checks: list[DashboardPaperReadinessCheck] = Field(default_factory=list)


class DashboardAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: AuditKind
    signal_id: str | None = None
    created_at: datetime
    action: str
    target: str
    source_path: str
    details: dict[str, object] = Field(default_factory=dict)


class DashboardGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    category: str
    label: str
    strategy_ids: list[str] = Field(default_factory=list)
    strategy_count: int = 0
    active_strategy_count: int = 0
    model_roles: list[str] = Field(default_factory=list)
    risk_tiers: list[str] = Field(default_factory=list)
    lifecycles: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    execution_modes: list[str] = Field(default_factory=list)
    backends: list[ExecutionBackend] = Field(default_factory=list)


class DashboardDataComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    timeframe: str
    left_source: str
    right_source: str
    left_feed: str | None = None
    right_feed: str | None = None
    left_rows: int = 0
    right_rows: int = 0
    matched_rows: int = 0
    missing_left_rows: int = 0
    missing_right_rows: int = 0
    matched_coverage_pct: float = 0.0
    max_abs_close_diff: float = 0.0
    mean_abs_close_diff: float = 0.0
    max_abs_close_diff_bps: float = 0.0
    mean_abs_close_diff_bps: float = 0.0
    max_abs_volume_diff: float = 0.0
    max_volume_diff_ratio: float = 0.0
    first_matched_timestamp: str | None = None
    last_matched_timestamp: str | None = None
    sample_missing_left_timestamps: list[str] = Field(default_factory=list)
    sample_missing_right_timestamps: list[str] = Field(default_factory=list)
    left_manifest_path: str | None = None
    right_manifest_path: str | None = None
    caveats: list[str] = Field(default_factory=list)
    report_json_path: str
    report_markdown_path: str


class DashboardFeaturePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    record_count: int = 0
    field_names: list[str] = Field(default_factory=list)
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    has_timestamp: bool = False
    has_published_at: bool = False
    has_fetched_at: bool = False
    has_dedupe_key: bool = False
    has_schema_version: bool = False
    point_in_time_status: Literal["complete", "partial", "missing"] = "missing"
    replay_warnings: list[str] = Field(default_factory=list)


class DashboardWorkflowReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    strategy_id: str
    status: Literal["ok", "warning", "blocked"] = "warning"
    source_path: str
    spec_hash: str | None = None
    backtest_run_id: str | None = None
    scan_signal_count: int = 0
    paper_readiness_status: PaperReadinessStatus | None = None
    paper_ready: bool = False
    output_paths: list[str] = Field(default_factory=list)
    path: str
    report_markdown_path: str | None = None


class DashboardOperationalCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["ok", "warning", "blocked"] = "warning"
    message: str = ""
    suggested_actions: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class DashboardDeploymentStep(DashboardOperationalCheck):
    output_paths: list[str] = Field(default_factory=list)


class DashboardReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "warning", "blocked"] = "warning"
    ready: bool = False
    generated_at: datetime | None = None
    path: str
    report_markdown_path: str | None = None
    checks: list[DashboardOperationalCheck] = Field(default_factory=list)


class DashboardDeploymentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "warning", "blocked"] = "warning"
    ready: bool = False
    generated_at: datetime | None = None
    path: str
    report_markdown_path: str | None = None
    steps: list[DashboardDeploymentStep] = Field(default_factory=list)


class DashboardSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_root: str
    generated_at: datetime
    read_model_version: str = "1"
    strategy_count: int = 0
    version_count: int = 0
    run_count: int = 0
    signal_count: int = 0
    review_count: int = 0
    context_count: int = 0
    journal_count: int = 0
    order_count: int = 0
    audit_count: int = 0
    data_comparison_count: int = 0
    feature_packet_count: int = 0
    workflow_report_count: int = 0
    readiness_status: Literal["ok", "warning", "blocked", "missing"] = "missing"
    readiness_ready: bool = False
    readiness_warning_count: int = 0
    readiness_blocked_count: int = 0
    deployment_status: Literal["ok", "warning", "blocked", "missing"] = "missing"
    deployment_ready: bool = False
    deployment_warning_count: int = 0
    deployment_blocked_count: int = 0
    active_strategy_count: int = 0
    paper_auto_strategy_count: int = 0
    paper_kill_switch_enabled: bool = False
    paper_open_order_count: int = 0
    paper_order_status_counts: dict[str, int] = Field(default_factory=dict)
    paper_account_equity: float | None = None
    paper_account_cash: float | None = None
    paper_account_buying_power: float | None = None
    paper_account_portfolio_value: float | None = None
    paper_account_snapshot_at: datetime | None = None
    paper_position_count: int = 0
    paper_total_position_market_value: float = 0.0
    paper_total_unrealized_pl: float = 0.0
    paper_positions_snapshot_at: datetime | None = None
    paper_reconciliation_status: str = "unknown"
    paper_reconciliation_issue_count: int = 0
    paper_reconciliation_report_path: str | None = None
    paper_alert_status: str = "unknown"
    paper_alert_count: int = 0
    paper_alert_report_path: str | None = None
    paper_readiness_count: int = 0
    paper_readiness_status_counts: dict[str, int] = Field(default_factory=dict)
    strategy_backend_counts: dict[str, int] = Field(default_factory=dict)
    backend_status_counts: dict[str, int] = Field(default_factory=dict)
    pure_quant_count: int = 0
    quant_review_count: int = 0
    quant_scan_count: int = 0
    quant_orchestrator_count: int = 0
    stable_count: int = 0
    moderate_count: int = 0
    high_count: int = 0
    lifecycle_counts: dict[str, int] = Field(default_factory=dict)
    model_role_counts: dict[str, int] = Field(default_factory=dict)
    risk_counts: dict[str, int] = Field(default_factory=dict)
    run_kind_counts: dict[str, int] = Field(default_factory=dict)
    compatibility_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    version_binding_mode: str = "derived_latest_snapshot"
    notes: list[str] = Field(default_factory=list)


class DashboardCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_root: str
    summary: DashboardSummary
    strategies: list[DashboardStrategy] = Field(default_factory=list)
    versions: list[DashboardVersion] = Field(default_factory=list)
    runs: list[DashboardRun] = Field(default_factory=list)
    signals: list[DashboardSignal] = Field(default_factory=list)
    reviews: list[DashboardReview] = Field(default_factory=list)
    contexts: list[DashboardContext] = Field(default_factory=list)
    journals: list[DashboardJournalEntry] = Field(default_factory=list)
    orders: list[DashboardOrder] = Field(default_factory=list)
    paper_positions: list[DashboardPaperPosition] = Field(default_factory=list)
    paper_readiness_reports: list[DashboardPaperReadinessReport] = Field(default_factory=list)
    audits: list[DashboardAuditEvent] = Field(default_factory=list)
    groups: list[DashboardGroup] = Field(default_factory=list)
    data_comparisons: list[DashboardDataComparison] = Field(default_factory=list)
    feature_packets: list[DashboardFeaturePacket] = Field(default_factory=list)
    workflow_reports: list[DashboardWorkflowReport] = Field(default_factory=list)
    readiness_report: DashboardReadinessReport | None = None
    deployment_report: DashboardDeploymentReport | None = None
