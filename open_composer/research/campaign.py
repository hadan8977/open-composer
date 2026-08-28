from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from open_composer.config import project_root

CAMPAIGN_ROOT = Path("reports/research/campaigns")
CAMPAIGN_FILENAME = "research-campaign-contract.json"
CAMPAIGN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,96}$")
CAMPAIGN_STAGES = {"pre-discovery", "pre-oos", "final"}

# Statistical family DSR/PBO/SPA trial counting is scoped to the current
# economic-mechanism family only (see docs/plan-gate-recalibration-and-research-
# velocity-2026-08-26.zh.md Work Item A1). Unrelated historical searches from
# earlier, unconnected hypotheses must not inflate this campaign's multiple-
# testing penalty; ``prior_effective_trial_count`` remains a lifetime diagnostic
# field but is intentionally excluded from the family-scoped count below.
MAX_FAMILY_EFFECTIVE_TRIAL_COUNT = 32

# A candidate whose absolute correlation to QQQ is at or below this
# threshold is economically orthogonal: its up/downside capture ratio
# relative to QQQ is not a meaningful pass/fail signal (a genuinely
# uncorrelated strategy's capture ratio is dominated by noise, not skill),
# so the capture-ratio gates become diagnostics instead of blockers.
QQQ_ORTHOGONALITY_CORRELATION_THRESHOLD = 0.3

# A2: DSR/PBO/SPA must be computed on a stitched, multi-year rolling-origin
# out-of-sample stream (see open_composer.research.kernel.rolling_origin),
# never on an in-sample development window. Below this many rows the
# multiple-testing correction has too little data to mean anything, so the
# family gate cannot pass regardless of the computed statistics.
MIN_DSR_STREAM_ROWS = 1000

# Finite stand-in for "no measurable QQQ-downside participation" in the
# capture ratio (an unambiguous pass); CampaignModel forbids inf/nan.
_UNMEASURABLE_DOWNSIDE_CAPTURE_RATIO = 1.0e6

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    ),
]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
CampaignStage = Literal["pre-discovery", "pre-oos", "final"]
PartitionKind = Literal["development", "frozen_oos", "challenge", "forward"]
PartitionOperation = Literal[
    "candidate_generation",
    "candidate_mutation",
    "candidate_pruning",
    "factor_evaluation",
    "deterministic_backtest",
    "model_training",
    "model_inference",
    "resource_allocation",
    "archive_update",
    "promotion_evaluation",
    "reporting",
]

_EXPLORATION_OPERATIONS = {
    "candidate_generation",
    "candidate_mutation",
    "candidate_pruning",
    "factor_evaluation",
    "deterministic_backtest",
    "model_training",
    "model_inference",
    "resource_allocation",
    "archive_update",
}
_NONDETERMINISTIC_TIE_BREAK_TOKENS = {
    "arrival_order",
    "current_time",
    "insertion_order",
    "random",
    "runtime_order",
    "shuffle",
    "stochastic",
    "timestamp",
    "wall_clock",
}
_REQUIRED_BENCHMARK_ROLES = {
    "same_symbol_buy_and_hold",
    "equal_weight_universe",
    "market_proxy",
    "growth_proxy",
    "sector_theme_proxy",
    "cash_proxy",
    "leveraged_growth_proxy",
    "ex_post_best_symbol",
}
_CANDIDATE_PROMOTION_GATE_NAMES = {
    "cagr_excess_qqq",
    "qqq_capture_ratio",
    "qqq_downside_capture",
    "max_drawdown",
    "mar",
    "positive_fold_count",
    "stress_total_return",
}


class CampaignModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class CampaignHypothesis(CampaignModel):
    hypothesis_id: Identifier
    parent_hypothesis_id: Identifier | None
    economic_mechanism: NonEmptyStr
    universe_or_asset_class: NonEmptyStr
    horizon: NonEmptyStr
    data_modality: NonEmptyStr
    portfolio_construction: NonEmptyStr
    execution_style: NonEmptyStr
    universe_selection: Literal[
        "point_in_time",
        "fixed_long_lived",
        "cross_asset",
        "static_hotspot_control",
    ]
    role: Literal["research", "control"]
    promotion_eligible: bool


class CampaignBranchQuota(CampaignModel):
    branch_id: Identifier
    hypothesis_id: Identifier
    min_candidates: int = Field(ge=1)
    max_candidates: int = Field(ge=1)


class CampaignCandidateBlueprint(CampaignModel):
    candidate_id: Identifier
    hypothesis_id: Identifier
    branch_id: Identifier
    child_iteration_id: Identifier
    method_variant: NonEmptyStr
    factor_variant: NonEmptyStr
    archive_descriptors: dict[NonEmptyStr, str | int | float | bool] = Field(min_length=1)
    model_training: bool
    promotion_eligible: bool


class CampaignVisibilityPartition(CampaignModel):
    partition_id: Identifier
    kind: PartitionKind
    allowed_operations: list[PartitionOperation] = Field(min_length=1)


class CampaignExposureBudgets(CampaignModel):
    candidate_budget: int = Field(ge=1)
    cumulative_trial_exposure_budget: int = Field(ge=1)
    # ``cumulative_trial_exposure_budget`` is the cap for this campaign's
    # incremental allocation ledger.  Historical multiple-testing exposure is
    # carried separately so it cannot be mistaken for a resource budget.
    prior_effective_trial_count: int = Field(default=0, ge=0)


class CampaignExplorationPolicy(CampaignModel):
    generation_mode: Literal[
        "enumerated_candidates",
        "bounded_grid",
        "deterministic_template_expansion",
    ]
    mutation_mode: Literal["none", "bounded_parameter_mutation"]


class CampaignTieBreakRule(CampaignModel):
    field: NonEmptyStr
    direction: Literal["ascending", "descending"]


class CampaignQDArchive(CampaignModel):
    cell_key_fields: list[NonEmptyStr] = Field(min_length=1)
    quality_metric: NonEmptyStr
    quality_direction: Literal["maximize", "minimize"]
    quality_partition_id: Identifier
    tie_break_rules: list[CampaignTieBreakRule] = Field(min_length=1)
    max_elites_per_cell: int = Field(default=1, ge=1)


class CampaignExpensiveResourceRung(CampaignModel):
    rung_id: Identifier
    order: int = Field(ge=1)
    resource_kind: Literal["ml_training", "llm_inference", "high_cost_simulation"]
    input_candidate_limit: int = Field(ge=1)
    survivor_limit: int = Field(ge=1)
    read_partition_ids: list[Identifier] = Field(min_length=1)
    ranking_metric: NonEmptyStr
    tie_break_rules: list[CampaignTieBreakRule] = Field(min_length=1)


class CampaignPromotionEvidence(CampaignModel):
    promotion_cohort_ref: NonEmptyStr
    pre_oos_seal_ref: NonEmptyStr
    common_return_matrix_ref: NonEmptyStr
    statistical_family_gate_ref: NonEmptyStr
    candidate_promotion_gate_ref: NonEmptyStr


class CampaignPromotionCohort(CampaignModel):
    schema_version: Literal[1]
    campaign_id: Identifier
    candidate_ids: list[Identifier] = Field(min_length=1)
    selection_partition_id: Identifier
    selected_before_frozen_oos: Literal[True]
    qd_archive_sha256: Sha256
    allocation_ledger_head_sha256: Sha256


class CampaignPreOOSSeal(CampaignModel):
    schema_version: Literal[1]
    campaign_id: Identifier
    campaign_contract_sha256: Sha256
    promotion_cohort_sha256: Sha256
    qd_archive_sha256: Sha256
    allocation_ledger_head_sha256: Sha256
    candidate_inventory_sha256: Sha256
    effective_trial_count: int = Field(ge=1)
    frozen_oos_read_at_seal: Literal[False]
    prior_effective_trial_count: int | None = Field(default=None, ge=0)
    incremental_effective_trial_count: int | None = Field(default=None, ge=1)


class CampaignReturnStreamIdentity(CampaignModel):
    frequency: Literal["daily"]
    primary_cost_bps: int = Field(ge=0)
    benchmark: Identifier
    continuous_across_folds: Literal[True]
    terminal_liquidation_included: Literal[False]


class CampaignCommonReturnMatrix(CampaignModel):
    schema_version: Literal[1]
    campaign_id: Identifier
    partition_id: Identifier
    candidate_ids: list[Identifier] = Field(min_length=1)
    pre_oos_seal_sha256: Sha256
    return_stream_identity: CampaignReturnStreamIdentity
    dates: list[NonEmptyStr] = Field(min_length=2)
    benchmark_returns: list[float]
    returns: dict[Identifier, list[float]]


class CampaignStatisticalGate(CampaignModel):
    value: float
    threshold: float
    operator: Literal[">", ">=", "<", "<="]
    passed: bool


class CampaignStatisticalFamilyGates(CampaignModel):
    schema_version: Literal[1]
    campaign_id: Identifier
    candidate_ids: list[Identifier] = Field(min_length=1)
    pre_oos_seal_sha256: Sha256
    common_return_matrix_sha256: Sha256
    effective_trial_count: int = Field(ge=1)
    all_candidate_sharpe_values_defined: bool
    candidate_sharpe_excess_bil: dict[Identifier, float]
    dsr: CampaignStatisticalGate
    pbo: CampaignStatisticalGate
    spa: CampaignStatisticalGate
    family_gate_pass: bool


class CampaignCandidatePromotionPolicy(CampaignModel):
    primary_cost_bps: int = Field(ge=0)
    stress_cost_bps: int = Field(ge=0)
    annualization_sessions: int = Field(ge=1)
    cagr_excess_qqq_minimum: float
    qqq_capture_ratio_minimum: float
    qqq_downside_capture_maximum: float
    max_drawdown_minimum: float
    mar_minimum: float
    chronological_fold_count: int = Field(ge=2)
    minimum_positive_folds: int = Field(ge=1)
    development_partition_id: Identifier
    development_fold_ids: list[Identifier] = Field(min_length=2)
    stress_total_return_minimum: float
    stress_total_return_operator: Literal[">"]
    required_benchmark_roles: list[NonEmptyStr] = Field(min_length=1)


class CampaignCandidatePromotionMetrics(CampaignModel):
    cagr: float
    cagr_excess_qqq: float
    # Diagnostic only, not gated -- see A4 in
    # docs/plan-gate-recalibration-and-research-velocity-2026-08-26.zh.md.
    tqqq_cagr_capture: float
    tqqq_upside_capture: float
    tqqq_downside_capture: float
    qqq_upside_capture: float
    qqq_downside_capture: float
    qqq_capture_ratio: float
    qqq_correlation: float
    max_drawdown: float
    mar: float
    positive_fold_count: int = Field(ge=0)
    stress_total_return: float
    passed_gates: dict[NonEmptyStr, bool]
    all_gates_pass: bool


class CampaignCandidatePromotionEvidence(CampaignModel):
    schema_version: Literal[1]
    campaign_id: Identifier
    candidate_ids: list[Identifier] = Field(min_length=1)
    pre_oos_seal_sha256: Sha256
    common_return_matrix_sha256: Sha256
    dates: list[NonEmptyStr] = Field(min_length=2)
    primary_return_stream_identity: CampaignReturnStreamIdentity
    stress_return_stream_identity: CampaignReturnStreamIdentity
    development_partition_id: Identifier
    development_fold_ids: list[Identifier] = Field(min_length=2)
    benchmark_returns: dict[Identifier, list[float]]
    benchmark_roles: dict[Identifier, dict[NonEmptyStr, Identifier]]
    stress_returns: dict[Identifier, list[float]]
    development_fold_returns: dict[Identifier, list[list[float]]]
    metrics: dict[Identifier, CampaignCandidatePromotionMetrics]
    all_candidates_pass: bool


class CampaignAdvancingPairCorrelationPolicy(CampaignModel):
    method: Literal["pearson"]
    return_stream: Literal["development_validation_continuous_daily_primary_20bps_terminal_free"]
    absolute_maximum: float = Field(ge=0.0, le=1.0)
    operator: Literal["<="]
    minimum_passing_pair_count: int = Field(ge=1)


class CampaignStatisticalFamilyPolicy(CampaignModel):
    primary_sharpe_minimum: float
    primary_sharpe_operator: Literal[">"]
    advancing_pair_correlation: CampaignAdvancingPairCorrelationPolicy
    dsr_minimum: float = Field(ge=0.0, le=1.0)
    pbo_maximum: float = Field(ge=0.0, le=1.0)
    spa_p_value_maximum: float = Field(gt=0.0, lt=1.0)
    dsr_hac_lag: Literal[21]
    pbo_block_count: Literal[8]
    pbo_in_sample_block_count: Literal[4]
    spa_block_length: Literal[21]
    spa_resample_count: Literal[2000]
    spa_seed: Literal[4201]
    # Defaults to the strictest interpretation so contracts written before this
    # field existed keep requiring everything (see A6 in docs/plan-gate-
    # recalibration-and-research-velocity-2026-08-26.zh.md). "paper_entry"
    # keeps DSR/Sharpe as hard gates but demotes PBO/SPA/advancing-pair
    # correlation to diagnostics; "live_entry" requires all of them.
    promotion_stage: Literal["paper_entry", "live_entry"] = "live_entry"


class ResearchCampaignContract(CampaignModel):
    schema_version: Literal[1]
    campaign_id: Identifier
    created_at: NonEmptyStr
    title: NonEmptyStr
    objective: NonEmptyStr
    parent_iteration_ids: list[Identifier] = Field(min_length=1)
    child_iteration_ids: list[Identifier] = Field(min_length=1)
    root_hypothesis_id: Identifier
    hypotheses: list[CampaignHypothesis] = Field(min_length=2)
    branch_quotas: list[CampaignBranchQuota] = Field(min_length=1)
    candidate_blueprints: list[CampaignCandidateBlueprint] = Field(min_length=1)
    visibility_partitions: list[CampaignVisibilityPartition] = Field(min_length=1)
    exposure_budgets: CampaignExposureBudgets
    exploration_policy: CampaignExplorationPolicy
    qd_archive: CampaignQDArchive
    statistical_family_policy: CampaignStatisticalFamilyPolicy
    candidate_promotion_policy: CampaignCandidatePromotionPolicy
    expensive_resource_rungs: list[CampaignExpensiveResourceRung] = Field(default_factory=list)
    promotion_evidence: CampaignPromotionEvidence | None = None


class CampaignValidationCounts(CampaignModel):
    hypotheses: int = 0
    branches: int = 0
    preregistered_candidates: int = 0
    visibility_partitions: int = 0
    promotion_eligible_hypotheses: int = 0
    control_hypotheses: int = 0
    expensive_resource_rungs: int = 0
    candidate_budget: int = 0
    branch_minimum_candidates: int = 0
    branch_maximum_candidates: int = 0
    prior_effective_trial_count: int = 0
    cumulative_trial_exposure_budget: int = 0


class CampaignValidationReport(CampaignModel):
    campaign_id: str
    stage: CampaignStage
    contract_path: str | None = None
    status: Literal["ok", "warning", "blocked"]
    blocked: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    counts: CampaignValidationCounts = Field(default_factory=CampaignValidationCounts)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


CampaignContractSource = ResearchCampaignContract | Mapping[str, Any] | str | Path


def campaign_contract_path(campaign_id: str, root: Path | None = None) -> Path:
    """Return the canonical path for one campaign contract."""
    if CAMPAIGN_ID_RE.fullmatch(campaign_id) is None:
        raise ValueError("campaign_id must match ^[a-z0-9][a-z0-9_-]{2,96}$")
    return (root or project_root()) / CAMPAIGN_ROOT / campaign_id / CAMPAIGN_FILENAME


def load_campaign_contract(
    campaign_id_or_path: str | Path,
    root: Path | None = None,
) -> ResearchCampaignContract:
    """Load a canonical campaign ID or an explicit JSON path as a strict contract."""
    path = _source_path(campaign_id_or_path, root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("research campaign contract must be a JSON object")
    return ResearchCampaignContract.model_validate(payload)


def validate_campaign_contract(
    source: CampaignContractSource,
    root: Path | None = None,
    *,
    stage: CampaignStage = "pre-discovery",
) -> CampaignValidationReport:
    """Validate one campaign and dereference stage-required evidence artifacts."""
    if stage not in CAMPAIGN_STAGES:
        raise ValueError(f"stage must be one of {', '.join(sorted(CAMPAIGN_STAGES))}")

    campaign_id = _source_campaign_id(source)
    path = _source_path_or_none(source, root)
    try:
        contract = _coerce_contract(source, root)
    except FileNotFoundError:
        return _blocked_report(
            campaign_id,
            stage,
            path,
            ["campaign_contract_missing"],
        )
    except json.JSONDecodeError:
        return _blocked_report(
            campaign_id,
            stage,
            path,
            ["campaign_contract_invalid_json"],
        )
    except ValidationError as exc:
        return _blocked_report(
            campaign_id,
            stage,
            path,
            _validation_error_blockers(exc),
        )
    except (OSError, ValueError) as exc:
        return _blocked_report(
            campaign_id,
            stage,
            path,
            [f"campaign_contract_load_error:{type(exc).__name__}"],
        )

    blocked = _contract_blockers(contract, stage, root=root, contract_path=path)
    warnings: list[str] = []
    status: Literal["ok", "warning", "blocked"] = (
        "blocked" if blocked else "warning" if warnings else "ok"
    )
    return CampaignValidationReport(
        campaign_id=contract.campaign_id,
        stage=stage,
        contract_path=str(path) if path is not None else None,
        status=status,
        blocked=_dedupe(blocked),
        warnings=warnings,
        counts=_contract_counts(contract),
    )


def _contract_blockers(
    contract: ResearchCampaignContract,
    stage: CampaignStage,
    *,
    root: Path | None,
    contract_path: Path | None,
) -> list[str]:
    blocked: list[str] = []
    blocked.extend(_identity_blockers(contract))
    blocked.extend(_hypothesis_tree_blockers(contract))
    blocked.extend(_branch_quota_blockers(contract))
    blocked.extend(_candidate_inventory_blockers(contract))
    blocked.extend(_visibility_blockers(contract))
    blocked.extend(_archive_blockers(contract))
    blocked.extend(_candidate_promotion_policy_blockers(contract))
    blocked.extend(_resource_rung_blockers(contract))
    blocked.extend(_hotspot_control_blockers(contract))
    if stage in {"pre-oos", "final"}:
        if contract.promotion_evidence is None:
            blocked.append("promotion_evidence_references_missing")
        else:
            blocked.extend(
                _promotion_evidence_blockers(
                    contract,
                    stage=stage,
                    root=root,
                    contract_path=contract_path,
                )
            )
    return _dedupe(blocked)


def _identity_blockers(contract: ResearchCampaignContract) -> list[str]:
    blocked: list[str] = []
    if CAMPAIGN_ID_RE.fullmatch(contract.campaign_id) is None:
        blocked.append(f"campaign_id_invalid:{contract.campaign_id}")
    try:
        created_at = datetime.fromisoformat(contract.created_at.replace("Z", "+00:00"))
    except ValueError:
        blocked.append("campaign_created_at_invalid")
    else:
        if created_at.tzinfo is None:
            blocked.append("campaign_created_at_timezone_missing")
    blocked.extend(_duplicate_blockers("parent_iteration_id", contract.parent_iteration_ids))
    blocked.extend(_duplicate_blockers("child_iteration_id", contract.child_iteration_ids))
    overlap = sorted(set(contract.parent_iteration_ids) & set(contract.child_iteration_ids))
    blocked.extend(f"iteration_id_is_both_parent_and_child:{item}" for item in overlap)
    return blocked


def _hypothesis_tree_blockers(contract: ResearchCampaignContract) -> list[str]:
    blocked: list[str] = []
    ids = [item.hypothesis_id for item in contract.hypotheses]
    blocked.extend(_duplicate_blockers("hypothesis_id", ids))
    if len(ids) != len(set(ids)):
        return blocked

    by_id = {item.hypothesis_id: item for item in contract.hypotheses}
    roots = sorted(
        item.hypothesis_id for item in contract.hypotheses if item.parent_hypothesis_id is None
    )
    if roots != [contract.root_hypothesis_id]:
        blocked.append(
            "hypothesis_root_invalid:"
            f"declared={contract.root_hypothesis_id}:actual={','.join(roots) or 'none'}"
        )
    if contract.root_hypothesis_id not in by_id:
        blocked.append(f"root_hypothesis_missing:{contract.root_hypothesis_id}")

    children: dict[str, list[str]] = {item: [] for item in ids}
    for item in contract.hypotheses:
        parent_id = item.parent_hypothesis_id
        if parent_id is None:
            continue
        if parent_id not in by_id:
            blocked.append(f"hypothesis_parent_missing:{item.hypothesis_id}:{parent_id}")
            continue
        children[parent_id].append(item.hypothesis_id)

    visited: set[str] = set()
    active: list[str] = []
    active_set: set[str] = set()
    cycles: set[tuple[str, ...]] = set()

    def visit(hypothesis_id: str) -> None:
        if hypothesis_id in active_set:
            start = active.index(hypothesis_id)
            cycles.add(tuple(sorted(active[start:])))
            return
        if hypothesis_id in visited:
            return
        active.append(hypothesis_id)
        active_set.add(hypothesis_id)
        for child_id in sorted(children.get(hypothesis_id, [])):
            visit(child_id)
        active.pop()
        active_set.remove(hypothesis_id)
        visited.add(hypothesis_id)

    for hypothesis_id in sorted(ids):
        visit(hypothesis_id)
    blocked.extend(f"hypothesis_cycle:{','.join(cycle)}" for cycle in sorted(cycles))

    reachable: set[str] = set()
    if contract.root_hypothesis_id in by_id:
        pending = [contract.root_hypothesis_id]
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)
            pending.extend(children.get(current, []))
    disconnected = sorted(set(ids) - reachable)
    if disconnected:
        blocked.append(f"hypothesis_tree_disconnected:{','.join(disconnected)}")
    return blocked


def _branch_quota_blockers(contract: ResearchCampaignContract) -> list[str]:
    blocked: list[str] = []
    branch_ids = [item.branch_id for item in contract.branch_quotas]
    hypothesis_ids = [item.hypothesis_id for item in contract.branch_quotas]
    blocked.extend(_duplicate_blockers("branch_id", branch_ids))
    blocked.extend(_duplicate_blockers("branch_hypothesis_id", hypothesis_ids))
    known_hypotheses = {item.hypothesis_id for item in contract.hypotheses}
    parent_hypotheses = {
        item.parent_hypothesis_id
        for item in contract.hypotheses
        if item.parent_hypothesis_id is not None
    }
    leaf_hypotheses = known_hypotheses - parent_hypotheses
    for quota in contract.branch_quotas:
        if quota.hypothesis_id not in known_hypotheses:
            blocked.append(f"branch_hypothesis_missing:{quota.branch_id}:{quota.hypothesis_id}")
        if quota.hypothesis_id == contract.root_hypothesis_id:
            blocked.append(f"branch_quota_targets_root:{quota.branch_id}")
        elif quota.hypothesis_id in parent_hypotheses:
            blocked.append(f"branch_quota_targets_non_leaf:{quota.branch_id}:{quota.hypothesis_id}")
        if quota.min_candidates > quota.max_candidates:
            blocked.append(
                f"branch_quota_min_gt_max:{quota.branch_id}:"
                f"{quota.min_candidates}>{quota.max_candidates}"
            )
    unbudgeted_leaves = sorted(leaf_hypotheses - set(hypothesis_ids))
    if unbudgeted_leaves:
        blocked.append(f"leaf_hypotheses_without_branch_quota:{','.join(unbudgeted_leaves)}")
    minimum = sum(item.min_candidates for item in contract.branch_quotas)
    budget = contract.exposure_budgets.candidate_budget
    if minimum > budget:
        blocked.append(f"branch_minimum_quota_overflow:{minimum}>{budget}")
    if contract.exposure_budgets.cumulative_trial_exposure_budget < budget:
        blocked.append(
            "cumulative_trial_exposure_budget_below_candidate_budget:"
            f"{contract.exposure_budgets.cumulative_trial_exposure_budget}<{budget}"
        )
    prior = contract.exposure_budgets.prior_effective_trial_count
    incremental_cap = contract.exposure_budgets.cumulative_trial_exposure_budget
    if prior < 0:
        blocked.append("prior_effective_trial_count_negative")
    if incremental_cap < budget:
        blocked.append(
            f"incremental_trial_exposure_budget_below_candidate_budget:{incremental_cap}<{budget}"
        )
    return blocked


def _candidate_inventory_blockers(contract: ResearchCampaignContract) -> list[str]:
    blocked: list[str] = []
    candidates = contract.candidate_blueprints
    candidate_ids = [item.candidate_id for item in candidates]
    blocked.extend(_duplicate_blockers("campaign_candidate_id", candidate_ids))
    budget = contract.exposure_budgets.candidate_budget
    if len(candidates) != budget:
        blocked.append(f"campaign_candidate_inventory_budget_mismatch:{len(candidates)}:{budget}")

    hypotheses = {item.hypothesis_id: item for item in contract.hypotheses}
    quotas = {item.branch_id: item for item in contract.branch_quotas}
    child_ids = set(contract.child_iteration_ids)
    expected_descriptors = set(contract.qd_archive.cell_key_fields)
    branch_counts: dict[str, int] = {branch_id: 0 for branch_id in quotas}
    child_counts: dict[str, int] = {child_id: 0 for child_id in child_ids}
    has_ml_rung = any(
        item.resource_kind == "ml_training" for item in contract.expensive_resource_rungs
    )

    for candidate in candidates:
        hypothesis = hypotheses.get(candidate.hypothesis_id)
        quota = quotas.get(candidate.branch_id)
        if hypothesis is None:
            blocked.append(
                f"campaign_candidate_hypothesis_missing:{candidate.candidate_id}:"
                f"{candidate.hypothesis_id}"
            )
        if quota is None:
            blocked.append(
                f"campaign_candidate_branch_missing:{candidate.candidate_id}:{candidate.branch_id}"
            )
        else:
            branch_counts[candidate.branch_id] += 1
            if quota.hypothesis_id != candidate.hypothesis_id:
                blocked.append(
                    f"campaign_candidate_branch_hypothesis_mismatch:{candidate.candidate_id}:"
                    f"{candidate.branch_id}:{candidate.hypothesis_id}"
                )
        if candidate.child_iteration_id not in child_ids:
            blocked.append(
                f"campaign_candidate_child_iteration_missing:{candidate.candidate_id}:"
                f"{candidate.child_iteration_id}"
            )
        else:
            child_counts[candidate.child_iteration_id] += 1
        if hypothesis is not None:
            if candidate.promotion_eligible and not hypothesis.promotion_eligible:
                blocked.append(
                    f"campaign_candidate_promotion_exceeds_hypothesis:{candidate.candidate_id}"
                )
            if hypothesis.role == "control" and candidate.promotion_eligible:
                blocked.append(
                    f"campaign_control_candidate_promotion_eligible:{candidate.candidate_id}"
                )
        actual_descriptors = set(candidate.archive_descriptors)
        if actual_descriptors != expected_descriptors:
            blocked.append(
                f"campaign_candidate_archive_descriptors_mismatch:{candidate.candidate_id}:"
                f"expected={','.join(sorted(expected_descriptors))}:"
                f"actual={','.join(sorted(actual_descriptors))}"
            )
        for name, value in candidate.archive_descriptors.items():
            if isinstance(value, float) and not math.isfinite(value):
                blocked.append(
                    f"campaign_candidate_archive_descriptor_nonfinite:"
                    f"{candidate.candidate_id}:{name}"
                )
            if isinstance(value, str) and (not value or value != value.strip()):
                blocked.append(
                    f"campaign_candidate_archive_descriptor_invalid:{candidate.candidate_id}:{name}"
                )
        if candidate.model_training and not has_ml_rung:
            blocked.append(f"campaign_ml_candidate_without_resource_rung:{candidate.candidate_id}")

    for branch_id, quota in quotas.items():
        count = branch_counts[branch_id]
        if count < quota.min_candidates:
            blocked.append(
                f"campaign_branch_candidate_count_below_min:{branch_id}:"
                f"{count}<{quota.min_candidates}"
            )
        if count > quota.max_candidates:
            blocked.append(
                f"campaign_branch_candidate_count_above_max:{branch_id}:"
                f"{count}>{quota.max_candidates}"
            )
    for child_id, count in sorted(child_counts.items()):
        if count == 0:
            blocked.append(f"campaign_child_iteration_without_candidates:{child_id}")
    return blocked


def _visibility_blockers(contract: ResearchCampaignContract) -> list[str]:
    blocked: list[str] = []
    partition_ids = [item.partition_id for item in contract.visibility_partitions]
    blocked.extend(_duplicate_blockers("visibility_partition_id", partition_ids))
    if not any(item.kind == "development" for item in contract.visibility_partitions):
        blocked.append("development_visibility_partition_missing")
    if not any(item.kind != "development" for item in contract.visibility_partitions):
        blocked.append("protected_visibility_partition_missing")
    for partition in contract.visibility_partitions:
        blocked.extend(
            _duplicate_blockers(
                f"partition_operation:{partition.partition_id}",
                partition.allowed_operations,
            )
        )
        exposed = sorted(set(partition.allowed_operations) & _EXPLORATION_OPERATIONS)
        if partition.kind != "development" and exposed:
            blocked.append(
                "protected_partition_exposed_to_exploration:"
                f"{partition.partition_id}:{','.join(exposed)}"
            )
    return blocked


def _archive_blockers(contract: ResearchCampaignContract) -> list[str]:
    archive = contract.qd_archive
    blocked = _duplicate_blockers("archive_cell_key_field", archive.cell_key_fields)
    if archive.max_elites_per_cell != 1:
        blocked.append("archive_max_elites_per_cell_not_supported_by_deterministic_qd_v1")
    partitions = {item.partition_id: item for item in contract.visibility_partitions}
    quality_partition = partitions.get(archive.quality_partition_id)
    if quality_partition is None:
        blocked.append(f"archive_quality_partition_missing:{archive.quality_partition_id}")
    elif quality_partition.kind != "development":
        blocked.append(f"archive_quality_partition_not_development:{archive.quality_partition_id}")
    elif "archive_update" not in quality_partition.allowed_operations:
        blocked.append(
            f"archive_quality_partition_disallows_archive_update:{archive.quality_partition_id}"
        )
    blocked.extend(_tie_break_blockers("archive", archive.tie_break_rules))
    if [rule.model_dump(mode="json") for rule in archive.tie_break_rules] != [
        {"field": "candidate_id", "direction": "ascending"}
    ]:
        blocked.append("archive_tie_break_not_supported_by_deterministic_qd_v1")
    return blocked


def _resource_rung_blockers(contract: ResearchCampaignContract) -> list[str]:
    blocked: list[str] = []
    rungs = sorted(contract.expensive_resource_rungs, key=lambda item: item.order)
    blocked.extend(_duplicate_blockers("resource_rung_id", [item.rung_id for item in rungs]))
    blocked.extend(_duplicate_blockers("resource_rung_order", [str(item.order) for item in rungs]))
    if rungs and [item.order for item in rungs] != list(range(1, len(rungs) + 1)):
        blocked.append("resource_rung_order_not_contiguous_from_one")
    partitions = {item.partition_id: item for item in contract.visibility_partitions}
    previous_survivors: int | None = None
    for rung in rungs:
        if rung.order == 1 and (
            rung.input_candidate_limit > contract.exposure_budgets.candidate_budget
        ):
            blocked.append(
                f"resource_rung_inputs_exceed_candidate_budget:{rung.rung_id}:"
                f"{rung.input_candidate_limit}>{contract.exposure_budgets.candidate_budget}"
            )
        if rung.survivor_limit > rung.input_candidate_limit:
            blocked.append(
                f"resource_rung_survivors_exceed_inputs:{rung.rung_id}:"
                f"{rung.survivor_limit}>{rung.input_candidate_limit}"
            )
        if previous_survivors is not None and rung.input_candidate_limit > previous_survivors:
            blocked.append(
                f"resource_rung_inputs_exceed_prior_survivors:{rung.rung_id}:"
                f"{rung.input_candidate_limit}>{previous_survivors}"
            )
        previous_survivors = rung.survivor_limit
        blocked.extend(
            _duplicate_blockers(
                f"resource_rung_partition:{rung.rung_id}",
                rung.read_partition_ids,
            )
        )
        allowed_operations: set[str] = set()
        for partition_id in rung.read_partition_ids:
            partition = partitions.get(partition_id)
            if partition is None:
                blocked.append(f"resource_rung_partition_missing:{rung.rung_id}:{partition_id}")
            elif partition.kind != "development":
                blocked.append(
                    "resource_rung_reads_non_development_partition:"
                    f"{rung.rung_id}:{partition_id}:{partition.kind}"
                )
            else:
                allowed_operations.update(partition.allowed_operations)
        if "resource_allocation" not in allowed_operations:
            blocked.append(f"resource_rung_lacks_allocation_partition:{rung.rung_id}")
        if rung.resource_kind == "ml_training" and "model_training" not in allowed_operations:
            blocked.append(f"ml_resource_rung_lacks_training_partition:{rung.rung_id}")
        blocked.extend(_tie_break_blockers(f"resource_rung:{rung.rung_id}", rung.tie_break_rules))
    return blocked


def _hotspot_control_blockers(contract: ResearchCampaignContract) -> list[str]:
    blocked: list[str] = []
    for hypothesis in contract.hypotheses:
        if hypothesis.universe_selection != "static_hotspot_control":
            continue
        if hypothesis.role != "control":
            blocked.append(f"static_hotspot_must_be_control:{hypothesis.hypothesis_id}")
        if hypothesis.promotion_eligible:
            blocked.append(
                f"static_hotspot_cannot_be_promotion_eligible:{hypothesis.hypothesis_id}"
            )
    return blocked


def _candidate_promotion_policy_blockers(contract: ResearchCampaignContract) -> list[str]:
    policy = contract.candidate_promotion_policy
    blocked: list[str] = []
    if policy.stress_cost_bps <= policy.primary_cost_bps:
        blocked.append(
            "candidate_promotion_stress_cost_not_above_primary:"
            f"{policy.stress_cost_bps}:{policy.primary_cost_bps}"
        )
    if policy.minimum_positive_folds > policy.chronological_fold_count:
        blocked.append(
            "candidate_promotion_positive_fold_requirement_impossible:"
            f"{policy.minimum_positive_folds}:{policy.chronological_fold_count}"
        )
    blocked.extend(
        _duplicate_blockers("candidate_promotion_development_fold_id", policy.development_fold_ids)
    )
    if len(policy.development_fold_ids) != policy.chronological_fold_count:
        blocked.append(
            "candidate_promotion_development_fold_count_mismatch:"
            f"{len(policy.development_fold_ids)}:{policy.chronological_fold_count}"
        )
    if policy.development_partition_id != contract.qd_archive.quality_partition_id:
        blocked.append(
            "candidate_promotion_development_partition_mismatch:"
            f"{policy.development_partition_id}:{contract.qd_archive.quality_partition_id}"
        )
    roles = list(policy.required_benchmark_roles)
    blocked.extend(_duplicate_blockers("candidate_promotion_benchmark_role", roles))
    if set(roles) != _REQUIRED_BENCHMARK_ROLES:
        blocked.append(
            "candidate_promotion_benchmark_roles_incomplete:"
            + ",".join(sorted(_REQUIRED_BENCHMARK_ROLES - set(roles)))
        )
    return blocked


def _promotion_evidence_blockers(
    contract: ResearchCampaignContract,
    *,
    stage: CampaignStage,
    root: Path | None,
    contract_path: Path | None,
) -> list[str]:
    evidence = contract.promotion_evidence
    if evidence is None:
        return ["promotion_evidence_references_missing"]
    repository_root = (root or project_root()).resolve()
    campaign_dir = (
        contract_path.parent.resolve()
        if contract_path is not None
        else campaign_contract_path(contract.campaign_id, repository_root).parent.resolve()
    )
    blocked: list[str] = []
    cohort, cohort_path, cohort_blocked = _load_campaign_evidence(
        evidence.promotion_cohort_ref,
        campaign_dir=campaign_dir,
        label="promotion_cohort",
        model=CampaignPromotionCohort,
    )
    blocked.extend(cohort_blocked)
    if cohort is None or cohort_path is None:
        return blocked

    blocked.extend(_promotion_cohort_identity_blockers(contract, cohort))
    blocked.extend(
        _selection_artifact_blockers(
            contract,
            cohort,
            campaign_dir=campaign_dir,
            repository_root=repository_root,
            contract_path=contract_path,
        )
    )
    seal, seal_path, seal_blocked = _load_campaign_evidence(
        evidence.pre_oos_seal_ref,
        campaign_dir=campaign_dir,
        label="pre_oos_seal",
        model=CampaignPreOOSSeal,
    )
    blocked.extend(seal_blocked)
    if seal is None or seal_path is None:
        return blocked
    blocked.extend(
        _pre_oos_seal_blockers(
            contract,
            cohort,
            seal,
            cohort_path=cohort_path,
            campaign_dir=campaign_dir,
            contract_path=contract_path,
        )
    )
    if stage == "pre-oos":
        return blocked

    matrix, matrix_path, matrix_blocked = _load_campaign_evidence(
        evidence.common_return_matrix_ref,
        campaign_dir=campaign_dir,
        label="common_return_matrix",
        model=CampaignCommonReturnMatrix,
    )
    gates, _, gates_blocked = _load_campaign_evidence(
        evidence.statistical_family_gate_ref,
        campaign_dir=campaign_dir,
        label="statistical_family_gates",
        model=CampaignStatisticalFamilyGates,
    )
    candidate_gates, _, candidate_gates_blocked = _load_campaign_evidence(
        evidence.candidate_promotion_gate_ref,
        campaign_dir=campaign_dir,
        label="candidate_promotion_gates",
        model=CampaignCandidatePromotionEvidence,
    )
    blocked.extend(matrix_blocked)
    blocked.extend(gates_blocked)
    blocked.extend(candidate_gates_blocked)
    if matrix is None or gates is None or candidate_gates is None or matrix_path is None:
        return blocked

    seal_sha256 = hashlib.sha256(seal_path.read_bytes()).hexdigest()
    blocked.extend(
        _common_return_matrix_blockers(
            contract,
            cohort,
            matrix,
            seal_sha256=seal_sha256,
        )
    )
    blocked.extend(
        _statistical_family_gate_blockers(
            contract,
            cohort,
            matrix,
            gates,
            matrix_sha256=hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
            seal_sha256=seal_sha256,
            expected_trial_count=seal.effective_trial_count,
        )
    )
    blocked.extend(
        _candidate_promotion_gate_blockers(
            contract,
            cohort,
            matrix,
            candidate_gates,
            matrix_sha256=hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
            seal_sha256=seal_sha256,
        )
    )
    return blocked


def _load_campaign_evidence(
    reference: str,
    *,
    campaign_dir: Path,
    label: str,
    model: type[CampaignModel],
) -> tuple[CampaignModel | None, Path | None, list[str]]:
    path, error = _campaign_evidence_path(reference, campaign_dir)
    if error:
        return None, path, [f"{label}_ref_invalid:{error}"]
    if path is None or not path.is_file() or path.is_symlink():
        return None, path, [f"{label}_missing"]
    if path.suffix.lower() != ".json":
        return None, path, [f"{label}_must_be_json"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, path, [f"{label}_invalid_json"]
    try:
        parsed = model.model_validate(payload)
    except ValidationError as exc:
        errors = []
        for item in exc.errors(include_url=False):
            location = ".".join(str(value) for value in item["loc"]) or "root"
            errors.append(f"{label}_schema_invalid:{location}:{item['type']}")
        return None, path, _dedupe(errors)
    return parsed, path, []


def _campaign_evidence_path(reference: str, campaign_dir: Path) -> tuple[Path | None, str | None]:
    raw = Path(reference)
    if raw.is_absolute():
        return None, "absolute_path_not_allowed"
    candidate = (campaign_dir / raw).resolve()
    try:
        candidate.relative_to(campaign_dir)
    except ValueError:
        return None, "path_escapes_campaign_directory"
    return candidate, None


def _repository_evidence_path(
    reference: str,
    repository_root: Path,
) -> tuple[Path | None, str | None]:
    raw = Path(reference)
    if raw.is_absolute():
        return None, "absolute_path_not_allowed"
    candidate = (repository_root / raw).resolve()
    try:
        candidate.relative_to(repository_root)
    except ValueError:
        return None, "path_escapes_repository"
    return candidate, None


def _pre_oos_seal_blockers(
    contract: ResearchCampaignContract,
    cohort: CampaignPromotionCohort,
    seal: CampaignPreOOSSeal,
    *,
    cohort_path: Path,
    campaign_dir: Path,
    contract_path: Path | None,
) -> list[str]:
    blocked: list[str] = []
    if seal.campaign_id != contract.campaign_id:
        blocked.append("pre_oos_seal_campaign_id_mismatch")
    if contract_path is None or not contract_path.is_file() or contract_path.is_symlink():
        return [*blocked, "pre_oos_seal_campaign_contract_missing"]
    contract_sha256 = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    if seal.campaign_contract_sha256 != contract_sha256:
        blocked.append("pre_oos_seal_campaign_contract_sha256_mismatch")
    if seal.promotion_cohort_sha256 != hashlib.sha256(cohort_path.read_bytes()).hexdigest():
        blocked.append("pre_oos_seal_promotion_cohort_sha256_mismatch")

    archive_path = campaign_dir / "qd-archive.json"
    if archive_path.is_file() and not archive_path.is_symlink():
        archive_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        if seal.qd_archive_sha256 != archive_sha256:
            blocked.append("pre_oos_seal_qd_archive_sha256_mismatch")
        if seal.qd_archive_sha256 != cohort.qd_archive_sha256:
            blocked.append("pre_oos_seal_qd_archive_cohort_mismatch")

    ledger_path = campaign_dir / "allocation-ledger.jsonl"
    ledger, ledger_blocked = _load_allocation_ledger_evidence(
        contract,
        ledger_path,
        contract_path=contract_path,
    )
    blocked.extend(ledger_blocked)
    if ledger is not None:
        if seal.allocation_ledger_head_sha256 != ledger.head_sha256:
            blocked.append("pre_oos_seal_allocation_ledger_head_sha256_mismatch")
        if seal.allocation_ledger_head_sha256 != cohort.allocation_ledger_head_sha256:
            blocked.append("pre_oos_seal_allocation_ledger_cohort_mismatch")
        if seal.candidate_inventory_sha256 != ledger.candidate_inventory_sha256:
            blocked.append("pre_oos_seal_candidate_inventory_sha256_mismatch")
        try:
            effective_trial_count = family_effective_trial_count_from_ledger(contract, ledger)
        except ValueError as exc:
            blocked.append(f"pre_oos_seal_trial_accounting_invalid:{exc}")
            return blocked
        if seal.effective_trial_count != effective_trial_count:
            blocked.append(
                "pre_oos_seal_effective_trial_count_mismatch:"
                f"{seal.effective_trial_count}:{effective_trial_count}"
            )
        prior = contract.exposure_budgets.prior_effective_trial_count
        # ``effective_trial_count`` is now already family-scoped (excludes
        # ``prior``), so the incremental figure recorded on the seal is just
        # that same value; ``prior`` is tracked on the seal purely as a
        # lifetime diagnostic, not added into the DSR/PBO/SPA trial count.
        incremental = effective_trial_count
        if prior > 0 and seal.prior_effective_trial_count is None:
            blocked.append("pre_oos_seal_prior_effective_trial_count_missing")
        elif (
            seal.prior_effective_trial_count is not None
            and seal.prior_effective_trial_count != prior
        ):
            blocked.append(
                "pre_oos_seal_prior_effective_trial_count_mismatch:"
                f"{seal.prior_effective_trial_count}:{prior}"
            )
        if prior > 0 and seal.incremental_effective_trial_count is None:
            blocked.append("pre_oos_seal_incremental_effective_trial_count_missing")
        elif (
            seal.incremental_effective_trial_count is not None
            and seal.incremental_effective_trial_count != incremental
        ):
            blocked.append(
                "pre_oos_seal_incremental_effective_trial_count_mismatch:"
                f"{seal.incremental_effective_trial_count}:{incremental}"
            )
    return blocked


def _promotion_cohort_identity_blockers(
    contract: ResearchCampaignContract,
    cohort: CampaignPromotionCohort,
) -> list[str]:
    blocked: list[str] = []
    if cohort.campaign_id != contract.campaign_id:
        blocked.append("promotion_cohort_campaign_id_mismatch")
    blocked.extend(_duplicate_blockers("promotion_cohort_candidate_id", cohort.candidate_ids))
    eligible_ids = {
        item.candidate_id for item in contract.candidate_blueprints if item.promotion_eligible
    }
    unknown = sorted(set(cohort.candidate_ids) - eligible_ids)
    if unknown:
        blocked.append(f"promotion_cohort_ineligible_candidates:{','.join(unknown)}")
    partitions = {item.partition_id: item for item in contract.visibility_partitions}
    selection_partition = partitions.get(cohort.selection_partition_id)
    if selection_partition is None:
        blocked.append(
            f"promotion_cohort_selection_partition_missing:{cohort.selection_partition_id}"
        )
    elif selection_partition.kind != "development":
        blocked.append(
            f"promotion_cohort_selection_partition_not_development:{cohort.selection_partition_id}"
        )
    return blocked


def _common_return_matrix_blockers(
    contract: ResearchCampaignContract,
    cohort: CampaignPromotionCohort,
    matrix: CampaignCommonReturnMatrix,
    *,
    seal_sha256: str,
) -> list[str]:
    blocked: list[str] = []
    if matrix.campaign_id != contract.campaign_id:
        blocked.append("common_return_matrix_campaign_id_mismatch")
    blocked.extend(_duplicate_blockers("common_return_matrix_candidate_id", matrix.candidate_ids))
    if matrix.candidate_ids != cohort.candidate_ids:
        blocked.append("common_return_matrix_candidate_inventory_mismatch")
    if matrix.pre_oos_seal_sha256 != seal_sha256:
        blocked.append("common_return_matrix_pre_oos_seal_sha256_mismatch")
    partitions = {item.partition_id: item for item in contract.visibility_partitions}
    partition = partitions.get(matrix.partition_id)
    if partition is None:
        blocked.append(f"common_return_matrix_partition_missing:{matrix.partition_id}")
    elif partition.kind != "frozen_oos":
        blocked.append(f"common_return_matrix_partition_not_frozen_oos:{matrix.partition_id}")
    primary_cost_bps = contract.candidate_promotion_policy.primary_cost_bps
    if matrix.return_stream_identity.primary_cost_bps != primary_cost_bps:
        blocked.append(
            "common_return_matrix_primary_cost_bps_mismatch:"
            f"{matrix.return_stream_identity.primary_cost_bps}:{primary_cost_bps}"
        )
    if matrix.return_stream_identity.benchmark != "BIL":
        blocked.append(
            f"common_return_matrix_benchmark_mismatch:{matrix.return_stream_identity.benchmark}:BIL"
        )
    if len(set(matrix.dates)) != len(matrix.dates):
        blocked.append("common_return_matrix_duplicate_dates")
    if matrix.dates != sorted(matrix.dates):
        blocked.append("common_return_matrix_dates_not_sorted")
    if set(matrix.returns) != set(matrix.candidate_ids):
        blocked.append("common_return_matrix_return_columns_mismatch")
    expected_rows = len(matrix.dates)
    if len(matrix.benchmark_returns) != expected_rows:
        blocked.append(
            "common_return_matrix_benchmark_row_count_mismatch:"
            f"{len(matrix.benchmark_returns)}:{expected_rows}"
        )
    if any(not math.isfinite(value) for value in matrix.benchmark_returns):
        blocked.append("common_return_matrix_nonfinite_benchmark_return")
    for candidate_id, values in matrix.returns.items():
        if len(values) != expected_rows:
            blocked.append(
                f"common_return_matrix_row_count_mismatch:{candidate_id}:"
                f"{len(values)}:{expected_rows}"
            )
        if any(not math.isfinite(value) for value in values):
            blocked.append(f"common_return_matrix_nonfinite_return:{candidate_id}")
    return blocked


def _statistical_family_gate_blockers(
    contract: ResearchCampaignContract,
    cohort: CampaignPromotionCohort,
    matrix: CampaignCommonReturnMatrix,
    gates: CampaignStatisticalFamilyGates,
    *,
    matrix_sha256: str,
    seal_sha256: str,
    expected_trial_count: int,
) -> list[str]:
    blocked: list[str] = []
    if gates.campaign_id != contract.campaign_id:
        blocked.append("statistical_family_gates_campaign_id_mismatch")
    blocked.extend(_duplicate_blockers("statistical_family_gate_candidate_id", gates.candidate_ids))
    if gates.candidate_ids != cohort.candidate_ids:
        blocked.append("statistical_family_gates_candidate_inventory_mismatch")
    if gates.pre_oos_seal_sha256 != seal_sha256:
        blocked.append("statistical_family_gates_pre_oos_seal_sha256_mismatch")
    if set(gates.candidate_sharpe_excess_bil) != set(cohort.candidate_ids):
        blocked.append("statistical_family_gates_candidate_sharpe_inventory_mismatch")
    if gates.common_return_matrix_sha256 != matrix_sha256:
        blocked.append("statistical_family_gates_common_return_matrix_sha256_mismatch")
    # Family-scoped: this campaign's own trial count is bounded by its own
    # candidate/exposure budgets and the hard cross-campaign cap, never by
    # ``prior_effective_trial_count`` (lifetime diagnostic only, see A1 in
    # docs/plan-gate-recalibration-and-research-velocity-2026-08-26.zh.md).
    minimum_trial_count = contract.exposure_budgets.candidate_budget
    maximum_trial_count = min(
        contract.exposure_budgets.cumulative_trial_exposure_budget,
        MAX_FAMILY_EFFECTIVE_TRIAL_COUNT,
    )
    if gates.effective_trial_count < minimum_trial_count:
        blocked.append(
            "statistical_family_gates_trial_count_below_candidate_budget:"
            f"{gates.effective_trial_count}:{minimum_trial_count}"
        )
    if gates.effective_trial_count > maximum_trial_count:
        blocked.append(
            "statistical_family_gates_trial_count_above_exposure_budget:"
            f"{gates.effective_trial_count}:"
            f"{maximum_trial_count}"
        )
    if gates.effective_trial_count != expected_trial_count:
        blocked.append(
            "statistical_family_gates_trial_count_pre_oos_seal_mismatch:"
            f"{gates.effective_trial_count}:{expected_trial_count}"
        )
    # matrix.return_stream_identity.continuous_across_folds is Literal[True], so
    # Pydantic already rejects any non-stitched stream at construction time; the
    # remaining, genuinely-checkable requirement is that it be long enough.
    if len(matrix.dates) < MIN_DSR_STREAM_ROWS:
        blocked.append(
            "statistical_family_gates_stitched_stream_too_short:"
            f"{len(matrix.dates)}:{MIN_DSR_STREAM_ROWS}"
        )
    policy = contract.statistical_family_policy
    expected = {
        "dsr": (policy.dsr_minimum, ">="),
        "pbo": (policy.pbo_maximum, "<="),
        "spa": (policy.spa_p_value_maximum, "<="),
    }
    for name, (threshold, operator) in expected.items():
        gate = getattr(gates, name)
        if gate.threshold != threshold or gate.operator != operator:
            blocked.append(f"statistical_family_gate_contract_mismatch:{name}")
        if gate.passed != _comparison_passes(gate.value, gate.threshold, gate.operator):
            blocked.append(f"statistical_family_gate_pass_flag_inconsistent:{name}")
    if not gates.all_candidate_sharpe_values_defined:
        blocked.append("statistical_family_gate_candidate_sharpe_undefined")
    blocked.extend(_recomputed_statistical_gate_blockers(contract, matrix, gates))
    # A6: at paper_entry, DSR stays a hard gate but PBO/SPA are diagnostics
    # only (still computed and recorded, just not blocking); live_entry
    # requires all three. See docs/plan-gate-recalibration-and-research-
    # velocity-2026-08-26.zh.md Work Item A6.
    required_statistical_gates = (
        ("dsr",) if policy.promotion_stage == "paper_entry" else ("dsr", "pbo", "spa")
    )
    if not gates.family_gate_pass or not all(
        getattr(gates, name).passed for name in required_statistical_gates
    ):
        blocked.append("statistical_family_gate_failed")
    failed_sharpe = sorted(
        candidate_id
        for candidate_id, value in gates.candidate_sharpe_excess_bil.items()
        if value <= policy.primary_sharpe_minimum
    )
    if failed_sharpe:
        blocked.append("statistical_family_primary_sharpe_gate_failed:" + ",".join(failed_sharpe))
    expected_family_pass = (
        not failed_sharpe
        and gates.all_candidate_sharpe_values_defined
        and len(matrix.dates) >= MIN_DSR_STREAM_ROWS
        and all(getattr(gates, name).passed for name in required_statistical_gates)
    )
    if gates.family_gate_pass != expected_family_pass:
        blocked.append("statistical_family_gate_family_pass_flag_inconsistent")
    return blocked


def _recomputed_statistical_gate_blockers(
    contract: ResearchCampaignContract,
    matrix: CampaignCommonReturnMatrix,
    gates: CampaignStatisticalFamilyGates,
) -> list[str]:
    from open_composer.research.campaign_statistics import recompute_campaign_statistics

    policy = contract.statistical_family_policy
    try:
        recomputed = recompute_campaign_statistics(
            candidate_ids=matrix.candidate_ids,
            candidate_returns=matrix.returns,
            benchmark_returns=matrix.benchmark_returns,
            effective_trial_count=gates.effective_trial_count,
            dsr_hac_lag=policy.dsr_hac_lag,
            pbo_block_count=policy.pbo_block_count,
            pbo_in_sample_block_count=policy.pbo_in_sample_block_count,
            spa_block_length=policy.spa_block_length,
            spa_resample_count=policy.spa_resample_count,
            spa_seed=policy.spa_seed,
        )
    except (ArithmeticError, ValueError) as exc:
        return [f"statistical_family_recomputation_failed:{type(exc).__name__}:{exc}"]

    blocked: list[str] = []
    for candidate_id in matrix.candidate_ids:
        reported = gates.candidate_sharpe_excess_bil.get(candidate_id)
        actual = recomputed.candidate_sharpe_excess_bil[candidate_id]
        if reported is None or not math.isclose(
            reported,
            actual,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            blocked.append(f"statistical_family_sharpe_recomputation_mismatch:{candidate_id}")
    recomputed_values = {
        "dsr": recomputed.dsr_probability,
        "pbo": recomputed.pbo_probability,
        "spa": recomputed.spa_p_value,
    }
    for name, actual in recomputed_values.items():
        gate = getattr(gates, name)
        if not math.isclose(gate.value, actual, rel_tol=1e-12, abs_tol=1e-12):
            blocked.append(f"statistical_family_{name}_recomputation_mismatch")
        expected_pass = _comparison_passes(actual, gate.threshold, gate.operator)
        if gate.passed != expected_pass:
            blocked.append(f"statistical_family_{name}_recomputed_pass_flag_inconsistent")
    return blocked


def recompute_candidate_promotion_metrics(
    *,
    candidate_returns: list[float],
    qqq_returns: list[float],
    tqqq_returns: list[float],
    stress_returns: list[float],
    development_fold_returns: list[list[float]],
    annualization_sessions: int,
) -> dict[str, float | int]:
    """Recompute every non-family promotion metric from return streams."""
    row_count = len(candidate_returns)
    if row_count < 2:
        raise ValueError("candidate promotion returns require at least two rows")
    for name, values in (
        ("candidate", candidate_returns),
        ("qqq", qqq_returns),
        ("tqqq", tqqq_returns),
        ("stress", stress_returns),
    ):
        if len(values) != row_count:
            raise ValueError(f"{name} return row count mismatch")
        _validate_compoundable_returns(values, label=name)
    if not development_fold_returns:
        raise ValueError("development fold returns are missing")
    for index, values in enumerate(development_fold_returns):
        if not values:
            raise ValueError(f"development fold {index} is empty")
        _validate_compoundable_returns(values, label=f"development_fold_{index}")

    cagr = _annualized_compound_return(candidate_returns, annualization_sessions)
    qqq_cagr = _annualized_compound_return(qqq_returns, annualization_sessions)
    tqqq_cagr = _annualized_compound_return(tqqq_returns, annualization_sessions)
    if tqqq_cagr <= 0.0:
        raise ValueError("TQQQ CAGR must be positive for CAGR capture")
    max_drawdown = _maximum_drawdown(candidate_returns)
    if max_drawdown >= 0.0:
        raise ValueError("candidate max drawdown must be negative for finite MAR")
    qqq_upside_capture = _conditional_capture(candidate_returns, qqq_returns, positive=True)
    qqq_downside_capture = _conditional_capture(candidate_returns, qqq_returns, positive=False)
    # A candidate that captured ~none of QQQ's downside is an unambiguous pass
    # on the ratio gate, not an error -- guard the division instead of
    # requiring every candidate to have nonzero downside participation.
    # ``allow_inf_nan=False`` on CampaignModel forbids inf/nan, so a large
    # finite sentinel stands in for "no measurable downside participation".
    if math.isclose(qqq_downside_capture, 0.0, rel_tol=0.0, abs_tol=1e-12):
        qqq_capture_ratio = (
            _UNMEASURABLE_DOWNSIDE_CAPTURE_RATIO if qqq_upside_capture > 0.0 else 0.0
        )
    else:
        qqq_capture_ratio = qqq_upside_capture / qqq_downside_capture
    return {
        "cagr": cagr,
        "cagr_excess_qqq": cagr - qqq_cagr,
        # Diagnostic only (see A4 in docs/plan-gate-recalibration-and-research-
        # velocity-2026-08-26.zh.md): TQQQ is not a viable promotion benchmark
        # on its own -- it can have negative CAGR over multi-year windows, so
        # "captured X% of TQQQ's upside" is not meaningful for an orthogonal
        # strategy. Kept for backward-looking comparability, never gated.
        "tqqq_cagr_capture": cagr / tqqq_cagr,
        "tqqq_upside_capture": _conditional_capture(
            candidate_returns,
            tqqq_returns,
            positive=True,
        ),
        "tqqq_downside_capture": _conditional_capture(
            candidate_returns,
            tqqq_returns,
            positive=False,
        ),
        "qqq_upside_capture": qqq_upside_capture,
        "qqq_downside_capture": qqq_downside_capture,
        "qqq_capture_ratio": qqq_capture_ratio,
        "qqq_correlation": _pearson_correlation(candidate_returns, qqq_returns),
        "max_drawdown": max_drawdown,
        "mar": cagr / abs(max_drawdown),
        "positive_fold_count": sum(
            _compound_return(values) > 0.0 for values in development_fold_returns
        ),
        "stress_total_return": _compound_return(stress_returns),
    }


def _candidate_promotion_gate_blockers(
    contract: ResearchCampaignContract,
    cohort: CampaignPromotionCohort,
    matrix: CampaignCommonReturnMatrix,
    evidence: CampaignCandidatePromotionEvidence,
    *,
    matrix_sha256: str,
    seal_sha256: str,
) -> list[str]:
    blocked: list[str] = []
    if evidence.campaign_id != contract.campaign_id:
        blocked.append("candidate_promotion_gates_campaign_id_mismatch")
    if evidence.candidate_ids != cohort.candidate_ids:
        blocked.append("candidate_promotion_gates_candidate_inventory_mismatch")
    if evidence.pre_oos_seal_sha256 != seal_sha256:
        blocked.append("candidate_promotion_gates_pre_oos_seal_sha256_mismatch")
    if evidence.common_return_matrix_sha256 != matrix_sha256:
        blocked.append("candidate_promotion_gates_common_return_matrix_sha256_mismatch")
    if evidence.dates != matrix.dates:
        blocked.append("candidate_promotion_gates_date_inventory_mismatch")

    policy = contract.candidate_promotion_policy
    if evidence.primary_return_stream_identity != matrix.return_stream_identity:
        blocked.append("candidate_promotion_gates_primary_return_stream_identity_mismatch")
    stress_identity = evidence.stress_return_stream_identity
    if (
        stress_identity.frequency != matrix.return_stream_identity.frequency
        or stress_identity.primary_cost_bps != policy.stress_cost_bps
        or stress_identity.benchmark != matrix.return_stream_identity.benchmark
    ):
        blocked.append("candidate_promotion_gates_stress_return_stream_identity_mismatch")
    if evidence.development_partition_id != policy.development_partition_id:
        blocked.append("candidate_promotion_gates_development_partition_mismatch")
    if evidence.development_fold_ids != policy.development_fold_ids:
        blocked.append("candidate_promotion_gates_development_fold_identity_mismatch")

    expected_ids = set(cohort.candidate_ids)
    inventories = {
        "benchmark_roles": set(evidence.benchmark_roles),
        "stress_returns": set(evidence.stress_returns),
        "development_fold_returns": set(evidence.development_fold_returns),
        "metrics": set(evidence.metrics),
    }
    for name, actual_ids in inventories.items():
        if actual_ids != expected_ids:
            blocked.append(f"candidate_promotion_gates_{name}_inventory_mismatch")

    row_count = len(matrix.dates)
    for benchmark_id, values in evidence.benchmark_returns.items():
        if len(values) != row_count:
            blocked.append(
                "candidate_promotion_gates_benchmark_row_count_mismatch:"
                f"{benchmark_id}:{len(values)}:{row_count}"
            )
        elif any(not math.isfinite(value) or value <= -1.0 for value in values):
            blocked.append(f"candidate_promotion_gates_benchmark_returns_invalid:{benchmark_id}")

    expected_gate_names = _CANDIDATE_PROMOTION_GATE_NAMES
    all_candidate_passes: list[bool] = []
    for candidate_id in cohort.candidate_ids:
        roles = evidence.benchmark_roles.get(candidate_id)
        if roles is None:
            continue
        if set(roles) != set(policy.required_benchmark_roles):
            blocked.append(f"candidate_promotion_gates_benchmark_roles_mismatch:{candidate_id}")
            continue
        missing_benchmarks = sorted(set(roles.values()) - set(evidence.benchmark_returns))
        if missing_benchmarks:
            blocked.append(
                "candidate_promotion_gates_benchmark_stream_missing:"
                f"{candidate_id}:{','.join(missing_benchmarks)}"
            )
            continue
        cash_returns = evidence.benchmark_returns[roles["cash_proxy"]]
        if len(cash_returns) == len(matrix.benchmark_returns) and any(
            not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-15)
            for left, right in zip(cash_returns, matrix.benchmark_returns, strict=True)
        ):
            blocked.append(f"candidate_promotion_gates_cash_proxy_mismatch:{candidate_id}")
        folds = evidence.development_fold_returns.get(candidate_id)
        if folds is None:
            continue
        if len(folds) != policy.chronological_fold_count:
            blocked.append(
                "candidate_promotion_gates_fold_count_mismatch:"
                f"{candidate_id}:{len(folds)}:{policy.chronological_fold_count}"
            )
            continue
        try:
            actual = recompute_candidate_promotion_metrics(
                candidate_returns=matrix.returns[candidate_id],
                qqq_returns=evidence.benchmark_returns[roles["growth_proxy"]],
                tqqq_returns=evidence.benchmark_returns[roles["leveraged_growth_proxy"]],
                stress_returns=evidence.stress_returns[candidate_id],
                development_fold_returns=folds,
                annualization_sessions=policy.annualization_sessions,
            )
        except (KeyError, ValueError) as exc:
            blocked.append(
                "candidate_promotion_gates_recomputation_failed:"
                f"{candidate_id}:{type(exc).__name__}:{exc}"
            )
            continue
        reported = evidence.metrics.get(candidate_id)
        if reported is None:
            continue
        for metric_name, actual_value in actual.items():
            reported_value = getattr(reported, metric_name)
            if isinstance(actual_value, int):
                if reported_value != actual_value:
                    blocked.append(
                        "candidate_promotion_gates_metric_recomputation_mismatch:"
                        f"{candidate_id}:{metric_name}"
                    )
            elif not math.isclose(
                float(reported_value),
                actual_value,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                blocked.append(
                    "candidate_promotion_gates_metric_recomputation_mismatch:"
                    f"{candidate_id}:{metric_name}"
                )
        expected_passes = _candidate_promotion_passes(actual, policy)
        if set(reported.passed_gates) != expected_gate_names:
            blocked.append(f"candidate_promotion_gates_pass_inventory_mismatch:{candidate_id}")
        for gate_name, expected_pass in expected_passes.items():
            if reported.passed_gates.get(gate_name) is not expected_pass:
                blocked.append(
                    f"candidate_promotion_gates_pass_flag_inconsistent:{candidate_id}:{gate_name}"
                )
        expected_all_pass = all(expected_passes.values())
        all_candidate_passes.append(expected_all_pass)
        if reported.all_gates_pass is not expected_all_pass:
            blocked.append(
                f"candidate_promotion_gates_candidate_pass_flag_inconsistent:{candidate_id}"
            )
        if not expected_all_pass:
            failed = sorted(name for name, passed in expected_passes.items() if not passed)
            blocked.append(f"candidate_promotion_gates_failed:{candidate_id}:{','.join(failed)}")
    expected_family_pass = len(all_candidate_passes) == len(cohort.candidate_ids) and all(
        all_candidate_passes
    )
    if evidence.all_candidates_pass is not expected_family_pass:
        blocked.append("candidate_promotion_gates_all_candidates_pass_flag_inconsistent")
    if not expected_family_pass:
        blocked.append("candidate_promotion_gates_family_failed")
    return blocked


def _qqq_capture_gate_passes(
    metrics: Mapping[str, float | int],
    policy: CampaignCandidatePromotionPolicy,
) -> tuple[bool, bool]:
    """Return (qqq_capture_ratio_pass, qqq_downside_capture_pass).

    A candidate whose absolute correlation to QQQ is at or below
    :data:`QQQ_ORTHOGONALITY_CORRELATION_THRESHOLD` is economically
    orthogonal to it; its capture ratio versus QQQ is noise, not a
    meaningful promotion signal, so both capture gates trivially pass and
    the metrics are reported for diagnosis only.
    """
    if abs(float(metrics["qqq_correlation"])) <= QQQ_ORTHOGONALITY_CORRELATION_THRESHOLD:
        return True, True
    ratio_pass = float(metrics["qqq_capture_ratio"]) >= policy.qqq_capture_ratio_minimum
    downside_pass = float(metrics["qqq_downside_capture"]) <= policy.qqq_downside_capture_maximum
    return ratio_pass, downside_pass


def _candidate_promotion_passes(
    metrics: Mapping[str, float | int],
    policy: CampaignCandidatePromotionPolicy,
) -> dict[str, bool]:
    qqq_capture_ratio_pass, qqq_downside_capture_pass = _qqq_capture_gate_passes(metrics, policy)
    return {
        "cagr_excess_qqq": (float(metrics["cagr_excess_qqq"]) >= policy.cagr_excess_qqq_minimum),
        "qqq_capture_ratio": qqq_capture_ratio_pass,
        "qqq_downside_capture": qqq_downside_capture_pass,
        "max_drawdown": float(metrics["max_drawdown"]) >= policy.max_drawdown_minimum,
        "mar": float(metrics["mar"]) >= policy.mar_minimum,
        "positive_fold_count": (
            int(metrics["positive_fold_count"]) >= policy.minimum_positive_folds
        ),
        "stress_total_return": (
            float(metrics["stress_total_return"]) > policy.stress_total_return_minimum
        ),
    }


def _validate_compoundable_returns(values: list[float], *, label: str) -> None:
    if any(not math.isfinite(value) or value <= -1.0 for value in values):
        raise ValueError(f"{label} returns must be finite and greater than -1")


def _compound_return(values: list[float]) -> float:
    return math.expm1(math.fsum(math.log1p(value) for value in values))


def _annualized_compound_return(values: list[float], annualization_sessions: int) -> float:
    return math.expm1(
        math.fsum(math.log1p(value) for value in values) * annualization_sessions / len(values)
    )


def _maximum_drawdown(values: list[float]) -> float:
    wealth = 1.0
    peak = 1.0
    maximum_drawdown = 0.0
    for value in values:
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        maximum_drawdown = min(maximum_drawdown, wealth / peak - 1.0)
    return maximum_drawdown


def _conditional_capture(
    candidate_returns: list[float],
    benchmark_returns: list[float],
    *,
    positive: bool,
) -> float:
    selected = [
        index
        for index, value in enumerate(benchmark_returns)
        if (value > 0.0 if positive else value < 0.0)
    ]
    if not selected:
        raise ValueError("conditional capture benchmark subset is empty")
    candidate_compound = _compound_return([candidate_returns[index] for index in selected])
    benchmark_compound = _compound_return([benchmark_returns[index] for index in selected])
    if math.isclose(benchmark_compound, 0.0, rel_tol=0.0, abs_tol=1e-15):
        raise ValueError("conditional capture benchmark denominator is zero")
    return candidate_compound / benchmark_compound


def _pearson_correlation(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("correlation series must have equal length")
    if len(left) < 2:
        raise ValueError("correlation requires at least two observations")
    n = len(left)
    mean_left = math.fsum(left) / n
    mean_right = math.fsum(right) / n
    centered_left = [value - mean_left for value in left]
    centered_right = [value - mean_right for value in right]
    covariance = math.fsum(a * b for a, b in zip(centered_left, centered_right, strict=True))
    variance_left = math.fsum(a * a for a in centered_left)
    variance_right = math.fsum(b * b for b in centered_right)
    denominator = math.sqrt(variance_left * variance_right)
    if math.isclose(denominator, 0.0, rel_tol=0.0, abs_tol=1e-15):
        raise ValueError("correlation is undefined for a zero-variance return series")
    correlation = covariance / denominator
    return max(-1.0, min(1.0, correlation))


def _comparison_passes(value: float, threshold: float, operator: str) -> bool:
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    return value <= threshold


def _selection_artifact_blockers(
    contract: ResearchCampaignContract,
    cohort: CampaignPromotionCohort,
    *,
    campaign_dir: Path,
    repository_root: Path,
    contract_path: Path | None,
) -> list[str]:
    blocked: list[str] = []
    archive_path = campaign_dir / "qd-archive.json"
    ledger_path = campaign_dir / "allocation-ledger.jsonl"
    archive = None
    ledger = None
    if not archive_path.is_file() or archive_path.is_symlink():
        blocked.append("qd_archive_evidence_missing")
    else:
        archive_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        if archive_sha256 != cohort.qd_archive_sha256:
            blocked.append("promotion_cohort_qd_archive_sha256_mismatch")
        archive, archive_blocked = _load_qd_archive_evidence(
            contract,
            archive_path,
            repository_root=repository_root,
            contract_path=contract_path,
        )
        blocked.extend(archive_blocked)
    if not ledger_path.is_file() or ledger_path.is_symlink():
        blocked.append("allocation_ledger_evidence_missing")
    else:
        ledger, ledger_blocked = _load_allocation_ledger_evidence(
            contract,
            ledger_path,
            contract_path=contract_path,
        )
        blocked.extend(ledger_blocked)
        if ledger is not None and ledger.head_sha256 != cohort.allocation_ledger_head_sha256:
            blocked.append("promotion_cohort_allocation_ledger_head_sha256_mismatch")
    if archive is not None and ledger is not None:
        blocked.extend(_sealed_selection_inventory_blockers(contract, cohort, archive, ledger))
    return blocked


def _load_qd_archive_evidence(
    contract: ResearchCampaignContract,
    path: Path,
    *,
    repository_root: Path,
    contract_path: Path | None,
) -> tuple[Any | None, list[str]]:
    from pydantic import TypeAdapter

    from open_composer.research.quality_diversity import (
        QualityDiversityArchive,
        build_quality_diversity_archive,
        quality_diversity_policy_from_campaign,
    )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, ["qd_archive_evidence_invalid_json"]
    if not isinstance(payload, dict):
        return None, ["qd_archive_evidence_invalid_shape"]
    try:
        archive = TypeAdapter(QualityDiversityArchive).validate_python(payload)
    except ValidationError:
        return None, ["qd_archive_evidence_invalid_shape"]
    if archive.model_dump() != payload:
        return None, ["qd_archive_evidence_noncanonical_or_extra_fields"]
    if contract_path is None or not contract_path.is_file():
        return None, ["qd_archive_campaign_contract_path_missing"]
    contract_sha256 = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    expected_policy = quality_diversity_policy_from_campaign(
        contract,
        campaign_contract_sha256=contract_sha256,
    )
    try:
        rebuilt = build_quality_diversity_archive(
            list(archive.candidates),
            expected_policy,
            excluded_candidate_ids=archive.excluded_candidate_ids,
            require_complete_inventory=True,
        )
    except ValueError as exc:
        return None, [f"qd_archive_evidence_invalid:{exc}"]
    if rebuilt.model_dump() != archive.model_dump():
        return None, ["qd_archive_evidence_rebuild_mismatch"]

    blocked: list[str] = []
    for candidate in archive.candidates:
        for label, reference, expected_sha256 in (
            (
                "metrics_snapshot",
                candidate.metrics_snapshot_path,
                candidate.metrics_snapshot_sha256,
            ),
            (
                "partition_contract",
                candidate.partition_contract_path,
                candidate.partition_contract_sha256,
            ),
        ):
            artifact, error = _repository_evidence_path(reference, repository_root)
            if error:
                blocked.append(f"qd_archive_{label}_path_invalid:{candidate.candidate_id}:{error}")
            elif artifact is None or not artifact.is_file() or artifact.is_symlink():
                blocked.append(f"qd_archive_{label}_missing:{candidate.candidate_id}")
            elif hashlib.sha256(artifact.read_bytes()).hexdigest() != expected_sha256:
                blocked.append(f"qd_archive_{label}_sha256_mismatch:{candidate.candidate_id}")
    return archive, blocked


def _load_allocation_ledger_evidence(
    contract: ResearchCampaignContract,
    path: Path,
    *,
    contract_path: Path | None,
) -> tuple[Any | None, list[str]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError):
        return None, ["allocation_ledger_evidence_invalid_jsonl"]
    if not rows:
        return None, ["allocation_ledger_evidence_empty"]
    from open_composer.research.quality_diversity import (
        AllocationLedger,
        AllocationLedgerEntry,
        initialize_allocation_ledger,
        validate_allocation_ledger,
    )

    try:
        entries = tuple(AllocationLedgerEntry(**row) for row in rows)
    except (TypeError, ValueError):
        return None, ["allocation_ledger_evidence_invalid_row"]
    contract_sha256 = (
        hashlib.sha256(contract_path.read_bytes()).hexdigest()
        if contract_path is not None and contract_path.is_file()
        else "0" * 64
    )
    base_ledger = initialize_allocation_ledger(
        contract,
        campaign_contract_sha256=contract_sha256,
    )
    ledger = AllocationLedger(
        campaign_id=base_ledger.campaign_id,
        campaign_contract_sha256=base_ledger.campaign_contract_sha256,
        candidate_inventory_sha256=base_ledger.candidate_inventory_sha256,
        registered_candidate_ids=base_ledger.registered_candidate_ids,
        allowed_visibility_partitions=base_ledger.allowed_visibility_partitions,
        effective_trial_exposure_budget=base_ledger.effective_trial_exposure_budget,
        entries=entries,
        head_sha256=entries[-1].entry_sha256,
    )
    try:
        validate_allocation_ledger(ledger)
    except ValueError as exc:
        return None, [f"allocation_ledger_evidence_invalid:{exc}"]
    return ledger, []


def _sealed_selection_inventory_blockers(
    contract: ResearchCampaignContract,
    cohort: CampaignPromotionCohort,
    archive: Any,
    ledger: Any,
) -> list[str]:
    registered = {item.candidate_id for item in contract.candidate_blueprints}
    ledger_ids = {item.candidate_id for item in ledger.entries}
    blocked: list[str] = []
    missing = sorted(registered - ledger_ids)
    if missing:
        blocked.append("allocation_ledger_registered_candidates_missing:" + ",".join(missing))
    latest = {candidate_id: None for candidate_id in registered}
    exposure = {candidate_id: 0.0 for candidate_id in registered}
    for entry in ledger.entries:
        latest[entry.candidate_id] = entry.decision
        exposure[entry.candidate_id] += float(entry.effective_trial_exposure)
    nonterminal = sorted(
        candidate_id for candidate_id, decision in latest.items() if decision in {None, "allocate"}
    )
    if nonterminal:
        blocked.append("allocation_ledger_unsealed_candidate_decisions:" + ",".join(nonterminal))
    advanced = {candidate_id for candidate_id, decision in latest.items() if decision == "advance"}
    if advanced != set(cohort.candidate_ids):
        blocked.append("promotion_cohort_allocation_decisions_mismatch")
    dependency_skipped = {
        candidate_id
        for candidate_id, decision in latest.items()
        if decision == "dependency_skipped"
    }
    if dependency_skipped != set(archive.excluded_candidate_ids):
        blocked.append("qd_archive_dependency_skips_allocation_ledger_mismatch")
    underexposed = sorted(
        candidate_id
        for candidate_id in registered - dependency_skipped
        if exposure[candidate_id] < 1.0
    )
    if underexposed:
        blocked.append("allocation_ledger_candidate_exposure_below_one:" + ",".join(underexposed))
    elite_ids = {elite.candidate.candidate_id for elite in archive.elites}
    missing_elites = sorted(set(cohort.candidate_ids) - elite_ids)
    if missing_elites:
        blocked.append("promotion_cohort_candidates_not_qd_elites:" + ",".join(missing_elites))
    return blocked


def _tie_break_blockers(
    owner: str,
    rules: list[CampaignTieBreakRule],
) -> list[str]:
    blocked = _duplicate_blockers(
        f"tie_break_field:{owner}",
        [item.field for item in rules],
    )
    for rule in rules:
        normalized = rule.field.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in _NONDETERMINISTIC_TIE_BREAK_TOKENS:
            blocked.append(f"nondeterministic_tie_break:{owner}:{rule.field}")
    final_rule = rules[-1] if rules else None
    if final_rule is None or (
        final_rule.field != "candidate_id" or final_rule.direction != "ascending"
    ):
        blocked.append(f"tie_break_missing_final_candidate_id_ascending:{owner}")
    return blocked


def _contract_counts(contract: ResearchCampaignContract) -> CampaignValidationCounts:
    return CampaignValidationCounts(
        hypotheses=len(contract.hypotheses),
        branches=len(contract.branch_quotas),
        preregistered_candidates=len(contract.candidate_blueprints),
        visibility_partitions=len(contract.visibility_partitions),
        promotion_eligible_hypotheses=sum(item.promotion_eligible for item in contract.hypotheses),
        control_hypotheses=sum(item.role == "control" for item in contract.hypotheses),
        expensive_resource_rungs=len(contract.expensive_resource_rungs),
        candidate_budget=contract.exposure_budgets.candidate_budget,
        branch_minimum_candidates=sum(item.min_candidates for item in contract.branch_quotas),
        branch_maximum_candidates=sum(item.max_candidates for item in contract.branch_quotas),
        prior_effective_trial_count=contract.exposure_budgets.prior_effective_trial_count,
        cumulative_trial_exposure_budget=(
            contract.exposure_budgets.cumulative_trial_exposure_budget
        ),
    )


def incremental_effective_trial_count_from_ledger(
    contract: ResearchCampaignContract,
    ledger: Any,
) -> int:
    """Return this campaign's realized trial count, including its floor.

    The ledger cap is a resource/allocation cap for the current campaign.  The
    candidate floor keeps preregistered candidates, controls, and dependency
    skips in the multiple-testing family even when a candidate has no return
    stream.  Historical exposure is added only after the current increment is
    computed.
    """
    entries = getattr(ledger, "entries", None)
    if not isinstance(entries, tuple | list):
        raise ValueError("allocation ledger entries are missing")
    realized = math.ceil(math.fsum(float(entry.effective_trial_exposure) for entry in entries))
    candidate_floor = contract.exposure_budgets.candidate_budget
    incremental_cap = contract.exposure_budgets.cumulative_trial_exposure_budget
    incremental = max(candidate_floor, realized)
    if incremental > incremental_cap:
        raise ValueError(
            "incremental effective trial exposure exceeds campaign cap: "
            f"{incremental}>{incremental_cap}"
        )
    return incremental


def effective_trial_count_from_ledger(
    contract: ResearchCampaignContract,
    ledger: Any,
) -> int:
    """Return the exact DSR/PBO/SPA trial count bound to a validated ledger."""
    return contract.exposure_budgets.prior_effective_trial_count + (
        incremental_effective_trial_count_from_ledger(contract, ledger)
    )


def family_effective_trial_count_from_ledger(
    contract: ResearchCampaignContract,
    ledger: Any,
) -> int:
    """Return this campaign family's own DSR/PBO/SPA trial count.

    Unlike :func:`effective_trial_count_from_ledger`, this intentionally
    excludes ``exposure_budgets.prior_effective_trial_count`` (the lifetime,
    cross-campaign multiple-testing exposure carried only for audit purposes)
    and enforces a hard cap of :data:`MAX_FAMILY_EFFECTIVE_TRIAL_COUNT`. A
    campaign that needs more candidates than this cap must seal the family and
    open an independent one rather than keep growing its own trial count.
    """
    incremental = incremental_effective_trial_count_from_ledger(contract, ledger)
    if incremental > MAX_FAMILY_EFFECTIVE_TRIAL_COUNT:
        raise ValueError(
            "family effective trial count exceeds the hard cap: "
            f"{incremental}>{MAX_FAMILY_EFFECTIVE_TRIAL_COUNT}"
        )
    return incremental


def _coerce_contract(
    source: CampaignContractSource,
    root: Path | None,
) -> ResearchCampaignContract:
    if isinstance(source, ResearchCampaignContract):
        return source
    if isinstance(source, Mapping):
        return ResearchCampaignContract.model_validate(dict(source))
    return load_campaign_contract(source, root)


def _source_path(source: str | Path, root: Path | None) -> Path:
    if isinstance(source, Path):
        return source
    if CAMPAIGN_ID_RE.fullmatch(source):
        return campaign_contract_path(source, root)
    return Path(source)


def _source_path_or_none(
    source: CampaignContractSource,
    root: Path | None,
) -> Path | None:
    if isinstance(source, (str, Path)):
        return _source_path(source, root)
    return None


def _source_campaign_id(source: CampaignContractSource) -> str:
    if isinstance(source, ResearchCampaignContract):
        return source.campaign_id
    if isinstance(source, Mapping):
        value = source.get("campaign_id")
        return str(value) if value is not None else "<invalid>"
    if isinstance(source, str) and CAMPAIGN_ID_RE.fullmatch(source):
        return source
    path = Path(source)
    if path.name == CAMPAIGN_FILENAME:
        return path.parent.name
    return path.stem or "<invalid>"


def _validation_error_blockers(exc: ValidationError) -> list[str]:
    blocked: list[str] = []
    for error in exc.errors(include_url=False):
        location = ".".join(str(item) for item in error["loc"]) or "root"
        error_type = str(error["type"])
        invalid_input = error.get("input")
        if isinstance(invalid_input, str) and invalid_input in {
            "unrestricted_code_generation",
            "unrestricted_mutation",
            "genetic_programming",
        }:
            blocked.append(f"unrestricted_generation_or_mutation_mode:{invalid_input}")
        blocked.append(f"contract_schema_invalid:{location}:{error_type}")
    return _dedupe(blocked)


def _blocked_report(
    campaign_id: str,
    stage: CampaignStage,
    path: Path | None,
    blocked: list[str],
) -> CampaignValidationReport:
    return CampaignValidationReport(
        campaign_id=campaign_id,
        stage=stage,
        contract_path=str(path) if path is not None else None,
        status="blocked",
        blocked=_dedupe(blocked),
        warnings=[],
    )


def _duplicate_blockers(label: str, values: list[Any]) -> list[str]:
    seen: set[Any] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(str(value))
        seen.add(value)
    return [f"duplicate_{label}:{value}" for value in sorted(duplicates)]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


__all__ = [
    "CAMPAIGN_FILENAME",
    "CAMPAIGN_ROOT",
    "CampaignAdvancingPairCorrelationPolicy",
    "CampaignBranchQuota",
    "CampaignCandidateBlueprint",
    "CampaignCandidatePromotionEvidence",
    "CampaignCandidatePromotionMetrics",
    "CampaignCandidatePromotionPolicy",
    "CampaignCommonReturnMatrix",
    "CampaignExpensiveResourceRung",
    "CampaignExplorationPolicy",
    "CampaignExposureBudgets",
    "CampaignHypothesis",
    "CampaignPromotionEvidence",
    "CampaignPromotionCohort",
    "CampaignPreOOSSeal",
    "CampaignQDArchive",
    "CampaignReturnStreamIdentity",
    "CampaignStatisticalFamilyGates",
    "CampaignStatisticalFamilyPolicy",
    "CampaignStatisticalGate",
    "CampaignTieBreakRule",
    "CampaignValidationCounts",
    "CampaignValidationReport",
    "CampaignVisibilityPartition",
    "ResearchCampaignContract",
    "campaign_contract_path",
    "load_campaign_contract",
    "recompute_candidate_promotion_metrics",
    "validate_campaign_contract",
]
