from __future__ import annotations

import http.client
import threading
from pathlib import Path

import pytest
import yaml
from conftest import assert_no_windows_paths

import open_composer.dashboard.auth as dashboard_auth
from open_composer.dashboard.commands import DashboardCommandError, resolve_dashboard_serve_root
from open_composer.dashboard.server import (
    DASHBOARD_CLI_PARITY,
    build_activity_trace_payload,
    build_dashboard_catalog_payload,
    build_dashboard_command_plan_payload,
    build_dashboard_command_run_payload,
    build_dashboard_environment_payload,
    build_dashboard_health_payload,
    build_draft_payload,
    build_llm_factor_prompt_payload,
    build_llm_factor_prompt_update_payload,
    build_notification_config_payload,
    build_notification_log_payload,
    build_notification_test_payload,
    build_paper_alerts_payload,
    build_paper_kill_switch_payload,
    build_paper_monitor_refresh_payload,
    build_project_context_payload,
    build_project_create_payload,
    build_project_detail_payload,
    build_project_queue_create_payload,
    build_project_queue_payload,
    build_project_state_payload,
    build_project_trace_payload,
    build_settings_agent_backend_payload,
    build_settings_agent_backend_update_payload,
    build_settings_capabilities_payload,
    build_settings_capabilities_test_payload,
    build_strategy_action_payload,
    build_strategy_detail_payload,
    build_strategy_drawdown_payload,
    build_strategy_equity_payload,
    build_strategy_runs_payload,
    build_strategy_signals_payload,
    build_strategy_spec_diff_payload,
    build_strategy_spec_payload,
    build_templates_payload,
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


def test_dashboard_step3_project_queue_trace_and_context_api(sample_workspace: Path) -> None:
    created = build_project_create_payload(
        sample_workspace,
        {
            "name": "Queue Test",
            "thesis": "Exercise dashboard queue.",
            "idea": "QQQ 15m queue test.",
        },
    )
    project_id = created["project"]["project_id"]

    queued = build_project_queue_create_payload(
        sample_workspace,
        project_id,
        {"kind": "advice", "body": "try a tighter stop", "metadata": {"source": "pytest"}},
    )

    assert queued["status"] == "queued"
    assert queued["queue_command_id"].startswith("q_")
    assert (sample_workspace / queued["queue_path"]).exists()

    detail = build_project_detail_payload(sample_workspace, project_id)
    context = build_project_context_payload(sample_workspace, project_id)
    queue = build_project_queue_payload(sample_workspace, project_id)
    trace = build_project_trace_payload(sample_workspace, project_id)

    assert detail["project"]["project_id"] == project_id
    assert "Strategy Project Context" in context["text"]
    assert queue["pending_count"] >= 1
    assert any(entry["metadata"].get("via") == "dashboard" for entry in trace["entries"])


def test_dashboard_step3_strategy_read_and_action_api(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    detail = build_strategy_detail_payload(sample_workspace, "fixture_pullback_15m")
    spec = build_strategy_spec_payload(sample_workspace, "fixture_pullback_15m")
    diff = build_strategy_spec_diff_payload(sample_workspace, "fixture_pullback_15m")
    runs = build_strategy_runs_payload(sample_workspace, "fixture_pullback_15m")
    signals = build_strategy_signals_payload(sample_workspace, "fixture_pullback_15m")
    equity = build_strategy_equity_payload(sample_workspace, "fixture_pullback_15m")
    drawdown = build_strategy_drawdown_payload(sample_workspace, "fixture_pullback_15m")

    assert detail["strategy"]["strategy_id"] == "fixture_pullback_15m"
    assert spec["active_path"] == "strategy_specs/drafts/fixture_pullback_15m.yaml"
    assert "diff" in diff
    assert runs["runs"] == []
    assert signals["signals"] == []
    assert isinstance(equity["points"], list)
    assert isinstance(drawdown["points"], list)

    queued = build_strategy_action_payload(
        sample_workspace,
        "fixture_pullback_15m",
        "evidence",
        {"reason": "pytest evidence"},
    )
    assert queued["status"] == "queued"
    assert queued["project_id"] == "fixture-pullback-15m"
    assert (sample_workspace / "projects" / queued["project_id"] / "queue.jsonl").exists()

    promoted = build_strategy_action_payload(
        sample_workspace,
        str(spec_path),
        "promote",
        {"reason": "pytest promote"},
    )
    assert promoted["status"] == "executed"
    assert promoted["output_paths"] == ["strategy_specs/approved/fixture_pullback_15m.yaml"]


def test_dashboard_llm_factor_prompt_trace_and_window_materialize(
    sample_workspace: Path,
) -> None:
    spec_path = _write_dashboard_llm_factor_spec(sample_workspace)
    factor_lab_path = (
        sample_workspace / "reports" / "research" / "qqq_news_regime_15m-factor-lab.json"
    )
    factor_lab_path.write_text(
        '{"status":"warning","factor_metrics":[{"name":"news_regime_score",'
        '"rank_ic":0.12,"rolling_rank_ic_mean":0.08,"rolling_rank_ic_min":-0.02,'
        '"observations":40,"coverage_pct":100,"flags":["sample_data"]}]}',
        encoding="utf-8",
    )

    prompt = build_llm_factor_prompt_payload(
        sample_workspace,
        "qqq_news_regime_15m",
        "news_regime_score",
    )
    updated = build_llm_factor_prompt_update_payload(
        sample_workspace,
        "qqq_news_regime_15m",
        "news_regime_score",
        {"prompt": prompt["prompt"] + "\nUse stricter point-in-time evidence."},
    )
    detail = build_strategy_detail_payload(sample_workspace, "qqq_news_regime_15m")
    queued = build_strategy_action_payload(
        sample_workspace,
        str(spec_path),
        "materialize",
        {"factor": "news_regime_score", "window_bars": 200},
    )
    trace = build_activity_trace_payload(sample_workspace, "limit=20&kind=dashboard")

    assert updated["needs_rematerialize"] is True
    assert updated["prompt_hash"].startswith("sha256:")
    assert detail["llm_factors"][0]["factor_lab"]["rank_ic"] == 0.12
    assert detail["llm_factors"][0]["prompt_hash"].startswith("sha256:")
    assert queued["status"] == "queued"
    assert "--window-bars 200" in (
        sample_workspace / "projects" / queued["project_id"] / "queue.jsonl"
    ).read_text(encoding="utf-8")
    assert any(row["operation"] == "dashboard_edit_llm_factor_prompt" for row in trace["entries"])


def test_dashboard_step3_build_settings_and_paper_api(sample_workspace: Path) -> None:
    templates = build_templates_payload()
    assert {item["strategy_kind"] for item in templates["templates"]} >= {
        "pure_quant",
        "quant_with_llm_review",
        "quant_with_llm_factor",
        "router",
    }

    draft = build_draft_payload(
        sample_workspace,
        {
            "strategy_kind": "pure_quant",
            "name": "QQQ Build Test",
            "thesis": "Build from dashboard.",
            "idea": "Create a QQQ 15m breakout strategy with volume expansion.",
            "max_rounds": 3,
        },
    )
    assert draft["status"] == "created"
    assert draft["spec_path"].startswith("strategy_specs/drafts/")
    assert (sample_workspace / draft["queue_path"]).exists()

    capabilities = build_settings_capabilities_payload(sample_workspace)
    assert capabilities["capabilities"]
    evaluated = build_settings_capabilities_test_payload(sample_workspace, {})
    assert evaluated["status"] == "executed"
    assert (sample_workspace / "reports" / "capabilities" / "evaluation.json").exists()

    backend = build_settings_agent_backend_payload(sample_workspace)
    assert backend["backend"] in {"file_queue", "codex_sdk"}
    switched = build_settings_agent_backend_update_payload(
        sample_workspace,
        {"backend": "file_queue"},
    )
    assert switched["status"] == "updated"
    assert "OPEN_COMPOSER_AGENT_BACKEND=file_queue" in (sample_workspace / ".env").read_text(
        encoding="utf-8"
    )

    kill = build_paper_kill_switch_payload(
        sample_workspace,
        {"enabled": True, "reason": "pytest stop"},
    )
    assert kill["kill_switch"]["enabled"] is True
    assert (sample_workspace / "reports" / "paper" / "kill_switch_events.jsonl").exists()
    monitor = build_paper_monitor_refresh_payload(sample_workspace, {})
    assert monitor["status"] == "executed"
    alerts = build_paper_alerts_payload(sample_workspace)
    assert "alerts" in alerts


def test_dashboard_step3_cli_parity_table_has_core_actions() -> None:
    assert DASHBOARD_CLI_PARITY["POST /api/build/draft"] == "oc strategy draft"
    assert DASHBOARD_CLI_PARITY["POST /api/projects/{id}/queue"] == "oc project continue"
    assert DASHBOARD_CLI_PARITY["POST /api/strategies/{name}/actions/materialize"] == (
        "oc feature materialize"
    )
    assert DASHBOARD_CLI_PARITY["POST /api/paper/kill-switch"] == "oc paper kill-switch"


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


def test_dashboard_cloudflare_access_auth_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OC_DASHBOARD_ALLOWED_EMAILS", "owner@example.com")
    monkeypatch.setenv("OC_CLOUDFLARE_ACCESS_TEAM_DOMAIN", "https://team.cloudflareaccess.com")
    monkeypatch.setenv("OC_CLOUDFLARE_ACCESS_AUD", "aud")
    monkeypatch.setattr(
        dashboard_auth,
        "decode_cloudflare_access_jwt",
        lambda assertion: {"email": assertion},
    )

    assert (
        dashboard_request_authorized(
            {"Cf-Access-Jwt-Assertion": "owner@example.com"},
            None,
            auth_mode="cloudflare_access",
        )
        is True
    )
    assert (
        dashboard_request_authorized(
            {"Cf-Access-Jwt-Assertion": "other@example.com"},
            None,
            auth_mode="cloudflare_access",
        )
        is False
    )
    assert dashboard_request_authorized({}, None, auth_mode="cloudflare_access") is False
    assert (
        dashboard_request_authorized(
            {"Authorization": "Bearer secret"},
            "secret",
            auth_mode="cloudflare_access_or_token",
        )
        is True
    )


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


def _write_dashboard_llm_factor_spec(sample_workspace: Path) -> Path:
    prompt = sample_workspace / "prompts" / "examples" / "news_regime_score.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("Return score and confidence as JSON.\n", encoding="utf-8")
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["name"] = "qqq_news_regime_15m"
    raw["factors"] = {
        "news_regime_score": {
            "source": "llm_feature",
            "field": "score",
            "default": 0.0,
            "description": "Materialized LLM score.",
            "input_view": "news_window_v1",
            "input_view_version": 1,
            "prompt_template_path": "prompts/examples/news_regime_score.md",
            "output_schema": {
                "type": "object",
                "required": ["score", "confidence"],
                "properties": {
                    "score": {"type": "number"},
                    "confidence": {"type": "number"},
                },
            },
            "model_ref": "local_test_stub",
        }
    }
    raw["entry"] = {"all": ["news_regime_score > 0"]}
    raw["exit"] = {"any": ["news_regime_score < 0"]}
    target = sample_workspace / "strategy_specs" / "drafts" / "qqq_news_regime_15m.yaml"
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return target
