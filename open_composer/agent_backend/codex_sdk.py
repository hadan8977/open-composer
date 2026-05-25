from __future__ import annotations

from pathlib import Path

import yaml

from open_composer.config import default_openai_model
from open_composer.projects import append_trace, unconsumed_queue

from .base import AgentSessionStatus
from .file_queue import FileQueueAgentBackend

REQUIRED_CLIENT_METHODS = (
    "start_session",
    "send_user_message",
    "is_session_alive",
    "cancel_session",
)
FALLBACK_HINT = "Set OPEN_COMPOSER_AGENT_BACKEND=file_queue to use the audited file queue fallback."

try:  # pragma: no cover - optional dependency surface
    from codex_sdk import CodexAppServerClient  # type: ignore
except ImportError:  # pragma: no cover - optional dependency surface
    CodexAppServerClient = None  # type: ignore


class CodexAgentBackend:
    name = "codex_sdk"

    def __init__(self, model: str | None = None):
        if CodexAppServerClient is None:
            raise RuntimeError(f"codex_sdk package is not installed. {FALLBACK_HINT}")
        self.model = model or default_openai_model()
        self._client = CodexAppServerClient()
        missing = [
            method
            for method in REQUIRED_CLIENT_METHODS
            if not callable(getattr(self._client, method, None))
        ]
        if missing:
            raise RuntimeError(
                "codex_sdk API is incompatible; missing methods: "
                f"{', '.join(missing)}. {FALLBACK_HINT}"
            )
        self._fallback = FileQueueAgentBackend()

    def send_command(
        self,
        project_id: str,
        *,
        kind: str,
        body: str,
        root: Path,
        existing_command_id: str | None = None,
    ) -> str:
        command_id = self._fallback.send_command(
            project_id,
            kind=kind,
            body=body,
            root=root,
            existing_command_id=existing_command_id,
        )
        session_id = self._load_or_create_session(project_id, root)
        self._client.send_user_message(
            session_id=session_id,
            content=(
                f"[queue:{command_id}] {kind}: {body}\n\n"
                f"Read projects/{project_id}/context.md and queue.jsonl before acting."
            ),
        )
        append_trace(
            project_id,
            agent="codex",
            operation="codex_sdk_send_user_message",
            queue_command_id=command_id,
            metadata={"session_id": session_id, "model": self.model},
            root=root,
        )
        return command_id

    def status(self, project_id: str, root: Path) -> AgentSessionStatus:
        path = self._session_binding_path(project_id, root)
        if not path.exists():
            return AgentSessionStatus(
                backend=self.name,
                session_id=None,
                status="disabled",
                last_seen_at=None,
                queue_pending=len(unconsumed_queue(project_id, root)),
            )
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        session_id = raw.get("codex_session_id")
        alive = bool(session_id and self._client.is_session_alive(session_id))
        return AgentSessionStatus(
            backend=self.name,
            session_id=str(session_id) if session_id else None,
            status="idle" if alive else "lost",
            last_seen_at=None,
            queue_pending=len(unconsumed_queue(project_id, root)),
        )

    def stop(self, project_id: str, root: Path) -> None:
        session_id = self._load_or_create_session(project_id, root)
        self._client.cancel_session(session_id)
        self._fallback.stop(project_id, root)

    def _session_binding_path(self, project_id: str, root: Path) -> Path:
        return root / "projects" / project_id / "session-binding.yaml"

    def _load_or_create_session(self, project_id: str, root: Path) -> str:
        path = self._session_binding_path(project_id, root)
        if path.exists():
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            session_id = raw.get("codex_session_id")
            if session_id and self._client.is_session_alive(session_id):
                return str(session_id)
        session_id = self._client.start_session(
            cwd=str(root),
            model=self.model,
            system_prompt_path=str(root / "projects" / project_id / "context.md"),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                {"codex_session_id": session_id, "model": self.model},
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return str(session_id)
