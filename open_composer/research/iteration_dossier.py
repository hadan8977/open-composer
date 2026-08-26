from __future__ import annotations

import hashlib
import json
import math
import re
import stat
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,80}$")
ITERATION_ROOT = Path("reports/research/iterations")
# Frozen migration inventory. Any iteration not present here must use schema v3
# and bind a canonical campaign, regardless of its self-declared timestamp.
LEGACY_UNBOUND_ITERATION_IDS = frozenset(
    {
        "mom_core_satellite_r7",
        "mom_dynamic_theme_chain_r8",
        "mom_dynamic_theme_stock_r9",
        "mom_etf_core_diversifier_forward_r10",
        "mom_etf_structural_family_r9",
        "mom_event_seeded_theme_stock_r10",
        "mom_high_beta_sleeve_ensemble_r1",
        "mom_minute_r1",
        "mom_minute_r2",
        "mom_minute_r3_ml",
        "mom_minute_r4_portfolio",
        "mom_multiasset_ai_r2",
        "mom_multiasset_forward_multimodal_r4",
        "mom_multiasset_forward_multimodal_r5",
        "mom_multiasset_forward_multimodal_r6",
        "mom_multiasset_ml_r1",
        "mom_multiasset_multimodal_r3",
        "mom_multiasset_paper_control_r7",
        "mom_multiasset_r1",
        "mom_multiscale_event_r5",
        "mom_multiscale_low_turnover_r6",
        "mom_pit_semantic_theme_r11",
        "mom_pit_semantic_theme_r12",
        "mom_pit_semantic_theme_r13",
        "mom_pit_semantic_theme_r14",
        "mom_pit_semantic_theme_r15",
        "mom_pit_semantic_theme_r16",
        "mom_pit_semantic_theme_r17",
        "mom_pit_semantic_theme_r18",
        "mom_pit_semantic_theme_r19",
        "mom_pit_semantic_theme_r20",
        "mom_pit_semantic_theme_r21",
        "mom_pit_semantic_theme_r22",
        "mom_pit_semantic_theme_r23",
        "mom_pit_semantic_theme_r24",
        "mom_robust_momentum_r4",
        "mom_spy_dual_trend_core_r8",
        "mom_stock_intraday_codesign_q1",
        "mom_vix_term_structure_overlay_r1",
        "mom_vix_term_structure_overlay_r1_implfix1",
        "nasdaq_lse_router_paper_r1",
    }
)
REQUIRED_SOURCE_FIELDS = {
    "url",
    "published_or_updated_at",
    "source_type",
    "credibility",
    "core_claim",
    "project_applicability",
    "reflection",
}
PAPER_SOURCE_TYPES = {"paper", "academic_paper", "working_paper", "ssrn", "arxiv"}
Q2_ITERATION_ID = "mom_stock_intraday_codesign_q1"
VALIDATION_STAGES = {"pre-backtest", "q2-preflight", "final", "q2-final"}
ARTIFACT_REQUIRED_STAGES = {"final", "q2-final"}
FINAL_STATUS_FIELDS = (
    "workflow_pass",
    "research_pass",
    "llm_contribution_pass",
    "paper_ready_pass",
)
LEGACY_FINAL_DECISIONS = {"continue", "pivot", "stop"}
MULTIMODAL_FINAL_CONFIGS = {
    "mom_multiasset_forward_multimodal_r4": {
        "receipt_contract": "multiasset_forward_multimodal_r4_v3",
        "report_type": "multiasset_forward_multimodal_r4_matched_transfer_evaluation",
        "preregistration_status": "behavior_contracts_locked_before_first_r4_price_calculation",
        "runner_status": "implementation_locked_before_first_r4_price_calculation",
        "fallback_identity_field": "R4F01_equals_R4M01",
        "decision_markers": {
            "continue_to_locked_forward_observation": "continue",
            "stop_r4": "stop",
        },
        "stop_decision": "stop_r4",
    },
    "mom_multiasset_forward_multimodal_r5": {
        "receipt_contract": "multiasset_forward_multimodal_r5_v3",
        "report_type": "multiasset_forward_multimodal_r5_matched_transfer_evaluation",
        "preregistration_status": "behavior_contracts_locked_before_first_r5_price_calculation",
        "runner_status": "implementation_locked_before_first_r5_price_calculation",
        "fallback_identity_field": "R5F01_equals_R5M01",
        "decision_markers": {
            "continue_to_locked_forward_observation": "continue",
            "stop_r5": "stop",
        },
        "stop_decision": "stop_r5",
        "evaluation_anchor_contract": ("multiasset_forward_multimodal_r5_evaluation_anchor_v1"),
        "external_custody_required": True,
        "harness_reconciliation_contract": (
            "multiasset_forward_multimodal_r5_harness_reconciliation_v1"
        ),
        "harness_candidate_ids": [
            "R5D01",
            "R5D02",
            "R5M01",
            "R5M02",
            "R5L01",
            "R5C01",
            "R5F01",
            "R5P01",
        ],
    },
}
MULTIMODAL_FINAL_CHILD_FILENAMES = {
    "feature_ledger": "feature-ledger.jsonl",
    "prediction_ledger": "prediction-ledger.jsonl",
    "daily_return_ledger": "daily-return-ledger.jsonl",
    "target_ledger": "target-ledger.jsonl",
    "event_ledger": "cost-event-ledger.jsonl",
    "benchmark_ledger": "benchmark-ledger.jsonl",
    "model_ledger": "model-ledger.jsonl",
    "trial_ledger": "trial-ledger.jsonl",
    "cost_reconciliation": "cost-reconciliation.json",
    "model_provenance": "model-provenance.json",
    "evaluation": "evaluation-report.json",
    "evaluation_markdown": "evaluation-report.md",
    "decision_record": "decision-record.md",
}
MULTIMODAL_FINAL_LOCK_FILENAMES = {
    "preregistration_lock": "preregistration-lock.json",
    "runner_lock": "runner-lock.json",
    "lock_anchor": "lock-anchor.json",
}


@dataclass(frozen=True)
class IterationDossierPaths:
    root: Path
    external_brief_json: Path
    external_brief_md: Path
    hypotheses_md: Path
    search_space_json: Path
    search_space_md: Path
    decision_record_md: Path


@dataclass(frozen=True)
class IterationDossierValidation:
    iter_id: str
    root: Path
    status: str
    blocked: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self, base: Path | None = None) -> dict[str, Any]:
        root = base or project_root()
        return {
            "iter_id": self.iter_id,
            "root": _relpath(self.root, root),
            "status": self.status,
            "blocked": list(self.blocked),
            "warnings": list(self.warnings),
            "checked_at": self.checked_at.isoformat(),
        }


def iteration_dossier_paths(iter_id: str, root: Path | None = None) -> IterationDossierPaths:
    _validate_iter_id(iter_id)
    base = root or project_root()
    dossier_root = base / ITERATION_ROOT / iter_id
    return IterationDossierPaths(
        root=dossier_root,
        external_brief_json=dossier_root / "external-brief.json",
        external_brief_md=dossier_root / "external-brief.md",
        hypotheses_md=dossier_root / "hypotheses.md",
        search_space_json=dossier_root / "search-space.json",
        search_space_md=dossier_root / "search-space.md",
        decision_record_md=dossier_root / "decision-record.md",
    )


def init_iteration_dossier(
    iter_id: str,
    root: Path | None = None,
    *,
    overwrite: bool = False,
) -> IterationDossierPaths:
    paths = iteration_dossier_paths(iter_id, root)
    ensure_dir(paths.root)
    _write_text_if_needed(paths.external_brief_md, _external_brief_md_template(iter_id), overwrite)
    _write_json_if_needed(
        paths.external_brief_json, _external_brief_json_template(iter_id), overwrite
    )
    _write_text_if_needed(paths.hypotheses_md, _hypotheses_template(iter_id), overwrite)
    _write_json_if_needed(paths.search_space_json, _search_space_json_template(iter_id), overwrite)
    _write_text_if_needed(paths.search_space_md, _search_space_md_template(iter_id), overwrite)
    _write_text_if_needed(paths.decision_record_md, _decision_record_template(iter_id), overwrite)
    return paths


def validate_iteration_dossier(
    iter_id: str,
    root: Path | None = None,
    *,
    stage: str = "pre-backtest",
    staged_evaluation_dir: Path | None = None,
) -> IterationDossierValidation:
    base = root or project_root()
    if stage not in VALIDATION_STAGES:
        raise ValueError(f"stage must be one of {', '.join(sorted(VALIDATION_STAGES))}")
    if staged_evaluation_dir is not None and stage not in ARTIFACT_REQUIRED_STAGES:
        raise ValueError("staged_evaluation_dir is only valid for final-stage validation")
    paths = iteration_dossier_paths(iter_id, base)
    blocked: list[str] = []
    warnings: list[str] = []
    if not paths.root.exists():
        return IterationDossierValidation(
            iter_id=iter_id,
            root=paths.root,
            status="blocked",
            blocked=["iteration_dossier_missing"],
        )
    for key, path in {
        "external_brief_md": paths.external_brief_md,
        "external_brief_json": paths.external_brief_json,
        "hypotheses_md": paths.hypotheses_md,
        "search_space_json": paths.search_space_json,
        "search_space_md": paths.search_space_md,
        "decision_record_md": paths.decision_record_md,
    }.items():
        if not path.exists():
            blocked.append(f"missing_{key}")
    external = _load_json(paths.external_brief_json, blocked, "external_brief")
    search_space = _load_json(paths.search_space_json, blocked, "search_space")
    if isinstance(external, dict):
        blocked.extend(_identity_blockers(external, iter_id, base))
        blocked.extend(_external_brief_blockers(external))
    if isinstance(search_space, dict):
        blocked.extend(_identity_blockers(search_space, iter_id, base))
        blocked.extend(
            _search_space_blockers(
                search_space,
                base,
                require_artifacts=stage in ARTIFACT_REQUIRED_STAGES,
                staged_evaluation_dir=staged_evaluation_dir,
            )
        )
    blocked.extend(
        _markdown_contract_blockers(
            paths,
            root=base,
            stage=stage,
            staged_evaluation_dir=staged_evaluation_dir,
        )
    )
    if iter_id == Q2_ITERATION_ID and stage in ARTIFACT_REQUIRED_STAGES:
        blocked.extend(_q2_output_artifact_blockers(base))
    status = "blocked" if blocked else "warning" if warnings else "ok"
    return IterationDossierValidation(
        iter_id=iter_id,
        root=paths.root,
        status=status,
        blocked=blocked,
        warnings=warnings,
    )


def require_iteration_execution_gate(
    spec_source: StrategySpec | str | Path,
    root: Path | None = None,
    *,
    enforce_unbound_design: bool = False,
    require_registered_iteration: bool = False,
) -> IterationDossierValidation | None:
    """Fail closed for execution that is or must be bound to an iteration."""
    from open_composer.research.design_contract import (
        research_design_mapping,
        research_design_requires_iteration_gate,
    )

    spec = (
        spec_source
        if isinstance(spec_source, StrategySpec)
        else load_strategy_spec(Path(spec_source))
    )
    design = research_design_mapping(spec)
    if not research_design_requires_iteration_gate(design):
        if require_registered_iteration:
            raise ValueError("research execution requires iter_id before execution")
        if enforce_unbound_design and _spec_requires_registered_iteration(spec):
            raise ValueError("strategy execution requires iter_id before execution")
        return None
    iter_id = str(design.get("iter_id") or "").strip()
    campaign_bound = bool(str(design.get("campaign_contract_path") or "").strip())
    if not iter_id:
        if _is_workflow_only_ungated_draft(spec, design):
            return None
        if campaign_bound or enforce_unbound_design or require_registered_iteration:
            raise ValueError("research_design requires iter_id before execution")
        return None
    result = validate_iteration_dossier(iter_id, root or project_root(), stage="pre-backtest")
    if not result.ok:
        raise ValueError(f"iteration dossier blocked for {iter_id}: {', '.join(result.blocked)}")
    return result


def _spec_requires_registered_iteration(spec: StrategySpec) -> bool:
    return bool(
        spec.lifecycle != "draft"
        or spec.execution.mode == "paper_auto"
        or spec.execution.broker != "none"
        or spec.model is not None
    )


def _is_workflow_only_ungated_draft(
    spec: StrategySpec,
    design: dict[str, Any],
) -> bool:
    """Allow only local sample smoke drafts to run before iteration registration."""
    from open_composer.research.design_contract import research_design_has_bindings

    return bool(
        design.get("workflow_only_ungated_draft") is True
        and spec.lifecycle == "draft"
        and spec.data.source == "sample"
        and spec.execution.mode == "manual_signal"
        and spec.execution.broker == "none"
        and spec.model is None
        and not research_design_has_bindings(design)
    )


def _q2_output_artifact_blockers(root: Path) -> list[str]:
    try:
        from open_composer.research.stock_momentum_codesign_q2 import (
            validate_q2_output_artifacts,
        )
    except ModuleNotFoundError as exc:
        if exc.name == "open_composer.research.stock_momentum_codesign_q2":
            return ["q2_output_validator_unavailable"]
        raise

    blockers = validate_q2_output_artifacts(root)
    if not isinstance(blockers, list) or not all(isinstance(item, str) for item in blockers):
        return ["q2_output_validator_invalid_result"]
    return blockers


def render_validation_markdown(result: IterationDossierValidation) -> str:
    lines = [
        f"# Iteration Dossier Validation: {result.iter_id}",
        "",
        f"- Status: `{result.status}`",
        f"- Root: `{result.root}`",
        f"- Checked at: `{result.checked_at.isoformat()}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in result.blocked) if result.blocked else lines.append(
        "- none"
    )
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- `{item}`" for item in result.warnings) if result.warnings else lines.append(
        "- none"
    )
    return "\n".join(lines).rstrip() + "\n"


def _validate_iter_id(iter_id: str) -> None:
    if not ITER_ID_RE.match(iter_id):
        raise ValueError("iter_id must match ^[a-z0-9][a-z0-9_-]{2,80}$ (example: mom_minute_r1)")


def _load_json(path: Path, blocked: list[str], label: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        blocked.append(f"{label}_invalid_json:{exc}")
        return None
    if not isinstance(payload, dict):
        blocked.append(f"{label}_not_object")
        return None
    return payload


def _external_brief_blockers(payload: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if int(payload.get("schema_version") or 1) >= 2:
        if not payload.get("current_source_card_paths"):
            blocked.append("external_brief_v2_missing_current_source_card_paths")
        if not payload.get("source_evidence_bindings"):
            blocked.append("external_brief_v2_missing_source_evidence_bindings")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        return ["external_brief_sources_missing"]
    if len(sources) < 8:
        blocked.append(f"external_brief_sources_lt_8:{len(sources)}")
    paper_count = 0
    for idx, source in enumerate(sources):
        if not isinstance(source, dict):
            blocked.append(f"external_brief_source_{idx}_not_object")
            continue
        missing = sorted(field for field in REQUIRED_SOURCE_FIELDS if not source.get(field))
        if missing:
            blocked.append(f"external_brief_source_{idx}_missing:{','.join(missing)}")
        if str(source.get("source_type") or "").strip().lower() in PAPER_SOURCE_TYPES:
            paper_count += 1
    if paper_count < 3:
        blocked.append(f"external_brief_paper_sources_lt_3:{paper_count}")
    topic_coverage = payload.get("topic_coverage")
    if not isinstance(topic_coverage, list) or len([item for item in topic_coverage if item]) < 6:
        blocked.append("external_brief_topic_coverage_incomplete")
    conclusions = payload.get("candidate_matrix_revisions")
    if not isinstance(conclusions, list) or not conclusions:
        blocked.append("external_brief_missing_candidate_matrix_revisions")
    return blocked


def _identity_blockers(payload: dict[str, Any], iter_id: str, root: Path) -> list[str]:
    blocked: list[str] = []
    if payload.get("iter_id") != iter_id:
        blocked.append("iteration_payload_iter_id_mismatch")
    if not str(payload.get("strategy_name") or "").strip():
        blocked.append("iteration_payload_missing_strategy_name")
    if "source_spec_path" not in payload:
        blocked.append("iteration_payload_missing_source_spec_path")
    if "spec_hash" not in payload:
        blocked.append("iteration_payload_missing_spec_hash")
    spec_path_raw = payload.get("source_spec_path")
    spec_hash = payload.get("spec_hash")
    if spec_path_raw:
        spec_path, error = _safe_repo_path(root, str(spec_path_raw))
        if error:
            blocked.append(f"iteration_payload_invalid_source_spec_path:{error}")
        elif not spec_path.exists():
            blocked.append("iteration_payload_source_spec_missing")
        else:
            try:
                spec = load_strategy_spec(spec_path)
                if spec_hash != strategy_content_hash(spec):
                    blocked.append("iteration_payload_stale_spec_hash")
            except Exception as exc:
                blocked.append(f"iteration_payload_source_spec_invalid:{exc}")
    elif spec_hash not in (None, ""):
        blocked.append("iteration_payload_spec_hash_without_source_spec_path")
    return blocked


def _search_space_blockers(
    payload: dict[str, Any],
    root: Path,
    *,
    require_artifacts: bool,
    staged_evaluation_dir: Path | None = None,
) -> list[str]:
    blocked: list[str] = []
    paths = payload.get("paths")
    if not isinstance(paths, list) or not paths:
        return ["search_space_paths_missing"]
    total = 0
    for idx, path in enumerate(paths):
        if not isinstance(path, dict):
            blocked.append(f"search_space_path_{idx}_not_object")
            continue
        name = str(path.get("name") or f"path_{idx}")
        combos = _int_or_none(path.get("candidate_count"))
        if combos is None or combos < 1:
            blocked.append(f"search_space_{name}_invalid_candidate_count")
            continue
        if combos > 24:
            blocked.append(f"search_space_{name}_candidate_count_gt_24:{combos}")
        total += combos
        for field_name in ["hypothesis_refs", "parameters", "benchmark_family"]:
            if path.get(field_name) in (None, "", [], {}):
                blocked.append(f"search_space_{name}_missing_{field_name}")
    budget = _int_or_none(payload.get("total_candidate_budget")) or total
    if budget != total:
        blocked.append(f"search_space_budget_total_mismatch:{budget}:{total}")
    if budget > 80:
        blocked.append(f"search_space_budget_gt_80:{budget}")
    if total > 80:
        blocked.append(f"search_space_total_candidates_gt_80:{total}")
    for field_name in ["trial_ledger_paths", "evaluation_report_paths"]:
        value = payload.get(field_name)
        if not isinstance(value, list):
            blocked.append(f"search_space_missing_{field_name}")
            continue
        for idx, item in enumerate(value):
            artifact_path, error = _safe_repo_path(root, str(item))
            if error:
                blocked.append(f"search_space_{field_name}_{idx}_invalid:{error}")
            elif require_artifacts and not _final_artifact_exists(
                artifact_path,
                staged_evaluation_dir=staged_evaluation_dir,
            ):
                blocked.append(f"search_space_{field_name}_{idx}_missing")
        if require_artifacts and not value:
            blocked.append(f"search_space_{field_name}_empty_final")
    knowledge_contract = payload.get("knowledge_contract")
    if knowledge_contract is not None:
        blocked.extend(_knowledge_contract_blockers(knowledge_contract, root))
    blocked.extend(
        _campaign_contract_blockers(
            payload,
            root,
            stage="pre-discovery",
        )
    )
    candidate_manifest_raw = str(payload.get("candidate_manifest_path") or "").strip()
    campaign_bound = bool(str(payload.get("campaign_contract_path") or "").strip())
    if campaign_bound and not candidate_manifest_raw:
        blocked.append("campaign_contract_child_candidate_manifest_missing")
    if candidate_manifest_raw:
        feasibility_payload: dict[str, Any] | None = None
        feasibility_path: Path | None = None
        for field_name in ["cost_table_path", "data_feasibility_path"]:
            raw_path = str(payload.get(field_name) or "").strip()
            if not raw_path:
                blocked.append(f"search_space_missing_{field_name}")
                continue
            prerequisite_path, prerequisite_error = _safe_repo_path(root, raw_path)
            if prerequisite_error:
                blocked.append(f"search_space_{field_name}_invalid:{prerequisite_error}")
                continue
            if not prerequisite_path.exists():
                blocked.append(f"search_space_{field_name}_missing")
                continue
            if field_name == "data_feasibility_path" and prerequisite_path.suffix == ".json":
                try:
                    feasibility = json.loads(prerequisite_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    blocked.append("search_space_data_feasibility_invalid_json")
                else:
                    if not isinstance(feasibility, dict):
                        blocked.append("search_space_data_feasibility_not_object")
                    else:
                        feasibility_payload = feasibility
                        feasibility_path = prerequisite_path
        candidate_manifest_path, error = _safe_repo_path(root, candidate_manifest_raw)
        if error:
            blocked.append(f"candidate_manifest_invalid_path:{error}")
        elif not candidate_manifest_path.exists():
            blocked.append("candidate_manifest_missing")
        else:
            blocked.extend(
                _candidate_manifest_blockers(
                    candidate_manifest_path,
                    payload,
                    root,
                    expected_total=total,
                )
            )
            blocked.extend(
                _data_feasibility_blockers(
                    feasibility_payload,
                    feasibility_path,
                    candidate_manifest_path,
                    payload,
                    root,
                )
            )
    return blocked


def _campaign_contract_blockers(
    payload: dict[str, Any],
    root: Path,
    *,
    stage: str,
) -> list[str]:
    raw_path = str(payload.get("campaign_contract_path") or "").strip()
    declared_id = str(payload.get("campaign_id") or "").strip()
    declared_sha256 = str(payload.get("campaign_contract_sha256") or "").strip()
    iter_id = str(payload.get("iter_id") or "").strip()
    registered_campaign_ids = _registered_campaign_ids_for_child(root, iter_id)
    requirement_blockers = _campaign_requirement_blockers(
        payload,
        registered_campaign_ids=registered_campaign_ids,
        campaign_bound=bool(raw_path),
    )
    if not raw_path:
        blocked = list(requirement_blockers)
        if declared_id:
            blocked.append("campaign_id_without_contract_path")
        if declared_sha256:
            blocked.append("campaign_contract_sha256_without_path")
        return blocked

    blocked = list(requirement_blockers)
    if not declared_id:
        blocked.append("campaign_id_missing")
    if not declared_sha256:
        blocked.append("campaign_contract_sha256_missing")
    contract_path, error = _safe_repo_path(root, raw_path)
    if error:
        return [*blocked, f"campaign_contract_invalid_path:{error}"]
    if not contract_path.is_file():
        return [*blocked, "campaign_contract_missing"]
    actual_sha256 = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    if declared_sha256 and declared_sha256 != actual_sha256:
        blocked.append("campaign_contract_sha256_mismatch")

    from open_composer.research.campaign import (
        load_campaign_contract,
        validate_campaign_contract,
    )

    validation = validate_campaign_contract(contract_path, root, stage=stage)
    blocked.extend(f"campaign_contract_{item}" for item in validation.blocked)
    try:
        contract = load_campaign_contract(contract_path, root)
    except (OSError, ValueError):
        return blocked
    canonical_contract_path = (
        root
        / "reports/research/campaigns"
        / contract.campaign_id
        / "research-campaign-contract.json"
    ).resolve()
    if contract_path.resolve() != canonical_contract_path:
        blocked.append("campaign_contract_noncanonical_path")
    if registered_campaign_ids and contract.campaign_id not in registered_campaign_ids:
        blocked.append(
            "campaign_contract_registered_child_identity_mismatch:"
            + ",".join(registered_campaign_ids)
            + f":{contract.campaign_id}"
        )
    if declared_id and contract.campaign_id != declared_id:
        blocked.append("campaign_contract_id_mismatch")
    iteration_id = iter_id
    if iteration_id not in contract.child_iteration_ids:
        blocked.append(f"campaign_contract_child_iteration_missing:{iteration_id}")
    assigned_candidates = [
        item for item in contract.candidate_blueprints if item.child_iteration_id == iteration_id
    ]
    iteration_budget = _int_or_none(payload.get("total_candidate_budget"))
    if iteration_budget != len(assigned_candidates):
        blocked.append(
            "campaign_contract_child_candidate_budget_mismatch:"
            f"{iteration_id}:{iteration_budget}:{len(assigned_candidates)}"
        )
    candidate_manifest_raw = str(payload.get("candidate_manifest_path") or "").strip()
    if not candidate_manifest_raw:
        blocked.append("campaign_contract_child_candidate_manifest_missing")
    else:
        candidate_manifest_path, manifest_error = _safe_repo_path(root, candidate_manifest_raw)
        if manifest_error is None and candidate_manifest_path.is_file():
            try:
                manifest = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
            else:
                rows = manifest.get("candidates") if isinstance(manifest, dict) else None
                if isinstance(rows, list):
                    actual_ids = [
                        str(row.get("candidate_id") or "") for row in rows if isinstance(row, dict)
                    ]
                    expected_ids = [item.candidate_id for item in assigned_candidates]
                    if actual_ids != expected_ids:
                        blocked.append(
                            f"campaign_contract_child_candidate_inventory_mismatch:{iteration_id}"
                        )
                    expected_by_id = {item.candidate_id: item for item in assigned_candidates}
                    hypotheses_by_id = {item.hypothesis_id: item for item in contract.hypotheses}
                    for index, row in enumerate(rows):
                        if not isinstance(row, dict):
                            continue
                        candidate_id = str(row.get("candidate_id") or "")
                        expected = expected_by_id.get(candidate_id)
                        if expected is None:
                            continue
                        expected_bindings = {
                            "campaign_id": contract.campaign_id,
                            "hypothesis_id": expected.hypothesis_id,
                            "branch_id": expected.branch_id,
                            "child_iteration_id": expected.child_iteration_id,
                            "promotion_eligible": expected.promotion_eligible,
                            "quality_metric": contract.qd_archive.quality_metric,
                        }
                        for field_name, expected_value in expected_bindings.items():
                            if row.get(field_name) != expected_value:
                                blocked.append(
                                    "campaign_contract_candidate_binding_mismatch:"
                                    f"{candidate_id or index}:{field_name}"
                                )
                        for field_name in (
                            "universe_contract_sha256",
                            "development_partition_contract_sha256",
                        ):
                            value = str(row.get(field_name) or "")
                            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                                blocked.append(
                                    "campaign_contract_candidate_evidence_identity_invalid:"
                                    f"{candidate_id or index}:{field_name}"
                                )
                        blocked.extend(
                            _campaign_candidate_file_binding_blockers(
                                row,
                                candidate_id=candidate_id or str(index),
                                root=root,
                                expected_development_partition_id=(
                                    contract.qd_archive.quality_partition_id
                                ),
                                expected_campaign_id=contract.campaign_id,
                                expected_candidate=expected,
                                expected_hypothesis=hypotheses_by_id[expected.hypothesis_id],
                                expected_data_feasibility_path=str(
                                    payload.get("data_feasibility_path") or ""
                                ),
                            )
                        )
    return blocked


def _campaign_requirement_blockers(
    payload: dict[str, Any],
    *,
    registered_campaign_ids: list[str],
    campaign_bound: bool,
) -> list[str]:
    blocked: list[str] = []
    schema_version = _int_or_none(payload.get("schema_version")) or 1
    iter_id = str(payload.get("iter_id") or "").strip()
    legacy_unbound = iter_id in LEGACY_UNBOUND_ITERATION_IDS
    created_at: datetime | None = None
    created_at_raw = payload.get("created_at")
    if not legacy_unbound and schema_version < 3:
        blocked.append("campaign_governance_schema_version_invalid_for_new_iteration")
    if schema_version >= 3:
        if not isinstance(created_at_raw, str) or not created_at_raw.strip():
            blocked.append("campaign_governance_created_at_missing")
        else:
            try:
                created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
            except ValueError:
                blocked.append("campaign_governance_created_at_invalid")
            else:
                if created_at.tzinfo is None:
                    blocked.append("campaign_governance_created_at_timezone_missing")
                else:
                    created_at = created_at.astimezone(UTC)
    if len(registered_campaign_ids) > 1:
        blocked.append(
            "campaign_contract_child_registered_multiple:" + ",".join(registered_campaign_ids)
        )
    if registered_campaign_ids and not campaign_bound:
        blocked.append(
            "campaign_contract_binding_missing_for_registered_child:" + registered_campaign_ids[0]
        )
    if not legacy_unbound and not campaign_bound:
        blocked.append("campaign_contract_required_for_new_iteration")
    return blocked


def _registered_campaign_ids_for_child(root: Path, iter_id: str) -> list[str]:
    if not iter_id:
        return []
    campaign_root = root / "reports/research/campaigns"
    if not campaign_root.is_dir() or campaign_root.is_symlink():
        return []
    result: list[str] = []
    for path in sorted(campaign_root.glob("*/research-campaign-contract.json")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        children = payload.get("child_iteration_ids") if isinstance(payload, dict) else None
        campaign_id = payload.get("campaign_id") if isinstance(payload, dict) else None
        if (
            isinstance(children, list)
            and iter_id in children
            and isinstance(campaign_id, str)
            and campaign_id
        ):
            result.append(campaign_id)
    return sorted(set(result))


def _campaign_candidate_file_binding_blockers(
    row: dict[str, Any],
    *,
    candidate_id: str,
    root: Path,
    expected_development_partition_id: str,
    expected_campaign_id: str,
    expected_candidate: Any,
    expected_hypothesis: Any,
    expected_data_feasibility_path: str,
) -> list[str]:
    blocked: list[str] = []
    bindings = (
        ("universe_contract_path", "universe_contract_sha256"),
        (
            "development_partition_contract_path",
            "development_partition_contract_sha256",
        ),
    )
    for path_field, sha_field in bindings:
        raw_path = str(row.get(path_field) or "").strip()
        if not raw_path:
            blocked.append(
                f"campaign_contract_candidate_evidence_path_missing:{candidate_id}:{path_field}"
            )
            continue
        path, error = _safe_repo_path(root, raw_path)
        if error:
            blocked.append(
                f"campaign_contract_candidate_evidence_path_invalid:"
                f"{candidate_id}:{path_field}:{error}"
            )
            continue
        if not path.is_file() or path.is_symlink():
            blocked.append(
                f"campaign_contract_candidate_evidence_file_missing:{candidate_id}:{path_field}"
            )
            continue
        expected_sha256 = str(row.get(sha_field) or "")
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_sha256 != actual_sha256:
            blocked.append(
                f"campaign_contract_candidate_evidence_sha256_mismatch:{candidate_id}:{sha_field}"
            )
        if path_field == "universe_contract_path":
            blocked.extend(
                _campaign_universe_contract_blockers(
                    path,
                    candidate_id=candidate_id,
                    root=root,
                    expected_campaign_id=expected_campaign_id,
                    expected_candidate=expected_candidate,
                    expected_hypothesis=expected_hypothesis,
                    expected_data_feasibility_path=expected_data_feasibility_path,
                )
            )
            continue
        if path_field != "development_partition_contract_path":
            continue
        try:
            partition = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            blocked.append(
                f"campaign_contract_candidate_development_partition_invalid_json:{candidate_id}"
            )
            continue
        if not isinstance(partition, dict):
            blocked.append(
                f"campaign_contract_candidate_development_partition_not_object:{candidate_id}"
            )
            continue
        if partition.get("partition_id") != expected_development_partition_id:
            blocked.append(
                f"campaign_contract_candidate_development_partition_id_mismatch:{candidate_id}"
            )
        if partition.get("kind") != "development":
            blocked.append(
                f"campaign_contract_candidate_development_partition_kind_mismatch:{candidate_id}"
            )
    return blocked


def _campaign_universe_contract_blockers(
    path: Path,
    *,
    candidate_id: str,
    root: Path,
    expected_campaign_id: str,
    expected_candidate: Any,
    expected_hypothesis: Any,
    expected_data_feasibility_path: str,
) -> list[str]:
    prefix = f"campaign_contract_candidate_universe_contract:{candidate_id}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [f"{prefix}:invalid_json"]
    if not isinstance(payload, dict):
        return [f"{prefix}:not_object"]

    blocked: list[str] = []
    expected_fields = {
        "schema_version": 1,
        "campaign_id": expected_campaign_id,
        "child_iteration_id": expected_candidate.child_iteration_id,
        "hypothesis_id": expected_candidate.hypothesis_id,
        "universe_selection": expected_hypothesis.universe_selection,
        "promotion_eligible": expected_candidate.promotion_eligible,
    }
    for field_name, expected_value in expected_fields.items():
        if payload.get(field_name) != expected_value:
            blocked.append(f"{prefix}:{field_name}_mismatch")

    status = payload.get("contract_status")
    if status not in {"ready", "dependency_skipped"}:
        blocked.append(f"{prefix}:contract_status_invalid")
        return blocked

    capability_ids = payload.get("capability_ids")
    if (
        not isinstance(capability_ids, list)
        or not capability_ids
        or any(not isinstance(item, str) or not item.strip() for item in capability_ids)
        or len(capability_ids) != len(set(capability_ids))
    ):
        blocked.append(f"{prefix}:capability_ids_invalid")
        capability_ids = []
    elif status == "ready":
        blocked.extend(
            _campaign_ready_capability_blockers(
                capability_ids,
                root=root,
                prefix=prefix,
                require_point_in_time=(expected_hypothesis.universe_selection == "point_in_time"),
            )
        )

    feasibility = payload.get("data_feasibility_binding")
    if not isinstance(feasibility, dict):
        blocked.append(f"{prefix}:data_feasibility_binding_missing")
    elif not expected_data_feasibility_path:
        blocked.append(f"{prefix}:expected_data_feasibility_path_missing")
    else:
        if feasibility.get("path") != expected_data_feasibility_path:
            blocked.append(f"{prefix}:data_feasibility_path_mismatch")
        feasibility_path, error = _safe_repo_path(root, expected_data_feasibility_path)
        if error or not feasibility_path.is_file() or feasibility_path.is_symlink():
            blocked.append(f"{prefix}:data_feasibility_file_missing")
        else:
            actual_sha256 = hashlib.sha256(feasibility_path.read_bytes()).hexdigest()
            if feasibility.get("sha256") != actual_sha256:
                blocked.append(f"{prefix}:data_feasibility_sha256_mismatch")
            blocked.extend(
                _campaign_data_feasibility_semantic_blockers(
                    feasibility_path,
                    expected_iter_id=expected_candidate.child_iteration_id,
                    expected_capability_ids=capability_ids,
                    expected_status=status,
                    prefix=prefix,
                )
            )
    if status == "dependency_skipped":
        dependency_blockers = payload.get("blockers")
        if (
            not isinstance(dependency_blockers, list)
            or not dependency_blockers
            or any(not isinstance(item, str) or not item.strip() for item in dependency_blockers)
        ):
            blocked.append(f"{prefix}:dependency_blockers_invalid")
        return blocked

    definition = payload.get("universe_definition")
    if not isinstance(definition, dict):
        blocked.append(f"{prefix}:universe_definition_missing")
        return blocked
    expected_mode = {
        "point_in_time": "point_in_time_membership",
        "fixed_long_lived": "fixed_long_lived_symbols",
        "cross_asset": "fixed_cross_asset_symbols",
        "static_hotspot_control": "static_hotspot_control",
    }[expected_hypothesis.universe_selection]
    if definition.get("membership_mode") != expected_mode:
        blocked.append(f"{prefix}:membership_mode_mismatch")

    if expected_hypothesis.universe_selection == "point_in_time":
        required = (
            "membership_artifact_path",
            "membership_artifact_sha256",
            "permanent_security_id_field",
            "membership_valid_from_field",
            "membership_valid_to_field",
            "delisting_return_field",
            "corporate_action_policy",
            "liquidity_visible_at_field",
        )
        for field_name in required:
            if not definition.get(field_name):
                blocked.append(f"{prefix}:point_in_time_{field_name}_missing")
        membership_raw = str(definition.get("membership_artifact_path") or "")
        membership_path, error = _safe_repo_path(root, membership_raw)
        if error or not membership_path.is_file() or membership_path.is_symlink():
            blocked.append(f"{prefix}:point_in_time_membership_artifact_missing")
        elif (
            definition.get("membership_artifact_sha256")
            != hashlib.sha256(membership_path.read_bytes()).hexdigest()
        ):
            blocked.append(f"{prefix}:point_in_time_membership_sha256_mismatch")
        else:
            blocked.extend(
                _campaign_pit_membership_blockers(
                    membership_path,
                    definition=definition,
                    prefix=prefix,
                )
            )
    else:
        symbols = definition.get("symbols")
        minimum_symbols = (
            1 if expected_hypothesis.universe_selection == "static_hotspot_control" else 2
        )
        if (
            not isinstance(symbols, list)
            or len(symbols) < minimum_symbols
            or any(not isinstance(item, str) or not item.strip() for item in symbols)
            or len(symbols) != len(set(symbols))
        ):
            blocked.append(f"{prefix}:symbols_invalid")
        if not str(definition.get("selection_rule") or "").strip():
            blocked.append(f"{prefix}:selection_rule_missing")
        frozen_at = definition.get("selection_frozen_at")
        if not isinstance(frozen_at, str):
            blocked.append(f"{prefix}:selection_frozen_at_missing")
        else:
            try:
                parsed = datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))
            except ValueError:
                blocked.append(f"{prefix}:selection_frozen_at_invalid")
            else:
                if parsed.tzinfo is None:
                    blocked.append(f"{prefix}:selection_frozen_at_timezone_missing")
    return blocked


def _campaign_ready_capability_blockers(
    capability_ids: list[str],
    *,
    root: Path,
    prefix: str,
    require_point_in_time: bool,
) -> list[str]:
    from open_composer.capabilities.registry import load_registry

    try:
        registry = load_registry(root)
    except (OSError, ValueError):
        return [f"{prefix}:capability_registry_invalid"]
    by_id = {item.id: item for item in registry.capabilities}
    blocked: list[str] = []
    unknown = sorted(set(capability_ids) - set(by_id))
    if unknown:
        blocked.append(f"{prefix}:capability_ids_unregistered:{','.join(unknown)}")
    ineligible = sorted(
        capability_id
        for capability_id in capability_ids
        if capability_id in by_id and by_id[capability_id].status not in {"approved", "trial"}
    )
    if ineligible:
        blocked.append(f"{prefix}:capability_ids_not_research_ready:{','.join(ineligible)}")
    if require_point_in_time and not any(
        capability_id in by_id and "point_in_time_universe" in by_id[capability_id].use_for
        for capability_id in capability_ids
    ):
        blocked.append(f"{prefix}:point_in_time_capability_missing")
    return blocked


def _campaign_data_feasibility_semantic_blockers(
    path: Path,
    *,
    expected_iter_id: str,
    expected_capability_ids: list[str],
    expected_status: str,
    prefix: str,
) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [f"{prefix}:data_feasibility_invalid_json"]
    if not isinstance(payload, dict):
        return [f"{prefix}:data_feasibility_not_object"]
    blocked: list[str] = []
    if _int_or_none(payload.get("schema_version")) != 1:
        blocked.append(f"{prefix}:data_feasibility_schema_version_mismatch")
    if payload.get("iter_id") != expected_iter_id:
        blocked.append(f"{prefix}:data_feasibility_iter_id_mismatch")
    campaign_universe = payload.get("campaign_universe")
    if not isinstance(campaign_universe, dict):
        blocked.append(f"{prefix}:data_feasibility_campaign_universe_missing")
        return blocked
    if campaign_universe.get("status") != expected_status:
        blocked.append(f"{prefix}:data_feasibility_campaign_universe_status_mismatch")
    declared_capabilities = campaign_universe.get("capability_ids")
    if not isinstance(declared_capabilities, list) or sorted(declared_capabilities) != sorted(
        expected_capability_ids
    ):
        blocked.append(f"{prefix}:data_feasibility_campaign_capabilities_mismatch")
    return blocked


def _campaign_pit_membership_blockers(
    path: Path,
    *,
    definition: dict[str, Any],
    prefix: str,
) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [f"{prefix}:point_in_time_membership_invalid_json"]
    if not isinstance(payload, dict):
        return [f"{prefix}:point_in_time_membership_not_object"]
    blocked: list[str] = []
    if _int_or_none(payload.get("schema_version")) != 1:
        blocked.append(f"{prefix}:point_in_time_membership_schema_version_mismatch")
    if not str(payload.get("source") or "").strip():
        blocked.append(f"{prefix}:point_in_time_membership_source_missing")
    if not _is_aware_datetime(payload.get("fetched_at")):
        blocked.append(f"{prefix}:point_in_time_membership_fetched_at_invalid")
    if definition.get("corporate_action_policy") not in {
        "point_in_time_split_dividend_adjusted_with_delisting_returns",
        "raw_prices_with_explicit_corporate_action_events",
    }:
        blocked.append(f"{prefix}:point_in_time_corporate_action_policy_invalid")

    rows = payload.get("memberships")
    if not isinstance(rows, list) or not rows:
        blocked.append(f"{prefix}:point_in_time_membership_rows_missing")
        return blocked
    permanent_id = str(definition["permanent_security_id_field"])
    valid_from = str(definition["membership_valid_from_field"])
    valid_to = str(definition["membership_valid_to_field"])
    delisting_return = str(definition["delisting_return_field"])
    liquidity_visible_at = str(definition["liquidity_visible_at_field"])
    required_fields = {
        permanent_id,
        valid_from,
        valid_to,
        delisting_return,
        liquidity_visible_at,
    }
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            blocked.append(f"{prefix}:point_in_time_membership_row_not_object:{index}")
            continue
        missing = sorted(required_fields - set(row))
        if missing:
            blocked.append(
                f"{prefix}:point_in_time_membership_row_fields_missing:{index}:{','.join(missing)}"
            )
            continue
        security_id = str(row.get(permanent_id) or "").strip()
        start = _parse_date(row.get(valid_from))
        end_value = row.get(valid_to)
        end_missing = end_value is None or end_value == ""
        end = None if end_missing else _parse_date(end_value)
        if not security_id or start is None:
            blocked.append(f"{prefix}:point_in_time_membership_row_identity_invalid:{index}")
            continue
        if not end_missing and end is None:
            blocked.append(f"{prefix}:point_in_time_membership_row_valid_to_invalid:{index}")
        elif end is not None and end < start:
            blocked.append(f"{prefix}:point_in_time_membership_row_interval_invalid:{index}")
        if not _is_aware_datetime(row.get(liquidity_visible_at)):
            blocked.append(f"{prefix}:point_in_time_membership_row_visible_at_invalid:{index}")
        delisting_value = row.get(delisting_return)
        if delisting_value is not None:
            try:
                numeric_delisting = float(delisting_value)
            except (TypeError, ValueError):
                numeric_delisting = math.nan
            if not math.isfinite(numeric_delisting):
                blocked.append(
                    f"{prefix}:point_in_time_membership_row_delisting_return_invalid:{index}"
                )
        identity = (security_id, str(row.get(valid_from)))
        if identity in seen:
            blocked.append(f"{prefix}:point_in_time_membership_row_duplicate:{index}")
        seen.add(identity)
    return blocked


def _is_aware_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _final_artifact_exists(
    artifact_path: Path,
    *,
    staged_evaluation_dir: Path | None,
) -> bool:
    candidate = artifact_path
    if staged_evaluation_dir is not None:
        canonical_evaluation_dir = staged_evaluation_dir.parent / "evaluation-run"
        try:
            relative = artifact_path.relative_to(canonical_evaluation_dir.resolve())
        except ValueError:
            pass
        else:
            candidate = staged_evaluation_dir / relative
    return not candidate.is_symlink() and candidate.is_file()


def _canonical_payload_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _candidate_policy_contract_rows(
    contracts: dict[str, Any],
    root: Path,
    *,
    expected_iter_id: str,
) -> tuple[dict[str, dict[str, dict[str, Any]]], list[str]]:
    blocked: list[str] = []
    result: dict[str, dict[str, dict[str, Any]]] = {}
    group = contracts.get("candidate_policies")
    if not isinstance(group, dict) or not group:
        return result, ["candidate_manifest_candidate_policy_contracts_missing"]
    for contract_id, binding in group.items():
        label = str(contract_id)
        if not isinstance(binding, dict):
            blocked.append(f"candidate_manifest_candidate_policy_{label}_binding_not_object")
            continue
        path, error = _safe_repo_path(root, str(binding.get("path") or ""))
        if error:
            blocked.append(f"candidate_manifest_candidate_policy_{label}_path_invalid:{error}")
            continue
        if (root / str(binding.get("path") or "")).is_symlink() or not path.is_file():
            blocked.append(f"candidate_manifest_candidate_policy_{label}_path_missing")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            blocked.append(f"candidate_manifest_candidate_policy_{label}_invalid_json")
            continue
        if not isinstance(payload, dict):
            blocked.append(f"candidate_manifest_candidate_policy_{label}_not_object")
            continue
        if payload.get("contract_id") != contract_id:
            blocked.append(f"candidate_manifest_candidate_policy_{label}_contract_id_mismatch")
        if payload.get("iter_id") != expected_iter_id:
            blocked.append(f"candidate_manifest_candidate_policy_{label}_iter_id_mismatch")
        if payload.get("generated_before_backtest") is not True:
            blocked.append(f"candidate_manifest_candidate_policy_{label}_not_preregistered")
        rows = payload.get("policies")
        if not isinstance(rows, list):
            blocked.append(f"candidate_manifest_candidate_policy_{label}_rows_missing")
            continue
        if payload.get("policy_count") != len(rows):
            blocked.append(f"candidate_manifest_candidate_policy_{label}_count_mismatch")
        by_id: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                blocked.append(
                    f"candidate_manifest_candidate_policy_{label}_row_{index}_not_object"
                )
                continue
            candidate_id = str(row.get("candidate_id") or "")
            if not candidate_id:
                blocked.append(
                    f"candidate_manifest_candidate_policy_{label}_row_{index}_id_missing"
                )
                continue
            if candidate_id in by_id:
                blocked.append(
                    f"candidate_manifest_candidate_policy_{label}_duplicate:{candidate_id}"
                )
                continue
            policy = row.get("policy")
            if not isinstance(policy, dict) or not policy:
                blocked.append(
                    f"candidate_manifest_candidate_policy_{label}_{candidate_id}_policy_missing"
                )
                continue
            actual_policy_sha256 = _canonical_payload_sha256(policy)
            declared_policy_sha256 = str(row.get("policy_sha256") or "")
            if declared_policy_sha256 != actual_policy_sha256:
                blocked.append(
                    f"candidate_manifest_candidate_policy_{label}_{candidate_id}_sha256_mismatch"
                )
            by_id[candidate_id] = row
        result[label] = by_id
    return result, blocked


def _spec_candidate_policy_blockers(
    spec: Any,
    *,
    candidate_id: str,
    expected_policy_sha256: str,
) -> list[str]:
    blocked: list[str] = []
    notes = spec.notes.model_dump(mode="json")
    if notes.get("candidate_id") != candidate_id:
        blocked.append(f"candidate_manifest_{candidate_id}_spec_candidate_id_mismatch")
    policy = notes.get("candidate_policy")
    if not isinstance(policy, dict) or not policy:
        blocked.append(f"candidate_manifest_{candidate_id}_spec_candidate_policy_missing")
        return blocked
    actual_policy_sha256 = _canonical_payload_sha256(policy)
    if expected_policy_sha256 and actual_policy_sha256 != expected_policy_sha256:
        blocked.append(f"candidate_manifest_{candidate_id}_spec_candidate_policy_mismatch")
    declared_policy_sha256 = str(notes.get("candidate_policy_sha256") or "")
    if declared_policy_sha256 != actual_policy_sha256:
        blocked.append(f"candidate_manifest_{candidate_id}_spec_candidate_policy_sha256_mismatch")
    return blocked


def _phase_one_preregistration_lock_blockers(
    root: Path,
    *,
    manifest_path: Path,
    search_space: dict[str, Any],
    candidates: list[Any],
) -> list[str]:
    blocked: list[str] = []
    lock_path = manifest_path.with_name("phase-one-preregistration-lock.json")
    try:
        lock_reference = lock_path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return ["candidate_manifest_phase_one_lock_outside_repo"]
    unresolved_lock = root / lock_reference
    if unresolved_lock.is_symlink() or not lock_path.is_file():
        return ["candidate_manifest_phase_one_lock_missing"]
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["candidate_manifest_phase_one_lock_invalid_json"]
    if not isinstance(lock, dict):
        return ["candidate_manifest_phase_one_lock_not_object"]

    expected_iter_id = str(search_space.get("iter_id") or "")
    expected_campaign_id = str(search_space.get("campaign_id") or "")
    if lock.get("iter_id") != expected_iter_id:
        blocked.append("candidate_manifest_phase_one_lock_iter_id_mismatch")
    if expected_campaign_id and lock.get("campaign_id") != expected_campaign_id:
        blocked.append("candidate_manifest_phase_one_lock_campaign_id_mismatch")
    for field_name in (
        "generated_before_backtest",
        "generated_before_model_training",
    ):
        if lock.get(field_name) is not True:
            blocked.append(f"candidate_manifest_phase_one_lock_{field_name}_invalid")
    for field_name in ("frozen_oos_read_authorized", "broker_writes"):
        if lock.get(field_name) is not False:
            blocked.append(f"candidate_manifest_phase_one_lock_{field_name}_invalid")

    candidate_rows = [row for row in candidates if isinstance(row, dict)]
    expected_ids = [str(row.get("candidate_id") or "") for row in candidate_rows]
    if lock.get("candidate_ids") != expected_ids:
        blocked.append("candidate_manifest_phase_one_lock_candidate_inventory_mismatch")
    expected_policy_sha256 = {
        str(row.get("candidate_id") or ""): str(row.get("candidate_policy_sha256") or "")
        for row in candidate_rows
    }
    if lock.get("candidate_policy_sha256") != expected_policy_sha256:
        blocked.append("candidate_manifest_phase_one_lock_candidate_policy_sha256_mismatch")

    inventory = lock.get("immutable_inventory")
    if not isinstance(inventory, dict) or not inventory:
        return [*blocked, "candidate_manifest_phase_one_lock_inventory_missing"]
    for name, binding in inventory.items():
        if not isinstance(binding, dict):
            blocked.append(f"candidate_manifest_phase_one_lock_{name}_binding_not_object")
            continue
        raw_path = str(binding.get("path") or "")
        path, error = _safe_repo_path(root, raw_path)
        if error:
            blocked.append(f"candidate_manifest_phase_one_lock_{name}_path_invalid:{error}")
            continue
        if (root / raw_path).is_symlink() or not path.is_file():
            blocked.append(f"candidate_manifest_phase_one_lock_{name}_path_missing")
            continue
        expected_hash = str(binding.get("sha256") or "")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_hash != actual_hash:
            blocked.append(f"candidate_manifest_phase_one_lock_{name}_sha256_mismatch")

    search_contracts = search_space.get("contracts")
    expected_policy_path = (
        str(search_contracts.get("candidate_policy") or "")
        if isinstance(search_contracts, dict)
        else ""
    )
    mandatory_paths = {"candidate_policy_contract": expected_policy_path}
    campaign_path = str(search_space.get("campaign_contract_path") or "")
    if campaign_path:
        mandatory_paths["campaign_contract"] = campaign_path
    for row in candidate_rows:
        candidate_id = str(row.get("candidate_id") or "")
        mandatory_paths[f"spec_{candidate_id}"] = str(row.get("spec_path") or "")
    for name, expected_path in mandatory_paths.items():
        binding = inventory.get(name)
        if not isinstance(binding, dict):
            blocked.append(f"candidate_manifest_phase_one_lock_{name}_binding_missing")
        elif binding.get("path") != expected_path:
            blocked.append(f"candidate_manifest_phase_one_lock_{name}_path_mismatch")
    return blocked


def _candidate_manifest_blockers(
    manifest_path: Path,
    search_space: dict[str, Any],
    root: Path,
    *,
    expected_total: int,
) -> list[str]:
    blocked: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["candidate_manifest_invalid_json"]
    if not isinstance(manifest, dict):
        return ["candidate_manifest_not_object"]
    expected_manifest_sha256 = str(search_space.get("candidate_manifest_sha256") or "")
    actual_manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if not expected_manifest_sha256:
        blocked.append("candidate_manifest_sha256_missing")
    elif expected_manifest_sha256 != actual_manifest_sha256:
        blocked.append("candidate_manifest_sha256_mismatch")
    if manifest.get("iter_id") != search_space.get("iter_id"):
        blocked.append("candidate_manifest_iter_id_mismatch")
    if manifest.get("generated_before_backtest") is not True:
        blocked.append("candidate_manifest_not_preregistered")
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list):
        return [*blocked, "candidate_manifest_candidates_missing"]
    if int(manifest.get("candidate_count") or -1) != len(candidates):
        blocked.append("candidate_manifest_count_mismatch")
    if len(candidates) != expected_total:
        blocked.append(f"candidate_manifest_total_mismatch:{len(candidates)}:{expected_total}")
    contracts = manifest.get("contracts")
    if not isinstance(contracts, dict):
        return [*blocked, "candidate_manifest_contracts_missing"]
    search_contracts = search_space.get("contracts")
    search_policy_path = (
        str(search_contracts.get("candidate_policy") or "").strip()
        if isinstance(search_contracts, dict)
        else ""
    )
    policy_bound = bool(search_policy_path) or isinstance(contracts.get("candidate_policies"), dict)
    manifest_contract = str(search_space.get("candidate_manifest_contract") or "")
    if manifest_contract:
        if manifest.get("manifest_type") != manifest_contract:
            blocked.append("candidate_manifest_contract_type_mismatch")
        if manifest_contract == "generic_candidate_family_v1":
            blocked.extend(_generic_manifest_contract_blockers(contracts, root))
    spec_hashes = manifest.get("spec_hashes")
    if not isinstance(spec_hashes, dict) or not spec_hashes:
        blocked.append("candidate_manifest_spec_hashes_missing")
        spec_hashes = {}
    contract_map = {
        "data_contract": "data",
        "feature_contract": "features",
        "label_contract": "labels",
        "validation_contract": "validation",
        "cost_contract": "costs",
        "benchmark_contract": "benchmarks",
    }
    if policy_bound:
        contract_map["candidate_policy_contract"] = "candidate_policies"
    required_fields = {
        "candidate_id",
        "path",
        "role",
        "method",
        "ablation",
        "spec_path",
        "fallback",
        *contract_map,
    }
    if policy_bound:
        required_fields.add("candidate_policy_sha256")
    policy_rows_by_contract: dict[str, dict[str, dict[str, Any]]] = {}
    if policy_bound:
        policy_rows_by_contract, policy_blocked = _candidate_policy_contract_rows(
            contracts,
            root,
            expected_iter_id=str(search_space.get("iter_id") or ""),
        )
        blocked.extend(policy_blocked)
    candidate_ids: set[str] = set()
    path_counts: dict[str, int] = {}
    validated_spec_paths: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            blocked.append(f"candidate_manifest_row_{index}_not_object")
            continue
        missing = sorted(field for field in required_fields if not candidate.get(field))
        if missing:
            blocked.append(f"candidate_manifest_row_{index}_missing:{','.join(missing)}")
            continue
        candidate_id = str(candidate["candidate_id"])
        if candidate_id in candidate_ids:
            blocked.append(f"candidate_manifest_duplicate_id:{candidate_id}")
        candidate_ids.add(candidate_id)
        path_name = str(candidate["path"])
        path_counts[path_name] = path_counts.get(path_name, 0) + 1
        for field_name, contract_group in contract_map.items():
            group = contracts.get(contract_group)
            if not isinstance(group, dict) or candidate[field_name] not in group:
                blocked.append(
                    f"candidate_manifest_{candidate_id}_unknown_{field_name}:"
                    f"{candidate[field_name]}"
                )
        expected_policy_sha256 = ""
        if policy_bound:
            policy_contract_id = str(candidate.get("candidate_policy_contract") or "")
            policy_row = policy_rows_by_contract.get(policy_contract_id, {}).get(candidate_id)
            if policy_row is None:
                blocked.append(
                    f"candidate_manifest_{candidate_id}_candidate_policy_missing_from_contract"
                )
            else:
                expected_policy_sha256 = str(policy_row.get("policy_sha256") or "")
                if candidate.get("method") != policy_row.get("method_variant"):
                    blocked.append(
                        f"candidate_manifest_{candidate_id}_candidate_policy_method_mismatch"
                    )
                if candidate.get("ablation") != policy_row.get("factor_variant"):
                    blocked.append(
                        f"candidate_manifest_{candidate_id}_candidate_policy_factor_mismatch"
                    )
            declared_policy_sha256 = str(candidate.get("candidate_policy_sha256") or "")
            if re.fullmatch(r"[0-9a-f]{64}", declared_policy_sha256) is None:
                blocked.append(f"candidate_manifest_{candidate_id}_candidate_policy_sha256_invalid")
            elif expected_policy_sha256 and declared_policy_sha256 != expected_policy_sha256:
                blocked.append(
                    f"candidate_manifest_{candidate_id}_candidate_policy_sha256_mismatch"
                )
        spec_path, error = _safe_repo_path(root, str(candidate["spec_path"]))
        if error:
            blocked.append(f"candidate_manifest_{candidate_id}_invalid_spec_path:{error}")
        elif not spec_path.exists():
            blocked.append(f"candidate_manifest_{candidate_id}_spec_missing")
        else:
            spec_reference = str(candidate["spec_path"])
            expected_spec_hash = str(spec_hashes.get(spec_reference) or "")
            if not expected_spec_hash:
                blocked.append(f"candidate_manifest_{candidate_id}_spec_hash_missing")
            else:
                try:
                    spec = load_strategy_spec(spec_path)
                    actual_spec_hash = strategy_content_hash(spec)
                except Exception as exc:
                    blocked.append(f"candidate_manifest_{candidate_id}_spec_invalid:{exc}")
                else:
                    if expected_spec_hash != actual_spec_hash:
                        blocked.append(f"candidate_manifest_{candidate_id}_spec_hash_mismatch")
                    if spec_reference not in validated_spec_paths:
                        blocked.extend(
                            _spec_iteration_binding_blockers(
                                spec,
                                spec_reference,
                                search_space,
                            )
                        )
                        validated_spec_paths.add(spec_reference)
                    if policy_bound:
                        blocked.extend(
                            _spec_candidate_policy_blockers(
                                spec,
                                candidate_id=candidate_id,
                                expected_policy_sha256=expected_policy_sha256,
                            )
                        )
    expected_path_counts = {
        str(row.get("name")): int(row.get("candidate_count") or 0)
        for row in search_space.get("paths", [])
        if isinstance(row, dict)
    }
    if path_counts != expected_path_counts:
        blocked.append(
            "candidate_manifest_path_counts_mismatch:"
            f"{json.dumps(path_counts, sort_keys=True)}:"
            f"{json.dumps(expected_path_counts, sort_keys=True)}"
        )
    if policy_bound:
        blocked.extend(
            _phase_one_preregistration_lock_blockers(
                root,
                manifest_path=manifest_path,
                search_space=search_space,
                candidates=candidates,
            )
        )
    return blocked


def _spec_iteration_binding_blockers(
    spec: Any,
    spec_reference: str,
    search_space: dict[str, Any],
) -> list[str]:
    blocked: list[str] = []
    from open_composer.research.design_contract import research_design_mapping

    try:
        research_design = research_design_mapping(spec)
    except ValueError:
        return [f"candidate_manifest_spec_binding_conflict:{spec_reference}"]
    if not research_design:
        return [f"candidate_manifest_spec_binding_missing:{spec_reference}"]
    if research_design.get("iter_id") != search_space.get("iter_id"):
        blocked.append(f"candidate_manifest_spec_iter_id_mismatch:{spec_reference}")
    if research_design.get("candidate_manifest_path") != search_space.get(
        "candidate_manifest_path"
    ):
        blocked.append(f"candidate_manifest_spec_manifest_path_mismatch:{spec_reference}")
    if research_design.get("campaign_contract_path") != search_space.get("campaign_contract_path"):
        blocked.append(f"candidate_manifest_spec_campaign_path_mismatch:{spec_reference}")
    feasibility_binding = research_design.get("data_feasibility_path") or research_design.get(
        "universe_contract_path"
    )
    if feasibility_binding != search_space.get("data_feasibility_path"):
        blocked.append(f"candidate_manifest_spec_feasibility_path_mismatch:{spec_reference}")
    contracts = search_space.get("contracts")
    expected_policy_path = (
        str(contracts.get("candidate_policy") or "") if isinstance(contracts, dict) else ""
    )
    if expected_policy_path:
        if research_design.get("candidate_policy_contract_path") != expected_policy_path:
            blocked.append(
                f"candidate_manifest_spec_candidate_policy_path_mismatch:{spec_reference}"
            )
        manifest_reference = str(search_space.get("candidate_manifest_path") or "")
        expected_lock_path = (
            Path(manifest_reference).with_name("phase-one-preregistration-lock.json").as_posix()
            if manifest_reference
            else ""
        )
        if research_design.get("preregistration_lock_path") != expected_lock_path:
            blocked.append(f"candidate_manifest_spec_phase_one_lock_path_mismatch:{spec_reference}")
    return blocked


def _generic_manifest_contract_blockers(
    contracts: dict[str, Any],
    root: Path,
) -> list[str]:
    blocked: list[str] = []
    checked_validation_paths: set[Path] = set()
    group_names = ["data", "features", "labels", "validation", "costs", "benchmarks"]
    if "candidate_policies" in contracts:
        group_names.append("candidate_policies")
    for group_name in group_names:
        group = contracts.get(group_name)
        if not isinstance(group, dict) or not group:
            blocked.append(f"candidate_manifest_generic_{group_name}_contracts_missing")
            continue
        for contract_id, binding in group.items():
            if not isinstance(binding, dict):
                blocked.append(
                    f"candidate_manifest_generic_{group_name}_{contract_id}_binding_not_object"
                )
                continue
            path, error = _safe_repo_path(root, str(binding.get("path") or ""))
            if error:
                blocked.append(
                    f"candidate_manifest_generic_{group_name}_{contract_id}_path_invalid:{error}"
                )
                continue
            if not path.is_file():
                blocked.append(
                    f"candidate_manifest_generic_{group_name}_{contract_id}_path_missing"
                )
                continue
            expected_hash = str(binding.get("sha256") or "")
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if not expected_hash:
                blocked.append(
                    f"candidate_manifest_generic_{group_name}_{contract_id}_sha256_missing"
                )
            elif expected_hash != actual_hash:
                blocked.append(
                    f"candidate_manifest_generic_{group_name}_{contract_id}_sha256_mismatch"
                )
            elif group_name == "validation" and path not in checked_validation_paths:
                blocked.extend(_generic_validation_contract_blockers(path))
                checked_validation_paths.add(path)
    return blocked


def _generic_validation_contract_blockers(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["candidate_manifest_generic_validation_contract_invalid_json"]
    if not isinstance(payload, dict):
        return ["candidate_manifest_generic_validation_contract_not_object"]
    gates = payload.get("family_gates")
    if not isinstance(gates, dict) or "pbo_min_partitions" not in gates:
        return []

    blocked: list[str] = []
    minimum = gates.get("pbo_min_partitions")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
        return ["candidate_manifest_generic_validation_pbo_min_partitions_invalid"]
    pbo = payload.get("pbo")
    if not isinstance(pbo, dict):
        return ["candidate_manifest_generic_validation_pbo_contract_missing"]

    block_count = pbo.get("block_count")
    in_sample_count = pbo.get("in_sample_block_count")
    counts_valid = all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (block_count, in_sample_count)
    )
    if not counts_valid or block_count < 8 or block_count % 2 or in_sample_count * 2 != block_count:
        blocked.append("candidate_manifest_generic_validation_pbo_block_counts_invalid")
        expected_partitions = None
    else:
        expected_partitions = math.comb(block_count, in_sample_count)

    block_ids = pbo.get("block_ids")
    if (
        not isinstance(block_ids, list)
        or block_count is None
        or len(block_ids) != block_count
        or len(set(map(str, block_ids))) != len(block_ids)
        or any(not isinstance(block_id, str) or not block_id for block_id in block_ids)
        or block_ids != sorted(block_ids)
    ):
        blocked.append("candidate_manifest_generic_validation_pbo_block_ids_invalid")

    construction = pbo.get("block_construction")
    if (
        not isinstance(construction, dict)
        or construction.get("algorithm") != "split_ordered_common_sessions_into_contiguous_blocks"
        or construction.get("remainder_allocation")
        != "one_extra_session_to_earliest_block_ids_in_order"
        or construction.get("maximum_size_difference") != 1
        or construction.get("no_shuffle") is not True
    ):
        blocked.append("candidate_manifest_generic_validation_pbo_construction_invalid")

    if (
        pbo.get("partition_enumeration") != "all_directional_combinations"
        or pbo.get("evaluate_complementary_orientations") is not True
    ):
        blocked.append("candidate_manifest_generic_validation_pbo_partition_symmetry_invalid")
    if expected_partitions is not None and pbo.get("expected_partition_count") != (
        expected_partitions
    ):
        blocked.append("candidate_manifest_generic_validation_pbo_partition_count_invalid")
    valid_minimum = pbo.get("minimum_valid_partition_count")
    if (
        not isinstance(valid_minimum, int)
        or isinstance(valid_minimum, bool)
        or expected_partitions is None
        or valid_minimum != expected_partitions
        or valid_minimum < minimum
    ):
        blocked.append("candidate_manifest_generic_validation_pbo_valid_minimum_invalid")

    candidates = pbo.get("selection_candidate_ids")
    controls = pbo.get("diagnostic_control_ids")
    if (
        not isinstance(candidates, list)
        or len(candidates) < 2
        or len(set(map(str, candidates))) != len(candidates)
        or any(not isinstance(candidate, str) or not candidate for candidate in candidates)
    ):
        blocked.append("candidate_manifest_generic_validation_pbo_candidates_invalid")
    if (
        not isinstance(controls, list)
        or any(not isinstance(control, str) or not control for control in controls)
        or set(map(str, candidates or [])) & set(map(str, controls or []))
    ):
        blocked.append("candidate_manifest_generic_validation_pbo_controls_invalid")

    requirements = pbo.get("valid_partition_requirements")
    required = {
        "all_candidate_Sharpe_values_are_defined",
        "all_selection_candidates_have_nonempty_finite_returns_on_both_sides",
        "exactly_four_in_sample_and_four_out_of_sample_blocks",
        "no_session_substitution_or_overlap",
    }
    requirement_set = set(map(str, requirements)) if isinstance(requirements, list) else set()
    legacy_tie_contract = {"deterministic_candidate_id_tie_break"}
    invariant_tie_contract = {
        "candidate_id_invariant_equal_weight_in_sample_ties",
        "candidate_id_invariant_average_oos_midranks",
        "identical_candidate_streams_contribute_exactly_0.5",
    }
    if not required.issubset(requirement_set) or not (
        legacy_tie_contract.issubset(requirement_set)
        or invariant_tie_contract.issubset(requirement_set)
    ):
        blocked.append("candidate_manifest_generic_validation_pbo_requirements_incomplete")
    return blocked


def _generic_data_feasibility_blockers(
    payload: dict[str, Any],
    feasibility_path: Path,
    manifest_path: Path,
    search_space: dict[str, Any],
    root: Path,
) -> list[str]:
    blocked: list[str] = []
    if not isinstance(payload.get("schema_version"), int):
        blocked.append("data_feasibility_schema_version_invalid")
    if not str(payload.get("report_type") or "").strip():
        blocked.append("data_feasibility_report_type_missing")
    if payload.get("iter_id") != search_space.get("iter_id"):
        blocked.append("data_feasibility_iter_id_mismatch")
    boolean_fields = [
        "workflow_pass",
        "research_pass",
        "llm_contribution_pass",
        "paper_ready_pass",
        "historical_evaluation_authorized",
    ]
    for field_name in boolean_fields:
        if not isinstance(payload.get(field_name), bool):
            blocked.append(f"data_feasibility_{field_name}_not_boolean")
    if payload.get("workflow_pass") is not True:
        blocked.append("data_feasibility_workflow_not_passed")
    if payload.get("historical_evaluation_authorized") is not True:
        blocked.append("search_space_data_feasibility_not_authorized")
    for field_name in ["research_pass", "llm_contribution_pass", "paper_ready_pass"]:
        if payload.get(field_name) is not False:
            blocked.append(f"data_feasibility_pre_evaluation_{field_name}_must_be_false")

    expected_sha = str(search_space.get("data_feasibility_sha256") or "")
    actual_sha = hashlib.sha256(feasibility_path.read_bytes()).hexdigest()
    if not expected_sha:
        blocked.append("data_feasibility_sha256_missing")
    elif expected_sha != actual_sha:
        blocked.append("data_feasibility_sha256_mismatch")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [*blocked, "data_feasibility_candidate_manifest_invalid_json"]
    candidates = manifest.get("candidates") if isinstance(manifest, dict) else None
    if not isinstance(candidates, list):
        return [*blocked, "data_feasibility_candidate_manifest_candidates_missing"]
    manifest_by_id = {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("candidate_id")
    }
    ids_by_path: dict[str, list[str]] = {}
    for candidate_id, candidate in manifest_by_id.items():
        ids_by_path.setdefault(str(candidate.get("path") or ""), []).append(candidate_id)

    path_gates = payload.get("path_gates")
    if not isinstance(path_gates, dict):
        return [*blocked, "data_feasibility_path_gates_missing"]
    if set(path_gates) != set(ids_by_path):
        blocked.append("data_feasibility_path_gate_set_mismatch")
    evaluated: list[str] = []
    skipped: list[str] = []
    actions_by_path: dict[str, str] = {}
    for path_name, candidate_ids in sorted(ids_by_path.items()):
        gate = path_gates.get(path_name)
        if not isinstance(gate, dict):
            blocked.append(f"data_feasibility_{path_name}_gate_missing")
            continue
        action = str(gate.get("action") or "")
        actions_by_path[path_name] = action
        if action == "evaluate":
            evaluated.extend(candidate_ids)
            if gate.get("historical_evaluation_go") is not True:
                blocked.append(f"data_feasibility_{path_name}_evaluate_without_go")
        elif action == "dependency_skipped":
            skipped.extend(candidate_ids)
            if gate.get("historical_evaluation_go") is not False:
                blocked.append(f"data_feasibility_{path_name}_skip_with_go")
        else:
            blocked.append(f"data_feasibility_{path_name}_invalid_action")
        declared_ids = gate.get("candidate_ids")
        if not isinstance(declared_ids, list) or sorted(map(str, declared_ids)) != sorted(
            candidate_ids
        ):
            blocked.append(f"data_feasibility_{path_name}_candidate_ids_mismatch")
    if payload.get("historical_evaluation_authorized") is True and not evaluated:
        blocked.append("data_feasibility_authorized_without_evaluated_candidates")

    accounting = payload.get("candidate_accounting")
    expected_accounting = {
        "frozen_candidate_count": len(candidates),
        "evaluation_authorized_count": len(evaluated),
        "dependency_skipped_count": len(skipped),
        "unresolved_count": 0,
        "balanced": len(evaluated) + len(skipped) == len(candidates),
    }
    if not isinstance(accounting, dict):
        blocked.append("data_feasibility_candidate_accounting_missing")
    else:
        for field_name, expected in expected_accounting.items():
            actual = accounting.get(field_name)
            matches = actual is expected if isinstance(expected, bool) else actual == expected
            if not matches or isinstance(actual, bool) != isinstance(expected, bool):
                blocked.append(
                    f"data_feasibility_accounting_{field_name}_mismatch:{actual}:{expected}"
                )

    authorization = payload.get("candidate_authorization")
    rows = authorization.get("rows") if isinstance(authorization, dict) else None
    if not isinstance(rows, list):
        blocked.append("data_feasibility_candidate_authorization_rows_missing")
    else:
        if authorization.get("candidate_count") != len(candidates):
            blocked.append("data_feasibility_candidate_authorization_count_mismatch")
        by_id: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                blocked.append(f"data_feasibility_candidate_authorization_row_{index}_not_object")
                continue
            candidate_id = str(row.get("candidate_id") or "")
            if not candidate_id:
                blocked.append(f"data_feasibility_candidate_authorization_row_{index}_id_missing")
            elif candidate_id in by_id:
                blocked.append(f"data_feasibility_candidate_authorization_duplicate:{candidate_id}")
            else:
                by_id[candidate_id] = row
        if set(by_id) != set(manifest_by_id):
            blocked.append("data_feasibility_candidate_authorization_id_set_mismatch")
        for candidate_id, candidate in manifest_by_id.items():
            row = by_id.get(candidate_id)
            if row is None:
                continue
            path_name = str(candidate.get("path") or "")
            if row.get("path") != path_name:
                blocked.append(
                    f"data_feasibility_candidate_authorization_path_mismatch:{candidate_id}"
                )
            if row.get("action") != actions_by_path.get(path_name):
                blocked.append(
                    f"data_feasibility_candidate_authorization_action_mismatch:{candidate_id}"
                )
            if not str(row.get("reason_code") or "").strip():
                blocked.append(
                    f"data_feasibility_candidate_authorization_reason_missing:{candidate_id}"
                )
            canonical_hash = candidate_authorization_binding_sha256(candidate)
            if row.get("candidate_binding_sha256") != canonical_hash:
                blocked.append(
                    f"data_feasibility_candidate_authorization_sha_mismatch:{candidate_id}"
                )

    references = payload.get("required_references")
    required_names = payload.get("required_reference_names")
    if not isinstance(required_names, list) or not required_names:
        blocked.append("data_feasibility_required_reference_names_missing")
        required_names = []
    if not isinstance(references, dict):
        blocked.append("data_feasibility_required_references_missing")
        references = {}
    if set(map(str, required_names)) != set(references):
        blocked.append("data_feasibility_required_reference_set_mismatch")
    for reference_name, reference in references.items():
        if not isinstance(reference, dict):
            blocked.append(f"data_feasibility_{reference_name}_reference_missing")
            continue
        path, error = _safe_repo_path(root, str(reference.get("path") or ""))
        if error:
            blocked.append(f"data_feasibility_{reference_name}_path_invalid:{error}")
        elif not path.is_file():
            blocked.append(f"data_feasibility_{reference_name}_path_missing")
        else:
            expected_hash = str(reference.get("sha256") or "")
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if not expected_hash:
                blocked.append(f"data_feasibility_{reference_name}_sha256_missing")
            elif expected_hash != actual_hash:
                blocked.append(f"data_feasibility_{reference_name}_sha256_mismatch")
    return blocked


def candidate_authorization_binding_sha256(candidate: dict[str, Any]) -> str:
    """Hash preregistered candidate semantics without circular evidence digests."""
    binding = dict(candidate)
    if str(binding.get("campaign_id") or "").strip():
        binding.pop("universe_contract_sha256", None)
        binding.pop("development_partition_contract_sha256", None)
    return hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _data_feasibility_blockers(
    payload: dict[str, Any] | None,
    feasibility_path: Path | None,
    manifest_path: Path,
    search_space: dict[str, Any],
    root: Path,
) -> list[str]:
    if payload is None or feasibility_path is None:
        return ["search_space_data_feasibility_missing_or_invalid"]
    if "q2_diagnostic_execution_authorized" not in payload:
        return _generic_data_feasibility_blockers(
            payload,
            feasibility_path,
            manifest_path,
            search_space,
            root,
        )
    blocked: list[str] = []
    if not isinstance(payload.get("schema_version"), int):
        blocked.append("data_feasibility_schema_version_invalid")
    if not str(payload.get("report_type") or "").strip():
        blocked.append("data_feasibility_report_type_missing")
    if payload.get("iter_id") != search_space.get("iter_id"):
        blocked.append("data_feasibility_iter_id_mismatch")
    for field_name in [
        "workflow_pass",
        "research_pass",
        "llm_contribution_pass",
        "paper_ready_pass",
        "q2_diagnostic_execution_authorized",
    ]:
        if not isinstance(payload.get(field_name), bool):
            blocked.append(f"data_feasibility_{field_name}_not_boolean")
    if payload.get("q2_diagnostic_execution_authorized") is not True:
        blocked.append("search_space_data_feasibility_not_authorized")
    if payload.get("workflow_pass") is not True:
        blocked.append("data_feasibility_workflow_not_passed")
    for field_name in ["research_pass", "llm_contribution_pass", "paper_ready_pass"]:
        if payload.get(field_name) is not False:
            blocked.append(f"data_feasibility_diagnostic_scope_{field_name}_must_be_false")

    expected_feasibility_sha = str(search_space.get("data_feasibility_sha256") or "")
    actual_feasibility_sha = hashlib.sha256(feasibility_path.read_bytes()).hexdigest()
    if not expected_feasibility_sha:
        blocked.append("data_feasibility_sha256_missing")
    elif expected_feasibility_sha != actual_feasibility_sha:
        blocked.append("data_feasibility_sha256_mismatch")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [*blocked, "data_feasibility_candidate_manifest_invalid_json"]
    candidates = manifest.get("candidates") if isinstance(manifest, dict) else None
    if not isinstance(candidates, list):
        return [*blocked, "data_feasibility_candidate_manifest_candidates_missing"]
    candidate_ids_by_path: dict[str, list[str]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        path_name = str(candidate.get("path") or "")
        candidate_id = str(candidate.get("candidate_id") or "")
        if path_name and candidate_id:
            candidate_ids_by_path.setdefault(path_name, []).append(candidate_id)

    path_gates = payload.get("path_gates")
    if not isinstance(path_gates, dict):
        return [*blocked, "data_feasibility_path_gates_missing"]
    if set(path_gates) != set(candidate_ids_by_path):
        blocked.append("data_feasibility_path_gate_set_mismatch")
    runnable_ids: list[str] = []
    skipped_ids: list[str] = []
    for path_name, candidate_ids in sorted(candidate_ids_by_path.items()):
        gate = path_gates.get(path_name)
        if not isinstance(gate, dict):
            blocked.append(f"data_feasibility_{path_name}_gate_missing")
            continue
        action = gate.get("q2_action")
        if action == "run_diagnostic":
            runnable_ids.extend(candidate_ids)
            if gate.get("historical_diagnostic_go") is not True:
                blocked.append(f"data_feasibility_{path_name}_run_without_diagnostic_go")
        elif action == "dependency_skipped":
            skipped_ids.extend(candidate_ids)
            if gate.get("historical_diagnostic_go") is not False:
                blocked.append(f"data_feasibility_{path_name}_skip_with_diagnostic_go")
        else:
            blocked.append(f"data_feasibility_{path_name}_invalid_action")
        if gate.get("historical_research_qualified") is not False:
            blocked.append(f"data_feasibility_{path_name}_research_scope_not_false")
        declared_ids = gate.get("candidate_ids")
        if declared_ids is not None:
            if not isinstance(declared_ids, list):
                blocked.append(f"data_feasibility_{path_name}_candidate_ids_not_list")
            elif sorted(map(str, declared_ids)) != sorted(candidate_ids):
                blocked.append(f"data_feasibility_{path_name}_candidate_ids_mismatch")

    event_ids = sorted(candidate_ids_by_path.get("event_llm", []))
    event_gate = path_gates.get("event_llm")
    if isinstance(event_gate, dict):
        declared_event_ids = event_gate.get("candidate_ids")
        if not isinstance(declared_event_ids, list):
            blocked.append("data_feasibility_event_llm_candidate_ids_not_list")
        elif sorted(map(str, declared_event_ids)) != event_ids:
            blocked.append("data_feasibility_event_llm_candidate_ids_mismatch")
    if payload.get("q2_diagnostic_execution_authorized") is True and not runnable_ids:
        blocked.append("data_feasibility_authorized_without_runnable_candidates")

    accounting = payload.get("candidate_accounting")
    expected_accounting = {
        "frozen_candidate_count": len(candidates),
        "diagnostic_runnable_count": len(runnable_ids),
        "dependency_skipped_count": len(skipped_ids),
        "unresolved_count": 0,
        "balanced": len(runnable_ids) + len(skipped_ids) == len(candidates),
    }
    if not isinstance(accounting, dict):
        blocked.append("data_feasibility_candidate_accounting_missing")
    else:
        for field_name, expected in expected_accounting.items():
            actual = accounting.get(field_name)
            if isinstance(expected, bool):
                matches = actual is expected
            else:
                matches = (
                    isinstance(actual, int) and not isinstance(actual, bool) and actual == expected
                )
            if not matches:
                blocked.append(
                    f"data_feasibility_accounting_{field_name}_mismatch:{actual}:{expected}"
                )

    authorization = payload.get("q2_authorization")
    authorization_rows = authorization.get("rows") if isinstance(authorization, dict) else None
    if not isinstance(authorization_rows, list):
        blocked.append("data_feasibility_q2_authorization_rows_missing")
    else:
        if authorization.get("candidate_count") != len(candidates):
            blocked.append("data_feasibility_q2_authorization_count_mismatch")
        authorization_by_id: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(authorization_rows):
            if not isinstance(row, dict):
                blocked.append(f"data_feasibility_q2_authorization_row_{index}_not_object")
                continue
            candidate_id = str(row.get("candidate_id") or "")
            if not candidate_id:
                blocked.append(f"data_feasibility_q2_authorization_row_{index}_id_missing")
                continue
            if candidate_id in authorization_by_id:
                blocked.append(f"data_feasibility_q2_authorization_duplicate:{candidate_id}")
            authorization_by_id[candidate_id] = row
        manifest_by_id = {
            str(candidate.get("candidate_id") or ""): candidate
            for candidate in candidates
            if isinstance(candidate, dict)
        }
        if set(authorization_by_id) != set(manifest_by_id):
            blocked.append("data_feasibility_q2_authorization_id_set_mismatch")
        for candidate_id, candidate in manifest_by_id.items():
            row = authorization_by_id.get(candidate_id)
            if row is None:
                continue
            path_name = str(candidate.get("path") or "")
            gate = path_gates.get(path_name)
            if row.get("path") != path_name:
                blocked.append(f"data_feasibility_q2_authorization_path_mismatch:{candidate_id}")
            if not isinstance(gate, dict) or row.get("action") != gate.get("q2_action"):
                blocked.append(f"data_feasibility_q2_authorization_action_mismatch:{candidate_id}")
            if not str(row.get("reason_code") or "").strip():
                blocked.append(f"data_feasibility_q2_authorization_reason_missing:{candidate_id}")
            canonical_sha = hashlib.sha256(
                json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if row.get("candidate_binding_sha256") != canonical_sha:
                blocked.append(
                    f"data_feasibility_q2_authorization_candidate_sha_mismatch:{candidate_id}"
                )
            evidence_raw = row.get("evidence_path")
            if evidence_raw:
                evidence_path, error = _safe_repo_path(root, str(evidence_raw))
                if error or not evidence_path.exists():
                    blocked.append(
                        f"data_feasibility_q2_authorization_evidence_invalid:{candidate_id}"
                    )
                elif (
                    row.get("evidence_sha256")
                    != hashlib.sha256(evidence_path.read_bytes()).hexdigest()
                ):
                    blocked.append(
                        f"data_feasibility_q2_authorization_evidence_sha_mismatch:{candidate_id}"
                    )

    resolved_references: dict[str, Path] = {}
    for field_name in [
        "parent_universe",
        "daily_panel",
        "intraday_panel",
        "cost_contract",
        "q2_execution_map",
    ]:
        reference = payload.get(field_name)
        if not isinstance(reference, dict):
            blocked.append(f"data_feasibility_{field_name}_reference_missing")
            continue
        reference_path, error = _safe_repo_path(root, str(reference.get("path") or ""))
        if error:
            blocked.append(f"data_feasibility_{field_name}_path_invalid:{error}")
            continue
        if not reference_path.exists():
            blocked.append(f"data_feasibility_{field_name}_path_missing")
            continue
        resolved_references[field_name] = reference_path
        expected_sha = str(reference.get("sha256") or "")
        actual_sha = hashlib.sha256(reference_path.read_bytes()).hexdigest()
        if not expected_sha:
            blocked.append(f"data_feasibility_{field_name}_sha256_missing")
        elif expected_sha != actual_sha:
            blocked.append(f"data_feasibility_{field_name}_sha256_mismatch")
    execution_map_path = resolved_references.get("q2_execution_map")
    if execution_map_path is not None:
        blocked.extend(
            _q2_execution_map_blockers(
                execution_map_path,
                manifest_by_id,
                set(runnable_ids),
                expected_iter_id=str(search_space.get("iter_id") or ""),
            )
        )
    return blocked


def _q2_execution_map_blockers(
    path: Path,
    manifest_by_id: dict[str, dict[str, Any]],
    runnable_ids: set[str],
    *,
    expected_iter_id: str,
) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["q2_execution_map_invalid_json"]
    if not isinstance(payload, dict):
        return ["q2_execution_map_not_object"]
    blocked: list[str] = []
    if expected_iter_id == "mom_stock_intraday_codesign_q1":
        from open_composer.research.stock_momentum_q2_contract import (
            build_q2_execution_map,
        )

        expected_payload = build_q2_execution_map({"candidates": list(manifest_by_id.values())})
        if payload != expected_payload:
            blocked.append("q2_execution_map_canonical_contract_mismatch")
    if payload.get("iter_id") != expected_iter_id:
        blocked.append("q2_execution_map_iter_id_mismatch")
    if payload.get("scope") != "historical_current_universe_diagnostic":
        blocked.append("q2_execution_map_scope_invalid")
    if payload.get("survivorship_labelled") is not True:
        blocked.append("q2_execution_map_survivorship_label_missing")
    if payload.get("primitive_field_allowlist") != ["open", "close", "volume"]:
        blocked.append("q2_execution_map_primitive_allowlist_invalid")
    for field_name in [
        "high_low_dependent_candidates_allowed",
        "forward_fill_allowed",
        "zero_return_substitution_allowed",
    ]:
        if payload.get(field_name) is not False:
            blocked.append(f"q2_execution_map_{field_name}_must_be_false")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return [*blocked, "q2_execution_map_rows_missing"]
    if payload.get("runnable_candidate_count") != len(runnable_ids):
        blocked.append("q2_execution_map_runnable_count_mismatch")
    by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            blocked.append(f"q2_execution_map_row_{index}_not_object")
            continue
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id:
            blocked.append(f"q2_execution_map_row_{index}_id_missing")
            continue
        if candidate_id in by_id:
            blocked.append(f"q2_execution_map_duplicate_id:{candidate_id}")
        by_id[candidate_id] = row
    if set(by_id) != runnable_ids:
        blocked.append("q2_execution_map_id_set_mismatch")
    for candidate_id, row in by_id.items():
        candidate = manifest_by_id.get(candidate_id)
        if candidate is None:
            continue
        if row.get("path") != candidate.get("path") or row.get("method") != candidate.get("method"):
            blocked.append(f"q2_execution_map_candidate_identity_mismatch:{candidate_id}")
        canonical_sha = hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if row.get("candidate_binding_sha256") != canonical_sha:
            blocked.append(f"q2_execution_map_candidate_sha_mismatch:{candidate_id}")
        if row.get("primitive_fields") != ["open", "close", "volume"]:
            blocked.append(f"q2_execution_map_primitive_fields_invalid:{candidate_id}")
        if row.get("research_pass") is not False:
            blocked.append(f"q2_execution_map_research_pass_not_false:{candidate_id}")
        if row.get("paper_ready_pass") is not False:
            blocked.append(f"q2_execution_map_paper_pass_not_false:{candidate_id}")
        if row.get("promotion_eligible") is not False:
            blocked.append(f"q2_execution_map_promotion_eligible:{candidate_id}")
        benchmarks = row.get("required_benchmarks")
        if not isinstance(benchmarks, list) or "ex_post_best_symbol_report_only" not in benchmarks:
            blocked.append(f"q2_execution_map_benchmarks_incomplete:{candidate_id}")
    return blocked


def _knowledge_contract_blockers(payload: Any, root: Path) -> list[str]:
    if not isinstance(payload, dict):
        return ["knowledge_contract_not_object"]
    blocked: list[str] = []
    required_paths = {
        "assessment_path": "knowledge-assessment.json",
        "scout_path": "knowledge-scout.json",
        "model_reuse_decision_path": "model-reuse-decision.json",
        "modality_role_matrix_path": "modality-role-matrix.json",
    }
    resolved: dict[str, Path] = {}
    for field_name in required_paths:
        raw = str(payload.get(field_name) or "").strip()
        if not raw:
            blocked.append(f"knowledge_contract_missing_{field_name}")
            continue
        path, error = _safe_repo_path(root, raw)
        if error:
            blocked.append(f"knowledge_contract_invalid_{field_name}:{error}")
        elif not path.exists():
            blocked.append(f"knowledge_contract_missing_artifact_{field_name}")
        else:
            resolved[field_name] = path
    partitions = payload.get("required_visibility_partitions")
    required_partitions = {
        "public_literature",
        "train_only_empirical",
        "challenge_result",
        "forward_observation",
    }
    if not isinstance(partitions, list) or not required_partitions.issubset(set(partitions)):
        blocked.append("knowledge_contract_visibility_partitions_incomplete")
    assessment_path = resolved.get("assessment_path")
    if assessment_path is not None:
        try:
            assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            blocked.append("knowledge_contract_assessment_invalid_json")
        else:
            if assessment.get("status") != "ok":
                blocked.append("knowledge_contract_assessment_not_ok")
            brief_path = assessment_path.parent / "external-brief.json"
            if not brief_path.is_file():
                blocked.append("knowledge_contract_external_brief_missing")
            else:
                expected_brief_hash = str(assessment.get("external_brief_sha256") or "")
                actual_brief_hash = hashlib.sha256(brief_path.read_bytes()).hexdigest()
                if not expected_brief_hash:
                    blocked.append("knowledge_contract_external_brief_sha256_missing")
                elif expected_brief_hash != actual_brief_hash:
                    blocked.append("knowledge_contract_external_brief_sha256_mismatch")
                expected_brief_path = _relpath(brief_path, root)
                if assessment.get("external_brief_path") != expected_brief_path:
                    blocked.append("knowledge_contract_external_brief_path_mismatch")
    return blocked


def _markdown_contract_blockers(
    paths: IterationDossierPaths,
    *,
    root: Path,
    stage: str,
    staged_evaluation_dir: Path | None = None,
) -> list[str]:
    blocked: list[str] = []
    decision_record_path = paths.decision_record_md
    if stage in ARTIFACT_REQUIRED_STAGES and (
        (paths.root / "evaluation-run").exists() or staged_evaluation_dir is not None
    ):
        receipt_blockers, authoritative_path = _final_evaluation_receipt_blockers(
            paths,
            root,
            staged_evaluation_dir=staged_evaluation_dir,
        )
        blocked.extend(receipt_blockers)
        if authoritative_path is not None:
            decision_record_path = authoritative_path
    for label, path in {
        "hypotheses": paths.hypotheses_md,
        "search_space_md": paths.search_space_md,
        "decision_record": decision_record_path,
        "external_brief_md": paths.external_brief_md,
    }.items():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if "TODO:" in text or len(text.split()) < 30:
            blocked.append(f"{label}_still_template")
    if paths.hypotheses_md.exists():
        text = paths.hypotheses_md.read_text(encoding="utf-8")
        for marker in ["Hypothesis", "Failure mode", "Measurement", "Stop/Pivot criterion"]:
            if marker not in text:
                blocked.append(f"hypotheses_missing_{_marker_slug(marker)}")
    if decision_record_path.exists():
        text = decision_record_path.read_text(encoding="utf-8")
        for marker in ["Path", "Decision", "Reason", "Next iteration suggestion"]:
            if marker not in text:
                blocked.append(f"decision_record_missing_{_marker_slug(marker)}")
        if stage in ARTIFACT_REQUIRED_STAGES and not re.search(
            r"\b(continue|pivot|stop)\b", text, re.IGNORECASE
        ):
            blocked.append("decision_record_missing_continue_pivot_stop")
    return blocked


def _final_evaluation_receipt_blockers(
    paths: IterationDossierPaths,
    root: Path,
    *,
    staged_evaluation_dir: Path | None = None,
) -> tuple[list[str], Path | None]:
    blocked: list[str] = []
    evaluation_dir = paths.root / "evaluation-run"
    actual_evaluation_dir = staged_evaluation_dir or evaluation_dir
    if actual_evaluation_dir.is_symlink() or not actual_evaluation_dir.is_dir():
        return ["final_evaluation_run_invalid"], None
    try:
        actual_evaluation_dir.resolve().relative_to(paths.root.resolve())
    except ValueError:
        return ["final_evaluation_staged_run_outside_iteration"], None
    receipt_path = actual_evaluation_dir / "evaluation-receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        return ["final_evaluation_receipt_missing"], None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["final_evaluation_receipt_invalid_json"], None
    if not isinstance(receipt, dict):
        return ["final_evaluation_receipt_not_object"], None
    iteration_id = paths.root.name
    strict_config = MULTIMODAL_FINAL_CONFIGS.get(iteration_id)
    is_strict_multimodal = strict_config is not None
    if receipt.get("iter_id") != iteration_id:
        blocked.append("final_evaluation_receipt_iter_id_mismatch")
    receipt_contract = receipt.get("receipt_contract")
    if is_strict_multimodal:
        if receipt_contract != strict_config["receipt_contract"]:
            blocked.append("final_evaluation_receipt_contract_mismatch")
        if receipt.get("schema_version") != 3:
            blocked.append("final_evaluation_receipt_schema_version_mismatch")
    else:
        if receipt_contract is not None:
            blocked.append("final_evaluation_receipt_contract_unsupported")
        if receipt.get("schema_version") != 1:
            blocked.append("final_evaluation_receipt_schema_version_mismatch")
    if receipt.get("evidence_publication_status") != "complete":
        blocked.append("final_evaluation_receipt_incomplete")
    for field_name in FINAL_STATUS_FIELDS:
        if type(receipt.get(field_name)) is not bool:
            blocked.append(f"final_evaluation_receipt_{field_name}_not_boolean")
    children = receipt.get("children")
    if not isinstance(children, dict):
        return blocked + ["final_evaluation_receipt_children_missing"], None

    expected_child_paths: dict[str, str] = {}
    if is_strict_multimodal:
        expected_child_paths = {
            name: _canonical_repo_path(evaluation_dir / filename, root)
            for name, filename in MULTIMODAL_FINAL_CHILD_FILENAMES.items()
        }
        missing_names = sorted(set(expected_child_paths) - set(children))
        extra_names = sorted(set(children) - set(expected_child_paths))
        blocked.extend(f"final_evaluation_child_{name}_missing" for name in missing_names)
        if extra_names:
            blocked.append("final_evaluation_receipt_unexpected_children:" + ",".join(extra_names))

    expected_inventory = {
        "evaluation-receipt.json",
        *(
            Path(str(binding.get("path") or "")).name
            for binding in children.values()
            if isinstance(binding, dict)
        ),
    }
    evaluation_anchor_contract = (
        strict_config.get("evaluation_anchor_contract") if is_strict_multimodal else None
    )
    if isinstance(evaluation_anchor_contract, str):
        expected_inventory.add("evaluation-anchor.json")
    actual_entries = list(actual_evaluation_dir.iterdir())
    actual_inventory = {entry.name for entry in actual_entries}
    missing_inventory = sorted(expected_inventory - actual_inventory)
    extra_inventory = sorted(actual_inventory - expected_inventory)
    if missing_inventory:
        blocked.append("final_evaluation_run_inventory_missing:" + ",".join(missing_inventory))
    if extra_inventory:
        blocked.append("final_evaluation_run_inventory_extra:" + ",".join(extra_inventory))
    if any(entry.is_symlink() or not entry.is_file() for entry in actual_entries):
        blocked.append("final_evaluation_run_inventory_non_regular")

    bound_paths = [
        str(binding.get("path") or "") for binding in children.values() if isinstance(binding, dict)
    ]
    if len(bound_paths) != len(set(bound_paths)):
        blocked.append("final_evaluation_receipt_child_paths_not_unique")

    canonical_legacy_decision_path = _canonical_repo_path(
        evaluation_dir / "decision-record.md", root
    )
    resolved_children: dict[str, Path] = {}
    for name, binding in children.items():
        if not isinstance(binding, dict):
            blocked.append(f"final_evaluation_child_{name}_binding_invalid")
            continue
        raw_path = str(binding.get("path") or "")
        expected_path = expected_child_paths.get(str(name))
        if expected_path is not None and raw_path != expected_path:
            blocked.append(f"final_evaluation_child_{name}_path_mismatch")
            continue
        if (
            not is_strict_multimodal
            and name == "decision_record"
            and raw_path != canonical_legacy_decision_path
        ):
            blocked.append("final_evaluation_child_decision_record_path_mismatch")
            continue
        canonical_child, error = _safe_repo_path(root, raw_path)
        if error:
            blocked.append(f"final_evaluation_child_{name}_path_invalid:{error}")
            continue
        try:
            relative = canonical_child.relative_to(evaluation_dir.resolve())
        except ValueError:
            blocked.append(f"final_evaluation_child_{name}_outside_evaluation_run")
            continue
        child = actual_evaluation_dir / relative
        if child.is_symlink() or not child.is_file():
            blocked.append(f"final_evaluation_child_{name}_missing")
            continue
        expected_hash = str(binding.get("sha256") or "")
        actual_hash = hashlib.sha256(child.read_bytes()).hexdigest()
        if expected_hash != actual_hash:
            blocked.append(f"final_evaluation_child_{name}_sha256_mismatch")
            continue
        expected_size = binding.get("size_bytes")
        if type(expected_size) is not int or expected_size < 0:
            blocked.append(f"final_evaluation_child_{name}_size_invalid")
            continue
        if expected_size != child.stat().st_size:
            blocked.append(f"final_evaluation_child_{name}_size_mismatch")
            continue
        resolved_children[str(name)] = child

    required_children = (
        set(MULTIMODAL_FINAL_CHILD_FILENAMES)
        if is_strict_multimodal
        else {"decision_record", "evaluation", "trial_ledger"}
    )
    missing = sorted(required_children - set(resolved_children))
    if missing:
        blocked.extend(f"final_evaluation_child_{name}_missing" for name in missing)
        return blocked, None

    if is_strict_multimodal:
        for label, filename in MULTIMODAL_FINAL_LOCK_FILENAMES.items():
            expected_path = paths.root / "lock-set" / filename
            blocked.extend(
                _final_receipt_file_binding_blockers(
                    root,
                    receipt.get(label),
                    label=label,
                    expected_path=expected_path,
                )
            )
        blocked.extend(
            _final_receipt_file_binding_blockers(
                root,
                receipt.get("evaluation_attempt"),
                label="evaluation_attempt",
                expected_path=paths.root / "evaluation-attempt.json",
            )
        )
        blocked.extend(
            _strict_multimodal_receipt_semantic_blockers(
                paths,
                root,
                receipt,
                evaluation_path=resolved_children["evaluation"],
                strict_config=strict_config,
            )
        )
        if isinstance(evaluation_anchor_contract, str):
            blocked.extend(
                _strict_multimodal_evaluation_anchor_blockers(
                    paths,
                    root,
                    receipt,
                    receipt_path=receipt_path,
                    actual_evaluation_dir=actual_evaluation_dir,
                    anchor_contract=evaluation_anchor_contract,
                )
            )

    decision_path = resolved_children["decision_record"]
    decision_text = decision_path.read_text(encoding="utf-8")
    marker = re.search(r"-\s*Decision:\s*(continue|pivot|stop)\b", decision_text, re.IGNORECASE)
    receipt_decision = receipt.get("decision")
    if marker is None:
        blocked.append("final_evaluation_decision_missing_continue_pivot_stop")
    elif is_strict_multimodal:
        expected_marker = (
            strict_config["decision_markers"].get(receipt_decision)
            if isinstance(receipt_decision, str)
            else None
        )
        if expected_marker is None:
            blocked.append("final_evaluation_receipt_decision_invalid")
        elif marker.group(1).lower() != expected_marker:
            blocked.append("final_evaluation_receipt_decision_mismatch")
    elif not isinstance(receipt_decision, str) or receipt_decision not in LEGACY_FINAL_DECISIONS:
        blocked.append("final_evaluation_receipt_decision_invalid")
    elif marker.group(1).lower() != receipt_decision:
        blocked.append("final_evaluation_receipt_decision_mismatch")

    try:
        evaluation = json.loads(resolved_children["evaluation"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        blocked.append("final_evaluation_report_invalid_json")
        evaluation = None
    if not isinstance(evaluation, dict):
        blocked.append("final_evaluation_report_not_object")
    else:
        if is_strict_multimodal:
            if evaluation.get("schema_version") != 1:
                blocked.append("final_evaluation_report_schema_version_mismatch")
            if evaluation.get("iter_id") != iteration_id:
                blocked.append("final_evaluation_report_iter_id_mismatch")
            if evaluation.get("report_type") != strict_config["report_type"]:
                blocked.append("final_evaluation_report_type_mismatch")
        for field_name in FINAL_STATUS_FIELDS:
            if type(evaluation.get(field_name)) is not bool:
                blocked.append(f"final_evaluation_report_{field_name}_not_boolean")
        for field_name in ("decision", *FINAL_STATUS_FIELDS):
            if evaluation.get(field_name) != receipt.get(field_name):
                blocked.append(f"final_evaluation_receipt_{field_name}_mismatch")
        if is_strict_multimodal:
            expected_decision = (
                "continue_to_locked_forward_observation"
                if receipt.get("research_pass") is True
                else strict_config["stop_decision"]
            )
            if receipt_decision != expected_decision:
                blocked.append("final_evaluation_receipt_decision_status_mismatch")
            if receipt.get("paper_ready_pass") is not False:
                blocked.append("final_evaluation_receipt_paper_ready_pass_must_be_false")
    return blocked, decision_path


def _strict_multimodal_evaluation_anchor_blockers(
    paths: IterationDossierPaths,
    root: Path,
    receipt: dict[str, Any],
    *,
    receipt_path: Path,
    actual_evaluation_dir: Path,
    anchor_contract: str,
) -> list[str]:
    anchor_path = actual_evaluation_dir / "evaluation-anchor.json"
    if anchor_path.is_symlink() or not anchor_path.is_file():
        return ["final_evaluation_anchor_missing"]
    blocked: list[str] = []
    if stat.S_IMODE(anchor_path.stat().st_mode) & 0o222:
        blocked.append("final_evaluation_anchor_not_read_only")
    try:
        raw = anchor_path.read_bytes()
        anchor = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return blocked + ["final_evaluation_anchor_invalid_json"]
    if not isinstance(anchor, dict):
        return blocked + ["final_evaluation_anchor_not_object"]

    def binding(path: Path, *, canonical_path: Path | None = None) -> dict[str, Any] | None:
        if path.is_symlink() or not path.is_file():
            return None
        content = path.read_bytes()
        return {
            "path": _canonical_repo_path(canonical_path or path, root),
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }

    lock_anchor_path = paths.root / "lock-set/lock-anchor.json"
    lock_anchor = _read_json_object(lock_anchor_path)
    source_bindings = {
        "receipt": binding(
            receipt_path,
            canonical_path=paths.root / "evaluation-run/evaluation-receipt.json",
        ),
        "preregistration_lock": binding(paths.root / "lock-set/preregistration-lock.json"),
        "runner_lock": binding(paths.root / "lock-set/runner-lock.json"),
        "lock_anchor": binding(lock_anchor_path),
        "evaluation_attempt": binding(paths.root / "evaluation-attempt.json"),
    }
    if any(value is None for value in source_bindings.values()) or lock_anchor is None:
        return blocked + ["final_evaluation_anchor_source_binding_missing"]
    operator_lock_anchor_sha256 = lock_anchor.get("operator_lock_anchor_sha256")
    subject = {
        "schema_version": 1,
        "anchor_contract": anchor_contract,
        "iter_id": paths.root.name,
        "status": "complete_for_external_hash_custody",
        "anchor_path": _canonical_repo_path(
            paths.root / "evaluation-run/evaluation-anchor.json", root
        ),
        **source_bindings,
        "operator_lock_anchor_sha256": operator_lock_anchor_sha256,
        "custody_requirement": (
            "record_evaluation_anchor_file_sha256_and_operator_subject_sha256_"
            "outside_the_mutable_worktree"
        ),
        "local_read_only_mode_is_not_independent_custody": True,
    }
    expected = {
        **subject,
        "operator_evaluation_anchor_sha256": hashlib.sha256(
            json.dumps(subject, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
                "ascii"
            )
        ).hexdigest(),
    }
    if anchor != expected:
        blocked.append("final_evaluation_anchor_semantics_invalid")
    canonical_bytes = (
        json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "ascii"
        )
        + b"\n"
    )
    if raw != canonical_bytes:
        blocked.append("final_evaluation_anchor_noncanonical_bytes")
    if anchor.get("receipt") != source_bindings["receipt"]:
        blocked.append("final_evaluation_anchor_receipt_binding_mismatch")
    if (
        anchor.get("operator_evaluation_anchor_sha256")
        != expected["operator_evaluation_anchor_sha256"]
    ):
        blocked.append("final_evaluation_anchor_operator_sha256_mismatch")
    if receipt.get("iter_id") != anchor.get("iter_id"):
        blocked.append("final_evaluation_anchor_receipt_iter_id_mismatch")
    return blocked


def _strict_multimodal_receipt_semantic_blockers(
    paths: IterationDossierPaths,
    root: Path,
    receipt: dict[str, Any],
    *,
    evaluation_path: Path,
    strict_config: dict[str, Any],
) -> list[str]:
    blocked: list[str] = []
    iteration_id = paths.root.name
    preregistration_path = paths.root / "lock-set/preregistration-lock.json"
    runner_path = paths.root / "lock-set/runner-lock.json"
    anchor_path = paths.root / "lock-set/lock-anchor.json"
    attempt_path = paths.root / "evaluation-attempt.json"

    preregistration = _read_json_object(preregistration_path)
    runner = _read_json_object(runner_path)
    anchor = _read_json_object(anchor_path)
    attempt = _read_json_object(attempt_path)
    evaluation = _read_json_object(evaluation_path)
    for label, payload in {
        "preregistration_lock": preregistration,
        "runner_lock": runner,
        "lock_anchor": anchor,
        "evaluation_attempt": attempt,
    }.items():
        if payload is None:
            blocked.append(f"final_evaluation_{label}_semantic_json_invalid")
    if any(payload is None for payload in (preregistration, runner, anchor, attempt)):
        return blocked

    if (
        preregistration.get("schema_version") != 1
        or preregistration.get("iter_id") != iteration_id
        or preregistration.get("status") != strict_config["preregistration_status"]
    ):
        blocked.append("final_evaluation_preregistration_lock_semantics_invalid")
    if (
        runner.get("schema_version") != 1
        or runner.get("iter_id") != iteration_id
        or runner.get("status") != strict_config["runner_status"]
    ):
        blocked.append("final_evaluation_runner_lock_semantics_invalid")

    preregistration_sha256 = hashlib.sha256(preregistration_path.read_bytes()).hexdigest()
    runner_sha256 = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    anchor_subject = {
        "iter_id": iteration_id,
        "preregistration_lock_sha256": preregistration_sha256,
        "runner_lock_sha256": runner_sha256,
    }
    operator_anchor_sha256 = hashlib.sha256(
        json.dumps(anchor_subject, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        anchor.get("schema_version") != 1
        or any(anchor.get(key) != value for key, value in anchor_subject.items())
        or anchor.get("operator_lock_anchor_sha256") != operator_anchor_sha256
    ):
        blocked.append("final_evaluation_lock_anchor_semantics_invalid")
    if (
        strict_config.get("external_custody_required") is True
        and anchor.get("external_custody_required") is not True
    ):
        blocked.append("final_evaluation_lock_anchor_external_custody_not_required")

    expected_attempt = {
        "schema_version": 1,
        "iter_id": iteration_id,
        "status": "reserved_before_first_price_parse",
        "operator_lock_anchor_sha256": operator_anchor_sha256,
        "preregistration_lock_sha256": preregistration_sha256,
        "runner_lock_sha256": runner_sha256,
        "rerun_policy": "any_existing_attempt_blocks_all_future_evaluation_attempts",
    }
    if any(attempt.get(key) != value for key, value in expected_attempt.items()):
        blocked.append("final_evaluation_attempt_semantics_invalid")
    custody_fields = ("lock_custody_receipt_sha256", "lock_custody_bundle_sha256")
    if strict_config.get("external_custody_required") is True and any(
        not _is_sha256(attempt.get(field_name)) for field_name in custody_fields
    ):
        blocked.append("final_evaluation_attempt_custody_binding_invalid")
    data_manifest_sha256 = attempt.get("data_manifest_sha256")
    if not _is_sha256(data_manifest_sha256):
        blocked.append("final_evaluation_attempt_data_manifest_sha256_invalid")
    if not isinstance(attempt.get("reserved_at"), str) or not attempt.get("reserved_at"):
        blocked.append("final_evaluation_attempt_reserved_at_missing")

    if evaluation is None:
        return blocked + ["final_evaluation_preflight_missing"]
    preflight = evaluation.get("preflight")
    if not isinstance(preflight, dict):
        return blocked + ["final_evaluation_preflight_missing"]
    expected_preflight_values = {
        "status": "ok",
        "preregistration_lock_path": _canonical_repo_path(preregistration_path, root),
        "preregistration_lock_sha256": preregistration_sha256,
        "runner_lock_path": _canonical_repo_path(runner_path, root),
        "runner_lock_sha256": runner_sha256,
        "lock_anchor_path": _canonical_repo_path(anchor_path, root),
        "lock_anchor_file_sha256": hashlib.sha256(anchor_path.read_bytes()).hexdigest(),
        "operator_lock_anchor_sha256": operator_anchor_sha256,
        "data_manifest_sha256": data_manifest_sha256,
    }
    harness_contract = strict_config.get("harness_reconciliation_contract")
    if isinstance(harness_contract, str):
        harness_reconciliation = preregistration.get("harness_reconciliation")
        if isinstance(harness_reconciliation, dict):
            expected_preflight_values["harness_reconciliation_sha256"] = hashlib.sha256(
                json.dumps(
                    harness_reconciliation,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("ascii")
            ).hexdigest()
        else:
            blocked.append("final_evaluation_harness_reconciliation_missing_from_lock")
    if any(preflight.get(key) != value for key, value in expected_preflight_values.items()):
        blocked.append("final_evaluation_preflight_lock_binding_mismatch")
    if strict_config.get("external_custody_required") is True:
        if any(not _is_sha256(preflight.get(field_name)) for field_name in custody_fields):
            blocked.append("final_evaluation_preflight_custody_binding_invalid")
        if any(
            preflight.get(field_name) != attempt.get(field_name) for field_name in custody_fields
        ):
            blocked.append("final_evaluation_preflight_attempt_custody_mismatch")
    if preflight.get("evaluation_attempt") != receipt.get("evaluation_attempt"):
        blocked.append("final_evaluation_preflight_attempt_binding_mismatch")
    for label in (
        "candidate_manifest",
        "data_contract",
        "data_manifest",
        "parent_snapshot_binding",
    ):
        blocked.extend(_preflight_path_hash_blockers(root, preflight, label=label))
    if isinstance(harness_contract, str):
        blocked.extend(
            _strict_r5_harness_reconciliation_blockers(
                paths,
                root,
                preregistration,
                evaluation,
                preflight=preflight,
                harness_contract=harness_contract,
                candidate_ids=list(strict_config.get("harness_candidate_ids") or []),
            )
        )

    checks = receipt.get("prepublication_checks")
    if not isinstance(checks, dict):
        return blocked + ["final_evaluation_prepublication_checks_missing"]
    reconciliation = evaluation.get("evidence_reconciliation")
    staged_verification = (
        reconciliation.get("staged_ledger_verification")
        if isinstance(reconciliation, dict)
        else None
    )
    expected_checks = {
        "prebacktest_dossier_status": preflight.get("status"),
        "workflow_pass": evaluation.get("workflow_pass"),
        "fallback_identity": _nested_value(
            evaluation,
            "fallback_identity",
            strict_config["fallback_identity_field"],
        ),
        "cost_reconciliation_pass": _nested_value(evaluation, "cost_reconciliation", "pass"),
        "benchmark_family_complete": _nested_value(evaluation, "benchmarks", "complete"),
        "staged_ledger_verification_pass": (
            staged_verification.get("pass") if isinstance(staged_verification, dict) else None
        ),
    }
    if isinstance(harness_contract, str):
        expected_checks["harness_reconciliation_pass"] = _nested_value(
            evaluation,
            "harness_reconciliation",
            "research_gate_pass",
        )
    if checks != expected_checks:
        blocked.append("final_evaluation_prepublication_checks_mismatch")
    if expected_checks["staged_ledger_verification_pass"] is not True:
        blocked.append("final_evaluation_staged_ledger_verification_not_passed")
    if checks.get("workflow_pass") != receipt.get("workflow_pass"):
        blocked.append("final_evaluation_prepublication_workflow_status_mismatch")
    return blocked


def _strict_r5_harness_reconciliation_blockers(
    paths: IterationDossierPaths,
    root: Path,
    preregistration: dict[str, Any],
    evaluation: dict[str, Any],
    *,
    preflight: dict[str, Any],
    harness_contract: str,
    candidate_ids: list[str],
) -> list[str]:
    blocked: list[str] = []
    reconciliation = preregistration.get("harness_reconciliation")
    if not isinstance(reconciliation, dict):
        return ["final_evaluation_harness_reconciliation_missing_from_lock"]
    if evaluation.get("harness_reconciliation") != reconciliation:
        blocked.append("final_evaluation_harness_reconciliation_report_mismatch")
    expected_digest = hashlib.sha256(
        json.dumps(
            reconciliation,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
    ).hexdigest()
    if preflight.get("harness_reconciliation_sha256") != expected_digest:
        blocked.append("final_evaluation_harness_reconciliation_preflight_hash_mismatch")
    if (
        reconciliation.get("schema_version") != 1
        or reconciliation.get("reconciliation_contract") != harness_contract
        or reconciliation.get("iter_id") != paths.root.name
        or reconciliation.get("stage") != "research"
        or reconciliation.get("candidate_count") != len(candidate_ids)
        or reconciliation.get("research_gate_pass") is not True
        or reconciliation.get("empirical_execution_evidence_pass") is not False
        or reconciliation.get("paper_readiness_evidence_pass") is not False
    ):
        blocked.append("final_evaluation_harness_reconciliation_semantics_invalid")
    limitations = reconciliation.get("limitations")
    if (
        not isinstance(limitations, list)
        or len(limitations) < 3
        or not any("deterministic" in str(item) for item in limitations)
        or not any("Paper TCA" in str(item) for item in limitations)
    ):
        blocked.append("final_evaluation_harness_reconciliation_limitations_missing")

    artifacts = preregistration.get("artifacts")
    artifact_by_path = {
        str(binding.get("path") or ""): binding
        for binding in artifacts or []
        if isinstance(binding, dict)
    }
    if len(artifact_by_path) != len(artifacts or []):
        blocked.append("final_evaluation_harness_lock_artifact_inventory_invalid")
    specs = preregistration.get("specs")
    spec_by_candidate = {
        str(binding.get("candidate_id") or ""): binding
        for binding in specs or []
        if isinstance(binding, dict)
    }
    if set(spec_by_candidate) != set(candidate_ids):
        blocked.append("final_evaluation_harness_spec_inventory_invalid")

    config_paths = {
        "risk_domains": Path("harness/risk_domains.yaml"),
        "artifact_contracts": Path("harness/artifact_contracts.yaml"),
        "skill_manifest": Path("harness/skill_manifest.yaml"),
    }
    contract_bindings = reconciliation.get("contract_bindings")
    if not isinstance(contract_bindings, dict) or set(contract_bindings) != set(config_paths):
        blocked.append("final_evaluation_harness_contract_bindings_invalid")
    else:
        for label, expected_path in config_paths.items():
            binding = contract_bindings[label]
            blocked.extend(
                _final_receipt_file_binding_blockers(
                    root,
                    binding,
                    label=f"harness_contract_{label}",
                    expected_path=root / expected_path,
                )
            )
            if artifact_by_path.get(expected_path.as_posix()) != binding:
                blocked.append(f"final_evaluation_harness_contract_{label}_not_lock_bound")

    candidates = reconciliation.get("candidates")
    if not isinstance(candidates, dict) or set(candidates) != set(candidate_ids):
        blocked.append("final_evaluation_harness_candidate_inventory_invalid")
        return blocked
    binding_suffixes = {
        "plan_json": "reports/harness/plans/{strategy}.json",
        "plan_markdown": "reports/harness/plans/{strategy}.md",
        "execution_policy": "reports/harness/execution/{strategy}-execution-policy.json",
        "execution_reality": "reports/harness/execution/{strategy}-execution-reality.json",
        "execution_reality_markdown": ("reports/harness/execution/{strategy}-execution-reality.md"),
        "source_cards": "reports/harness/source_cards/{strategy}.jsonl",
        "verify_receipt": "reports/harness/verify/{strategy}.json",
    }
    for candidate_id in candidate_ids:
        row = candidates[candidate_id]
        strategy_name = f"us_multiasset_forward_mm_r5_{candidate_id[2:].lower()}"
        spec_path = Path(f"strategy_specs/drafts/{strategy_name}.yaml")
        spec_binding = spec_by_candidate.get(candidate_id, {})
        if (
            not isinstance(row, dict)
            or row.get("candidate_id") != candidate_id
            or row.get("strategy_name") != strategy_name
            or row.get("spec_path") != spec_path.as_posix()
            or row.get("spec_file_sha256") != spec_binding.get("file_sha256")
            or row.get("spec_semantic_sha256") != spec_binding.get("semantic_sha256")
            or row.get("risk_domains") != ["daily_open_execution"]
            or row.get("required_skills") != ["execution-reality-reviewer", "source-researcher"]
            or row.get("required_artifacts")
            != ["execution_policy", "execution_reality_report", "source_cards"]
            or row.get("blocking_rule_ids")
            != ["naked_market_order_must_be_justified", "compare_at_least_two_execution_methods"]
            or row.get("structural_research_harness_pass") is not True
            or row.get("empirical_execution_evidence_pass") is not False
            or row.get("paper_readiness_evidence_pass") is not False
        ):
            blocked.append(f"final_evaluation_harness_candidate_semantics_invalid:{candidate_id}")
            continue
        bindings = row.get("bindings")
        if not isinstance(bindings, dict) or set(bindings) != set(binding_suffixes):
            blocked.append(f"final_evaluation_harness_candidate_bindings_invalid:{candidate_id}")
            continue
        for label, template in binding_suffixes.items():
            expected_relative = Path(template.format(strategy=strategy_name))
            binding = bindings[label]
            blocked.extend(
                _final_receipt_file_binding_blockers(
                    root,
                    binding,
                    label=f"harness_{candidate_id}_{label}",
                    expected_path=root / expected_relative,
                )
            )
            if artifact_by_path.get(expected_relative.as_posix()) != binding:
                blocked.append(f"final_evaluation_harness_{candidate_id}_{label}_not_lock_bound")
    return blocked


def _preflight_path_hash_blockers(
    root: Path,
    preflight: dict[str, Any],
    *,
    label: str,
) -> list[str]:
    raw_path = preflight.get(f"{label}_path")
    expected_hash = preflight.get(f"{label}_sha256")
    path, error = _safe_repo_path(root, str(raw_path or ""))
    if error:
        return [f"final_evaluation_preflight_{label}_path_invalid:{error}"]
    unresolved = root / str(raw_path or "")
    if unresolved.is_symlink() or not path.is_file():
        return [f"final_evaluation_preflight_{label}_missing"]
    if (
        not _is_sha256(expected_hash)
        or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash
    ):
        return [f"final_evaluation_preflight_{label}_sha256_mismatch"]
    return []


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _nested_value(payload: dict[str, Any], parent: str, child: str) -> Any:
    value = payload.get(parent)
    return value.get(child) if isinstance(value, dict) else None


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _final_receipt_file_binding_blockers(
    root: Path,
    binding: Any,
    *,
    label: str,
    expected_path: Path,
) -> list[str]:
    blocked: list[str] = []
    if not isinstance(binding, dict):
        return [f"final_evaluation_{label}_binding_invalid"]
    raw_path = str(binding.get("path") or "")
    if raw_path != _canonical_repo_path(expected_path, root):
        blocked.append(f"final_evaluation_{label}_path_mismatch")
        return blocked
    resolved, error = _safe_repo_path(root, raw_path)
    unresolved = root / raw_path
    if error:
        return [f"final_evaluation_{label}_path_invalid:{error}"]
    if unresolved.is_symlink() or not resolved.is_file():
        return [f"final_evaluation_{label}_missing"]
    expected_hash = binding.get("sha256")
    if not isinstance(expected_hash, str) or hashlib.sha256(resolved.read_bytes()).hexdigest() != (
        expected_hash
    ):
        blocked.append(f"final_evaluation_{label}_sha256_mismatch")
    expected_size = binding.get("size_bytes")
    if type(expected_size) is not int or expected_size < 0:
        blocked.append(f"final_evaluation_{label}_size_invalid")
    elif expected_size != resolved.stat().st_size:
        blocked.append(f"final_evaluation_{label}_size_mismatch")
    return blocked


def _canonical_repo_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _write_text_if_needed(path: Path, text: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        return
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def _write_json_if_needed(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        return
    write_json(path, payload)


def _external_brief_json_template(iter_id: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "iter_id": iter_id,
        "strategy_name": "us_minute_momentum",
        "source_spec_path": None,
        "spec_hash": None,
        "objective": "US minute momentum round 1",
        "current_source_card_paths": [],
        "source_evidence_bindings": [],
        "sources": [],
        "topic_coverage": [],
        "candidate_matrix_revisions": [],
        "hypothesis_links": [],
    }


def _search_space_json_template(iter_id: str) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "created_at": datetime.now(UTC).isoformat(),
        "iter_id": iter_id,
        "strategy_name": "us_minute_momentum",
        "source_spec_path": None,
        "spec_hash": None,
        "total_candidate_budget": 80,
        "paths": [],
        "trial_ledger_paths": [],
        "evaluation_report_paths": [],
        "cost_table_path": "",
        "data_feasibility_path": "",
    }


def _external_brief_md_template(iter_id: str) -> str:
    return f"""# External Brief: {iter_id}

TODO: Replace this template with at least eight sourced findings, including at
least three paper-level sources. Each source must include URL, date, type,
credibility, core claim, Open Composer applicability, and a reflection on
overfit/decay/cost sensitivity.
"""


def _hypotheses_template(iter_id: str) -> str:
    return f"""# Hypotheses: {iter_id}

TODO: List falsifiable hypotheses. Each hypothesis needs source support,
expected failure mode, measurement window, benchmark family, and stop/pivot
criterion.

## H1

- Hypothesis:
- Failure mode:
- Measurement:
- Stop/Pivot criterion:
"""


def _search_space_md_template(iter_id: str) -> str:
    return f"""# Search Space: {iter_id}

TODO: Define each path, parameter grid, path candidate count, total candidate
budget, cost assumptions, benchmark family, and which Wave 9.2 go/no-go band it
uses. Keep each path <=24 combinations and the full round <=80 combinations.
"""


def _decision_record_template(iter_id: str) -> str:
    return f"""# Decision Record: {iter_id}

TODO: At the end of the round, record each path's continue/pivot/stop decision,
evidence, rejected variants, next action, and whether ML or AI-information
round entry conditions are met.

## P1

- Path:
- Decision: pending
- Reason:
- Next iteration suggestion:
"""


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _safe_repo_path(root: Path, raw: str) -> tuple[Path, str | None]:
    path = Path(raw)
    if path.is_absolute():
        return path, "absolute_path"
    resolved = (root / path).resolve()
    root_resolved = root.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return resolved, "outside_repo"
    return resolved, None


def _marker_slug(marker: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", marker.lower()).strip("_")
