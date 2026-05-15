from __future__ import annotations

import getpass
import hashlib
import ipaddress
import os
import re
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
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import ensure_dir
from open_composer.remote.server import build_remote_doctor_report
from open_composer.storage import write_json

DEFAULT_VERCEL_PROJECT = "open-composer-dashboard"
DEFAULT_REMOTE_HOST = "127.0.0.1"
DEFAULT_REMOTE_PORT = 8787
DEFAULT_OWNER = "owner"
DEFAULT_SESSION_TTL_SECONDS = 604800
DEFAULT_PBKDF2_ITERATIONS = 600_000
DEFAULT_SYSTEMD_UNIT_PATH = Path("/etc/systemd/system/open-composer-remote.service")
DEFAULT_CADDYFILE_PATH = Path("/etc/caddy/Caddyfile")
REPORT_DIR = Path("reports/deployment/vps-bootstrap")
SECRET_PLACEHOLDER = "<redacted>"

REMOTE_ENV_KEYS = [
    "OC_REMOTE_BASE_URL",
    "OC_REMOTE_SHARED_SECRET",
    "OC_DASHBOARD_PASSWORD_HASH",
    "OC_DASHBOARD_SESSION_SECRET",
    "OC_DASHBOARD_OWNER",
    "OC_DASHBOARD_ALLOWED_ORIGIN",
    "OC_DASHBOARD_SESSION_TTL_SECONDS",
]

VERCEL_ENV_KEYS = [
    "OC_REMOTE_BASE_URL",
    "OC_REMOTE_SHARED_SECRET",
    "OC_DASHBOARD_PASSWORD_HASH",
    "OC_DASHBOARD_SESSION_SECRET",
    "OC_DASHBOARD_OWNER",
    "OC_DASHBOARD_ALLOWED_ORIGIN",
    "OC_DASHBOARD_SESSION_TTL_SECONDS",
]


class VpsBootstrapError(RuntimeError):
    pass


class VpsBootstrapStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["ok", "warning", "blocked", "skipped"]
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    suggested_actions: list[str] = Field(default_factory=list)
    output_paths: list[str] = Field(default_factory=list)


class VpsBootstrapPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_root: str
    apply: bool
    ready: bool
    status: Literal["ok", "warning", "blocked"]
    daemon_url: str | None = None
    daemon_bind: str = f"{DEFAULT_REMOTE_HOST}:{DEFAULT_REMOTE_PORT}"
    vercel_project: str
    vercel_origin: str | None = None
    dashboard_dir: str
    remote_env_path: str
    systemd_unit_path: str
    caddyfile_path: str
    generated_systemd_unit_path: str
    generated_caddyfile_path: str
    generated_password_path: str | None = None
    deployment_url: str | None = None
    secret_env_names: list[str] = Field(default_factory=list)
    vercel_env_names: list[str] = Field(default_factory=list)
    steps: list[VpsBootstrapStep] = Field(default_factory=list)
    report_json_path: str | None = None
    report_markdown_path: str | None = None


def default_vercel_command() -> list[str]:
    if shutil.which("vercel"):
        return ["vercel"]
    return ["npx", "--yes", "vercel@latest"]


class VpsBootstrapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    root: Path
    apply: bool = False
    vercel_token: str | None = None
    vercel_project: str = DEFAULT_VERCEL_PROJECT
    vercel_scope: str | None = None
    vercel_command: list[str] = Field(default_factory=default_vercel_command)
    daemon_url: str | None = None
    vercel_origin: str | None = None
    owner: str = DEFAULT_OWNER
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    remote_host: str = DEFAULT_REMOTE_HOST
    remote_port: int = DEFAULT_REMOTE_PORT
    service_user: str
    service_group: str
    env_path: Path
    systemd_unit_path: Path = DEFAULT_SYSTEMD_UNIT_PATH
    caddyfile_path: Path = DEFAULT_CADDYFILE_PATH
    use_sudo: bool = False
    skip_system: bool = False
    skip_vercel: bool = False
    skip_prepare: bool = False
    dashboard_password: str | None = None
    generated_dashboard_password: bool = False
    remote_shared_secret: str
    dashboard_session_secret: str
    dashboard_password_hash: str
    remote_env: dict[str, str]
    vercel_env: dict[str, str]
    plan: VpsBootstrapPlan


@dataclass(frozen=True)
class CommandExecutionResult:
    args: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


CommandRunner = Callable[
    [Sequence[str], Path, str | None, int, bool, dict[str, str] | None], CommandExecutionResult
]


def build_vps_bootstrap_config(
    root: Path,
    *,
    apply: bool = False,
    vercel_token: str | None = None,
    vercel_project: str = DEFAULT_VERCEL_PROJECT,
    vercel_scope: str | None = None,
    vercel_command: str | Sequence[str] | None = None,
    daemon_url: str | None = None,
    public_ip: str | None = None,
    vercel_origin: str | None = None,
    dashboard_password: str | None = None,
    generate_password: bool = True,
    rotate_secrets: bool = False,
    owner: str = DEFAULT_OWNER,
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    remote_host: str = DEFAULT_REMOTE_HOST,
    remote_port: int = DEFAULT_REMOTE_PORT,
    service_user: str | None = None,
    service_group: str | None = None,
    env_path: Path | None = None,
    systemd_unit_path: Path = DEFAULT_SYSTEMD_UNIT_PATH,
    caddyfile_path: Path = DEFAULT_CADDYFILE_PATH,
    use_sudo: bool = False,
    skip_system: bool = False,
    skip_vercel: bool = False,
    skip_prepare: bool = False,
) -> VpsBootstrapConfig:
    base = root.resolve()
    env_file = env_path or base / ".env"
    existing_env = read_env_values(env_file)
    project = normalize_vercel_project(vercel_project)
    origin = normalize_https_url(vercel_origin or f"https://{project}.vercel.app")
    resolved_daemon_url = resolve_daemon_url(daemon_url=daemon_url, public_ip=public_ip)

    remote_secret = (
        generate_shared_secret()
        if rotate_secrets
        else existing_env.get("OC_REMOTE_SHARED_SECRET") or generate_shared_secret()
    )
    session_secret = (
        generate_shared_secret()
        if rotate_secrets
        else existing_env.get("OC_DASHBOARD_SESSION_SECRET") or generate_shared_secret()
    )
    password_hash, raw_password, generated_password = resolve_dashboard_password_hash(
        existing_hash=existing_env.get("OC_DASHBOARD_PASSWORD_HASH"),
        dashboard_password=dashboard_password,
        generate_password=generate_password,
        rotate_secrets=rotate_secrets,
    )
    if not owner.strip():
        raise VpsBootstrapError("OC_DASHBOARD_OWNER must not be empty")
    if session_ttl_seconds <= 0:
        raise VpsBootstrapError("session TTL must be positive")

    remote_env = {
        "OC_REMOTE_BASE_URL": resolved_daemon_url or "",
        "OC_REMOTE_SHARED_SECRET": remote_secret,
        "OC_DASHBOARD_PASSWORD_HASH": password_hash,
        "OC_DASHBOARD_SESSION_SECRET": session_secret,
        "OC_DASHBOARD_OWNER": owner,
        "OC_DASHBOARD_ALLOWED_ORIGIN": origin,
        "OC_DASHBOARD_SESSION_TTL_SECONDS": str(session_ttl_seconds),
    }
    vercel_env = {
        "OC_REMOTE_BASE_URL": resolved_daemon_url or "",
        "OC_REMOTE_SHARED_SECRET": remote_secret,
        "OC_DASHBOARD_PASSWORD_HASH": password_hash,
        "OC_DASHBOARD_SESSION_SECRET": session_secret,
        "OC_DASHBOARD_OWNER": owner,
        "OC_DASHBOARD_ALLOWED_ORIGIN": origin,
        "OC_DASHBOARD_SESSION_TTL_SECONDS": str(session_ttl_seconds),
    }

    generated_dir = base / REPORT_DIR
    password_path = generated_dir / "generated-dashboard-password.txt"
    plan = build_vps_bootstrap_plan(
        root=base,
        apply=apply,
        daemon_url=resolved_daemon_url,
        vercel_project=project,
        vercel_origin=origin,
        env_path=env_file,
        systemd_unit_path=systemd_unit_path,
        caddyfile_path=caddyfile_path,
        generated_systemd_unit_path=generated_dir / "open-composer-remote.service",
        generated_caddyfile_path=generated_dir / "Caddyfile",
        generated_password_path=password_path if generated_password else None,
        vercel_token=vercel_token,
        skip_system=skip_system,
        skip_vercel=skip_vercel,
        skip_prepare=skip_prepare,
    )

    return VpsBootstrapConfig(
        root=base,
        apply=apply,
        vercel_token=vercel_token,
        vercel_project=project,
        vercel_scope=vercel_scope,
        vercel_command=parse_command(vercel_command)
        if vercel_command
        else default_vercel_command(),
        daemon_url=resolved_daemon_url,
        vercel_origin=origin,
        owner=owner,
        session_ttl_seconds=session_ttl_seconds,
        remote_host=remote_host,
        remote_port=remote_port,
        service_user=service_user or getpass.getuser(),
        service_group=service_group or service_user or getpass.getuser(),
        env_path=env_file,
        systemd_unit_path=systemd_unit_path,
        caddyfile_path=caddyfile_path,
        skip_system=skip_system,
        skip_vercel=skip_vercel,
        skip_prepare=skip_prepare,
        dashboard_password=raw_password,
        generated_dashboard_password=generated_password,
        remote_shared_secret=remote_secret,
        dashboard_session_secret=session_secret,
        dashboard_password_hash=password_hash,
        remote_env=remote_env,
        vercel_env=vercel_env,
        plan=plan,
    )


def build_vps_bootstrap_plan(
    *,
    root: Path,
    apply: bool,
    daemon_url: str | None,
    vercel_project: str,
    vercel_origin: str,
    env_path: Path,
    systemd_unit_path: Path,
    caddyfile_path: Path,
    generated_systemd_unit_path: Path,
    generated_caddyfile_path: Path,
    generated_password_path: Path | None,
    vercel_token: str | None,
    skip_system: bool,
    skip_vercel: bool,
    skip_prepare: bool,
) -> VpsBootstrapPlan:
    steps: list[VpsBootstrapStep] = []
    steps.append(
        VpsBootstrapStep(
            name="mode",
            status="ok",
            message="Apply mode is enabled." if apply else "Dry run only; no deployment changes.",
            details={"apply": apply},
        )
    )
    steps.append(
        VpsBootstrapStep(
            name="daemon_url",
            status="ok" if daemon_url else ("blocked" if apply else "warning"),
            message=(
                f"Remote daemon public URL will be {daemon_url}."
                if daemon_url
                else (
                    "A daemon HTTPS URL is required before apply; apply can auto-detect "
                    "public IPv4 unless --no-detect-ip is used."
                )
            ),
            suggested_actions=[] if daemon_url else ["Pass --daemon-url or --public-ip."],
        )
    )
    steps.append(
        VpsBootstrapStep(
            name="secrets",
            status="ok",
            message="Remote shared secret, session secret, and password hash are available.",
            details={"raw_values": SECRET_PLACEHOLDER},
        )
    )
    steps.append(
        VpsBootstrapStep(
            name="local_env",
            status="ok",
            message=f"Remote environment variables will be merged into {env_path}.",
            output_paths=[relpath(env_path, root)],
        )
    )
    if not skip_vercel:
        dashboard_dir = root / "dashboard"
        dashboard_missing_status: Literal["warning", "blocked"] = "blocked" if apply else "warning"
        steps.append(
            VpsBootstrapStep(
                name="dashboard_dir",
                status="ok" if dashboard_dir.exists() else dashboard_missing_status,
                message=(
                    "Dashboard directory is available for Vercel deployment."
                    if dashboard_dir.exists()
                    else "dashboard/ is missing; Vercel deployment cannot be created."
                ),
                output_paths=[relpath(dashboard_dir, root)],
            )
        )
    if not skip_system:
        system_tools_missing = [
            name for name in ["systemctl", "caddy"] if shutil.which(name) is None
        ]
        system_tools_status: Literal["ok", "warning", "blocked"] = (
            "ok" if not system_tools_missing else "blocked" if apply else "warning"
        )
        steps.append(
            VpsBootstrapStep(
                name="system_tools",
                status=system_tools_status,
                message=(
                    "systemctl and caddy are available."
                    if not system_tools_missing
                    else "Missing system tool(s): " + ", ".join(system_tools_missing)
                ),
                details={"missing": system_tools_missing},
                suggested_actions=[
                    "Install Caddy or rerun with --skip-system.",
                ]
                if system_tools_missing
                else [],
            )
        )
    steps.append(
        VpsBootstrapStep(
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
    steps.append(
        VpsBootstrapStep(
            name="vercel",
            status="skipped"
            if skip_vercel
            else ("ok" if vercel_token else "blocked" if apply else "warning"),
            message=(
                "Vercel deployment is skipped."
                if skip_vercel
                else (
                    f"Vercel project {vercel_project} will be configured."
                    if vercel_token
                    else "VERCEL_TOKEN is required before apply unless --skip-vercel is used."
                )
            ),
            details={
                "origin": vercel_origin,
                "token": SECRET_PLACEHOLDER if vercel_token else None,
            },
            suggested_actions=[] if skip_vercel or vercel_token else ["Set VERCEL_TOKEN."],
        )
    )
    if skip_prepare:
        steps.append(
            VpsBootstrapStep(
                name="deploy_prepare",
                status="skipped",
                message="Workspace deploy preparation is skipped.",
            )
        )
    blocked = any(step.status == "blocked" for step in steps)
    warning = any(step.status == "warning" for step in steps)
    status: Literal["ok", "warning", "blocked"] = (
        "blocked" if blocked else "warning" if warning else "ok"
    )
    report_json_path = root / REPORT_DIR / "plan.json"
    report_markdown_path = root / REPORT_DIR / "plan.md"
    return VpsBootstrapPlan(
        source_root=str(root),
        apply=apply,
        ready=not blocked,
        status=status,
        daemon_url=daemon_url,
        vercel_project=vercel_project,
        vercel_origin=vercel_origin,
        dashboard_dir=relpath(root / "dashboard", root),
        remote_env_path=relpath(env_path, root),
        systemd_unit_path=systemd_unit_path.as_posix(),
        caddyfile_path=caddyfile_path.as_posix(),
        generated_systemd_unit_path=relpath(generated_systemd_unit_path, root),
        generated_caddyfile_path=relpath(generated_caddyfile_path, root),
        generated_password_path=relpath(generated_password_path, root)
        if generated_password_path
        else None,
        secret_env_names=REMOTE_ENV_KEYS,
        vercel_env_names=VERCEL_ENV_KEYS,
        steps=steps,
        report_json_path=relpath(report_json_path, root),
        report_markdown_path=relpath(report_markdown_path, root),
    )


def write_vps_bootstrap_report(plan: VpsBootstrapPlan, root: Path) -> tuple[Path, Path]:
    json_path = root / REPORT_DIR / "plan.json"
    md_path = root / REPORT_DIR / "plan.md"
    plan.report_json_path = relpath(json_path, root)
    plan.report_markdown_path = relpath(md_path, root)
    write_json(json_path, plan)
    ensure_dir(md_path.parent)
    md_path.write_text(render_vps_bootstrap_markdown(plan), encoding="utf-8")
    return json_path, md_path


def apply_vps_bootstrap(
    config: VpsBootstrapConfig,
    *,
    command_runner: CommandRunner | None = None,
) -> VpsBootstrapPlan:
    if not config.plan.ready:
        blocked = [step.name for step in config.plan.steps if step.status == "blocked"]
        raise VpsBootstrapError(f"VPS bootstrap is blocked: {', '.join(blocked)}")
    runner = command_runner or run_command
    steps = list(config.plan.steps)

    if not config.skip_prepare:
        runner(["make", "deploy-prepare"], config.root, None, 1200, True, None)
        steps.append(
            VpsBootstrapStep(
                name="apply.deploy_prepare",
                status="ok",
                message="Workspace deployment surface was rebuilt.",
            )
        )

    write_remote_env(config)
    steps.append(
        VpsBootstrapStep(
            name="apply.local_env",
            status="ok",
            message=f"Remote environment variables were written to {config.env_path}.",
            output_paths=[relpath(config.env_path, config.root)],
        )
    )
    if config.generated_dashboard_password and config.dashboard_password:
        password_path = write_generated_password(config)
        steps.append(
            VpsBootstrapStep(
                name="apply.dashboard_password",
                status="ok",
                message="Generated dashboard password was written to an owner-only file.",
                output_paths=[relpath(password_path, config.root)],
            )
        )

    if not config.skip_system:
        generated_unit, generated_caddyfile = write_system_templates(config)
        steps.append(
            VpsBootstrapStep(
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
        runner([*systemctl, "reload", "caddy"], config.root, None, 120, True, None)
        steps.append(
            VpsBootstrapStep(
                name="apply.system_service",
                status="ok",
                message="systemd service and Caddy reverse proxy were installed/reloaded.",
                output_paths=[
                    config.systemd_unit_path.as_posix(),
                    config.caddyfile_path.as_posix(),
                ],
            )
        )

    for key, value in config.remote_env.items():
        if value:
            os.environ[key] = value
    doctor = build_remote_doctor_report(config.root)
    steps.append(
        VpsBootstrapStep(
            name="apply.remote_doctor",
            status="ok" if doctor.ready else "blocked",
            message=f"Remote doctor status: {doctor.status}.",
            details={"checks": [check.model_dump(mode="json") for check in doctor.checks]},
        )
    )

    deployment_url: str | None = None
    if not config.skip_vercel:
        deployment_url = apply_vercel(config, runner)
        steps.append(
            VpsBootstrapStep(
                name="apply.vercel",
                status="ok",
                message="Vercel project environment and production deployment were updated.",
                details={"deployment_url": deployment_url or config.vercel_origin},
            )
        )

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
            "deployment_url": deployment_url,
        }
    )
    write_vps_bootstrap_report(plan, config.root)
    return plan


def write_remote_env(config: VpsBootstrapConfig) -> Path:
    text = config.env_path.read_text(encoding="utf-8") if config.env_path.exists() else ""
    merged = merge_env_text(text, config.remote_env)
    ensure_dir(config.env_path.parent)
    config.env_path.write_text(merged, encoding="utf-8")
    os.chmod(config.env_path, 0o600)
    return config.env_path


def write_generated_password(config: VpsBootstrapConfig) -> Path:
    if not config.dashboard_password:
        raise VpsBootstrapError("dashboard password is not available")
    path = config.root / REPORT_DIR / "generated-dashboard-password.txt"
    ensure_dir(path.parent)
    path.write_text(config.dashboard_password + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def write_system_templates(config: VpsBootstrapConfig) -> tuple[Path, Path]:
    if not config.daemon_url:
        raise VpsBootstrapError("daemon URL is required to render Caddyfile")
    output_dir = config.root / REPORT_DIR
    unit_path = output_dir / "open-composer-remote.service"
    caddyfile_path = output_dir / "Caddyfile"
    ensure_dir(output_dir)
    unit_path.write_text(render_systemd_unit(config), encoding="utf-8")
    caddyfile_path.write_text(render_caddyfile(config.daemon_url), encoding="utf-8")
    return unit_path, caddyfile_path


def install_system_templates(
    config: VpsBootstrapConfig,
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
    else:
        ensure_dir(config.systemd_unit_path.parent)
        ensure_dir(config.caddyfile_path.parent)
        shutil.copy2(generated_unit, config.systemd_unit_path)
        shutil.copy2(generated_caddyfile, config.caddyfile_path)


def sudo_prefix(config: VpsBootstrapConfig, args: Sequence[str]) -> list[str]:
    if config.use_sudo:
        return ["sudo", *args]
    return list(args)


def apply_vercel(config: VpsBootstrapConfig, runner: CommandRunner) -> str | None:
    if not config.vercel_token:
        raise VpsBootstrapError("VERCEL_TOKEN is required for Vercel deployment")
    dashboard_dir = config.root / "dashboard"
    if not dashboard_dir.exists():
        raise VpsBootstrapError("dashboard directory is missing")
    base_cmd = list(config.vercel_command)
    token_args = ["--token", config.vercel_token]
    scope_args = ["--scope", config.vercel_scope] if config.vercel_scope else []

    runner(
        [
            *base_cmd,
            "link",
            "--yes",
            "--project",
            config.vercel_project,
            *scope_args,
            *token_args,
        ],
        dashboard_dir,
        None,
        300,
        True,
        None,
    )
    for name, value in config.vercel_env.items():
        runner(
            [*base_cmd, "env", "rm", name, "production", "--yes", *scope_args, *token_args],
            dashboard_dir,
            None,
            180,
            False,
            None,
        )
        runner(
            [*base_cmd, "env", "add", name, "production", *scope_args, *token_args],
            dashboard_dir,
            value + "\n",
            180,
            True,
            None,
        )
    result = runner(
        [*base_cmd, "deploy", "--prod", "--yes", *scope_args, *token_args],
        dashboard_dir,
        None,
        900,
        True,
        None,
    )
    return parse_vercel_deployment_url(result.stdout) or config.vercel_origin


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
        env=env,
    )
    result = CommandExecutionResult(
        args=list(args),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if check and result.returncode != 0:
        safe = safe_command(args)
        detail = (result.stderr or result.stdout).strip()
        raise VpsBootstrapError(f"command failed ({result.returncode}): {safe}\n{detail}")
    return result


def resolve_daemon_url(*, daemon_url: str | None, public_ip: str | None) -> str | None:
    if daemon_url:
        return normalize_https_url(daemon_url)
    if public_ip:
        return daemon_url_from_public_ip(public_ip)
    return None


def daemon_url_from_public_ip(public_ip: str) -> str:
    try:
        parsed = ipaddress.ip_address(public_ip.strip())
    except ValueError as exc:
        raise VpsBootstrapError(f"invalid public IP: {public_ip}") from exc
    if parsed.version != 4:
        raise VpsBootstrapError("sslip.io daemon URL generation currently requires an IPv4 address")
    return f"https://{parsed}.sslip.io"


def detect_public_ip(timeout_seconds: int = 5) -> str:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout_seconds) as response:
            value = response.read().decode("utf-8").strip()
    except OSError as exc:
        raise VpsBootstrapError(
            "public IP detection failed; pass --public-ip or --daemon-url"
        ) from exc
    ipaddress.ip_address(value)
    return value


def normalize_https_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise VpsBootstrapError("remote URLs must be absolute https:// URLs")
    return normalized


def normalize_vercel_project(value: str) -> str:
    project = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?", project):
        raise VpsBootstrapError(
            "Vercel project must be 1-100 chars of lowercase letters, numbers, or hyphens"
        )
    return project


def generate_shared_secret() -> str:
    return secrets.token_urlsafe(48)


def generate_dashboard_password() -> str:
    return secrets.token_urlsafe(18)


def hash_dashboard_password(
    password: str,
    *,
    iterations: int = DEFAULT_PBKDF2_ITERATIONS,
    salt: str | None = None,
) -> str:
    if not password:
        raise VpsBootstrapError("dashboard password must not be empty")
    selected_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        selected_salt.encode("utf-8"),
        iterations,
        dklen=32,
    ).hex()
    return f"pbkdf2-sha256:{iterations}:{selected_salt}:{digest}"


def resolve_dashboard_password_hash(
    *,
    existing_hash: str | None,
    dashboard_password: str | None,
    generate_password: bool,
    rotate_secrets: bool,
) -> tuple[str, str | None, bool]:
    if dashboard_password:
        return hash_dashboard_password(dashboard_password), dashboard_password, False
    if existing_hash and not rotate_secrets:
        return existing_hash, None, False
    if generate_password:
        password = generate_dashboard_password()
        return hash_dashboard_password(password), password, True
    raise VpsBootstrapError(
        "dashboard password hash is missing; pass --dashboard-password or --generate-password"
    )


def read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            values[key] = value.strip().strip('"').strip("'")
    return values


def merge_env_text(existing_text: str, updates: dict[str, str]) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for line in existing_text.splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if match and match.group(1) in updates:
            key = match.group(1)
            lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            lines.append(line)
    if lines and lines[-1].strip():
        lines.append("")
    for key in updates:
        if key not in seen:
            lines.append(f"{key}={updates[key]}")
    return "\n".join(lines).rstrip() + "\n"


def render_systemd_unit(config: VpsBootstrapConfig) -> str:
    return "\n".join(
        [
            "[Unit]",
            "Description=Open Composer Remote Dashboard daemon",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"User={config.service_user}",
            f"Group={config.service_group}",
            f"WorkingDirectory={config.root.as_posix()}",
            f"EnvironmentFile={config.env_path.as_posix()}",
            (
                "ExecStart=/usr/bin/env uv run oc remote serve "
                f"--host {config.remote_host} --port {config.remote_port}"
            ),
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


def render_caddyfile(daemon_url: str) -> str:
    host = urlparse(daemon_url).netloc
    if not host:
        raise VpsBootstrapError("daemon URL host is missing")
    return "\n".join(
        [
            f"{host} {{",
            "  encode zstd gzip",
            "  request_body {",
            "    max_size 1MB",
            "  }",
            f"  reverse_proxy {DEFAULT_REMOTE_HOST}:{DEFAULT_REMOTE_PORT}",
            "}",
            "",
        ]
    )


def render_vps_bootstrap_markdown(plan: VpsBootstrapPlan) -> str:
    lines = [
        "# Open Composer VPS Bootstrap Plan",
        "",
        f"- Status: `{plan.status}`",
        f"- Ready: `{plan.ready}`",
        f"- Apply: `{plan.apply}`",
        f"- Daemon URL: `{plan.daemon_url or 'missing'}`",
        f"- Vercel project: `{plan.vercel_project}`",
        f"- Vercel origin: `{plan.vercel_origin or 'missing'}`",
        f"- Remote env: `{plan.remote_env_path}`",
        "",
        "## Steps",
        "",
    ]
    for step in plan.steps:
        lines.append(f"- `{step.status}` **{step.name}**: {step.message}")
        if step.output_paths:
            lines.append(f"  outputs: {', '.join(f'`{path}`' for path in step.output_paths)}")
    lines.extend(
        [
            "",
            "## Secret Handling",
            "",
            "Raw remote shared secrets and session secrets are intentionally redacted "
            "from this report.",
            "If a dashboard password was generated, it is written only during apply "
            "to an owner-only file.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_command(command: str | Sequence[str]) -> list[str]:
    if isinstance(command, str):
        parsed = shlex.split(command)
    else:
        parsed = [str(item) for item in command]
    if not parsed:
        raise VpsBootstrapError("command must not be empty")
    return parsed


def parse_vercel_deployment_url(output: str) -> str | None:
    matches = re.findall(r"https://[A-Za-z0-9._/-]*vercel\.app[A-Za-z0-9._/-]*", output)
    return matches[-1].rstrip(".") if matches else None


def safe_command(args: Sequence[str]) -> str:
    safe: list[str] = []
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            safe.append(SECRET_PLACEHOLDER)
            skip_next = False
            continue
        safe.append(str(arg))
        if arg == "--token" and index < len(args) - 1:
            skip_next = True
    return " ".join(shlex.quote(item) for item in safe)


def relpath(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
