from __future__ import annotations

import json
import os
from collections.abc import Mapping
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from open_composer.agent_requests import (
    AgentRequestCreate,
    create_agent_request,
    list_agent_requests,
)
from open_composer.config import ensure_dir
from open_composer.dashboard.commands import DashboardCommandError
from open_composer.dashboard.server import (
    build_dashboard_catalog_payload,
    build_dashboard_command_plan_payload,
)
from open_composer.remote.auth import HMACAuthError, NonceStore, verify_signed_request
from open_composer.remote.jobs import RemoteJobError, RemoteJobManager
from open_composer.remote.schemas import (
    RemoteCommandMetadata,
    RemoteCommandRunRequest,
    RemoteDoctorCheck,
    RemoteDoctorReport,
    remote_backup_required,
    remote_double_confirmation_phrase,
    remote_risk_level,
)

MAX_REMOTE_BODY_BYTES = 1_000_000


class RemoteServerError(RuntimeError):
    pass


class RemoteHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "OpenComposerRemote/0.1"

    def __init__(
        self,
        *args: Any,
        root: Path,
        shared_secret: str,
        allowed_actor: str,
        nonce_store: NonceStore,
        job_manager: RemoteJobManager,
        **kwargs: Any,
    ) -> None:
        self.root = root
        self.shared_secret = shared_secret
        self.allowed_actor = allowed_actor
        self.nonce_store = nonce_store
        self.job_manager = job_manager
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"status": "ok", "service": "open-composer-remote"})
            return
        if not self._authorize(path, b""):
            return
        try:
            if path == "/dashboard/catalog":
                self._send_json(build_dashboard_catalog_payload(self.root))
                return
            if path.startswith("/dashboard/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                self._send_json(self.job_manager.load_job(job_id).model_dump(mode="json"))
                return
            if path == "/dashboard/events":
                self._send_json({"events": self.job_manager.read_events()})
                return
            if path == "/agent-requests":
                self._send_json(
                    {
                        "requests": [
                            request.model_dump(mode="json")
                            for request in list_agent_requests(self.root)
                        ]
                    }
                )
                return
            self._send_json({"error": "Unknown remote API path"}, status=404)
        except RemoteJobError as exc:
            self._send_json({"error": str(exc)}, status=404)
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary.
            self._send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._read_body()
        except RemoteServerError as exc:
            self._send_json({"error": str(exc)}, status=413)
            return
        if not self._authorize(path, body):
            return
        try:
            payload = _json_payload(body)
            if path == "/dashboard/command-plan":
                response = build_dashboard_command_plan_payload(self.root, payload)
                response["remote"] = _remote_metadata(response["action"])
                self._send_json(response)
                return
            if path == "/dashboard/command-run":
                request = RemoteCommandRunRequest.model_validate(payload)
                record = self.job_manager.create_command_job(request, actor=self.allowed_actor)
                self._send_json(self.job_manager.response_for_job(record).model_dump(mode="json"))
                return
            if path == "/agent-requests":
                request = create_agent_request(
                    AgentRequestCreate.model_validate(payload),
                    self.root,
                )
                self._send_json(request.model_dump(mode="json"), status=201)
                return
            self._send_json({"error": "Unknown remote API path"}, status=404)
        except (DashboardCommandError, RemoteServerError, ValueError, ValidationError) as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary.
            self._send_json({"error": str(exc)}, status=500)

    def _read_body(self) -> bytes:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length or "0")
        except ValueError as exc:
            raise RemoteServerError("Content-Length must be an integer") from exc
        if length > MAX_REMOTE_BODY_BYTES:
            raise RemoteServerError("request body is too large")
        return self.rfile.read(length) if length > 0 else b""

    def _authorize(self, path: str, body: bytes) -> bool:
        try:
            verify_signed_request(
                method=self.command,
                path=path,
                body=body,
                headers=_headers_mapping(self.headers),
                secret=self.shared_secret,
                nonce_store=self.nonce_store,
                allowed_actor=self.allowed_actor,
            )
        except HMACAuthError as exc:
            self._send_json({"error": str(exc)}, status=401)
            return False
        return True

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def create_remote_server(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    shared_secret: str | None = None,
    allowed_actor: str | None = None,
) -> ThreadingHTTPServer:
    secret = shared_secret or os.getenv("OC_REMOTE_SHARED_SECRET", "")
    if not secret:
        raise RemoteServerError("OC_REMOTE_SHARED_SECRET is required for remote daemon")
    actor = allowed_actor or os.getenv("OC_DASHBOARD_OWNER", "owner")
    nonce_store = NonceStore(root / "reports" / "dashboard" / "remote-nonces.json")
    job_manager = RemoteJobManager(root)
    handler = partial(
        RemoteHTTPRequestHandler,
        root=root,
        shared_secret=secret,
        allowed_actor=actor,
        nonce_store=nonce_store,
        job_manager=job_manager,
    )
    return ThreadingHTTPServer((host, port), handler)


def serve_remote(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    shared_secret: str | None = None,
    allowed_actor: str | None = None,
) -> None:
    with create_remote_server(
        root,
        host=host,
        port=port,
        shared_secret=shared_secret,
        allowed_actor=allowed_actor,
    ) as server:
        print(f"remote daemon serving http://{host}:{port}")
        print("remote_api=HMAC")
        server.serve_forever()


def build_remote_doctor_report(root: Path) -> RemoteDoctorReport:
    checks = [
        RemoteDoctorCheck(
            name="shared_secret",
            status="ok" if os.getenv("OC_REMOTE_SHARED_SECRET") else "blocked",
            message="OC_REMOTE_SHARED_SECRET is set."
            if os.getenv("OC_REMOTE_SHARED_SECRET")
            else "OC_REMOTE_SHARED_SECRET is required before serving remote commands.",
        ),
        RemoteDoctorCheck(
            name="owner",
            status="ok" if os.getenv("OC_DASHBOARD_OWNER", "owner") else "blocked",
            message="Remote owner actor is configured.",
        ),
        _directory_check(root / "reports" / "dashboard" / "jobs", "job_dir"),
        _directory_check(root / "reports" / "backups" / "remote", "backup_dir"),
        _env_permission_check(root / ".env"),
    ]
    status = "ok"
    if any(check.status == "blocked" for check in checks):
        status = "blocked"
    elif any(check.status == "warning" for check in checks):
        status = "warning"
    return RemoteDoctorReport(status=status, ready=status != "blocked", checks=checks)


def _remote_metadata(action: str) -> dict[str, object]:
    metadata = RemoteCommandMetadata(
        risk_level=remote_risk_level(action),
        backup_required=remote_backup_required(action),
        double_confirmation_required=remote_double_confirmation_phrase(action) is not None,
        double_confirmation_phrase=remote_double_confirmation_phrase(action),
    )
    return metadata.model_dump(mode="json")


def _json_payload(body: bytes) -> dict[str, Any]:
    if not body.strip():
        return {}
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise RemoteServerError("request body must be a JSON object")
    return data


def _headers_mapping(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in headers.items()}


def _directory_check(path: Path, name: str) -> RemoteDoctorCheck:
    try:
        ensure_dir(path)
    except OSError as exc:
        return RemoteDoctorCheck(name=name, status="blocked", message=str(exc))
    return RemoteDoctorCheck(name=name, status="ok", message=f"{path} is writable.")


def _env_permission_check(path: Path) -> RemoteDoctorCheck:
    if not path.exists():
        return RemoteDoctorCheck(
            name="env_permissions",
            status="warning",
            message=".env is missing; daemon may still run if environment variables are injected.",
        )
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        return RemoteDoctorCheck(
            name="env_permissions",
            status="warning",
            message=".env exists but should be chmod 600 on the remote server.",
        )
    return RemoteDoctorCheck(
        name="env_permissions",
        status="ok",
        message=".env permissions are owner-only.",
    )
