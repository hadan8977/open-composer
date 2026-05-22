from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.agent_requests import AgentRequest, AgentRequestCreate, create_agent_request
from open_composer.config import ensure_dir, project_root
from open_composer.models.project import StrategyProject
from open_composer.projects import (
    load_project,
    project_agent_prompt,
    write_project,
    write_project_context,
)
from open_composer.research.artifact_state import (
    ProjectArtifactState,
    write_project_artifact_state,
)
from open_composer.storage import write_json

IterationIntent = Literal[
    "resolve_blockers",
    "produce_missing_evidence",
    "paper_readiness_review",
    "small_strategy_optimization",
]


class ProjectIterationStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_name: str
    intent: str
    reason: str
    expected_artifacts: list[str] = Field(default_factory=list)


class ProjectIterationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    project_id: str
    strategy_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rounds_requested: int = Field(default=1, ge=1, le=10)
    requested_by: str = "dashboard"
    intent: IterationIntent = "small_strategy_optimization"
    user_advice: str = ""
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_minimal_actions: list[str] = Field(default_factory=list)
    do_not_repeat: list[str] = Field(default_factory=list)
    step_plan: list[ProjectIterationStep] = Field(default_factory=list)
    context_path: str
    artifact_state_path: str
    latest_run_path: str | None = None


class ProjectIterationRequestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: StrategyProject
    artifact_state: ProjectArtifactState
    iteration_plan: ProjectIterationPlan
    iteration_plan_path: str
    agent_request: AgentRequest
    agent_request_path: str


def create_project_iteration_request(
    project_id: str,
    root: Path | None = None,
    *,
    rounds: int = 1,
    advice: str = "",
    requested_by: str = "dashboard",
) -> ProjectIterationRequestResult:
    base = root or project_root()
    project = load_project(project_id, base)
    project.iteration.user_requested_stop = False
    project.state = "iterating"

    artifact_state, artifact_state_path = write_project_artifact_state(project, base)
    plan = _build_iteration_plan(
        project=project,
        artifact_state=artifact_state,
        artifact_state_path=_relpath(artifact_state_path, base),
        rounds=rounds,
        advice=advice,
        requested_by=requested_by,
    )
    project.next_action = plan.intent
    project.blockers = list(plan.blockers)
    context_path = write_project_context(project, base, task=_context_task(plan))
    plan.context_path = _relpath(context_path, base)
    project.state = "iterating"
    write_project(project, base)

    plan_path = _write_iteration_plan(plan, base)
    prompt = _iteration_prompt(project, plan)
    related_paths = _unique(
        [
            f"projects/{project.project_id}/project.yaml",
            plan.context_path,
            _relpath(artifact_state_path, base),
            _relpath(plan_path, base),
            *([project.current_spec_path] if project.current_spec_path else []),
            *([project.latest_run_path] if project.latest_run_path else []),
        ]
    )
    request = create_agent_request(
        AgentRequestCreate(
            requested_by=requested_by,
            task_type="strategy_optimization",
            title=f"Continue strategy project: {project.name}",
            prompt=prompt,
            related_paths=related_paths,
        ),
        base,
    )
    return ProjectIterationRequestResult(
        project=project,
        artifact_state=artifact_state,
        iteration_plan=plan,
        iteration_plan_path=_relpath(plan_path, base),
        agent_request=request,
        agent_request_path=f"reports/agent_requests/{request.request_id}.json",
    )


def _build_iteration_plan(
    *,
    project: StrategyProject,
    artifact_state: ProjectArtifactState,
    artifact_state_path: str,
    rounds: int,
    advice: str,
    requested_by: str,
) -> ProjectIterationPlan:
    blockers = _unique([*project.blockers, *artifact_state.blocked_items])
    warnings = _unique(artifact_state.warning_items)
    next_actions = _unique(artifact_state.next_minimal_actions)
    intent = _choose_intent(project, artifact_state, blockers)
    steps = _step_plan(intent, artifact_state, blockers, next_actions)
    return ProjectIterationPlan(
        project_id=project.project_id,
        strategy_name=artifact_state.strategy_name,
        rounds_requested=rounds,
        requested_by=requested_by,
        intent=intent,
        user_advice=advice.strip(),
        blockers=blockers,
        warnings=warnings,
        next_minimal_actions=next_actions,
        do_not_repeat=list(artifact_state.do_not_repeat),
        step_plan=steps,
        context_path=f"projects/{project.project_id}/context.md",
        artifact_state_path=artifact_state_path,
        latest_run_path=project.latest_run_path,
    )


def _choose_intent(
    project: StrategyProject,
    artifact_state: ProjectArtifactState,
    blockers: list[str],
) -> IterationIntent:
    if any(_is_evidence_blocker(item) for item in blockers):
        return "produce_missing_evidence"
    if any(item.startswith(("promotion:", "paper_readiness:")) for item in blockers):
        return "paper_readiness_review"
    if blockers:
        return "resolve_blockers"
    evidence = artifact_state.evidence_status
    if any(item.status == "blocked" for item in evidence.values()):
        return "produce_missing_evidence"
    if project.gate_summary.paper_ready_pass is False:
        return "paper_readiness_review"
    return "small_strategy_optimization"


def _step_plan(
    intent: IterationIntent,
    artifact_state: ProjectArtifactState,
    blockers: list[str],
    next_actions: list[str],
) -> list[ProjectIterationStep]:
    if intent == "produce_missing_evidence":
        return [
            ProjectIterationStep(
                step_name="artifact_state_review",
                intent="read_current_state",
                reason="Start from the deterministic Project artifact state.",
                expected_artifacts=[artifact_state.current_spec_path or ""],
            ),
            ProjectIterationStep(
                step_name="evidence_gap_repair",
                intent="produce_missing_evidence",
                reason=_first(next_actions, "Evidence blockers exist."),
                expected_artifacts=_expected_evidence_artifacts(
                    blockers, artifact_state.strategy_name
                ),
            ),
            ProjectIterationStep(
                step_name="project_run_summary",
                intent="write_run_ledger",
                reason="Record changed artifacts, blockers, and next minimal actions.",
                expected_artifacts=[f"projects/{artifact_state.project_id}/runs/round-XXX.yaml"],
            ),
        ]
    if intent == "paper_readiness_review":
        return [
            ProjectIterationStep(
                step_name="readiness_blocker_review",
                intent="resolve_promotion_or_paper_blocker",
                reason=_first(next_actions, "Promotion or paper readiness is blocked."),
                expected_artifacts=[
                    f"reports/research/{artifact_state.strategy_name}-promotion.json",
                    f"reports/paper/readiness/{artifact_state.strategy_name}.json",
                ],
            )
        ]
    if intent == "resolve_blockers":
        return [
            ProjectIterationStep(
                step_name="blocker_repair",
                intent="resolve_current_blockers",
                reason=_first(blockers, "Resolve deterministic Project blockers."),
                expected_artifacts=[],
            )
        ]
    return [
        ProjectIterationStep(
            step_name="bounded_strategy_optimization",
            intent="small_strategy_optimization",
            reason="No blocking artifact state was found; change at most one or two key variables.",
            expected_artifacts=[
                f"reports/research/{artifact_state.strategy_name}-research-report.json",
                f"reports/research/{artifact_state.strategy_name}-promotion.json",
            ],
        ),
        ProjectIterationStep(
            step_name="project_run_summary",
            intent="write_run_ledger",
            reason="Append a lightweight run summary after the worker finishes.",
            expected_artifacts=[f"projects/{artifact_state.project_id}/runs/round-XXX.yaml"],
        ),
    ]


def _context_task(plan: ProjectIterationPlan) -> str:
    lines = [
        f"Iteration intent: {plan.intent}",
        f"Rounds requested: {plan.rounds_requested}",
    ]
    if plan.user_advice:
        lines.append(f"User advice: {plan.user_advice}")
    if plan.blockers:
        lines.append("Current blockers:")
        lines.extend(f"- {item}" for item in plan.blockers[:12])
    if plan.next_minimal_actions:
        lines.append("Next minimal actions:")
        lines.extend(f"- {item}" for item in plan.next_minimal_actions[:8])
    if plan.do_not_repeat:
        lines.append("Do not repeat:")
        lines.extend(f"- {item}" for item in plan.do_not_repeat[:8])
    lines.append("Keep each round bounded to one or two key variables.")
    return "\n".join(lines)


def _iteration_prompt(project: StrategyProject, plan: ProjectIterationPlan) -> str:
    return "\n".join(
        [
            project_agent_prompt(project, _context_task(plan)),
            "",
            "Iteration control:",
            f"- plan_path: {plan.context_path.replace('context.md', 'iteration-plan-latest.json')}",
            f"- artifact_state_path: {plan.artifact_state_path}",
            f"- intent: {plan.intent}",
            "- Treat worker self-report as a claim; write artifacts and a Project run summary.",
            "- Do not mark paper readiness from LLM judgment alone.",
        ]
    )


def _write_iteration_plan(plan: ProjectIterationPlan, base: Path) -> Path:
    project_dir = ensure_dir(base / "projects" / plan.project_id)
    latest_path = project_dir / "iteration-plan-latest.json"
    write_json(latest_path, plan)
    stamp = plan.created_at.strftime("%Y%m%dT%H%M%SZ")
    archive_path = ensure_dir(project_dir / "plans") / f"{stamp}.json"
    write_json(archive_path, plan)
    return latest_path


def _expected_evidence_artifacts(blockers: list[str], strategy_name: str) -> list[str]:
    expected: list[str] = []
    if any("factor_quality" in item or "factor_lab" in item for item in blockers):
        expected.append(f"reports/research/{strategy_name}-factor-lab.json")
    if any("execution_reality" in item or item.startswith("router:") for item in blockers):
        expected.append(f"reports/harness/execution/{strategy_name}-execution-reality.json")
    if any("alt_llm" in item or "alternative" in item for item in blockers):
        expected.extend(
            [
                f"reports/research/{strategy_name}-pit-replay.json",
                f"reports/research/{strategy_name}-marginal-lift.json",
                f"reports/research/{strategy_name}-modality-robustness.json",
            ]
        )
    if any(item.startswith("short_selling:") for item in blockers):
        expected.extend(
            [
                f"reports/research/{strategy_name}-borrow-cost-estimate.json",
                f"reports/research/{strategy_name}-short-squeeze-stress.json",
                f"reports/research/{strategy_name}-ex-dividend-risk-note.md",
            ]
        )
    return _unique(expected)


def _is_evidence_blocker(value: str) -> bool:
    return value.startswith(
        (
            "factor_quality:",
            "execution_reality:",
            "alt_llm_evidence:",
            "short_selling:",
            "router:",
        )
    )


def _first(values: list[str], fallback: str) -> str:
    return values[0] if values else fallback


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
