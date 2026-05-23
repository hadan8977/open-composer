from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import project_root
from open_composer.models.project import QueueCommand, QueueCommandKind, StrategyProject
from open_composer.projects import (
    append_queue,
    append_trace,
    load_project,
    write_project,
    write_project_context,
)
from open_composer.research.artifact_state import (
    ProjectArtifactState,
    write_project_artifact_state,
)

IterationIntent = Literal[
    "resolve_blockers",
    "produce_missing_evidence",
    "paper_readiness_review",
    "small_strategy_optimization",
]


class ContinueResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: StrategyProject
    artifact_state: ProjectArtifactState
    queue_command: QueueCommand
    queue_path: str
    trace_path: str
    context_path: str
    context_bytes: int
    artifact_state_path: str
    intent: IterationIntent
    rounds_requested: int = Field(default=1, ge=1, le=10)


# Backward-compatible public name used by older callers/tests. It now returns
# the queue-based Step 2 result instead of a one-shot request object.
ProjectIterationRequestResult = ContinueResult


def continue_project(
    project_id: str,
    *,
    body: str = "",
    kind: QueueCommandKind = "continue",
    via: Literal["dashboard", "cli", "api"] = "cli",
    root: Path | None = None,
    rounds: int = 1,
    requested_by: str = "cli",
) -> ContinueResult:
    base = root or project_root()
    project = load_project(project_id, base)
    project.iteration.user_requested_stop = False
    project.state = "iterating"

    artifact_state, artifact_state_path = write_project_artifact_state(project, base)
    intent = _choose_intent(project, artifact_state)
    project.next_action = intent
    project.blockers = list(_unique([*project.blockers, *artifact_state.blocked_items]))
    write_project(project, base)

    task = _context_task(
        intent=intent,
        rounds=rounds,
        body=body,
        blockers=project.blockers,
        warnings=artifact_state.warning_items,
        next_actions=artifact_state.next_minimal_actions,
        do_not_repeat=artifact_state.do_not_repeat,
    )
    context_path = write_project_context(project, base, task=task)
    context_bytes = len(context_path.read_bytes())
    command = append_queue(
        project.project_id,
        kind=kind,
        body=body,
        via=via,
        metadata={
            "requested_by": requested_by,
            "rounds": rounds,
            "intent": intent,
            "artifact_state_path": _relpath(artifact_state_path, base),
            "context_path": _relpath(context_path, base),
        },
        root=base,
    )
    append_trace(
        project.project_id,
        agent="system",
        operation="project_continue_queued",
        queue_command_id=command.id,
        metadata={"kind": kind, "intent": intent, "context_bytes": context_bytes},
        root=base,
    )
    return ContinueResult(
        project=project,
        artifact_state=artifact_state,
        queue_command=command,
        queue_path=f"projects/{project.project_id}/queue.jsonl",
        trace_path=f"projects/{project.project_id}/trace.jsonl",
        context_path=_relpath(context_path, base),
        context_bytes=context_bytes,
        artifact_state_path=_relpath(artifact_state_path, base),
        intent=intent,
        rounds_requested=rounds,
    )


def create_project_iteration_request(
    project_id: str,
    root: Path | None = None,
    *,
    rounds: int = 1,
    advice: str = "",
    requested_by: str = "dashboard",
) -> ContinueResult:
    return continue_project(
        project_id,
        body=advice,
        kind="continue",
        via="dashboard" if requested_by == "dashboard" else "cli",
        root=root,
        rounds=rounds,
        requested_by=requested_by,
    )


def _choose_intent(
    project: StrategyProject,
    artifact_state: ProjectArtifactState,
) -> IterationIntent:
    blockers = _unique([*project.blockers, *artifact_state.blocked_items])
    if any(_is_evidence_blocker(item) for item in blockers):
        return "produce_missing_evidence"
    if any(item.startswith(("promotion:", "paper_readiness:")) for item in blockers):
        return "paper_readiness_review"
    if blockers:
        return "resolve_blockers"
    evidence = artifact_state.evidence_status
    if any(item.status == "blocked" for item in evidence.values()):
        return "produce_missing_evidence"
    if (
        isinstance(project.gate_summary, dict)
        and project.gate_summary.get("paper_ready_pass") is False
    ):
        return "paper_readiness_review"
    return "small_strategy_optimization"


def _context_task(
    *,
    intent: IterationIntent,
    rounds: int,
    body: str,
    blockers: list[str],
    warnings: list[str],
    next_actions: list[str],
    do_not_repeat: list[str],
) -> str:
    lines = [
        f"Queued at: {datetime.now(UTC).isoformat()}",
        f"Iteration intent: {intent}",
        f"Rounds requested: {rounds}",
        "",
        "Agent operating principle:",
        (
            "Use the active Codex/Claude Code session context when available. The product "
            "queue is a durable command channel, not a rigid step planner."
        ),
        (
            "Choose the exact tool order yourself, but write durable artifacts, trace entries, "
            "and Project run summaries for any material result."
        ),
    ]
    if body.strip():
        lines.extend(["", "User command:", body.strip()])
    if blockers:
        lines.append("")
        lines.append("Current blockers:")
        lines.extend(f"- {item}" for item in blockers[:16])
    if warnings:
        lines.append("")
        lines.append("Current warnings:")
        lines.extend(f"- {item}" for item in warnings[:12])
    if next_actions:
        lines.append("")
        lines.append("Next minimal actions:")
        lines.extend(f"- {item}" for item in next_actions[:10])
    if do_not_repeat:
        lines.append("")
        lines.append("Do not repeat:")
        lines.extend(f"- {item}" for item in do_not_repeat[:10])
    return "\n".join(lines)


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
