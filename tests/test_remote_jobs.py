from __future__ import annotations

from pathlib import Path

import pytest

from open_composer.dashboard.commands import (
    build_dashboard_command_plan,
    write_dashboard_command_plan,
)
from open_composer.remote.jobs import RemoteJobManager
from open_composer.remote.schemas import (
    REMOTE_STRATEGY_DOUBLE_CONFIRMATION,
    RemoteCommandRunRequest,
)


def _write_plan(sample_workspace: Path, action: str, **kwargs) -> Path:
    plan = build_dashboard_command_plan(
        action,  # type: ignore[arg-type]
        sample_workspace,
        requested_by="dashboard",
        reason="remote test",
        **kwargs,
    )
    return write_dashboard_command_plan(plan, sample_workspace)


def test_remote_green_command_runs_as_job(sample_workspace: Path) -> None:
    plan_path = _write_plan(
        sample_workspace,
        "strategy.validate",
        strategy_path="strategy_specs/drafts/fixture_pullback_15m.yaml",
    )
    manager = RemoteJobManager(sample_workspace, autostart=False)
    record = manager.create_command_job(
        RemoteCommandRunRequest(
            plan_path=str(plan_path.relative_to(sample_workspace)),
            confirm="CONFIRM STRATEGY COMMAND",
        ),
        actor="owner",
    )

    completed = manager.run_job(record.job_id)

    assert completed.status == "executed"
    assert completed.backup_manifest_path is None
    assert completed.result_path
    assert (sample_workspace / "reports" / "dashboard" / "jobs" / f"{record.job_id}.json").exists()
    assert (sample_workspace / "reports" / "dashboard" / "jobs" / f"{record.job_id}.log").exists()


def test_remote_yellow_command_creates_backup(sample_workspace: Path) -> None:
    plan_path = _write_plan(
        sample_workspace,
        "strategy.backtest.rerun",
        strategy_path="strategy_specs/drafts/fixture_pullback_15m.yaml",
    )
    manager = RemoteJobManager(sample_workspace, autostart=False)
    record = manager.create_command_job(
        RemoteCommandRunRequest(
            plan_path=str(plan_path.relative_to(sample_workspace)),
            confirm="CONFIRM STRATEGY COMMAND",
        ),
        actor="owner",
    )

    completed = manager.run_job(record.job_id)

    assert completed.status == "executed"
    assert completed.backup_manifest_path
    assert (sample_workspace / completed.backup_manifest_path).exists()


def test_remote_red_command_requires_double_confirmation(sample_workspace: Path) -> None:
    plan_path = _write_plan(
        sample_workspace,
        "strategy.approve",
        strategy_path="strategy_specs/drafts/fixture_pullback_15m.yaml",
    )
    manager = RemoteJobManager(sample_workspace, autostart=False)
    record = manager.create_command_job(
        RemoteCommandRunRequest(
            plan_path=str(plan_path.relative_to(sample_workspace)),
            confirm="CONFIRM STRATEGY COMMAND",
        ),
        actor="owner",
    )

    completed = manager.run_job(record.job_id)

    assert completed.status == "blocked"
    assert "double confirmation" in completed.message
    assert not (
        sample_workspace / "strategy_specs" / "approved" / "fixture_pullback_15m.yaml"
    ).exists()


def test_remote_red_command_creates_backup_and_executes(sample_workspace: Path) -> None:
    plan_path = _write_plan(
        sample_workspace,
        "strategy.approve",
        strategy_path="strategy_specs/drafts/fixture_pullback_15m.yaml",
    )
    manager = RemoteJobManager(sample_workspace, autostart=False)
    record = manager.create_command_job(
        RemoteCommandRunRequest(
            plan_path=str(plan_path.relative_to(sample_workspace)),
            confirm="CONFIRM STRATEGY COMMAND",
            double_confirm=REMOTE_STRATEGY_DOUBLE_CONFIRMATION,
        ),
        actor="owner",
    )

    completed = manager.run_job(record.job_id)

    assert completed.status == "executed"
    assert completed.backup_manifest_path
    assert (sample_workspace / completed.backup_manifest_path).exists()
    assert any(
        path.name.endswith(".before.yaml")
        for path in (sample_workspace / "reports" / "backups" / "remote" / record.job_id).glob(
            "*.yaml"
        )
    )
    assert (sample_workspace / "strategy_specs" / "approved" / "fixture_pullback_15m.yaml").exists()


def test_remote_paper_auto_activation_keeps_readiness_gate(sample_workspace: Path) -> None:
    plan_path = _write_plan(
        sample_workspace,
        "strategy.activate.paper_auto",
        strategy_path="strategy_specs/drafts/fixture_pullback_15m.yaml",
        data_source="sample",
    )
    manager = RemoteJobManager(sample_workspace, autostart=False)
    record = manager.create_command_job(
        RemoteCommandRunRequest(
            plan_path=str(plan_path.relative_to(sample_workspace)),
            confirm="CONFIRM STRATEGY COMMAND",
            double_confirm=REMOTE_STRATEGY_DOUBLE_CONFIRMATION,
        ),
        actor="owner",
    )

    completed = manager.run_job(record.job_id)

    assert completed.status == "blocked"
    assert completed.backup_manifest_path
    assert "sample" in completed.message or "readiness" in completed.message
    assert not (
        sample_workspace / "strategy_specs" / "active" / "fixture_pullback_15m.yaml"
    ).exists()


def test_remote_job_rejects_plan_path_traversal(sample_workspace: Path) -> None:
    manager = RemoteJobManager(sample_workspace, autostart=False)

    with pytest.raises(Exception, match="plan_path"):
        manager.create_command_job(
            RemoteCommandRunRequest(
                plan_path="../README.md",
                confirm="CONFIRM STRATEGY COMMAND",
            ),
            actor="owner",
        )
