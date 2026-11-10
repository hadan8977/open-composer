"""Bounded local waiting and checkpoint availability, without provider calls.

No shell from artifacts is executed. The existing driver owns locks, admission,
provider dispatch and receiving Replies; this module only observes bound evidence.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.research.knowledge_tools import safe_path
from open_composer.research.process_identity import process_state


class WaitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    session: str = Field(min_length=1)
    completion_marker: str | None = None
    failure_marker: str | None = None
    cancel_marker: str | None = None
    process: str | None = None  # JSON identity, inside this run
    local_only: bool = False  # launcher exit never implies remote completion


def bound_path(root: Path, run: Path, name: str) -> Path:
    path = safe_path(root, name)
    if not path.is_relative_to(run):
        raise ValueError("Wait evidence must belong to this run")
    return path


def bind_wait(root: Path, run: Path, spec: WaitSpec, session: str) -> dict:
    if spec.session != session:
        raise ValueError("Wait must bind the original worker session")
    if not spec.completion_marker and not (spec.process and spec.local_only):
        raise ValueError("Wait needs an explicit completion condition")
    for key in ("completion_marker", "failure_marker", "cancel_marker", "process"):
        if getattr(spec, key):
            bound_path(root, run, getattr(spec, key))
    saved = None
    if spec.process:
        saved = json.loads(bound_path(root, run, spec.process).read_text())
        if process_state(saved) in ("legacy_unknown", "unknown", "identity_mismatch"):
            raise ValueError("Wait process lacks a verifiable launch identity")
    payload = spec.model_dump()
    wait_id = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
    return {
        "id": wait_id,
        "spec": payload,
        "state": "waiting",
        "attempt": None,
        "process_identity": saved,
    }


def wait_event(root: Path, run: Path, record: dict, deadline: float, require_research) -> dict:
    spec = WaitSpec.model_validate(record["spec"])
    while True:
        try:
            require_research(root)
        except ValueError:
            return {"state": "paused"}
        # Terminal markers take precedence over completion when both exist.
        for key, state in (
            ("cancel_marker", "cancelled"),
            ("failure_marker", "failed"),
            ("completion_marker", "ready"),
        ):
            name = getattr(spec, key)
            if name:
                path = bound_path(root, run, name)
                if path.is_file():
                    with path.open("rb") as stream:
                        marker = stream.read(65537)
                    if len(marker) > 65536:
                        return {"state": "unknown", "reason": "Marker exceeds 64 KiB"}
                    event = hashlib.sha256(
                        f"{record['id']}:{key}:{name}:".encode() + marker
                    ).hexdigest()[:24]
                    return {"state": state, "event": event, "evidence": name}
        if spec.process:
            saved = json.loads(bound_path(root, run, spec.process).read_text())
            if saved != record.get("process_identity"):
                return {"state": "unknown", "reason": "Bound process record changed"}
            observed = process_state(saved)
            if observed in ("identity_mismatch", "unknown", "legacy_unknown"):
                return {"state": "unknown", "reason": "Process identity needs reconciliation"}
            if observed == "exited" and spec.local_only:
                return {"state": "ready", "event": record["id"] + "-exit", "evidence": spec.process}
        if time.monotonic() >= deadline:
            return {"state": "timeout"}
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))


def checkpoint_status(root: Path, run: Path, name: str | None, session: str | None) -> dict:
    """Readable input locations are availability evidence, never engine snapshots."""
    if name is None:
        return {"state": "absent", "native_resumable": False}
    if session is None:
        return {"state": "session_unknown", "native_resumable": False}
    path = bound_path(root, run, name)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"state": "unavailable", "native_resumable": False}
    if not isinstance(data, dict) or data.get("kind") != "research_checkpoint":
        return {"state": "legacy_evidence", "native_resumable": False}
    if data.get("schema_version") != 1 or data.get("session") != session:
        return {"state": "binding_mismatch", "native_resumable": False}
    if not all(isinstance(data.get(key), list) for key in ("inputs", "completed", "remaining")):
        return {"state": "invalid_checkpoint", "native_resumable": False}
    if not all(
        isinstance(item, dict) and item.get("type", "file") in ("file", "directory")
        for item in data["inputs"]
    ):
        return {"state": "invalid_checkpoint", "native_resumable": False}
    available = True
    inputs = []
    for item in data.get("inputs", []):
        try:
            source = safe_path(root, item["path"])
            stat = source.stat()
            ok = source.is_file() if item.get("type", "file") == "file" else source.is_dir()
            if source.is_file():
                with source.open("rb") as stream:
                    stream.read(1)
            expected = item.get("version")
            if expected is not None:
                ok = ok and expected == {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        except (OSError, ValueError, KeyError, TypeError):
            ok = False
        inputs.append({"path": item.get("path"), "available": ok})
        available = available and ok
    declared = data.get("native_resumable") is True and bool(data.get("engine_snapshot"))
    if declared:
        try:
            snapshot = bound_path(root, run, data["engine_snapshot"])
            with snapshot.open("rb") as stream:
                stream.read(1)
        except (OSError, ValueError):
            available = False
    return {
        "state": "available" if available else "dependency_unavailable",
        "native_resumable": bool(declared and available),
        "inputs": inputs,
        "completed": data.get("completed", []),
        "remaining": data.get("remaining", []),
    }
