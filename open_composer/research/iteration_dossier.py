from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,80}$")
ITERATION_ROOT = Path("reports/research/iterations")
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
VALIDATION_STAGES = {"pre-backtest", "final"}


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
) -> IterationDossierValidation:
    base = root or project_root()
    if stage not in VALIDATION_STAGES:
        raise ValueError(f"stage must be one of {', '.join(sorted(VALIDATION_STAGES))}")
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
            _search_space_blockers(search_space, base, require_artifacts=stage == "final")
        )
    blocked.extend(_markdown_contract_blockers(paths, stage=stage))
    status = "blocked" if blocked else "warning" if warnings else "ok"
    return IterationDossierValidation(
        iter_id=iter_id,
        root=paths.root,
        status=status,
        blocked=blocked,
        warnings=warnings,
    )


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
            elif require_artifacts and not artifact_path.exists():
                blocked.append(f"search_space_{field_name}_{idx}_missing")
        if require_artifacts and not value:
            blocked.append(f"search_space_{field_name}_empty_final")
    knowledge_contract = payload.get("knowledge_contract")
    if knowledge_contract is not None:
        blocked.extend(_knowledge_contract_blockers(knowledge_contract, root))
    candidate_manifest_raw = str(payload.get("candidate_manifest_path") or "").strip()
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
    return blocked


def _spec_iteration_binding_blockers(
    spec: Any,
    spec_reference: str,
    search_space: dict[str, Any],
) -> list[str]:
    blocked: list[str] = []
    notes = spec.notes.model_dump(mode="json") if hasattr(spec.notes, "model_dump") else {}
    research_design = notes.get("research_design") if isinstance(notes, dict) else None
    if not isinstance(research_design, dict):
        return [f"candidate_manifest_spec_binding_missing:{spec_reference}"]
    if research_design.get("iter_id") != search_space.get("iter_id"):
        blocked.append(f"candidate_manifest_spec_iter_id_mismatch:{spec_reference}")
    if research_design.get("candidate_manifest_path") != search_space.get(
        "candidate_manifest_path"
    ):
        blocked.append(f"candidate_manifest_spec_manifest_path_mismatch:{spec_reference}")
    feasibility_binding = research_design.get("data_feasibility_path") or research_design.get(
        "universe_contract_path"
    )
    if feasibility_binding != search_space.get("data_feasibility_path"):
        blocked.append(f"candidate_manifest_spec_feasibility_path_mismatch:{spec_reference}")
    return blocked


def _data_feasibility_blockers(
    payload: dict[str, Any] | None,
    feasibility_path: Path | None,
    manifest_path: Path,
    search_space: dict[str, Any],
    root: Path,
) -> list[str]:
    if payload is None or feasibility_path is None:
        return ["search_space_data_feasibility_missing_or_invalid"]
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
    return blocked


def _markdown_contract_blockers(paths: IterationDossierPaths, *, stage: str) -> list[str]:
    blocked: list[str] = []
    for label, path in {
        "hypotheses": paths.hypotheses_md,
        "search_space_md": paths.search_space_md,
        "decision_record": paths.decision_record_md,
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
    if paths.decision_record_md.exists():
        text = paths.decision_record_md.read_text(encoding="utf-8")
        for marker in ["Path", "Decision", "Reason", "Next iteration suggestion"]:
            if marker not in text:
                blocked.append(f"decision_record_missing_{_marker_slug(marker)}")
        if stage == "final" and not re.search(r"\b(continue|pivot|stop)\b", text, re.IGNORECASE):
            blocked.append("decision_record_missing_continue_pivot_stop")
    return blocked


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
        "schema_version": 1,
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
