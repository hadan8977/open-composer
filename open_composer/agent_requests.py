from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import ensure_dir, project_root
from open_composer.storage import write_json

AgentRequestStatus = Literal["open", "in_progress", "completed", "cancelled"]
AgentRequestType = Literal["research", "review", "parameter_scan", "strategy_optimization"]
_ABSOLUTE_PATH_PATTERN = re.compile(r"^([/\\]|[A-Za-z]:[\\/])")


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    requested_by: str = "dashboard"
    task_type: AgentRequestType
    title: str
    prompt: str
    related_paths: list[str] = Field(default_factory=list)
    status: AgentRequestStatus = "open"
    result_links: list[str] = Field(default_factory=list)


class AgentRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_by: str = "dashboard"
    task_type: AgentRequestType = "research"
    title: str
    prompt: str
    related_paths: list[str] = Field(default_factory=list)


def create_agent_request(
    payload: AgentRequestCreate,
    root: Path | None = None,
) -> AgentRequest:
    base = root or project_root()
    request = AgentRequest(
        request_id=_new_request_id(),
        requested_by=payload.requested_by,
        task_type=payload.task_type,
        title=payload.title.strip(),
        prompt=payload.prompt.strip(),
        related_paths=[_validate_relative_path(base, path) for path in payload.related_paths],
    )
    if not request.title:
        raise ValueError("agent request title is required")
    if not request.prompt:
        raise ValueError("agent request prompt is required")
    write_agent_request(request, base)
    return request


def write_agent_request(request: AgentRequest, root: Path | None = None) -> Path:
    base = root or project_root()
    path = base / "reports" / "agent_requests" / f"{request.request_id}.json"
    return write_json(path, request)


def load_agent_request(request_id: str, root: Path | None = None) -> AgentRequest:
    base = root or project_root()
    path = base / "reports" / "agent_requests" / f"{request_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"agent request not found: {request_id}")
    return AgentRequest.model_validate_json(path.read_text(encoding="utf-8"))


def list_agent_requests(root: Path | None = None) -> list[AgentRequest]:
    base = root or project_root()
    directory = base / "reports" / "agent_requests"
    if not directory.exists():
        return []
    requests = [
        AgentRequest.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]
    return sorted(requests, key=lambda request: request.created_at, reverse=True)


def complete_agent_request(
    request_id: str,
    *,
    result_links: list[str],
    root: Path | None = None,
) -> AgentRequest:
    base = root or project_root()
    request = load_agent_request(request_id, base)
    request.status = "completed"
    request.result_links = [_validate_relative_path(base, path) for path in result_links]
    write_agent_request(request, base)
    return request


def ensure_agent_request_dir(root: Path | None = None) -> Path:
    base = root or project_root()
    return ensure_dir(base / "reports" / "agent_requests")


def _new_request_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"agentreq_{stamp}_{uuid4().hex[:8]}"


def _validate_relative_path(root: Path, value: str) -> str:
    path = value.strip()
    if not path:
        return path
    if _ABSOLUTE_PATH_PATTERN.match(path):
        raise ValueError("agent request paths must be workspace-relative")
    candidate = Path(path)
    if candidate.is_absolute():
        raise ValueError("agent request paths must be workspace-relative")
    resolved = (root / candidate).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
        raise ValueError("agent request paths must stay within the workspace")
    return candidate.as_posix()
