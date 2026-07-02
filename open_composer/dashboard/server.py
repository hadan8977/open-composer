import difflib
import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, get_args
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import yaml

from open_composer.agent_backend import get_agent_backend
from open_composer.capabilities import evaluate_capabilities, load_registry
from open_composer.config import (
    agent_backend_name,
    alpaca_api_base_url,
    cloudflare_access_audience,
    cloudflare_access_team_domain,
    dashboard_allowed_emails,
    dashboard_allowed_origin,
    dashboard_api_token,
    dashboard_auth_mode,
    data_feed,
    default_openai_model,
    ensure_dir,
    openai_api_key_env_name,
    openai_base_url,
    openai_base_url_source,
    optional_env_status,
)
from open_composer.dashboard.auth import (
    dashboard_auth_required,
    dashboard_request_authorized,
)
from open_composer.dashboard.catalog import build_dashboard_catalog
from open_composer.dashboard.commands import (
    DashboardCommandError,
    _execute_strategy_command,
    build_dashboard_command_plan,
    execute_dashboard_command_plan,
    load_dashboard_command_plan,
    resolve_dashboard_serve_root,
    write_dashboard_command_plan,
)
from open_composer.feature_packets import default_materialized_feature_path
from open_composer.models.notification import NotificationKind, NotificationSeverity
from open_composer.models.project import QueueCommandKind, StrategyProjectCreate
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.notifications import (
    notification_config_status,
    read_notification_log,
    send_test_notification,
)
from open_composer.paper_controls import (
    build_paper_alerts,
    build_paper_status,
    clear_paper_kill_switch,
    enable_paper_kill_switch,
    refresh_paper_monitor,
    write_paper_status,
)
from open_composer.projects import (
    append_queue,
    append_trace,
    create_project,
    list_projects,
    load_project,
    read_queue,
    read_trace_tail,
    trace_path,
    update_project_state,
    write_project,
    write_project_context,
)
from open_composer.research.drafter import draft_strategy_from_idea_with_status
from open_composer.strategy_lifecycle import resolve_strategy_path
from open_composer.strategy_versions import strategy_content_hash


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
                    auth_required=dashboard_auth_required(self.dashboard_token),
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
                    auth_required=dashboard_auth_required(self.dashboard_token),
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
        if path == "/api/settings/environment":
            self._send_json(
                build_dashboard_environment_payload(
                    self.dashboard_root,
                    Path(self.directory),
                    auth_required=dashboard_auth_required(self.dashboard_token),
                )
            )
            return
        if path == "/api/settings/capabilities":
            self._send_json(build_settings_capabilities_payload(self.dashboard_root))
            return
        if path == "/api/settings/agent-backend":
            self._send_json(build_settings_agent_backend_payload(self.dashboard_root))
            return
        if path == "/api/settings/notifications":
            self._send_json(build_notification_config_payload(self.dashboard_root))
            return
        if path == "/api/activity/trace":
            self._send_json(build_activity_trace_payload(self.dashboard_root, parsed.query))
            return
        if path == "/api/build/templates":
            self._send_json(build_templates_payload())
            return
        if path.startswith("/api/factors/"):
            parts = _api_parts(path)
            if len(parts) == 3 and parts[2] == "decay":
                self._handle_json_result(build_factor_decay_payload, parts[1])
                return
        if path.startswith("/api/projects/"):
            parts = _api_parts(path)
            if len(parts) == 2:
                self._handle_json_result(build_project_detail_payload, parts[1])
                return
            if len(parts) == 3 and parts[2] == "context":
                self._handle_json_result(build_project_context_payload, parts[1], parsed.query)
                return
            if len(parts) == 3 and parts[2] == "queue":
                self._handle_json_result(build_project_queue_payload, parts[1], parsed.query)
                return
            if len(parts) == 3 and parts[2] == "trace":
                self._handle_json_result(build_project_trace_payload, parts[1], parsed.query)
                return
            if len(parts) == 4 and parts[2] == "trace" and parts[3] == "stream":
                self._handle_project_trace_stream(parts[1], parsed.query)
                return
        if path.startswith("/api/strategies/"):
            parts = _api_parts(path)
            if len(parts) == 2:
                self._handle_json_result(build_strategy_detail_payload, parts[1])
                return
            if len(parts) == 3 and parts[2] == "spec":
                self._handle_json_result(build_strategy_spec_payload, parts[1])
                return
            if len(parts) == 4 and parts[2] == "spec" and parts[3] == "diff":
                self._handle_json_result(build_strategy_spec_diff_payload, parts[1], parsed.query)
                return
            if len(parts) == 3 and parts[2] == "runs":
                self._handle_json_result(build_strategy_runs_payload, parts[1])
                return
            if len(parts) == 3 and parts[2] == "signals":
                self._handle_json_result(build_strategy_signals_payload, parts[1], parsed.query)
                return
            if len(parts) == 3 and parts[2] == "equity":
                self._handle_json_result(build_strategy_equity_payload, parts[1], parsed.query)
                return
            if len(parts) == 3 and parts[2] == "drawdown":
                self._handle_json_result(build_strategy_drawdown_payload, parts[1], parsed.query)
                return
            if len(parts) == 5 and parts[2] == "runs" and parts[4] == "signals":
                self._handle_json_result(build_strategy_run_signals_payload, parts[1], parts[3])
                return
            if len(parts) == 5 and parts[2] == "runs" and parts[4] == "equity":
                self._handle_json_result(build_strategy_run_equity_payload, parts[1], parts[3])
                return
            if len(parts) == 5 and parts[2] == "llm-factors" and parts[4] == "prompt":
                self._handle_json_result(build_llm_factor_prompt_payload, parts[1], parts[3])
                return
        if path == "/api/paper/positions":
            self._send_json(build_paper_positions_payload(self.dashboard_root))
            return
        if path == "/api/paper/orders":
            self._send_json(build_paper_orders_payload(self.dashboard_root))
            return
        if path == "/api/paper/alerts":
            self._send_json(build_paper_alerts_payload(self.dashboard_root))
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
        if path.startswith("/api/projects/"):
            parts = _api_parts(path)
            if len(parts) == 3 and parts[2] == "queue":
                self._handle_project_queue(parts[1], payload)
                return
            if len(parts) == 3 and parts[2] == "stop":
                self._handle_project_stop(parts[1], payload)
                return
        if path.startswith("/api/strategies/"):
            parts = _api_parts(path)
            if len(parts) == 4 and parts[2] == "spec" and parts[3] == "accept":
                self._handle_strategy_spec_accept(parts[1], payload)
                return
            if len(parts) == 4 and parts[2] == "spec" and parts[3] == "reject":
                self._handle_strategy_spec_reject(parts[1], payload)
                return
            if len(parts) == 4 and parts[2] == "actions":
                self._handle_strategy_action(parts[1], parts[3], payload)
                return
            if len(parts) == 5 and parts[2] == "llm-factors" and parts[4] == "prompt":
                self._handle_json_result(
                    build_llm_factor_prompt_update_payload,
                    parts[1],
                    parts[3],
                    payload,
                )
                return
        if path == "/api/build/draft":
            self._handle_build_draft(payload)
            return
        if path == "/api/settings/capabilities/test":
            self._handle_settings_capabilities_test(payload)
            return
        if path == "/api/settings/agent-backend":
            self._handle_settings_agent_backend(payload)
            return
        if path == "/api/paper/kill-switch":
            self._handle_paper_kill_switch(payload)
            return
        if path == "/api/paper/sync":
            self._handle_paper_sync(payload)
            return
        if path == "/api/paper/monitor/refresh":
            self._handle_paper_monitor_refresh(payload)
            return
        if path == "/api/notifications/test":
            self._handle_notification_test(payload)
            return
        self.send_error(404, "Unknown dashboard API path")

    def _handle_json_result(self, builder: Any, *args: Any) -> None:
        try:
            self._send_json(builder(self.dashboard_root, *args))
        except (ValueError, FileNotFoundError, OSError, yaml.YAMLError) as exc:
            self._send_json({"error": str(exc)}, status=400)

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

    def _handle_project_queue(self, project_id: str, payload: dict[str, Any]) -> None:
        try:
            self._send_json(
                build_project_queue_create_payload(self.dashboard_root, project_id, payload)
            )
        except (ValueError, FileNotFoundError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_project_stop(self, project_id: str, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_project_stop_payload(self.dashboard_root, project_id, payload))
        except (ValueError, FileNotFoundError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_strategy_action(
        self, strategy_name: str, action: str, payload: dict[str, Any]
    ) -> None:
        try:
            self._send_json(
                build_strategy_action_payload(self.dashboard_root, strategy_name, action, payload)
            )
        except (ValueError, FileNotFoundError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_strategy_spec_accept(self, strategy_name: str, payload: dict[str, Any]) -> None:
        try:
            self._send_json(
                build_strategy_spec_accept_payload(self.dashboard_root, strategy_name, payload)
            )
        except (ValueError, FileNotFoundError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_strategy_spec_reject(self, strategy_name: str, payload: dict[str, Any]) -> None:
        try:
            self._send_json(
                build_strategy_spec_reject_payload(self.dashboard_root, strategy_name, payload)
            )
        except (ValueError, FileNotFoundError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_build_draft(self, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_draft_payload(self.dashboard_root, payload), status=201)
        except (ValueError, OSError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_settings_capabilities_test(self, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_settings_capabilities_test_payload(self.dashboard_root, payload))
        except (ValueError, OSError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_settings_agent_backend(self, payload: dict[str, Any]) -> None:
        try:
            self._send_json(
                build_settings_agent_backend_update_payload(self.dashboard_root, payload)
            )
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_paper_kill_switch(self, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_paper_kill_switch_payload(self.dashboard_root, payload))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_paper_sync(self, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_paper_sync_payload(self.dashboard_root, payload))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_paper_monitor_refresh(self, payload: dict[str, Any]) -> None:
        try:
            self._send_json(build_paper_monitor_refresh_payload(self.dashboard_root, payload))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_project_trace_stream(self, project_id: str, query: str) -> None:
        try:
            self._send_trace_stream(project_id, query)
        except (BrokenPipeError, ConnectionResetError):
            return
        except (ValueError, FileNotFoundError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _send_trace_stream(self, project_id: str, query: str) -> None:
        load_project(project_id, self.dashboard_root)
        values = parse_qs(query)
        last_ts = self.headers.get("Last-Event-ID") or values.get("since_ts", [""])[0] or ""
        ticks = _query_int(query, "ticks", default=300, minimum=1, maximum=3600)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        for _ in range(ticks):
            rows = _read_trace_since(project_id, last_ts, self.dashboard_root)
            for row in rows:
                last_ts = str(row.get("ts") or last_ts)
                payload = json.dumps(row, ensure_ascii=False)
                self.wfile.write(f"id: {last_ts}\ndata: {payload}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b": heartbeat\n\n")
            self.wfile.flush()
            time.sleep(1.0)

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
        query = urlparse(self.path).query
        if dashboard_request_authorized(self.headers, self.dashboard_token, query=query):
            return True
        self._send_json({"error": "Dashboard API authentication is required."}, status=401)
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
    auth_mode = dashboard_auth_mode()
    with create_dashboard_server(root, host=host, port=port, api_token=token) as server:
        print(f"dashboard serving http://{host}:{port}")
        print(f"root={resolve_dashboard_serve_root(root)}")
        print(
            f"api_auth={'required' if dashboard_auth_required(token) else 'disabled'} "
            f"mode={auth_mode}"
        )
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
    auth_mode = dashboard_auth_mode()
    token_required = auth_mode in {"token", "cloudflare_access_or_token"}
    cloudflare_required = auth_mode in {"cloudflare_access", "cloudflare_access_or_token"}
    allowed_emails = sorted(dashboard_allowed_emails())
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
                    "OPEN_COMPOSER_DASHBOARD_AUTH_MODE",
                    "ok",
                    auth_mode,
                    required=False,
                ),
                _env_item(
                    "OPEN_COMPOSER_DASHBOARD_TOKEN",
                    "ok" if (not token_required or auth_required) else "warning",
                    "required for token mode; optional Cloudflare Access fallback; "
                    "value never exposed",
                    required=False,
                    next_action="set `OPEN_COMPOSER_DASHBOARD_TOKEN` or run `scripts/deploy-vps.sh`"
                    if token_required and not auth_required
                    else "",
                ),
                _env_item(
                    "OC_DASHBOARD_ALLOWED_ORIGIN",
                    "ok" if dashboard_allowed_origin() else "warning",
                    dashboard_allowed_origin() or "not restricted; acceptable for localhost only",
                    required=False,
                ),
                _env_item(
                    "OC_CLOUDFLARE_ACCESS_TEAM_DOMAIN",
                    "ok"
                    if (not cloudflare_required or cloudflare_access_team_domain())
                    else "blocked",
                    cloudflare_access_team_domain() or "missing",
                    required=cloudflare_required,
                    next_action="set your Cloudflare team domain, e.g. https://team.cloudflareaccess.com"
                    if cloudflare_required and not cloudflare_access_team_domain()
                    else "",
                ),
                _env_item(
                    "OC_CLOUDFLARE_ACCESS_AUD",
                    "ok"
                    if (not cloudflare_required or cloudflare_access_audience())
                    else "blocked",
                    "presence only; value never exposed"
                    if cloudflare_access_audience()
                    else "missing",
                    required=cloudflare_required,
                    next_action="copy the Access application AUD tag from Cloudflare"
                    if cloudflare_required and not cloudflare_access_audience()
                    else "",
                ),
                _env_item(
                    "OC_DASHBOARD_ALLOWED_EMAILS",
                    "ok" if (not cloudflare_required or allowed_emails) else "blocked",
                    ", ".join(allowed_emails) if allowed_emails else "missing",
                    required=cloudflare_required,
                    next_action="set the comma-separated email allowlist for Dashboard users"
                    if cloudflare_required and not allowed_emails
                    else "",
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


def build_dashboard_catalog_payload(root: Path) -> dict[str, Any]:
    catalog = build_dashboard_catalog(root)
    return catalog.model_dump(mode="json")


def build_factor_decay_payload(root: Path, factor_id: str) -> dict[str, Any]:
    from open_composer.research.factor_decay import build_factor_decay_payload as _build

    return _build(root, factor_id)


BUILD_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "id": "pure_quant_qqq_momentum",
        "name": "QQQ intraday momentum",
        "strategy_kind": "pure_quant",
        "tag": "single-symbol",
        "thesis": "Follow QQQ intraday trend with bounded turnover and execution review.",
        "idea": (
            "Create a QQQ 15m pure quant momentum StrategySpec with EMA trend, volume "
            "filter, bounded parameter ranges, benchmark family, Factor Quality, "
            "Execution Reality, and no paper readiness claim until gates pass."
        ),
    },
    {
        "id": "quant_with_llm_review_news",
        "name": "QQQ quant with LLM review",
        "strategy_kind": "quant_with_llm_review",
        "tag": "llm-review",
        "thesis": "Keep trading deterministic while LLM review explains news and context risk.",
        "idea": (
            "Create a QQQ 15m strategy whose signals remain deterministic, with LLM review "
            "used only as advisory evidence for news/context interpretation."
        ),
    },
    {
        "id": "quant_with_llm_factor_sentiment",
        "name": "Quant with LLM factor",
        "strategy_kind": "quant_with_llm_factor",
        "tag": "llm-factor",
        "thesis": "Test whether a point-in-time LLM sentiment factor adds marginal lift.",
        "idea": (
            "Create a QQQ 15m quant strategy with a replayable LLM sentiment factor. The "
            "factor must be materialized into point-in-time packets before it affects "
            "backtests or paper readiness."
        ),
    },
    {
        "id": "router_meta_selection",
        "name": "Router meta-selection",
        "strategy_kind": "router",
        "tag": "router",
        "thesis": "Select between candidate sleeves through target weights and rebalance intents.",
        "idea": (
            "Create a router-style StrategyProject for ETF sleeve selection with explicit "
            "target weights, rebalance intent evidence, cost stress, and paper-readiness blockers."
        ),
    },
)


DASHBOARD_CLI_PARITY: dict[str, str] = {
    "POST /api/build/draft": "oc strategy draft",
    "POST /api/projects/{id}/queue": "oc project continue",
    "POST /api/projects/{id}/stop": "oc agent stop",
    "POST /api/strategies/{name}/actions/evidence": "oc strategy evidence",
    "POST /api/strategies/{name}/actions/materialize": "oc feature materialize",
    "POST /api/strategies/{name}/actions/promote": "oc strategy approve",
    "POST /api/strategies/{name}/actions/activate": "oc strategy activate",
    "POST /api/strategies/{name}/actions/disable": "oc strategy disable",
    "POST /api/strategies/{name}/spec/accept": "oc strategy approve",
    "POST /api/paper/kill-switch": "oc paper kill-switch",
    "POST /api/paper/sync": "oc paper sync / oc paper sync-account",
    "POST /api/paper/monitor/refresh": "oc paper monitor",
    "POST /api/settings/capabilities/test": "oc capability test",
    "POST /api/settings/agent-backend": "oc agent use",
}


def build_templates_payload() -> dict[str, Any]:
    return {
        "templates": list(BUILD_TEMPLATES),
        "strategy_kinds": [
            {
                "id": "pure_quant",
                "label": "Pure quant",
                "description": "Deterministic factors and rules only.",
            },
            {
                "id": "quant_with_llm_review",
                "label": "Quant + LLM review",
                "description": "LLM is advisory and never directly changes trading signals.",
            },
            {
                "id": "quant_with_llm_factor",
                "label": "Quant + LLM factor",
                "description": "LLM output is materialized into point-in-time replay packets.",
            },
            {
                "id": "router",
                "label": "Router",
                "description": "Target weights, rebalance intents, and execution observations.",
            },
        ],
    }


def build_project_detail_payload(root: Path, project_id: str) -> dict[str, Any]:
    project = load_project(project_id, root)
    context_path = root / "projects" / project.project_id / "context.md"
    context = _read_text(context_path, max_bytes=4096)
    backend = get_agent_backend()
    status = backend.status(project.project_id, root)
    return {
        "project": project.model_dump(mode="json"),
        "project_path": f"projects/{project.project_id}/project.yaml",
        "context_path": f"projects/{project.project_id}/context.md",
        "context_head": context,
        "queue": [
            item.model_dump(mode="json", by_alias=True)
            for item in read_queue(project_id, root)[-50:]
        ],
        "trace": [item.model_dump(mode="json") for item in read_trace_tail(project_id, 50, root)],
        "agent_backend": _agent_status_payload(status),
    }


def build_project_context_payload(root: Path, project_id: str, query: str = "") -> dict[str, Any]:
    load_project(project_id, root)
    max_bytes = _query_int(query, "max_bytes", default=128 * 1024, minimum=1, maximum=128 * 1024)
    path = root / "projects" / project_id / "context.md"
    return {
        "project_id": project_id,
        "path": f"projects/{project_id}/context.md",
        "text": _read_text(path, max_bytes=max_bytes),
        "max_bytes": max_bytes,
    }


def build_project_queue_payload(root: Path, project_id: str, query: str = "") -> dict[str, Any]:
    load_project(project_id, root)
    limit = _query_int(query, "limit", default=100, minimum=1, maximum=500)
    include_consumed = _query_bool(query, "include_consumed", default=True)
    commands = read_queue(project_id, root)
    if not include_consumed:
        commands = [item for item in commands if item.consumed_at is None]
    return {
        "project_id": project_id,
        "queue_path": f"projects/{project_id}/queue.jsonl",
        "commands": [item.model_dump(mode="json", by_alias=True) for item in commands[-limit:]],
        "pending_count": sum(1 for item in commands if item.consumed_at is None),
    }


def build_project_trace_payload(root: Path, project_id: str, query: str = "") -> dict[str, Any]:
    load_project(project_id, root)
    values = parse_qs(query)
    since_ts = values.get("since_ts", [""])[0]
    limit = _query_int(query, "limit", default=100, minimum=1, maximum=500)
    rows = _read_trace_since(project_id, since_ts, root)
    return {
        "project_id": project_id,
        "trace_path": f"projects/{project_id}/trace.jsonl",
        "entries": rows[-limit:],
    }


def build_activity_trace_payload(root: Path, query: str = "") -> dict[str, Any]:
    values = parse_qs(query)
    project_filter = str(values.get("project", [""])[0] or "").strip()
    kind_filter = str(values.get("kind", [""])[0] or "").strip()
    since_ts = str(values.get("since_ts", [""])[0] or "").strip()
    limit = _query_int(query, "limit", default=100, minimum=1, maximum=1000)
    rows: list[dict[str, Any]] = []
    for project in list_projects(root):
        if (
            project_filter
            and project.project_id != project_filter
            and project.name != project_filter
        ):
            continue
        for row in _read_jsonl_rows(trace_path(project.project_id, root)):
            ts = str(row.get("ts") or "")
            if since_ts and ts <= since_ts:
                continue
            agent = str(row.get("agent") or "")
            operation = str(row.get("operation") or "")
            if kind_filter and kind_filter not in {agent, operation}:
                continue
            rows.append(
                {
                    **row,
                    "project_id": project.project_id,
                    "project_name": project.name,
                }
            )
    rows.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    return {
        "entries": rows[:limit],
        "limit": limit,
        "project": project_filter or None,
        "kind": kind_filter or None,
        "since_ts": since_ts or None,
    }


def build_project_queue_create_payload(
    root: Path, project_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    kind = str(payload.get("kind") or "advice").strip()
    if kind not in set(get_args(QueueCommandKind)):
        raise ValueError("invalid queue command kind")
    body = str(payload.get("body") or payload.get("message") or "").strip()
    metadata = _json_mapping(payload.get("metadata"))
    metadata = {
        **metadata,
        "via": "dashboard",
        "idempotency_key": str(payload.get("idempotency_key") or uuid4().hex),
    }
    command = append_queue(
        project_id,
        kind=kind,  # type: ignore[arg-type]
        body=body,
        via="dashboard",
        metadata=metadata,
        root=root,
    )
    append_trace(
        project_id,
        agent="dashboard",
        operation="dashboard_queue_command",
        queue_command_id=command.id,
        metadata={"via": "dashboard", "kind": kind},
        root=root,
    )
    backend = get_agent_backend()
    backend_command_id = backend.send_command(
        project_id,
        kind=kind,
        body=body,
        root=root,
        existing_command_id=command.id,
    )
    return {
        "status": "queued",
        "queue_command_id": backend_command_id,
        "queue_command": command.model_dump(mode="json", by_alias=True),
        "queue_path": f"projects/{project_id}/queue.jsonl",
        "trace_path": f"projects/{project_id}/trace.jsonl",
        "agent_backend": backend.name,
    }


def build_project_stop_payload(
    root: Path, project_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    reason = str(payload.get("reason") or "User requested stop from Dashboard.").strip()
    project = load_project(project_id, root)
    project.iteration.user_requested_stop = True
    project.iteration.stop_reason = "user_requested_stop"
    project.next_action = "iteration_stopped_by_user"
    write_project(project, root)
    command = append_queue(project_id, kind="stop", body=reason, via="dashboard", root=root)
    append_trace(
        project_id,
        agent="dashboard",
        operation="dashboard_stop_requested",
        queue_command_id=command.id,
        metadata={"via": "dashboard", "reason": reason},
        root=root,
    )
    backend = get_agent_backend()
    if backend.name != "file_queue":
        backend.stop(project_id, root)
    return {
        "status": "queued",
        "project": project.model_dump(mode="json"),
        "queue_command_id": command.id,
        "queue_path": f"projects/{project_id}/queue.jsonl",
        "trace_path": f"projects/{project_id}/trace.jsonl",
    }


def build_strategy_detail_payload(root: Path, strategy_name: str) -> dict[str, Any]:
    catalog = build_dashboard_catalog(root).model_dump(mode="json")
    strategy = _find_catalog_strategy(catalog, strategy_name)
    if strategy is None:
        raise FileNotFoundError(f"strategy not found: {strategy_name}")
    resolved_name = str(
        strategy.get("strategy_id") or strategy.get("strategy_name") or strategy_name
    )
    project_id = _project_id_for_strategy(root, resolved_name)
    project_payload = (
        build_project_detail_payload(root, project_id)
        if (root / "projects" / project_id).exists()
        else None
    )
    runs = [
        row
        for row in catalog.get("runs", [])
        if isinstance(row, dict)
        and str(row.get("strategy_id") or row.get("strategy_name")) == resolved_name
    ]
    signals = [
        row
        for row in catalog.get("signals", [])
        if isinstance(row, dict)
        and str(row.get("strategy_id") or row.get("strategy_name")) == resolved_name
    ]
    paper_readiness = [
        row
        for row in catalog.get("paper_readiness_reports", [])
        if isinstance(row, dict)
        and str(row.get("strategy_id") or row.get("strategy_name")) == resolved_name
    ]
    research = [
        row
        for row in catalog.get("research_reports", [])
        if isinstance(row, dict) and str(row.get("strategy_name")) == resolved_name
    ]
    return {
        "strategy": strategy,
        "project_id": project_id,
        "project": project_payload["project"] if project_payload else None,
        "queue": project_payload["queue"] if project_payload else [],
        "trace": project_payload["trace"] if project_payload else [],
        "runs": sorted(runs, key=lambda row: str(row.get("run_id", "")), reverse=True),
        "signals": sorted(signals, key=lambda row: str(row.get("timestamp", "")), reverse=True),
        "paper_readiness": paper_readiness,
        "research_reports": research,
        "spec": build_strategy_spec_payload(root, resolved_name),
        "equity": build_strategy_equity_payload(root, resolved_name, ""),
        "drawdown": build_strategy_drawdown_payload(root, resolved_name, ""),
        "llm_factors": _llm_factor_rows(root, resolved_name),
        "pass_reasons": _pass_reasons(project_payload, paper_readiness, research),
    }


def build_strategy_spec_payload(root: Path, strategy_name: str) -> dict[str, Any]:
    active_path = resolve_strategy_path(strategy_name, root)
    active_text = active_path.read_text(encoding="utf-8")
    active_spec = load_strategy_spec(active_path)
    draft_path = root / "strategy_specs" / "drafts" / f"{active_spec.name}.yaml"
    draft_text = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""
    return {
        "strategy_name": active_spec.name,
        "active_path": _relpath(active_path, root),
        "active_hash": strategy_content_hash(active_spec),
        "active_text": active_text,
        "draft_path": _relpath(draft_path, root) if draft_path.exists() else None,
        "draft_text": draft_text,
        "draft_hash": strategy_content_hash(load_strategy_spec(draft_path))
        if draft_path.exists()
        else None,
        "has_pending_draft": draft_path.exists() and draft_path.resolve() != active_path.resolve(),
    }


def build_strategy_spec_diff_payload(
    root: Path, strategy_name: str, query: str = ""
) -> dict[str, Any]:
    payload = build_strategy_spec_payload(root, strategy_name)
    active_lines = str(payload["active_text"]).splitlines()
    draft_lines = str(payload["draft_text"] or "").splitlines()
    if not draft_lines:
        draft_lines = active_lines
    diff = list(
        difflib.unified_diff(
            active_lines,
            draft_lines,
            fromfile=str(payload["active_path"]),
            tofile=str(payload["draft_path"] or payload["active_path"]),
            lineterm="",
        )
    )
    return {**payload, "diff": diff}


def build_llm_factor_prompt_payload(
    root: Path, strategy_name: str, factor_name: str
) -> dict[str, Any]:
    spec_path, spec, factor = _load_llm_factor(root, strategy_name, factor_name)
    prompt_path = _resolve_dashboard_path(root, str(factor.prompt_template_path))
    prompt = prompt_path.read_text(encoding="utf-8")
    return {
        "strategy_name": spec.name,
        "factor_name": factor_name,
        "source_spec_path": _relpath(spec_path, root),
        "prompt_template_path": _relpath(prompt_path, root),
        "prompt": prompt,
        "prompt_hash": _hash_text(prompt),
        "needs_rematerialize": False,
    }


def build_llm_factor_prompt_update_payload(
    root: Path,
    strategy_name: str,
    factor_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    spec_path, spec, factor = _load_llm_factor(root, strategy_name, factor_name)
    prompt = str(payload.get("prompt") or "")
    if not prompt.strip():
        raise ValueError("prompt must not be empty")
    prompt_path = _resolve_dashboard_path(root, str(factor.prompt_template_path))
    ensure_dir(prompt_path.parent)
    prompt_path.write_text(prompt.rstrip() + "\n", encoding="utf-8")
    prompt_hash = _hash_text(prompt_path.read_text(encoding="utf-8"))
    project = _ensure_project_for_strategy(root, spec.name, spec_path)
    append_trace(
        project.project_id,
        agent="dashboard",
        operation="dashboard_edit_llm_factor_prompt",
        metadata={
            "factor": factor_name,
            "prompt_hash": prompt_hash,
            "prompt_template_path": _relpath(prompt_path, root),
            "needs_rematerialize": True,
        },
        root=root,
    )
    return {
        "status": "updated",
        "strategy_name": spec.name,
        "factor_name": factor_name,
        "prompt_template_path": _relpath(prompt_path, root),
        "prompt_hash": prompt_hash,
        "needs_rematerialize": True,
        "trace_path": f"projects/{project.project_id}/trace.jsonl",
    }


def build_strategy_runs_payload(root: Path, strategy_name: str) -> dict[str, Any]:
    catalog = build_dashboard_catalog(root).model_dump(mode="json")
    strategy = _find_catalog_strategy(catalog, strategy_name)
    if strategy is None:
        raise FileNotFoundError(f"strategy not found: {strategy_name}")
    resolved = str(strategy.get("strategy_id") or strategy_name)
    return {
        "strategy_name": resolved,
        "runs": [
            row
            for row in catalog.get("runs", [])
            if isinstance(row, dict)
            and str(row.get("strategy_id") or row.get("strategy_name")) == resolved
        ],
    }


def build_strategy_run_signals_payload(
    root: Path, strategy_name: str, run_id: str
) -> dict[str, Any]:
    return {
        "strategy_name": strategy_name,
        "run_id": run_id,
        "signals": _signal_rows(root, strategy_name=strategy_name, run_id=run_id),
    }


def build_strategy_signals_payload(
    root: Path, strategy_name: str, query: str = ""
) -> dict[str, Any]:
    limit = _query_int(query, "limit", default=200, minimum=1, maximum=1000)
    offset = _query_int(query, "offset", default=0, minimum=0, maximum=100000)
    rows = _signal_rows(root, strategy_name=strategy_name)
    return {
        "strategy_name": strategy_name,
        "signals": rows[offset : offset + limit],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    }


def build_strategy_equity_payload(
    root: Path, strategy_name: str, query: str = ""
) -> dict[str, Any]:
    run_id = parse_qs(query).get("run_id", [""])[0] if query else ""
    rows = _equity_rows(root, strategy_name=strategy_name, run_id=run_id or None)
    return {"strategy_name": strategy_name, "run_id": run_id or None, "points": rows}


def build_strategy_run_equity_payload(
    root: Path, strategy_name: str, run_id: str
) -> dict[str, Any]:
    return {
        "strategy_name": strategy_name,
        "run_id": run_id,
        "points": _equity_rows(root, strategy_name=strategy_name, run_id=run_id),
    }


def build_strategy_drawdown_payload(
    root: Path, strategy_name: str, query: str = ""
) -> dict[str, Any]:
    points = _equity_rows(root, strategy_name=strategy_name)
    peak: float | None = None
    drawdown: list[dict[str, Any]] = []
    for point in points:
        value = float(point.get("value") or 0)
        peak = value if peak is None else max(peak, value)
        drawdown.append(
            {
                "ts": point.get("ts"),
                "value": 0.0 if not peak else round((value / peak - 1) * 100, 4),
            }
        )
    return {"strategy_name": strategy_name, "points": drawdown}


def build_strategy_action_payload(
    root: Path, strategy_name: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    allowed = {"evidence", "materialize", "promote", "activate", "disable"}
    if action not in allowed:
        raise ValueError(f"strategy action must be one of: {', '.join(sorted(allowed))}")
    spec_path = resolve_strategy_path(strategy_name, root)
    spec = load_strategy_spec(spec_path)
    project = _ensure_project_for_strategy(root, spec.name, spec_path)
    if action in {"evidence", "materialize"}:
        command_id = _queue_strategy_action(root, project.project_id, action, spec_path, payload)
        return {
            "status": "queued",
            "strategy_name": spec.name,
            "project_id": project.project_id,
            "queue_command_id": command_id,
            "trace_path": f"projects/{project.project_id}/trace.jsonl",
        }
    if action == "promote":
        plan = build_dashboard_command_plan(
            "strategy.approve",
            root,
            reason=str(payload.get("reason") or "Dashboard promote"),
            requested_by="dashboard",
            strategy_path=spec_path,
        )
        output_paths, message = _execute_strategy_command(plan, root)
        append_trace(
            project.project_id,
            agent="dashboard",
            operation="dashboard_strategy_promote",
            metadata={"via": "dashboard", "output_paths": output_paths},
            root=root,
        )
        return {"status": "executed", "message": message, "output_paths": output_paths}
    if action == "activate":
        mode = str(payload.get("mode") or "manual").strip()
        plan = build_dashboard_command_plan(
            "strategy.activate.paper_auto" if mode == "paper_auto" else "strategy.activate.manual",
            root,
            reason=str(payload.get("reason") or "Dashboard activate"),
            requested_by="dashboard",
            strategy_path=spec_path,
            data_source=str(payload.get("data_source") or "keep"),
        )
        output_paths, message = _execute_strategy_command(plan, root)
        append_trace(
            project.project_id,
            agent="dashboard",
            operation="dashboard_strategy_activate",
            metadata={"via": "dashboard", "mode": mode, "output_paths": output_paths},
            root=root,
        )
        return {"status": "executed", "message": message, "output_paths": output_paths}
    plan = build_dashboard_command_plan(
        "strategy.disable",
        root,
        reason=str(payload.get("reason") or "Dashboard disable"),
        requested_by="dashboard",
        strategy_path=spec_path,
    )
    output_paths, message = _execute_strategy_command(plan, root)
    append_trace(
        project.project_id,
        agent="dashboard",
        operation="dashboard_strategy_disable",
        metadata={"via": "dashboard", "output_paths": output_paths},
        root=root,
    )
    return {"status": "executed", "message": message, "output_paths": output_paths}


def build_strategy_spec_accept_payload(
    root: Path, strategy_name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    draft_path = root / "strategy_specs" / "drafts" / f"{strategy_name}.yaml"
    if not draft_path.exists():
        raise FileNotFoundError(f"pending draft not found: {strategy_name}")
    plan = build_dashboard_command_plan(
        "strategy.approve",
        root,
        reason=str(payload.get("reason") or "Dashboard accept draft"),
        requested_by="dashboard",
        strategy_path=draft_path,
    )
    output_paths, message = _execute_strategy_command(plan, root)
    approved_path = root / output_paths[0]
    project = _ensure_project_for_strategy(root, strategy_name, approved_path)
    append_trace(
        project.project_id,
        agent="dashboard",
        operation="dashboard_spec_accept",
        metadata={
            "via": "dashboard",
            "draft_path": _relpath(draft_path, root),
            "output_paths": output_paths,
        },
        root=root,
    )
    return {"status": "accepted", "message": message, "output_paths": output_paths}


def build_strategy_spec_reject_payload(
    root: Path, strategy_name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    draft_path = root / "strategy_specs" / "drafts" / f"{strategy_name}.yaml"
    if not draft_path.exists():
        raise FileNotFoundError(f"pending draft not found: {strategy_name}")
    rejected_dir = root / "strategy_specs" / "retired" / "rejected"
    ensure_dir(rejected_dir)
    target = rejected_dir / f"{strategy_name}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.yaml"
    draft_path.replace(target)
    project = _ensure_project_for_strategy(root, strategy_name, target)
    append_trace(
        project.project_id,
        agent="dashboard",
        operation="dashboard_spec_reject",
        metadata={"via": "dashboard", "rejected_path": _relpath(target, root)},
        root=root,
    )
    return {"status": "rejected", "output_path": _relpath(target, root)}


def build_draft_payload(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    idea = str(payload.get("idea") or "").strip()
    if not idea:
        raise ValueError("idea is required")
    strategy_kind = str(payload.get("strategy_kind") or "pure_quant").strip()
    if strategy_kind not in {
        "pure_quant",
        "quant_with_llm_review",
        "quant_with_llm_factor",
        "router",
    }:
        raise ValueError("invalid strategy_kind")
    template_id = str(payload.get("template_id") or "").strip() or None
    thesis = str(payload.get("thesis") or "").strip() or idea
    use_llm = bool(payload.get("use_llm", False))
    result = draft_strategy_from_idea_with_status(idea, root, use_llm=use_llm)
    spec = load_strategy_spec(result.path)
    if strategy_kind == "quant_with_llm_factor":
        _write_llm_prompt_placeholder(root, spec.name)
    project, _ = create_project(
        StrategyProjectCreate(
            name=spec.name,
            thesis=thesis,
            idea=idea,
            template_id=template_id,
            requested_by="dashboard",
            current_spec_path=_relpath(result.path, root),
            max_rounds=int(payload.get("max_rounds") or 5),
            use_llm=use_llm,
            tags=[strategy_kind],
        ),
        root,
    )
    body = (
        "Review the newly drafted StrategySpec, validate it, and prepare the minimal "
        "next evidence actions. Keep StrategySpec as source of truth."
    )
    command = append_queue(
        project.project_id,
        kind="continue",
        body=body,
        via="dashboard",
        metadata={
            "via": "dashboard",
            "strategy_kind": strategy_kind,
            "template_id": template_id,
            "source_spec_path": _relpath(result.path, root),
        },
        root=root,
    )
    append_trace(
        project.project_id,
        agent="dashboard",
        operation="dashboard_build_draft",
        queue_command_id=command.id,
        metadata={
            "via": "dashboard",
            "strategy_kind": strategy_kind,
            "spec_path": _relpath(result.path, root),
            "used_llm": result.used_llm,
            "fallback_reason": result.fallback_reason,
        },
        root=root,
    )
    return {
        "status": "created",
        "project": project.model_dump(mode="json"),
        "strategy_name": spec.name,
        "spec_path": _relpath(result.path, root),
        "project_path": f"projects/{project.project_id}/project.yaml",
        "context_path": f"projects/{project.project_id}/context.md",
        "queue_command_id": command.id,
        "queue_path": f"projects/{project.project_id}/queue.jsonl",
        "trace_path": f"projects/{project.project_id}/trace.jsonl",
        "used_llm": result.used_llm,
        "fallback_reason": result.fallback_reason,
    }


def build_settings_capabilities_payload(root: Path) -> dict[str, Any]:
    registry = load_registry(root)
    evaluation_path = root / "reports" / "capabilities" / "evaluation.json"
    evaluations_by_id: dict[str, dict[str, Any]] = {}
    raw = _read_json_mapping(evaluation_path)
    for row in raw.get("evaluations", []) if isinstance(raw.get("evaluations"), list) else []:
        if isinstance(row, dict):
            evaluations_by_id[str(row.get("capability_id"))] = row
    return {
        "registry_version": registry.version,
        "evaluation_path": _relpath(evaluation_path, root) if evaluation_path.exists() else None,
        "capabilities": [
            {
                **capability.model_dump(mode="json"),
                "evaluation": evaluations_by_id.get(capability.id),
            }
            for capability in registry.capabilities
        ],
    }


def build_settings_capabilities_test_payload(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    evaluations = evaluate_capabilities(root)
    return {
        "status": "executed",
        "output_paths": [
            "reports/capabilities/evaluation.json",
            "reports/capabilities/evaluation.md",
        ],
        "evaluations": [item.model_dump(mode="json") for item in evaluations],
    }


def build_settings_agent_backend_payload(root: Path) -> dict[str, Any]:
    backend = get_agent_backend()
    project_statuses: list[dict[str, Any]] = []
    for project in list_projects(root)[:20]:
        try:
            status = backend.status(project.project_id, root)
        except Exception as exc:  # pragma: no cover - optional SDK status
            project_statuses.append(
                {"project_id": project.project_id, "status": "error", "error": str(exc)}
            )
        else:
            project_statuses.append(
                {"project_id": project.project_id, **_agent_status_payload(status)}
            )
    return {
        "backend": backend.name,
        "configured_backend": agent_backend_name(),
        "available": ["file_queue", "codex_sdk"],
        "fallback_hint": "Set OPEN_COMPOSER_AGENT_BACKEND=file_queue if codex_sdk is unavailable.",
        "project_statuses": project_statuses,
    }


def build_settings_agent_backend_update_payload(
    root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    backend = str(payload.get("backend") or "").strip()
    if backend not in {"file_queue", "codex_sdk"}:
        raise ValueError("backend must be file_queue or codex_sdk")
    env_path = root / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated = False
    for index, line in enumerate(lines):
        if line.startswith("OPEN_COMPOSER_AGENT_BACKEND="):
            lines[index] = f"OPEN_COMPOSER_AGENT_BACKEND={backend}"
            updated = True
            break
    if not updated:
        lines.append(f"OPEN_COMPOSER_AGENT_BACKEND={backend}")
    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"status": "updated", "backend": backend, "env_path": ".env"}


def build_paper_kill_switch_payload(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled", True))
    reason = str(payload.get("reason") or "Dashboard paper kill switch update.").strip()
    if enabled:
        state = enable_paper_kill_switch(root, reason=reason, updated_by="dashboard")
    else:
        state = clear_paper_kill_switch(root, reason=reason, updated_by="dashboard")
    status_path = write_paper_status(root)
    _append_dashboard_event(
        root,
        action="paper.kill_switch.enable" if enabled else "paper.kill_switch.clear",
        message=reason,
    )
    return {
        "status": "executed",
        "kill_switch": state.model_dump(mode="json"),
        "output_paths": [_relpath(status_path, root), "reports/paper/kill_switch.json"],
    }


def build_paper_sync_payload(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    # Keep broker sync as an explicit queued command in Dashboard-first mode. The
    # existing CLI remains the execution surface for live broker reads.
    project = _system_project(root)
    kind = "advice"
    body = "Run paper sync for orders/account snapshots, then refresh paper status."
    command = append_queue(
        project.project_id,
        kind=kind,  # type: ignore[arg-type]
        body=body,
        via="dashboard",
        metadata={"via": "dashboard", "action": "paper_sync"},
        root=root,
    )
    append_trace(
        project.project_id,
        agent="dashboard",
        operation="dashboard_paper_sync_queued",
        queue_command_id=command.id,
        metadata={"via": "dashboard"},
        root=root,
    )
    get_agent_backend().send_command(
        project.project_id,
        kind=kind,
        body=body,
        root=root,
        existing_command_id=command.id,
    )
    return {
        "status": "queued",
        "project_id": project.project_id,
        "queue_command_id": command.id,
        "queue_path": f"projects/{project.project_id}/queue.jsonl",
    }


def build_paper_monitor_refresh_payload(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    report = refresh_paper_monitor(root, sync_broker=bool(payload.get("sync_broker", False)))
    _append_dashboard_event(
        root,
        action="paper.monitor.refresh",
        message=f"Paper monitor refresh: {report.status}",
    )
    return {
        "status": "executed",
        "monitor": report.model_dump(mode="json"),
        "output_paths": [
            path
            for path in [
                report.status_path,
                report.reconciliation_report_path,
                report.alert_report_path,
                report.report_json_path,
                report.report_markdown_path,
            ]
            if path
        ],
    }


def build_paper_positions_payload(root: Path) -> dict[str, Any]:
    catalog = build_dashboard_catalog(root).model_dump(mode="json")
    return {"positions": catalog.get("paper_positions", [])}


def build_paper_orders_payload(root: Path) -> dict[str, Any]:
    catalog = build_dashboard_catalog(root).model_dump(mode="json")
    return {"orders": catalog.get("orders", [])}


def build_paper_alerts_payload(root: Path) -> dict[str, Any]:
    status = build_paper_status(root)
    report = build_paper_alerts(root)
    return {
        "status": status.model_dump(mode="json"),
        "alerts": report.model_dump(mode="json"),
    }


def _ensure_project_for_strategy(root: Path, strategy_name: str, spec_path: Path):
    project_id = _project_id_for_strategy(root, strategy_name)
    if (root / "projects" / project_id / "project.yaml").exists():
        project = load_project(project_id, root)
        if project.current_spec_path is None:
            project.current_spec_path = _relpath(spec_path, root)
            write_project(project, root)
        return project
    project, _ = create_project(
        StrategyProjectCreate(
            name=strategy_name,
            thesis=f"StrategyProject for {strategy_name}.",
            idea=f"Continue research and lifecycle management for {strategy_name}.",
            requested_by="dashboard",
            current_spec_path=_relpath(spec_path, root),
            tags=["dashboard-linked"],
        ),
        root,
    )
    return project


def _system_project(root: Path):
    if (root / "projects" / "dashboard-ops" / "project.yaml").exists():
        return load_project("dashboard-ops", root)
    project, _ = create_project(
        StrategyProjectCreate(
            name="Dashboard Ops",
            thesis="Operational queue for Dashboard-triggered system actions.",
            idea=(
                "Handle Dashboard operational actions without running long work in the HTTP server."
            ),
            requested_by="dashboard",
            tags=["dashboard-ops"],
        ),
        root,
    )
    return project


def _project_id_for_strategy(root: Path, strategy_name: str) -> str:
    normalized = _slugify(strategy_name)
    if (root / "projects" / normalized / "project.yaml").exists():
        return normalized
    for project in list_projects(root):
        if (
            project.name == strategy_name
            or project.current_spec_path == f"strategy_specs/drafts/{strategy_name}.yaml"
        ):
            return project.project_id
    return normalized


def _queue_strategy_action(
    root: Path,
    project_id: str,
    action: str,
    spec_path: Path,
    payload: dict[str, Any],
) -> str:
    if action == "evidence":
        body = (
            f"Run `uv run oc strategy evidence {_relpath(spec_path, root)}` "
            "and update project evidence."
        )
        kind = "continue"
    elif action == "materialize":
        factor = str(payload.get("factor") or "").strip()
        refresh = " --refresh" if bool(payload.get("refresh", False)) else ""
        factor_arg = f" --factor {factor}" if factor else ""
        window_bars = payload.get("window_bars")
        window_arg = ""
        if window_bars not in {None, "", "full"}:
            window_value = int(window_bars)
            if window_value < 1:
                raise ValueError("window_bars must be positive")
            window_arg = f" --window-bars {window_value}"
        body = (
            f"Run `uv run oc feature materialize "
            f"{_relpath(spec_path, root)}{factor_arg}{refresh}{window_arg}` "
            "then rerun LLM contribution evidence."
        )
        kind = "materialize"
    else:
        raise ValueError(f"unsupported queued action: {action}")
    command = append_queue(
        project_id,
        kind=kind,  # type: ignore[arg-type]
        body=body,
        via="dashboard",
        metadata={
            "via": "dashboard",
            "action": action,
            "source_spec_path": _relpath(spec_path, root),
            **_json_mapping(payload.get("metadata")),
        },
        root=root,
    )
    append_trace(
        project_id,
        agent="dashboard",
        operation=f"dashboard_strategy_{action}_queued",
        queue_command_id=command.id,
        metadata={"via": "dashboard", "source_spec_path": _relpath(spec_path, root)},
        root=root,
    )
    return get_agent_backend().send_command(
        project_id,
        kind=kind,
        body=body,
        root=root,
        existing_command_id=command.id,
    )


def _agent_status_payload(status: Any) -> dict[str, Any]:
    last_seen_at = getattr(status, "last_seen_at", None)
    return {
        "backend": getattr(status, "backend", ""),
        "session_id": getattr(status, "session_id", None),
        "status": getattr(status, "status", "idle"),
        "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
        "queue_pending": getattr(status, "queue_pending", 0),
    }


def _find_catalog_strategy(catalog: dict[str, Any], strategy_name: str) -> dict[str, Any] | None:
    for row in catalog.get("strategies", []):
        if not isinstance(row, dict):
            continue
        names = {
            str(row.get("strategy_id") or ""),
            str(row.get("strategy_name") or ""),
            _slugify(str(row.get("strategy_name") or "")),
        }
        if strategy_name in names:
            return row
    return None


def _llm_factor_rows(root: Path, strategy_name: str) -> list[dict[str, Any]]:
    try:
        spec_path = resolve_strategy_path(strategy_name, root)
        spec = load_strategy_spec(spec_path)
    except (FileNotFoundError, ValueError):
        return []
    rows: list[dict[str, Any]] = []
    for name, factor in spec.factors.items():
        if factor.source != "llm_feature":
            continue
        packet_path = (
            _resolve_dashboard_path(root, str(factor.path))
            if factor.path
            else default_materialized_feature_path(root, spec.name, name)
        )
        prompt_path = (
            _resolve_dashboard_path(root, str(factor.prompt_template_path))
            if factor.prompt_template_path
            else None
        )
        prompt = (
            prompt_path.read_text(encoding="utf-8") if prompt_path and prompt_path.exists() else ""
        )
        packet_count = len(_read_jsonl_rows(packet_path))
        rows.append(
            {
                "name": name,
                "field": factor.field,
                "path": factor.path or _relpath(packet_path, root),
                "packet_count": packet_count,
                "prompt_template_path": factor.prompt_template_path,
                "prompt_preview": prompt[:1200],
                "prompt_hash": _hash_text(prompt) if prompt else None,
                "input_view": factor.input_view,
                "input_view_version": factor.input_view_version,
                "model_ref": factor.model_ref,
                "point_in_time_ready": packet_count > 0,
                "factor_lab": _factor_lab_metric(root, spec.name, name),
            }
        )
    return rows


def _pass_reasons(
    project_payload: dict[str, Any] | None,
    paper_readiness: list[dict[str, Any]],
    research_reports: list[dict[str, Any]],
) -> dict[str, list[str]]:
    project = project_payload.get("project") if project_payload else {}
    gate = project.get("gate_summary") if isinstance(project, dict) else {}
    blockers = _string_items(project.get("blockers") if isinstance(project, dict) else None)
    blocked_checks = _string_items(gate.get("blocked_checks") if isinstance(gate, dict) else None)
    warning_checks = _string_items(gate.get("warning_checks") if isinstance(gate, dict) else None)
    report_items: list[str] = []
    for report in research_reports:
        report_items.extend(_string_items(report.get("blocked_items")))
        report_items.extend(_string_items(report.get("warning_items")))
    paper_items: list[str] = []
    for report in paper_readiness:
        checks = report.get("checks")
        if isinstance(checks, list):
            for check in checks:
                if isinstance(check, dict) and str(check.get("status") or "") != "pass":
                    message = check.get("message", check.get("status"))
                    paper_items.append(f"{check.get('name', 'paper_check')}: {message}")
    common = [*blocked_checks, *warning_checks, *blockers, *report_items]
    return {
        "workflow_pass": common,
        "research_pass": common,
        "llm_contribution_pass": common,
        "paper_ready_pass": [*common, *paper_items],
    }


def _load_llm_factor(root: Path, strategy_name: str, factor_name: str):
    spec_path = resolve_strategy_path(strategy_name, root)
    spec = load_strategy_spec(spec_path)
    factor = spec.factors.get(factor_name)
    if factor is None:
        raise FileNotFoundError(f"factor not found: {factor_name}")
    if factor.source != "llm_feature":
        raise ValueError(f"factor is not source=llm_feature: {factor_name}")
    if not factor.prompt_template_path:
        raise ValueError(f"factor has no prompt_template_path: {factor_name}")
    return spec_path, spec, factor


def _factor_lab_metric(root: Path, strategy_name: str, factor_name: str) -> dict[str, Any] | None:
    payload = _read_json_mapping(root / "reports" / "research" / f"{strategy_name}-factor-lab.json")
    metrics = payload.get("factor_metrics")
    if not isinstance(metrics, list):
        return None
    for metric in metrics:
        if isinstance(metric, dict) and str(metric.get("name") or "") == factor_name:
            return {
                "status": payload.get("status"),
                "rank_ic": metric.get("rank_ic"),
                "rolling_rank_ic_mean": metric.get("rolling_rank_ic_mean"),
                "rolling_rank_ic_min": metric.get("rolling_rank_ic_min"),
                "observations": metric.get("observations"),
                "coverage_pct": metric.get("coverage_pct"),
                "flags": metric.get("flags", []),
            }
    return None


def _signal_rows(
    root: Path,
    *,
    strategy_name: str,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / "signal_logs").glob("*.jsonl")):
        for row in _read_jsonl_rows(path):
            if strategy_name not in {
                str(row.get("strategy_name") or ""),
                str(row.get("strategy_id") or ""),
            }:
                continue
            if run_id and str(row.get("run_id") or "") != run_id:
                continue
            rows.append({**row, "log_path": _relpath(path, root)})
    return sorted(rows, key=lambda row: str(row.get("timestamp", "")))


def _equity_rows(
    root: Path,
    *,
    strategy_name: str,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    signals = _signal_rows(root, strategy_name=strategy_name, run_id=run_id)
    if signals:
        value = 100_000.0
        position_price: float | None = None
        rows = [{"ts": signals[0]["timestamp"], "value": value}]
        for signal in signals:
            price = float(signal.get("price") or 0)
            side = str(signal.get("side") or "").lower()
            if side in {"buy", "sell_short", "short"} and position_price is None:
                position_price = price
            elif position_price is not None and price:
                direction = -1 if side in {"buy_to_cover", "cover"} else 1
                value *= 1 + direction * ((price / position_price) - 1) * 0.2
                position_price = None
            rows.append({"ts": signal.get("timestamp"), "value": round(value, 2), "price": price})
        return rows
    catalog = build_dashboard_catalog(root).model_dump(mode="json")
    runs = [
        row
        for row in catalog.get("runs", [])
        if isinstance(row, dict)
        and strategy_name in {str(row.get("strategy_id")), str(row.get("strategy_name"))}
        and (not run_id or str(row.get("run_id")) == run_id)
    ]
    if not runs:
        return []
    latest = sorted(runs, key=lambda row: str(row.get("run_id", "")))[-1]
    start = float(latest.get("start_equity") or 100_000)
    end = float(latest.get("end_equity") or start)
    return [
        {"ts": "start", "value": round(start, 2)},
        {"ts": str(latest.get("run_id") or "latest"), "value": round(end, 2)},
    ]


def _read_trace_since(project_id: str, since_ts: str, root: Path) -> list[dict[str, Any]]:
    rows = _read_jsonl_rows(trace_path(project_id, root))
    if not since_ts:
        return rows
    return [row for row in rows if str(row.get("ts") or "") > since_ts]


def _read_jsonl_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                rows.append(raw)
    return rows


def _read_json_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _read_text(path: Path, *, max_bytes: int) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="ignore")


def _write_llm_prompt_placeholder(root: Path, strategy_name: str) -> Path:
    path = root / "prompts" / "llm_factors" / f"{strategy_name}-sentiment.md"
    if path.exists():
        return path
    ensure_dir(path.parent)
    path.write_text(
        "\n".join(
            [
                "# LLM Factor Prompt",
                "",
                "Score only point-in-time visible information. Return structured JSON "
                "that matches the StrategySpec output_schema.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _template_name(template_id: str | None) -> str | None:
    if not template_id:
        return None
    for template in BUILD_TEMPLATES:
        if template["id"] == template_id:
            return template["name"]
    return None


def _append_dashboard_event(root: Path, *, action: str, message: str) -> None:
    from open_composer.models.dashboard_command import DashboardCommandEvent
    from open_composer.storage import append_jsonl

    append_jsonl(
        root / "reports" / "dashboard" / "commands" / "events.jsonl",
        [
            DashboardCommandEvent(
                command_id=(
                    f"dashapi_{action.replace('.', '_')}_"
                    f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
                ),
                action=action,  # type: ignore[arg-type]
                status="executed",
                actor="dashboard",
                reason=message,
                message=message,
            )
        ],
    )


def _api_parts(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part][1:]


def _json_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _slugify(value: str) -> str:
    text = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "strategy-project"


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_dashboard_path(root: Path, value: str) -> Path:
    path = Path(value)
    resolved = path if path.is_absolute() else root / path
    try:
        resolved.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path must stay inside dashboard root: {value}") from exc
    return resolved


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_project_create_payload(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    project, command = create_project(StrategyProjectCreate.model_validate(payload), root)
    response: dict[str, Any] = {
        "project": project.model_dump(mode="json"),
        "project_path": f"projects/{project.project_id}/project.yaml",
        "context_path": f"projects/{project.project_id}/context.md",
    }
    if command is not None:
        response["queue_command"] = command.model_dump(mode="json", by_alias=True)
        response["queue_path"] = f"projects/{project.project_id}/queue.jsonl"
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
        from open_composer.research.iteration_controller import continue_project

        result = continue_project(
            project_id,
            root=root,
            body=direction,
            kind="continue",
            via="dashboard",
            rounds=int(payload.get("rounds") or 1),
            requested_by=str(payload.get("requested_by") or "dashboard"),
        )
        project = result.project
        queue_command = result.queue_command
        queue_path = result.queue_path
        trace_path = result.trace_path
        context_path = result.context_path
        artifact_state_path = result.artifact_state_path
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
    else:
        raise ValueError("action must be one of: stop, archive, continue, paper_review")
    response = {"project": project.model_dump(mode="json")}
    if "queue_command" in locals():
        response["queue_command"] = queue_command.model_dump(mode="json", by_alias=True)
        response["queue_path"] = queue_path
        response["trace_path"] = trace_path
        response["context_path"] = context_path
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


def _query_int(
    query: str,
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    values = parse_qs(query).get(key, [])
    if not values:
        return default
    try:
        return max(minimum, min(maximum, int(values[0])))
    except ValueError:
        return default


def _query_bool(query: str, key: str, *, default: bool) -> bool:
    values = parse_qs(query).get(key, [])
    if not values:
        return default
    return values[0].strip().lower() in {"1", "true", "yes", "on"}
