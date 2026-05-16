from __future__ import annotations

import json
import secrets
from collections.abc import Mapping
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, get_args
from urllib.parse import parse_qs, urlparse

from open_composer.config import dashboard_allowed_origin, dashboard_api_token
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
from open_composer.notifications import (
    notification_config_status,
    read_notification_log,
    send_test_notification,
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


def _query_limit(query: str, default: int = 50) -> int:
    values = parse_qs(query).get("limit", [])
    if not values:
        return default
    try:
        return max(1, min(500, int(values[0])))
    except ValueError:
        return default
