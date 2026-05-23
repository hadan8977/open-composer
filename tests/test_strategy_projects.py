from __future__ import annotations

from pathlib import Path

from open_composer.dashboard.catalog import build_dashboard_catalog
from open_composer.models.project import StrategyProjectCreate, StrategyProjectRun
from open_composer.projects import (
    append_project_run,
    create_project,
    list_projects,
    load_project,
    verify_project_run,
)
from open_composer.research.artifact_state import write_project_artifact_state
from open_composer.research.iteration_controller import create_project_iteration_request


def test_create_project_writes_context_without_request(sample_workspace: Path) -> None:
    project, request = create_project(
        StrategyProjectCreate(
            name="QQQ Momentum",
            thesis="Follow QQQ momentum with bounded drawdown.",
            idea="Create a QQQ 15m momentum StrategySpec with evidence tracks.",
            template_id="qqq-momentum",
            max_rounds=3,
        ),
        sample_workspace,
    )

    assert project.project_id == "qqq-momentum"
    assert project.state == "idea"
    assert project.iteration.max_rounds == 3
    assert request is None
    assert (sample_workspace / "projects" / "qqq-momentum" / "project.yaml").exists()
    context = sample_workspace / "projects" / "qqq-momentum" / "context.md"
    assert context.exists()
    assert "Factor Quality" in context.read_text(encoding="utf-8")

    loaded = load_project("qqq-momentum", sample_workspace)
    assert loaded.name == "QQQ Momentum"
    assert list_projects(sample_workspace)[0].project_id == "qqq-momentum"


def test_dashboard_catalog_includes_project_and_legacy_fallback(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "open_composer.adapters.execution.nautilus_trader.nautilus_trader_available",
        lambda: True,
    )
    create_project(
        StrategyProjectCreate(
            name="QQQ Momentum",
            thesis="Follow QQQ momentum with bounded drawdown.",
            idea="Create a QQQ 15m momentum StrategySpec with evidence tracks.",
        ),
        sample_workspace,
        create_request=False,
    )

    catalog = build_dashboard_catalog(sample_workspace)

    assert catalog.summary.project_count == 2
    project_ids = {project.project_id for project in catalog.projects}
    assert "qqq-momentum" in project_ids
    assert "fixture-pullback-15m" in project_ids
    created = next(project for project in catalog.projects if project.project_id == "qqq-momentum")
    assert created.evidence.execution_reality.status == "unknown"
    assert created.artifact_state == {}
    fallback = next(
        project for project in catalog.projects if project.project_id == "fixture-pullback-15m"
    )
    assert fallback.imported_from_strategy is True
    assert fallback.current_spec_path == "strategy_specs/drafts/fixture_pullback_15m.yaml"


def test_dashboard_catalog_includes_project_control_state(sample_workspace: Path) -> None:
    project, _ = create_project(
        StrategyProjectCreate(
            name="Fixture Pullback",
            thesis="Use existing fixture StrategySpec.",
            current_spec_path="strategy_specs/drafts/fixture_pullback_15m.yaml",
        ),
        sample_workspace,
        create_request=False,
    )
    result = create_project_iteration_request(project.project_id, sample_workspace)

    catalog = build_dashboard_catalog(sample_workspace)
    record = next(item for item in catalog.projects if item.project_id == project.project_id)

    assert record.artifact_state["project_id"] == project.project_id
    assert record.next_minimal_actions
    assert record.latest_run_summary == {}
    assert result.iteration_plan_path == f"projects/{project.project_id}/iteration-plan-latest.json"


def test_project_run_append_verifies_missing_paths_and_logs_notification(
    sample_workspace: Path,
) -> None:
    project, _ = create_project(
        StrategyProjectCreate(
            name="QQQ Momentum",
            thesis="Follow QQQ momentum with bounded drawdown.",
            idea="Create a QQQ 15m momentum StrategySpec with evidence tracks.",
        ),
        sample_workspace,
        create_request=False,
    )
    run = StrategyProjectRun(
        round=1,
        status="ok",
        changed_paths=["reports/research/missing.md"],
        next_action="fix missing artifacts",
    )

    verified = verify_project_run(project, run, sample_workspace)
    updated, run_path = append_project_run(project.project_id, verified, sample_workspace)

    assert run_path.exists()
    assert updated.state == "blocked"
    assert "changed_paths_missing" in updated.blockers
    log_path = sample_workspace / "reports" / "notifications" / "log.jsonl"
    assert log_path.exists()
    assert "Strategy project round 1 complete" in log_path.read_text(encoding="utf-8")


def test_artifact_state_scans_project_evidence_and_financial_boundaries(
    sample_workspace: Path,
) -> None:
    project, _ = create_project(
        StrategyProjectCreate(
            name="Fixture Pullback",
            thesis="Use existing fixture StrategySpec.",
            current_spec_path="strategy_specs/drafts/fixture_pullback_15m.yaml",
        ),
        sample_workspace,
        create_request=False,
    )

    state, path = write_project_artifact_state(project, sample_workspace)

    assert path.exists()
    assert state.current_spec_path == "strategy_specs/drafts/fixture_pullback_15m.yaml"
    assert state.last_successful_step == "strategy_spec"
    assert state.evidence_status["factor_quality"].status in {
        "not_applicable",
        "unknown",
        "blocked",
    }
    assert state.evidence_status["alt_llm_evidence"].status in {
        "not_applicable",
        "unknown",
        "blocked",
    }
    assert (
        path.relative_to(sample_workspace).as_posix()
        == "projects/fixture-pullback/artifact-state.json"
    )


def test_project_run_ledger_tracks_steps_and_repeated_blocker(
    sample_workspace: Path,
) -> None:
    project, _ = create_project(
        StrategyProjectCreate(
            name="QQQ Momentum",
            thesis="Follow QQQ momentum with bounded drawdown.",
        ),
        sample_workspace,
        create_request=False,
    )
    artifact = sample_workspace / "reports" / "research" / "round-output.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"status":"blocked"}\n', encoding="utf-8")
    first = StrategyProjectRun(
        round=1,
        status="blocked",
        changed_paths=["reports/research/round-output.json"],
        step_events=[
            {
                "step_name": "promotion",
                "status": "blocked",
                "output_artifacts": ["reports/research/round-output.json"],
                "blocked_items": ["walk_forward_report:missing"],
            }
        ],
        blocker_summary={
            "trigger": "promotion_blocked",
            "failed_step": "promotion",
            "root_blockers": ["walk_forward_report:missing"],
            "next_minimal_actions": ["generate missing walk-forward evidence"],
            "artifact_refs": ["reports/research/round-output.json"],
        },
    )
    append_project_run(
        project.project_id, verify_project_run(project, first, sample_workspace), sample_workspace
    )

    project = load_project(project.project_id, sample_workspace)
    second = StrategyProjectRun(
        round=2,
        status="blocked",
        changed_paths=["reports/research/round-output.json"],
        blocker_summary={
            "trigger": "promotion_blocked",
            "failed_step": "promotion",
            "root_blockers": ["walk_forward_report:missing"],
        },
    )
    _, run_path = append_project_run(
        project.project_id,
        verify_project_run(project, second, sample_workspace),
        sample_workspace,
    )
    text = run_path.read_text(encoding="utf-8")

    assert "do not repeat unresolved blocker: walk_forward_report:missing" in text
    assert (sample_workspace / "projects" / project.project_id / "artifact-state.json").exists()


def test_iteration_controller_creates_plan_context_and_request(sample_workspace: Path) -> None:
    project, _ = create_project(
        StrategyProjectCreate(
            name="Fixture Pullback",
            thesis="Use existing fixture StrategySpec.",
            current_spec_path="strategy_specs/drafts/fixture_pullback_15m.yaml",
        ),
        sample_workspace,
        create_request=False,
    )

    result = create_project_iteration_request(
        project.project_id,
        sample_workspace,
        rounds=2,
        advice="reduce parameter count before retesting",
        requested_by="pytest",
    )

    assert result.iteration_plan_path == f"projects/{project.project_id}/iteration-plan-latest.json"
    assert result.agent_request.task_type == "strategy_optimization"
    assert (
        result.iteration_plan.artifact_state_path
        == f"projects/{project.project_id}/artifact-state.json"
    )
    assert "projects/fixture-pullback/context.md" in result.agent_request.related_paths
    context = sample_workspace / "projects" / project.project_id / "context.md"
    assert "Artifact State" in context.read_text(encoding="utf-8")
