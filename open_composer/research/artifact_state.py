from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import project_root
from open_composer.models.project import ProjectEvidenceStatus, StrategyProject, StrategyProjectRun
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import write_json

_LEVERAGED_ETF_SYMBOLS = {
    "TQQQ",
    "SQQQ",
    "UPRO",
    "SPXU",
    "SPXL",
    "SOXL",
    "SOXS",
    "TECL",
    "TECS",
    "FNGU",
    "FNGD",
    "LABU",
    "LABD",
    "TMF",
    "TMV",
    "UVXY",
    "SVXY",
}


class ProjectArtifactEvidenceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProjectEvidenceStatus = "unknown"
    summary: str = ""
    artifact_path: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProjectArtifactState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    project_id: str
    strategy_name: str
    current_spec_path: str | None = None
    last_successful_step: str = "unknown"
    latest_artifacts: dict[str, str] = Field(default_factory=dict)
    evidence_status: dict[str, ProjectArtifactEvidenceState] = Field(default_factory=dict)
    blocked_items: list[str] = Field(default_factory=list)
    warning_items: list[str] = Field(default_factory=list)
    next_minimal_actions: list[str] = Field(default_factory=list)
    do_not_repeat: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def build_project_artifact_state(
    project: StrategyProject,
    root: Path | None = None,
) -> ProjectArtifactState:
    base = root or project_root()
    spec, spec_name, spec_blockers = _load_project_spec(project, base)
    strategy_name = spec_name or _strategy_name_from_project(project)
    latest_artifacts: dict[str, str] = {}
    blocked: list[str] = list(spec_blockers)
    warnings: list[str] = []
    next_actions: list[str] = []
    do_not_repeat: list[str] = []

    latest_run = _load_latest_run(project, base)
    if project.latest_run_path:
        latest_artifacts["latest_run"] = project.latest_run_path
    if latest_run:
        blocked.extend(latest_run.blockers)
        if latest_run.blocker_summary:
            blocked.extend(latest_run.blocker_summary.root_blockers)
            next_actions.extend(latest_run.blocker_summary.next_minimal_actions)
            do_not_repeat.extend(latest_run.blocker_summary.do_not_repeat)
            for path in latest_run.blocker_summary.artifact_refs:
                _record_existing_artifact(
                    base,
                    latest_artifacts,
                    f"blocker_ref:{Path(path).stem}",
                    path,
                    blocked,
                )

    evidence = {
        "factor_quality": _factor_quality_state(base, strategy_name, spec, latest_artifacts),
        "execution_reality": _execution_reality_state(base, strategy_name, spec, latest_artifacts),
        "alt_llm_evidence": _alt_llm_state(base, strategy_name, spec, latest_artifacts),
    }

    for key, item in evidence.items():
        blocked.extend(f"{key}:{blocker}" for blocker in item.blockers)
        warnings.extend(f"{key}:{warning}" for warning in item.warnings)
        if item.status == "blocked":
            next_actions.append(_evidence_next_action(key))

    _scan_promotion(base, strategy_name, latest_artifacts, blocked, warnings)
    _scan_paper_readiness(base, strategy_name, latest_artifacts, blocked, warnings)
    if spec:
        _scan_financial_boundaries(
            base, strategy_name, spec, latest_artifacts, blocked, warnings, next_actions
        )

    if not blocked and project.blockers:
        blocked.extend(project.blockers)
    if not next_actions:
        next_actions.append(_default_next_action(blocked, evidence))

    return ProjectArtifactState(
        project_id=project.project_id,
        strategy_name=strategy_name,
        current_spec_path=project.current_spec_path,
        last_successful_step=_last_successful_step(project, latest_artifacts, blocked),
        latest_artifacts=dict(sorted(latest_artifacts.items())),
        evidence_status=evidence,
        blocked_items=_unique(blocked),
        warning_items=_unique(warnings),
        next_minimal_actions=_unique(next_actions),
        do_not_repeat=_unique(do_not_repeat),
    )


def write_project_artifact_state(
    project: StrategyProject,
    root: Path | None = None,
) -> tuple[ProjectArtifactState, Path]:
    base = root or project_root()
    state = build_project_artifact_state(project, base)
    project_state_path = base / "projects" / project.project_id / "artifact-state.json"
    write_json(project_state_path, state)
    strategy_state_path = (
        base / "reports" / "research" / "state" / f"{state.strategy_name}-artifact-state.json"
    )
    write_json(strategy_state_path, state)
    return state, project_state_path


def load_project_artifact_state(
    project_id: str,
    root: Path | None = None,
) -> ProjectArtifactState:
    base = root or project_root()
    path = base / "projects" / project_id / "artifact-state.json"
    if not path.exists():
        raise FileNotFoundError(f"project artifact state not found: {project_id}")
    return ProjectArtifactState.model_validate_json(path.read_text(encoding="utf-8"))


def _load_project_spec(
    project: StrategyProject, base: Path
) -> tuple[StrategySpec | None, str | None, list[str]]:
    if not project.current_spec_path:
        return None, None, ["strategy_spec:missing"]
    path = base / project.current_spec_path
    if not path.exists():
        return None, None, ["strategy_spec:missing"]
    try:
        spec = load_strategy_spec(path)
    except Exception as exc:  # pragma: no cover - defensive scanner path
        return None, None, [f"strategy_spec:invalid:{exc}"]
    return spec, spec.name, []


def _load_latest_run(project: StrategyProject, base: Path) -> StrategyProjectRun | None:
    if not project.latest_run_path:
        return None
    path = base / project.latest_run_path
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return StrategyProjectRun.model_validate(raw)
    except ValueError:
        return None


def _factor_quality_state(
    base: Path,
    strategy_name: str,
    spec: StrategySpec | None,
    artifacts: dict[str, str],
) -> ProjectArtifactEvidenceState:
    path = base / "reports" / "research" / f"{strategy_name}-factor-lab.json"
    raw, error = _read_json(path)
    if raw is None:
        if spec and spec.factors:
            return ProjectArtifactEvidenceState(
                status="blocked",
                summary="Custom factors are declared but Factor Lab evidence is missing.",
                blockers=["factor_lab_missing"],
            )
        return ProjectArtifactEvidenceState(
            status="not_applicable",
            summary="No explicit StrategySpec factors require Factor Lab diagnostics.",
        )
    rel = _relpath(path, base)
    artifacts["factor_lab"] = rel
    if error:
        return ProjectArtifactEvidenceState(
            status="blocked",
            summary="Factor Lab artifact exists but could not be read.",
            artifact_path=rel,
            blockers=["factor_lab_invalid_json"],
        )
    status = _status(raw.get("status"))
    flags = [str(item) for item in raw.get("quality_flags", []) if item]
    warnings = [] if status != "warning" else flags
    blockers = flags if status == "blocked" else []
    return ProjectArtifactEvidenceState(
        status=status,
        summary=_summary_from_status("Factor Lab", status, flags),
        artifact_path=rel,
        blockers=blockers,
        warnings=warnings,
    )


def _execution_reality_state(
    base: Path,
    strategy_name: str,
    spec: StrategySpec | None,
    artifacts: dict[str, str],
) -> ProjectArtifactEvidenceState:
    report = base / "reports" / "harness" / "execution" / f"{strategy_name}-execution-reality.json"
    raw, error = _read_json(report)
    if raw is None:
        research = _research_report_execution_reality(base, strategy_name)
        if research:
            artifacts["research_report"] = research["path"]
            status = _status(research["status"])
            return ProjectArtifactEvidenceState(
                status=status,
                summary="Execution reality was recovered from the latest research report.",
                artifact_path=research["path"],
                blockers=[] if status != "blocked" else ["execution_reality_not_ok"],
                warnings=list(research["warnings"]),
            )
        if _execution_required(spec):
            return ProjectArtifactEvidenceState(
                status="blocked",
                summary="Execution reality evidence is required before paper readiness.",
                blockers=["execution_reality_missing"],
            )
        return ProjectArtifactEvidenceState(
            status="unknown",
            summary="Execution reality evidence has not been linked yet.",
        )
    rel = _relpath(report, base)
    artifacts["execution_reality"] = rel
    if error:
        return ProjectArtifactEvidenceState(
            status="blocked",
            summary="Execution reality artifact exists but could not be read.",
            artifact_path=rel,
            blockers=["execution_reality_invalid_json"],
        )
    status = _status(raw.get("status"))
    blockers = [str(item) for item in raw.get("blockers", []) if item]
    warnings = [str(item) for item in raw.get("warnings", []) if item]
    return ProjectArtifactEvidenceState(
        status=status,
        summary=f"Execution reality status is {status}.",
        artifact_path=rel,
        blockers=blockers if status == "blocked" else [],
        warnings=warnings,
    )


def _alt_llm_state(
    base: Path,
    strategy_name: str,
    spec: StrategySpec | None,
    artifacts: dict[str, str],
) -> ProjectArtifactEvidenceState:
    path = base / "reports" / "research" / f"{strategy_name}-alt-data-quality.json"
    raw, error = _read_json(path)
    required = _alt_llm_required(spec)
    if raw is None:
        if required:
            return ProjectArtifactEvidenceState(
                status="blocked",
                summary="LLM or alternative-data dependency needs PIT and contribution evidence.",
                blockers=["alt_llm_evidence_missing"],
            )
        return ProjectArtifactEvidenceState(
            status="not_applicable",
            summary="No LLM, news, event, macro, or alternative-data factor is declared.",
        )
    rel = _relpath(path, base)
    artifacts["alternative_data_quality"] = rel
    if error:
        return ProjectArtifactEvidenceState(
            status="blocked",
            summary="Alternative-data artifact exists but could not be read.",
            artifact_path=rel,
            blockers=["alt_llm_evidence_invalid_json"],
        )
    status = _status(raw.get("status"))
    warnings = [str(item) for item in raw.get("warnings", []) if item]
    factors = raw.get("factors", [])
    if required and status == "ok":
        missing = _missing_alt_llm_evidence(base, strategy_name)
        if missing:
            return ProjectArtifactEvidenceState(
                status="blocked",
                summary="PIT, marginal lift, or robustness evidence is missing.",
                artifact_path=rel,
                blockers=missing,
                warnings=warnings,
            )
    return ProjectArtifactEvidenceState(
        status=status,
        summary=f"Alternative-data/LLM evidence status is {status}; factors={len(factors)}.",
        artifact_path=rel,
        blockers=[] if status != "blocked" else warnings or ["alt_llm_evidence_blocked"],
        warnings=warnings if status == "warning" else [],
    )


def _scan_promotion(
    base: Path,
    strategy_name: str,
    artifacts: dict[str, str],
    blocked: list[str],
    warnings: list[str],
) -> None:
    path = base / "reports" / "research" / f"{strategy_name}-promotion.json"
    raw, error = _read_json(path)
    if raw is None:
        return
    rel = _relpath(path, base)
    artifacts["promotion"] = rel
    if error:
        blocked.append("promotion:invalid_json")
        return
    for check in raw.get("checks", []):
        if not isinstance(check, dict):
            continue
        name = str(check.get("name") or "check")
        status = check.get("status")
        if status == "blocked":
            blocked.append(f"promotion:{name}")
        elif status == "warning":
            warnings.append(f"promotion:{name}")
    gate = raw.get("gate_summary")
    if isinstance(gate, dict):
        if gate.get("research_pass") is False:
            blocked.append("promotion:research_pass_false")
        if gate.get("paper_ready_pass") is False:
            blocked.append("promotion:paper_ready_pass_false")


def _scan_paper_readiness(
    base: Path,
    strategy_name: str,
    artifacts: dict[str, str],
    blocked: list[str],
    warnings: list[str],
) -> None:
    for path in [
        base / "reports" / "paper" / "readiness" / f"{strategy_name}.json",
        base / "reports" / "paper" / "readiness" / f"{strategy_name}-readiness.json",
    ]:
        raw, error = _read_json(path)
        if raw is None:
            continue
        rel = _relpath(path, base)
        artifacts["paper_readiness"] = rel
        if error:
            blocked.append("paper_readiness:invalid_json")
            return
        if raw.get("ready") is False or raw.get("status") == "blocked":
            blocked.append("paper_readiness:blocked")
        elif raw.get("status") == "warning":
            warnings.append("paper_readiness:warning")
        return


def _scan_financial_boundaries(
    base: Path,
    strategy_name: str,
    spec: StrategySpec,
    artifacts: dict[str, str],
    blocked: list[str],
    warnings: list[str],
    next_actions: list[str],
) -> None:
    if spec.position_direction in {"short_only", "long_short"}:
        required = {
            "short_sale_source_cards": f"reports/harness/source_cards/{strategy_name}.jsonl",
            "borrow_cost_estimate": f"reports/research/{strategy_name}-borrow-cost-estimate.json",
            "short_squeeze_stress": f"reports/research/{strategy_name}-short-squeeze-stress.json",
            "ex_dividend_risk_note": f"reports/research/{strategy_name}-ex-dividend-risk-note.md",
            "short_exposure_policy": (
                f"reports/harness/execution/{strategy_name}-short-exposure-policy.json"
            ),
        }
        for key, rel in required.items():
            _record_existing_artifact(base, artifacts, key, rel, blocked)
        missing = [
            key
            for key, rel in required.items()
            if key not in artifacts or not (base / rel).exists()
        ]
        if missing:
            blocked.extend(f"short_selling:{key}:missing" for key in missing)
            next_actions.append(
                "produce missing short-selling borrow, squeeze, and dividend evidence"
            )

    if spec.portfolio.mode != "single_symbol":
        required = {
            "router_target_weights": f"reports/execution/{strategy_name}-target-weights.json",
            "router_rebalance_intents": f"reports/execution/{strategy_name}-rebalance-intents.json",
            "router_execution_observation": (
                f"reports/execution/{strategy_name}-execution-observation.json"
            ),
            "router_cost_stress": f"reports/research/{strategy_name}-router-cost-stress.json",
            "router_data_evidence": f"reports/research/{strategy_name}-router-data-evidence.json",
            "router_validation": f"reports/research/{strategy_name}-router-validation.json",
        }
        for key, rel in required.items():
            _record_existing_artifact(base, artifacts, key, rel, blocked)
        observation, error = _read_json(base / required["router_execution_observation"])
        if observation and not error:
            substate = str(observation.get("execution_substate") or "unknown")
            if substate == "blocked":
                blocked.append("router:execution_observation_blocked")
            elif substate == "observation_only":
                warnings.append("router:execution_observation_only")
        missing = [key for key, rel in required.items() if not (base / rel).exists()]
        if missing:
            blocked.extend(f"router:{key}:missing" for key in missing)
            next_actions.append(
                "produce missing router target-weight and execution-observation artifacts"
            )

    _scan_options_artifacts(base, strategy_name, artifacts, warnings)


def _scan_options_artifacts(
    base: Path,
    strategy_name: str,
    artifacts: dict[str, str],
    warnings: list[str],
) -> None:
    for suffix in ("options-overlay-research", "options-research", "research"):
        path = base / "reports" / "options" / f"{strategy_name}-{suffix}.json"
        raw, error = _read_json(path)
        if raw is None:
            continue
        rel = _relpath(path, base)
        artifacts[f"options:{suffix}"] = rel
        if error:
            warnings.append("options:invalid_json")
        else:
            substate = raw.get("execution_substate") or raw.get("status") or "observation_only"
            warnings.append(f"options:{substate}")


def _record_existing_artifact(
    base: Path,
    artifacts: dict[str, str],
    key: str,
    rel: str,
    blocked: list[str],
) -> None:
    if (base / rel).exists():
        artifacts[key] = rel
    else:
        blocked.append(f"{key}:missing")


def _research_report_execution_reality(base: Path, strategy_name: str) -> dict[str, object] | None:
    path = base / "reports" / "research" / f"{strategy_name}-research-report.json"
    raw, error = _read_json(path)
    if raw is None or error:
        return None
    backtest = raw.get("backtest")
    if not isinstance(backtest, dict):
        return None
    reality = backtest.get("execution_reality")
    if not isinstance(reality, dict):
        return None
    return {
        "path": _relpath(path, base),
        "status": reality.get("status", "unknown"),
        "warnings": reality.get("warnings", []),
    }


def _missing_alt_llm_evidence(base: Path, strategy_name: str) -> list[str]:
    required = {
        "pit_replay_missing": base / "reports" / "research" / f"{strategy_name}-pit-replay.json",
        "marginal_lift_missing": base
        / "reports"
        / "research"
        / f"{strategy_name}-marginal-lift.json",
        "modality_robustness_missing": base
        / "reports"
        / "research"
        / f"{strategy_name}-modality-robustness.json",
    }
    return [key for key, path in required.items() if not path.exists()]


def _read_json(path: Path) -> tuple[dict[str, Any] | None, bool]:
    if not path.exists():
        return None, False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, True
    return (raw, False) if isinstance(raw, dict) else ({}, True)


def _status(value: object) -> ProjectEvidenceStatus:
    if value in {"ok", "warning", "blocked", "not_applicable", "unknown"}:
        return value  # type: ignore[return-value]
    return "unknown"


def _execution_required(spec: StrategySpec | None) -> bool:
    if spec is None:
        return False
    return (
        spec.execution.mode == "paper_auto"
        or spec.portfolio.mode != "single_symbol"
        or spec.execution_policy is not None
        or spec.reality_model is not None
        or any(symbol.upper() in _LEVERAGED_ETF_SYMBOLS for symbol in spec.universe)
    )


def _alt_llm_required(spec: StrategySpec | None) -> bool:
    if spec is None:
        return False
    if spec.llm_review.enabled:
        return True
    if any(factor.source in {"llm_feature", "feature_packet"} for factor in spec.factors.values()):
        return True
    return any(
        capability.startswith(("news.", "events.", "event.", "macro.", "llm."))
        for capability in spec.required_capabilities
    )


def _summary_from_status(prefix: str, status: ProjectEvidenceStatus, details: list[str]) -> str:
    if details:
        return f"{prefix} status is {status}: {', '.join(details[:3])}."
    return f"{prefix} status is {status}."


def _evidence_next_action(key: str) -> str:
    return {
        "factor_quality": "produce or fix Factor Lab evidence before further optimization",
        "execution_reality": "produce execution reality evidence before paper readiness",
        "alt_llm_evidence": "produce PIT, marginal lift, and robustness evidence for LLM/alt data",
    }.get(key, f"resolve {key} evidence blocker")


def _default_next_action(
    blocked: list[str], evidence: dict[str, ProjectArtifactEvidenceState]
) -> str:
    if "strategy_spec:missing" in blocked:
        return "create or link a draft StrategySpec before research iteration"
    if blocked:
        return "resolve current blockers before continuing optimization"
    if any(item.status == "warning" for item in evidence.values()):
        return "review warnings and run a small targeted improvement"
    return "run a small bounded strategy optimization"


def _last_successful_step(
    project: StrategyProject,
    artifacts: dict[str, str],
    blocked: list[str],
) -> str:
    if "paper_readiness" in artifacts and not any(
        item.startswith("paper_readiness:") for item in blocked
    ):
        return "paper_readiness"
    if "promotion" in artifacts:
        return "promotion"
    if "latest_run" in artifacts:
        return "latest_run"
    if project.current_spec_path:
        return "strategy_spec"
    return "project_created"


def _strategy_name_from_project(project: StrategyProject) -> str:
    return (
        project.current_spec_path.rsplit("/", maxsplit=1)[-1].removesuffix(".yaml")
        if project.current_spec_path
        else project.project_id.replace("-", "_")
    )


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
