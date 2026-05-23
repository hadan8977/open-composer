from __future__ import annotations

import http.client
import threading
from pathlib import Path

import pytest
from conftest import assert_no_windows_paths

from open_composer.dashboard.commands import DashboardCommandError, resolve_dashboard_serve_root
from open_composer.dashboard.server import (
    build_dashboard_catalog_payload,
    build_dashboard_command_plan_payload,
    build_dashboard_command_run_payload,
    build_dashboard_environment_payload,
    build_dashboard_health_payload,
    build_notification_config_payload,
    build_notification_log_payload,
    build_notification_test_payload,
    build_project_create_payload,
    build_project_state_payload,
    create_dashboard_server,
    dashboard_request_authorized,
)
from open_composer.strategy_lifecycle import activate_strategy


def test_dashboard_server_creates_and_updates_strategy_project(sample_workspace: Path) -> None:
    response = build_project_create_payload(
        sample_workspace,
        {
            "name": "QQQ Momentum",
            "thesis": "Follow QQQ momentum with bounded drawdown.",
            "idea": "Create a QQQ 15m momentum StrategySpec with evidence tracks.",
            "max_rounds": 4,
        },
    )

    assert response["project_path"] == "projects/qqq-momentum/project.yaml"
    assert response["context_path"] == "projects/qqq-momentum/context.md"
    assert "agent_request_path" not in response

    state = build_project_state_payload(sample_workspace, "qqq-momentum", {"action": "stop"})
    assert state["project"]["iteration"]["user_requested_stop"] is True
    assert state["project"]["iteration"]["stop_reason"] == "user_requested_stop"

    continued = build_project_state_payload(
        sample_workspace,
        "qqq-momentum",
        {"action": "continue", "direction": "reduce parameters and retest"},
    )
    assert continued["project"]["state"] == "iterating"
    assert continued["queue_command"]["kind"] == "continue"
    assert continued["queue_path"] == "projects/qqq-momentum/queue.jsonl"
    assert continued["trace_path"] == "projects/qqq-momentum/trace.jsonl"
    assert continued["context_path"] == "projects/qqq-momentum/context.md"
    assert continued["artifact_state_path"] == "projects/qqq-momentum/artifact-state.json"


def test_dashboard_server_payloads_expose_health_catalog_and_command_api(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    active = activate_strategy(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
    )
    assert active.exists()

    serve_root = sample_workspace / "reports" / "dashboard"
    serve_root.mkdir(parents=True, exist_ok=True)
    (serve_root / "index.html").write_text("<html><body>dashboard</body></html>", encoding="utf-8")

    assert resolve_dashboard_serve_root(sample_workspace) == serve_root

    health = build_dashboard_health_payload(sample_workspace, serve_root)
    catalog = build_dashboard_catalog_payload(sample_workspace)

    assert health["status"] == "ok"
    assert health["dashboard_root"] == sample_workspace.as_posix()
    assert health["serve_root"] == serve_root.as_posix()
    assert health["auth_required"] is False
    assert catalog["summary"]["strategy_count"] >= 1
    environment = build_dashboard_environment_payload(sample_workspace, serve_root)
    assert environment["status"] in {"ok", "warning", "blocked"}
    assert environment["auth_required"] is False
    assert any(section["section"] == "model" for section in environment["sections"])
    assert any(
        item["name"] == "ALPACA_PAPER"
        for section in environment["sections"]
        for item in section["items"]
    )

    plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "paper.status.refresh",
            "reason": "server api test",
            "requested_by": "pytest",
        },
    )

    assert plan["action"] == "paper.status.refresh"
    assert plan["confirmation_phrase"] == "CONFIRM PAPER COMMAND"
    assert plan["plan_path"]

    result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": plan["plan_path"],
            "confirm": plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert result["status"] == "executed"
    assert result["message"] == "Paper status refreshed."
    assert result["result_path"]

    sync_path = sample_workspace / "reports" / "paper" / "sync.jsonl"

    def fake_sync_orders(root: Path) -> Path:
        sync_path.parent.mkdir(parents=True, exist_ok=True)
        sync_path.write_text('{"id":"order_1","status":"accepted"}\n', encoding="utf-8")
        return sync_path

    monkeypatch.setattr("open_composer.dashboard.commands.sync_paper_orders", fake_sync_orders)
    sync_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "paper.sync.orders",
            "reason": "server sync test",
            "requested_by": "pytest",
        },
    )
    assert sync_plan["action"] == "paper.sync.orders"

    sync_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": sync_plan["plan_path"],
            "confirm": sync_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert sync_result["status"] == "executed"
    assert sync_result["message"] == "Paper orders synced."
    assert sync_result["output_paths"] == ["reports/paper/sync.jsonl"]

    system_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "system.prepare_workspace",
            "reason": "server deploy test",
            "requested_by": "pytest",
        },
    )
    assert system_plan["action"] == "system.prepare_workspace"
    assert system_plan["confirmation_phrase"] == "CONFIRM SYSTEM COMMAND"
    system_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": system_plan["plan_path"],
            "confirm": system_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert system_result["status"] == "executed"
    assert system_result["message"] == "Workspace preparation completed."
    assert any(path.startswith("reports/deployment/") for path in system_result["output_paths"])

    readiness_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "system.readiness.refresh",
            "reason": "server readiness test",
            "requested_by": "pytest",
        },
    )
    assert readiness_plan["action"] == "system.readiness.refresh"
    readiness_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": readiness_plan["plan_path"],
            "confirm": readiness_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert readiness_result["status"] == "executed"
    assert readiness_result["message"] == "Deployment readiness refreshed."
    assert any(path.startswith("reports/readiness/") for path in readiness_result["output_paths"])

    draft_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "strategy.draft",
            "reason": "server draft test",
            "requested_by": "pytest",
            "idea": (
                "Create a QQQ 15m breakout strategy with volume expansion and volatility filter."
            ),
        },
    )
    assert draft_plan["action"] == "strategy.draft"
    assert draft_plan["confirmation_phrase"] == "CONFIRM STRATEGY COMMAND"
    draft_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": draft_plan["plan_path"],
            "confirm": draft_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert draft_result["status"] == "executed"
    assert draft_result["message"] == "Strategy draft created."
    assert draft_result["output_paths"] == ["strategy_specs/drafts/qqq_breakout_volume_15m.yaml"]

    validate_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "strategy.validate",
            "reason": "server validate test",
            "requested_by": "pytest",
            "strategy_path": "strategy_specs/drafts/fixture_pullback_15m.yaml",
        },
    )
    assert validate_plan["action"] == "strategy.validate"
    validate_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": validate_plan["plan_path"],
            "confirm": validate_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert validate_result["status"] == "executed"
    assert validate_result["output_paths"] == [
        "reports/specs/fixture_pullback_15m.validation.json",
        "reports/specs/fixture_pullback_15m.validation.md",
    ]

    capability_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "strategy.capabilities.refresh",
            "reason": "server capability test",
            "requested_by": "pytest",
            "strategy_path": "strategy_specs/drafts/fixture_pullback_15m.yaml",
        },
    )
    assert capability_plan["action"] == "strategy.capabilities.refresh"
    capability_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": capability_plan["plan_path"],
            "confirm": capability_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert capability_result["status"] == "executed"
    assert capability_result["message"] == "Strategy capability report refreshed."

    workflow_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "strategy.workflow.verify",
            "reason": "server workflow test",
            "requested_by": "pytest",
            "strategy_path": "strategy_specs/drafts/fixture_pullback_15m.yaml",
        },
    )
    assert workflow_plan["action"] == "strategy.workflow.verify"
    workflow_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": workflow_plan["plan_path"],
            "confirm": workflow_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert workflow_result["status"] == "executed"
    assert workflow_result["message"] == "Strategy workflow verification completed."
    assert any(path.startswith("reports/workflows/") for path in workflow_result["output_paths"])

    account_path = sample_workspace / "reports" / "paper" / "account.json"
    positions_path = sample_workspace / "reports" / "paper" / "positions.json"

    def fake_sync_account(root: Path) -> tuple[Path, Path]:
        account_path.parent.mkdir(parents=True, exist_ok=True)
        account_path.write_text(
            '{"generated_at":"2026-01-02T15:45:00Z","equity":10000,"cash":5000,'
            '"buying_power":8000,"portfolio_value":10000,"status":"ACTIVE","paper":true}\n',
            encoding="utf-8",
        )
        positions_path.write_text('{"positions":[]}\n', encoding="utf-8")
        return account_path, positions_path

    monkeypatch.setattr("open_composer.dashboard.commands.sync_paper_account", fake_sync_account)
    account_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "paper.sync.account",
            "reason": "server account test",
            "requested_by": "pytest",
        },
    )
    account_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": account_plan["plan_path"],
            "confirm": account_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert account_result["status"] == "executed"
    assert account_result["message"] == "Paper account and positions synced."
    assert account_result["output_paths"] == [
        "reports/paper/account.json",
        "reports/paper/positions.json",
    ]

    lifecycle_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "strategy.approve",
            "reason": "server lifecycle test",
            "requested_by": "pytest",
            "strategy_path": "strategy_specs/drafts/fixture_pullback_15m.yaml",
        },
    )
    assert lifecycle_plan["action"] == "strategy.approve"
    assert lifecycle_plan["confirmation_phrase"] == "CONFIRM STRATEGY COMMAND"
    lifecycle_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": lifecycle_plan["plan_path"],
            "confirm": lifecycle_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert lifecycle_result["status"] == "executed"
    assert (sample_workspace / "strategy_specs" / "approved" / "fixture_pullback_15m.yaml").exists()

    rerun_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "strategy.backtest.rerun",
            "reason": "server backtest test",
            "requested_by": "pytest",
            "strategy_path": "strategy_specs/drafts/fixture_pullback_15m.yaml",
        },
    )
    assert rerun_plan["action"] == "strategy.backtest.rerun"
    assert rerun_plan["confirmation_phrase"] == "CONFIRM STRATEGY COMMAND"
    rerun_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": rerun_plan["plan_path"],
            "confirm": rerun_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert rerun_result["status"] == "executed"
    assert rerun_result["message"] == "Strategy backtest rerun completed."
    assert any(path.startswith("reports/backtests/") for path in rerun_result["output_paths"])

    scan_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "strategy.scan.rerun",
            "reason": "server scan test",
            "requested_by": "pytest",
            "strategy_path": "strategy_specs/drafts/fixture_pullback_15m.yaml",
        },
    )
    assert scan_plan["action"] == "strategy.scan.rerun"
    scan_result = build_dashboard_command_run_payload(
        sample_workspace,
        {
            "plan_path": scan_plan["plan_path"],
            "confirm": scan_plan["confirmation_phrase"],
            "executed_by": "pytest",
        },
    )
    assert scan_result["status"] == "executed"
    assert scan_result["message"].startswith("Strategy scan rerun completed with")
    assert any(path.startswith("reports/scans/") for path in scan_result["output_paths"])

    paper_auto_plan = build_dashboard_command_plan_payload(
        sample_workspace,
        {
            "action": "strategy.activate.paper_auto",
            "reason": "server paper automation test",
            "requested_by": "pytest",
            "strategy_path": "strategy_specs/drafts/fixture_pullback_15m.yaml",
            "data_source": "sample",
        },
    )
    assert paper_auto_plan["action"] == "strategy.activate.paper_auto"
    with pytest.raises(DashboardCommandError):
        build_dashboard_command_run_payload(
            sample_workspace,
            {
                "plan_path": paper_auto_plan["plan_path"],
                "confirm": paper_auto_plan["confirmation_phrase"],
                "executed_by": "pytest",
            },
        )
    assert (
        sample_workspace
        / "reports"
        / "paper"
        / "readiness"
        / "fixture_pullback_15m.activation_candidate.json"
    ).exists()

    assert_no_windows_paths(
        [
            health,
            catalog,
            plan,
            result,
            sync_plan,
            sync_result,
            system_plan,
            system_result,
            readiness_plan,
            readiness_result,
            draft_plan,
            draft_result,
            validate_plan,
            validate_result,
            capability_plan,
            capability_result,
            workflow_plan,
            workflow_result,
            account_plan,
            account_result,
            lifecycle_plan,
            lifecycle_result,
            rerun_plan,
            rerun_result,
            scan_plan,
            scan_result,
            paper_auto_plan,
        ]
    )

    with pytest.raises(
        DashboardCommandError, match="plan_path must stay within the current workspace"
    ):
        build_dashboard_command_run_payload(
            sample_workspace,
            {
                "plan_path": str(Path("/tmp/outside-plan.json")),
                "confirm": "CONFIRM PAPER COMMAND",
                "executed_by": "pytest",
            },
        )


def test_dashboard_notification_payloads(sample_workspace: Path) -> None:
    config = build_notification_config_payload(sample_workspace)
    assert config["config_path"] == "config/notifications.yaml"
    assert config["log_path"] == "reports/notifications/log.jsonl"
    assert config["telegram_bot_token_present"] is False

    test_payload = build_notification_test_payload(
        sample_workspace,
        {"kind": "system_alert", "severity": "info", "dry_run": True},
    )
    assert test_payload["notification"]["kind"] == "system_alert"
    assert any(item["channel"] == "log_only" for item in test_payload["notification"]["deliveries"])

    log = build_notification_log_payload(sample_workspace, limit=10)
    assert log["notifications"][-1]["title"] == "Open Composer notification test"


def test_dashboard_api_token_auth_gate(sample_workspace: Path) -> None:
    serve_root = sample_workspace / "reports" / "dashboard"
    serve_root.mkdir(parents=True, exist_ok=True)

    health = build_dashboard_health_payload(sample_workspace, serve_root, auth_required=True)

    assert health["auth_required"] is True
    assert dashboard_request_authorized({}, None) is True
    assert dashboard_request_authorized({}, "secret") is False
    assert (
        dashboard_request_authorized(
            {"X-Open-Composer-Token": "secret"},
            "secret",
        )
        is True
    )
    assert dashboard_request_authorized({"Authorization": "Bearer secret"}, "secret") is True
    assert dashboard_request_authorized({"Authorization": "Bearer wrong"}, "secret") is False


def test_dashboard_cors_blocks_external_origin_when_unconfigured(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OC_DASHBOARD_ALLOWED_ORIGIN", raising=False)
    status, headers = _dashboard_health_request(
        sample_workspace,
        origin="https://evil.example",
    )

    assert status == 200
    assert "access-control-allow-origin" not in headers
    assert headers["vary"] == "Origin"


def test_dashboard_cors_allows_localhost_origin_when_unconfigured(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OC_DASHBOARD_ALLOWED_ORIGIN", raising=False)
    status, headers = _dashboard_health_request(sample_workspace, origin="__LOCALHOST__")

    assert status == 200
    assert headers["access-control-allow-origin"].startswith("http://127.0.0.1:")
    assert headers["vary"] == "Origin"


def test_dashboard_cors_allows_configured_origin(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OC_DASHBOARD_ALLOWED_ORIGIN", "https://dashboard.example")
    status, headers = _dashboard_health_request(
        sample_workspace,
        origin="https://dashboard.example",
    )

    assert status == 200
    assert headers["access-control-allow-origin"] == "https://dashboard.example"


def _dashboard_health_request(
    sample_workspace: Path,
    *,
    origin: str,
) -> tuple[int, dict[str, str]]:
    serve_root = sample_workspace / "reports" / "dashboard"
    serve_root.mkdir(parents=True, exist_ok=True)
    (serve_root / "index.html").write_text("<html><body>dashboard</body></html>", encoding="utf-8")

    server = create_dashboard_server(sample_workspace, host="127.0.0.1", port=0, api_token=None)
    port = int(server.server_address[1])
    request_origin = f"http://127.0.0.1:{port}" if origin == "__LOCALHOST__" else origin
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request(
            "GET",
            "/api/dashboard/health",
            headers={"Origin": request_origin},
        )
        response = connection.getresponse()
        response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, headers
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
