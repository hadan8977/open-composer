from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from numbers import Real
from typing import Literal

from open_composer.research.kernel.datamodel import ResearchDataModel

QualityDirection = Literal["maximize", "minimize"]
AllocationDecision = Literal[
    "allocate",
    "advance",
    "prune",
    "reject",
    "stop",
    "dependency_skipped",
]
DescriptorValue = str | int | float | bool

SELECTION_VISIBILITY_PARTITIONS = frozenset({"train", "development"})
FORBIDDEN_SELECTION_VISIBILITY_PREFIXES = ("frozen_oos", "challenge", "forward")
ALLOCATION_DECISIONS = frozenset(
    {"allocate", "advance", "prune", "reject", "stop", "dependency_skipped"}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class QualityDiversityCandidate(ResearchDataModel):
    candidate_id: str
    hypothesis_id: str
    branch: str
    archive_descriptors: dict[str, DescriptorValue]
    quality: float
    quality_metric: str
    visibility_partition: str
    metrics_snapshot_path: str
    metrics_snapshot_sha256: str
    partition_contract_path: str
    partition_contract_sha256: str
    promotion_eligible: bool
    resource_rung: int


@dataclass(frozen=True)
class QualityDiversityPolicy(ResearchDataModel):
    campaign_id: str
    campaign_contract_sha256: str
    descriptor_names: tuple[str, ...]
    quality_direction: QualityDirection
    quality_metric: str
    quality_partition_id: str
    candidate_budget: int
    registered_candidate_ids: tuple[str, ...]
    candidate_hypothesis_ids: dict[str, str]
    candidate_branch_ids: dict[str, str]
    candidate_promotion_eligibility: dict[str, bool]
    candidate_archive_descriptors: dict[str, dict[str, DescriptorValue]]
    ranking_fields: tuple[str, ...] = ("quality", "candidate_id")
    selection_visibility_partitions: tuple[str, ...] = ("train", "development")
    branch_min_quotas: dict[str, int] = field(default_factory=dict)
    branch_max_quotas: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityDiversityElite(ResearchDataModel):
    cell_id: str
    cell_descriptors: dict[str, DescriptorValue]
    candidate: QualityDiversityCandidate


@dataclass(frozen=True)
class BranchQuotaReport(ResearchDataModel):
    branch: str
    candidate_count: int
    elite_count: int
    min_quota: int | None
    max_quota: int | None
    minimum_met: bool | None
    maximum_met: bool | None


@dataclass(frozen=True)
class QualityDiversityArchive(ResearchDataModel):
    policy: QualityDiversityPolicy
    eligible_candidate_count: int
    candidates: tuple[QualityDiversityCandidate, ...]
    excluded_candidate_ids: tuple[str, ...]
    elites: tuple[QualityDiversityElite, ...]
    branch_quotas: tuple[BranchQuotaReport, ...]

    @property
    def elite_count(self) -> int:
        return len(self.elites)


def quality_diversity_policy_from_campaign(
    contract: object,
    *,
    campaign_contract_sha256: str,
) -> QualityDiversityPolicy:
    """Build the only supported QD policy shape from a validated campaign contract."""
    from open_composer.research.campaign import ResearchCampaignContract

    if not isinstance(contract, ResearchCampaignContract):
        raise TypeError("quality-diversity policy requires a ResearchCampaignContract")
    candidates = contract.candidate_blueprints
    return QualityDiversityPolicy(
        campaign_id=contract.campaign_id,
        campaign_contract_sha256=campaign_contract_sha256,
        descriptor_names=tuple(contract.qd_archive.cell_key_fields),
        quality_direction=contract.qd_archive.quality_direction,
        quality_metric=contract.qd_archive.quality_metric,
        quality_partition_id=contract.qd_archive.quality_partition_id,
        candidate_budget=contract.exposure_budgets.candidate_budget,
        registered_candidate_ids=tuple(item.candidate_id for item in candidates),
        candidate_hypothesis_ids={item.candidate_id: item.hypothesis_id for item in candidates},
        candidate_branch_ids={item.candidate_id: item.branch_id for item in candidates},
        candidate_promotion_eligibility={
            item.candidate_id: item.promotion_eligible for item in candidates
        },
        candidate_archive_descriptors={
            item.candidate_id: dict(item.archive_descriptors) for item in candidates
        },
        selection_visibility_partitions=tuple(
            item.partition_id
            for item in contract.visibility_partitions
            if item.kind == "development"
        ),
        branch_min_quotas={item.branch_id: item.min_candidates for item in contract.branch_quotas},
        branch_max_quotas={item.branch_id: item.max_candidates for item in contract.branch_quotas},
    )


def build_quality_diversity_archive(
    candidates: list[QualityDiversityCandidate] | tuple[QualityDiversityCandidate, ...],
    policy: QualityDiversityPolicy,
    *,
    excluded_candidate_ids: list[str] | tuple[str, ...] = (),
    require_complete_inventory: bool = False,
) -> QualityDiversityArchive:
    """Build one deterministic elite per preregistered descriptor cell."""

    _validate_policy(policy)
    ordered = sorted(candidates, key=lambda candidate: candidate.candidate_id)
    _validate_candidates(ordered, policy)
    excluded = tuple(sorted(excluded_candidate_ids))
    _validate_archive_inventory(
        ordered,
        excluded,
        policy,
        require_complete_inventory=require_complete_inventory,
    )

    elites_by_cell: dict[str, QualityDiversityElite] = {}
    for candidate in ordered:
        descriptors = {
            name: candidate.archive_descriptors[name] for name in policy.descriptor_names
        }
        cell_id = _canonical_json(descriptors)
        incumbent = elites_by_cell.get(cell_id)
        if incumbent is None or _candidate_precedes(
            candidate,
            incumbent.candidate,
            direction=policy.quality_direction,
        ):
            elites_by_cell[cell_id] = QualityDiversityElite(
                cell_id=cell_id,
                cell_descriptors=descriptors,
                candidate=candidate,
            )

    elites = tuple(elites_by_cell[cell_id] for cell_id in sorted(elites_by_cell))
    branch_quotas = _branch_quota_reports(ordered, elites, policy)
    return QualityDiversityArchive(
        policy=policy,
        eligible_candidate_count=len(ordered),
        candidates=tuple(ordered),
        excluded_candidate_ids=excluded,
        elites=elites,
        branch_quotas=branch_quotas,
    )


def _validate_policy(policy: QualityDiversityPolicy) -> None:
    if not _is_nonempty_identifier(policy.campaign_id):
        raise ValueError("quality-diversity campaign ID must be non-empty")
    if not _is_sha256(policy.campaign_contract_sha256):
        raise ValueError("quality-diversity campaign contract identity is not SHA-256")
    if not policy.descriptor_names:
        raise ValueError("quality-diversity policy requires at least one cell descriptor")
    if len(set(policy.descriptor_names)) != len(policy.descriptor_names):
        raise ValueError("quality-diversity cell descriptors must be unique")
    if any(not _is_nonempty_identifier(name) for name in policy.descriptor_names):
        raise ValueError("quality-diversity cell descriptor names must be non-empty")
    if policy.quality_direction not in {"maximize", "minimize"}:
        raise ValueError("quality-diversity quality direction must be maximize or minimize")
    if not _is_nonempty_identifier(policy.quality_metric):
        raise ValueError("quality-diversity quality metric must be non-empty")
    if policy.ranking_fields != ("quality", "candidate_id"):
        raise ValueError("quality-diversity ranking must preregister quality then candidate_id")
    if not _is_nonnegative_int(policy.candidate_budget) or policy.candidate_budget == 0:
        raise ValueError("quality-diversity candidate budget must be a positive integer")
    if len(set(policy.registered_candidate_ids)) != len(policy.registered_candidate_ids):
        raise ValueError("quality-diversity registered candidate IDs must be unique")
    if any(not _is_nonempty_identifier(item) for item in policy.registered_candidate_ids):
        raise ValueError("quality-diversity registered candidate IDs must be non-empty")
    if len(policy.registered_candidate_ids) != policy.candidate_budget:
        raise ValueError(
            "quality-diversity registered candidate inventory must equal candidate budget"
        )
    registered = set(policy.registered_candidate_ids)
    binding_maps = {
        "hypothesis": policy.candidate_hypothesis_ids,
        "branch": policy.candidate_branch_ids,
        "promotion": policy.candidate_promotion_eligibility,
        "archive descriptor": policy.candidate_archive_descriptors,
    }
    for label, bindings in binding_maps.items():
        if set(bindings) != registered:
            raise ValueError(
                f"quality-diversity {label} bindings must match registered candidate inventory"
            )
    if any(not _is_nonempty_identifier(item) for item in policy.candidate_hypothesis_ids.values()):
        raise ValueError("quality-diversity candidate hypothesis bindings must be non-empty")
    if any(not _is_nonempty_identifier(item) for item in policy.candidate_branch_ids.values()):
        raise ValueError("quality-diversity candidate branch bindings must be non-empty")

    partitions = policy.selection_visibility_partitions
    if not partitions or len(set(partitions)) != len(partitions):
        raise ValueError("selection visibility partitions must be non-empty and unique")
    invalid_partitions = sorted(
        partition for partition in partitions if not _is_development_partition_id(partition)
    )
    if invalid_partitions:
        raise ValueError(
            "selection visibility is restricted to explicit train/development partitions: "
            + ", ".join(invalid_partitions)
        )
    if policy.quality_partition_id not in partitions:
        raise ValueError("quality-diversity quality partition is not selection-visible")

    branches = set(policy.branch_min_quotas) | set(policy.branch_max_quotas)
    if any(not _is_nonempty_identifier(branch) for branch in branches):
        raise ValueError("branch quota names must be non-empty")
    for branch in sorted(branches):
        minimum = policy.branch_min_quotas.get(branch)
        maximum = policy.branch_max_quotas.get(branch)
        if minimum is not None and not _is_nonnegative_int(minimum):
            raise ValueError(f"branch minimum quota must be a nonnegative integer: {branch}")
        if maximum is not None and not _is_nonnegative_int(maximum):
            raise ValueError(f"branch maximum quota must be a nonnegative integer: {branch}")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"branch minimum quota exceeds maximum quota: {branch}")


def _validate_candidates(
    candidates: list[QualityDiversityCandidate],
    policy: QualityDiversityPolicy,
) -> None:
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("quality-diversity candidate_id values must be unique")
    if len(candidates) > policy.candidate_budget:
        raise ValueError("quality-diversity candidate budget exceeded")
    unregistered = sorted(set(candidate_ids) - set(policy.registered_candidate_ids))
    if unregistered:
        raise ValueError(
            "quality-diversity candidates are outside the preregistered inventory: "
            + ", ".join(unregistered)
        )

    for candidate in candidates:
        if not _is_nonempty_identifier(candidate.candidate_id):
            raise ValueError("quality-diversity candidate_id must be non-empty")
        if not _is_nonempty_identifier(candidate.hypothesis_id):
            raise ValueError(f"candidate hypothesis_id is missing: {candidate.candidate_id}")
        if not _is_nonempty_identifier(candidate.branch):
            raise ValueError(f"candidate branch is missing: {candidate.candidate_id}")
        if not _is_finite_number(candidate.quality):
            raise ValueError(f"candidate quality must be finite: {candidate.candidate_id}")
        _validate_selection_visibility(
            candidate.visibility_partition,
            allowed=set(policy.selection_visibility_partitions),
            subject=f"candidate {candidate.candidate_id}",
        )
        if candidate.quality_metric != policy.quality_metric:
            raise ValueError(f"candidate quality metric identity drift: {candidate.candidate_id}")
        if candidate.visibility_partition != policy.quality_partition_id:
            raise ValueError(
                f"candidate quality partition identity drift: {candidate.candidate_id}"
            )
        if not _is_sha256(candidate.metrics_snapshot_sha256):
            raise ValueError(
                f"candidate metrics snapshot identity is not SHA-256: {candidate.candidate_id}"
            )
        if not _is_nonempty_identifier(candidate.metrics_snapshot_path):
            raise ValueError(
                f"candidate metrics snapshot path is missing: {candidate.candidate_id}"
            )
        if not _is_sha256(candidate.partition_contract_sha256):
            raise ValueError(
                f"candidate partition contract identity is not SHA-256: {candidate.candidate_id}"
            )
        if not _is_nonempty_identifier(candidate.partition_contract_path):
            raise ValueError(
                f"candidate partition contract path is missing: {candidate.candidate_id}"
            )
        if candidate.hypothesis_id != policy.candidate_hypothesis_ids[candidate.candidate_id]:
            raise ValueError(f"candidate hypothesis binding drift: {candidate.candidate_id}")
        if candidate.branch != policy.candidate_branch_ids[candidate.candidate_id]:
            raise ValueError(f"candidate branch binding drift: {candidate.candidate_id}")
        if (
            candidate.promotion_eligible
            != policy.candidate_promotion_eligibility[candidate.candidate_id]
        ):
            raise ValueError(f"candidate promotion eligibility drift: {candidate.candidate_id}")
        if not _is_nonnegative_int(candidate.resource_rung):
            raise ValueError(
                f"candidate resource_rung must be a nonnegative integer: {candidate.candidate_id}"
            )
        if not isinstance(candidate.archive_descriptors, dict):
            raise ValueError(
                f"candidate archive descriptors are malformed: {candidate.candidate_id}"
            )
        missing = [
            name for name in policy.descriptor_names if name not in candidate.archive_descriptors
        ]
        if missing:
            raise ValueError(
                f"candidate is missing cell descriptors ({', '.join(missing)}): "
                f"{candidate.candidate_id}"
            )
        unexpected = sorted(set(candidate.archive_descriptors) - set(policy.descriptor_names))
        if unexpected:
            raise ValueError(
                f"candidate has undeclared cell descriptors ({', '.join(unexpected)}): "
                f"{candidate.candidate_id}"
            )
        declared_branches = set(policy.branch_min_quotas) | set(policy.branch_max_quotas)
        if declared_branches and candidate.branch not in declared_branches:
            raise ValueError(
                f"candidate branch is outside preregistered quotas: {candidate.candidate_id}:"
                f"{candidate.branch}"
            )
        for name in policy.descriptor_names:
            _validate_descriptor_value(
                candidate.archive_descriptors[name],
                candidate_id=candidate.candidate_id,
                descriptor_name=name,
            )
        if (
            candidate.archive_descriptors
            != policy.candidate_archive_descriptors[candidate.candidate_id]
        ):
            raise ValueError(
                f"candidate archive descriptor binding drift: {candidate.candidate_id}"
            )
    candidate_counts = {
        branch: sum(candidate.branch == branch for candidate in candidates)
        for branch in policy.branch_max_quotas
    }
    exceeded = [
        f"{branch}:{candidate_counts[branch]}>{maximum}"
        for branch, maximum in sorted(policy.branch_max_quotas.items())
        if candidate_counts[branch] > maximum
    ]
    if exceeded:
        raise ValueError("quality-diversity branch maximum quota exceeded: " + ", ".join(exceeded))


def _validate_archive_inventory(
    candidates: list[QualityDiversityCandidate],
    excluded_candidate_ids: tuple[str, ...],
    policy: QualityDiversityPolicy,
    *,
    require_complete_inventory: bool,
) -> None:
    candidate_ids = {candidate.candidate_id for candidate in candidates}
    excluded_ids = set(excluded_candidate_ids)
    if len(excluded_ids) != len(excluded_candidate_ids):
        raise ValueError("quality-diversity excluded candidate IDs must be unique")
    if candidate_ids & excluded_ids:
        raise ValueError("quality-diversity candidate cannot be both evaluated and excluded")
    unregistered = sorted(excluded_ids - set(policy.registered_candidate_ids))
    if unregistered:
        raise ValueError(
            "quality-diversity excluded candidates are outside the preregistered inventory: "
            + ", ".join(unregistered)
        )
    if require_complete_inventory:
        missing = sorted(set(policy.registered_candidate_ids) - candidate_ids - excluded_ids)
        if missing:
            raise ValueError(
                "quality-diversity sealed inventory is incomplete: " + ", ".join(missing)
            )


def _candidate_precedes(
    candidate: QualityDiversityCandidate,
    incumbent: QualityDiversityCandidate,
    *,
    direction: QualityDirection,
) -> bool:
    if candidate.quality == incumbent.quality:
        return candidate.candidate_id < incumbent.candidate_id
    if direction == "maximize":
        return candidate.quality > incumbent.quality
    return candidate.quality < incumbent.quality


def _branch_quota_reports(
    candidates: list[QualityDiversityCandidate],
    elites: tuple[QualityDiversityElite, ...],
    policy: QualityDiversityPolicy,
) -> tuple[BranchQuotaReport, ...]:
    branches = sorted(
        {candidate.branch for candidate in candidates}
        | set(policy.branch_min_quotas)
        | set(policy.branch_max_quotas)
    )
    candidate_counts = {
        branch: sum(candidate.branch == branch for candidate in candidates) for branch in branches
    }
    elite_counts = {
        branch: sum(elite.candidate.branch == branch for elite in elites) for branch in branches
    }
    reports: list[BranchQuotaReport] = []
    for branch in branches:
        minimum = policy.branch_min_quotas.get(branch)
        maximum = policy.branch_max_quotas.get(branch)
        count = candidate_counts[branch]
        reports.append(
            BranchQuotaReport(
                branch=branch,
                candidate_count=count,
                elite_count=elite_counts[branch],
                min_quota=minimum,
                max_quota=maximum,
                minimum_met=None if minimum is None else count >= minimum,
                maximum_met=None if maximum is None else count <= maximum,
            )
        )
    return tuple(reports)


@dataclass(frozen=True)
class AllocationLedgerEntry(ResearchDataModel):
    sequence: int
    candidate_id: str
    decision: AllocationDecision
    resource_used: dict[str, float]
    metrics_snapshot_sha256: str
    effective_trial_exposure: float
    visibility_partition: str
    previous_entry_sha256: str | None
    entry_sha256: str


@dataclass(frozen=True)
class AllocationLedger(ResearchDataModel):
    campaign_id: str
    campaign_contract_sha256: str
    candidate_inventory_sha256: str
    registered_candidate_ids: tuple[str, ...]
    allowed_visibility_partitions: tuple[str, ...]
    effective_trial_exposure_budget: float
    entries: tuple[AllocationLedgerEntry, ...] = field(default_factory=tuple)
    head_sha256: str | None = None


def initialize_allocation_ledger(
    contract: object,
    *,
    campaign_contract_sha256: str,
) -> AllocationLedger:
    """Bind a new empty allocation ledger to one immutable campaign inventory."""
    from open_composer.research.campaign import ResearchCampaignContract

    if not isinstance(contract, ResearchCampaignContract):
        raise TypeError("allocation ledger requires a ResearchCampaignContract")
    candidate_payload = [item.model_dump(mode="json") for item in contract.candidate_blueprints]
    candidate_inventory_sha256 = hashlib.sha256(
        _canonical_json(candidate_payload).encode("ascii")
    ).hexdigest()
    ledger = AllocationLedger(
        campaign_id=contract.campaign_id,
        campaign_contract_sha256=campaign_contract_sha256,
        candidate_inventory_sha256=candidate_inventory_sha256,
        registered_candidate_ids=tuple(item.candidate_id for item in contract.candidate_blueprints),
        allowed_visibility_partitions=tuple(
            item.partition_id
            for item in contract.visibility_partitions
            if item.kind == "development"
        ),
        effective_trial_exposure_budget=float(
            contract.exposure_budgets.cumulative_trial_exposure_budget
        ),
    )
    validate_allocation_ledger(ledger)
    return ledger


def append_allocation_entry(
    ledger: AllocationLedger,
    *,
    candidate_id: str,
    decision: AllocationDecision,
    resource_used: dict[str, float],
    metrics_snapshot_sha256: str,
    effective_trial_exposure: float,
    visibility_partition: str,
) -> AllocationLedger:
    """Return a new ledger containing exactly one validated append."""

    validate_allocation_ledger(ledger)
    sequence = len(ledger.entries) + 1
    previous_entry_sha256 = ledger.head_sha256
    entry_without_hash = AllocationLedgerEntry(
        sequence=sequence,
        candidate_id=candidate_id,
        decision=decision,
        resource_used=dict(resource_used),
        metrics_snapshot_sha256=metrics_snapshot_sha256,
        effective_trial_exposure=effective_trial_exposure,
        visibility_partition=visibility_partition,
        previous_entry_sha256=previous_entry_sha256,
        entry_sha256="",
    )
    _validate_allocation_entry_fields(entry_without_hash)
    _validate_selection_visibility(
        entry_without_hash.visibility_partition,
        allowed=set(ledger.allowed_visibility_partitions),
        subject=f"allocation ledger entry {sequence}",
    )
    entry_sha256 = compute_allocation_entry_sha256(ledger, entry_without_hash)
    entry = AllocationLedgerEntry(
        sequence=sequence,
        candidate_id=candidate_id,
        decision=decision,
        resource_used=dict(resource_used),
        metrics_snapshot_sha256=metrics_snapshot_sha256,
        effective_trial_exposure=effective_trial_exposure,
        visibility_partition=visibility_partition,
        previous_entry_sha256=previous_entry_sha256,
        entry_sha256=entry_sha256,
    )
    extended = AllocationLedger(
        campaign_id=ledger.campaign_id,
        campaign_contract_sha256=ledger.campaign_contract_sha256,
        candidate_inventory_sha256=ledger.candidate_inventory_sha256,
        registered_candidate_ids=ledger.registered_candidate_ids,
        allowed_visibility_partitions=ledger.allowed_visibility_partitions,
        effective_trial_exposure_budget=ledger.effective_trial_exposure_budget,
        entries=(*ledger.entries, entry),
        head_sha256=entry.entry_sha256,
    )
    validate_allocation_extension(ledger, extended)
    return extended


def validate_allocation_ledger(
    ledger: AllocationLedger,
    *,
    expected_head_sha256: str | None = None,
) -> None:
    if not _is_nonempty_identifier(ledger.campaign_id):
        raise ValueError("allocation ledger campaign_id must be non-empty")
    if not _is_sha256(ledger.campaign_contract_sha256):
        raise ValueError("allocation ledger campaign contract identity is not SHA-256")
    if not _is_sha256(ledger.candidate_inventory_sha256):
        raise ValueError("allocation ledger candidate inventory identity is not SHA-256")
    if not ledger.registered_candidate_ids or len(set(ledger.registered_candidate_ids)) != len(
        ledger.registered_candidate_ids
    ):
        raise ValueError("allocation ledger registered candidate IDs must be non-empty and unique")
    if any(not _is_nonempty_identifier(item) for item in ledger.registered_candidate_ids):
        raise ValueError("allocation ledger registered candidate IDs must be non-empty")
    if not ledger.allowed_visibility_partitions or len(
        set(ledger.allowed_visibility_partitions)
    ) != len(ledger.allowed_visibility_partitions):
        raise ValueError(
            "allocation ledger allowed visibility partitions must be non-empty and unique"
        )
    invalid_partitions = sorted(
        item
        for item in ledger.allowed_visibility_partitions
        if not _is_development_partition_id(item)
    )
    if invalid_partitions:
        raise ValueError(
            "allocation ledger visibility is restricted to train/development partitions: "
            + ", ".join(invalid_partitions)
        )
    if not _is_finite_number(ledger.effective_trial_exposure_budget) or (
        float(ledger.effective_trial_exposure_budget) <= 0.0
    ):
        raise ValueError("allocation ledger trial exposure budget must be finite and positive")
    if expected_head_sha256 is not None and not _is_sha256(expected_head_sha256):
        raise ValueError("expected allocation ledger head is not a SHA-256 identity")

    previous_hash: str | None = None
    effective_trial_exposure = 0.0
    for expected_sequence, entry in enumerate(ledger.entries, start=1):
        if entry.sequence != expected_sequence:
            raise ValueError("allocation ledger sequence must be monotonically contiguous")
        _validate_allocation_entry_fields(entry)
        _validate_selection_visibility(
            entry.visibility_partition,
            allowed=set(ledger.allowed_visibility_partitions),
            subject=f"allocation ledger entry {entry.sequence}",
        )
        if entry.candidate_id not in ledger.registered_candidate_ids:
            raise ValueError(
                f"allocation ledger candidate is not preregistered: {entry.candidate_id}"
            )
        if entry.previous_entry_sha256 != previous_hash:
            raise ValueError("allocation ledger previous-entry hash chain is invalid")
        expected_entry_hash = compute_allocation_entry_sha256(ledger, entry)
        if entry.entry_sha256 != expected_entry_hash:
            raise ValueError("allocation ledger entry hash identity is invalid")
        effective_trial_exposure += float(entry.effective_trial_exposure)
        if effective_trial_exposure > float(ledger.effective_trial_exposure_budget):
            raise ValueError("allocation ledger effective trial exposure budget exceeded")
        previous_hash = entry.entry_sha256

    if ledger.head_sha256 != previous_hash:
        raise ValueError("allocation ledger head does not match the hash chain")
    if expected_head_sha256 is not None and ledger.head_sha256 != expected_head_sha256:
        raise ValueError("allocation ledger head differs from the expected sealed identity")


def validate_allocation_extension(
    previous: AllocationLedger,
    current: AllocationLedger,
) -> None:
    """Prove that ``current`` preserves every entry in ``previous`` exactly."""

    validate_allocation_ledger(previous)
    validate_allocation_ledger(current)
    if current.campaign_id != previous.campaign_id:
        raise ValueError("allocation ledger campaign identity changed")
    if current.campaign_contract_sha256 != previous.campaign_contract_sha256:
        raise ValueError("allocation ledger campaign contract identity changed")
    if current.candidate_inventory_sha256 != previous.candidate_inventory_sha256:
        raise ValueError("allocation ledger candidate inventory identity changed")
    if current.registered_candidate_ids != previous.registered_candidate_ids:
        raise ValueError("allocation ledger registered candidate inventory changed")
    if current.allowed_visibility_partitions != previous.allowed_visibility_partitions:
        raise ValueError("allocation ledger visibility partition contract changed")
    if current.effective_trial_exposure_budget != previous.effective_trial_exposure_budget:
        raise ValueError("allocation ledger trial exposure budget changed")
    if len(current.entries) < len(previous.entries):
        raise ValueError("allocation ledger cannot truncate its existing prefix")
    if current.entries[: len(previous.entries)] != previous.entries:
        raise ValueError("allocation ledger existing prefix was mutated or reordered")


def compute_allocation_entry_sha256(
    ledger: AllocationLedger,
    entry: AllocationLedgerEntry,
) -> str:
    subject = {
        "campaign_id": ledger.campaign_id,
        "campaign_contract_sha256": ledger.campaign_contract_sha256,
        "candidate_inventory_sha256": ledger.candidate_inventory_sha256,
        "registered_candidate_ids": ledger.registered_candidate_ids,
        "allowed_visibility_partitions": ledger.allowed_visibility_partitions,
        "effective_trial_exposure_budget": ledger.effective_trial_exposure_budget,
        "sequence": entry.sequence,
        "candidate_id": entry.candidate_id,
        "decision": entry.decision,
        "resource_used": entry.resource_used,
        "metrics_snapshot_sha256": entry.metrics_snapshot_sha256,
        "effective_trial_exposure": entry.effective_trial_exposure,
        "visibility_partition": entry.visibility_partition,
        "previous_entry_sha256": entry.previous_entry_sha256,
    }
    return hashlib.sha256(_canonical_json(subject).encode("ascii")).hexdigest()


def _validate_allocation_entry_fields(entry: AllocationLedgerEntry) -> None:
    if not _is_nonempty_identifier(entry.candidate_id):
        raise ValueError("allocation ledger candidate_id must be non-empty")
    if entry.decision not in ALLOCATION_DECISIONS:
        raise ValueError(f"allocation ledger decision is unsupported: {entry.decision}")
    if not _is_nonnegative_int(entry.sequence) or entry.sequence == 0:
        raise ValueError("allocation ledger sequence must be a positive integer")
    if not isinstance(entry.resource_used, dict) or not entry.resource_used:
        raise ValueError("allocation ledger resource_used must be a non-empty mapping")
    for resource_name, value in entry.resource_used.items():
        if not _is_nonempty_identifier(resource_name):
            raise ValueError("allocation ledger resource names must be non-empty")
        if not _is_finite_number(value) or float(value) < 0.0:
            raise ValueError(
                f"allocation ledger resource usage must be finite and nonnegative: {resource_name}"
            )
    if not _is_sha256(entry.metrics_snapshot_sha256):
        raise ValueError("allocation ledger metrics snapshot must be a lowercase SHA-256 identity")
    if not _is_finite_number(entry.effective_trial_exposure) or (
        float(entry.effective_trial_exposure) < 0.0
    ):
        raise ValueError(
            "allocation ledger effective trial exposure must be finite and nonnegative"
        )
    if entry.decision == "dependency_skipped" and float(entry.effective_trial_exposure) != 0.0:
        raise ValueError("dependency-skipped allocation entry must have zero trial exposure")
    if entry.previous_entry_sha256 is not None and not _is_sha256(entry.previous_entry_sha256):
        raise ValueError("allocation ledger previous-entry identity is not SHA-256")
    if entry.entry_sha256 and not _is_sha256(entry.entry_sha256):
        raise ValueError("allocation ledger entry identity is not SHA-256")


def _validate_selection_visibility(
    partition: str,
    *,
    allowed: set[str],
    subject: str,
) -> None:
    if not isinstance(partition, str):
        raise ValueError(f"{subject} selection visibility partition is malformed")
    normalized = partition.strip().lower()
    if normalized.startswith(FORBIDDEN_SELECTION_VISIBILITY_PREFIXES):
        raise ValueError(f"{subject} uses forbidden selection visibility: {partition}")
    if partition not in allowed:
        raise ValueError(
            f"{subject} selection visibility is outside explicit train/development partitions: "
            f"{partition}"
        )


def _validate_descriptor_value(
    value: DescriptorValue,
    *,
    candidate_id: str,
    descriptor_name: str,
) -> None:
    if isinstance(value, str):
        if not value or value != value.strip():
            raise ValueError(
                f"candidate cell descriptor is empty or unnormalized: "
                f"{candidate_id}.{descriptor_name}"
            )
        return
    if isinstance(value, bool | int):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    raise ValueError(
        f"candidate cell descriptor must be a finite JSON scalar: {candidate_id}.{descriptor_name}"
    )


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _is_nonempty_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _is_development_partition_id(value: object) -> bool:
    if not _is_nonempty_identifier(value):
        return False
    normalized = str(value).lower()
    return normalized in SELECTION_VISIBILITY_PARTITIONS or normalized.startswith(
        ("train_", "train-", "development_", "development-")
    )


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_finite_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None
