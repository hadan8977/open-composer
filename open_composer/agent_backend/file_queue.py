from __future__ import annotations

from pathlib import Path

from open_composer.projects import append_queue, read_trace_tail, unconsumed_queue

from .base import AgentSessionStatus


class FileQueueAgentBackend:
    name = "file_queue"

    def send_command(
        self,
        project_id: str,
        *,
        kind: str,
        body: str,
        root: Path,
        existing_command_id: str | None = None,
    ) -> str:
        if existing_command_id:
            return existing_command_id
        return append_queue(
            project_id,
            kind=kind,  # type: ignore[arg-type]
            body=body,
            via="api",
            root=root,
        ).id

    def status(self, project_id: str, root: Path) -> AgentSessionStatus:
        tail = read_trace_tail(project_id, 1, root)
        last_seen = tail[-1].ts if tail else None
        return AgentSessionStatus(
            backend=self.name,
            session_id=None,
            status="idle",
            last_seen_at=last_seen,
            queue_pending=len(unconsumed_queue(project_id, root)),
        )

    def stop(self, project_id: str, root: Path) -> None:
        append_queue(
            project_id,
            kind="stop",
            body="User requested stop.",
            via="cli",
            root=root,
        )
