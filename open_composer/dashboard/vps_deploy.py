from __future__ import annotations

import getpass
import ipaddress
import json
import os
import secrets
import shlex
import shutil
import subprocess
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import ensure_dir
from open_composer.storage import write_json

DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8000
DEFAULT_PUBLIC_HTTPS_PORT = 443
FALLBACK_PUBLIC_HTTPS_PORT = 8443
DEFAULT_SYSTEMD_UNIT_PATH = Path("/etc/systemd/system/open-composer-dashboard.service")
DEFAULT_CADDYFILE_PATH = Path("/etc/caddy/Caddyfile")
REPORT_DIR = Path("reports/deployment/vps-dashboard")
SECRET_PLACEHOLDER = "<redacted>"

DASHBOARD_ENV_KEYS = [
    "OPEN_COMPOSER_DASHBOARD_TOKEN",
    "OC_DASHBOARD_ALLOWED_ORIGIN",
]


class VpsDashboardDeployError(RuntimeError):
    pass


class VpsDashboardDeployStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["ok", "warning", "blocked", "skipped"]
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    suggested_actions: list[str] = Field(default_factory=list)
    output_paths: list[str] = Field(default_factory=list)


class VpsDashboardDeployPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_root: str
    apply: bool
    ready: bool
    status: Literal["ok", "warning", "blocked"]
    mode: Literal["vps_dashboard"] = "vps_dashboard"
    dashboard_url: str | None = None
    dashboard_bind: str = f"{DEFAULT_DASHBOARD_HOST}:{DEFAULT_DASHBOARD_PORT}"
    env_path: str
    systemd_unit_path: str
    caddyfile_path: str
    generated_systemd_unit_path: str
    generated_caddyfile_path: str
    generated_token_path: str | None = None
    token_available: bool = False
    verify_enabled: bool = True
    secret_env_names: list[str] = Field(default_factory=list)
    steps: list[VpsDashboardDeployStep] = Field(default_factory=list)
    report_json_path: str | None = None
    report_markdown_path: str | None = None


class VpsDashboardDeployConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    root: Path
    apply: bool = False
    dashboard_url: str | None = None
    dashboard_host: str = DEFAULT_DASHBOARD_HOST
    dashboard_port: int = DEFAULT_DASHBOARD_PORT
    service_user: str
    service_group: str
    env_path: Path
    systemd_unit_path: Path = DEFAULT_SYSTEMD_UNIT_PATH
    caddyfile_path: Path = DEFAULT_CADDYFILE_PATH
    use_sudo: bool = False
    skip_system: bool = False
    skip_prepare: bool = False
    verify: bool = True
    dashboard_token: str
    generated_dashboard_token: bool = False
    dashboard_env: dict[str, str]
    plan: VpsDashboardDeployPlan


@dataclass(frozen=True)
class CommandExecutionResult:
    args: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


CommandRunner = Callable[
    [Sequence[str], Path, str | None, int, bool, dict[str, str] | None], CommandExecutionResult
]


def build_vps_dashboard_deploy_config(
    root: Path,
    *,
    apply: bool = False,
    dashboard_url: str | None = None,
    public_ip: str | None = None,
    dashboard_host: str = DEFAULT_DASHBOARD_HOST,
    dashboard_port: int = DEFAULT_DASHBOARD_PORT,
    dashboard_token: str | None = None,
    rotate_token: bool = False,
    service_user: str | None = None,
    service_group: str | None = None,
    env_path: Path | None = None,
    systemd_unit_path: Path = DEFAULT_SYSTEMD_UNIT_PATH,
    caddyfile_path: Path = DEFAULT_CADDYFILE_PATH,
    use_sudo: bool = False,
    skip_system: bool = False,
    skip_prepare: bool = False,
    verify: bool = True,
) -> VpsDashboardDeployConfig:
    base = root.resolve()
    env_file = env_path or base / ".env"
    existing_env = read_env_values(env_file)
    resolved_url = resolve_dashboard_url(
        dashboard_url=dashboard_url,
        public_ip=public_ip,
        prefer_fallback_port=apply and not dashboard_url and public_ip is not None,
    )
    token = resolve_dashboard_token(
        existing_token=existing_env.get("OPEN_COMPOSER_DASHBOARD_TOKEN"),
        provided_token=dashboard_token,
        rotate_token=rotate_token,
    )
    generated_token = bool(
        token
        and dashboard_token is None
        and (rotate_token or not existing_env.get("OPEN_COMPOSER_DASHBOARD_TOKEN"))
    )
    env = {
        "OPEN_COMPOSER_DASHBOARD_TOKEN": token,
        "OC_DASHBOARD_ALLOWED_ORIGIN": resolved_url
        or existing_env.get("OC_DASHBOARD_ALLOWED_ORIGIN", ""),
    }
    generated_unit_path = base / REPORT_DIR / "open-composer-dashboard.service"
    generated_caddyfile_path = base / REPORT_DIR / "Caddyfile"
    generated_token_path = base / REPORT_DIR / "generated-dashboard-token.txt"
    plan = build_vps_dashboard_deploy_plan(
        root=base,
        apply=apply,
        dashboard_url=resolved_url,
        env_path=env_file,
        systemd_unit_path=systemd_unit_path,
        caddyfile_path=caddyfile_path,
        generated_systemd_unit_path=generated_unit_path,
        generated_caddyfile_path=generated_caddyfile_path,
        generated_token_path=generated_token_path,
        token_available=bool(token),
        generated_token=generated_token,
        skip_system=skip_system,
        skip_prepare=skip_prepare,
        verify=verify,
        dashboard_host=dashboard_host,
        dashboard_port=dashboard_port,
    )
    return VpsDashboardDeployConfig(
        root=base,
        apply=apply,
        dashboard_url=resolved_url,
        dashboard_host=dashboard_host,
        dashboard_port=dashboard_port,
        service_user=service_user or getpass.getuser(),
        service_group=service_group or service_user or getpass.getuser(),
        env_path=env_file,
        systemd_unit_path=systemd_unit_path,
        caddyfile_path=caddyfile_path,
        use_sudo=use_sudo,
        skip_system=skip_system,
        skip_prepare=skip_prepare,
        verify=verify,
        dashboard_token=token,
        generated_dashboard_token=generated_token,
        dashboard_env=env,
        plan=plan,
    )


def build_vps_dashboard_deploy_plan(
    *,
    root: Path,
    apply: bool,
    dashboard_url: str | None,
    env_path: Path,
    systemd_unit_path: Path,
    caddyfile_path: Path,
    generated_systemd_unit_path: Path,
    generated_caddyfile_path: Path,
    generated_token_path: Path,
    token_available: bool,
    generated_token: bool,
    skip_system: bool,
    skip_prepare: bool,
    verify: bool,
    dashboard_host: str,
    dashboard_port: int,
) -> VpsDashboardDeployPlan:
    steps: list[VpsDashboardDeployStep] = [
        VpsDashboardDeployStep(
            name="mode",
            status="ok",
            message=(
                "VPS Dashboard apply mode is enabled."
                if apply
                else "Dry run only; no deployment changes."
            ),
            details={"mode": "vps_dashboard", "apply": apply},
        ),
        VpsDashboardDeployStep(
            name="dashboard_url",
            status="ok" if dashboard_url else ("blocked" if apply else "warning"),
            message=(
                f"Dashboard public URL will be {dashboard_url}."
                if dashboard_url
                else "Dashboard public HTTPS URL is required before apply."
            ),
            suggested_actions=[] if dashboard_url else ["Pass --dashboard-url or --public-ip."],
        ),
        VpsDashboardDeployStep(
            name="api_token",
            status="ok" if token_available else "blocked",
            message="Dashboard API token is available and will not be exposed in reports."
            if token_available
            else "Dashboard API token is required before exposing the Dashboard.",
            details={"raw_value": SECRET_PLACEHOLDER if token_available else None},
            suggested_actions=[] if token_available else ["Set OPEN_COMPOSER_DASHBOARD_TOKEN."],
        ),
        VpsDashboardDeployStep(
            name="local_env",
            status="ok",
            message=f"Dashboard environment variables will be merged into {env_path}.",
            output_paths=[relpath(env_path, root)],
        ),
    ]
    if not skip_system:
        system_tools_missing = [
            name for name in ["systemctl", "caddy"] if shutil.which(name) is None
        ]
        steps.append(
            VpsDashboardDeployStep(
                name="system_tools",
                status="ok" if not system_tools_missing else "warning",
                message=(
                    "systemctl and caddy are available."
                    if not system_tools_missing
                    else "Missing system tool(s): " + ", ".join(system_tools_missing)
                ),
                details={"missing": system_tools_missing},
                suggested_actions=["Install systemctl/Caddy or rerun with --skip-system."]
                if system_tools_missing
                else [],
            )
        )
    steps.append(
        VpsDashboardDeployStep(
            name="system_service",
            status="skipped" if skip_system else "ok",
            message=(
                "System service installation is skipped."
                if skip_system
                else "systemd and Caddy templates will be generated and installed on apply."
            ),
            output_paths=[
                relpath(generated_systemd_unit_path, root),
                relpath(generated_caddyfile_path, root),
            ],
        )
    )
    if skip_prepare:
        steps.append(
            VpsDashboardDeployStep(
                name="deploy_prepare",
                status="skipped",
                message="Workspace deploy preparation is skipped.",
            )
        )
    steps.append(
        VpsDashboardDeployStep(
            name="post_deploy_verify",
            status="ok" if verify else "skipped",
            message=(
                "Post-deploy Dashboard health check will run after apply."
                if verify
                else "Post-deploy verification is skipped."
            ),
        )
    )
    blocked = any(step.status == "blocked" for step in steps)
    warning = any(step.status == "warning" for step in steps)
    status: Literal["ok", "warning", "blocked"] = (
        "blocked" if blocked else "warning" if warning else "ok"
    )
    report_json_path = root / REPORT_DIR / "plan.json"
    report_markdown_path = root / REPORT_DIR / "plan.md"
    return VpsDashboardDeployPlan(
        source_root=str(root),
        apply=apply,
        ready=not blocked,
        status=status,
        dashboard_url=dashboard_url,
        dashboard_bind=f"{dashboard_host}:{dashboard_port}",
        env_path=relpath(env_path, root),
        systemd_unit_path=systemd_unit_path.as_posix(),
        caddyfile_path=caddyfile_path.as_posix(),
        generated_systemd_unit_path=relpath(generated_systemd_unit_path, root),
        generated_caddyfile_path=relpath(generated_caddyfile_path, root),
        generated_token_path=relpath(generated_token_path, root) if generated_token else None,
        token_available=token_available,
        verify_enabled=verify,
        secret_env_names=DASHBOARD_ENV_KEYS,
        steps=steps,
        report_json_path=relpath(report_json_path, root),
        report_markdown_path=relpath(report_markdown_path, root),
    )


def apply_vps_dashboard_deploy(
    config: VpsDashboardDeployConfig,
    *,
    command_runner: CommandRunner | None = None,
) -> VpsDashboardDeployPlan:
    if not config.plan.ready:
        blocked = [step.name for step in config.plan.steps if step.status == "blocked"]
        raise VpsDashboardDeployError(f"VPS Dashboard deployment is blocked: {', '.join(blocked)}")
    runner = command_runner or run_command
    steps = list(config.plan.steps)

    if not config.skip_prepare:
        runner(["make", "deploy-prepare"], config.root, None, 1200, True, None)
        runner(["make", "dashboard-build"], config.root, None, 1200, True, None)
        steps.append(
            VpsDashboardDeployStep(
                name="apply.deploy_prepare",
                status="ok",
                message="Workspace deployment surface and Dashboard bundle were rebuilt.",
            )
        )

    write_dashboard_env(config)
    steps.append(
        VpsDashboardDeployStep(
            name="apply.local_env",
            status="ok",
            message=f"Dashboard environment variables were written to {config.env_path}.",
            output_paths=[relpath(config.env_path, config.root)],
        )
    )
    if config.generated_dashboard_token and config.dashboard_token:
        token_path = write_generated_token(config)
        steps.append(
            VpsDashboardDeployStep(
                name="apply.dashboard_token",
                status="ok",
                message="Generated Dashboard API token was written to an owner-only file.",
                output_paths=[relpath(token_path, config.root)],
            )
        )

    if not config.skip_system:
        generated_unit, generated_caddyfile = write_system_templates(config)
        steps.append(
            VpsDashboardDeployStep(
                name="apply.system_templates",
                status="ok",
                message="systemd and Caddy templates were generated.",
                output_paths=[
                    relpath(generated_unit, config.root),
                    relpath(generated_caddyfile, config.root),
                ],
            )
        )
        install_system_templates(config, generated_unit, generated_caddyfile, runner)
        systemctl = sudo_prefix(config, ["systemctl"])
        runner([*systemctl, "daemon-reload"], config.root, None, 120, True, None)
        runner(
            [*systemctl, "enable", "--now", config.systemd_unit_path.stem],
            config.root,
            None,
            120,
            True,
            None,
        )
        runner(
            [*systemctl, "restart", config.systemd_unit_path.stem],
            config.root,
            None,
            120,
            True,
            None,
        )
        runner(
            [
                *sudo_prefix(config, ["caddy"]),
                "validate",
                "--config",
                config.caddyfile_path.as_posix(),
            ],
            config.root,
            None,
            120,
            True,
            None,
        )
        runner([*systemctl, "restart", "caddy"], config.root, None, 120, True, None)
        steps.append(
            VpsDashboardDeployStep(
                name="apply.system_service",
                status="ok",
                message="Dashboard systemd service and Caddy reverse proxy were installed.",
                output_paths=[
                    config.systemd_unit_path.as_posix(),
                    config.caddyfile_path.as_posix(),
                ],
            )
        )

    if config.verify:
        steps.append(verify_vps_dashboard_deploy(config))

    blocked = any(step.status == "blocked" for step in steps)
    warning = any(step.status == "warning" for step in steps)
    status: Literal["ok", "warning", "blocked"] = (
        "blocked" if blocked else "warning" if warning else "ok"
    )
    plan = config.plan.model_copy(
        update={
            "generated_at": datetime.now(UTC),
            "steps": steps,
            "status": status,
            "ready": not blocked,
            "token_available": bool(config.dashboard_token),
        }
    )
    write_vps_dashboard_deploy_report(plan, config.root)
    return plan


def write_vps_dashboard_deploy_report(
    plan: VpsDashboardDeployPlan,
    root: Path,
) -> tuple[Path, Path]:
    json_path = root / REPORT_DIR / "plan.json"
    md_path = root / REPORT_DIR / "plan.md"
    plan.report_json_path = relpath(json_path, root)
    plan.report_markdown_path = relpath(md_path, root)
    write_json(json_path, plan)
    ensure_dir(md_path.parent)
    md_path.write_text(render_vps_dashboard_deploy_markdown(plan), encoding="utf-8")
    return json_path, md_path


def write_dashboard_env(config: VpsDashboardDeployConfig) -> Path:
    text = config.env_path.read_text(encoding="utf-8") if config.env_path.exists() else ""
    merged = merge_env_text(text, config.dashboard_env)
    ensure_dir(config.env_path.parent)
    config.env_path.write_text(merged, encoding="utf-8")
    set_owner_only_permissions(config.env_path)
    return config.env_path


def write_generated_token(config: VpsDashboardDeployConfig) -> Path:
    path = config.root / REPORT_DIR / "generated-dashboard-token.txt"
    ensure_dir(path.parent)
    path.write_text(config.dashboard_token + "\n", encoding="utf-8")
    set_owner_only_permissions(path)
    return path


def write_system_templates(config: VpsDashboardDeployConfig) -> tuple[Path, Path]:
    if not config.dashboard_url:
        raise VpsDashboardDeployError("dashboard URL is required to render Caddyfile")
    output_dir = config.root / REPORT_DIR
    unit_path = output_dir / "open-composer-dashboard.service"
    caddyfile_path = output_dir / "Caddyfile"
    ensure_dir(output_dir)
    unit_path.write_text(render_systemd_unit(config), encoding="utf-8")
    caddyfile_path.write_text(render_caddyfile(config), encoding="utf-8")
    return unit_path, caddyfile_path


def install_system_templates(
    config: VpsDashboardDeployConfig,
    generated_unit: Path,
    generated_caddyfile: Path,
    runner: CommandRunner,
) -> None:
    if config.use_sudo:
        runner(
            [
                "sudo",
                "install",
                "-D",
                "-m",
                "0644",
                generated_unit.as_posix(),
                config.systemd_unit_path.as_posix(),
            ],
            config.root,
            None,
            120,
            True,
            None,
        )
        runner(
            [
                "sudo",
                "install",
                "-D",
                "-m",
                "0644",
                generated_caddyfile.as_posix(),
                config.caddyfile_path.as_posix(),
            ],
            config.root,
            None,
            120,
            True,
            None,
        )
        return
    ensure_dir(config.systemd_unit_path.parent)
    ensure_dir(config.caddyfile_path.parent)
    shutil.copy2(generated_unit, config.systemd_unit_path)
    shutil.copy2(generated_caddyfile, config.caddyfile_path)


def verify_vps_dashboard_deploy(config: VpsDashboardDeployConfig) -> VpsDashboardDeployStep:
    if not config.dashboard_url:
        return VpsDashboardDeployStep(
            name="verify.dashboard_health",
            status="blocked",
            message="Dashboard URL is missing; health check cannot run.",
        )
    try:
        payload = http_request_json(
            f"{config.dashboard_url.rstrip('/')}/api/dashboard/health",
            headers={"X-Open-Composer-Token": config.dashboard_token},
            timeout=15,
        )
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return VpsDashboardDeployStep(
            name="verify.dashboard_health",
            status="blocked",
            message="Dashboard health check failed.",
            details={"error": str(exc)},
            suggested_actions=[
                "Check `systemctl status open-composer-dashboard` and `systemctl status caddy`."
            ],
        )
    status = "ok" if payload.get("status") == "ok" else "blocked"
    return VpsDashboardDeployStep(
        name="verify.dashboard_health",
        status=status,
        message="Dashboard health endpoint returned ok."
        if status == "ok"
        else "Dashboard health endpoint did not return ok.",
        details={"response": payload},
    )


def http_request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict[str, object]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("response body must be a JSON object")
    return payload


def render_systemd_unit(config: VpsDashboardDeployConfig) -> str:
    uv = shutil.which("uv") or "/usr/bin/env uv"
    uv_prefix = shlex.split(uv) if uv != "/usr/bin/env uv" else ["/usr/bin/env", "uv"]
    exec_start = [
        *uv_prefix,
        "run",
        "oc",
        "dashboard",
        "serve",
        "--host",
        config.dashboard_host,
        "--port",
        str(config.dashboard_port),
    ]
    return "\n".join(
        [
            "[Unit]",
            "Description=Open Composer Dashboard",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"User={config.service_user}",
            f"Group={config.service_group}",
            f"WorkingDirectory={config.root.as_posix()}",
            f"EnvironmentFile={config.env_path.as_posix()}",
            f"ExecStart={shlex.join(exec_start)}",
            "Restart=on-failure",
            "RestartSec=5",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=full",
            f"ReadWritePaths={config.root.as_posix()}",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def render_caddyfile(config: VpsDashboardDeployConfig) -> str:
    if not config.dashboard_url:
        raise VpsDashboardDeployError("dashboard URL is required to render Caddyfile")
    parsed = urlparse(config.dashboard_url)
    host = parsed.hostname
    if not host:
        raise VpsDashboardDeployError("dashboard URL must include a hostname")
    public_port = parsed.port
    site = host if public_port in (None, DEFAULT_PUBLIC_HTTPS_PORT) else f"{host}:{public_port}"
    return "\n".join(
        [
            f"{site} {{",
            f"    reverse_proxy {config.dashboard_host}:{config.dashboard_port}",
            "}",
            "",
        ]
    )


def sudo_prefix(config: VpsDashboardDeployConfig, args: Sequence[str]) -> list[str]:
    if config.use_sudo:
        return ["sudo", *args]
    return list(args)


def run_command(
    args: Sequence[str],
    cwd: Path,
    input_text: str | None,
    timeout_seconds: int,
    check: bool,
    env: dict[str, str] | None,
) -> CommandExecutionResult:
    completed = subprocess.run(
        list(args),
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        env={**os.environ, **(env or {})},
    )
    if check and completed.returncode != 0:
        raise VpsDashboardDeployError(
            f"command failed ({completed.returncode}): {shlex.join(list(args))}\n"
            f"{completed.stderr.strip()}"
        )
    return CommandExecutionResult(
        args=list(args),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def resolve_dashboard_url(
    *,
    dashboard_url: str | None,
    public_ip: str | None,
    prefer_fallback_port: bool = False,
) -> str | None:
    if dashboard_url:
        return normalize_https_url(dashboard_url)
    if public_ip:
        return dashboard_url_from_public_ip(public_ip)
    return None


def dashboard_url_from_public_ip(
    public_ip: str,
    *,
    domain: str = "nip.io",
    public_port: int = DEFAULT_PUBLIC_HTTPS_PORT,
) -> str:
    normalized_ip = ipaddress.ip_address(public_ip.strip())
    host = f"{normalized_ip}.{domain}"
    if public_port == DEFAULT_PUBLIC_HTTPS_PORT:
        return f"https://{host}"
    return f"https://{host}:{public_port}"


def detect_public_ip() -> str | None:
    for url in ["https://api.ipify.org", "https://ifconfig.me/ip"]:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                value = response.read().decode("utf-8").strip()
            ipaddress.ip_address(value)
            return value
        except (ValueError, OSError):
            continue
    return None


def normalize_https_url(value: str) -> str:
    stripped = value.strip().rstrip("/")
    if not stripped:
        raise VpsDashboardDeployError("dashboard URL cannot be empty")
    parsed = urlparse(stripped)
    if parsed.scheme != "https" or not parsed.netloc:
        raise VpsDashboardDeployError("dashboard URL must be an HTTPS URL")
    return stripped


def resolve_dashboard_token(
    *,
    existing_token: str | None,
    provided_token: str | None,
    rotate_token: bool,
) -> str:
    if provided_token:
        return provided_token.strip()
    if existing_token and not rotate_token:
        return existing_token.strip()
    return secrets.token_urlsafe(32)


def read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def merge_env_text(text: str, updates: dict[str, str]) -> str:
    lines = text.splitlines()
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            result.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            result.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            result.append(line)
    for key, value in updates.items():
        if key not in seen and value:
            result.append(f"{key}={value}")
    return "\n".join(result).rstrip() + "\n"


def set_owner_only_permissions(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)


def is_tcp_port_available(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def render_vps_dashboard_deploy_markdown(plan: VpsDashboardDeployPlan) -> str:
    lines = [
        "# Open Composer VPS Dashboard Deployment",
        "",
        f"- Generated: `{plan.generated_at.isoformat()}`",
        f"- Mode: `{plan.mode}`",
        f"- Status: `{plan.status}`",
        f"- Ready: `{str(plan.ready).lower()}`",
        f"- Dashboard URL: `{plan.dashboard_url or 'missing'}`",
        f"- Dashboard bind: `{plan.dashboard_bind}`",
        f"- Token available: `{str(plan.token_available).lower()}`",
        f"- Env path: `{plan.env_path}`",
        f"- systemd unit: `{plan.systemd_unit_path}`",
        f"- Caddyfile: `{plan.caddyfile_path}`",
        "",
        "## Steps",
        "",
    ]
    for step in plan.steps:
        lines.append(f"- `{step.name}`: **{step.status}** - {step.message}")
        if step.suggested_actions:
            for action in step.suggested_actions:
                lines.append(f"  - next: {action}")
        if step.output_paths:
            for output in step.output_paths:
                lines.append(f"  - output: `{output}`")
    lines.extend(
        [
            "",
            "## Operator Notes",
            "",
            "- This is the canonical deployment mode: VPS serves the Dashboard directly.",
            "- Vercel is not required for normal deployments.",
            "- Long strategy work remains file/CLI/agent driven; the Dashboard only "
            "shows state and sends controlled local requests.",
            "- Open the Dashboard with `?token=<OPEN_COMPOSER_DASHBOARD_TOKEN>` once; "
            "the browser stores the token locally.",
            "",
        ]
    )
    return "\n".join(lines)


def relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
