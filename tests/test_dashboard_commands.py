from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from open_composer.dashboard import build_dashboard_catalog
from open_composer.dashboard.commands import (
    DashboardCommandError,
    build_dashboard_command_plan,
    execute_dashboard_command_plan,
    resolve_dashboard_serve_root,
    write_dashboard_command_plan,
)
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_controls import load_paper_kill_switch


def _active_paper_spec(sample_workspace: Path) -> Path:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = yaml.safe_load(draft.read_text(encoding="utf-8"))
    raw["lifecycle"] = "active"
    raw["execution"]["mode"] = "paper_auto"
    raw["execution"]["broker"] = "alpaca_paper"
    active = sample_workspace / "strategy_specs" / "active" / "fixture_pullback_15m.yaml"
    active.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return active


def test_dashboard_command_plan_is_paper_only_and_bound_to_active_spec(
    sample_workspace: Path,
) -> None:
    _active_paper_spec(sample_workspace)

    plan = build_dashboard_command_plan(
        "paper.monitor.refresh",
        sample_workspace,
        reason="operator refresh",
        requested_by="dashboard",
    )
    path = write_dashboard_command_plan(plan, sample_workspace)
    events_path = sample_workspace / "reports" / "dashboard" / "commands" / "events.jsonl"

    assert path.exists()
    assert events_path.exists()
    assert plan.paper_only is True
    assert plan.real_money_allowed is False
    assert plan.confirmation_required is True
    assert plan.cli_args == ["uv", "run", "oc", "paper", "monitor"]
    assert len(plan.target_strategy_bindings) == 1
    assert plan.target_strategy_bindings[0].strategy_name == "fixture_pullback_15m"
    assert plan.target_strategy_bindings[0].execution_mode == "paper_auto"
    assert plan.target_strategy_bindings[0].broker == "alpaca_paper"
    assert plan.target_strategy_bindings[0].spec_hash


def test_dashboard_strategy_lifecycle_command_plan_is_bound_to_spec(
    sample_workspace: Path,
) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    plan = build_dashboard_command_plan(
        "strategy.approve",
        sample_workspace,
        reason="promote to approved",
        requested_by="dashboard",
        strategy_path=draft,
    )

    assert plan.paper_only is False
    assert plan.confirmation_phrase == "CONFIRM STRATEGY COMMAND"
    assert plan.cli_args == [
        "uv",
        "run",
        "oc",
        "strategy",
        "approve",
        "strategy_specs/drafts/fixture_pullback_15m.yaml",
    ]
    assert len(plan.target_strategy_bindings) == 1
    assert plan.target_strategy_bindings[0].strategy_name == "fixture_pullback_15m"
    assert plan.target_strategy_bindings[0].lifecycle == "draft"
    assert (
        plan.target_strategy_bindings[0].source_path
        == "strategy_specs/drafts/fixture_pullback_15m.yaml"
    )


def test_dashboard_strategy_draft_command_creates_draft_spec(
    sample_workspace: Path,
) -> None:
    idea = "Create a QQQ 15m breakout strategy with volume expansion and volatility filter."

    plan = build_dashboard_command_plan(
        "strategy.draft",
        sample_workspace,
        reason="draft from dashboard",
        requested_by="dashboard",
        idea=idea,
    )

    assert plan.paper_only is False
    assert plan.confirmation_phrase == "CONFIRM STRATEGY COMMAND"
    assert plan.idea == idea
    assert plan.target_strategy_bindings == []
    assert plan.cli_args == ["uv", "run", "oc", "strategy", "draft", "--idea", idea]

    write_dashboard_command_plan(plan, sample_workspace)
    result = execute_dashboard_command_plan(
        plan,
        sample_workspace,
        confirmation=plan.confirmation_phrase,
        executed_by="dashboard",
    )

    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_breakout_volume_15m.yaml"
    assert result.status == "executed"
    assert result.message == "Strategy draft created."
    assert result.output_paths == ["strategy_specs/drafts/qqq_breakout_volume_15m.yaml"]
    assert draft.exists()
    assert load_strategy_spec(draft).name == "qqq_breakout_volume_15m"


def test_dashboard_strategy_draft_requires_idea(sample_workspace: Path) -> None:
    with pytest.raises(DashboardCommandError):
        build_dashboard_command_plan("strategy.draft", sample_workspace)


def test_dashboard_strategy_approve_command_writes_lifecycle_files(
    sample_workspace: Path,
) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    plan = build_dashboard_command_plan(
        "strategy.approve",
        sample_workspace,
        reason="promote to approved",
        requested_by="dashboard",
        strategy_path=draft,
    )
    write_dashboard_command_plan(plan, sample_workspace)
    result = execute_dashboard_command_plan(
        plan,
        sample_workspace,
        confirmation=plan.confirmation_phrase,
        executed_by="dashboard",
    )

    approved = sample_workspace / "strategy_specs" / "approved" / "fixture_pullback_15m.yaml"
    assert result.status == "executed"
    assert approved.exists()
    assert load_strategy_spec(approved).lifecycle == "approved"


def test_dashboard_strategy_backtest_command_writes_reports(
    sample_workspace: Path,
) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    plan = build_dashboard_command_plan(
        "strategy.backtest.rerun",
        sample_workspace,
        reason="rerun backtest",
        requested_by="dashboard",
        strategy_path=draft,
    )
    assert plan.confirmation_phrase == "CONFIRM STRATEGY COMMAND"
    assert plan.cli_args == [
        "uv",
        "run",
        "oc",
        "backtest",
        "strategy_specs/drafts/fixture_pullback_15m.yaml",
    ]
    write_dashboard_command_plan(plan, sample_workspace)
    result = execute_dashboard_command_plan(
        plan,
        sample_workspace,
        confirmation=plan.confirmation_phrase,
        executed_by="dashboard",
    )

    assert result.status == "executed"
    assert result.message == "Strategy backtest rerun completed."
    assert any(path.startswith("reports/backtests/") for path in result.output_paths)
    assert any(path.startswith("signal_logs/") for path in result.output_paths)


def test_dashboard_strategy_validate_and_capability_commands_write_reports(
    sample_workspace: Path,
) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    validate_plan = build_dashboard_command_plan(
        "strategy.validate",
        sample_workspace,
        reason="validate spec",
        requested_by="dashboard",
        strategy_path=draft,
    )
    assert validate_plan.cli_args == [
        "uv",
        "run",
        "oc",
        "spec",
        "validate",
        "strategy_specs/drafts/fixture_pullback_15m.yaml",
    ]
    write_dashboard_command_plan(validate_plan, sample_workspace)
    validate_result = execute_dashboard_command_plan(
        validate_plan,
        sample_workspace,
        confirmation=validate_plan.confirmation_phrase,
        executed_by="dashboard",
    )
    assert validate_result.status == "executed"
    assert validate_result.message == "Strategy validated."
    assert validate_result.output_paths == [
        "reports/specs/fixture_pullback_15m.validation.json",
        "reports/specs/fixture_pullback_15m.validation.md",
    ]

    capability_plan = build_dashboard_command_plan(
        "strategy.capabilities.refresh",
        sample_workspace,
        reason="refresh capabilities",
        requested_by="dashboard",
        strategy_path=draft,
    )
    assert capability_plan.cli_args == [
        "uv",
        "run",
        "oc",
        "spec",
        "capabilities",
        "strategy_specs/drafts/fixture_pullback_15m.yaml",
    ]
    write_dashboard_command_plan(capability_plan, sample_workspace)
    capability_result = execute_dashboard_command_plan(
        capability_plan,
        sample_workspace,
        confirmation=capability_plan.confirmation_phrase,
        executed_by="dashboard",
    )
    assert capability_result.status == "executed"
    assert capability_result.message == "Strategy capability report refreshed."
    assert capability_result.output_paths == [
        "reports/capabilities/fixture_pullback_15m.json",
        "reports/capabilities/fixture_pullback_15m.md",
    ]


def test_dashboard_strategy_workflow_verify_runs_core_checks(
    sample_workspace: Path,
) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    plan = build_dashboard_command_plan(
        "strategy.workflow.verify",
        sample_workspace,
        reason="verify workflow",
        requested_by="dashboard",
        strategy_path=draft,
    )
    assert plan.confirmation_phrase == "CONFIRM STRATEGY COMMAND"
    assert plan.cli_args == ["uv", "run", "oc", "dashboard", "command-run"]
    write_dashboard_command_plan(plan, sample_workspace)
    result = execute_dashboard_command_plan(
        plan,
        sample_workspace,
        confirmation=plan.confirmation_phrase,
        executed_by="dashboard",
    )

    assert result.status == "executed"
    assert result.message == "Strategy workflow verification completed."
    assert "reports/workflows/fixture_pullback_15m.verify.json" in result.output_paths
    assert "reports/specs/fixture_pullback_15m.validation.json" in result.output_paths
    assert "reports/capabilities/fixture_pullback_15m.json" in result.output_paths
    assert any(path.startswith("reports/backtests/") for path in result.output_paths)
    assert any(path.startswith("reports/paper/readiness/") for path in result.output_paths)


def test_dashboard_strategy_scan_command_writes_reports(
    sample_workspace: Path,
) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    plan = build_dashboard_command_plan(
        "strategy.scan.rerun",
        sample_workspace,
        reason="rerun scan",
        requested_by="dashboard",
        strategy_path=draft,
    )
    assert plan.confirmation_phrase == "CONFIRM STRATEGY COMMAND"
    assert plan.cli_args == [
        "uv",
        "run",
        "oc",
        "scan",
        "strategy_specs/drafts/fixture_pullback_15m.yaml",
    ]
    write_dashboard_command_plan(plan, sample_workspace)
    result = execute_dashboard_command_plan(
        plan,
        sample_workspace,
        confirmation=plan.confirmation_phrase,
        executed_by="dashboard",
    )

    assert result.status == "executed"
    assert result.message.startswith("Strategy scan rerun completed with")
    assert any(path.startswith("reports/scans/") for path in result.output_paths)
    assert any(path.startswith("signal_logs/") for path in result.output_paths)


def test_dashboard_strategy_paper_auto_activation_blocks_on_readiness(
    sample_workspace: Path,
) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    plan = build_dashboard_command_plan(
        "strategy.activate.paper_auto",
        sample_workspace,
        reason="prepare paper automation",
        requested_by="dashboard",
        strategy_path=draft,
        data_source="sample",
    )
    write_dashboard_command_plan(plan, sample_workspace)

    with pytest.raises(DashboardCommandError):
        execute_dashboard_command_plan(
            plan,
            sample_workspace,
            confirmation=plan.confirmation_phrase,
            executed_by="dashboard",
        )

    result_path = (
        sample_workspace / "reports" / "dashboard" / "commands" / f"{plan.command_id}.result.json"
    )
    readiness_path = (
        sample_workspace
        / "reports"
        / "paper"
        / "readiness"
        / "fixture_pullback_15m.activation_candidate.json"
    )
    assert result_path.exists()
    assert readiness_path.exists()


def test_dashboard_command_execution_requires_confirmation(sample_workspace: Path) -> None:
    plan = build_dashboard_command_plan(
        "paper.status.refresh",
        sample_workspace,
        reason="status check",
    )
    write_dashboard_command_plan(plan, sample_workspace)

    try:
        execute_dashboard_command_plan(plan, sample_workspace, confirmation="wrong")
    except DashboardCommandError as exc:
        assert "Confirmation phrase did not match" in str(exc)
    else:
        raise AssertionError("dashboard command should require explicit confirmation")

    result_path = (
        sample_workspace / "reports" / "dashboard" / "commands" / f"{plan.command_id}.result.json"
    )
    assert result_path.exists()


def test_dashboard_kill_switch_command_reuses_paper_controls_and_audit(
    sample_workspace: Path,
) -> None:
    plan = build_dashboard_command_plan(
        "paper.kill_switch.enable",
        sample_workspace,
        reason="operator hold",
        requested_by="dashboard",
    )
    write_dashboard_command_plan(plan, sample_workspace)
    result = execute_dashboard_command_plan(
        plan,
        sample_workspace,
        confirmation=plan.confirmation_phrase,
        executed_by="dashboard",
    )
    catalog = build_dashboard_catalog(sample_workspace)

    assert result.status == "executed"
    assert result.result_path
    assert load_paper_kill_switch(sample_workspace).enabled is True
    assert catalog.summary.paper_kill_switch_enabled is True
    assert any(audit.kind == "paper_kill_switch" for audit in catalog.audits)


def test_dashboard_sync_commands_are_paper_only_and_write_results(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    orders_path = sample_workspace / "reports" / "paper" / "sync.jsonl"
    account_path = sample_workspace / "reports" / "paper" / "account.json"
    positions_path = sample_workspace / "reports" / "paper" / "positions.json"

    def fake_sync_orders(root: Path) -> Path:
        orders_path.parent.mkdir(parents=True, exist_ok=True)
        orders_path.write_text('{"id":"order_1","status":"accepted"}\n', encoding="utf-8")
        return orders_path

    def fake_sync_account(root: Path) -> tuple[Path, Path]:
        account_path.parent.mkdir(parents=True, exist_ok=True)
        account_path.write_text('{"equity":10000,"cash":5000,"paper":true}\n', encoding="utf-8")
        positions_path.write_text('{"positions":[]}\n', encoding="utf-8")
        return account_path, positions_path

    monkeypatch.setattr("open_composer.dashboard.commands.sync_paper_orders", fake_sync_orders)
    monkeypatch.setattr("open_composer.dashboard.commands.sync_paper_account", fake_sync_account)

    orders_plan = build_dashboard_command_plan(
        "paper.sync.orders",
        sample_workspace,
        reason="sync orders",
    )
    assert orders_plan.cli_args == ["uv", "run", "oc", "paper", "sync"]
    write_dashboard_command_plan(orders_plan, sample_workspace)
    orders_result = execute_dashboard_command_plan(
        orders_plan,
        sample_workspace,
        confirmation=orders_plan.confirmation_phrase,
    )
    assert orders_result.status == "executed"
    assert orders_result.output_paths == ["reports/paper/sync.jsonl"]

    account_plan = build_dashboard_command_plan(
        "paper.sync.account",
        sample_workspace,
        reason="sync account",
    )
    assert account_plan.cli_args == ["uv", "run", "oc", "paper", "sync-account"]
    write_dashboard_command_plan(account_plan, sample_workspace)
    account_result = execute_dashboard_command_plan(
        account_plan,
        sample_workspace,
        confirmation=account_plan.confirmation_phrase,
    )
    assert account_result.status == "executed"
    assert account_result.output_paths == [
        "reports/paper/account.json",
        "reports/paper/positions.json",
    ]


def test_dashboard_system_commands_prepare_workspace_and_refresh_readiness(
    sample_workspace: Path,
) -> None:
    prepare_plan = build_dashboard_command_plan(
        "system.prepare_workspace",
        sample_workspace,
        reason="workspace refresh",
        requested_by="dashboard",
    )
    assert prepare_plan.paper_only is False
    assert prepare_plan.confirmation_phrase == "CONFIRM SYSTEM COMMAND"
    assert prepare_plan.cli_args == ["uv", "run", "oc", "deploy", "prepare"]
    assert prepare_plan.target_strategy_bindings == []

    write_dashboard_command_plan(prepare_plan, sample_workspace)
    prepare_result = execute_dashboard_command_plan(
        prepare_plan,
        sample_workspace,
        confirmation=prepare_plan.confirmation_phrase,
        executed_by="dashboard",
    )
    assert prepare_result.status == "executed"
    assert prepare_result.message == "Workspace preparation completed."
    assert any(path.startswith("reports/deployment/") for path in prepare_result.output_paths)
    assert any(path.startswith("reports/dashboard/") for path in prepare_result.output_paths)

    readiness_plan = build_dashboard_command_plan(
        "system.readiness.refresh",
        sample_workspace,
        reason="refresh readiness",
        requested_by="dashboard",
    )
    assert readiness_plan.confirmation_phrase == "CONFIRM SYSTEM COMMAND"
    assert readiness_plan.cli_args == ["uv", "run", "oc", "readiness"]
    write_dashboard_command_plan(readiness_plan, sample_workspace)
    readiness_result = execute_dashboard_command_plan(
        readiness_plan,
        sample_workspace,
        confirmation=readiness_plan.confirmation_phrase,
        executed_by="dashboard",
    )
    assert readiness_result.status == "executed"
    assert readiness_result.message == "Deployment readiness refreshed."
    assert any(path.startswith("reports/readiness/") for path in readiness_result.output_paths)


def test_dashboard_serve_root_prefers_dist_then_static_html(sample_workspace: Path) -> None:
    dist_root = sample_workspace / "dashboard" / "dist"
    html_root = sample_workspace / "reports" / "dashboard"
    dist_root.mkdir(parents=True, exist_ok=True)
    html_root.mkdir(parents=True, exist_ok=True)

    html_path = html_root / "index.html"
    html_path.write_text("<html>static</html>", encoding="utf-8")
    assert resolve_dashboard_serve_root(sample_workspace) == html_root

    dist_path = dist_root / "index.html"
    dist_path.write_text("<html>dist</html>", encoding="utf-8")
    assert resolve_dashboard_serve_root(sample_workspace) == dist_root


def test_dashboard_serve_root_returns_none_when_bundle_missing(sample_workspace: Path) -> None:
    assert resolve_dashboard_serve_root(sample_workspace) is None
