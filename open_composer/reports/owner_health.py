"""Check a report's business artifact, independently of scheduler success."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def report_event_health(root: Path, event_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "event_id": event_id,
        "status": "missing_business_result",
        "artifact_verified": False,
        "delivery_verified": False,
        "scope": "Read-only artifact check; no claim about report semantics or user receipt.",
    }
    try:
        hold = json.loads((root / "reports/research/control/owner-compute-hold.json").read_text())
        allowed = hold.get("reporting", {}).get("allowed")
        if allowed is False:
            return {**result, "status": "not_authorized"}
        if allowed is not True:
            return {**result, "status": "authority_unknown"}
        state = json.loads((root / "reports/owner/reporting-state.json").read_text())
    except (OSError, ValueError, AttributeError):
        return {**result, "status": "state_unreadable"}
    if not isinstance(state, dict):
        return {**result, "status": "state_unreadable"}
    records = state.get("reports", [])
    records = list(records.values()) if isinstance(records, dict) else records
    if not isinstance(records, list):
        return {**result, "status": "state_unreadable"}
    matches = [
        r
        for r in [*records, state.get("last_report", {})]
        if isinstance(r, dict) and (r.get("event_id") or r.get("event")) == event_id
    ]
    if not matches:
        return result
    record = matches[-1]
    raw_path = record.get("file")
    if not isinstance(raw_path, str) or not raw_path:
        return {**result, "status": "artifact_missing"}
    path = (root / raw_path).resolve()
    if not path.is_relative_to((root / "reports/owner").resolve()) or path.suffix != ".md":
        return {**result, "status": "artifact_path_invalid"}
    try:
        content = path.read_bytes()
    except OSError:
        return {**result, "status": "artifact_missing", "file": raw_path}
    if not content.strip():
        return {**result, "status": "artifact_empty", "file": raw_path}
    digest = hashlib.sha256(content).hexdigest()
    if record.get("sha256") and record["sha256"] != digest:
        return {**result, "status": "artifact_changed", "file": raw_path}
    completed = event_id in state.get("completed_event_ids", [])
    return {
        **result,
        "status": "written" if completed else "produced_not_completed",
        "artifact_verified": True,
        "file": raw_path,
        "sha256": digest,
        "delivery_note": "Written is not published/read; verify the existing delivery route.",
    }
