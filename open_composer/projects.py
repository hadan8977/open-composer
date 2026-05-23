from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from open_composer.config import ensure_dir, project_root
from open_composer.models.project import (
    ProjectEvidence,
    ProjectEvidenceItem,
    ProjectEvidenceStatus,
    ProjectState,
    QueueCommand,
    QueueCommandKind,
    QueueCommandVia,
    StrategyProject,
    StrategyProjectCreate,
    StrategyProjectRun,
    TraceAgent,
    TraceEntry,
)
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.notifications import safe_dispatch_notification
from open_composer.storage import append_jsonl, write_json

_ABSOLUTE_PATH_PATTERN = re.compile(r"^([/\\]|[A-Za-z]:[\\/])")
_SLUG_SAFE_PATTERN = re.compile(r"[^a-z0-9]+")
_PROJECT_FILE = "project.yaml"
DEFAULT_PROJECT_CONTEXT_BYTES = 32 * 1024
MAX_PROJECT_CONTEXT_BYTES = 128 * 1024


def project_dir(root: Path | None = None) -> Path:
    base = root or project_root()
    return base / "projects"


def project_path(project_id: str, root: Path | None = None) -> Path:
    return project_dir(root) / project_id / _PROJECT_FILE


def create_project(
    payload: StrategyProjectCreate,
    root: Path | None = None,
    *,
    create_request: bool = False,
) -> tuple[StrategyProject, QueueCommand | None]:
    base = root or project_root()
    project_id = unique_project_id(
        slugify(payload.name or payload.thesis or "strategy-project"), base
    )
    current_spec_path = (
        _validate_relative_path(base, payload.current_spec_path)
        if payload.current_spec_path
        else None
    )
    project = StrategyProject(
        project_id=project_id,
        name=payload.name,
        state="draft" if current_spec_path else "idea",
        thesis=payload.thesis.strip() or payload.idea.strip(),
        current_spec_path=current_spec_path,
        next_action="generate_initial_strategy_spec"
        if current_spec_path is None
        else "run_initial_research",
        iteration={"max_rounds": payload.max_rounds},
        tags=payload.tags,
    )
    write_project(project, base)
    write_project_context(
        project,
        base,
        task=payload.idea or payload.thesis,
        template_id=payload.template_id,
    )
    request: QueueCommand | None = None
    if create_request:
        request = append_queue(
            project.project_id,
            kind="continue",
            body=project_agent_prompt(project, payload.idea or payload.thesis),
            via="cli",
            metadata={
                "requested_by": payload.requested_by,
                "task_type": "research",
                "title": f"Build strategy project: {project.name}",
                "related_paths": [
                    f"projects/{project.project_id}/project.yaml",
                    f"projects/{project.project_id}/context.md",
                    *([current_spec_path] if current_spec_path else []),
                ],
            },
            root=base,
        )
    return project, request


def load_project(project_id: str, root: Path | None = None) -> StrategyProject:
    path = project_path(project_id, root)
    if not path.exists():
        raise FileNotFoundError(f"strategy project not found: {project_id}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"strategy project must be a mapping: {path}")
    return StrategyProject.model_validate(raw)


def list_projects(root: Path | None = None) -> list[StrategyProject]:
    base = root or project_root()
    root_dir = project_dir(base)
    if not root_dir.exists():
        return []
    projects: list[StrategyProject] = []
    for path in sorted(root_dir.glob(f"*/{_PROJECT_FILE}")):
        try:
            projects.append(
                StrategyProject.model_validate(yaml.safe_load(path.read_text("utf-8")) or {})
            )
        except (OSError, ValueError, yaml.YAMLError):
            continue
    return sorted(
        projects, key=lambda item: (item.archived, _state_rank(item.state), item.name.lower())
    )


def write_project(project: StrategyProject, root: Path | None = None) -> Path:
    base = root or project_root()
    project.updated_at = datetime.now(UTC)
    path = project_path(project.project_id, base)
    ensure_dir(path.parent)
    path.write_text(
        yaml.safe_dump(project.model_dump(mode="json"), sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    return path


def append_project_run(
    project_id: str,
    run: StrategyProjectRun,
    root: Path | None = None,
) -> tuple[StrategyProject, Path]:
    base = root or project_root()
    project = load_project(project_id, base)
    _augment_repeated_blockers(base, project, run)
    run_path = base / "projects" / project_id / "runs" / f"round-{run.round:03d}.yaml"
    ensure_dir(run_path.parent)
    run_path.write_text(
        yaml.safe_dump(run.model_dump(mode="json"), sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    project.latest_run_path = _relpath(run_path, base)
    project.iteration.current_round = max(project.iteration.current_round, run.round)
    project.blockers = _unique_strings(
        [
            *run.blockers,
            *(run.blocker_summary.root_blockers if run.blocker_summary else []),
        ]
    )
    if run.next_action:
        project.next_action = run.next_action
    if run.status in {"blocked", "failed"}:
        project.state = "blocked"
    elif project.state in {"idea", "draft", "researching"}:
        project.state = "iterating"
    write_project(project, base)
    try:
        from open_composer.research.artifact_state import write_project_artifact_state

        write_project_artifact_state(project, base)
    except (OSError, ValueError, yaml.YAMLError):  # pragma: no cover - artifact-state best effort
        pass
    safe_dispatch_notification(
        kind="system_alert",
        severity="warn" if run.status in {"blocked", "failed"} else "info",
        title=f"Strategy project round {run.round} complete",
        body=f"{project.name}: {run.status}; next_action={project.next_action}",
        metadata={
            "project_id": project.project_id,
            "run_path": project.latest_run_path,
            "status": run.status,
            "blockers": run.blockers,
        },
        root=base,
    )
    return project, run_path


def update_project_state(
    project_id: str,
    state: ProjectState,
    root: Path | None = None,
    *,
    next_action: str | None = None,
    blockers: list[str] | None = None,
) -> StrategyProject:
    base = root or project_root()
    project = load_project(project_id, base)
    project.state = state
    if next_action is not None:
        project.next_action = next_action
    if blockers is not None:
        project.blockers = blockers
    write_project(project, base)
    return project


def write_project_context(
    project: StrategyProject,
    root: Path | None = None,
    *,
    task: str = "",
    template_id: str | None = None,
    max_bytes: int | None = DEFAULT_PROJECT_CONTEXT_BYTES,
) -> Path:
    base = root or project_root()
    path = base / "projects" / project.project_id / "context.md"
    ensure_dir(path.parent)
    lines = [
        f"# Strategy Project Context: {project.name}",
        "",
        (
            "Open Composer is a personal AI strategy workbench. StrategySpec is the source "
            "of truth for strategy behavior."
        ),
        (
            "Use repo Harness, reports, capabilities, and paper readiness gates. Do not "
            "treat sample data or worker self-report as paper-ready evidence."
        ),
        "",
        "## Project",
        f"- project_id: `{project.project_id}`",
        f"- state: `{project.state}`",
        f"- thesis: {project.thesis or 'n/a'}",
        f"- current_spec_path: `{project.current_spec_path or 'n/a'}`",
        f"- latest_run_path: `{project.latest_run_path or 'n/a'}`",
        f"- next_action: `{project.next_action}`",
        "",
        "## Evidence Tracks",
        _context_evidence_line("Factor Quality", project.evidence.factor_quality),
        _context_evidence_line("Execution Reality", project.evidence.execution_reality),
        _context_evidence_line("Alt/LLM Evidence", project.evidence.alt_llm_evidence),
        "",
        "## Iteration",
        f"- current_round: {project.iteration.current_round}",
        f"- max_rounds: {project.iteration.max_rounds}",
        f"- mode: `{project.iteration.mode}`",
        f"- stop_conditions: {', '.join(project.iteration.stop_conditions)}",
        "",
        "## Artifact State",
        *_context_artifact_state_lines(base, project),
        "",
        "## Latest Queue Commands",
        *_context_queue_lines(base, project),
        "",
        "## Latest Trace",
        *_context_trace_lines(base, project),
        "",
        "## Latest Run Ledger",
        *_context_latest_run_lines(base, project),
        "",
        "## Current Task",
        task.strip() or "Continue according to the project next_action.",
    ]
    if template_id:
        lines.append(f"- template_id: `{template_id}`")
    text = "\n".join(lines).rstrip() + "\n"
    if max_bytes is not None:
        text = _truncate_utf8(text, min(max_bytes, MAX_PROJECT_CONTEXT_BYTES))
    path.write_text(text, encoding="utf-8")
    return path


def queue_path(project_id: str, root: Path | None = None) -> Path:
    base = root or project_root()
    return base / "projects" / project_id / "queue.jsonl"


def trace_path(project_id: str, root: Path | None = None) -> Path:
    base = root or project_root()
    return base / "projects" / project_id / "trace.jsonl"


def append_queue(
    project_id: str,
    kind: QueueCommandKind,
    body: str,
    root: Path | None = None,
    *,
    via: QueueCommandVia = "cli",
    metadata: dict[str, Any] | None = None,
    from_actor: str = "user",
) -> QueueCommand:
    base = root or project_root()
    load_project(project_id, base)
    command = QueueCommand(
        id=f"q_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
        from_actor=from_actor,
        via=via,
        kind=kind,
        body=body.strip(),
        metadata=metadata or {},
    )
    append_jsonl(queue_path(project_id, base), [command.model_dump(mode="json", by_alias=True)])
    return command


def read_queue(project_id: str, root: Path | None = None) -> list[QueueCommand]:
    return [
        QueueCommand.model_validate(raw)
        for raw in _read_jsonl_mappings(queue_path(project_id, root))
    ]


def unconsumed_queue(project_id: str, root: Path | None = None) -> list[QueueCommand]:
    return [command for command in read_queue(project_id, root) if command.consumed_at is None]


def mark_queue_command_consumed(
    project_id: str,
    command_id: str,
    root: Path | None = None,
) -> None:
    base = root or project_root()
    path = queue_path(project_id, base)
    commands = read_queue(project_id, base)
    updated: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for command in commands:
        if command.id == command_id and command.consumed_at is None:
            command.consumed_at = now
        updated.append(command.model_dump(mode="json", by_alias=True))
    ensure_dir(path.parent)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in updated),
        encoding="utf-8",
    )


def append_trace(
    project_id: str,
    *,
    agent: TraceAgent = "system",
    operation: str,
    queue_command_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    root: Path | None = None,
) -> TraceEntry:
    base = root or project_root()
    load_project(project_id, base)
    entry = TraceEntry(
        span_id=f"sp_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
        agent=agent,
        operation=operation,
        queue_command_id=queue_command_id,
        metadata=metadata or {},
    )
    append_jsonl(trace_path(project_id, base), [entry])
    return entry


def read_trace_tail(
    project_id: str,
    n: int = 20,
    root: Path | None = None,
) -> list[TraceEntry]:
    rows = _read_jsonl_mappings(trace_path(project_id, root))
    return [TraceEntry.model_validate(raw) for raw in rows[-n:]]


def project_agent_prompt(project: StrategyProject, idea: str) -> str:
    task = idea.strip() or project.thesis
    return "\n".join(
        [
            f"Work on Open Composer StrategyProject `{project.project_id}`.",
            f"Project file: projects/{project.project_id}/project.yaml",
            f"Context file: projects/{project.project_id}/context.md",
            "",
            "Goal:",
            task,
            "",
            "Required workflow:",
            "1. Keep StrategySpec as the source of truth for strategy behavior.",
            "2. Create or update a draft StrategySpec first, then validate it.",
            "3. Generate research artifacts and reports before recommending promotion.",
            (
                "4. Update Project Evidence for Factor Quality, Execution Reality, and "
                "Alt/LLM Evidence."
            ),
            (
                "5. Do not mark paper_ready unless deterministic gates and paper readiness "
                "evidence support it."
            ),
        ]
    )


def build_project_from_strategy(
    strategy_name: str,
    *,
    strategy_path: str | None,
    lifecycle: str,
    factors: list[str],
    llm_or_alt: bool,
    paper_ready: bool | None,
    root: Path | None = None,
) -> StrategyProject:
    base = root or project_root()
    project_id = slugify(strategy_name)
    evidence = ProjectEvidence(
        factor_quality=ProjectEvidenceItem(
            status="unknown" if factors else "not_applicable",
            summary="No project-level Factor Quality artifact has been linked yet."
            if factors
            else "No explicit factor diagnostics are required for this legacy single-spec view.",
        ),
        execution_reality=ProjectEvidenceItem(
            status="unknown",
            summary="No project-level Execution Reality artifact has been linked yet.",
        ),
        alt_llm_evidence=ProjectEvidenceItem(
            status="unknown" if llm_or_alt else "not_applicable",
            summary=(
                "LLM or alternative-data evidence is required before claiming independent "
                "contribution."
            )
            if llm_or_alt
            else "No LLM, news, event, macro, or alternative-data factor is declared.",
        ),
    )
    gate = {
        "workflow_pass": lifecycle in {"approved", "active"},
        "paper_ready_pass": paper_ready,
        "status": "unknown",
    }
    state: ProjectState
    if lifecycle == "active":
        state = "active_paper" if paper_ready else "candidate"
    elif lifecycle == "approved":
        state = "candidate"
    elif lifecycle == "retired":
        state = "retired"
    else:
        state = "draft"
    return StrategyProject(
        project_id=project_id,
        name=strategy_name,
        state=state,
        thesis="Imported from legacy StrategySpec catalog.",
        current_spec_path=_validate_relative_path(base, strategy_path) if strategy_path else None,
        gate_summary=gate,
        evidence=evidence,
        next_action="create_strategy_project_file"
        if not (base / "projects" / project_id / _PROJECT_FILE).exists()
        else "review_project",
    )


def verify_project_run(
    project: StrategyProject,
    run: StrategyProjectRun,
    root: Path | None = None,
) -> StrategyProjectRun:
    base = root or project_root()
    expected_paths = _run_artifact_paths(run)
    missing_paths = [path for path in expected_paths if not (base / path).exists()]
    spec_status = "unknown"
    if project.current_spec_path:
        try:
            load_strategy_spec(base / project.current_spec_path)
            spec_status = "ok"
        except Exception as exc:  # pragma: no cover - defensive summary path
            spec_status = f"blocked: {exc}"
    mismatch = False
    worker_gate = _gate_from_mapping(run.worker_claim.get("gate_summary"))
    verified_gate = _gate_from_mapping(run.verified.get("gate_summary"))
    if worker_gate and verified_gate:
        mismatch = worker_gate != verified_gate
    artifact_status = "ok" if not missing_paths else "blocked"
    blockers = [
        *run.blockers,
        *(run.blocker_summary.root_blockers if run.blocker_summary else []),
    ]
    if missing_paths:
        blockers.append("changed_paths_missing")
    if mismatch:
        blockers.append("worker_self_report_mismatch")
    run.verified = {
        **run.verified,
        "artifact_check": artifact_status,
        "missing_paths": missing_paths,
        "spec_status": spec_status,
        "mismatch": mismatch,
    }
    run.blockers = _unique_strings(blockers)
    if run.blockers and run.status == "ok":
        run.status = "blocked"
    return run


def slugify(value: str) -> str:
    normalized = _SLUG_SAFE_PATTERN.sub("-", value.strip().lower()).strip("-")
    return normalized[:64].strip("-") or "strategy-project"


def unique_project_id(base_slug: str, root: Path) -> str:
    candidate = base_slug
    while (root / "projects" / candidate / _PROJECT_FILE).exists():
        candidate = f"{base_slug}-{uuid4().hex[:6]}"
    return candidate


def _state_rank(state: ProjectState) -> int:
    order = {
        "blocked": 0,
        "paper_review": 1,
        "active_paper": 2,
        "iterating": 3,
        "researching": 4,
        "candidate": 5,
        "draft": 6,
        "idea": 7,
        "retired": 8,
    }
    return order[state]


def _validate_relative_path(root: Path, value: str | None) -> str | None:
    if value is None:
        return None
    path = value.strip()
    if not path:
        return None
    if _ABSOLUTE_PATH_PATTERN.match(path):
        raise ValueError("project paths must be workspace-relative")
    candidate = Path(path)
    if candidate.is_absolute():
        raise ValueError("project paths must be workspace-relative")
    resolved = (root / candidate).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
        raise ValueError("project paths must stay within the workspace")
    return candidate.as_posix()


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _context_evidence_line(name: str, item: ProjectEvidenceItem) -> str:
    artifact = item.artifact_path or "n/a"
    blockers = ", ".join(item.blockers) if item.blockers else "none"
    return (
        f"- {name}: `{item.status}`; artifact=`{artifact}`; "
        f"blockers={blockers}; summary={item.summary}"
    )


def _context_artifact_state_lines(base: Path, project: StrategyProject) -> list[str]:
    path = base / "projects" / project.project_id / "artifact-state.json"
    raw = _read_json_mapping(path)
    if not raw:
        return ["- artifact_state_path: `n/a`", "- last_successful_step: `unknown`"]
    evidence = raw.get("evidence_status")
    evidence_lines: list[str] = []
    if isinstance(evidence, dict):
        for key in ("factor_quality", "execution_reality", "alt_llm_evidence"):
            value = evidence.get(key)
            if isinstance(value, dict):
                evidence_lines.append(f"- evidence.{key}: `{value.get('status', 'unknown')}`")
            else:
                evidence_lines.append(f"- evidence.{key}: `{value or 'unknown'}`")
    return [
        f"- artifact_state_path: `projects/{project.project_id}/artifact-state.json`",
        f"- last_successful_step: `{raw.get('last_successful_step', 'unknown')}`",
        f"- blocked_items: {_join_short_list(raw.get('blocked_items'))}",
        f"- warning_items: {_join_short_list(raw.get('warning_items'))}",
        f"- next_minimal_actions: {_join_short_list(raw.get('next_minimal_actions'))}",
        f"- do_not_repeat: {_join_short_list(raw.get('do_not_repeat'))}",
        *evidence_lines,
    ]


def _context_queue_lines(base: Path, project: StrategyProject) -> list[str]:
    commands = read_queue(project.project_id, base)[-5:]
    if not commands:
        return ["- queue: `empty`"]
    lines: list[str] = []
    for command in commands:
        body = command.body.replace("\n", " ").strip()
        if len(body) > 160:
            body = body[:157] + "..."
        consumed = "consumed" if command.consumed_at else "pending"
        lines.append(
            f"- [{command.ts.isoformat()}] `{command.kind}` {consumed}: {body or '(empty)'}"
        )
    return lines


def _context_trace_lines(base: Path, project: StrategyProject) -> list[str]:
    entries = read_trace_tail(project.project_id, 5, base)
    if not entries:
        return ["- trace: `empty`"]
    lines: list[str] = []
    for entry in entries:
        lines.append(
            f"- [{entry.ts.isoformat()}] `{entry.agent}` `{entry.operation}` "
            f"queue={entry.queue_command_id or 'n/a'}"
        )
    return lines


def _context_latest_run_lines(base: Path, project: StrategyProject) -> list[str]:
    if not project.latest_run_path:
        return ["- latest_run: `n/a`"]
    run = _read_yaml_mapping(base / project.latest_run_path)
    if not run:
        return [f"- latest_run: `{project.latest_run_path}`", "- latest_run_status: `unreadable`"]
    blocker_summary = run.get("blocker_summary")
    lines = [
        f"- latest_run: `{project.latest_run_path}`",
        f"- status: `{run.get('status', 'unknown')}`",
        f"- round: {run.get('round', 'unknown')}",
        f"- blockers: {_join_short_list(run.get('blockers'))}",
        f"- next_action: `{run.get('next_action', '') or 'n/a'}`",
    ]
    if isinstance(blocker_summary, dict):
        lines.extend(
            [
                f"- failed_step: `{blocker_summary.get('failed_step', 'unknown')}`",
                f"- root_blockers: {_join_short_list(blocker_summary.get('root_blockers'))}",
                (
                    "- next_minimal_actions: "
                    f"{_join_short_list(blocker_summary.get('next_minimal_actions'))}"
                ),
                f"- do_not_repeat: {_join_short_list(blocker_summary.get('do_not_repeat'))}",
            ]
        )
    return lines


def _gate_from_mapping(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    keys = ("workflow_pass", "research_pass", "llm_contribution_pass", "paper_ready_pass")
    return {key: value.get(key) for key in keys if key in value}


def write_project_json(project: StrategyProject, root: Path | None = None) -> Path:
    base = root or project_root()
    return write_json(base / "projects" / project.project_id / "project.json", project)


def evidence_status_from_gate(status: str | None) -> ProjectEvidenceStatus:
    if status == "ok":
        return "ok"
    if status == "blocked":
        return "blocked"
    if status == "warning":
        return "warning"
    return "unknown"


def load_project_run_summary(path: Path) -> StrategyProjectRun:
    raw = _read_yaml_mapping(path)
    if not raw:
        raise ValueError(f"project run summary is empty or unreadable: {path}")
    return StrategyProjectRun.model_validate(raw)


def _run_artifact_paths(run: StrategyProjectRun) -> list[str]:
    paths: list[str] = []
    paths.extend(run.changed_paths)
    for event in run.step_events:
        paths.extend(event.output_artifacts)
    if run.blocker_summary:
        paths.extend(run.blocker_summary.artifact_refs)
    return _unique_strings(paths)


def _augment_repeated_blockers(
    base: Path, project: StrategyProject, run: StrategyProjectRun
) -> None:
    if not run.blocker_summary or not run.blocker_summary.root_blockers:
        return
    previous = _latest_run_with_blocker_summary(base, project)
    if previous is None or previous.blocker_summary is None:
        return
    previous_blockers = set(previous.blocker_summary.root_blockers)
    repeated = [
        blocker for blocker in run.blocker_summary.root_blockers if blocker in previous_blockers
    ]
    if not repeated:
        return
    additions = [f"do not repeat unresolved blocker: {blocker}" for blocker in repeated]
    run.blocker_summary.do_not_repeat = _unique_strings(
        [*run.blocker_summary.do_not_repeat, *additions]
    )


def _latest_run_with_blocker_summary(
    base: Path, project: StrategyProject
) -> StrategyProjectRun | None:
    run_dir = base / "projects" / project.project_id / "runs"
    if not run_dir.exists():
        return None
    for path in sorted(run_dir.glob("round-*.yaml"), reverse=True):
        try:
            run = load_project_run_summary(path)
        except ValueError:
            continue
        if run.blocker_summary:
            return run
    return None


def _read_json_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _read_jsonl_mappings(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                rows.append(raw)
    return rows


def _truncate_utf8(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    marker = "\n\n[context truncated to byte budget]\n"
    budget = max(max_bytes - len(marker.encode("utf-8")), 0)
    return encoded[:budget].decode("utf-8", errors="ignore").rstrip() + marker


def _join_short_list(value: object, *, limit: int = 4) -> str:
    if not isinstance(value, list):
        return "none"
    values = [str(item) for item in value if str(item).strip()]
    if not values:
        return "none"
    suffix = "" if len(values) <= limit else f", +{len(values) - limit} more"
    return "; ".join(values[:limit]) + suffix


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
