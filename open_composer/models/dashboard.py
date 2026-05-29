from __future__ import annotations

import types
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, get_args, get_origin, get_type_hints

from open_composer.json_utils import json_safe_payload
from open_composer.models.execution_backend import BackendStatus, ExecutionBackend
from open_composer.models.project import ProjectEvidenceStatus, ProjectState

Lifecycle = Literal["draft", "approved", "active", "retired"]
CapabilityStatus = Literal["supported", "partial", "blocked", "unsupported"]
PaperReadinessStatus = Literal["ok", "warning", "blocked"]
ModelRole = Literal["pure_quant", "quant_review", "quant_scan", "quant_orchestrator"]
RiskTier = Literal["stable", "moderate", "high"]
RunKind = Literal["backtest", "scan", "paper", "unknown"]
AuditKind = Literal["journal", "paper_order", "paper_kill_switch", "dashboard_command"]


class DashboardDataModel:
    """Small Pydantic-compatible shim for internal Dashboard read models."""

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return json_safe_payload(asdict(self))

    @classmethod
    def model_validate(cls, data: object) -> Any:
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            msg = f"{cls.__name__}.model_validate expected a mapping"
            raise TypeError(msg)
        hints = get_type_hints(cls)
        return cls(
            **{
                name: _coerce_dashboard_value(data[name], hint)
                for name, hint in hints.items()
                if name in data
            }
        )


def _coerce_dashboard_value(value: Any, annotation: Any) -> Any:
    if value is None:
        return None
    origin = get_origin(annotation)
    args = get_args(annotation)
    if annotation is Any or annotation is object:
        return value
    if origin is Literal:
        return value
    if origin is list:
        inner = args[0] if args else Any
        return [_coerce_dashboard_value(item, inner) for item in value]
    if origin is dict:
        value_type = args[1] if len(args) > 1 else Any
        return {str(key): _coerce_dashboard_value(item, value_type) for key, item in value.items()}
    if origin in {types.UnionType, getattr(types, "UnionType", object)}:
        non_none = [item for item in args if item is not type(None)]
        if len(non_none) == 1:
            return _coerce_dashboard_value(value, non_none[0])
        return value
    if isinstance(annotation, type) and issubclass(annotation, DashboardDataModel):
        return annotation.model_validate(value)
    if annotation is datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


@dataclass(kw_only=True)
class DashboardCapabilityFinding(DashboardDataModel):
    capability: str
    status: CapabilityStatus
    reasons: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardCustomDataBinding(DashboardDataModel):
    factor_name: str
    source: str
    path: str
    field: str
    record_count: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    point_in_time_status: Literal["complete", "partial", "missing"] = "missing"
    replay_warnings: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardVersion(DashboardDataModel):
    strategy_id: str
    strategy_name: str
    version_id: str
    primary_lifecycle: Lifecycle
    lifecycles: list[Lifecycle] = field(default_factory=list)
    source_paths: list[str] = field(default_factory=list)
    primary_path: str
    content_hash: str
    parent_version_id: str | None = None
    created_by: str = "unknown"
    created_at: datetime
    modified_at: datetime
    first_seen_at: datetime
    symbol: str
    timeframe: str
    universe: list[str] = field(default_factory=list)
    factor_names: list[str] = field(default_factory=list)
    llm_feature_factor_names: list[str] = field(default_factory=list)
    feature_packet_factor_names: list[str] = field(default_factory=list)
    backend: ExecutionBackend = "python_reference"
    backend_status: BackendStatus = "supported"
    backend_reasons: list[str] = field(default_factory=list)
    execution_mode: str
    broker: str
    data_source: str
    llm_review_enabled: bool
    llm_review_model: str | None = None
    model_role: ModelRole
    model_role_reasons: list[str] = field(default_factory=list)
    risk_tier: RiskTier
    risk_reasons: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    compatibility: list[DashboardCapabilityFinding] = field(default_factory=list)
    note: str = ""


@dataclass(kw_only=True)
class DashboardStrategy(DashboardDataModel):
    strategy_id: str
    strategy_name: str
    current_version_id: str | None = None
    version_ids: list[str] = field(default_factory=list)
    version_count: int = 0
    source_paths: list[str] = field(default_factory=list)
    lifecycle: Lifecycle
    lifecycle_counts: dict[str, int] = field(default_factory=dict)
    symbol: str
    timeframe: str
    universe: list[str] = field(default_factory=list)
    universe_size: int = 0
    factor_names: list[str] = field(default_factory=list)
    factor_count: int = 0
    llm_feature_factor_names: list[str] = field(default_factory=list)
    feature_packet_factor_names: list[str] = field(default_factory=list)
    backend: ExecutionBackend = "python_reference"
    backend_status: BackendStatus = "supported"
    backend_reasons: list[str] = field(default_factory=list)
    execution_mode: str
    broker: str
    data_source: str
    llm_review_enabled: bool
    llm_review_model: str | None = None
    model_role: ModelRole
    model_role_reasons: list[str] = field(default_factory=list)
    risk_tier: RiskTier
    risk_reasons: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    compatibility: dict[str, CapabilityStatus] = field(default_factory=dict)
    compatibility_reasons: dict[str, list[str]] = field(default_factory=dict)


@dataclass(kw_only=True)
class DashboardRun(DashboardDataModel):
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
    custom_data_bindings: list[DashboardCustomDataBinding] = field(default_factory=list)
    symbol: str
    timeframe: str
    bars: int | None = None
    signals: int = 0
    trades: int | None = None
    start_equity: float | None = None
    end_equity: float | None = None
    total_return_pct: float | None = None
    buy_hold_return_pct: float | None = None
    alpha_vs_buy_hold_pct: float | None = None
    annualized_return_pct: float | None = None
    sharpe_ratio: float | None = None
    total_fees: float | None = None
    data_sanity_status: Literal["ok", "warning", "unknown"] | None = None
    evidence_level: str | None = None
    data_sanity_source: str | None = None
    data_sanity_mode: str | None = None
    data_sanity_feed: str | None = None
    data_sanity_path: str | None = None
    data_sanity_warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    first_signal_at: datetime | None = None
    last_signal_at: datetime | None = None


@dataclass(kw_only=True)
class DashboardSignal(DashboardDataModel):
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
    conditions: list[str] = field(default_factory=list)
    log_path: str
    review_path: str | None = None
    context_path: str | None = None


@dataclass(kw_only=True)
class DashboardReview(DashboardDataModel):
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


@dataclass(kw_only=True)
class DashboardContext(DashboardDataModel):
    signal_id: str
    symbol: str
    generated_at: datetime
    event_count: int = 0
    macro_count: int = 0
    news_count: int = 0
    notes: list[str] = field(default_factory=list)
    path: str


@dataclass(kw_only=True)
class DashboardJournalEntry(DashboardDataModel):
    id: str
    signal_id: str
    action: str
    notes: str = ""
    outcome: str = ""
    created_at: datetime
    path: str


@dataclass(kw_only=True)
class DashboardOrder(DashboardDataModel):
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


@dataclass(kw_only=True)
class DashboardPaperPosition(DashboardDataModel):
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


@dataclass(kw_only=True)
class DashboardPaperReadinessCheck(DashboardDataModel):
    name: str
    status: PaperReadinessStatus
    message: str
    suggested_actions: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardPaperReadinessReport(DashboardDataModel):
    strategy_name: str
    strategy_id: str
    status: PaperReadinessStatus
    ready: bool
    generated_at: datetime
    path: str
    report_markdown_path: str | None = None
    gate_summary: dict[str, object] = field(default_factory=dict)
    blocking_checks: list[str] = field(default_factory=list)
    warning_checks: list[str] = field(default_factory=list)
    checks: list[DashboardPaperReadinessCheck] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardAuditEvent(DashboardDataModel):
    id: str
    kind: AuditKind
    signal_id: str | None = None
    created_at: datetime
    action: str
    target: str
    source_path: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(kw_only=True)
class DashboardGroup(DashboardDataModel):
    group_id: str
    category: str
    label: str
    strategy_ids: list[str] = field(default_factory=list)
    strategy_count: int = 0
    active_strategy_count: int = 0
    model_roles: list[str] = field(default_factory=list)
    risk_tiers: list[str] = field(default_factory=list)
    lifecycles: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=list)
    execution_modes: list[str] = field(default_factory=list)
    backends: list[ExecutionBackend] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardDataComparison(DashboardDataModel):
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
    sample_missing_left_timestamps: list[str] = field(default_factory=list)
    sample_missing_right_timestamps: list[str] = field(default_factory=list)
    left_manifest_path: str | None = None
    right_manifest_path: str | None = None
    caveats: list[str] = field(default_factory=list)
    report_json_path: str
    report_markdown_path: str


@dataclass(kw_only=True)
class DashboardFeaturePacket(DashboardDataModel):
    path: str
    record_count: int = 0
    field_names: list[str] = field(default_factory=list)
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    has_timestamp: bool = False
    has_published_at: bool = False
    has_fetched_at: bool = False
    has_visible_at: bool = False
    has_dedupe_key: bool = False
    has_schema_version: bool = False
    point_in_time_status: Literal["complete", "partial", "missing"] = "missing"
    replay_warnings: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardRouterExecutionArtifact(DashboardDataModel):
    strategy_name: str
    execution_substate: str = "unknown"
    route_label: str | None = None
    latest_rebalance_session: str | None = None
    latest_order_required_intents: int = 0
    target_weights_path: str | None = None
    rebalance_intents_path: str | None = None
    cost_stress_path: str | None = None
    data_evidence_path: str | None = None
    validation_path: str | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardWorkflowReport(DashboardDataModel):
    strategy_name: str
    strategy_id: str
    status: Literal["ok", "warning", "blocked"] = "warning"
    source_path: str
    spec_hash: str | None = None
    backtest_run_id: str | None = None
    scan_signal_count: int = 0
    paper_readiness_status: PaperReadinessStatus | None = None
    paper_ready: bool = False
    output_paths: list[str] = field(default_factory=list)
    path: str
    report_markdown_path: str | None = None


@dataclass(kw_only=True)
class DashboardResearchReport(DashboardDataModel):
    strategy_name: str
    kind: Literal[
        "promotion",
        "parameter_sweep",
        "exposure_switch",
        "llm_exposure_switch",
        "rotation",
        "market_timing",
        "geometry_features",
        "router_evidence",
        "alternative_data_evidence",
        "short_risk",
        "unknown",
    ] = "unknown"
    status: Literal["ok", "warning", "blocked"] = "warning"
    ready: bool = False
    source_path: str
    report_json_path: str
    report_markdown_path: str | None = None
    check_count: int = 0
    candidate_count: int | None = None
    data_as_of: str | None = None
    data_feed: str | None = None
    data_source_mode: str | None = None
    cache_fallback: bool = False
    data_warnings: list[str] = field(default_factory=list)
    output_paths: list[str] = field(default_factory=list)
    gate_summary: dict[str, object] = field(default_factory=dict)
    next_action: str = ""
    evidence_strength: str = "unknown"
    benchmark_family_complete: bool | None = None
    overfit_risk: str | None = None
    llm_contribution_status: str | None = None
    paper_readiness_status: PaperReadinessStatus | None = None
    data_provenance: dict[str, object] = field(default_factory=dict)
    iteration_outcome: str | None = None
    candidate_status: str | None = None
    data_compare_status: str | None = None
    route_attribution_status: str | None = None


@dataclass(kw_only=True)
class DashboardResearchRun(DashboardDataModel):
    run_id: str
    generated_at: datetime | None = None
    strategy_name: str
    source_spec_path: str
    spec_hash: str | None = None
    status: Literal["ok", "warning", "blocked"] = "warning"
    kind: str = "research_report"
    research_mode: Literal["playground", "audited"] | None = None
    data_profile: dict[str, object] = field(default_factory=dict)
    candidate_count: int = 0
    trial_count: int = 0
    runtime_seconds: float | None = None
    gate_status: Literal["ok", "warning", "blocked"] = "warning"
    blocked_items: list[str] = field(default_factory=list)
    warning_items: list[str] = field(default_factory=list)
    report_path: str | None = None
    json_path: str | None = None
    contract_path: str | None = None
    source_artifacts: dict[str, str | None] = field(default_factory=dict)
    artifact_count: int = 0
    artifact_refs: list[dict[str, object]] = field(default_factory=list)
    next_action: str = ""
    progress_status: str | None = None
    progress_stage: str | None = None
    progress_event_path: str | None = None
    progress_partial: bool = False
    progress_candidate_index: int | None = None
    progress_candidate_count: int | None = None


@dataclass(kw_only=True)
class DashboardProjectEvidenceItem(DashboardDataModel):
    status: ProjectEvidenceStatus = "unknown"
    summary: str = ""
    artifact_path: str | None = None
    blockers: list[str] = field(default_factory=list)
    updated_at: datetime | None = None


@dataclass(kw_only=True)
class DashboardProjectEvidence(DashboardDataModel):
    factor_quality: DashboardProjectEvidenceItem = field(
        default_factory=DashboardProjectEvidenceItem
    )
    execution_reality: DashboardProjectEvidenceItem = field(
        default_factory=DashboardProjectEvidenceItem
    )
    alt_llm_evidence: DashboardProjectEvidenceItem = field(
        default_factory=DashboardProjectEvidenceItem
    )


@dataclass(kw_only=True)
class DashboardProject(DashboardDataModel):
    project_id: str
    name: str
    state: ProjectState
    thesis: str = ""
    current_spec_path: str | None = None
    latest_run_path: str | None = None
    gate_summary: dict[str, object] = field(default_factory=dict)
    evidence: DashboardProjectEvidence = field(default_factory=DashboardProjectEvidence)
    artifact_state: dict[str, object] = field(default_factory=dict)
    latest_run_summary: dict[str, object] = field(default_factory=dict)
    blocker_summary: dict[str, object] = field(default_factory=dict)
    next_minimal_actions: list[str] = field(default_factory=list)
    do_not_repeat: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_action: str = ""
    current_round: int = 0
    max_rounds: int = 5
    iteration_mode: str = "auto_continue_until_stop"
    stop_reason: str | None = None
    user_requested_stop: bool = False
    paper_status: str = "not_requested"
    archived: bool = False
    imported_from_strategy: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(kw_only=True)
class DashboardOperationalCheck(DashboardDataModel):
    name: str
    status: Literal["ok", "warning", "blocked"] = "warning"
    message: str = ""
    suggested_actions: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)


@dataclass(kw_only=True)
class DashboardDeploymentStep(DashboardOperationalCheck):
    output_paths: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardReadinessReport(DashboardDataModel):
    status: Literal["ok", "warning", "blocked"] = "warning"
    ready: bool = False
    generated_at: datetime | None = None
    path: str
    report_markdown_path: str | None = None
    checks: list[DashboardOperationalCheck] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardDeploymentReport(DashboardDataModel):
    status: Literal["ok", "warning", "blocked"] = "warning"
    ready: bool = False
    generated_at: datetime | None = None
    path: str
    report_markdown_path: str | None = None
    steps: list[DashboardDeploymentStep] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardSummary(DashboardDataModel):
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
    router_execution_artifact_count: int = 0
    router_observation_only_count: int = 0
    workflow_report_count: int = 0
    research_report_count: int = 0
    research_run_count: int = 0
    research_blocked_count: int = 0
    research_warning_count: int = 0
    project_count: int = 0
    project_blocked_count: int = 0
    project_iterating_count: int = 0
    project_candidate_count: int = 0
    project_active_paper_count: int = 0
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
    paper_order_status_counts: dict[str, int] = field(default_factory=dict)
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
    paper_readiness_status_counts: dict[str, int] = field(default_factory=dict)
    strategy_backend_counts: dict[str, int] = field(default_factory=dict)
    backend_status_counts: dict[str, int] = field(default_factory=dict)
    pure_quant_count: int = 0
    quant_review_count: int = 0
    quant_scan_count: int = 0
    quant_orchestrator_count: int = 0
    stable_count: int = 0
    moderate_count: int = 0
    high_count: int = 0
    lifecycle_counts: dict[str, int] = field(default_factory=dict)
    model_role_counts: dict[str, int] = field(default_factory=dict)
    risk_counts: dict[str, int] = field(default_factory=dict)
    run_kind_counts: dict[str, int] = field(default_factory=dict)
    compatibility_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    version_binding_mode: str = "derived_latest_snapshot"
    notes: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class DashboardCatalog(DashboardDataModel):
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_root: str
    summary: DashboardSummary
    strategies: list[DashboardStrategy] = field(default_factory=list)
    projects: list[DashboardProject] = field(default_factory=list)
    versions: list[DashboardVersion] = field(default_factory=list)
    runs: list[DashboardRun] = field(default_factory=list)
    signals: list[DashboardSignal] = field(default_factory=list)
    reviews: list[DashboardReview] = field(default_factory=list)
    contexts: list[DashboardContext] = field(default_factory=list)
    journals: list[DashboardJournalEntry] = field(default_factory=list)
    orders: list[DashboardOrder] = field(default_factory=list)
    paper_positions: list[DashboardPaperPosition] = field(default_factory=list)
    paper_readiness_reports: list[DashboardPaperReadinessReport] = field(default_factory=list)
    audits: list[DashboardAuditEvent] = field(default_factory=list)
    groups: list[DashboardGroup] = field(default_factory=list)
    data_comparisons: list[DashboardDataComparison] = field(default_factory=list)
    feature_packets: list[DashboardFeaturePacket] = field(default_factory=list)
    router_execution_artifacts: list[DashboardRouterExecutionArtifact] = field(default_factory=list)
    workflow_reports: list[DashboardWorkflowReport] = field(default_factory=list)
    research_reports: list[DashboardResearchReport] = field(default_factory=list)
    research_runs: list[DashboardResearchRun] = field(default_factory=list)
    readiness_report: DashboardReadinessReport | None = None
    deployment_report: DashboardDeploymentReport | None = None
