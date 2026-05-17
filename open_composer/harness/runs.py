"""Harness run log — append-only JSONL evidence store for gate results.

Each run record captures: strategy name, spec hash, stage, gate results, and timestamp.
The log lives at {root}/reports/research/harness-runs.jsonl.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.research.kernel.gates import GateResult

_LOG_FILENAME = "harness-runs.jsonl"


def _log_path(root: Path) -> Path:
    return root / "reports" / "research" / _LOG_FILENAME


def append_run(
    *,
    strategy_name: str,
    spec_hash: str,
    stage: str,
    results: list[GateResult],
    root: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Append a gate-run record to the JSONL log and return the log path."""
    base = root or project_root()
    log = _log_path(base)
    ensure_dir(log.parent)
    record: dict[str, Any] = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "strategy_name": strategy_name,
        "spec_hash": spec_hash,
        "stage": stage,
        "status": _aggregate_status(results),
        "gate_results": [r.model_dump(mode="json") for r in results],
    }
    if extra:
        record.update(extra)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return log


def query_runs(
    *,
    strategy_name: str | None = None,
    stage: str | None = None,
    gate_name: str | None = None,
    since: datetime | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Read the JSONL log and return matching run records.

    Filters are ANDed together. Returns an empty list if the log does not exist.
    """
    base = root or project_root()
    log = _log_path(base)
    if not log.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if strategy_name and record.get("strategy_name") != strategy_name:
            continue
        if stage and record.get("stage") != stage:
            continue
        if gate_name:
            gate_names_in_record = {g["name"] for g in record.get("gate_results", [])}
            if gate_name not in gate_names_in_record:
                continue
        if since:
            recorded_at_str = record.get("recorded_at", "")
            try:
                recorded_at = datetime.fromisoformat(recorded_at_str)
                if recorded_at < since:
                    continue
            except ValueError:
                continue
        records.append(record)
    return records


def evidence_for(
    strategy_name: str,
    spec_hash: str,
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Return all run records for a specific strategy + spec hash combination."""
    base = root or project_root()
    runs = query_runs(strategy_name=strategy_name, root=base)
    return [r for r in runs if r.get("spec_hash") == spec_hash]


def _aggregate_status(results: list[GateResult]) -> str:
    if any(r.status == "blocked" for r in results):
        return "blocked"
    if any(r.status == "warning" for r in results):
        return "warning"
    return "ok"
