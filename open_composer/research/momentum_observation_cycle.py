from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.execution.momentum_shadow import run_momentum_shadow_observation
from open_composer.market_calendar import expected_rth_bar_closes
from open_composer.research.momentum_data_refresh import refresh_momentum_research_data
from open_composer.storage import append_jsonl, write_json


@dataclass(frozen=True)
class MomentumObservationCycleResult:
    status: str
    receipt_path: Path
    readiness_path: Path
    theoretical_proxy_path: Path
    payload: dict[str, Any]


def resolve_momentum_remediation(
    root: Path,
    strategy_name: str,
    slot: str,
    *,
    resolved_by: str,
    reason: str,
    evidence_path: Path,
) -> Path:
    path = root / "reports/shadow" / strategy_name / "remediations" / f"{slot}.json"
    if not path.exists():
        raise FileNotFoundError(f"momentum remediation not found: {path}")
    if not resolved_by.strip() or len(reason.strip()) < 10:
        raise ValueError("remediation resolution requires identity and a specific reason")
    if not evidence_path.is_file():
        raise ValueError("remediation resolution evidence does not exist")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(
        {
            "resolved": True,
            "resolved_at": datetime.now(UTC).isoformat(),
            "resolved_by": resolved_by.strip(),
            "resolution_reason": reason.strip(),
            "resolution_evidence_path": str(evidence_path),
            "resolution_evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        }
    )
    write_json(path, payload)
    return path


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

    unresolved = _unresolved_remediations(root, spec_path.stem)
    if unresolved:
        raise RuntimeError(f"unresolved momentum shadow remediation: {unresolved[0]}")

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
            unresolved_remediations=_unresolved_remediations(root, spec_path.stem),
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
    unresolved_remediations: list[str] | None = None,
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
    session_timestamps: dict[str, set[pd.Timestamp]] = {}
    for row in rows:
        timestamp = pd.Timestamp(row["effective_timestamp"]).tz_convert("UTC")
        session = timestamp.tz_convert("America/New_York").date().isoformat()
        session_timestamps.setdefault(session, set()).add(timestamp)
    complete_sessions = sum(
        timestamps == expected_rth_bar_closes(date.fromisoformat(session))
        for session, timestamps in session_timestamps.items()
    )
    session_completeness = complete_sessions / max(len(session_timestamps), 1)
    cross_source_current, cross_source_metrics = _external_evidence_current(
        cross_source, as_of, expected_type="cross_source_state_agreement"
    )
    fill_tca_current, _ = _external_evidence_current(
        observed_fill_tca, as_of, expected_type="observed_fill_tca"
    )
    unresolved = unresolved_remediations or []
    state_lower_bound = float(cross_source_metrics.get("wilson_lower_bound", 0.0))
    direction_mismatches = int(cross_source_metrics.get("direction_mismatches", 1))
    shadow_evidence_pass = (
        len(sessions) >= 60
        and len(intents) >= 60
        and len(entries) >= 20
        and len(exits) >= 20
        and session_completeness >= 0.95
        and state_lower_bound >= 0.97
        and direction_mismatches == 0
        and cross_source_current
        and fill_tca_current
        and not unresolved
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
        "session_completeness": round(session_completeness, 6),
        "unresolved_remediation_count": len(unresolved),
        "unresolved_remediations": unresolved,
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
            "threshold_session_completeness": 0.95,
            "state_agreement_wilson_lower_bound": state_lower_bound,
            "direction_mismatches": direction_mismatches,
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


def _external_evidence_current(
    payload: dict[str, Any] | None, as_of: pd.Timestamp, *, expected_type: str
) -> tuple[bool, dict[str, Any]]:
    required = {
        "evidence_type",
        "provider",
        "source_tier",
        "collected_at",
        "data_as_of",
        "coverage_ratio",
        "sample_count",
        "sha256",
        "expires_at",
        "passed",
    }
    if (
        not payload
        or not required.issubset(payload)
        or payload.get("evidence_type") != expected_type
    ):
        return False, {}
    if payload.get("passed") is not True:
        return False, {}
    allowlists = {
        "cross_source_state_agreement": ({"longbridge", "alpaca"}, {"cross_source"}),
        "observed_fill_tca": ({"alpaca"}, {"paper_simulation"}),
    }
    providers, tiers = allowlists[expected_type]
    if payload.get("provider") not in providers or payload.get("source_tier") not in tiers:
        return False, {}
    if float(payload["coverage_ratio"]) < 0.95 or int(payload["sample_count"]) < 60:
        return False, {}
    artifact_path = Path(str(payload.get("artifact_path", "")))
    sha = str(payload.get("sha256", ""))
    if (
        not artifact_path.is_file()
        or len(sha) != 64
        or any(char not in "0123456789abcdef" for char in sha)
        or hashlib.sha256(artifact_path.read_bytes()).hexdigest() != sha
    ):
        return False, {}
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    collected_at = pd.Timestamp(payload["collected_at"])
    if collected_at.tzinfo is None:
        collected_at = collected_at.tz_localize("UTC")
    data_as_of = pd.Timestamp(payload["data_as_of"])
    if data_as_of.tzinfo is None:
        data_as_of = data_as_of.tz_localize("UTC")
    if data_as_of > collected_at or collected_at.tz_convert("UTC") > as_of:
        return False, {}
    expires_at = pd.Timestamp(payload["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.tz_localize("UTC")
    if expires_at.tz_convert("UTC") < as_of:
        return False, {}
    if expected_type == "cross_source_state_agreement":
        matches = int(artifact.get("state_matches", 0))
        total = int(artifact.get("state_total", 0))
        mismatches = int(artifact.get("direction_mismatches", 1))
        lower = _wilson_lower_bound(matches, total)
        return bool(total >= 60 and lower >= 0.97 and mismatches == 0), {
            "wilson_lower_bound": lower,
            "direction_mismatches": mismatches,
        }
    fills = artifact.get("fills", [])
    required_fill = {
        "order_id",
        "fill_id",
        "submitted_at",
        "filled_at",
        "fill_price",
        "reference_price",
        "symbol",
        "qty",
        "account_mode",
    }
    valid = len(fills) >= 60 and all(required_fill.issubset(fill) for fill in fills)
    if valid:
        order_ids = [str(fill["order_id"]) for fill in fills]
        fill_ids = [str(fill["fill_id"]) for fill in fills]
        valid = len(order_ids) == len(set(order_ids)) and len(fill_ids) == len(set(fill_ids))
    if valid:
        for fill in fills:
            submitted = pd.Timestamp(fill["submitted_at"])
            filled = pd.Timestamp(fill["filled_at"])
            valid = valid and (
                fill.get("account_mode") == "paper"
                and fill.get("symbol") == "TQQQ"
                and float(fill["qty"]) > 0
                and float(fill["fill_price"]) > 0
                and float(fill["reference_price"]) > 0
                and submitted <= filled <= data_as_of
            )
    return bool(valid), {"fill_count": len(fills)}


def _wilson_lower_bound(matches: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = matches / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5)
    return (centre - margin) / denominator


def _unresolved_remediations(root: Path, strategy_name: str) -> list[str]:
    directory = root / "reports/shadow" / strategy_name / "remediations"
    if not directory.exists():
        return []
    unresolved = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload.get("resolved") or not _resolution_is_valid(payload):
            unresolved.append(str(path.relative_to(root)))
    return unresolved


def _resolution_is_valid(payload: dict[str, Any]) -> bool:
    required = {
        "resolved_at",
        "resolved_by",
        "resolution_reason",
        "resolution_evidence_path",
        "resolution_evidence_sha256",
    }
    if not required.issubset(payload) or len(str(payload["resolution_reason"]).strip()) < 10:
        return False
    path = Path(str(payload["resolution_evidence_path"]))
    if not path.is_file():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == payload["resolution_evidence_sha256"]


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
