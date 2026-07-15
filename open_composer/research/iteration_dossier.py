from __future__ import annotations

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
        "schema_version": 1,
        "iter_id": iter_id,
        "strategy_name": "us_minute_momentum",
        "source_spec_path": None,
        "spec_hash": None,
        "objective": "US minute momentum round 1",
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
