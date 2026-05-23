from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol


@dataclass(frozen=True)
class AgentSessionStatus:
    backend: str
    session_id: str | None
    status: Literal["idle", "running", "lost", "disabled"]
    last_seen_at: datetime | None
    queue_pending: int


class AgentBackend(Protocol):
    name: str

    def send_command(
        self,
        project_id: str,
        *,
        kind: str,
        body: str,
        root: Path,
        existing_command_id: str | None = None,
    ) -> str: ...

    def status(self, project_id: str, root: Path) -> AgentSessionStatus: ...

    def stop(self, project_id: str, root: Path) -> None: ...
