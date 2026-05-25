from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from open_composer.dashboard.vps_deploy import (
    CommandExecutionResult,
    apply_vps_dashboard_deploy,
    build_vps_dashboard_deploy_config,
    dashboard_url_from_public_ip,
    merge_env_text,
    render_caddyfile,
    render_systemd_unit,
    write_dashboard_env,
    write_system_templates,
    write_vps_dashboard_deploy_report,
)


def test_vps_dashboard_deploy_builds_plan_without_raw_token(sample_workspace: Path) -> None:
    config = build_vps_dashboard_deploy_config(
        sample_workspace,
        public_ip="203.0.113.10",
        dashboard_token="dashboard-token-secret",
        skip_system=True,
    )
    json_path, md_path = write_vps_dashboard_deploy_report(config.plan, sample_workspace)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")

    assert config.plan.status == "ok"
    assert config.dashboard_url == "https://203.0.113.10.nip.io"
    assert config.plan.dashboard_url == "https://203.0.113.10.nip.io"
    assert config.plan.mode == "vps_dashboard"
    assert "dashboard-token-secret" not in json_path.read_text(encoding="utf-8")
    assert "dashboard-token-secret" not in markdown
    assert payload["secret_env_names"] == [
        "OPEN_COMPOSER_DASHBOARD_TOKEN",
        "OPEN_COMPOSER_DASHBOARD_AUTH_MODE",
        "OC_DASHBOARD_ALLOWED_ORIGIN",
        "OC_CLOUDFLARE_ACCESS_TEAM_DOMAIN",
        "OC_CLOUDFLARE_ACCESS_AUD",
        "OC_DASHBOARD_ALLOWED_EMAILS",
    ]


def test_vps_dashboard_deploy_apply_requires_dashboard_url(sample_workspace: Path) -> None:
    config = build_vps_dashboard_deploy_config(
        sample_workspace,
        apply=True,
        dashboard_token="dashboard-token-secret",
        skip_system=True,
    )

    assert config.plan.status == "blocked"
    blocked = {step.name for step in config.plan.steps if step.status == "blocked"}
    assert blocked == {"dashboard_url"}


def test_vps_dashboard_deploy_merges_env_without_dropping_values(
    sample_workspace: Path,
) -> None:
    env_path = sample_workspace / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=keep\nOPEN_COMPOSER_DASHBOARD_TOKEN=old\n",
        encoding="utf-8",
    )
    config = build_vps_dashboard_deploy_config(
        sample_workspace,
        public_ip="203.0.113.10",
        dashboard_token="dashboard-token-secret",
        skip_system=True,
        env_path=env_path,
    )
    write_dashboard_env(config)

    text = env_path.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY=keep" in text
    assert "OPEN_COMPOSER_DASHBOARD_TOKEN=dashboard-token-secret" in text
    assert "OC_DASHBOARD_ALLOWED_ORIGIN=https://203.0.113.10.nip.io" in text
    if os.name != "nt":
        assert oct(env_path.stat().st_mode & 0o777) == "0o600"


def test_vps_dashboard_deploy_renders_system_templates(sample_workspace: Path) -> None:
    config = build_vps_dashboard_deploy_config(
        sample_workspace,
        public_ip="203.0.113.10",
        dashboard_token="dashboard-token-secret",
        service_user="opencomposer",
        service_group="opencomposer",
    )

    unit = render_systemd_unit(config)
    caddyfile = render_caddyfile(config)
    generated_unit, generated_caddyfile = write_system_templates(config)

    assert "User=opencomposer" in unit
    assert f"WorkingDirectory={sample_workspace.as_posix()}" in unit
    assert "run oc dashboard serve --host 127.0.0.1 --port 8000" in unit
    assert "203.0.113.10.nip.io {" in caddyfile
    assert "reverse_proxy 127.0.0.1:8000" in caddyfile
    assert generated_unit.name == "open-composer-dashboard.service"
    assert generated_caddyfile.name == "Caddyfile"


def test_vps_dashboard_cloudflare_access_skips_caddy(sample_workspace: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_runner(
        args: Sequence[str],
        cwd: Path,
        input_text: str | None,
        timeout_seconds: int,
        check: bool,
        env: dict[str, str] | None,
    ) -> CommandExecutionResult:
        calls.append(list(args))
        return CommandExecutionResult(args=list(args), returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "open_composer.dashboard.vps_deploy.http_request_status",
        lambda *_args, **_kwargs: 200,
    )
    config = build_vps_dashboard_deploy_config(
        sample_workspace,
        apply=True,
        remote_access_mode="cloudflare_tunnel",
        dashboard_auth_mode="cloudflare_access",
        dashboard_url="https://dashboard.example.com",
        cloudflare_access_team_domain="https://team.cloudflareaccess.com",
        cloudflare_access_audience="aud",
        dashboard_allowed_emails="owner@example.com",
        systemd_unit_path=sample_workspace / "open-composer-dashboard.service",
        caddyfile_path=sample_workspace / "Caddyfile",
        skip_prepare=True,
        verify=True,
    )

    plan = apply_vps_dashboard_deploy(config, command_runner=fake_runner)
    env_path = sample_workspace / ".env"
    env_text = env_path.read_text(encoding="utf-8")

    assert config.caddy_enabled is False
    assert plan.status == "ok"
    assert plan.remote_access_mode == "cloudflare_tunnel"
    assert plan.caddy_enabled is False
    assert "OPEN_COMPOSER_DASHBOARD_AUTH_MODE=cloudflare_access" in env_text
    assert "OC_CLOUDFLARE_ACCESS_AUD=aud" in env_text
    assert any(step.name == "verify.dashboard_local" for step in plan.steps)
    assert not any("caddy" in part for call in calls for part in call)


def test_vps_dashboard_deploy_apply_does_not_call_vercel(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_runner(
        args: Sequence[str],
        cwd: Path,
        input_text: str | None,
        timeout_seconds: int,
        check: bool,
        env: dict[str, str] | None,
    ) -> CommandExecutionResult:
        calls.append(list(args))
        return CommandExecutionResult(args=list(args), returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "open_composer.dashboard.vps_deploy.http_request_json",
        lambda *_args, **_kwargs: {"status": "ok"},
    )
    config = build_vps_dashboard_deploy_config(
        sample_workspace,
        apply=True,
        public_ip="203.0.113.10",
        dashboard_token="dashboard-token-secret",
        skip_system=True,
        skip_prepare=True,
        verify=True,
    )

    plan = apply_vps_dashboard_deploy(config, command_runner=fake_runner)

    assert plan.status == "ok"
    assert not any("vercel" in part for call in calls for part in call)
    assert any(step.name == "verify.dashboard_health" for step in plan.steps)


def test_dashboard_url_from_public_ip_uses_nip_io() -> None:
    assert dashboard_url_from_public_ip("203.0.113.44") == "https://203.0.113.44.nip.io"


def test_vps_dashboard_merge_env_text_replaces_known_keys() -> None:
    merged = merge_env_text(
        "A=1\nOPEN_COMPOSER_DASHBOARD_TOKEN=old\n",
        {"OPEN_COMPOSER_DASHBOARD_TOKEN": "new", "OC_DASHBOARD_ALLOWED_ORIGIN": "https://x"},
    )

    assert "A=1" in merged
    assert "OPEN_COMPOSER_DASHBOARD_TOKEN=new" in merged
    assert "OC_DASHBOARD_ALLOWED_ORIGIN=https://x" in merged
