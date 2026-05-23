from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.models.project import StrategyProjectCreate
from open_composer.projects import (
    append_queue,
    append_trace,
    create_project,
    mark_queue_command_consumed,
    read_queue,
    read_trace_tail,
    unconsumed_queue,
)


def test_project_queue_and_trace_lifecycle(sample_workspace: Path) -> None:
    project, _ = create_project(
        StrategyProjectCreate(name="Queue Test", thesis="Exercise queue contract."),
        sample_workspace,
    )
    command = append_queue(
        project.project_id,
        kind="continue",
        body="Retest after reducing parameter count.",
        root=sample_workspace,
        via="cli",
    )
    trace = append_trace(
        project.project_id,
        agent="system",
        operation="queued_for_agent",
        queue_command_id=command.id,
        root=sample_workspace,
    )

    assert command.id.startswith("q_")
    assert read_queue(project.project_id, sample_workspace)[0].id == command.id
    assert unconsumed_queue(project.project_id, sample_workspace)[0].id == command.id
    assert read_trace_tail(project.project_id, 1, sample_workspace)[0].span_id == trace.span_id
    assert (sample_workspace / "projects" / project.project_id / "queue.jsonl").exists()
    assert (sample_workspace / "projects" / project.project_id / "trace.jsonl").exists()

    mark_queue_command_consumed(project.project_id, command.id, sample_workspace)
    assert unconsumed_queue(project.project_id, sample_workspace) == []


def test_project_queue_rejects_missing_project(sample_workspace: Path) -> None:
    with pytest.raises(FileNotFoundError):
        append_queue("missing", kind="continue", body="x", root=sample_workspace)


def test_project_context_has_larger_bounded_budget(sample_workspace: Path) -> None:
    project, _ = create_project(
        StrategyProjectCreate(
            name="Context Budget",
            thesis="Exercise context compiler budget.",
            idea="x" * 80_000,
        ),
        sample_workspace,
    )

    context_path = sample_workspace / "projects" / project.project_id / "context.md"

    assert context_path.stat().st_size <= 32 * 1024
    assert context_path.stat().st_size > 1024


def test_project_continue_cli_uses_backend_without_duplicate_queue(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    monkeypatch.setenv("OPEN_COMPOSER_AGENT_BACKEND", "file_queue")
    project, _ = create_project(
        StrategyProjectCreate(name="CLI Backend", thesis="Exercise backend dispatch."),
        sample_workspace,
    )

    result = CliRunner().invoke(
        app,
        [
            "project",
            "continue",
            project.project_id,
            "--advice",
            "keep the same session context",
        ],
        catch_exceptions=False,
    )

    commands = read_queue(project.project_id, sample_workspace)
    assert result.exit_code == 0
    assert len(commands) == 1
    assert commands[0].kind == "continue"
    assert "queue command written" in result.output
