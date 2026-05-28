import rawCatalog, { catalogPath } from "virtual:dashboard-catalog";

export type RiskLevel = "stable" | "moderate" | "high";
export type ModelClass =
  | "pure-quant"
  | "quant-review"
  | "quant-scan"
  | "quant-orchestrator";
export type CapabilityStatus =
  | "supported"
  | "partial"
  | "blocked"
  | "unsupported";
export type OperationalStatus = "ok" | "warning" | "blocked";
export type ProjectEvidenceStatus =
  | "ok"
  | "warning"
  | "blocked"
  | "not_applicable"
  | "unknown";
export type ProjectState =
  | "idea"
  | "draft"
  | "researching"
  | "iterating"
  | "candidate"
  | "paper_review"
  | "active_paper"
  | "retired"
  | "blocked";

export interface Strategy {
  id: string;
  name: string;
  symbol: string;
  timeframe: string;
  version: string;
  status: "active" | "approved" | "draft" | "retired";
  modelClass: ModelClass;
  risk: RiskLevel;
  group: string;
  pine: boolean;
  python: boolean;
  alpaca: boolean;
  lastReturn: number;
  sharpe: number;
  trades: number;
  series: number[];
  backend: string;
  backendStatus: CapabilityStatus;
  backendReasons: string[];
  backendPlanPath: string | null;
  paperReadinessReportPath: string | null;
  paperReadiness: PaperReadinessReport | null;
  customDataBindings: CustomDataBinding[];
  broker: string;
  dataSource: string;
  executionMode: string;
  sourcePath: string;
  specHash?: string | null;
  note: string;
  factors: string[];
  requiredCapabilities: string[];
  compatibility: Record<string, CapabilityStatus>;
  compatibilityReasons: Record<string, string[]>;
  llmReviewEnabled: boolean;
  llmReviewModel?: string | null;
}

export interface ProjectEvidenceItem {
  status: ProjectEvidenceStatus;
  summary: string;
  artifactPath: string | null;
  blockers: string[];
  updatedAt: string | null;
}

export interface ProjectEvidence {
  factorQuality: ProjectEvidenceItem;
  executionReality: ProjectEvidenceItem;
  altLLMEvidence: ProjectEvidenceItem;
}

export interface ProjectControlState {
  lastSuccessfulStep: string;
  latestArtifacts: Record<string, string>;
  blockedItems: string[];
  warningItems: string[];
}

export interface ProjectRunLedger {
  status: string;
  round: number | null;
  taskType: string;
  changedPaths: string[];
  stepEvents: Array<{
    stepName: string;
    status: string;
    outputArtifacts: string[];
    blockedItems: string[];
    warningItems: string[];
  }>;
}

export interface StrategyProject {
  projectId: string;
  name: string;
  state: ProjectState;
  thesis: string;
  currentSpecPath: string | null;
  latestRunPath: string | null;
  gateSummary: {
    workflowPass: boolean | null;
    researchPass: boolean | null;
    llmContributionPass: boolean | null;
    paperReadyPass: boolean | null;
    status: string;
    blockedChecks: string[];
    warningChecks: string[];
  };
  evidence: ProjectEvidence;
  artifactState: ProjectControlState;
  latestRunSummary: ProjectRunLedger | null;
  blockerSummary: {
    trigger: string;
    failedStep: string;
    rootBlockers: string[];
    nextMinimalActions: string[];
    doNotRepeat: string[];
    artifactRefs: string[];
  } | null;
  nextMinimalActions: string[];
  doNotRepeat: string[];
  blockers: string[];
  nextAction: string;
  currentRound: number;
  maxRounds: number;
  iterationMode: string;
  stopReason: string | null;
  userRequestedStop: boolean;
  paperStatus: string;
  archived: boolean;
  importedFromStrategy: boolean;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface CustomDataBinding {
  factorName: string;
  source: string;
  path: string;
  field: string;
  recordCount: number;
  firstTimestamp: string | null;
  lastTimestamp: string | null;
  pointInTimeStatus: "complete" | "partial" | "missing";
  replayWarnings: string[];
}

export interface RecentSignal {
  id: string;
  t: string;
  strat: string;
  side: string;
  px: number;
  sz: number;
  tag: string;
  symbol: string;
}

export interface TimelineEvent {
  t: string;
  kind: string;
  title: string;
  impact: "high" | "med" | "low";
}

export interface LLMReview {
  id: string;
  strat: string;
  verdict: string;
  summary: string;
  color: "pink" | "orange" | "green" | "cyan" | "purple" | "paper";
}

export interface AuditLogEntry {
  t: string;
  who: "user" | "codex" | "system" | "llm";
  action: string;
  target: string;
}

export interface VersionEntry {
  id: string;
  strat: string;
  parent: string;
  by: string;
  at: string;
  status: Strategy["status"];
  diff: string;
  hash: string;
}

export interface StrategyGroup {
  id: string;
  name: string;
  weight: number;
  color: "green" | "pink" | "cyan" | "orange" | "black" | "purple";
  risk: RiskLevel;
  children: string[];
  category: string;
}

export interface PaperPosition {
  sym: string;
  qty: number;
  avg: number;
  mkt: number;
  upnl: number;
  strat: string;
}

export interface PaperReadinessCheck {
  name: string;
  status: "ok" | "warning" | "blocked";
  message: string;
  suggestedActions: string[];
}

export interface PaperReadinessReport {
  strategyId: string;
  strategyName: string;
  status: "ok" | "warning" | "blocked";
  ready: boolean;
  generatedAt: string | null;
  path: string;
  markdownPath: string | null;
  blockingChecks: string[];
  warningChecks: string[];
  checks: PaperReadinessCheck[];
}

export interface ResearchRun {
  id: string;
  generatedAt: string | null;
  strategyName: string;
  kind: string;
  researchMode: "playground" | "audited" | null;
  status: OperationalStatus;
  gateStatus: OperationalStatus;
  sourceSpecPath: string;
  reportPath: string | null;
  jsonPath: string | null;
  candidateCount: number;
  trialCount: number;
  runtimeSeconds: number | null;
  blockedItems: string[];
  warningItems: string[];
  dataSourceMode: string;
  dataAsOf: string | null;
  artifactCount: number;
  nextAction: string;
}

export interface DashboardSummaryView {
  catalogPath: string;
  generatedAt: string | null;
  generatedLabel: string;
  sourceRoot: string;
  readModelVersion: string;
  strategyCount: number;
  activeStrategyCount: number;
  approvedStrategyCount: number;
  draftStrategyCount: number;
  retiredStrategyCount: number;
  versionCount: number;
  runCount: number;
  signalCount: number;
  reviewCount: number;
  contextCount: number;
  journalCount: number;
  orderCount: number;
  auditCount: number;
  dataComparisonCount: number;
  featurePacketCount: number;
  workflowReportCount: number;
  researchReportCount: number;
  researchRunCount: number;
  researchBlockedCount: number;
  researchWarningCount: number;
  projectCount: number;
  projectBlockedCount: number;
  projectIteratingCount: number;
  projectCandidateCount: number;
  projectActivePaperCount: number;
  readinessStatus: "ok" | "warning" | "blocked" | "missing";
  readinessReady: boolean;
  readinessWarningCount: number;
  readinessBlockedCount: number;
  deploymentStatus: "ok" | "warning" | "blocked" | "missing";
  deploymentReady: boolean;
  deploymentWarningCount: number;
  deploymentBlockedCount: number;
  deploymentNextAction: string | null;
  readinessNextAction: string | null;
  paperAutoStrategyCount: number;
  paperOpenOrderCount: number;
  paperPositionCount: number;
  paperKillSwitchEnabled: boolean;
  paperReconciliationStatus: string;
  paperAlertStatus: string;
  paperAccountEquity: number | null;
  paperAccountCash: number | null;
  paperAccountSnapshotAt: string | null;
  paperPositionsSnapshotAt: string | null;
  paperTotalUnrealizedPl: number;
  paperReadinessCount: number;
  paperReadinessStatusCounts: Record<string, number>;
  backendStatusCounts: Record<string, number>;
  modelRoleCounts: Record<string, number>;
  riskCounts: Record<string, number>;
  lifecycleCounts: Record<string, number>;
  compatibilityCounts: Record<string, Record<string, number>>;
  notes: string[];
}

interface DashboardCatalog {
  generated_at?: string | null;
  source_root?: string;
  summary?: DashboardSummaryRecord;
  strategies?: DashboardStrategyRecord[];
  projects?: DashboardProjectRecord[];
  versions?: DashboardVersionRecord[];
  runs?: DashboardRunRecord[];
  signals?: DashboardSignalRecord[];
  reviews?: DashboardReviewRecord[];
  contexts?: DashboardContextRecord[];
  orders?: DashboardOrderRecord[];
  paper_positions?: DashboardPaperPositionRecord[];
  paper_readiness_reports?: DashboardPaperReadinessRecord[];
  audits?: DashboardAuditRecord[];
  groups?: DashboardGroupRecord[];
  data_comparisons?: DashboardDataComparisonRecord[];
  feature_packets?: DashboardFeaturePacketRecord[];
  workflow_reports?: DashboardWorkflowReportRecord[];
  research_reports?: DashboardResearchReportRecord[];
  research_runs?: DashboardResearchRunRecord[];
  readiness_report?: DashboardReadinessReportRecord | null;
  deployment_report?: DashboardDeploymentReportRecord | null;
}

interface DashboardSummaryRecord {
  source_root?: string;
  generated_at?: string | null;
  read_model_version?: string;
  strategy_count?: number;
  active_strategy_count?: number;
  version_count?: number;
  run_count?: number;
  signal_count?: number;
  review_count?: number;
  context_count?: number;
  journal_count?: number;
  order_count?: number;
  audit_count?: number;
  data_comparison_count?: number;
  feature_packet_count?: number;
  workflow_report_count?: number;
  research_report_count?: number;
  research_run_count?: number;
  research_blocked_count?: number;
  research_warning_count?: number;
  project_count?: number;
  project_blocked_count?: number;
  project_iterating_count?: number;
  project_candidate_count?: number;
  project_active_paper_count?: number;
  readiness_status?: "ok" | "warning" | "blocked" | "missing";
  readiness_ready?: boolean;
  readiness_warning_count?: number;
  readiness_blocked_count?: number;
  deployment_status?: "ok" | "warning" | "blocked" | "missing";
  deployment_ready?: boolean;
  deployment_warning_count?: number;
  deployment_blocked_count?: number;
  paper_auto_strategy_count?: number;
  paper_open_order_count?: number;
  paper_position_count?: number;
  paper_kill_switch_enabled?: boolean;
  paper_reconciliation_status?: string;
  paper_alert_status?: string;
  paper_account_equity?: number | null;
  paper_account_cash?: number | null;
  paper_account_snapshot_at?: string | null;
  paper_positions_snapshot_at?: string | null;
  paper_total_unrealized_pl?: number;
  paper_readiness_count?: number;
  paper_readiness_status_counts?: Record<string, number>;
  backend_status_counts?: Record<string, number>;
  model_role_counts?: Record<string, number>;
  risk_counts?: Record<string, number>;
  lifecycle_counts?: Record<string, number>;
  compatibility_counts?: Record<string, Record<string, number>>;
  notes?: string[];
}

interface DashboardStrategyRecord {
  strategy_id: string;
  strategy_name: string;
  current_version_id?: string | null;
  version_ids?: string[];
  lifecycle: Strategy["status"];
  symbol: string;
  timeframe: string;
  backend?: string;
  backend_status?: CapabilityStatus;
  backend_reasons?: string[];
  broker?: string;
  data_source?: string;
  execution_mode?: string;
  model_role?:
    | "pure_quant"
    | "quant_review"
    | "quant_scan"
    | "quant_orchestrator";
  risk_tier?: RiskLevel;
  factor_names?: string[];
  llm_feature_factor_names?: string[];
  feature_packet_factor_names?: string[];
  required_capabilities?: string[];
  source_paths?: string[];
  compatibility?: Record<string, CapabilityStatus>;
  compatibility_reasons?: Record<string, string[]>;
  llm_review_enabled?: boolean;
  llm_review_model?: string | null;
}

interface DashboardProjectRecord {
  project_id: string;
  name: string;
  state: ProjectState;
  thesis?: string;
  current_spec_path?: string | null;
  latest_run_path?: string | null;
  gate_summary?: {
    workflow_pass?: boolean | null;
    research_pass?: boolean | null;
    llm_contribution_pass?: boolean | null;
    paper_ready_pass?: boolean | null;
    status?: string;
    blocked_checks?: string[];
    warning_checks?: string[];
  };
  evidence?: {
    factor_quality?: DashboardProjectEvidenceItemRecord;
    execution_reality?: DashboardProjectEvidenceItemRecord;
    alt_llm_evidence?: DashboardProjectEvidenceItemRecord;
  };
  artifact_state?: Record<string, unknown>;
  latest_run_summary?: Record<string, unknown>;
  blocker_summary?: Record<string, unknown>;
  next_minimal_actions?: string[];
  do_not_repeat?: string[];
  blockers?: string[];
  next_action?: string;
  current_round?: number;
  max_rounds?: number;
  iteration_mode?: string;
  stop_reason?: string | null;
  user_requested_stop?: boolean;
  paper_status?: string;
  archived?: boolean;
  imported_from_strategy?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

interface DashboardProjectEvidenceItemRecord {
  status?: ProjectEvidenceStatus;
  summary?: string;
  artifact_path?: string | null;
  blockers?: string[];
  updated_at?: string | null;
}

interface DashboardVersionRecord extends DashboardStrategyRecord {
  version_id: string;
  parent_version_id?: string | null;
  created_by?: string;
  created_at?: string;
  modified_at?: string;
  content_hash?: string;
  primary_lifecycle?: Strategy["status"];
  primary_path?: string;
  note?: string;
}

interface DashboardRunRecord {
  run_id: string;
  strategy_id: string;
  strategy_name: string;
  version_id?: string | null;
  spec_hash?: string | null;
  backend_plan_path?: string | null;
  kind?: string;
  source_path?: string;
  report_path?: string | null;
  signal_log_path?: string | null;
  symbol?: string;
  timeframe?: string;
  paper_readiness_report_path?: string | null;
  custom_data_bindings?: DashboardCustomDataBindingRecord[];
  signals?: number;
  trades?: number | null;
  total_return_pct?: number | null;
  buy_hold_return_pct?: number | null;
  alpha_vs_buy_hold_pct?: number | null;
  annualized_return_pct?: number | null;
  sharpe_ratio?: number | null;
  end_equity?: number | null;
  start_equity?: number | null;
}

interface DashboardCustomDataBindingRecord {
  factor_name: string;
  source: string;
  path: string;
  field: string;
  record_count?: number;
  first_timestamp?: string | null;
  last_timestamp?: string | null;
  point_in_time_status?: "complete" | "partial" | "missing";
  replay_warnings?: string[];
}

interface DashboardSignalRecord {
  signal_id: string;
  run_id: string;
  strategy_id: string;
  strategy_name: string;
  symbol: string;
  timestamp: string;
  action: string;
  side: string;
  source: string;
  price: number;
}

interface DashboardReviewRecord {
  signal_id: string;
  strategy_id: string;
  strategy_name: string;
  verdict: string;
  confidence: number;
  model: string;
  created_at: string;
  action_suggestion: string;
  path: string;
}

interface DashboardContextRecord {
  signal_id: string;
  symbol: string;
  generated_at: string;
  event_count?: number;
  macro_count?: number;
  news_count?: number;
}

interface DashboardOrderRecord {
  id: string;
  signal_id: string;
  strategy_name: string;
  symbol: string;
  side: string;
  qty: number;
  status: string;
  submitted_at: string;
}

interface DashboardPaperPositionRecord {
  symbol: string;
  qty: number;
  market_value?: number | null;
  cost_basis?: number | null;
  unrealized_pl?: number | null;
  unrealized_plpc?: number | null;
  current_price?: number | null;
  side?: string;
  updated_at?: string;
  path?: string;
}

interface DashboardPaperReadinessCheckRecord {
  name?: string;
  status?: "ok" | "warning" | "blocked";
  message?: string;
  suggested_actions?: string[];
}

interface DashboardPaperReadinessRecord {
  strategy_name?: string;
  strategy_id?: string;
  status?: "ok" | "warning" | "blocked";
  ready?: boolean;
  generated_at?: string | null;
  path?: string;
  report_markdown_path?: string | null;
  blocking_checks?: string[];
  warning_checks?: string[];
  checks?: DashboardPaperReadinessCheckRecord[];
}

interface DashboardAuditRecord {
  id: string;
  kind: string;
  created_at: string;
  action: string;
  target: string;
  source_path: string;
}

interface DashboardGroupRecord {
  group_id: string;
  category: string;
  label: string;
  strategy_ids?: string[];
  strategy_count?: number;
  active_strategy_count?: number;
  risk_tiers?: RiskLevel[];
}

interface DashboardDataComparisonRecord {
  symbol: string;
  timeframe: string;
  left_source: string;
  right_source: string;
  matched_coverage_pct?: number;
  report_json_path?: string;
}

interface DashboardFeaturePacketRecord {
  path: string;
  record_count?: number;
  first_timestamp?: string | null;
  last_timestamp?: string | null;
  point_in_time_status?: "complete" | "partial" | "missing";
  replay_warnings?: string[];
}

interface DashboardWorkflowReportRecord {
  strategy_name?: string;
  strategy_id?: string;
  status?: "ok" | "warning" | "blocked";
  source_path?: string;
  spec_hash?: string | null;
  backtest_run_id?: string | null;
  scan_signal_count?: number;
  paper_readiness_status?: "ok" | "warning" | "blocked" | null;
  paper_ready?: boolean;
  output_paths?: string[];
  path?: string;
  report_markdown_path?: string | null;
}

interface DashboardResearchReportRecord {
  strategy_name?: string;
  kind?: string;
  status?: OperationalStatus;
  ready?: boolean;
  report_json_path?: string;
  report_markdown_path?: string | null;
  next_action?: string;
}

interface DashboardResearchRunRecord {
  run_id?: string;
  generated_at?: string | null;
  strategy_name?: string;
  source_spec_path?: string;
  status?: OperationalStatus;
  kind?: string;
  research_mode?: "playground" | "audited" | null;
  data_profile?: Record<string, unknown>;
  candidate_count?: number;
  trial_count?: number;
  runtime_seconds?: number | null;
  gate_status?: OperationalStatus;
  blocked_items?: string[];
  warning_items?: string[];
  report_path?: string | null;
  json_path?: string | null;
  artifact_count?: number;
  next_action?: string;
}

interface DashboardOperationalCheckRecord {
  name?: string;
  status?: "ok" | "warning" | "blocked";
  message?: string;
  suggested_actions?: string[];
  details?: Record<string, unknown>;
}

interface DashboardDeploymentStepRecord extends DashboardOperationalCheckRecord {
  output_paths?: string[];
}

interface DashboardReadinessReportRecord {
  status?: "ok" | "warning" | "blocked";
  ready?: boolean;
  generated_at?: string | null;
  path?: string;
  report_markdown_path?: string | null;
  checks?: DashboardOperationalCheckRecord[];
}

interface DashboardDeploymentReportRecord {
  status?: "ok" | "warning" | "blocked";
  ready?: boolean;
  generated_at?: string | null;
  path?: string;
  report_markdown_path?: string | null;
  steps?: DashboardDeploymentStepRecord[];
}

let catalog = (rawCatalog ?? {}) as DashboardCatalog;
let summaryRecord = catalog.summary ?? {};
let catalogGeneratedAt =
  catalog.generated_at ?? summaryRecord.generated_at ?? null;
let allRuns = asArray(catalog.runs);
let allVersions = asArray(catalog.versions);
let allProjects = asArray(catalog.projects);
let allPaperReadiness = asArray(catalog.paper_readiness_reports);
let allResearchRuns = asArray(catalog.research_runs);
let versionById = new Map(
  allVersions.map((version) => [version.version_id, version]),
);
let paperReadinessByStrategy = buildPaperReadinessByStrategy();

export let dashboardSummary: DashboardSummaryView = buildDashboardSummary();
export let strategies: Strategy[] = buildStrategies();
export let projects: StrategyProject[] = buildProjects();
export let recentSignals: RecentSignal[] = buildRecentSignals();
export let events: TimelineEvent[] = buildTimelineEvents();
export let llmReviews: LLMReview[] = buildLLMReviews();
export let auditLog: AuditLogEntry[] = buildAuditLog();
export let versions: VersionEntry[] = buildVersions();
export let strategyGroups: StrategyGroup[] = buildStrategyGroups();
export let paperPositions: PaperPosition[] = buildPaperPositions();
export let paperOrders = buildPaperOrders();
export let paperReadinessReports: PaperReadinessReport[] =
  buildPaperReadinessReports();
export let researchRuns: ResearchRun[] = buildResearchRuns();

export function applyDashboardCatalog(nextCatalog: DashboardCatalog): void {
  catalog = nextCatalog ?? {};
  summaryRecord = catalog.summary ?? {};
  catalogGeneratedAt =
    catalog.generated_at ?? summaryRecord.generated_at ?? null;
  allRuns = asArray(catalog.runs);
  allVersions = asArray(catalog.versions);
  allProjects = asArray(catalog.projects);
  allPaperReadiness = asArray(catalog.paper_readiness_reports);
  allResearchRuns = asArray(catalog.research_runs);
  versionById = new Map(
    allVersions.map((version) => [version.version_id, version]),
  );
  paperReadinessByStrategy = buildPaperReadinessByStrategy();

  dashboardSummary = buildDashboardSummary();
  strategies = buildStrategies();
  projects = buildProjects();
  recentSignals = buildRecentSignals();
  llmReviews = buildLLMReviews();
  auditLog = buildAuditLog();
  versions = buildVersions();
  paperPositions = buildPaperPositions();
  paperOrders = buildPaperOrders();
  paperReadinessReports = buildPaperReadinessReports();
  researchRuns = buildResearchRuns();
  events = buildTimelineEvents();
  strategyGroups = buildStrategyGroups();

  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("dashboard-catalog-updated"));
  }
}

function buildDashboardSummary(): DashboardSummaryView {
  return {
    catalogPath,
    generatedAt: catalogGeneratedAt,
    generatedLabel: formatDateTime(catalogGeneratedAt),
    sourceRoot: summaryRecord.source_root ?? catalog.source_root ?? "",
    readModelVersion: summaryRecord.read_model_version ?? "1",
    strategyCount:
      summaryRecord.strategy_count ?? asArray(catalog.strategies).length,
    activeStrategyCount:
      summaryRecord.active_strategy_count ?? lifecycleCount("active"),
    approvedStrategyCount: lifecycleCount("approved"),
    draftStrategyCount: lifecycleCount("draft"),
    retiredStrategyCount: lifecycleCount("retired"),
    versionCount: summaryRecord.version_count ?? allVersions.length,
    runCount: summaryRecord.run_count ?? allRuns.length,
    signalCount: summaryRecord.signal_count ?? asArray(catalog.signals).length,
    reviewCount: summaryRecord.review_count ?? asArray(catalog.reviews).length,
    contextCount:
      summaryRecord.context_count ?? asArray(catalog.contexts).length,
    journalCount: summaryRecord.journal_count ?? 0,
    orderCount: summaryRecord.order_count ?? asArray(catalog.orders).length,
    auditCount: summaryRecord.audit_count ?? asArray(catalog.audits).length,
    dataComparisonCount:
      summaryRecord.data_comparison_count ??
      asArray(catalog.data_comparisons).length,
    featurePacketCount:
      summaryRecord.feature_packet_count ??
      asArray(catalog.feature_packets).length,
    workflowReportCount:
      summaryRecord.workflow_report_count ??
      asArray(catalog.workflow_reports).length,
    researchReportCount:
      summaryRecord.research_report_count ??
      asArray(catalog.research_reports).length,
    researchRunCount:
      summaryRecord.research_run_count ?? allResearchRuns.length,
    researchBlockedCount:
      summaryRecord.research_blocked_count ??
      allResearchRuns.filter((run) => run.status === "blocked").length,
    researchWarningCount:
      summaryRecord.research_warning_count ??
      allResearchRuns.filter((run) => run.status === "warning").length,
    projectCount: summaryRecord.project_count ?? allProjects.length,
    projectBlockedCount:
      summaryRecord.project_blocked_count ??
      allProjects.filter((project) => project.state === "blocked").length,
    projectIteratingCount:
      summaryRecord.project_iterating_count ??
      allProjects.filter(
        (project) =>
          project.state === "researching" || project.state === "iterating",
      ).length,
    projectCandidateCount:
      summaryRecord.project_candidate_count ??
      allProjects.filter((project) => project.state === "candidate").length,
    projectActivePaperCount:
      summaryRecord.project_active_paper_count ??
      allProjects.filter((project) => project.state === "active_paper").length,
    readinessStatus:
      summaryRecord.readiness_status ??
      catalog.readiness_report?.status ??
      "missing",
    readinessReady:
      summaryRecord.readiness_ready ?? Boolean(catalog.readiness_report?.ready),
    readinessWarningCount:
      summaryRecord.readiness_warning_count ??
      operationalCount(catalog.readiness_report?.checks, "warning"),
    readinessBlockedCount:
      summaryRecord.readiness_blocked_count ??
      operationalCount(catalog.readiness_report?.checks, "blocked"),
    deploymentStatus:
      summaryRecord.deployment_status ??
      catalog.deployment_report?.status ??
      "missing",
    deploymentReady:
      summaryRecord.deployment_ready ??
      Boolean(catalog.deployment_report?.ready),
    deploymentWarningCount:
      summaryRecord.deployment_warning_count ??
      operationalCount(catalog.deployment_report?.steps, "warning"),
    deploymentBlockedCount:
      summaryRecord.deployment_blocked_count ??
      operationalCount(catalog.deployment_report?.steps, "blocked"),
    deploymentNextAction: firstSuggestedAction(
      catalog.deployment_report?.steps,
    ),
    readinessNextAction: firstSuggestedAction(catalog.readiness_report?.checks),
    paperAutoStrategyCount: summaryRecord.paper_auto_strategy_count ?? 0,
    paperOpenOrderCount: summaryRecord.paper_open_order_count ?? 0,
    paperPositionCount: summaryRecord.paper_position_count ?? 0,
    paperKillSwitchEnabled: summaryRecord.paper_kill_switch_enabled ?? false,
    paperReconciliationStatus:
      summaryRecord.paper_reconciliation_status ?? "unknown",
    paperAlertStatus: summaryRecord.paper_alert_status ?? "unknown",
    paperAccountEquity: summaryRecord.paper_account_equity ?? null,
    paperAccountCash: summaryRecord.paper_account_cash ?? null,
    paperAccountSnapshotAt: summaryRecord.paper_account_snapshot_at ?? null,
    paperPositionsSnapshotAt: summaryRecord.paper_positions_snapshot_at ?? null,
    paperTotalUnrealizedPl: summaryRecord.paper_total_unrealized_pl ?? 0,
    paperReadinessCount: summaryRecord.paper_readiness_count ?? 0,
    paperReadinessStatusCounts:
      summaryRecord.paper_readiness_status_counts ?? {},
    backendStatusCounts: summaryRecord.backend_status_counts ?? {},
    modelRoleCounts: summaryRecord.model_role_counts ?? {},
    riskCounts: summaryRecord.risk_counts ?? {},
    lifecycleCounts: summaryRecord.lifecycle_counts ?? {},
    compatibilityCounts: summaryRecord.compatibility_counts ?? {},
    notes: summaryRecord.notes ?? [],
  };
}

function buildStrategies(): Strategy[] {
  return asArray(catalog.strategies).map((strategy) => {
    const latestRun = latestRunFor(strategy.strategy_id);
    const version =
      versionById.get(strategy.current_version_id ?? "") ??
      allVersions.find((record) => record.strategy_id === strategy.strategy_id);
    const compatibility = strategy.compatibility ?? {};
    const versionLabel = shortVersion(
      strategy.current_version_id ?? version?.version_id,
    );
    const contentHash = version?.content_hash;
    const totalReturn = latestRun?.total_return_pct ?? 0;

    return {
      id: strategy.strategy_id,
      name: humanize(strategy.strategy_name),
      symbol: strategy.symbol,
      timeframe: strategy.timeframe,
      version: versionLabel,
      status: strategy.lifecycle,
      modelClass: normalizeModelClass(strategy.model_role),
      risk: strategy.risk_tier ?? "moderate",
      group: modelRoleLabel(strategy.model_role),
      pine: compatibility.tradingview_pine_strategy === "supported",
      python: isRunnable(compatibility.python_mvp_backtest),
      alpaca: compatibility.alpaca_paper_execution === "supported",
      lastReturn: round(totalReturn, 2),
      sharpe: round(latestRun?.sharpe_ratio ?? 0, 2),
      trades: latestRun?.trades ?? latestRun?.signals ?? 0,
      series: seededSeries(contentHash ?? strategy.strategy_id, totalReturn),
      backend: strategy.backend ?? "python_reference",
      backendStatus: strategy.backend_status ?? "partial",
      backendReasons: strategy.backend_reasons ?? [],
      backendPlanPath: latestRun?.backend_plan_path ?? null,
      paperReadinessReportPath: latestRun?.paper_readiness_report_path ?? null,
      paperReadiness:
        paperReadinessByStrategy.get(strategy.strategy_id) ?? null,
      customDataBindings: buildCustomDataBindings(
        latestRun?.custom_data_bindings,
      ),
      broker: strategy.broker ?? "none",
      dataSource: strategy.data_source ?? "unknown",
      executionMode: strategy.execution_mode ?? "manual_signal",
      sourcePath: strategy.source_paths?.[0] ?? version?.primary_path ?? "",
      specHash: latestRun?.spec_hash ?? contentHash ?? null,
      note: version?.note ?? "",
      factors: strategy.factor_names ?? [],
      requiredCapabilities: strategy.required_capabilities ?? [],
      compatibility,
      compatibilityReasons: strategy.compatibility_reasons ?? {},
      llmReviewEnabled: strategy.llm_review_enabled ?? false,
      llmReviewModel: strategy.llm_review_model ?? null,
    };
  });
}

function buildProjects(): StrategyProject[] {
  const derived =
    allProjects.length > 0 ? allProjects : deriveProjectsFromStrategies();
  return derived
    .slice()
    .sort(
      (left, right) =>
        projectSortWeight(left) - projectSortWeight(right) ||
        left.name.localeCompare(right.name),
    )
    .map((project) => ({
      projectId: project.project_id,
      name: humanize(project.name),
      state: project.state,
      thesis: project.thesis ?? "",
      currentSpecPath: project.current_spec_path ?? null,
      latestRunPath: project.latest_run_path ?? null,
      gateSummary: {
        workflowPass: project.gate_summary?.workflow_pass ?? null,
        researchPass: project.gate_summary?.research_pass ?? null,
        llmContributionPass:
          project.gate_summary?.llm_contribution_pass ?? null,
        paperReadyPass: project.gate_summary?.paper_ready_pass ?? null,
        status: project.gate_summary?.status ?? "unknown",
        blockedChecks: project.gate_summary?.blocked_checks ?? [],
        warningChecks: project.gate_summary?.warning_checks ?? [],
      },
      evidence: {
        factorQuality: buildProjectEvidenceItem(
          project.evidence?.factor_quality,
        ),
        executionReality: buildProjectEvidenceItem(
          project.evidence?.execution_reality,
        ),
        altLLMEvidence: buildProjectEvidenceItem(
          project.evidence?.alt_llm_evidence,
        ),
      },
      artifactState: buildProjectControlState(project.artifact_state),
      latestRunSummary: buildProjectRunLedger(project.latest_run_summary),
      blockerSummary: buildProjectBlockerSummary(project.blocker_summary),
      nextMinimalActions: asStringArray(project.next_minimal_actions),
      doNotRepeat: asStringArray(project.do_not_repeat),
      blockers: project.blockers ?? [],
      nextAction: project.next_action ?? "",
      currentRound: project.current_round ?? 0,
      maxRounds: project.max_rounds ?? 5,
      iterationMode: project.iteration_mode ?? "auto_continue_until_stop",
      stopReason: project.stop_reason ?? null,
      userRequestedStop: project.user_requested_stop ?? false,
      paperStatus: project.paper_status ?? "not_requested",
      archived: project.archived ?? false,
      importedFromStrategy: project.imported_from_strategy ?? false,
      createdAt: project.created_at ?? null,
      updatedAt: project.updated_at ?? null,
    }));
}

function deriveProjectsFromStrategies(): DashboardProjectRecord[] {
  return asArray(catalog.strategies).map((strategy) => {
    const latestRun = latestRunFor(strategy.strategy_id);
    return {
      project_id: strategy.strategy_id,
      name: strategy.strategy_name,
      state:
        strategy.lifecycle === "active"
          ? "candidate"
          : strategy.lifecycle === "draft"
            ? "draft"
            : "candidate",
      thesis: strategy.note ?? "",
      current_spec_path: strategy.source_paths?.[0] ?? null,
      latest_run_path: latestRun?.report_path ?? latestRun?.source_path ?? null,
      gate_summary: {
        workflow_pass: strategy.lifecycle !== "draft",
        research_pass: latestRun?.kind === "paper" ? true : null,
        llm_contribution_pass: strategy.llm_review_enabled ? null : null,
        paper_ready_pass: null,
        status: "unknown",
        blocked_checks: [],
        warning_checks: [],
      },
      evidence: {
        factor_quality: {
          status:
            strategy.factor_names.length > 0 ? "unknown" : "not_applicable",
          summary:
            strategy.factor_names.length > 0
              ? "Factor diagnostics have not been linked yet."
              : "No factor lab evidence is required.",
          artifact_path: null,
          blockers: [],
          updated_at: null,
        },
        execution_reality: {
          status: "unknown",
          summary: "Execution reality evidence has not been linked yet.",
          artifact_path: null,
          blockers: [],
          updated_at: null,
        },
        alt_llm_evidence: {
          status:
            strategy.llm_review_enabled ||
            strategy.llm_feature_factor_names?.length ||
            strategy.feature_packet_factor_names?.length
              ? "unknown"
              : "not_applicable",
          summary:
            strategy.llm_review_enabled ||
            strategy.llm_feature_factor_names?.length ||
            strategy.feature_packet_factor_names?.length
              ? "Alt/LLM evidence has not been linked yet."
              : "No LLM or alternative-data factor is declared.",
          artifact_path: null,
          blockers: [],
          updated_at: null,
        },
      },
      artifact_state: {},
      latest_run_summary: {},
      blocker_summary: {},
      next_minimal_actions: [],
      do_not_repeat: [],
      blockers: [],
      next_action:
        strategy.lifecycle === "active"
          ? "review_project_evidence"
          : "create_or_link_strategy_project",
      current_round: 0,
      max_rounds: 5,
      iteration_mode: "auto_continue_until_stop",
      stop_reason: null,
      user_requested_stop: false,
      paper_status:
        strategy.lifecycle === "active" ? "review_requested" : "not_requested",
      archived: strategy.lifecycle === "retired",
      imported_from_strategy: true,
      created_at: null,
      updated_at: null,
    };
  });
}

function buildCustomDataBindings(
  bindings: DashboardCustomDataBindingRecord[] | undefined,
): CustomDataBinding[] {
  return asArray(bindings).map((binding) => ({
    factorName: binding.factor_name,
    source: binding.source,
    path: binding.path,
    field: binding.field,
    recordCount: binding.record_count ?? 0,
    firstTimestamp: binding.first_timestamp ?? null,
    lastTimestamp: binding.last_timestamp ?? null,
    pointInTimeStatus: binding.point_in_time_status ?? "missing",
    replayWarnings: binding.replay_warnings ?? [],
  }));
}

function buildProjectEvidenceItem(
  item: DashboardProjectEvidenceItemRecord | undefined,
): ProjectEvidenceItem {
  return {
    status: item?.status ?? "unknown",
    summary: item?.summary ?? "No evidence has been linked yet.",
    artifactPath: item?.artifact_path ?? null,
    blockers: item?.blockers ?? [],
    updatedAt: item?.updated_at ?? null,
  };
}

function buildProjectControlState(
  value: Record<string, unknown> | undefined,
): ProjectControlState {
  const record = value ?? {};
  const artifacts = isRecord(record.latest_artifacts)
    ? record.latest_artifacts
    : {};
  return {
    lastSuccessfulStep:
      typeof record?.last_successful_step === "string"
        ? record.last_successful_step
        : "unknown",
    latestArtifacts: Object.fromEntries(
      Object.entries(artifacts).map(([key, value]) => [key, String(value)]),
    ),
    blockedItems: asStringArray(record?.blocked_items),
    warningItems: asStringArray(record?.warning_items),
  };
}

function buildProjectRunLedger(
  record: Record<string, unknown> | undefined,
): ProjectRunLedger | null {
  if (!record || Object.keys(record).length === 0) return null;
  return {
    status: typeof record.status === "string" ? record.status : "unknown",
    round: typeof record.round === "number" ? record.round : null,
    taskType:
      typeof record.task_type === "string" ? record.task_type : "unknown",
    changedPaths: asStringArray(record.changed_paths),
    stepEvents: asArray(record.step_events)
      .filter(isRecord)
      .map((event) => ({
        stepName:
          typeof event.step_name === "string" ? event.step_name : "unknown",
        status: typeof event.status === "string" ? event.status : "unknown",
        outputArtifacts: asStringArray(event.output_artifacts),
        blockedItems: asStringArray(event.blocked_items),
        warningItems: asStringArray(event.warning_items),
      })),
  };
}

function buildProjectBlockerSummary(
  record: Record<string, unknown> | undefined,
): StrategyProject["blockerSummary"] {
  if (!record || Object.keys(record).length === 0) return null;
  return {
    trigger: typeof record.trigger === "string" ? record.trigger : "blocked",
    failedStep:
      typeof record.failed_step === "string" ? record.failed_step : "unknown",
    rootBlockers: asStringArray(record.root_blockers),
    nextMinimalActions: asStringArray(record.next_minimal_actions),
    doNotRepeat: asStringArray(record.do_not_repeat),
    artifactRefs: asStringArray(record.artifact_refs),
  };
}

function projectSortWeight(project: DashboardProjectRecord): number {
  const order: Record<ProjectState, number> = {
    blocked: 0,
    paper_review: 1,
    active_paper: 2,
    iterating: 3,
    researching: 4,
    candidate: 5,
    draft: 6,
    idea: 7,
    retired: 8,
  };
  return order[project.state] ?? 99;
}

function buildRecentSignals(): RecentSignal[] {
  return asArray(catalog.signals)
    .slice()
    .sort((left, right) => compareDateDesc(left.timestamp, right.timestamp))
    .slice(0, 10)
    .map((signal) => ({
      id: signal.signal_id,
      t: formatTime(signal.timestamp),
      strat: humanize(signal.strategy_name),
      side: signal.side.toUpperCase(),
      px: signal.price,
      sz: 0,
      tag: signal.action || signal.source,
      symbol: signal.symbol,
    }));
}

function buildLLMReviews(): LLMReview[] {
  return asArray(catalog.reviews)
    .slice()
    .sort((left, right) => compareDateDesc(left.created_at, right.created_at))
    .slice(0, 12)
    .map((review) => ({
      id: review.signal_id,
      strat: humanize(review.strategy_name),
      verdict: review.verdict,
      summary: `${review.action_suggestion} (${Math.round(review.confidence * 100)}% confidence)`,
      color: reviewColor(review.verdict),
    }));
}

function buildAuditLog(): AuditLogEntry[] {
  return asArray(catalog.audits)
    .slice()
    .sort((left, right) => compareDateDesc(left.created_at, right.created_at))
    .slice(0, 20)
    .map((audit) => ({
      t: formatDateTime(audit.created_at),
      who: audit.kind.includes("journal") ? "user" : "system",
      action: audit.action,
      target: audit.target,
    }));
}

function buildVersions(): VersionEntry[] {
  return allVersions
    .slice()
    .sort((left, right) =>
      compareDateDesc(
        left.modified_at ?? left.created_at,
        right.modified_at ?? right.created_at,
      ),
    )
    .map((version) => ({
      id: shortVersion(version.version_id),
      strat: humanize(version.strategy_name),
      parent: shortVersion(version.parent_version_id) || "root",
      by: version.created_by ?? "file_scan",
      at: formatDateTime(version.modified_at ?? version.created_at),
      status: version.primary_lifecycle ?? version.lifecycle,
      diff: `${version.factor_names?.length ?? 0} factors`,
      hash: shortHash(version.content_hash),
    }));
}

function buildPaperPositions(): PaperPosition[] {
  return asArray(catalog.paper_positions).map((position) => {
    const qty = position.qty ?? 0;
    const avg = qty === 0 ? 0 : Math.abs((position.cost_basis ?? 0) / qty);
    const mkt =
      position.current_price ??
      (qty === 0 ? 0 : Math.abs((position.market_value ?? 0) / qty));
    const linkedOrder = asArray(catalog.orders)
      .slice()
      .reverse()
      .find((order) => order.symbol === position.symbol);

    return {
      sym: position.symbol,
      qty,
      avg: round(avg, 2),
      mkt: round(mkt, 2),
      upnl: round(position.unrealized_pl ?? 0, 2),
      strat: linkedOrder
        ? humanize(linkedOrder.strategy_name)
        : "Paper account",
    };
  });
}

function buildPaperOrders() {
  return asArray(catalog.orders).map((order) => ({
    id: order.id,
    signalId: order.signal_id,
    strategy: humanize(order.strategy_name),
    symbol: order.symbol,
    side: order.side.toUpperCase(),
    qty: order.qty,
    status: order.status,
    submittedAt: formatDateTime(order.submitted_at),
  }));
}

function buildPaperReadinessReports(): PaperReadinessReport[] {
  return allPaperReadiness
    .slice()
    .sort((left, right) =>
      compareDateDesc(left.generated_at, right.generated_at),
    )
    .map((report) => ({
      strategyId: report.strategy_id ?? report.strategy_name ?? "unknown",
      strategyName: humanize(
        report.strategy_name ?? report.strategy_id ?? "unknown",
      ),
      status: report.status ?? "blocked",
      ready: Boolean(report.ready),
      generatedAt: report.generated_at ?? null,
      path: report.path ?? "",
      markdownPath: report.report_markdown_path ?? null,
      blockingChecks: report.blocking_checks ?? [],
      warningChecks: report.warning_checks ?? [],
      checks: asArray(report.checks).map((check) => ({
        name: check.name ?? "",
        status: check.status ?? "blocked",
        message: check.message ?? "",
        suggestedActions: check.suggested_actions ?? [],
      })),
    }));
}

function buildPaperReadinessByStrategy(): Map<string, PaperReadinessReport> {
  return new Map(
    buildPaperReadinessReports().map((report) => [report.strategyId, report]),
  );
}

function buildResearchRuns(): ResearchRun[] {
  return allResearchRuns
    .slice()
    .sort((left, right) =>
      compareDateDesc(left.generated_at, right.generated_at),
    )
    .map((run) => {
      const dataProfile = run.data_profile ?? {};
      return {
        id: run.run_id ?? "research-run",
        generatedAt: run.generated_at ?? null,
        strategyName: humanize(run.strategy_name ?? "unknown"),
        kind: run.kind ?? "research_report",
        researchMode: run.research_mode ?? null,
        status: run.status ?? "warning",
        gateStatus: run.gate_status ?? run.status ?? "warning",
        sourceSpecPath: run.source_spec_path ?? "",
        reportPath: run.report_path ?? null,
        jsonPath: run.json_path ?? null,
        candidateCount: run.candidate_count ?? 0,
        trialCount: run.trial_count ?? 0,
        runtimeSeconds: run.runtime_seconds ?? null,
        blockedItems: run.blocked_items ?? [],
        warningItems: run.warning_items ?? [],
        dataSourceMode: String(
          dataProfile.source_mode ?? dataProfile.status ?? "unknown",
        ),
        dataAsOf:
          typeof dataProfile.data_as_of === "string"
            ? dataProfile.data_as_of
            : null,
        artifactCount: run.artifact_count ?? 0,
        nextAction: run.next_action ?? "",
      };
    });
}

function latestRunFor(strategyId: string): DashboardRunRecord | undefined {
  return allRuns
    .filter((run) => run.strategy_id === strategyId)
    .sort((left, right) => compareRunDesc(left, right))[0];
}

function buildTimelineEvents(): TimelineEvent[] {
  const rows: TimelineEvent[] = [];

  if (catalogGeneratedAt) {
    rows.push({
      t: formatTime(catalogGeneratedAt),
      kind: "Catalog",
      title: `Read model rebuilt from ${dashboardSummary.strategyCount} strategies, ${dashboardSummary.runCount} runs and ${dashboardSummary.signalCount} signals`,
      impact: "low",
    });
  }

  if (catalog.deployment_report) {
    rows.push({
      t: formatTime(catalog.deployment_report.generated_at),
      kind: "Deploy",
      title: `Deployment ${catalog.deployment_report.status ?? "warning"} · ${dashboardSummary.deploymentWarningCount} warnings · ${dashboardSummary.deploymentNextAction ?? "no action"}`,
      impact: operationalImpact(catalog.deployment_report.status),
    });
  }

  if (catalog.readiness_report) {
    rows.push({
      t: formatTime(catalog.readiness_report.generated_at),
      kind: "Readiness",
      title: `Readiness ${catalog.readiness_report.status ?? "warning"} · ready ${catalog.readiness_report.ready ? "yes" : "no"} · ${dashboardSummary.readinessNextAction ?? "no action"}`,
      impact: operationalImpact(catalog.readiness_report.status),
    });
  }

  for (const comparison of asArray(catalog.data_comparisons).slice(0, 5)) {
    const coverage = comparison.matched_coverage_pct ?? 0;
    rows.push({
      t: comparison.timeframe,
      kind: "Data",
      title: `${comparison.symbol}: ${comparison.left_source} / ${comparison.right_source} coverage ${coverage.toFixed(1)}%`,
      impact: coverage >= 95 ? "low" : coverage >= 80 ? "med" : "high",
    });
  }

  for (const packet of asArray(catalog.feature_packets).slice(0, 5)) {
    rows.push({
      t: formatTime(packet.last_timestamp ?? packet.first_timestamp),
      kind: "Feature",
      title: `${packet.path} contains ${packet.record_count ?? 0} records; PIT ${packet.point_in_time_status ?? "missing"}`,
      impact: packet.point_in_time_status === "complete" ? "low" : "high",
    });
  }

  for (const workflow of asArray(catalog.workflow_reports).slice(0, 5)) {
    rows.push({
      t: workflow.status ?? "warning",
      kind: "Workflow",
      title: `${humanize(workflow.strategy_name ?? workflow.strategy_id)} verification: ${workflow.status ?? "warning"} · ${workflow.scan_signal_count ?? 0} scan signals`,
      impact:
        workflow.status === "ok"
          ? "low"
          : workflow.status === "blocked"
            ? "high"
            : "med",
    });
  }

  for (const context of asArray(catalog.contexts).slice(0, 5)) {
    const total =
      (context.event_count ?? 0) +
      (context.macro_count ?? 0) +
      (context.news_count ?? 0);
    rows.push({
      t: formatTime(context.generated_at),
      kind: "Context",
      title: `${context.symbol}: ${total} context records linked to ${context.signal_id}`,
      impact: total > 0 ? "med" : "low",
    });
  }

  for (const note of dashboardSummary.notes.slice(
    0,
    Math.max(0, 6 - rows.length),
  )) {
    rows.push({
      t: "note",
      kind: "Status",
      title: note,
      impact: note.toLowerCase().includes("no ") ? "med" : "low",
    });
  }

  return rows.slice(0, 10);
}

function buildStrategyGroups(): StrategyGroup[] {
  const modelGroups = asArray(catalog.groups).filter(
    (group) => group.category === "model_role",
  );
  const fallbackGroups = asArray(catalog.groups).filter((group) =>
    ["risk_tier", "backend", "data_source"].includes(group.category),
  );
  const source = modelGroups.length > 0 ? modelGroups : fallbackGroups;
  const total = Math.max(1, dashboardSummary.strategyCount);

  return source.slice(0, 8).map((group, index) => ({
    id: group.group_id,
    name: groupLabel(group),
    weight: Math.round(((group.strategy_count ?? 0) / total) * 100),
    color: ["green", "cyan", "purple", "orange", "black", "pink"][
      index % 6
    ] as StrategyGroup["color"],
    risk: group.risk_tiers?.includes("high")
      ? "high"
      : group.risk_tiers?.includes("moderate")
        ? "moderate"
        : "stable",
    children: asArray(group.strategy_ids).map(
      (id) =>
        strategies.find((strategy) => strategy.id === id)?.name ?? humanize(id),
    ),
    category: group.category,
  }));
}

function groupLabel(group: DashboardGroupRecord): string {
  if (group.category === "model_role") {
    return modelRoleLabel(group.label as DashboardStrategyRecord["model_role"]);
  }
  return humanize(group.label);
}

function isRunnable(status?: CapabilityStatus): boolean {
  return status === "supported" || status === "partial";
}

function normalizeModelClass(
  role?: DashboardStrategyRecord["model_role"],
): ModelClass {
  switch (role) {
    case "quant_review":
      return "quant-review";
    case "quant_scan":
      return "quant-scan";
    case "quant_orchestrator":
      return "quant-orchestrator";
    default:
      return "pure-quant";
  }
}

function modelRoleLabel(role?: DashboardStrategyRecord["model_role"]): string {
  switch (role) {
    case "quant_review":
      return "Quant review";
    case "quant_scan":
      return "Quant scan";
    case "quant_orchestrator":
      return "Quant orchestrator";
    default:
      return "Pure quant";
  }
}

function lifecycleCount(lifecycle: Strategy["status"]): number {
  return summaryRecord.lifecycle_counts?.[lifecycle] ?? 0;
}

function operationalCount(
  checks:
    | DashboardOperationalCheckRecord[]
    | DashboardDeploymentStepRecord[]
    | undefined,
  status: "warning" | "blocked",
): number {
  return asArray(checks).filter((check) => check.status === status).length;
}

function firstSuggestedAction(
  checks:
    | DashboardOperationalCheckRecord[]
    | DashboardDeploymentStepRecord[]
    | undefined,
): string | null {
  for (const check of asArray(checks)) {
    const action = check.suggested_actions?.[0];
    if (action) {
      return action;
    }
  }
  return null;
}

function operationalImpact(
  status?: "ok" | "warning" | "blocked",
): TimelineEvent["impact"] {
  if (status === "ok") {
    return "low";
  }
  if (status === "blocked") {
    return "high";
  }
  return "med";
}

function reviewColor(verdict: string): LLMReview["color"] {
  const normalized = verdict.toLowerCase();
  if (normalized.includes("reject") || normalized.includes("needs")) {
    return "pink";
  }
  if (normalized.includes("caveat") || normalized.includes("consider")) {
    return "orange";
  }
  if (normalized.includes("approve")) {
    return "green";
  }
  return "cyan";
}

function seededSeries(seedText: string, returnPct: number, n = 28): number[] {
  let seed = 0;
  for (const char of seedText) {
    seed = (seed * 31 + char.charCodeAt(0)) >>> 0;
  }

  const start = 100;
  const end = start * (1 + returnPct / 100);
  const out: number[] = [];
  for (let i = 0; i < n; i += 1) {
    seed = (1664525 * seed + 1013904223) >>> 0;
    const progress = i / Math.max(1, n - 1);
    const drift = start + (end - start) * progress;
    const noise = (seed / 0xffffffff - 0.5) * 2;
    const dampener = Math.sin(progress * Math.PI);
    out.push(round(drift + noise * dampener * 2.4, 2));
  }
  out[n - 1] = round(end, 2);
  return out;
}

function compareRunDesc(
  left: DashboardRunRecord,
  right: DashboardRunRecord,
): number {
  return String(right.run_id).localeCompare(String(left.run_id));
}

function compareDateDesc(left?: string | null, right?: string | null): number {
  return dateValue(right) - dateValue(left);
}

function dateValue(value?: string | null): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function formatTime(value?: string | null): string {
  if (!value) {
    return "n/a";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "not generated";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function shortVersion(version?: string | null): string {
  if (!version) {
    return "";
  }
  return version.startsWith("ver_") ? `ver_${version.slice(4, 10)}` : version;
}

function shortHash(hash?: string | null): string {
  if (!hash) {
    return "n/a";
  }
  return `${hash.slice(0, 6)}..${hash.slice(-4)}`;
}

function humanize(value?: string | null): string {
  if (!value) {
    return "Unknown";
  }
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function asArray<T>(value: T[] | undefined | null): T[];
function asArray<T = unknown>(value: unknown): T[];
function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asStringArray(value: unknown): string[] {
  return asArray(value)
    .map((item) => String(item))
    .filter(Boolean);
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
