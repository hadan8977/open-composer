from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from open_composer.remote.bootstrap import (
    CommandExecutionResult,
    apply_vps_bootstrap,
    build_vps_bootstrap_config,
    daemon_url_from_public_ip,
    hash_dashboard_password,
    merge_env_text,
    parse_vercel_deployment_url,
    render_caddyfile,
    render_systemd_unit,
    write_remote_env,
    write_system_templates,
    write_vps_bootstrap_report,
)


def test_vps_bootstrap_builds_dry_run_plan_without_raw_secret(sample_workspace: Path) -> None:
    (sample_workspace / "dashboard").mkdir()
    config = build_vps_bootstrap_config(
        sample_workspace,
        vercel_token="vercel_token_secret",
        public_ip="203.0.113.10",
        dashboard_password="dashboard-secret",
        skip_system=True,
    )
    write_system_templates(config)
    json_path, md_path = write_vps_bootstrap_report(config.plan, sample_workspace)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")

    assert config.plan.status == "ok"
    assert config.daemon_url == "https://203.0.113.10.sslip.io"
    assert config.vercel_origin == "https://open-composer-dashboard.vercel.app"
    assert "dashboard-secret" not in json_path.read_text(encoding="utf-8")
    assert "vercel_token_secret" not in json_path.read_text(encoding="utf-8")
    assert "dashboard-secret" not in markdown
    assert "vercel_token_secret" not in markdown
    assert payload["secret_env_names"] == [
        "OC_REMOTE_BASE_URL",
        "OC_REMOTE_SHARED_SECRET",
        "OC_DASHBOARD_PASSWORD_HASH",
        "OC_DASHBOARD_SESSION_SECRET",
        "OC_DASHBOARD_OWNER",
        "OC_DASHBOARD_ALLOWED_ORIGIN",
        "OC_DASHBOARD_SESSION_TTL_SECONDS",
    ]


def test_vps_bootstrap_blocks_without_daemon_url_or_token(sample_workspace: Path) -> None:
    (sample_workspace / "dashboard").mkdir()
    config = build_vps_bootstrap_config(
        sample_workspace,
        dashboard_password="dashboard-secret",
        skip_system=True,
    )

    assert config.plan.status == "warning"
    blocked = {step.name for step in config.plan.steps if step.status == "blocked"}
    warnings = {step.name for step in config.plan.steps if step.status == "warning"}
    assert not blocked
    assert "daemon_url" in warnings
    assert "vercel" in warnings


def test_vps_bootstrap_apply_blocks_without_daemon_url_or_token(sample_workspace: Path) -> None:
    (sample_workspace / "dashboard").mkdir()
    config = build_vps_bootstrap_config(
        sample_workspace,
        apply=True,
        dashboard_password="dashboard-secret",
        skip_system=True,
    )

    assert config.plan.status == "blocked"
    blocked = {step.name for step in config.plan.steps if step.status == "blocked"}
    assert {"daemon_url", "vercel"}.issubset(blocked)


def test_vps_bootstrap_can_skip_vercel_for_local_daemon_only(sample_workspace: Path) -> None:
    config = build_vps_bootstrap_config(
        sample_workspace,
        public_ip="203.0.113.20",
        dashboard_password="dashboard-secret",
        skip_vercel=True,
        skip_system=True,
    )

    assert config.plan.status == "ok"
    assert any(step.name == "vercel" and step.status == "skipped" for step in config.plan.steps)


def test_vps_bootstrap_hashes_dashboard_password_with_pbkdf2() -> None:
    hashed = hash_dashboard_password("secret", iterations=10, salt="abc")

    assert hashed.startswith("pbkdf2-sha256:10:abc:")
    assert len(hashed.rsplit(":", 1)[-1]) == 64


def test_vps_bootstrap_merges_env_without_dropping_existing_values(sample_workspace: Path) -> None:
    env_path = sample_workspace / ".env"
    env_path.write_text("OPENAI_API_KEY=keep\nOC_REMOTE_SHARED_SECRET=old\n", encoding="utf-8")
    config = build_vps_bootstrap_config(
        sample_workspace,
        public_ip="203.0.113.10",
        dashboard_password="dashboard-secret",
        skip_vercel=True,
        skip_system=True,
        env_path=env_path,
    )
    write_remote_env(config)

    text = env_path.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY=keep" in text
    assert "OC_REMOTE_SHARED_SECRET=old" in text
    assert "OC_REMOTE_BASE_URL=https://203.0.113.10.sslip.io" in text
    assert "OC_DASHBOARD_ALLOWED_ORIGIN=https://open-composer-dashboard.vercel.app" in text
    assert oct(env_path.stat().st_mode & 0o777) == "0o600"


def test_merge_env_text_replaces_known_keys_and_appends_missing() -> None:
    merged = merge_env_text(
        "A=1\nOC_REMOTE_BASE_URL=https://old.example\n",
        {"OC_REMOTE_BASE_URL": "https://new.example", "OC_DASHBOARD_OWNER": "owner"},
    )

    assert "A=1" in merged
    assert "OC_REMOTE_BASE_URL=https://new.example" in merged
    assert "OC_DASHBOARD_OWNER=owner" in merged


def test_vps_bootstrap_renders_system_templates(sample_workspace: Path) -> None:
    config = build_vps_bootstrap_config(
        sample_workspace,
        public_ip="203.0.113.10",
        dashboard_password="dashboard-secret",
        skip_vercel=True,
        service_user="opencomposer",
        service_group="opencomposer",
    )

    unit = render_systemd_unit(config)
    caddyfile = render_caddyfile(config.daemon_url or "")

    assert "User=opencomposer" in unit
    assert f"WorkingDirectory={sample_workspace.as_posix()}" in unit
    assert "uv run oc remote serve --host 127.0.0.1 --port 8787" in unit
    assert "203.0.113.10.sslip.io {" in caddyfile
    assert "reverse_proxy 127.0.0.1:8787" in caddyfile


def test_daemon_url_from_public_ip_uses_sslip() -> None:
    assert daemon_url_from_public_ip("203.0.113.44") == "https://203.0.113.44.sslip.io"


def test_parse_vercel_deployment_url_from_cli_output() -> None:
    assert (
        parse_vercel_deployment_url("Queued\nhttps://open-composer-dashboard.vercel.app\n")
        == "https://open-composer-dashboard.vercel.app"
    )


def test_vps_bootstrap_apply_uses_vercel_env_and_redacts_token(sample_workspace: Path) -> None:
    calls: list[tuple[list[str], str | None]] = []
    (sample_workspace / "dashboard").mkdir()
    (sample_workspace / "dashboard" / "package.json").write_text(
        '{"name":"@open-composer/dashboard"}\n',
        encoding="utf-8",
    )

    def fake_runner(
        args: Sequence[str],
        cwd: Path,
        input_text: str | None,
        timeout_seconds: int,
        check: bool,
        env: dict[str, str] | None,
    ) -> CommandExecutionResult:
        calls.append((list(args), input_text))
        stdout = "https://open-composer-dashboard.vercel.app\n" if "deploy" in args else ""
        return CommandExecutionResult(args=list(args), returncode=0, stdout=stdout, stderr="")

    config = build_vps_bootstrap_config(
        sample_workspace,
        apply=True,
        vercel_token="vercel_token_secret",
        public_ip="203.0.113.10",
        dashboard_password="dashboard-secret",
        skip_system=True,
        skip_prepare=True,
        vercel_command=["vercel"],
    )

    plan = apply_vps_bootstrap(config, command_runner=fake_runner)

    assert plan.status == "ok"
    assert plan.deployment_url == "https://open-composer-dashboard.vercel.app"
    assert any(call[0][:2] == ["vercel", "link"] for call in calls)
    env_adds = [call for call in calls if call[0][:3] == ["vercel", "env", "add"]]
    assert {call[0][3] for call in env_adds} >= {
        "OC_REMOTE_BASE_URL",
        "OC_REMOTE_SHARED_SECRET",
        "OC_DASHBOARD_PASSWORD_HASH",
    }
    assert any(call[1] == "https://203.0.113.10.sslip.io\n" for call in env_adds)
    assert "vercel_token_secret" not in (
        sample_workspace / "reports" / "deployment" / "vps-bootstrap" / "plan.json"
    ).read_text(encoding="utf-8")
