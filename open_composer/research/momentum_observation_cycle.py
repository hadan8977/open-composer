from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.execution.momentum_shadow import run_momentum_shadow_observation
from open_composer.research.momentum_data_refresh import refresh_momentum_research_data
from open_composer.storage import append_jsonl, write_json


@dataclass(frozen=True)
class MomentumObservationCycleResult:
    status: str
    receipt_path: Path
    readiness_path: Path
    theoretical_proxy_path: Path
    payload: dict[str, Any]


def run_momentum_observation_cycle(
    spec_path: Path,
    root: Path,
    *,
    as_of: datetime | None = None,
    refresh: bool = False,
    dry_run: bool = False,
) -> MomentumObservationCycleResult:
    observed_at = _utc_timestamp(as_of or datetime.now(UTC))
    slot = observed_at.floor("30min").strftime("%Y%m%dT%H%MZ")
    run_dir = root / "reports/shadow" / spec_path.stem / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = run_dir / f"{slot}.json"
    readiness_path = root / "reports/shadow" / spec_path.stem / "readiness.json"
    proxy_path = root / "reports/shadow" / spec_path.stem / "theoretical-execution.jsonl"
    if receipt_path.exists():
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        return MomentumObservationCycleResult(
            status=str(payload["status"]),
            receipt_path=receipt_path,
            readiness_path=readiness_path,
            theoretical_proxy_path=proxy_path,
            payload=payload,
        )
    if dry_run:
        payload = {
            "report_type": "momentum_observation_cycle",
            "status": "dry_run",
            "slot": slot,
            "as_of": observed_at.isoformat(),
            "refresh_requested": refresh,
            "broker_writes": False,
            "paper_order_authorization": False,
        }
        return MomentumObservationCycleResult(
            status="dry_run",
            receipt_path=receipt_path,
            readiness_path=readiness_path,
            theoretical_proxy_path=proxy_path,
            payload=payload,
        )

    lock_path = root / "reports/shadow" / spec_path.stem / ".cycle.lock"
    lock_fd = _acquire_lock(lock_path)
    try:
        refresh_payload = None
        if refresh:
            refresh_result = refresh_momentum_research_data(root, end=observed_at.to_pydatetime())
            refresh_payload = {
                "status": refresh_result.status,
                "receipt_path": str(refresh_result.receipt_path.relative_to(root)),
            }
            if refresh_result.status != "ok":
                raise RuntimeError("strict momentum data refresh failed")
        shadow = run_momentum_shadow_observation(spec_path, root, as_of=observed_at.to_pydatetime())
        proxy_rows = build_theoretical_execution_proxy(shadow.forward_ledger_path)
        _append_unique_proxy_rows(proxy_path, proxy_rows)
        readiness = evaluate_momentum_shadow_readiness(
            shadow.forward_ledger_path,
            proxy_path,
            shadow_status=shadow.status,
            as_of=observed_at,
        )
        write_json(readiness_path, readiness)
        payload = {
            "report_type": "momentum_observation_cycle",
            "status": shadow.status,
            "slot": slot,
            "as_of": observed_at.isoformat(),
            "refresh_requested": refresh,
            "refresh": refresh_payload,
            "shadow_observation_path": str(shadow.observation_path.relative_to(root)),
            "forward_ledger_path": str(shadow.forward_ledger_path.relative_to(root)),
            "theoretical_proxy_path": str(proxy_path.relative_to(root)),
            "readiness_path": str(readiness_path.relative_to(root)),
            "paper_order_authorization": False,
            "broker_writes": False,
        }
        write_json(receipt_path, payload)
        return MomentumObservationCycleResult(
            status=shadow.status,
            receipt_path=receipt_path,
            readiness_path=readiness_path,
            theoretical_proxy_path=proxy_path,
            payload=payload,
        )
    except Exception as exc:
        remediation_dir = root / "reports/shadow" / spec_path.stem / "remediations"
        remediation_dir.mkdir(parents=True, exist_ok=True)
        remediation = {
            "status": "blocked",
            "slot": slot,
            "as_of": observed_at.isoformat(),
            "error": str(exc),
            "resolved": False,
            "paper_order_authorization": False,
            "broker_writes": False,
        }
        write_json(remediation_dir / f"{slot}.json", remediation)
        raise
    finally:
        os.close(lock_fd)
        lock_path.unlink(missing_ok=True)


def build_theoretical_execution_proxy(forward_ledger_path: Path) -> list[dict[str, Any]]:
    if not forward_ledger_path.exists():
        return []
    rows = _read_jsonl(forward_ledger_path)
    result = []
    for row in rows:
        decision = row.get("decision_price")
        execution = row.get("expected_execution_open")
        if decision in (None, 0) or execution is None:
            continue
        effective = pd.Timestamp(row["effective_timestamp"]).tz_convert("America/New_York")
        result.append(
            {
                "evidence_class": "theoretical_execution_proxy",
                "spec_hash": row["spec_hash"],
                "signal_timestamp": row["signal_timestamp"],
                "effective_timestamp": row["effective_timestamp"],
                "execution_session_type": (
                    "opening_proxy"
                    if effective.hour == 9 and effective.minute == 30
                    else "intraday_proxy"
                ),
                "decision_close": float(decision),
                "next_open": float(execution),
                "decision_to_next_open_bps": round(
                    (float(execution) / float(decision) - 1.0) * 10000.0, 6
                ),
                "observed_fill": False,
                "quote_available": False,
                "vwap_available": False,
                "paper_order_authorization": False,
            }
        )
    return result


def evaluate_momentum_shadow_readiness(
    forward_ledger_path: Path,
    theoretical_proxy_path: Path,
    *,
    shadow_status: str,
    as_of: pd.Timestamp,
    cross_source: dict[str, Any] | None = None,
    observed_fill_tca: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = _read_jsonl(forward_ledger_path)
    proxy_rows = _read_jsonl(theoretical_proxy_path)
    sessions = {
        pd.Timestamp(row["signal_timestamp"]).tz_convert("America/New_York").date().isoformat()
        for row in rows
    }
    intents = [row for row in rows if row.get("order_required_intent")]
    entries = [row for row in intents if float(row.get("target_weight", 0.0)) > 0]
    exits = [row for row in intents if float(row.get("target_weight", 0.0)) == 0]
    operational_pass = len(sessions) >= 20
    cross_source_current = _external_evidence_current(cross_source, as_of)
    fill_tca_current = _external_evidence_current(observed_fill_tca, as_of)
    shadow_evidence_pass = (
        len(sessions) >= 60
        and len(intents) >= 60
        and len(entries) >= 20
        and len(exits) >= 20
        and cross_source_current
        and fill_tca_current
    )
    if shadow_status == "blocked":
        status = "blocked"
    elif shadow_evidence_pass:
        status = "shadow_observation_complete"
    else:
        status = "collecting"
    return {
        "report_type": "momentum_shadow_readiness",
        "status": status,
        "as_of": as_of.isoformat(),
        "forward_trading_days": len(sessions),
        "forward_decisions": len(rows),
        "forward_intents": len(intents),
        "entry_intents": len(entries),
        "exit_intents": len(exits),
        "theoretical_proxy_rows": len(proxy_rows),
        "operational_interim": {
            "threshold_trading_days": 20,
            "passed": operational_pass,
            "meaning": "scheduler/data/idempotency smoke only",
        },
        "shadow_evidence": {
            "threshold_trading_days": 60,
            "threshold_intents": 60,
            "threshold_entry_intents": 20,
            "threshold_exit_intents": 20,
            "cross_source_passed": cross_source_current,
            "observed_fill_tca_passed": fill_tca_current,
            "passed": shadow_evidence_pass,
        },
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "paper_authorized": False,
        "ml_eligible": False,
        "product_capability_complete": True,
    }


def _append_unique_proxy_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    existing = {
        (row["spec_hash"], row["signal_timestamp"], row["effective_timestamp"])
        for row in _read_jsonl(path)
    }
    additions = [
        row
        for row in rows
        if (row["spec_hash"], row["signal_timestamp"], row["effective_timestamp"]) not in existing
    ]
    if additions:
        append_jsonl(path, additions)


def _external_evidence_current(payload: dict[str, Any] | None, as_of: pd.Timestamp) -> bool:
    if not payload or not payload.get("passed") or not payload.get("expires_at"):
        return False
    expires_at = pd.Timestamp(payload["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.tz_localize("UTC")
    return bool(expires_at.tz_convert("UTC") >= as_of)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _acquire_lock(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"momentum observation cycle lock already exists: {path}") from exc


def _utc_timestamp(value: datetime) -> pd.Timestamp:
    result = pd.Timestamp(value)
    return result.tz_localize("UTC") if result.tzinfo is None else result.tz_convert("UTC")
