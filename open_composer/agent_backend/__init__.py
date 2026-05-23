from __future__ import annotations

from open_composer.config import agent_backend_name

from .base import AgentBackend, AgentSessionStatus
from .file_queue import FileQueueAgentBackend


def get_agent_backend() -> AgentBackend:
    name = agent_backend_name()
    if name == "codex_sdk":
        try:
            from .codex_sdk import CodexAgentBackend

            return CodexAgentBackend()
        except RuntimeError:
            return FileQueueAgentBackend()
    return FileQueueAgentBackend()


__all__ = [
    "AgentBackend",
    "AgentSessionStatus",
    "FileQueueAgentBackend",
    "get_agent_backend",
]
