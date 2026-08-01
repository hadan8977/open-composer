from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.multiasset_paper_control_r7_snapshot import (
    validate_r7_forward_snapshot_contract,
)
from open_composer.adapters.execution.router_target_weights import (
    write_router_execution_artifacts,
)
from open_composer.market_calendar import NEW_YORK, us_equity_session_close
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.multiasset_forward_multimodal_r5 import (
    RANKABLE_SYMBOLS,
    RESERVE_SYMBOL,
    _canonical_json_bytes,
)
from open_composer.research.multiasset_paper_control_r7 import (
    ADAPTER_PATH,
    ITER_ID,
    ITERATION_DIR,
    SHADOW_IDS,
    SPEC_PATHS,
    R7FamilyComputation,
    compute_r7_family_targets,
    load_r6_source_specs,
    load_r7_panels,
    load_r7_specs,
    validate_r7_specs,
    verify_r7_lock,
)
from open_composer.strategy_versions import strategy_content_hash

FAMILY_NAME = "us_multiasset_paper_control_r7_family"
FORWARD_SESSION_TARGET = 20
FORWARD_EPOCH = date(2026, 8, 3)
MAX_CLOCK_SKEW = timedelta(minutes=5)
MAX_OBSERVATION_LAG = timedelta(hours=12)
MIN_SNAPSHOT_AFTER_CLOSE_LAG = timedelta(minutes=15)
RECEIPT_CONTRACT = "multiasset_paper_control_r7_family_forward_observation_v1"
READINESS_CONTRACT = "multiasset_paper_control_r7_family_forward_readiness_v1"
EVIDENCE_ROLES = (
    "router_target_weights",
    "router_rebalance_intents",
    "router_execution_observation",
    "router_cost_stress",
    "router_data_evidence",
    "router_validation",
)


@dataclass(frozen=True)
class R7ForwardTargetWeightResult:
    report_path: Path
    forward_ledger_path: Path
    forward_readiness_path: Path
    receipt_path: Path
    target_weights_paths: dict[str, Path]
    observation_paths: dict[str, Path]
    market_session: str
    valid_session_count: int
    forward_observation_pass: bool
    execution_substate: str = "observation_only"
    broker_writes: bool = False


def run_multiasset_paper_control_r7_target_weight_mapping(
    spec_path: Path,
    root: Path,
    *,
    snapshot_manifest_path: Path,
    as_of: datetime,
) -> R7ForwardTargetWeightResult:
    base = root.resolve()
    lock_path = base / "reports/forward/.locks/multiasset-paper-control-r7-family.lock"
    with _exclusive_file_lock(lock_path):
        return _run_locked(
            spec_path,
            base,
            snapshot_manifest_path=snapshot_manifest_path,
            as_of=as_of,
        )


def _run_locked(
    spec_path: Path,
    root: Path,
    *,
    snapshot_manifest_path: Path,
    as_of: datetime,
) -> R7ForwardTargetWeightResult:
    observed_at = _as_utc(as_of)
    now = _utc_now()
    if observed_at > now or now - observed_at > MAX_CLOCK_SKEW:
        raise ValueError("R7 observations must use the current non-backfilled clock")
    expected_session = _latest_completed_session(observed_at)
    if expected_session < FORWARD_EPOCH:
        raise ValueError("R7 forward receipts cannot begin before 2026-08-03")
    session_close = _session_close_utc(expected_session)
    if observed_at < session_close or observed_at - session_close > MAX_OBSERVATION_LAG:
        raise ValueError("R7 observation is outside the completed-session window")

    specs, source_specs, lock = _require_locked_family(root, spec_path)
    manifest_path = _resolve_root_file(root, snapshot_manifest_path, label="R7 snapshot manifest")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_payload = json.loads(manifest_bytes)
    if not isinstance(manifest_payload, dict):
        raise ValueError("R7 snapshot manifest must be a JSON object")
    validate_r7_forward_snapshot_contract(root, manifest_payload, expected_session)
    panels = load_r7_panels(
        root,
        manifest_path,
        expected_manifest_sha256=manifest_sha256,
    )
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != manifest_sha256:
        raise ValueError("R7 snapshot manifest changed while loading")
    manifest = panels["all"].manifest
    latest_panel_session = pd.Timestamp(panels["all"].close.index.max()).date()
    latest_manifest_session = _manifest_latest_complete_session(manifest)
    retrieved_at = _manifest_retrieved_at(manifest)
    if latest_panel_session != expected_session or latest_manifest_session != expected_session:
        raise ValueError(
            "R7 snapshot latest completed session mismatch: "
            f"panel={latest_panel_session} manifest={latest_manifest_session} "
            f"expected={expected_session}"
        )
    if not (session_close + MIN_SNAPSHOT_AFTER_CLOSE_LAG <= retrieved_at <= observed_at):
        raise ValueError("R7 snapshot retrieval is outside the observation window")

    ledger_path = _family_dir(root) / "decisions.jsonl"
    rows = _read_jsonl(ledger_path)
    duplicate = _matching_session_row(rows, expected_session)
    if duplicate is not None:
        if duplicate.get("snapshot_manifest_sha256") != manifest_sha256:
            raise ValueError("R7 session already exists with a different snapshot")
        readiness = _build_readiness(root=root, rows=rows, lock=lock, as_of=observed_at)
        if expected_session.isoformat() not in readiness["valid_session_ids"]:
            raise ValueError("existing R7 receipt is invalid or tampered")
        _write_json(_family_dir(root) / "readiness.json", readiness)
        _write_latest_from_row(root, duplicate, readiness)
        return _result_from_row(root, duplicate, readiness)

    preflight = _build_readiness(
        root=root,
        rows=rows,
        lock=lock,
        as_of=observed_at,
        pending_session=expected_session,
    )
    if preflight["epoch_closed"]:
        _write_json(_family_dir(root) / "readiness.json", preflight)
        raise ValueError(
            "R7 forward epoch is closed by a missing or invalid required session: "
            + ", ".join(preflight["missing_required_sessions"])
        )

    iteration = root / ITERATION_DIR
    feature_contract = _load_json(iteration / "feature-contract.json")
    computation = compute_r7_family_targets(
        panels["all"],
        specs,
        source_specs,
        provenance={
            "data_manifest_sha256": manifest_sha256,
            "feature_contract_sha256": _sha256(iteration / "feature-contract.json"),
            "label_contract_sha256": _sha256(iteration / "label-contract.json"),
            "prompt_hash": str(feature_contract["llm_formula_provenance"]["prompt_hash"]),
        },
    )
    latest_records = computation.latest_records
    candidate_payloads = {
        candidate_id: {
            "weights": latest_records[candidate_id]["weights"],
            "target_sha256": latest_records[candidate_id]["target_sha256"],
            "target_series_sha256": computation.target_series_sha256[candidate_id],
            "selected_symbols": latest_records[candidate_id]["selected_symbols"],
            "fallback_reason": latest_records[candidate_id].get("fallback_reason"),
            "order_eligible_in_r7": False,
            "broker_writes": False,
        }
        for candidate_id in SPEC_PATHS
    }
    if candidate_payloads["R7F01"]["weights"] != candidate_payloads["R7M01"]["weights"]:
        raise ValueError("R7 family publication failed F01=M01 identity")
    family_target_sha256 = hashlib.sha256(_canonical_json_bytes(candidate_payloads)).hexdigest()

    latest_artifacts: dict[str, dict[str, Path]] = {}
    immutable_artifacts: dict[str, dict[str, dict[str, Any]]] = {}
    for candidate_id, spec in specs.items():
        target_rows, intents = _execution_rows(
            spec=spec,
            candidate_id=candidate_id,
            computation=computation,
            spec_hash=strategy_content_hash(spec),
            manifest_hash=manifest_sha256,
        )
        artifacts = write_router_execution_artifacts(
            root=root,
            spec_path=root / SPEC_PATHS[candidate_id],
            spec=spec,
            target_rows=target_rows,
            rebalance_intents=intents,
            data_profile={
                "source_mode": "immutable_alpaca_contract_snapshot",
                "provider": "alpaca",
                "feed": "sip",
                "adjustment": "all",
                "session_scope": "regular",
                "snapshot_manifest_path": _relpath(manifest_path, root),
                "snapshot_manifest_sha256": manifest_sha256,
                "snapshot_retrieved_at": retrieved_at.isoformat(),
                "latest_complete_session": expected_session.isoformat(),
            },
            route_label=spec.portfolio.selected_route_label,
            mapping_summary={
                "iter_id": ITER_ID,
                "candidate_id": candidate_id,
                "family_target_sha256": family_target_sha256,
                "target_sha256": latest_records[candidate_id]["target_sha256"],
                "target_series_sha256": computation.target_series_sha256[candidate_id],
                "shadow_only": candidate_id in SHADOW_IDS,
                "paper_order_authorization": False,
                "broker_writes": False,
                "generic_paper_bridge": False,
            },
            acquisition_tier="research_strict",
            parity_check={
                "status": "ok",
                "checks": {
                    "same_snapshot_family": True,
                    "D01_exact_equal_weight": True,
                    "F01_exact_M01_identity": True,
                    "broker_free": True,
                },
                "blockers": [],
                "warnings": [],
            },
            target_backend="python_reference_observation",
            generated_at=observed_at,
        )
        _require_router_artifacts(spec, artifacts)
        latest_artifacts[candidate_id] = artifacts
        immutable_artifacts[candidate_id] = _freeze_candidate_artifacts(
            root=root,
            market_session=expected_session,
            candidate_id=candidate_id,
            artifacts=artifacts,
        )

    snapshot_evidence = (
        _family_dir(root) / "evidence" / expected_session.isoformat() / ("snapshot-manifest.json")
    )
    _write_immutable_bytes(snapshot_evidence, manifest_bytes)
    calculation_path = (
        _family_dir(root)
        / "evidence"
        / expected_session.isoformat()
        / ("family-target-calculation.json")
    )
    calculation = {
        "schema_version": 1,
        "report_type": "multiasset_paper_control_r7_family_target_calculation",
        "iter_id": ITER_ID,
        "market_session": expected_session.isoformat(),
        "latest_target_records": latest_records,
        "latest_model_records": _latest_model_records(computation),
        "target_series_sha256": computation.target_series_sha256,
        "family_target_sha256": family_target_sha256,
        "paper_order_authorization": False,
        "broker_writes": False,
    }
    _write_immutable_json(calculation_path, calculation)

    spec_semantic_hashes = {
        candidate_id: strategy_content_hash(spec) for candidate_id, spec in specs.items()
    }
    receipt = {
        "schema_version": 1,
        "receipt_contract": RECEIPT_CONTRACT,
        "evidence_class": "broker_free_forward_observation",
        "strategy_group": FAMILY_NAME,
        "iter_id": ITER_ID,
        "market_session": expected_session.isoformat(),
        "observed_at": observed_at.isoformat(),
        "forward_epoch": FORWARD_EPOCH.isoformat(),
        "snapshot_manifest_path": _relpath(manifest_path, root),
        "snapshot_manifest_sha256": manifest_sha256,
        "snapshot_retrieved_at": retrieved_at.isoformat(),
        "snapshot_evidence": _binding(snapshot_evidence, root),
        "family_target_sha256": family_target_sha256,
        "candidate_targets": candidate_payloads,
        "candidate_artifacts": immutable_artifacts,
        "family_target_calculation": _binding(calculation_path, root),
        "spec_semantic_sha256": spec_semantic_hashes,
        "preregistration_lock_sha256": lock["hashes"]["preregistration_lock"],
        "runner_lock_sha256": lock["hashes"]["runner_lock"],
        "lock_anchor_sha256": lock["hashes"]["lock_anchor"],
        "evaluation_receipt_sha256": lock["hashes"]["evaluation_receipt"],
        "adapter_implementation_sha256": _sha256(root / ADAPTER_PATH),
        "candidate_count": 8,
        "order_candidate_ids": ["R7D01"],
        "shadow_only_candidate_ids": sorted(SHADOW_IDS),
        "execution_substate": "observation_only",
        "paper_order_authorization": False,
        "broker_writes": False,
        "generic_paper_bridge": False,
    }
    receipt_path = _family_dir(root) / "receipts" / f"{expected_session.isoformat()}.json"
    receipt_bytes = _canonical_json_bytes(receipt) + b"\n"
    _write_immutable_bytes(receipt_path, receipt_bytes)
    ledger_row = {**receipt, "forward_receipt": _binding(receipt_path, root)}
    _append_ledger_row(ledger_path, ledger_row)

    rows = _read_jsonl(ledger_path)
    readiness = _build_readiness(root=root, rows=rows, lock=lock, as_of=observed_at)
    readiness_path = _family_dir(root) / "readiness.json"
    _write_json(readiness_path, readiness)
    report_path = _family_dir(root) / "latest-observation.json"
    report = {
        "schema_version": 1,
        "report_type": "multiasset_paper_control_r7_family_forward_observation",
        "strategy_group": FAMILY_NAME,
        "iter_id": ITER_ID,
        "generated_at": observed_at.isoformat(),
        "market_session": expected_session.isoformat(),
        "family_target_sha256": family_target_sha256,
        "candidate_targets": candidate_payloads,
        "receipt": ledger_row["forward_receipt"],
        "forward_readiness": readiness,
        "latest_artifacts": {
            candidate_id: {role: _relpath(path, root) for role, path in artifacts.items()}
            for candidate_id, artifacts in latest_artifacts.items()
        },
        "execution_substate": "observation_only",
        "research_pass": True,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "paper_order_authorization": False,
        "broker_writes": False,
        "generic_paper_bridge": False,
    }
    _write_json(report_path, report)
    return _result_from_row(root, ledger_row, readiness)


def _require_locked_family(
    root: Path, requested_spec_path: Path
) -> tuple[dict[str, StrategySpec], dict[str, StrategySpec], dict[str, Any]]:
    resolved = _resolve_root_file(root, requested_spec_path, label="R7 StrategySpec")
    canonical = {candidate_id: (root / path).resolve() for candidate_id, path in SPEC_PATHS.items()}
    if resolved not in canonical.values():
        raise ValueError("R7 target mapping requires a canonical R7 family StrategySpec")
    requested = load_strategy_spec(resolved)
    if requested.research_design is None or requested.research_design.iter_id != ITER_ID:
        raise ValueError("R7 requested StrategySpec has the wrong iteration identity")
    if (
        requested.lifecycle != "draft"
        or requested.execution.mode != "manual_signal"
        or requested.execution.broker != "none"
    ):
        raise ValueError("R7 forward mapping is broker-free draft/manual_signal only")

    lock = verify_r7_lock(root)
    evaluation_path = root / ITERATION_DIR / "evaluation-run/evaluation-receipt.json"
    evaluation = _load_json(evaluation_path)
    if (
        evaluation.get("receipt_contract") is not None
        or evaluation.get("iter_id") != ITER_ID
        or evaluation.get("workflow_pass") is not True
        or evaluation.get("research_pass") is not True
        or evaluation.get("paper_ready_pass") is not False
        or evaluation.get("paper_order_authorization") is not False
        or evaluation.get("broker_writes") is not False
    ):
        raise ValueError("R7 implementation evaluation receipt is incomplete")
    lock["hashes"]["evaluation_receipt"] = _sha256(evaluation_path)
    specs = load_r7_specs(root)
    source_specs = load_r6_source_specs(root)
    validate_r7_specs(specs, source_specs, root=root)
    return specs, source_specs, lock


def _execution_rows(
    *,
    spec: StrategySpec,
    candidate_id: str,
    computation: R7FamilyComputation,
    spec_hash: str,
    manifest_hash: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    records = {
        str(row["execution_session"]): row
        for row in computation.target_records
        if row["candidate_id"] == candidate_id
    }
    target_rows: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    prior = pd.Series(0.0, index=computation.targets[candidate_id].columns, dtype=float)
    for session, weights in computation.targets[candidate_id].iterrows():
        session_text = pd.Timestamp(session).date().isoformat()
        record = records[session_text]
        rebalance_id = (
            "r7_"
            + hashlib.sha256(
                f"{spec.name}|{candidate_id}|{session_text}|{record['target_sha256']}".encode()
            ).hexdigest()[:24]
        )
        for symbol in sorted(weights.index):
            target_weight = float(weights[symbol])
            from_weight = float(prior[symbol])
            delta = target_weight - from_weight
            side = "buy" if delta > 1e-12 else "sell" if delta < -1e-12 else "hold"
            common = {
                "iter_id": ITER_ID,
                "candidate_id": candidate_id,
                "spec_hash": spec_hash,
                "snapshot_manifest_sha256": manifest_hash,
                "target_sha256": record["target_sha256"],
                "fallback_reason": record.get("fallback_reason"),
                "paper_order_authorization": False,
                "broker_writes": False,
            }
            target_rows.append(
                {
                    "rebalance_id": rebalance_id,
                    "rebalance_session": session_text,
                    "signal_session": str(record["decision_session"]),
                    "time_rule": "regular_session_open",
                    "symbol": symbol,
                    "target_weight": target_weight,
                    **common,
                }
            )
            intents.append(
                {
                    "rebalance_id": rebalance_id,
                    "rebalance_session": session_text,
                    "time_rule": "regular_session_open",
                    "symbol": symbol,
                    "from_weight": from_weight,
                    "to_weight": target_weight,
                    "delta_weight": delta,
                    "side": side,
                    "intent_type": "set_target_weight_observation",
                    "requires_order": False,
                    **common,
                }
            )
        prior = weights.astype(float)
    return target_rows, intents


def _require_router_artifacts(spec: StrategySpec, artifacts: dict[str, Path]) -> None:
    if set(artifacts) != set(EVIDENCE_ROLES):
        raise ValueError(f"R7 router artifact inventory is incomplete: {spec.name}")
    observation = _load_json(artifacts["router_execution_observation"])
    validation = _load_json(artifacts["router_validation"])
    if (
        observation.get("execution_substate") != "observation_only"
        or observation.get("blockers")
        or validation.get("status") != "ok"
        or validation.get("blockers")
    ):
        raise ValueError(f"R7 router artifacts are blocked: {spec.name}")
    intents = _load_json(artifacts["router_rebalance_intents"])
    if any(row.get("requires_order") is not False for row in intents.get("intents", [])):
        raise ValueError(f"R7 router intents unexpectedly require orders: {spec.name}")


def _freeze_candidate_artifacts(
    *,
    root: Path,
    market_session: date,
    candidate_id: str,
    artifacts: dict[str, Path],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    directory = _family_dir(root) / "evidence" / market_session.isoformat() / candidate_id
    for role, source in artifacts.items():
        destination = directory / f"{role}{source.suffix}"
        _write_immutable_bytes(destination, source.read_bytes())
        output[role] = _binding(destination, root)
    return output


def _latest_model_records(computation: R7FamilyComputation) -> dict[str, dict[str, Any] | None]:
    result: dict[str, dict[str, Any] | None] = {candidate_id: None for candidate_id in SPEC_PATHS}
    for candidate_id in result:
        rows = [row for row in computation.model_records if row["candidate_id"] == candidate_id]
        if rows:
            result[candidate_id] = max(rows, key=lambda row: str(row["decision_session"]))
    return result


def _build_readiness(
    *,
    root: Path,
    rows: list[dict[str, Any]],
    lock: dict[str, Any],
    as_of: datetime,
    pending_session: date | None = None,
) -> dict[str, Any]:
    valid: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, Any]] = []
    for line_number, row in enumerate(rows, start=1):
        reasons = _validate_ledger_row(root=root, row=row, lock=lock, as_of=as_of)
        session = str(row.get("market_session") or "")
        if session in valid:
            reasons.append("duplicate_market_session")
        if reasons:
            excluded.append(
                {"line": line_number, "market_session": session, "reasons": sorted(set(reasons))}
            )
        else:
            valid[session] = row

    cutoff = _latest_completed_session(as_of)
    required = _expected_sessions(FORWARD_EPOCH, FORWARD_SESSION_TARGET)
    completed = [session for session in required if session <= cutoff]
    pending = pending_session.isoformat() if pending_session else None
    missing = [
        session.isoformat()
        for session in completed
        if session.isoformat() not in valid and session.isoformat() != pending
    ]
    invalid_required = sorted(
        {
            item["market_session"]
            for item in excluded
            if item["market_session"] in {session.isoformat() for session in completed}
        }
    )
    contiguous: list[str] = []
    for session in required:
        session_text = session.isoformat()
        if session > cutoff or session_text == pending:
            break
        if session_text not in valid:
            break
        contiguous.append(session_text)
    epoch_closed = bool(missing or invalid_required)
    forward_pass = len(contiguous) >= FORWARD_SESSION_TARGET and not epoch_closed
    return {
        "schema_version": 1,
        "readiness_contract": READINESS_CONTRACT,
        "report_type": "multiasset_paper_control_r7_family_forward_readiness",
        "strategy_group": FAMILY_NAME,
        "iter_id": ITER_ID,
        "generated_at": as_of.isoformat(),
        "forward_epoch": FORWARD_EPOCH.isoformat(),
        "minimum_contiguous_bound_sessions": FORWARD_SESSION_TARGET,
        "required_session_ids": [session.isoformat() for session in required],
        "valid_session_ids": sorted(valid),
        "valid_receipt_count": len(valid),
        "contiguous_bound_session_ids": contiguous,
        "contiguous_bound_session_count": len(contiguous),
        "missing_required_sessions": missing,
        "invalid_required_sessions": invalid_required,
        "excluded_receipts": excluded,
        "epoch_closed": epoch_closed,
        "forward_observation_pass": forward_pass,
        "canary_prerequisite_forward_pass": forward_pass,
        "workflow_pass": not excluded and not epoch_closed,
        "research_pass": True,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "matched_tca_observations": 0,
        "matched_tca_required": 30,
        "execution_substate": "observation_only",
        "paper_order_authorization": False,
        "broker_writes": False,
        "generic_paper_bridge": False,
        "preregistration_lock_sha256": lock["hashes"]["preregistration_lock"],
        "runner_lock_sha256": lock["hashes"]["runner_lock"],
        "lock_anchor_sha256": lock["hashes"]["lock_anchor"],
        "evaluation_receipt_sha256": lock["hashes"].get("evaluation_receipt"),
        "adapter_implementation_sha256": _sha256(root / ADAPTER_PATH),
    }


def _validate_ledger_row(
    *,
    root: Path,
    row: dict[str, Any],
    lock: dict[str, Any],
    as_of: datetime,
) -> list[str]:
    reasons: list[str] = []
    expected = {
        "receipt_contract": RECEIPT_CONTRACT,
        "evidence_class": "broker_free_forward_observation",
        "strategy_group": FAMILY_NAME,
        "iter_id": ITER_ID,
        "forward_epoch": FORWARD_EPOCH.isoformat(),
        "candidate_count": 8,
        "order_candidate_ids": ["R7D01"],
        "shadow_only_candidate_ids": sorted(SHADOW_IDS),
        "execution_substate": "observation_only",
        "paper_order_authorization": False,
        "broker_writes": False,
        "generic_paper_bridge": False,
        "preregistration_lock_sha256": lock["hashes"]["preregistration_lock"],
        "runner_lock_sha256": lock["hashes"]["runner_lock"],
        "lock_anchor_sha256": lock["hashes"]["lock_anchor"],
        "evaluation_receipt_sha256": lock["hashes"].get("evaluation_receipt"),
        "adapter_implementation_sha256": _sha256(root / ADAPTER_PATH),
    }
    reasons.extend(
        f"{field}_mismatch" for field, value in expected.items() if row.get(field) != value
    )
    try:
        session = date.fromisoformat(str(row["market_session"]))
        observed = _as_utc(datetime.fromisoformat(str(row["observed_at"])))
    except (KeyError, ValueError):
        return reasons + ["session_or_observed_at_invalid"]
    if session < FORWARD_EPOCH or us_equity_session_close(session) is None:
        reasons.append("market_session_invalid")
    else:
        close = _session_close_utc(session)
        if observed < close or observed - close > MAX_OBSERVATION_LAG:
            reasons.append("observation_window_invalid")
    if observed > as_of or _latest_completed_session(observed) != session:
        reasons.append("observation_timing_invalid")

    candidate_targets = row.get("candidate_targets")
    if not isinstance(candidate_targets, dict) or set(candidate_targets) != set(SPEC_PATHS):
        reasons.append("candidate_target_inventory_invalid")
    else:
        for candidate_id, payload in candidate_targets.items():
            if not isinstance(payload, dict) or not _valid_weights(
                payload.get("weights"), candidate_id
            ):
                reasons.append(f"candidate_weights_invalid:{candidate_id}")
                continue
            if _target_hash(payload["weights"]) != payload.get("target_sha256"):
                reasons.append(f"candidate_target_hash_invalid:{candidate_id}")
        if candidate_targets["R7F01"].get("weights") != candidate_targets["R7M01"].get("weights"):
            reasons.append("F01_M01_identity_invalid")
    if isinstance(candidate_targets, dict):
        if hashlib.sha256(_canonical_json_bytes(candidate_targets)).hexdigest() != row.get(
            "family_target_sha256"
        ):
            reasons.append("family_target_hash_invalid")

    for label, binding in (
        ("forward_receipt", row.get("forward_receipt")),
        ("snapshot_evidence", row.get("snapshot_evidence")),
        ("family_target_calculation", row.get("family_target_calculation")),
    ):
        if not _binding_valid(root, binding):
            reasons.append(f"{label}_invalid")
    receipt_binding = row.get("forward_receipt")
    if _binding_valid(root, receipt_binding):
        receipt = _load_json(root / str(receipt_binding["path"]))
        expected_receipt = {key: value for key, value in row.items() if key != "forward_receipt"}
        if receipt != expected_receipt:
            reasons.append("forward_receipt_payload_mismatch")
    artifacts = row.get("candidate_artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(SPEC_PATHS):
        reasons.append("candidate_artifact_inventory_invalid")
    else:
        for candidate_id, bindings in artifacts.items():
            if not isinstance(bindings, dict) or set(bindings) != set(EVIDENCE_ROLES):
                reasons.append(f"candidate_artifact_roles_invalid:{candidate_id}")
                continue
            if any(not _binding_valid(root, binding) for binding in bindings.values()):
                reasons.append(f"candidate_artifact_binding_invalid:{candidate_id}")
    return reasons


def _write_latest_from_row(root: Path, row: dict[str, Any], readiness: dict[str, Any]) -> None:
    report = {
        "schema_version": 1,
        "report_type": "multiasset_paper_control_r7_family_forward_observation",
        "strategy_group": FAMILY_NAME,
        "iter_id": ITER_ID,
        "generated_at": readiness["generated_at"],
        "market_session": row["market_session"],
        "family_target_sha256": row["family_target_sha256"],
        "candidate_targets": row["candidate_targets"],
        "receipt": row["forward_receipt"],
        "forward_readiness": readiness,
        "execution_substate": "observation_only",
        "research_pass": True,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "paper_order_authorization": False,
        "broker_writes": False,
        "generic_paper_bridge": False,
    }
    _write_json(_family_dir(root) / "latest-observation.json", report)


def _result_from_row(
    root: Path, row: dict[str, Any], readiness: dict[str, Any]
) -> R7ForwardTargetWeightResult:
    target_paths = {
        candidate_id: root / "reports/execution" / f"{spec_name}-target-weights.json"
        for candidate_id, spec_name in (
            (candidate_id, load_strategy_spec(root / path).name)
            for candidate_id, path in SPEC_PATHS.items()
        )
    }
    observation_paths = {
        candidate_id: root / "reports/execution" / f"{spec_name}-execution-observation.json"
        for candidate_id, spec_name in (
            (candidate_id, load_strategy_spec(root / path).name)
            for candidate_id, path in SPEC_PATHS.items()
        )
    }
    return R7ForwardTargetWeightResult(
        report_path=_family_dir(root) / "latest-observation.json",
        forward_ledger_path=_family_dir(root) / "decisions.jsonl",
        forward_readiness_path=_family_dir(root) / "readiness.json",
        receipt_path=root / row["forward_receipt"]["path"],
        target_weights_paths=target_paths,
        observation_paths=observation_paths,
        market_session=str(row["market_session"]),
        valid_session_count=int(readiness["contiguous_bound_session_count"]),
        forward_observation_pass=bool(readiness["forward_observation_pass"]),
    )


def _manifest_latest_complete_session(manifest: dict[str, Any]) -> date:
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 56:
        raise ValueError("R7 snapshot must contain 14 symbols by four adjustments")
    complete_sessions = [
        item.get("quality", {}).get("complete_sessions") for item in items if isinstance(item, dict)
    ]
    if len(complete_sessions) != 56 or any(
        not isinstance(sessions, list) or not sessions for sessions in complete_sessions
    ):
        raise ValueError("R7 snapshot complete-session evidence is missing")
    latest = {str(sessions[-1]) for sessions in complete_sessions}
    if len(latest) != 1:
        raise ValueError("R7 snapshot complete-session inventory is inconsistent")
    return date.fromisoformat(latest.pop())


def _manifest_retrieved_at(manifest: dict[str, Any]) -> datetime:
    try:
        return _as_utc(datetime.fromisoformat(str(manifest["retrieved_at"]).replace("Z", "+00:00")))
    except (KeyError, ValueError) as exc:
        raise ValueError("R7 snapshot retrieved_at is invalid") from exc


def _valid_weights(weights: Any, candidate_id: str) -> bool:
    if not isinstance(weights, dict) or set(weights) != {RESERVE_SYMBOL, *RANKABLE_SYMBOLS}:
        return False
    cap = 0.08 if candidate_id == "R7D01" else 0.34
    values: list[float] = []
    for symbol, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        number = float(value)
        if not math.isfinite(number) or number < -1e-12:
            return False
        if symbol != RESERVE_SYMBOL and number > cap + 1e-12:
            return False
        values.append(number)
    return math.isclose(sum(values), 1.0, abs_tol=1e-9, rel_tol=0.0)


def _target_hash(weights: dict[str, float]) -> str:
    return hashlib.sha256(_canonical_json_bytes(weights)).hexdigest()


def _expected_sessions(start: date, count: int) -> list[date]:
    sessions: list[date] = []
    current = start
    while len(sessions) < count:
        if us_equity_session_close(current) is not None:
            sessions.append(current)
        current += timedelta(days=1)
    return sessions


def _latest_completed_session(value: datetime) -> date:
    local = value.astimezone(NEW_YORK)
    candidate = local.date()
    close = us_equity_session_close(candidate)
    if close is None or local.time() < close:
        candidate -= timedelta(days=1)
    while us_equity_session_close(candidate) is None:
        candidate -= timedelta(days=1)
    return candidate


def _session_close_utc(session: date) -> datetime:
    close = us_equity_session_close(session)
    if close is None:
        raise ValueError(f"R7 date is not a US trading session: {session}")
    return datetime.combine(session, close, tzinfo=NEW_YORK).astimezone(UTC)


def _matching_session_row(rows: list[dict[str, Any]], session: date) -> dict[str, Any] | None:
    matches = [row for row in rows if row.get("market_session") == session.isoformat()]
    if len(matches) > 1:
        raise ValueError("R7 forward ledger contains duplicate sessions")
    return matches[0] if matches else None


def _family_dir(root: Path) -> Path:
    return root / "reports/forward" / FAMILY_NAME


def _resolve_root_file(root: Path, path: Path, *, label: str) -> Path:
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc
    if candidate.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    return resolved


def _binding(path: Path, root: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": _relpath(path, root),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def _binding_valid(root: Path, binding: Any) -> bool:
    if not isinstance(binding, dict):
        return False
    try:
        path = _resolve_root_file(root, Path(str(binding["path"])), label="R7 evidence")
        current = _binding(path, root)
    except (KeyError, OSError, ValueError):
        return False
    return all(current.get(key) == binding.get(key) for key in ("path", "sha256", "size_bytes"))


@contextmanager
def _exclusive_file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _append_ledger_row(path: Path, row: dict[str, Any]) -> None:
    existing = _read_jsonl(path)
    duplicate = _matching_session_row(existing, date.fromisoformat(row["market_session"]))
    if duplicate is not None:
        if duplicate != row:
            raise ValueError("R7 forward ledger session changed")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    content = b"".join(_canonical_json_bytes(item) + b"\n" for item in [*existing, row])
    _atomic_write(path, content, mode=0o600)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("R7 forward ledger rows must be objects")
    return rows


def _write_immutable_json(path: Path, payload: dict[str, Any]) -> None:
    _write_immutable_bytes(path, _canonical_json_bytes(payload) + b"\n")


def _write_immutable_bytes(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"immutable R7 evidence differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, content, mode=0o400)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, _canonical_json_bytes(payload) + b"\n", mode=0o600)


def _atomic_write(path: Path, content: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"R7 JSON artifact must be an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("R7 timestamps must include a timezone")
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
