from __future__ import annotations

import importlib.util
import json
import os
import secrets
import sys
from collections.abc import Mapping
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, get_args
from urllib.parse import parse_qs, urlparse

from open_composer.agent_requests import AgentRequestCreate, create_agent_request
from open_composer.config import (
    alpaca_api_base_url,
    dashboard_allowed_origin,
    dashboard_api_token,
    data_feed,
    default_openai_model,
    openai_api_key_env_name,
    openai_base_url,
    openai_base_url_source,
    optional_env_status,
)
from open_composer.dashboard.catalog import build_dashboard_catalog
from open_composer.dashboard.commands import (
    DashboardCommandError,
    build_dashboard_command_plan,
    execute_dashboard_command_plan,
    load_dashboard_command_plan,
    resolve_dashboard_serve_root,
    write_dashboard_command_plan,
)
from open_composer.models.notification import NotificationKind, NotificationSeverity
from open_composer.models.project import StrategyProjectCreate
from open_composer.notifications import (
    notification_config_status,
    read_notification_log,
    send_test_notification,
)
from open_composer.projects import (
    create_project,
    load_project,
    project_agent_prompt,
    update_project_state,
    write_project,
    write_project_context,
)


class DashboardServerError(RuntimeError):
    pass


class DashboardHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        dashboard_root: Path,
        dashboard_token: str | None,
        **kwargs: Any,
    ) -> None:
        self.dashboard_root = dashboard_root
        self.dashboard_token = dashboard_token
        super().__init__(*args, **kwargs)

    def end_headers(self) -> None:
        request_origin = str(self.headers.get("Origin", "")).strip()
        allowed_origin = dashboard_allowed_origin()
        if allowed_origin:
            if request_origin == allowed_origin:
                self.send_header("Access-Control-Allow-Origin", allowed_origin)
        else:
            port = int(self.server.server_address[1])
            local_origins = {
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
            }
            if request_origin in local_origins:
                self.send_header("Access-Control-Allow-Origin", request_origin)
        self.send_header("Vary", "Origin")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Authorization, Content-Type, X-Open-Composer-Token",
        )
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/") and not self._authorize_api():
            return
        if path == "/api/dashboard/health":
            self._send_json(
                build_dashboard_health_payload(
                    self.dashboard_root,
                    Path(self.directory),
                    auth_required=bool(self.dashboard_token),
                )
            )
            return
        if path == "/api/dashboard/catalog":
            self._send_json(build_dashboard_catalog_payload(self.dashboard_root))
            return
        if path == "/api/dashboard/environment":
            self._send_json(
                build_dashboard_environment_payload(
                    self.dashboard_root,
                    Path(self.directory),
                    auth_required=bool(self.dashboard_token),
                )
            )
            return
        if path == "/api/notifications/config":
            self._send_json(build_notification_config_payload(self.dashboard_root))
            return
        if path == "/api/notifications/log":
            limit = _query_limit(parsed.query)
            self._send_json(build_notification_log_payload(self.dashboard_root, limit=limit))
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/") and not self._authorize_api():
            return
        payload = self._read_json_body()
        if path == "/api/dashboard/command-plan":
            self._handle_command_plan(payload)
            return
        if path == "/api/dashboard/command-run":
            self._handle_command_run(payload)
            return
        if path == "/api/projects":
            self._handle_project_create(payload)
            return
        if path.startswith("/api/projects/") and path.endswith("/state"):
            project_id = path.removeprefix("/api/projects/").removesuffix("/state").strip("/")
            self._handle_project_state(project_id, payload)
            return
        if path == "/api/notifications/test":
            self._handle_notification_test(payload)
            return
        self.send_error(404, "Unknown dashboard API path")

    def _handle_command_plan(self, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_dashboard_command_plan_payload(self.dashboard_root, payload))
        except DashboardCommandError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_command_run(self, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_dashboard_command_run_payload(self.dashboard_root, payload))
        except DashboardCommandError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_notification_test(self, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_notification_test_payload(self.dashboard_root, payload))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_project_create(self, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_project_create_payload(self.dashboard_root, payload), status=201)
        except (ValueError, OSError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_project_state(self, project_id: str, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_project_state_payload(self.dashboard_root, project_id, payload))
        except (ValueError, FileNotFoundError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length <= 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        if not body.strip():
            return {}
        data = json.loads(body)
        if not isinstance(data, dict):
            raise DashboardServerError("request body must be a JSON object")
        return data

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _authorize_api(self) -> bool:
        if dashboard_request_authorized(self.headers, self.dashboard_token):
            return True
        self._send_json({"error": "Dashboard API token is required."}, status=401)
        return False


def create_dashboard_server(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    api_token: str | None = None,
) -> ThreadingHTTPServer:
    serve_root = resolve_dashboard_serve_root(root)
    if serve_root is None:
        raise DashboardServerError(
            "dashboard bundle not found; run `make dashboard-build` or "
            "`uv run oc dashboard html` first"
        )
    handler = partial(
        DashboardHTTPRequestHandler,
        directory=str(serve_root),
        dashboard_root=root,
        dashboard_token=api_token if api_token is not None else dashboard_api_token(),
    )
    return ThreadingHTTPServer((host, port), handler)


def serve_dashboard(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    api_token: str | None = None,
) -> None:
    token = api_token if api_token is not None else dashboard_api_token()
    with create_dashboard_server(root, host=host, port=port, api_token=token) as server:
        print(f"dashboard serving http://{host}:{port}")
        print(f"root={resolve_dashboard_serve_root(root)}")
        print(f"api_auth={'required' if token else 'disabled'}")
        server.serve_forever()


def build_dashboard_health_payload(
    root: Path,
    serve_root: Path,
    *,
    auth_required: bool = False,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "dashboard_root": root.as_posix(),
        "serve_root": serve_root.as_posix(),
        "auth_required": auth_required,
    }


def build_dashboard_environment_payload(
    root: Path,
    serve_root: Path,
    *,
    auth_required: bool = False,
) -> dict[str, Any]:
    notification_status = notification_config_status(root)
    sample_path = root / "data" / "sample" / "qqq_15m.csv"
    package_names = ["pydantic", "pandas", "numpy", "yaml", "typer", "rich"]
    packages = [
        _env_item(
            name=f"Package {name}",
            status="ok" if importlib.util.find_spec(name) else "blocked",
            detail="installed" if importlib.util.find_spec(name) else "missing Python package",
            required=True,
        )
        for name in package_names
    ]
    openai_key_env = openai_api_key_env_name()
    sections = [
        {
            "section": "workspace",
            "title": "Workspace",
            "items": [
                _env_item("Python", "ok", sys.version.split()[0], required=True),
                _env_item(
                    "Workspace root",
                    "ok" if root.exists() else "blocked",
                    root.as_posix(),
                    required=True,
                ),
                _env_item(
                    "Dashboard build",
                    "ok" if (serve_root / "index.html").exists() else "warning",
                    serve_root.relative_to(root).as_posix()
                    if _is_relative_to(serve_root, root)
                    else serve_root.as_posix(),
                    required=True,
                    next_action="run `uv run oc dashboard build`"
                    if not (serve_root / "index.html").exists()
                    else "",
                ),
                _env_item(
                    "Sample data",
                    "ok" if sample_path.exists() else "blocked",
                    sample_path.relative_to(root).as_posix()
                    if _is_relative_to(sample_path, root)
                    else sample_path.as_posix(),
                    required=True,
                ),
                *packages,
            ],
        },
        {
            "section": "model",
            "title": "Model access",
            "items": [
                _env_item(
                    openai_key_env,
                    "ok" if os.getenv(openai_key_env) or os.getenv("OPENAI_API_KEY") else "warning",
                    "presence only; value never exposed",
                    required=False,
                    next_action=f"set `{openai_key_env}` for LLM review/drafting"
                    if optional_env_status(openai_key_env) == "missing"
                    and optional_env_status("OPENAI_API_KEY") == "missing"
                    else "",
                ),
                _env_item(
                    "OPENAI_BASE_URL",
                    "ok" if openai_base_url_source() != "missing" else "warning",
                    openai_base_url() or "default provider endpoint",
                    required=False,
                ),
                _env_item("OPENAI_MODEL", "ok", default_openai_model(), required=False),
            ],
        },
        {
            "section": "paper",
            "title": "Paper trading",
            "items": [
                _env_item(
                    "ALPACA_API_KEY_ID",
                    "ok" if os.getenv("ALPACA_API_KEY_ID") else "warning",
                    "presence only; value never exposed",
                    required=False,
                    next_action="set `ALPACA_API_KEY_ID` for paper account sync"
                    if not os.getenv("ALPACA_API_KEY_ID")
                    else "",
                ),
                _env_item(
                    "ALPACA_API_SECRET_KEY",
                    "ok" if os.getenv("ALPACA_API_SECRET_KEY") else "warning",
                    "presence only; value never exposed",
                    required=False,
                    next_action="set `ALPACA_API_SECRET_KEY` for paper account sync"
                    if not os.getenv("ALPACA_API_SECRET_KEY")
                    else "",
                ),
                _env_item(
                    "ALPACA_PAPER",
                    "ok"
                    if os.getenv("ALPACA_PAPER", "true").strip().lower() == "true"
                    else "blocked",
                    os.getenv("ALPACA_PAPER", "true"),
                    required=True,
                    next_action="keep `ALPACA_PAPER=true`; real-money writes are out of scope",
                ),
                _env_item("ALPACA_API_BASE_URL", "ok", alpaca_api_base_url(), required=False),
                _env_item("ALPACA_DATA_FEED", "ok", data_feed(), required=False),
            ],
        },
        {
            "section": "notifications",
            "title": "Notifications",
            "items": [
                _env_item(
                    "config/notifications.yaml",
                    "ok" if notification_status.config_exists else "warning",
                    notification_status.config_path,
                    required=False,
                    next_action="create `config/notifications.yaml` to customize policies"
                    if not notification_status.config_exists
                    else "",
                ),
                _env_item(
                    "Telegram enabled",
                    "ok" if notification_status.telegram_enabled else "warning",
                    str(notification_status.telegram_enabled).lower(),
                    required=False,
                ),
                _env_item(
                    notification_status.telegram_bot_token_env,
                    "ok" if notification_status.telegram_bot_token_present else "warning",
                    "presence only; value never exposed",
                    required=False,
                ),
                _env_item(
                    notification_status.telegram_chat_id_env,
                    "ok" if notification_status.telegram_chat_id_present else "warning",
                    "presence only; value never exposed",
                    required=False,
                ),
            ],
        },
        {
            "section": "deployment",
            "title": "Deployment",
            "items": [
                _env_item(
                    "Deployment mode",
                    "ok",
                    "VPS-hosted Dashboard; strategy work remains local/file-first",
                    required=True,
                ),
                _env_item(
                    "OPEN_COMPOSER_DASHBOARD_TOKEN",
                    "ok" if auth_required else "warning",
                    "required before exposing the VPS Dashboard; value never exposed",
                    required=False,
                    next_action="set `OPEN_COMPOSER_DASHBOARD_TOKEN` or run `scripts/deploy-vps.sh`"
                    if not auth_required
                    else "",
                ),
                _env_item(
                    "OC_DASHBOARD_ALLOWED_ORIGIN",
                    "ok" if dashboard_allowed_origin() else "warning",
                    dashboard_allowed_origin() or "not restricted; acceptable for localhost only",
                    required=False,
                ),
            ],
        },
    ]
    all_items = [item for section in sections for item in section["items"]]
    blockers = [
        item["name"] for item in all_items if item["required"] and item["status"] == "blocked"
    ]
    warnings = [item["name"] for item in all_items if item["status"] == "warning"]
    status = "blocked" if blockers else "warning" if warnings else "ok"
    return {
        "schema_version": 1,
        "generated_at": _now_iso(),
        "status": status,
        "root": root.as_posix(),
        "serve_root": serve_root.as_posix(),
        "auth_required": auth_required,
        "sections": sections,
        "blocked_items": blockers,
        "warning_items": warnings,
        "notes": [
            "Secrets are never returned by this API; only presence is shown.",
            "Canonical deployment is VPS-hosted Dashboard plus local/file-first execution.",
            "Vercel is not required for normal deployment.",
            "Dashboard does not run long backtests or broker writes in the browser.",
            "Real-money broker write access remains out of scope for this MVP.",
        ],
    }


def dashboard_request_authorized(
    headers: Mapping[str, str],
    api_token: str | None,
) -> bool:
    if not api_token:
        return True
    provided = str(headers.get("X-Open-Composer-Token", "")).strip()
    authorization = str(headers.get("Authorization", "")).strip()
    if not provided and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    return secrets.compare_digest(provided, api_token)


def build_dashboard_catalog_payload(root: Path) -> dict[str, Any]:
    catalog = build_dashboard_catalog(root)
    return catalog.model_dump(mode="json")


def build_project_create_payload(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    project, request = create_project(StrategyProjectCreate.model_validate(payload), root)
    response: dict[str, Any] = {
        "project": project.model_dump(mode="json"),
        "project_path": f"projects/{project.project_id}/project.yaml",
        "context_path": f"projects/{project.project_id}/context.md",
    }
    if request is not None:
        response["agent_request"] = request.model_dump(mode="json")
        response["agent_request_path"] = f"reports/agent_requests/{request.request_id}.json"
    return response


def build_project_state_payload(
    root: Path, project_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    action = str(payload.get("action", "")).strip()
    request = None
    if action == "stop":
        project = load_project(project_id, root)
        project.iteration.user_requested_stop = True
        project.iteration.stop_reason = "user_requested_stop"
        project.next_action = "iteration_stopped_by_user"
        write_project(project, root)
    elif action == "archive":
        project = update_project_state(project_id, "retired", root, next_action="archived")
        project.archived = True
        write_project(project, root)
    elif action == "continue":
        direction = str(payload.get("direction") or "continue_iteration")
        from open_composer.research.iteration_controller import create_project_iteration_request

        result = create_project_iteration_request(
            project_id,
            root,
            rounds=int(payload.get("rounds") or 1),
            advice=direction,
            requested_by=str(payload.get("requested_by") or "dashboard"),
        )
        project = result.project
        request = result.agent_request
        iteration_plan_path = result.iteration_plan_path
        artifact_state_path = result.iteration_plan.artifact_state_path
    elif action == "paper_review":
        project = update_project_state(
            project_id,
            "paper_review",
            root,
            next_action="run_paper_readiness_review",
        )
        project.paper.status = "review_requested"
        write_project(project, root)
        write_project_context(project, root, task="Run paper readiness review for this project.")
        request = create_agent_request(
            AgentRequestCreate(
                requested_by=str(payload.get("requested_by") or "dashboard"),
                task_type="review",
                title=f"Paper review strategy project: {project.name}",
                prompt=project_agent_prompt(project, "Run paper readiness review."),
                related_paths=[
                    f"projects/{project.project_id}/project.yaml",
                    f"projects/{project.project_id}/context.md",
                    *([project.current_spec_path] if project.current_spec_path else []),
                ],
            ),
            root,
        )
    else:
        raise ValueError("action must be one of: stop, archive, continue, paper_review")
    response = {"project": project.model_dump(mode="json")}
    if request is not None:
        response["agent_request"] = request.model_dump(mode="json")
        response["agent_request_path"] = f"reports/agent_requests/{request.request_id}.json"
    if "iteration_plan_path" in locals():
        response["iteration_plan_path"] = iteration_plan_path
    if "artifact_state_path" in locals():
        response["artifact_state_path"] = artifact_state_path
    return response


def build_dashboard_command_plan_payload(
    root: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    action = str(payload.get("action", "")).strip()
    reason = str(payload.get("reason", ""))
    requested_by = str(payload.get("requested_by", "dashboard"))
    allowed: set[str] = {
        "paper.status.refresh",
        "paper.monitor.refresh",
        "paper.sync.orders",
        "paper.sync.account",
        "paper.kill_switch.enable",
        "paper.kill_switch.clear",
        "system.prepare_workspace",
        "system.readiness.refresh",
        "strategy.draft",
        "strategy.workflow.verify",
        "strategy.validate",
        "strategy.capabilities.refresh",
        "strategy.approve",
        "strategy.activate.manual",
        "strategy.activate.paper_auto",
        "strategy.backtest.rerun",
        "strategy.scan.rerun",
        "strategy.disable",
    }
    if action not in allowed:
        raise DashboardCommandError(f"action must be one of: {', '.join(sorted(allowed))}")
    strategy_path = str(payload.get("strategy_path", "")).strip() or None
    data_source = str(payload.get("data_source", "keep")).strip() or "keep"
    idea = str(payload.get("idea", "")).strip()
    use_llm = bool(payload.get("use_llm", False))
    plan = build_dashboard_command_plan(
        action,  # type: ignore[arg-type]
        root,
        reason=reason,
        requested_by=requested_by,
        strategy_path=strategy_path,
        data_source=data_source,
        idea=idea,
        use_llm=use_llm,
    )
    path = write_dashboard_command_plan(plan, root)
    response = plan.model_dump(mode="json")
    response["plan_path"] = path.relative_to(root).as_posix()
    return response


def build_dashboard_command_run_payload(
    root: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    plan_path = str(payload.get("plan_path", "")).strip()
    confirmation = str(payload.get("confirm", ""))
    executed_by = str(payload.get("executed_by", "dashboard"))
    if not plan_path:
        raise DashboardCommandError("plan_path is required")
    candidate = Path(plan_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if candidate != root.resolve() and not candidate.is_relative_to(root.resolve()):
        raise DashboardCommandError("plan_path must stay within the current workspace")
    plan = load_dashboard_command_plan(candidate)
    result = execute_dashboard_command_plan(
        plan,
        root,
        confirmation=confirmation,
        executed_by=executed_by,
    )
    return result.model_dump(mode="json")


def build_notification_config_payload(root: Path) -> dict[str, Any]:
    return notification_config_status(root).model_dump(mode="json")


def build_notification_log_payload(root: Path, *, limit: int = 50) -> dict[str, Any]:
    return {"notifications": read_notification_log(root, limit=limit)}


def build_notification_test_payload(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind", "signal_actionable")).strip() or "signal_actionable"
    severity = str(payload.get("severity", "info")).strip() or "info"
    dry_run = bool(payload.get("dry_run", False))
    if kind not in set(get_args(NotificationKind)):
        raise ValueError("invalid notification kind")
    if severity not in set(get_args(NotificationSeverity)):
        raise ValueError("invalid notification severity")
    record = send_test_notification(
        root,
        kind=kind,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        dry_run=dry_run,
    )
    return {"notification": record.model_dump(mode="json")}


def _env_item(
    name: str,
    status: str,
    detail: str,
    *,
    required: bool,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "detail": detail,
        "required": required,
        "next_action": next_action,
    }


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _query_limit(query: str, default: int = 50) -> int:
    values = parse_qs(query).get("limit", [])
    if not values:
        return default
    try:
        return max(1, min(500, int(values[0])))
    except ValueError:
        return default
