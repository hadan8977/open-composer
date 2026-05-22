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


def test_create_project_writes_context_and_agent_request(sample_workspace: Path) -> None:
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
    assert request is not None
    assert (sample_workspace / "projects" / "qqq-momentum" / "project.yaml").exists()
    context = sample_workspace / "projects" / "qqq-momentum" / "context.md"
    assert context.exists()
    assert "Factor Quality" in context.read_text(encoding="utf-8")
    assert (sample_workspace / "reports" / "agent_requests" / f"{request.request_id}.json").exists()

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
    fallback = next(
        project for project in catalog.projects if project.project_id == "fixture-pullback-15m"
    )
    assert fallback.imported_from_strategy is True
    assert fallback.current_spec_path == "strategy_specs/drafts/fixture_pullback_15m.yaml"


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
