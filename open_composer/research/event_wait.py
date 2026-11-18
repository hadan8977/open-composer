"""Local waiting for a blocked worker's markers or launched process; no provider calls.

The driver owns locks, dispatch and receiving replies; this module only observes files
and processes inside the run.
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
    local_only: bool = False  # remote supervisor exit requests reconciliation only


def bound_path(root: Path, run: Path, name: str) -> Path:
    path = safe_path(root, name)
    if not path.is_relative_to(run):
        raise ValueError("Wait evidence must belong to this run")
    return path


def bind_wait(root: Path, run: Path, spec: WaitSpec) -> dict:
    if not spec.completion_marker and not (spec.process and spec.local_only):
        raise ValueError("Wait needs an explicit completion condition")
    for key in ("completion_marker", "failure_marker", "cancel_marker"):
        if getattr(spec, key):
            bound_path(root, run, getattr(spec, key))
    saved = None
    if spec.process:
        saved = json.loads(bound_path(root, run, spec.process).read_text(encoding="utf-8"))
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
        # Cancel and failure evidence take precedence over completion.
        for key, state in (
            ("cancel_marker", "cancelled"),
            ("failure_marker", "failed"),
            ("completion_marker", "ready"),
        ):
            name = getattr(spec, key)
            path = name and bound_path(root, run, name)
            if not path or not path.is_file():
                continue
            # Same marker content, same event: the driver's attempt dedupe relies on it.
            seed = f"{record['id']}:{key}:{name}:".encode() + path.read_bytes()
            event = hashlib.sha256(seed).hexdigest()[:24]
            if key == "failure_marker":
                return {
                    "state": "ready",
                    "event": event,
                    "event_kind": "failure_reconciliation",
                    "evidence": name,
                    "failure_status": "failed",
                    "remote_status": "unknown",
                    "reason": (
                        "Bound failure marker observed. Inspect failure and saved outputs; "
                        "this event proves no numerical completion and authorizes no retry."
                        " Unresolved quota, authorization or resource blockers remain "
                        "checkpoints."
                    ),
                }
            return {"state": state, "event": event, "evidence": name}
        if spec.process and process_state(record["process_identity"]) == "exited":
            if spec.local_only:
                return {"state": "ready", "event": record["id"] + "-exit", "evidence": spec.process}
            # Ready means ready to resume the bound worker, not remote completion.
            return {
                "state": "ready",
                "event": record["id"] + "-supervisor-exit",
                "event_kind": "remote_reconciliation",
                "evidence": spec.process,
                "remote_status": "unknown",
                "reason": (
                    "Local supervisor exited. Reconcile remote status and existing "
                    "outputs; this event proves no remote completion and authorizes no retry."
                ),
            }
        if time.monotonic() >= deadline:
            return {"state": "timeout"}
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))


def checkpoint_status(root: Path, run: Path, name: str | None, session: str | None) -> dict:
    """Whether a saved checkpoint's declared inputs (and engine snapshot) still exist."""
    if name is None:
        return {"state": "absent", "native_resumable": False}
    try:
        data = json.loads(bound_path(root, run, name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "unavailable", "native_resumable": False}
    if not isinstance(data, dict) or data.get("kind") != "research_checkpoint":
        return {"state": "legacy_evidence", "native_resumable": False}
    if data.get("session") != session:
        return {"state": "binding_mismatch", "native_resumable": False}
    inputs = []
    for item in data.get("inputs", []):
        try:
            source = safe_path(root, item["path"])
            ok = source.is_dir() if item.get("type") == "directory" else source.is_file()
            if ok and item.get("version") is not None:
                stat = source.stat()
                ok = item["version"] == {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        except (OSError, ValueError, KeyError):
            ok = False
        inputs.append({"path": item.get("path"), "available": ok})
    available = all(item["available"] for item in inputs)
    declared = data.get("native_resumable") is True and bool(data.get("engine_snapshot"))
    if declared:
        try:
            available = available and bound_path(root, run, data["engine_snapshot"]).exists()
        except ValueError:
            available = False
    return {
        "state": "available" if available else "dependency_unavailable",
        "native_resumable": declared and available,
        "inputs": inputs,
        "completed": data.get("completed", []),
        "remaining": data.get("remaining", []),
    }
