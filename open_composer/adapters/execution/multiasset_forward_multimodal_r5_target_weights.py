from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import secrets
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.adapters.data.alpaca_snapshot import verify_alpaca_contract_snapshot
from open_composer.adapters.execution.router_target_weights import (
    _cost_stress_payload,
    _data_evidence_payload,
    _validation_payload,
    write_router_execution_artifacts,
)
from open_composer.market_calendar import NEW_YORK, us_equity_session_close
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.evidence_custody import (
    ExternalCustodyRecord,
    verify_external_custody_record,
)
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.research.multiasset_forward_multimodal_r5 import (
    EVALUATION_ANCHOR_CONTRACT,
    ITER_ID,
    ITERATION_DIR,
    R5_CANDIDATE_ROLE_CONTRACT,
    R5_CUSTODY_NAMESPACE,
    R5_SELECTION_PROHIBITED_CANDIDATE_IDS,
    RANKABLE_SYMBOLS,
    RESERVE_SYMBOL,
    SPEC_PATHS,
    PanelData,
    _validate_r5_spec_execution_contract,
    build_candidate_targets_for_segment,
    build_monthly_feature_dataset,
    build_point_in_time_features,
    canonical_target_hash,
    load_r5_panel,
)
from open_composer.strategy_versions import strategy_content_hash
from open_composer.yaml_utils import safe_load_yaml

FORWARD_SESSION_TARGET = 20
MAX_OBSERVATION_CLOCK_SKEW = timedelta(minutes=5)
MAX_SESSION_OBSERVATION_LAG = timedelta(hours=12)
MIN_SNAPSHOT_AFTER_CLOSE_LAG = timedelta(minutes=15)
ADAPTER_RELATIVE_PATH = Path(
    "open_composer/adapters/execution/multiasset_forward_multimodal_r5_target_weights.py"
)
RECEIPT_CONTRACT = "multiasset_forward_multimodal_r5_forward_observation_v1"
READINESS_CONTRACT = "multiasset_forward_multimodal_r5_forward_readiness_v1"
SELECTION_PROHIBITED = R5_SELECTION_PROHIBITED_CANDIDATE_IDS
_EXPECTED_EVALUATION_CHILDREN = {
    "feature_ledger",
    "prediction_ledger",
    "daily_return_ledger",
    "target_ledger",
    "event_ledger",
    "benchmark_ledger",
    "model_ledger",
    "trial_ledger",
    "cost_reconciliation",
    "model_provenance",
    "evaluation",
    "evaluation_markdown",
    "decision_record",
}


@dataclass(frozen=True)
class R5DossierBinding:
    candidate_id: str
    candidate_row: dict[str, Any]
    spec_path: Path
    spec_file_sha256: str
    spec_semantic_sha256: str
    specs: dict[str, StrategySpec]
    forward_epoch: date
    paths: dict[str, Path]
    hashes: dict[str, str]
    operator_lock_anchor_sha256: str
    operator_evaluation_anchor_sha256: str
    adapter_sha256: str
    lock_custody: ExternalCustodyRecord
    evaluation_custody: ExternalCustodyRecord


@dataclass(frozen=True)
class R5TargetComputation:
    candidate_id: str
    targets: pd.DataFrame
    target_records: list[dict[str, Any]]
    model_records: list[dict[str, Any]]
    latest_target_record: dict[str, Any]
    latest_model_record: dict[str, Any] | None
    target_series_sha256: str


@dataclass(frozen=True)
class R5ForwardTargetWeightResult:
    report_path: Path
    target_weights_path: Path
    rebalance_intents_path: Path
    observation_path: Path
    forward_ledger_path: Path
    forward_readiness_path: Path
    receipt_path: Path
    candidate_id: str
    market_session: str
    target_sha256: str
    forward_observation_pass: bool
    execution_substate: str = "observation_only"
    broker_writes: bool = False


def run_multiasset_forward_multimodal_r5_target_weight_mapping(
    spec_path: Path,
    root: Path,
    *,
    candidate_id: str,
    snapshot_manifest_path: Path,
    custody_dir: Path,
    as_of: datetime,
) -> R5ForwardTargetWeightResult:
    base = root.resolve()
    resolved_spec_path = _resolve_root_file(base, spec_path, label="R5 StrategySpec")
    lock_identity = hashlib.sha256(
        f"{_relpath(resolved_spec_path, base)}|{candidate_id}".encode()
    ).hexdigest()
    lock_path = base / "reports" / "forward" / ".locks" / f"{lock_identity}.lock"
    with _exclusive_file_lock(lock_path):
        return _run_multiasset_forward_multimodal_r5_target_weight_mapping_locked(
            resolved_spec_path,
            root,
            candidate_id=candidate_id,
            snapshot_manifest_path=snapshot_manifest_path,
            custody_dir=custody_dir,
            as_of=as_of,
        )


def _run_multiasset_forward_multimodal_r5_target_weight_mapping_locked(
    spec_path: Path,
    root: Path,
    *,
    candidate_id: str,
    snapshot_manifest_path: Path,
    custody_dir: Path,
    as_of: datetime,
) -> R5ForwardTargetWeightResult:
    base = root.resolve()
    observed_at = _as_utc(as_of)
    current_time = _utc_now()
    if observed_at > current_time:
        raise ValueError("R5 forward observation as_of cannot be in the future")
    if current_time - observed_at > MAX_OBSERVATION_CLOCK_SKEW:
        raise ValueError("R5 forward observations cannot be backfilled")

    resolved_spec_path = _resolve_root_file(base, spec_path, label="R5 StrategySpec")
    spec = _load_strategy_spec(resolved_spec_path)
    _require_observation_only_spec(spec, candidate_id, resolved_spec_path, base)
    dossier = _require_final_dossier(
        root=base,
        spec=spec,
        spec_path=resolved_spec_path,
        candidate_id=candidate_id,
        custody_dir=custody_dir,
    )

    manifest_path = _resolve_root_file(
        base,
        snapshot_manifest_path,
        label="R5 forward snapshot manifest",
    )
    manifest_bytes = _read_regular_file_bytes(manifest_path)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    panel = _load_forward_panel(base, manifest_path)
    if _sha256_file(manifest_path) != manifest_hash:
        raise ValueError("R5 forward snapshot manifest changed while loading the panel")
    manifest = panel.manifest
    expected_session = _latest_completed_session(observed_at)
    session_close = _session_close_utc(expected_session)
    if observed_at < session_close or observed_at - session_close > MAX_SESSION_OBSERVATION_LAG:
        raise ValueError("R5 forward observation is outside the non-backfill session window")
    latest_panel_session = pd.Timestamp(panel.close.index.max()).date()
    latest_manifest_session = _manifest_latest_complete_session(manifest)
    retrieved_at = _manifest_retrieved_at(manifest)
    if latest_panel_session != expected_session or latest_manifest_session != expected_session:
        raise ValueError(
            "R5 forward snapshot latest completed session mismatch: "
            f"panel={latest_panel_session.isoformat()} "
            f"manifest={latest_manifest_session.isoformat()} "
            f"expected={expected_session.isoformat()}"
        )
    if not _snapshot_observation_window_valid(
        retrieved_at=retrieved_at,
        session_close=session_close,
        observed_at=observed_at,
    ):
        raise ValueError("R5 forward snapshot retrieval is outside the observation window")
    if expected_session < dossier.forward_epoch:
        raise ValueError("R5 forward observation is before the frozen epoch")

    ledger_path = _forward_dir(base, spec.name) / "decisions.jsonl"
    existing_rows = _read_jsonl(base, ledger_path)
    existing_rows = _recover_orphan_receipts(
        root=base,
        spec=spec,
        dossier=dossier,
        ledger_path=ledger_path,
        rows=existing_rows,
        as_of=observed_at,
    )
    preflight = _build_forward_readiness(
        root=base,
        spec=spec,
        dossier=dossier,
        rows=existing_rows,
        as_of=observed_at,
        pending_session=expected_session,
    )
    if preflight["epoch_closed"]:
        readiness_path = _write_readiness(base, spec.name, preflight)
        raise ValueError(
            "R5 forward epoch is closed because a required contiguous session "
            "is missing or invalid: "
            + ", ".join(preflight["missing_required_sessions"])
            + f" (readiness={_relpath(readiness_path, base)})"
        )

    provenance = {
        "data_manifest_sha256": manifest_hash,
        "feature_contract_sha256": _locked_artifact_hash(dossier, "feature-contract.json"),
        "label_contract_sha256": _locked_artifact_hash(dossier, "label-contract.json"),
        "prompt_hash": _formula_prompt_hash(base, dossier),
    }
    computation = compute_selected_candidate_targets(
        panel,
        dossier.specs,
        candidate_id=candidate_id,
        train_start_session=_training_start(base, dossier),
        provenance=provenance,
    )
    current_weights = {
        str(symbol): float(weight)
        for symbol, weight in computation.targets.iloc[-1].sort_index().items()
    }
    target_sha256 = _target_hash(current_weights)
    if target_sha256 != computation.latest_target_record["target_sha256"]:
        raise ValueError("R5 forward target hash differs from the reference target record")

    duplicate = _matching_session_row(existing_rows, expected_session)
    identity = _receipt_identity(
        root=base,
        dossier=dossier,
        spec=spec,
        manifest_path=manifest_path,
        manifest_hash=manifest_hash,
        market_session=expected_session,
        target_sha256=target_sha256,
        target_series_sha256=computation.target_series_sha256,
    )
    if duplicate is not None:
        if duplicate.get("identity") != identity:
            raise ValueError("R5 forward receipt already exists with different bound contents")
        readiness = _build_forward_readiness(
            root=base,
            spec=spec,
            dossier=dossier,
            rows=existing_rows,
            as_of=observed_at,
        )
        if expected_session.isoformat() not in readiness["valid_session_ids"]:
            raise ValueError("existing R5 forward receipt is invalid or tampered")
        _write_readiness(base, spec.name, readiness)
        _write_latest_report_from_existing(base, spec, duplicate, readiness)
        return _result_from_existing(base, spec, duplicate, readiness)

    target_rows, intents = _execution_rows(
        spec=spec,
        computation=computation,
        spec_hash=dossier.spec_semantic_sha256,
        manifest_hash=manifest_hash,
    )
    parity = _expected_parity(candidate_id, expected_session.isoformat())
    with _router_stage(
        base,
        spec_name=spec.name,
        spec_path=resolved_spec_path,
    ) as (router_stage_root, staged_spec_path):
        staged_artifacts = write_router_execution_artifacts(
            root=router_stage_root,
            spec_path=staged_spec_path,
            spec=spec,
            target_rows=target_rows,
            rebalance_intents=intents,
            data_profile={
                "source_mode": "immutable_alpaca_contract_snapshot",
                "provider": "alpaca",
                "feed": "sip",
                "adjustment": "all",
                "session_scope": "regular",
                "snapshot_manifest_path": _relpath(manifest_path, base),
                "snapshot_manifest_sha256": manifest_hash,
                "snapshot_retrieved_at": retrieved_at.isoformat(),
                "latest_complete_session": expected_session.isoformat(),
            },
            route_label=spec.portfolio.selected_route_label,
            mapping_summary={
                "iter_id": ITER_ID,
                "candidate_id": candidate_id,
                "spec_hash": dossier.spec_semantic_sha256,
                "target_sha256": target_sha256,
                "target_series_sha256": computation.target_series_sha256,
                "fallback_evidence": _fallback_evidence(computation),
                "paper_order_authorization": False,
                "broker_writes": False,
                "generic_paper_bridge": False,
            },
            acquisition_tier="research_strict",
            parity_check=parity,
            target_backend="python_reference_observation",
            generated_at=observed_at,
        )
        _bind_staged_observation_to_evidence(
            root=base,
            strategy_name=spec.name,
            market_session=expected_session,
            artifacts=staged_artifacts,
        )
        _require_observation_artifacts(
            spec,
            staged_artifacts,
            root=base,
            market_session=expected_session,
        )
        if _sha256_file(manifest_path) != manifest_hash:
            raise ValueError("R5 forward snapshot manifest changed before evidence publication")
        calculation = {
            "schema_version": 1,
            "report_type": "multiasset_forward_multimodal_r5_target_calculation",
            "iter_id": ITER_ID,
            "candidate_id": candidate_id,
            "market_session": expected_session.isoformat(),
            "latest_target_record": computation.latest_target_record,
            "latest_model_record": computation.latest_model_record,
            "target_series_sha256": computation.target_series_sha256,
            "fallback_evidence": _fallback_evidence(computation),
            "paper_order_authorization": False,
            "broker_writes": False,
        }
        evidence_bindings = _freeze_forward_evidence(
            root=base,
            strategy_name=spec.name,
            market_session=expected_session,
            file_sources={
                **staged_artifacts,
                "strategy_spec": dossier.spec_path,
                "preregistration_lock": dossier.paths["preregistration_lock"],
                "runner_lock": dossier.paths["runner_lock"],
                "lock_anchor": dossier.paths["lock_anchor"],
                "evaluation_receipt": dossier.paths["evaluation_receipt"],
                "evaluation_anchor": dossier.paths["evaluation_anchor"],
                "evaluation_attempt": dossier.paths["evaluation_attempt"],
                "adapter_implementation": base / ADAPTER_RELATIVE_PATH,
                "external_lock_custody_receipt": dossier.lock_custody.receipt_path,
                "external_evaluation_custody_receipt": dossier.evaluation_custody.receipt_path,
            },
            byte_sources={"snapshot_manifest": (manifest_path.suffix, manifest_bytes)},
            generated_payloads={"target_calculation": calculation},
        )
    artifacts = {
        role: base / evidence_bindings[role]["path"]
        for role in (
            "router_target_weights",
            "router_rebalance_intents",
            "router_execution_observation",
            "router_cost_stress",
            "router_data_evidence",
            "router_validation",
        )
    }
    receipt = {
        "schema_version": 1,
        "receipt_contract": RECEIPT_CONTRACT,
        "evidence_class": "broker_free_forward_observation",
        "identity": identity,
        "strategy_name": spec.name,
        "iter_id": ITER_ID,
        "candidate_id": candidate_id,
        "market_session": expected_session.isoformat(),
        "observed_at": observed_at.isoformat(),
        "forward_epoch": dossier.forward_epoch.isoformat(),
        "latest_target_session": str(computation.targets.index[-1].date()),
        "target_sha256": target_sha256,
        "target_series_sha256": computation.target_series_sha256,
        "weights": current_weights,
        "selected_symbols": computation.latest_target_record["selected_symbols"],
        "fallback_evidence": _fallback_evidence(computation),
        "snapshot_manifest_path": _relpath(manifest_path, base),
        "snapshot_manifest_sha256": manifest_hash,
        "snapshot_retrieved_at": retrieved_at.isoformat(),
        "spec_file_sha256": dossier.spec_file_sha256,
        "spec_semantic_sha256": dossier.spec_semantic_sha256,
        "preregistration_lock_sha256": dossier.hashes["preregistration_lock"],
        "runner_lock_sha256": dossier.hashes["runner_lock"],
        "lock_anchor_sha256": dossier.hashes["lock_anchor"],
        "operator_lock_anchor_sha256": dossier.operator_lock_anchor_sha256,
        "evaluation_receipt_sha256": dossier.hashes["evaluation_receipt"],
        "evaluation_anchor_sha256": dossier.hashes["evaluation_anchor"],
        "operator_evaluation_anchor_sha256": dossier.operator_evaluation_anchor_sha256,
        "evaluation_attempt_sha256": dossier.hashes["evaluation_attempt"],
        "adapter_implementation_sha256": dossier.adapter_sha256,
        "lock_custody_receipt_sha256": dossier.lock_custody.receipt_sha256,
        "lock_custody_bundle_sha256": dossier.lock_custody.bundle_sha256,
        "evaluation_custody_receipt_sha256": dossier.evaluation_custody.receipt_sha256,
        "evaluation_custody_bundle_sha256": dossier.evaluation_custody.bundle_sha256,
        "evidence_bindings": evidence_bindings,
        "execution_substate": "observation_only",
        "paper_order_authorization": False,
        "broker_writes": False,
        "generic_paper_bridge": False,
    }
    receipt_path = (
        _forward_dir(base, spec.name) / "receipts" / f"{expected_session.isoformat()}.json"
    )
    receipt_bytes = _canonical_json_bytes(receipt)
    _write_immutable_bytes(base, receipt_path, receipt_bytes)
    ledger_row = {
        **receipt,
        "forward_receipt": {
            "path": _relpath(receipt_path, base),
            "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "size_bytes": len(receipt_bytes),
        },
    }
    _append_ledger_row(base, ledger_path, ledger_row)

    rows = _read_jsonl(base, ledger_path)
    readiness = _build_forward_readiness(
        root=base,
        spec=spec,
        dossier=dossier,
        rows=rows,
        as_of=observed_at,
    )
    readiness_path = _write_readiness(base, spec.name, readiness)
    report_path = _forward_dir(base, spec.name) / "latest-observation.json"
    report = {
        "schema_version": 1,
        "report_type": "multiasset_forward_multimodal_r5_forward_observation",
        "strategy_name": spec.name,
        "iter_id": ITER_ID,
        "candidate_id": candidate_id,
        "generated_at": observed_at.isoformat(),
        "market_session": expected_session.isoformat(),
        "target_sha256": target_sha256,
        "target_series_sha256": computation.target_series_sha256,
        "fallback_evidence": _fallback_evidence(computation),
        "receipt": ledger_row["forward_receipt"],
        "forward_readiness": readiness,
        "artifacts": {key: _relpath(path, base) for key, path in artifacts.items()},
        "evidence_bindings": evidence_bindings,
        "execution_substate": "observation_only",
        "research_pass": True,
        "paper_ready_pass": False,
        "paper_order_authorization": False,
        "broker_writes": False,
        "generic_paper_bridge": False,
    }
    _write_json_atomic(base, report_path, report)
    return R5ForwardTargetWeightResult(
        report_path=report_path,
        target_weights_path=artifacts["router_target_weights"],
        rebalance_intents_path=artifacts["router_rebalance_intents"],
        observation_path=artifacts["router_execution_observation"],
        forward_ledger_path=ledger_path,
        forward_readiness_path=readiness_path,
        receipt_path=receipt_path,
        candidate_id=candidate_id,
        market_session=expected_session.isoformat(),
        target_sha256=target_sha256,
        forward_observation_pass=bool(readiness["forward_observation_pass"]),
    )


def compute_selected_candidate_targets(
    panel: PanelData,
    specs: dict[str, StrategySpec],
    *,
    candidate_id: str,
    train_start_session: str,
    provenance: dict[str, str] | None = None,
) -> R5TargetComputation:
    if candidate_id not in SPEC_PATHS or candidate_id in SELECTION_PROHIBITED:
        raise ValueError(f"R5 candidate is not deployable: {candidate_id}")
    execution_contract = _validate_r5_spec_execution_contract(specs)
    features = build_point_in_time_features(
        panel.close,
        panel.volume,
        formula_spec=specs[execution_contract["formula_spec_candidate_id"]],
    )
    dataset = build_monthly_feature_dataset(
        panel,
        features,
        placebo_spec=specs[execution_contract["placebo_spec_candidate_id"]],
        rebalance_schedule=execution_contract["rebalance_schedule"],
    )
    latest_panel_session = pd.Timestamp(panel.close.index.max()).date().isoformat()
    points = (
        dataset[dataset["execution_session"] <= latest_panel_session][
            ["execution_position", "execution_session"]
        ]
        .drop_duplicates()
        .sort_values("execution_position")
    )
    if points.empty:
        raise ValueError("R5 forward panel has no completed monthly execution point")
    selected_points = points.tail(2)
    execution_start = str(selected_points["execution_session"].iloc[0])
    execution_end = str(selected_points["execution_session"].iloc[-1])
    frames, target_records, model_records, _ = build_candidate_targets_for_segment(
        dataset,
        segment_id="FORWARD",
        execution_start=execution_start,
        execution_end=execution_end,
        train_start_session=train_start_session,
        columns=panel.open.columns,
        specs=specs,
        provenance=provenance,
    )
    targets = frames[candidate_id]
    selected_records = [row for row in target_records if row["candidate_id"] == candidate_id]
    if len(selected_records) != len(targets):
        raise ValueError("R5 reference target records are incomplete for selected candidate")
    selected_models = [row for row in model_records if row["candidate_id"] == candidate_id]
    latest_record = max(selected_records, key=lambda row: str(row["execution_session"]))
    latest_models = [
        row
        for row in selected_models
        if str(row["decision_session"]) == str(latest_record["decision_session"])
    ]
    if specs[candidate_id].model is not None and len(latest_models) != 1:
        raise ValueError("R5 selected model candidate lacks one current model record")
    if specs[candidate_id].model is None and latest_models:
        raise ValueError("R5 deterministic candidate unexpectedly has a model record")
    return R5TargetComputation(
        candidate_id=candidate_id,
        targets=targets,
        target_records=selected_records,
        model_records=selected_models,
        latest_target_record=latest_record,
        latest_model_record=latest_models[0] if latest_models else None,
        target_series_sha256=canonical_target_hash(targets),
    )


def _require_observation_only_spec(
    spec: StrategySpec,
    candidate_id: str,
    spec_path: Path,
    root: Path,
) -> None:
    if candidate_id not in SPEC_PATHS:
        raise ValueError(f"unknown R5 candidate: {candidate_id}")
    if candidate_id in SELECTION_PROHIBITED:
        raise ValueError(f"R5 candidate is selection-prohibited: {candidate_id}")
    expected_path = (root / SPEC_PATHS[candidate_id]).resolve()
    if spec_path != expected_path:
        raise ValueError("requested R5 candidate does not match the canonical candidate spec path")
    expected_name = f"us_multiasset_forward_mm_r5_{candidate_id.removeprefix('R5').lower()}"
    notes = spec.notes.model_dump(mode="json")
    design = spec.research_design.model_dump(mode="json") if spec.research_design else {}
    if spec.name != expected_name or notes.get("candidate_id") != candidate_id:
        raise ValueError("R5 candidate identity or strategy name mismatch")
    if design.get("iter_id") != ITER_ID:
        raise ValueError("R5 target mapping requires the frozen R5 iteration id")
    if spec.portfolio.mode != "cross_sectional_momentum":
        raise ValueError("R5 target mapping requires portfolio.mode=cross_sectional_momentum")
    if spec.lifecycle != "draft" or spec.execution.mode != "manual_signal":
        raise ValueError("R5 broker-free target mapping requires draft/manual_signal")
    if spec.execution.broker != "none":
        raise ValueError("R5 broker-free target mapping forbids broker access")


def _require_final_dossier(
    *,
    root: Path,
    spec: StrategySpec,
    spec_path: Path,
    candidate_id: str,
    custody_dir: Path,
) -> R5DossierBinding:
    validation = validate_iteration_dossier(ITER_ID, root, stage="final")
    if not validation.ok:
        raise ValueError("R5 final dossier is incomplete: " + ", ".join(validation.blocked))
    iteration = root / ITERATION_DIR
    paths = {
        "preregistration_lock": iteration / "lock-set/preregistration-lock.json",
        "runner_lock": iteration / "lock-set/runner-lock.json",
        "lock_anchor": iteration / "lock-set/lock-anchor.json",
        "evaluation_attempt": iteration / "evaluation-attempt.json",
        "evaluation_receipt": iteration / "evaluation-run/evaluation-receipt.json",
        "evaluation_anchor": iteration / "evaluation-run/evaluation-anchor.json",
        "evaluation_report": iteration / "evaluation-run/evaluation-report.json",
    }
    payloads = {name: _read_json(path, label=name) for name, path in paths.items()}
    hashes = {name: _sha256_file(path) for name, path in paths.items()}

    prereg = payloads["preregistration_lock"]
    runner = payloads["runner_lock"]
    lock_anchor = payloads["lock_anchor"]
    receipt = payloads["evaluation_receipt"]
    evaluation_anchor = payloads["evaluation_anchor"]
    evaluation = payloads["evaluation_report"]
    if prereg.get("iter_id") != ITER_ID or prereg.get("status") != (
        "behavior_contracts_locked_before_first_r5_price_calculation"
    ):
        raise ValueError("R5 preregistration lock identity is invalid")
    for binding in prereg.get("artifacts", []):
        _verify_binding(root, binding, label="preregistration artifact")

    spec_rows = prereg.get("specs")
    if not isinstance(spec_rows, list) or len(spec_rows) != len(SPEC_PATHS):
        raise ValueError("R5 preregistration spec inventory is incomplete")
    specs: dict[str, StrategySpec] = {}
    requested_spec_row: dict[str, Any] | None = None
    for row in spec_rows:
        if not isinstance(row, dict):
            raise ValueError("R5 locked spec row is invalid")
        locked_candidate = str(row.get("candidate_id") or "")
        expected_relative = SPEC_PATHS.get(locked_candidate)
        if expected_relative is None or row.get("path") != expected_relative.as_posix():
            raise ValueError("R5 locked spec candidate/path binding is invalid")
        path = _verify_binding(
            root,
            {"path": row.get("path"), "sha256": row.get("file_sha256")},
            label=f"locked spec {locked_candidate}",
        )
        loaded = _load_strategy_spec(path)
        if strategy_content_hash(loaded) != row.get("semantic_sha256"):
            raise ValueError(f"R5 locked semantic spec hash mismatch: {locked_candidate}")
        specs[locked_candidate] = loaded
        if locked_candidate == candidate_id:
            requested_spec_row = row
    if set(specs) != set(SPEC_PATHS) or requested_spec_row is None:
        raise ValueError("R5 locked spec candidate inventory is incomplete")
    if spec_path != (root / str(requested_spec_row["path"])).resolve():
        raise ValueError("current R5 StrategySpec is not the locked requested candidate file")
    if strategy_content_hash(spec) != requested_spec_row["semantic_sha256"]:
        raise ValueError("current R5 StrategySpec semantic hash differs from lock")
    _validate_r5_spec_execution_contract(specs)

    if runner.get("iter_id") != ITER_ID or runner.get("status") != (
        "implementation_locked_before_first_r5_price_calculation"
    ):
        raise ValueError("R5 runner lock identity is invalid")
    runner_files = runner.get("files")
    if not isinstance(runner_files, list) or not runner_files:
        raise ValueError("R5 runner lock file inventory is missing")
    adapter_binding: dict[str, Any] | None = None
    for binding in runner_files:
        _verify_binding(root, binding, label="runner file")
        if isinstance(binding, dict) and binding.get("path") == ADAPTER_RELATIVE_PATH.as_posix():
            adapter_binding = binding
    if adapter_binding is None:
        raise ValueError("R5 runner lock does not bind the forward target adapter")
    adapter_sha256 = _sha256_file(root / ADAPTER_RELATIVE_PATH)
    if adapter_binding.get("sha256") != adapter_sha256:
        raise ValueError("R5 forward target adapter implementation hash differs from runner lock")

    anchor_subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": hashes["preregistration_lock"],
        "runner_lock_sha256": hashes["runner_lock"],
    }
    operator_lock_anchor = hashlib.sha256(_canonical_json_bytes(anchor_subject)).hexdigest()
    if (
        lock_anchor.get("schema_version") != 1
        or any(lock_anchor.get(key) != value for key, value in anchor_subject.items())
        or lock_anchor.get("operator_lock_anchor_sha256") != operator_lock_anchor
    ):
        raise ValueError("R5 lock anchor is stale or inconsistent")

    if (
        receipt.get("schema_version") != 3
        or receipt.get("receipt_contract") != "multiasset_forward_multimodal_r5_v3"
        or receipt.get("iter_id") != ITER_ID
        or receipt.get("evidence_publication_status") != "complete"
        or receipt.get("research_pass") is not True
        or receipt.get("paper_ready_pass") is not False
    ):
        raise ValueError("R5 evaluation receipt is incomplete or research_pass is false")
    for name in ("preregistration_lock", "runner_lock", "lock_anchor", "evaluation_attempt"):
        expected_name = name
        if receipt.get(name) != _binding(root, paths[expected_name]):
            raise ValueError(f"R5 evaluation receipt {name} binding mismatch")
    children = receipt.get("children")
    if not isinstance(children, dict) or not _EXPECTED_EVALUATION_CHILDREN.issubset(children):
        raise ValueError("R5 evaluation receipt child inventory is incomplete")
    for name, binding in children.items():
        _verify_binding(root, binding, label=f"evaluation child {name}")
    if children["evaluation"] != _binding(root, paths["evaluation_report"]):
        raise ValueError("R5 evaluation report is not the receipt-bound evaluation child")

    if (
        evaluation.get("iter_id") != ITER_ID
        or evaluation.get("workflow_pass") is not True
        or evaluation.get("research_pass") is not True
        or evaluation.get("paper_ready_pass") is not False
        or evaluation.get("decision") != "continue_to_locked_forward_observation"
    ):
        raise ValueError("R5 evaluation report does not authorize broker-free forward observation")
    selected = evaluation.get("selected_candidate_ids")
    if (
        not isinstance(selected, list)
        or len(selected) != len(set(selected))
        or candidate_id not in selected
        or set(selected) - set(SPEC_PATHS)
        or set(selected) & set(SELECTION_PROHIBITED)
    ):
        raise ValueError("requested R5 candidate is not selected by the authoritative evaluation")
    evaluation_candidates = evaluation.get("candidates")
    if not isinstance(evaluation_candidates, dict) or set(evaluation_candidates) != set(SPEC_PATHS):
        raise ValueError("R5 evaluation candidate inventory is incomplete")
    for locked_candidate, contract in R5_CANDIDATE_ROLE_CONTRACT.items():
        row = evaluation_candidates.get(locked_candidate)
        if (
            not isinstance(row, dict)
            or row.get("promotion_eligible") is not contract["promotion_eligible"]
        ):
            raise ValueError(
                f"R5 evaluation eligibility differs from immutable role contract: "
                f"{locked_candidate}"
            )
    if evaluation_candidates[candidate_id].get("promotion_eligible") is not True:
        raise ValueError("requested R5 candidate is not promotion-eligible in evaluation")

    artifact_paths = {
        str(binding.get("path")): binding
        for binding in prereg.get("artifacts", [])
        if isinstance(binding, dict)
    }
    manifest_relative = (ITERATION_DIR / "candidate-manifest.json").as_posix()
    manifest_binding = artifact_paths.get(manifest_relative)
    if manifest_binding is None:
        raise ValueError("R5 candidate manifest is not preregistration-locked")
    candidate_manifest_path = _verify_binding(
        root,
        manifest_binding,
        label="locked candidate manifest",
    )
    candidate_manifest = _read_json(candidate_manifest_path, label="candidate manifest")
    rows = candidate_manifest.get("candidates")
    if not isinstance(rows, list) or len(rows) != len(SPEC_PATHS):
        raise ValueError("R5 locked candidate manifest inventory is incomplete")
    by_id = {str(row.get("candidate_id") or ""): row for row in rows if isinstance(row, dict)}
    if list(by_id) != list(SPEC_PATHS) or any(
        by_id[locked_candidate] != contract
        for locked_candidate, contract in R5_CANDIDATE_ROLE_CONTRACT.items()
    ):
        raise ValueError("R5 locked candidate manifest differs from immutable role contract")
    candidate_row = by_id[candidate_id]
    if (
        candidate_row.get("promotion_eligible") is not True
        or candidate_row.get("spec_path") != requested_spec_row["path"]
        or candidate_id in SELECTION_PROHIBITED
    ):
        raise ValueError("requested R5 candidate is selection-prohibited or spec-mismatched")

    anchor_subject = {
        key: value
        for key, value in evaluation_anchor.items()
        if key != "operator_evaluation_anchor_sha256"
    }
    operator_evaluation_anchor = hashlib.sha256(_canonical_json_bytes(anchor_subject)).hexdigest()
    if (
        evaluation_anchor.get("schema_version") != 1
        or evaluation_anchor.get("anchor_contract") != EVALUATION_ANCHOR_CONTRACT
        or evaluation_anchor.get("iter_id") != ITER_ID
        or evaluation_anchor.get("status") != "complete_for_external_hash_custody"
        or evaluation_anchor.get("operator_lock_anchor_sha256") != operator_lock_anchor
        or evaluation_anchor.get("operator_evaluation_anchor_sha256") != operator_evaluation_anchor
        or evaluation_anchor.get("receipt") != _binding(root, paths["evaluation_receipt"])
        or evaluation_anchor.get("preregistration_lock")
        != _binding(root, paths["preregistration_lock"])
        or evaluation_anchor.get("runner_lock") != _binding(root, paths["runner_lock"])
        or evaluation_anchor.get("lock_anchor") != _binding(root, paths["lock_anchor"])
        or evaluation_anchor.get("evaluation_attempt")
        != _binding(root, paths["evaluation_attempt"])
    ):
        raise ValueError("R5 evaluation anchor is stale or inconsistent")

    holdout_relative = (ITERATION_DIR / "holdout-contract.json").as_posix()
    holdout_binding = artifact_paths.get(holdout_relative)
    if holdout_binding is None:
        raise ValueError("R5 holdout contract is not preregistration-locked")
    holdout = _read_json(
        _verify_binding(root, holdout_binding, label="locked holdout contract"),
        label="holdout contract",
    )
    if (
        holdout.get("iter_id") != ITER_ID
        or holdout.get("forward_count_start") != 0
        or holdout.get("minimum_contiguous_bound_sessions") != FORWARD_SESSION_TARGET
        or holdout.get("backfill_allowed") is not False
        or holdout.get("strategy_or_implementation_change_resets_count") is not True
        or holdout.get("missing_required_session_action")
        != "close_epoch_and_start_new_epoch_after_adjudication"
    ):
        raise ValueError("R5 holdout forward contract is incompatible")
    forward_epoch = _epoch_date(holdout.get("forward_epoch_utc"))
    lock_custody, evaluation_custody = _require_external_custody(
        root=root,
        custody_dir=custody_dir,
        preregistration=prereg,
        runner=runner,
        evaluation_receipt=receipt,
        paths=paths,
        hashes=hashes,
        operator_lock_anchor_sha256=operator_lock_anchor,
        operator_evaluation_anchor_sha256=operator_evaluation_anchor,
    )
    return R5DossierBinding(
        candidate_id=candidate_id,
        candidate_row=candidate_row,
        spec_path=spec_path,
        spec_file_sha256=str(requested_spec_row["file_sha256"]),
        spec_semantic_sha256=str(requested_spec_row["semantic_sha256"]),
        specs=specs,
        forward_epoch=forward_epoch,
        paths=paths | {"candidate_manifest": candidate_manifest_path},
        hashes=hashes | {"candidate_manifest": _sha256_file(candidate_manifest_path)},
        operator_lock_anchor_sha256=operator_lock_anchor,
        operator_evaluation_anchor_sha256=operator_evaluation_anchor,
        adapter_sha256=adapter_sha256,
        lock_custody=lock_custody,
        evaluation_custody=evaluation_custody,
    )


def _require_external_custody(
    *,
    root: Path,
    custody_dir: Path,
    preregistration: dict[str, Any],
    runner: dict[str, Any],
    evaluation_receipt: dict[str, Any],
    paths: dict[str, Path],
    hashes: dict[str, str],
    operator_lock_anchor_sha256: str,
    operator_evaluation_anchor_sha256: str,
) -> tuple[ExternalCustodyRecord, ExternalCustodyRecord]:
    lock_receipt_path = (
        custody_dir / R5_CUSTODY_NAMESPACE / "lock" / operator_lock_anchor_sha256 / "receipt.json"
    )
    lock_record = verify_external_custody_record(
        project_root=root,
        custody_root=custody_dir,
        receipt_path=lock_receipt_path,
        expected_namespace=R5_CUSTODY_NAMESPACE,
        expected_record_kind="lock",
        expected_subject_sha256=operator_lock_anchor_sha256,
    )
    lock_subject = lock_record.payload.get("subject")
    if (
        not isinstance(lock_subject, dict)
        or lock_subject.get("iter_id") != ITER_ID
        or lock_subject.get("operator_lock_anchor_sha256") != operator_lock_anchor_sha256
        or lock_subject.get("lock_anchor_file_sha256") != hashes["lock_anchor"]
        or lock_subject.get("source_bundle_complete") is not True
    ):
        raise ValueError("R5 external lock custody subject is invalid")
    expected_lock_entries: dict[str, str] = {}
    for binding in preregistration.get("artifacts", []):
        _add_expected_custody_entry(
            expected_lock_entries,
            binding,
            hash_field="sha256",
            label="preregistration artifact",
        )
    for binding in preregistration.get("specs", []):
        _add_expected_custody_entry(
            expected_lock_entries,
            binding,
            hash_field="file_sha256",
            label="locked StrategySpec",
        )
    for binding in runner.get("files", []):
        _add_expected_custody_entry(
            expected_lock_entries,
            binding,
            hash_field="sha256",
            label="runner file",
        )
    for name in ("preregistration_lock", "runner_lock", "lock_anchor"):
        expected_lock_entries[_relpath(paths[name], root)] = hashes[name]
    _require_custody_entries(lock_record, expected_lock_entries, label="lock")

    evaluation_receipt_path = (
        custody_dir
        / R5_CUSTODY_NAMESPACE
        / "evaluation"
        / operator_evaluation_anchor_sha256
        / "receipt.json"
    )
    evaluation_record = verify_external_custody_record(
        project_root=root,
        custody_root=custody_dir,
        receipt_path=evaluation_receipt_path,
        expected_namespace=R5_CUSTODY_NAMESPACE,
        expected_record_kind="evaluation",
        expected_subject_sha256=operator_evaluation_anchor_sha256,
    )
    evaluation_subject = evaluation_record.payload.get("subject")
    if (
        not isinstance(evaluation_subject, dict)
        or evaluation_subject.get("iter_id") != ITER_ID
        or evaluation_subject.get("operator_lock_anchor_sha256") != operator_lock_anchor_sha256
        or evaluation_subject.get("operator_evaluation_anchor_sha256")
        != operator_evaluation_anchor_sha256
        or evaluation_subject.get("evaluation_anchor_file_sha256") != hashes["evaluation_anchor"]
        or evaluation_subject.get("lock_custody_receipt_sha256") != lock_record.receipt_sha256
        or evaluation_subject.get("publication_only_recovery_allowed") is not True
        or evaluation_subject.get("price_recomputation_allowed") is not False
    ):
        raise ValueError("R5 external evaluation custody subject is invalid")
    expected_evaluation_entries = {
        _relpath(paths[name], root): hashes[name]
        for name in (
            "preregistration_lock",
            "runner_lock",
            "lock_anchor",
            "evaluation_attempt",
            "evaluation_receipt",
            "evaluation_anchor",
        )
    }
    children = evaluation_receipt.get("children")
    if not isinstance(children, dict):
        raise ValueError("R5 evaluation custody lacks a receipt child inventory")
    for binding in children.values():
        _add_expected_custody_entry(
            expected_evaluation_entries,
            binding,
            hash_field="sha256",
            label="evaluation child",
        )
    expected_evaluation_entries["external-custody/lock-receipt.json"] = lock_record.receipt_sha256
    _require_custody_entries(
        evaluation_record,
        expected_evaluation_entries,
        label="evaluation",
    )
    return lock_record, evaluation_record


def _add_expected_custody_entry(
    expected: dict[str, str],
    binding: Any,
    *,
    hash_field: str,
    label: str,
) -> None:
    if not isinstance(binding, dict):
        raise ValueError(f"R5 {label} custody binding is invalid")
    path = binding.get("path")
    digest = binding.get(hash_field)
    if not isinstance(path, str) or not path or not _is_sha256(digest):
        raise ValueError(f"R5 {label} custody binding fields are invalid")
    previous = expected.setdefault(path, digest)
    if previous != digest:
        raise ValueError(f"R5 custody entry has conflicting hashes: {path}")


def _require_custody_entries(
    record: ExternalCustodyRecord,
    expected: dict[str, str],
    *,
    label: str,
) -> None:
    entries = record.payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"R5 external {label} custody entry manifest is invalid")
    actual = {
        str(binding.get("path")): str(binding.get("sha256"))
        for binding in entries
        if isinstance(binding, dict)
    }
    missing_or_changed = sorted(
        path for path, digest in expected.items() if actual.get(path) != digest
    )
    if missing_or_changed:
        raise ValueError(
            f"R5 external {label} custody is incomplete: " + ", ".join(missing_or_changed)
        )


def _execution_rows(
    *,
    spec: StrategySpec,
    computation: R5TargetComputation,
    spec_hash: str,
    manifest_hash: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    records = {str(row["execution_session"]): row for row in computation.target_records}
    target_rows: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    prior = pd.Series(0.0, index=computation.targets.columns, dtype=float)
    for session, weights in computation.targets.iterrows():
        session_text = pd.Timestamp(session).date().isoformat()
        record = records[session_text]
        rebalance_id = (
            "r5_"
            + hashlib.sha256(
                f"{spec.name}|{computation.candidate_id}|{session_text}|{record['target_sha256']}".encode()
            ).hexdigest()[:24]
        )
        for symbol in sorted(computation.targets.columns):
            target_weight = float(weights[symbol])
            from_weight = float(prior[symbol])
            delta = target_weight - from_weight
            side = "buy" if delta > 1e-12 else "sell" if delta < -1e-12 else "hold"
            common = {
                "iter_id": ITER_ID,
                "candidate_id": computation.candidate_id,
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


@contextmanager
def _router_stage(root: Path, *, spec_name: str, spec_path: Path):
    stage_parent = _forward_dir(root, spec_name) / ".router-staging"
    _ensure_output_directory(root, stage_parent)
    stage_root = _make_output_temp_directory(
        root,
        stage_parent,
        prefix="observation-",
    )
    try:
        staged_spec_path = stage_root / _relpath(spec_path, root)
        _write_bytes_atomic(
            root,
            staged_spec_path,
            _read_regular_file_bytes(spec_path),
            mode=0o400,
        )
        yield stage_root, staged_spec_path
    finally:
        _remove_output_tree(root, stage_root, missing_ok=True)
        _fsync_output_directory(root, stage_parent)


def _bind_staged_observation_to_evidence(
    *,
    root: Path,
    strategy_name: str,
    market_session: date,
    artifacts: dict[str, Path],
) -> None:
    try:
        observation_path = artifacts["router_execution_observation"]
    except KeyError as exc:
        raise ValueError("R5 staged router artifact set is incomplete") from exc
    observation = _read_json(observation_path, label="execution observation")
    role_by_field = {
        "target_weights_path": "router_target_weights",
        "rebalance_intents_path": "router_rebalance_intents",
        "cost_stress_path": "router_cost_stress",
        "data_evidence_path": "router_data_evidence",
        "validation_path": "router_validation",
    }
    for field_name, role in role_by_field.items():
        source = artifacts.get(role)
        if source is None:
            raise ValueError("R5 staged router artifact set is incomplete")
        observation[field_name] = _relpath(
            _evidence_file_path(
                root,
                strategy_name=strategy_name,
                market_session=market_session,
                role=role,
                suffix=source.suffix,
            ),
            root,
        )
    _write_bytes_atomic(
        root,
        observation_path,
        _canonical_json_bytes(observation) + b"\n",
        mode=0o600,
    )


def _require_observation_artifacts(
    spec: StrategySpec,
    artifacts: dict[str, Path],
    *,
    root: Path,
    market_session: date,
) -> None:
    try:
        target = _read_json(artifacts["router_target_weights"], label="target weights")
        intents = _read_json(artifacts["router_rebalance_intents"], label="rebalance intents")
        observation = _read_json(
            artifacts["router_execution_observation"],
            label="execution observation",
        )
        cost_stress = _read_json(
            artifacts["router_cost_stress"],
            label="router cost stress",
        )
        data_evidence = _read_json(
            artifacts["router_data_evidence"],
            label="router data evidence",
        )
        validation = _read_json(
            artifacts["router_validation"],
            label="router validation",
        )
    except KeyError as exc:
        raise ValueError("R5 router artifact set is incomplete") from exc
    if (
        target.get("strategy_name") != spec.name
        or target.get("portfolio_mode") != "cross_sectional_momentum"
        or target.get("target_backend") != "python_reference_observation"
    ):
        raise ValueError("R5 target-weight artifact identity is invalid")
    intent_rows = intents.get("intents")
    if (
        intents.get("strategy_name") != spec.name
        or intents.get("execution_substate") != "observation_only"
        or not isinstance(intent_rows, list)
        or any(row.get("requires_order") is not False for row in intent_rows)
    ):
        raise ValueError("R5 rebalance intents are not strictly observation-only")
    if (
        observation.get("strategy_name") != spec.name
        or observation.get("execution_substate") != "observation_only"
        or observation.get("blockers")
        or observation.get("latest_rebalance_session") != market_session.isoformat()
    ):
        raise ValueError("R5 execution observation is blocked or orderable")
    role_by_field = {
        "target_weights_path": "router_target_weights",
        "rebalance_intents_path": "router_rebalance_intents",
        "cost_stress_path": "router_cost_stress",
        "data_evidence_path": "router_data_evidence",
        "validation_path": "router_validation",
    }
    for field_name, role in role_by_field.items():
        source = artifacts.get(role)
        if source is None:
            raise ValueError("R5 router artifact set is incomplete")
        expected = _relpath(
            _evidence_file_path(
                root,
                strategy_name=spec.name,
                market_session=market_session,
                role=role,
                suffix=source.suffix,
            ),
            root,
        )
        if observation.get(field_name) != expected:
            raise ValueError("R5 execution observation evidence path binding is invalid")
    summary = target.get("summary")
    data_profile = target.get("data_profile")
    if not isinstance(summary, dict) or not isinstance(data_profile, dict):
        raise ValueError("R5 target-weight summary or data profile is invalid")
    candidate_id = summary.get("candidate_id")
    target_rows = target.get("target_weights")
    parity = _expected_parity(str(candidate_id or ""), market_session.isoformat())
    if not isinstance(target_rows, list):
        raise ValueError("R5 target-weight rows are invalid")
    expected_cost_stress = _cost_stress_payload(spec, summary)
    expected_data_evidence = _data_evidence_payload(
        spec=spec,
        data_profile=data_profile,
        acquisition_tier="research_strict",
    )
    expected_validation = _validation_payload(
        spec=spec,
        summary=summary,
        parity_check=parity,
        target_rows=target_rows,
    )
    if (
        intents.get("summary") != summary
        or cost_stress != expected_cost_stress
        or data_evidence != expected_data_evidence
        or validation != expected_validation
        or expected_validation.get("status") != "ok"
        or expected_validation.get("blockers")
    ):
        raise ValueError("R5 supporting router artifact semantics are invalid")


def _expected_parity(candidate_id: str, market_session: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "blockers": [],
        "warnings": [
            "observation_only_no_broker_writes",
            "not_connected_to_generic_paper_authorization",
        ],
        "reference_implementation": (
            "open_composer.research.multiasset_forward_multimodal_r5."
            "build_candidate_targets_for_segment"
        ),
        "target_rows_match_frozen_r5_reference": True,
        "candidate_id": candidate_id,
        "latest_complete_session": market_session,
    }


def _build_forward_readiness(
    *,
    root: Path,
    spec: StrategySpec,
    dossier: R5DossierBinding,
    rows: list[dict[str, Any]],
    as_of: datetime,
    pending_session: date | None = None,
) -> dict[str, Any]:
    cutoff_session = _latest_completed_session(as_of)
    valid: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, Any]] = []
    for line_number, row in enumerate(rows, start=1):
        reasons = _validate_ledger_row(
            root=root,
            spec=spec,
            dossier=dossier,
            row=row,
            as_of=as_of,
        )
        session = str(row.get("market_session") or "")
        if session in valid:
            reasons.append("duplicate_market_session")
        if reasons:
            excluded.append(
                {"line": line_number, "market_session": session, "reasons": sorted(set(reasons))}
            )
        else:
            valid[session] = row

    required = _expected_sessions(dossier.forward_epoch, count=FORWARD_SESSION_TARGET)
    completed_required = [session for session in required if session <= cutoff_session]
    pending_text = pending_session.isoformat() if pending_session else None
    missing = [
        session.isoformat()
        for session in completed_required
        if session.isoformat() not in valid and session.isoformat() != pending_text
    ]
    contiguous: list[str] = []
    for session in required:
        session_text = session.isoformat()
        if session > cutoff_session or session_text == pending_text:
            break
        if session_text not in valid:
            break
        contiguous.append(session_text)
    invalid_required = sorted(
        {
            item["market_session"]
            for item in excluded
            if item["market_session"] in {session.isoformat() for session in completed_required}
        }
    )
    epoch_closed = bool(missing or invalid_required)
    passed = len(contiguous) >= FORWARD_SESSION_TARGET and not epoch_closed
    return {
        "schema_version": 1,
        "readiness_contract": READINESS_CONTRACT,
        "report_type": "multiasset_forward_multimodal_r5_forward_readiness",
        "strategy_name": spec.name,
        "iter_id": ITER_ID,
        "candidate_id": dossier.candidate_id,
        "generated_at": as_of.isoformat(),
        "forward_epoch": dossier.forward_epoch.isoformat(),
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
        "epoch_close_reason": (
            "missing_or_invalid_required_session_start_new_epoch_after_adjudication"
            if epoch_closed
            else None
        ),
        "forward_observation_pass": passed,
        "workflow_pass": not excluded and not epoch_closed,
        "research_pass": True,
        "paper_ready_pass": False,
        "execution_substate": "observation_only",
        "paper_order_authorization": False,
        "broker_writes": False,
        "generic_paper_bridge": False,
        "preregistration_lock_sha256": dossier.hashes["preregistration_lock"],
        "runner_lock_sha256": dossier.hashes["runner_lock"],
        "operator_lock_anchor_sha256": dossier.operator_lock_anchor_sha256,
        "evaluation_receipt_sha256": dossier.hashes["evaluation_receipt"],
        "operator_evaluation_anchor_sha256": dossier.operator_evaluation_anchor_sha256,
        "adapter_implementation_sha256": dossier.adapter_sha256,
        "lock_custody_receipt_sha256": dossier.lock_custody.receipt_sha256,
        "lock_custody_bundle_sha256": dossier.lock_custody.bundle_sha256,
        "evaluation_custody_receipt_sha256": dossier.evaluation_custody.receipt_sha256,
        "evaluation_custody_bundle_sha256": dossier.evaluation_custody.bundle_sha256,
    }


def _validate_ledger_row(
    *,
    root: Path,
    spec: StrategySpec,
    dossier: R5DossierBinding,
    row: dict[str, Any],
    as_of: datetime,
) -> list[str]:
    reasons: list[str] = []
    expected_fields = {
        "receipt_contract": RECEIPT_CONTRACT,
        "evidence_class": "broker_free_forward_observation",
        "strategy_name": spec.name,
        "iter_id": ITER_ID,
        "candidate_id": dossier.candidate_id,
        "forward_epoch": dossier.forward_epoch.isoformat(),
        "spec_file_sha256": dossier.spec_file_sha256,
        "spec_semantic_sha256": dossier.spec_semantic_sha256,
        "preregistration_lock_sha256": dossier.hashes["preregistration_lock"],
        "runner_lock_sha256": dossier.hashes["runner_lock"],
        "lock_anchor_sha256": dossier.hashes["lock_anchor"],
        "operator_lock_anchor_sha256": dossier.operator_lock_anchor_sha256,
        "evaluation_receipt_sha256": dossier.hashes["evaluation_receipt"],
        "evaluation_anchor_sha256": dossier.hashes["evaluation_anchor"],
        "operator_evaluation_anchor_sha256": dossier.operator_evaluation_anchor_sha256,
        "evaluation_attempt_sha256": dossier.hashes["evaluation_attempt"],
        "adapter_implementation_sha256": dossier.adapter_sha256,
        "lock_custody_receipt_sha256": dossier.lock_custody.receipt_sha256,
        "lock_custody_bundle_sha256": dossier.lock_custody.bundle_sha256,
        "evaluation_custody_receipt_sha256": dossier.evaluation_custody.receipt_sha256,
        "evaluation_custody_bundle_sha256": dossier.evaluation_custody.bundle_sha256,
        "execution_substate": "observation_only",
        "paper_order_authorization": False,
        "broker_writes": False,
        "generic_paper_bridge": False,
    }
    reasons.extend(
        f"{field}_mismatch" for field, value in expected_fields.items() if row.get(field) != value
    )
    try:
        session = date.fromisoformat(str(row["market_session"]))
        observed = _as_utc(datetime.fromisoformat(str(row["observed_at"])))
    except (KeyError, ValueError):
        return reasons + ["session_or_observed_at_invalid"]
    if session < dossier.forward_epoch or us_equity_session_close(session) is None:
        reasons.append("market_session_invalid")
    else:
        session_close = _session_close_utc(session)
        if observed < session_close or observed - session_close > MAX_SESSION_OBSERVATION_LAG:
            reasons.append("observation_session_window_invalid")
    if observed > as_of or _latest_completed_session(observed) != session:
        reasons.append("observation_timing_invalid")
    weights = row.get("weights")
    if not _valid_weights(weights, spec) or _target_hash(weights) != row.get("target_sha256"):
        reasons.append("target_weights_or_hash_invalid")
    try:
        latest_target = date.fromisoformat(str(row.get("latest_target_session") or ""))
    except ValueError:
        reasons.append("latest_target_session_invalid")
    else:
        if latest_target > session:
            reasons.append("latest_target_session_after_observation")
    identity = row.get("identity")
    if not isinstance(identity, dict) or not _is_sha256(row.get("target_series_sha256")):
        reasons.append("receipt_identity_invalid")
    reasons.extend(_validate_evidence_bindings(root, spec, dossier, row))
    binding = row.get("forward_receipt")
    try:
        _, receipt_bytes = _read_bound_file(root, binding, label="forward receipt")
        receipt = json.loads(receipt_bytes)
    except (OSError, ValueError, json.JSONDecodeError):
        reasons.append("forward_receipt_invalid")
    else:
        expected = {key: value for key, value in row.items() if key != "forward_receipt"}
        if receipt != expected:
            reasons.append("forward_receipt_payload_mismatch")
    try:
        manifest_path = _resolve_root_file(
            root,
            Path(str(row.get("snapshot_manifest_path") or "")),
            label="receipt snapshot manifest",
        )
        if _sha256_file(manifest_path) != row.get("snapshot_manifest_sha256"):
            raise ValueError("snapshot hash mismatch")
        expected_identity = _receipt_identity(
            root=root,
            dossier=dossier,
            spec=spec,
            manifest_path=manifest_path,
            manifest_hash=str(row["snapshot_manifest_sha256"]),
            market_session=session,
            target_sha256=str(row["target_sha256"]),
            target_series_sha256=str(row["target_series_sha256"]),
        )
        if identity != expected_identity:
            raise ValueError("receipt identity mismatch")
        manifest = verify_alpaca_contract_snapshot(root, manifest_path)
        retrieved_at = _manifest_retrieved_at(manifest)
        if _manifest_latest_complete_session(
            manifest
        ) != session or not _snapshot_observation_window_valid(
            retrieved_at=retrieved_at,
            session_close=_session_close_utc(session),
            observed_at=observed,
        ):
            raise ValueError("snapshot timing mismatch")
    except (KeyError, OSError, TypeError, ValueError):
        reasons.append("snapshot_bundle_binding_invalid")
    return reasons


def _validate_evidence_bindings(
    root: Path,
    spec: StrategySpec,
    dossier: R5DossierBinding,
    row: dict[str, Any],
) -> list[str]:
    bindings = row.get("evidence_bindings")
    required = {
        "router_target_weights",
        "router_rebalance_intents",
        "router_execution_observation",
        "router_cost_stress",
        "router_data_evidence",
        "router_validation",
        "target_calculation",
        "snapshot_manifest",
        "strategy_spec",
        "preregistration_lock",
        "runner_lock",
        "lock_anchor",
        "evaluation_receipt",
        "evaluation_anchor",
        "evaluation_attempt",
        "adapter_implementation",
        "external_lock_custody_receipt",
        "external_evaluation_custody_receipt",
    }
    if not isinstance(bindings, dict) or set(bindings) != required:
        return ["evidence_binding_roles_missing"]
    payloads: dict[str, bytes] = {}
    reasons: list[str] = []
    expected_parent = (
        _forward_dir(root, spec.name) / "evidence" / str(row.get("market_session") or "")
    ).resolve()
    for role in sorted(required):
        try:
            path, contents = _read_bound_file(root, bindings[role], label=role)
            path.relative_to(expected_parent)
            payloads[role] = contents
        except (OSError, ValueError):
            reasons.append(f"{role}_binding_invalid")
    if reasons:
        return reasons
    expected_hashes = {
        "strategy_spec": dossier.spec_file_sha256,
        "preregistration_lock": dossier.hashes["preregistration_lock"],
        "runner_lock": dossier.hashes["runner_lock"],
        "lock_anchor": dossier.hashes["lock_anchor"],
        "evaluation_receipt": dossier.hashes["evaluation_receipt"],
        "evaluation_anchor": dossier.hashes["evaluation_anchor"],
        "evaluation_attempt": dossier.hashes["evaluation_attempt"],
        "adapter_implementation": dossier.adapter_sha256,
        "external_lock_custody_receipt": dossier.lock_custody.receipt_sha256,
        "external_evaluation_custody_receipt": dossier.evaluation_custody.receipt_sha256,
        "snapshot_manifest": str(row.get("snapshot_manifest_sha256")),
    }
    for role, expected in expected_hashes.items():
        if hashlib.sha256(payloads[role]).hexdigest() != expected:
            reasons.append(f"{role}_content_mismatch")
    latest = str(row.get("latest_target_session") or "")
    target_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    data_profile: dict[str, Any] = {}
    try:
        target = json.loads(payloads["router_target_weights"])
        target_rows = target["target_weights"]
        if not isinstance(target_rows, list) or not target_rows:
            raise ValueError("target rows missing")
        grouped_weights: dict[str, dict[str, float]] = {}
        target_hash_by_session: dict[str, str] = {}
        expected_row_fields = {
            "iter_id": ITER_ID,
            "candidate_id": dossier.candidate_id,
            "spec_hash": dossier.spec_semantic_sha256,
            "snapshot_manifest_sha256": row.get("snapshot_manifest_sha256"),
            "paper_order_authorization": False,
            "broker_writes": False,
        }
        for item in target_rows:
            if not isinstance(item, dict) or any(
                item.get(field) != value for field, value in expected_row_fields.items()
            ):
                raise ValueError("target row identity mismatch")
            session = str(item["rebalance_session"])
            symbol = str(item["symbol"])
            if symbol in grouped_weights.setdefault(session, {}):
                raise ValueError("duplicate target symbol")
            grouped_weights[session][symbol] = float(item["target_weight"])
            item_target_hash = str(item["target_sha256"])
            previous_hash = target_hash_by_session.setdefault(session, item_target_hash)
            if previous_hash != item_target_hash:
                raise ValueError("target session hash mismatch")
        if any(set(weights) != set(spec.universe) for weights in grouped_weights.values()):
            raise ValueError("target universe mismatch")
        for session, weights in grouped_weights.items():
            if _target_hash(weights) != target_hash_by_session[session]:
                raise ValueError("target row hash mismatch")
        target_frame = pd.DataFrame.from_dict(grouped_weights, orient="index").sort_index()
        target_frame.index = pd.DatetimeIndex(target_frame.index)
        weights = grouped_weights[latest]
        summary = target["summary"]
        data_profile = target["data_profile"]
        if (
            target.get("strategy_name") != spec.name
            or target.get("source_spec_path") != _relpath(dossier.spec_path, root)
            or target.get("portfolio_mode") != "cross_sectional_momentum"
            or target.get("target_backend") != "python_reference_observation"
            or summary.get("candidate_id") != dossier.candidate_id
            or summary.get("iter_id") != ITER_ID
            or summary.get("spec_hash") != dossier.spec_semantic_sha256
            or summary.get("target_sha256") != row.get("target_sha256")
            or summary.get("target_series_sha256") != row.get("target_series_sha256")
            or summary.get("paper_order_authorization") is not False
            or summary.get("broker_writes") is not False
            or weights != row.get("weights")
            or canonical_target_hash(target_frame) != row.get("target_series_sha256")
            or data_profile.get("snapshot_manifest_path") != row.get("snapshot_manifest_path")
            or data_profile.get("snapshot_manifest_sha256") != row.get("snapshot_manifest_sha256")
            or data_profile.get("snapshot_retrieved_at") != row.get("snapshot_retrieved_at")
            or data_profile.get("latest_complete_session") != row.get("market_session")
            or data_profile.get("provider") != "alpaca"
            or data_profile.get("feed") != "sip"
            or data_profile.get("adjustment") != "all"
            or data_profile.get("session_scope") != "regular"
        ):
            reasons.append("target_weights_payload_mismatch")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        reasons.append("target_weights_payload_invalid")
    try:
        intents = json.loads(payloads["router_rebalance_intents"])
        intent_rows = intents["intents"]
        if not isinstance(intent_rows, list) or len(intent_rows) != len(target_rows):
            raise ValueError("intent rows missing")
        targets_by_key = {
            (str(item["rebalance_id"]), str(item["symbol"])): item for item in target_rows
        }
        for item in intent_rows:
            target_item = targets_by_key[(str(item["rebalance_id"]), str(item["symbol"]))]
            delta = float(item["to_weight"]) - float(item["from_weight"])
            expected_side = "buy" if delta > 1e-12 else "sell" if delta < -1e-12 else "hold"
            if (
                float(item["to_weight"]) != float(target_item["target_weight"])
                or float(item["delta_weight"]) != delta
                or item.get("side") != expected_side
                or item.get("rebalance_session") != target_item.get("rebalance_session")
                or item.get("iter_id") != ITER_ID
                or item.get("candidate_id") != dossier.candidate_id
                or item.get("spec_hash") != dossier.spec_semantic_sha256
                or item.get("snapshot_manifest_sha256") != row.get("snapshot_manifest_sha256")
                or item.get("target_sha256") != target_item.get("target_sha256")
                or item.get("paper_order_authorization") is not False
                or item.get("broker_writes") is not False
            ):
                raise ValueError("intent semantic mismatch")
        if (
            intents.get("strategy_name") != spec.name
            or intents.get("source_spec_path") != _relpath(dossier.spec_path, root)
            or intents.get("execution_substate") != "observation_only"
            or intents.get("summary") != summary
            or any(item.get("requires_order") is not False for item in intent_rows)
        ):
            reasons.append("rebalance_intents_payload_mismatch")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        reasons.append("rebalance_intents_payload_invalid")
    try:
        observation = json.loads(payloads["router_execution_observation"])
        path_roles = {
            "target_weights_path": "router_target_weights",
            "rebalance_intents_path": "router_rebalance_intents",
            "cost_stress_path": "router_cost_stress",
            "data_evidence_path": "router_data_evidence",
            "validation_path": "router_validation",
        }
        if (
            observation.get("strategy_name") != spec.name
            or observation.get("source_spec_path") != _relpath(dossier.spec_path, root)
            or observation.get("execution_substate") != "observation_only"
            or observation.get("blockers")
            or observation.get("latest_rebalance_session") != latest
            or any(
                observation.get(field_name) != bindings[role]["path"]
                for field_name, role in path_roles.items()
            )
        ):
            reasons.append("execution_observation_payload_mismatch")
    except (KeyError, TypeError, json.JSONDecodeError):
        reasons.append("execution_observation_payload_invalid")
    try:
        calculation = json.loads(payloads["target_calculation"])
        latest_record = calculation.get("latest_target_record", {})
        if (
            calculation.get("iter_id") != ITER_ID
            or calculation.get("candidate_id") != dossier.candidate_id
            or calculation.get("market_session") != row.get("market_session")
            or latest_record.get("candidate_id") != dossier.candidate_id
            or latest_record.get("execution_session") != latest
            or latest_record.get("target_sha256") != row.get("target_sha256")
            or latest_record.get("weights") != row.get("weights")
            or calculation.get("target_series_sha256") != row.get("target_series_sha256")
            or calculation.get("paper_order_authorization") is not False
            or calculation.get("broker_writes") is not False
        ):
            reasons.append("target_calculation_payload_mismatch")
    except (TypeError, json.JSONDecodeError):
        reasons.append("target_calculation_payload_invalid")
    try:
        cost_stress = json.loads(payloads["router_cost_stress"])
        data_evidence = json.loads(payloads["router_data_evidence"])
        validation = json.loads(payloads["router_validation"])
        expected_cost_stress = _cost_stress_payload(spec, summary)
        expected_data_evidence = _data_evidence_payload(
            spec=spec,
            data_profile=data_profile,
            acquisition_tier="research_strict",
        )
        expected_validation = _validation_payload(
            spec=spec,
            summary=summary,
            parity_check=_expected_parity(
                dossier.candidate_id,
                str(row.get("market_session") or ""),
            ),
            target_rows=target_rows,
        )
        if (
            cost_stress != expected_cost_stress
            or data_evidence != expected_data_evidence
            or validation != expected_validation
            or expected_validation.get("status") != "ok"
            or expected_validation.get("blockers")
        ):
            reasons.append("supporting_router_payload_mismatch")
    except (TypeError, ValueError, json.JSONDecodeError):
        reasons.append("supporting_router_payload_invalid")
    return reasons


def _freeze_forward_evidence(
    *,
    root: Path,
    strategy_name: str,
    market_session: date,
    file_sources: dict[str, Path],
    byte_sources: dict[str, tuple[str, bytes]],
    generated_payloads: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    evidence_parent = _forward_dir(root, strategy_name) / "evidence"
    _ensure_output_directory(root, evidence_parent)
    evidence_dir = evidence_parent / market_session.isoformat()
    payloads: dict[str, tuple[str, bytes]] = {}
    for role, source in file_sources.items():
        contents = _read_regular_file_bytes(source)
        suffix = source.suffix if source.suffix in {".json", ".yaml", ".yml", ".py"} else ".bin"
        payloads[role] = (f"{role}{suffix}", contents)
    for role, (raw_suffix, contents) in byte_sources.items():
        suffix = raw_suffix if raw_suffix in {".json", ".yaml", ".yml", ".py"} else ".bin"
        payloads[role] = (f"{role}{suffix}", contents)
    for role, payload in generated_payloads.items():
        payloads[role] = (f"{role}.json", _canonical_json_bytes(payload))
    bindings = {
        role: {
            "path": _relpath(evidence_dir / filename, root),
            "sha256": hashlib.sha256(contents).hexdigest(),
            "size_bytes": len(contents),
        }
        for role, (filename, contents) in sorted(payloads.items())
    }
    if _output_directory_exists(root, evidence_dir):
        _require_complete_evidence_directory(root, evidence_dir, payloads)
        return bindings

    temporary = _make_output_temp_directory(
        root,
        evidence_parent,
        prefix=f".{market_session.isoformat()}.",
        suffix=".tmp",
    )
    try:
        for _role, (filename, contents) in sorted(payloads.items()):
            _write_immutable_bytes(root, temporary / filename, contents)
        _fsync_output_directory(root, temporary)
        try:
            _rename_directory_atomic(temporary, evidence_dir)
        except FileExistsError:
            _require_complete_evidence_directory(root, evidence_dir, payloads)
        _fsync_output_directory(root, evidence_parent)
    finally:
        _remove_output_tree(root, temporary, missing_ok=True)
        _fsync_output_directory(root, evidence_parent)
    _require_complete_evidence_directory(root, evidence_dir, payloads)
    return bindings


def _require_complete_evidence_directory(
    root: Path,
    evidence_dir: Path,
    payloads: dict[str, tuple[str, bytes]],
) -> None:
    expected = {filename: contents for filename, contents in payloads.values()}
    with _open_output_directory(root, evidence_dir, create=False) as descriptor:
        actual = set(os.listdir(descriptor))
        if actual != set(expected):
            raise ValueError("R5 forward evidence bundle inventory differs")
        for filename, contents in expected.items():
            observed, metadata = _read_regular_at(descriptor, filename)
            if observed != contents or metadata.st_mode & 0o222:
                raise ValueError(
                    f"immutable R5 forward evidence differs: {evidence_dir / filename}"
                )


def _evidence_file_path(
    root: Path,
    *,
    strategy_name: str,
    market_session: date,
    role: str,
    suffix: str,
) -> Path:
    normalized_suffix = suffix if suffix in {".json", ".yaml", ".yml", ".py"} else ".bin"
    return (
        _forward_dir(root, strategy_name)
        / "evidence"
        / market_session.isoformat()
        / f"{role}{normalized_suffix}"
    )


def _receipt_identity(
    *,
    root: Path,
    dossier: R5DossierBinding,
    spec: StrategySpec,
    manifest_path: Path,
    manifest_hash: str,
    market_session: date,
    target_sha256: str,
    target_series_sha256: str,
) -> dict[str, str]:
    return {
        "strategy_name": spec.name,
        "candidate_id": dossier.candidate_id,
        "market_session": market_session.isoformat(),
        "forward_epoch": dossier.forward_epoch.isoformat(),
        "spec_file_sha256": dossier.spec_file_sha256,
        "spec_semantic_sha256": dossier.spec_semantic_sha256,
        "snapshot_manifest_path": _relpath(manifest_path, root),
        "snapshot_manifest_sha256": manifest_hash,
        "preregistration_lock_sha256": dossier.hashes["preregistration_lock"],
        "runner_lock_sha256": dossier.hashes["runner_lock"],
        "lock_anchor_sha256": dossier.hashes["lock_anchor"],
        "operator_lock_anchor_sha256": dossier.operator_lock_anchor_sha256,
        "evaluation_receipt_sha256": dossier.hashes["evaluation_receipt"],
        "evaluation_anchor_sha256": dossier.hashes["evaluation_anchor"],
        "operator_evaluation_anchor_sha256": dossier.operator_evaluation_anchor_sha256,
        "evaluation_attempt_sha256": dossier.hashes["evaluation_attempt"],
        "adapter_implementation_sha256": dossier.adapter_sha256,
        "lock_custody_receipt_sha256": dossier.lock_custody.receipt_sha256,
        "lock_custody_bundle_sha256": dossier.lock_custody.bundle_sha256,
        "evaluation_custody_receipt_sha256": dossier.evaluation_custody.receipt_sha256,
        "evaluation_custody_bundle_sha256": dossier.evaluation_custody.bundle_sha256,
        "target_sha256": target_sha256,
        "target_series_sha256": target_series_sha256,
    }


def _fallback_evidence(computation: R5TargetComputation) -> dict[str, Any]:
    model = computation.latest_model_record
    return {
        "fallback_reason": computation.latest_target_record.get("fallback_reason"),
        "unexpected_model_fallback": computation.latest_target_record.get(
            "unexpected_model_fallback"
        ),
        "selected_symbols": computation.latest_target_record.get("selected_symbols"),
        "model_id": model.get("model_id") if model else None,
        "model_status": model.get("status") if model else "not_applicable_deterministic",
        "model_failure_reason": model.get("failure_reason") if model else None,
        "fitted_model_sha256": model.get("fitted_model_sha256") if model else None,
        "prediction_sha256": model.get("prediction_sha256") if model else None,
    }


def _result_from_existing(
    root: Path,
    spec: StrategySpec,
    row: dict[str, Any],
    readiness: dict[str, Any],
) -> R5ForwardTargetWeightResult:
    bindings = row["evidence_bindings"]
    return R5ForwardTargetWeightResult(
        report_path=_forward_dir(root, spec.name) / "latest-observation.json",
        target_weights_path=root / bindings["router_target_weights"]["path"],
        rebalance_intents_path=root / bindings["router_rebalance_intents"]["path"],
        observation_path=root / bindings["router_execution_observation"]["path"],
        forward_ledger_path=_forward_dir(root, spec.name) / "decisions.jsonl",
        forward_readiness_path=_forward_dir(root, spec.name) / "readiness.json",
        receipt_path=root / row["forward_receipt"]["path"],
        candidate_id=dossier_candidate(row),
        market_session=str(row["market_session"]),
        target_sha256=str(row["target_sha256"]),
        forward_observation_pass=bool(readiness["forward_observation_pass"]),
    )


def _write_latest_report_from_existing(
    root: Path,
    spec: StrategySpec,
    row: dict[str, Any],
    readiness: dict[str, Any],
) -> Path:
    bindings = row.get("evidence_bindings")
    if not isinstance(bindings, dict):
        raise ValueError("existing R5 forward receipt lacks evidence bindings")
    artifact_roles = {
        "router_target_weights",
        "router_rebalance_intents",
        "router_execution_observation",
        "router_cost_stress",
        "router_data_evidence",
        "router_validation",
    }
    try:
        artifacts = {role: str(bindings[role]["path"]) for role in sorted(artifact_roles)}
    except (KeyError, TypeError) as exc:
        raise ValueError("existing R5 forward receipt artifact inventory is incomplete") from exc
    path = _forward_dir(root, spec.name) / "latest-observation.json"
    payload = {
        "schema_version": 1,
        "report_type": "multiasset_forward_multimodal_r5_forward_observation",
        "strategy_name": spec.name,
        "iter_id": ITER_ID,
        "candidate_id": str(row["candidate_id"]),
        "generated_at": str(row["observed_at"]),
        "market_session": str(row["market_session"]),
        "target_sha256": str(row["target_sha256"]),
        "target_series_sha256": str(row["target_series_sha256"]),
        "fallback_evidence": row.get("fallback_evidence"),
        "receipt": row["forward_receipt"],
        "forward_readiness": readiness,
        "artifacts": artifacts,
        "evidence_bindings": bindings,
        "execution_substate": "observation_only",
        "research_pass": True,
        "paper_ready_pass": False,
        "paper_order_authorization": False,
        "broker_writes": False,
        "generic_paper_bridge": False,
    }
    _write_json_atomic(root, path, payload)
    return path


def dossier_candidate(row: dict[str, Any]) -> str:
    return str(row["candidate_id"])


def _matching_session_row(rows: list[dict[str, Any]], session: date) -> dict[str, Any] | None:
    matches = [row for row in rows if row.get("market_session") == session.isoformat()]
    if len(matches) > 1:
        raise ValueError("R5 forward ledger contains duplicate market sessions")
    return matches[0] if matches else None


def _forward_output_root(path: Path) -> Path:
    candidate = Path(os.path.abspath(os.fspath(path)))
    matches = [
        index
        for index in range(len(candidate.parts) - 1)
        if candidate.parts[index : index + 2] == ("reports", "forward")
    ]
    if not matches:
        raise ValueError(f"R5 output is outside reports/forward: {path}")
    return Path(*candidate.parts[: matches[-1]])


def _recover_orphan_receipts(
    *,
    root: Path,
    spec: StrategySpec,
    dossier: R5DossierBinding,
    ledger_path: Path,
    rows: list[dict[str, Any]],
    as_of: datetime,
) -> list[dict[str, Any]]:
    receipt_dir = _forward_dir(root, spec.name) / "receipts"
    names = _list_output_directory(root, receipt_dir, missing_ok=True)
    known_sessions = {str(row.get("market_session") or "") for row in rows}
    for name in names:
        try:
            session = date.fromisoformat(Path(name).stem)
        except ValueError as exc:
            raise ValueError(f"unexpected R5 forward receipt entry: {name}") from exc
        if Path(name).suffix != ".json":
            raise ValueError(f"unexpected R5 forward receipt entry: {name}")
        receipt_path = receipt_dir / name
        receipt_bytes = _read_output_file_bytes(root, receipt_path)
        try:
            receipt = json.loads(receipt_bytes)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid orphan R5 forward receipt: {name}") from exc
        if not isinstance(receipt, dict) or receipt.get("market_session") != session.isoformat():
            raise ValueError(f"invalid orphan R5 forward receipt identity: {name}")
        if session.isoformat() in known_sessions:
            continue
        row = {
            **receipt,
            "forward_receipt": {
                "path": _relpath(receipt_path, root),
                "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
                "size_bytes": len(receipt_bytes),
            },
        }
        reasons = _validate_ledger_row(
            root=root,
            spec=spec,
            dossier=dossier,
            row=row,
            as_of=as_of,
        )
        if reasons:
            raise ValueError(
                "orphan R5 forward receipt is invalid and cannot be recovered: "
                + ", ".join(sorted(set(reasons)))
            )
        _append_ledger_row(root, ledger_path, row)
        known_sessions.add(session.isoformat())
    return _read_jsonl(root, ledger_path)


@contextmanager
def _exclusive_file_lock(path: Path):
    root = _forward_output_root(path)
    with _open_output_parent(root, path, create=True) as (parent_fd, name):
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            raise ValueError(f"R5 lock is not a regular file: {path}")
        handle = os.fdopen(descriptor, "a+b")
    with handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _append_ledger_row(root: Path, path: Path, row: dict[str, Any]) -> None:
    with _exclusive_file_lock(path.with_name(f".{path.name}.lock")):
        existing = _read_jsonl(root, path)
        duplicate = _matching_session_row(
            existing,
            date.fromisoformat(row["market_session"]),
        )
        if duplicate is not None:
            if duplicate != row:
                raise ValueError("R5 forward ledger session was concurrently changed")
            return
        contents = b"".join(_canonical_json_bytes(item) + b"\n" for item in [*existing, row])
        _write_bytes_atomic(root, path, contents, mode=0o600)


def _write_readiness(root: Path, strategy_name: str, payload: dict[str, Any]) -> Path:
    path = _forward_dir(root, strategy_name) / "readiness.json"
    _write_json_atomic(root, path, payload)
    return path


def _load_forward_panel(root: Path, manifest_path: Path) -> PanelData:
    return load_r5_panel(
        root,
        manifest_path,
        expected_manifest_sha256=_sha256_file(manifest_path),
    )


def _training_start(root: Path, dossier: R5DossierBinding) -> str:
    path = root / ITERATION_DIR / "validation-contract.json"
    expected = _locked_artifact_hash(dossier, "validation-contract.json")
    payload = _read_json_verified(path, expected, label="validation contract")
    folds = payload.get("folds")
    if not isinstance(folds, list) or not folds or not isinstance(folds[0], dict):
        raise ValueError("R5 validation contract lacks a training start")
    value = str(folds[0].get("train_start") or "")
    date.fromisoformat(value)
    return value


def _formula_prompt_hash(root: Path, dossier: R5DossierBinding) -> str:
    path = root / ITERATION_DIR / "feature-contract.json"
    expected = _locked_artifact_hash(dossier, "feature-contract.json")
    payload = _read_json_verified(path, expected, label="feature contract")
    provenance = payload.get("llm_formula_provenance")
    value = provenance.get("prompt_hash") if isinstance(provenance, dict) else None
    return str(value or "")


def _locked_artifact_hash(dossier: R5DossierBinding, filename: str) -> str:
    prereg = _read_json(dossier.paths["preregistration_lock"], label="preregistration lock")
    expected = (ITERATION_DIR / filename).as_posix()
    matches = [
        str(item.get("sha256"))
        for item in prereg.get("artifacts", [])
        if isinstance(item, dict) and item.get("path") == expected
    ]
    if len(matches) != 1 or not _is_sha256(matches[0]):
        raise ValueError(f"R5 locked artifact binding is missing: {filename}")
    return matches[0]


def _resolve_root_file(root: Path, path: Path, *, label: str) -> Path:
    candidate = path if path.is_absolute() else root / path
    if candidate.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} is not a regular file")
    return resolved


def _verify_binding(root: Path, binding: Any, *, label: str) -> Path:
    path, _contents = _read_bound_file(root, binding, label=label)
    return path


def _binding_fields(binding: Any, *, label: str) -> tuple[str, str, int | None]:
    if not isinstance(binding, dict):
        raise ValueError(f"{label} binding is invalid")
    raw_path = binding.get("path")
    expected_hash = binding.get("sha256")
    if not isinstance(raw_path, str) or not raw_path or not _is_sha256(expected_hash):
        raise ValueError(f"{label} binding fields are invalid")
    size = binding.get("size_bytes")
    if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 0):
        raise ValueError(f"{label} binding size is invalid")
    return raw_path, expected_hash, size


def _binding(root: Path, path: Path) -> dict[str, Any]:
    contents = _read_regular_file_bytes(path)
    return {
        "path": _relpath(path, root),
        "sha256": hashlib.sha256(contents).hexdigest(),
        "size_bytes": len(contents),
    }


def _read_bound_file(root: Path, binding: Any, *, label: str) -> tuple[Path, bytes]:
    raw_path, expected_hash, expected_size = _binding_fields(binding, label=label)
    path = _resolve_root_file(root, Path(raw_path), label=label)
    contents = _read_regular_file_bytes(path)
    if hashlib.sha256(contents).hexdigest() != expected_hash:
        raise ValueError(f"{label} binding SHA-256 mismatch")
    if expected_size is not None and len(contents) != expected_size:
        raise ValueError(f"{label} binding size mismatch")
    return path, contents


def _read_regular_file_bytes(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError(f"R5 refuses symlinked input: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"R5 input is not a regular file: {path}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    contents = b"".join(chunks)
    if identity_before != identity_after or len(contents) != before.st_size:
        raise ValueError(f"R5 input changed while being read: {path}")
    return contents


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(_read_regular_file_bytes(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid R5 {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"R5 {label} must be an object")
    return payload


def _read_json_verified(path: Path, expected: str, *, label: str) -> dict[str, Any]:
    if _sha256_file(path) != expected:
        raise ValueError(f"R5 {label} differs from preregistration lock")
    return _read_json(path, label=label)


def _load_strategy_spec(path: Path) -> StrategySpec:
    try:
        raw = safe_load_yaml(_read_regular_file_bytes(path).decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"invalid R5 StrategySpec: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("R5 StrategySpec must be a mapping")
    return StrategySpec.model_validate(raw)


def _read_jsonl(root: Path, path: Path) -> list[dict[str, Any]]:
    try:
        contents = _read_output_file_bytes(root, path)
    except FileNotFoundError:
        return []
    try:
        rows = [json.loads(line) for line in contents.decode("utf-8").splitlines() if line]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid R5 forward ledger: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("R5 forward ledger rows must be objects")
    return rows


def _write_immutable_bytes(root: Path, path: Path, contents: bytes) -> None:
    with _open_output_parent(root, path, create=True) as (parent_fd, name):
        try:
            existing, metadata = _read_regular_at(parent_fd, name)
        except FileNotFoundError:
            pass
        else:
            if existing != contents or metadata.st_mode & 0o222:
                raise ValueError(f"immutable R5 forward evidence differs: {path}")
            return
        temporary_name, temporary_fd = _create_temporary_file(parent_fd, name, mode=0o600)
        try:
            try:
                _write_descriptor(temporary_fd, contents, mode=0o400)
            finally:
                os.close(temporary_fd)
            try:
                os.link(
                    temporary_name,
                    name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                existing, metadata = _read_regular_at(parent_fd, name)
                if existing != contents or metadata.st_mode & 0o222:
                    raise ValueError(f"immutable R5 forward evidence differs: {path}") from None
            os.fsync(parent_fd)
        finally:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


def _write_json_atomic(root: Path, path: Path, payload: dict[str, Any]) -> None:
    contents = _canonical_json_bytes(payload) + b"\n"
    _write_bytes_atomic(root, path, contents, mode=0o600)


def _write_bytes_atomic(root: Path, path: Path, contents: bytes, *, mode: int) -> None:
    with _open_output_parent(root, path, create=True) as (parent_fd, name):
        temporary_name, temporary_fd = _create_temporary_file(parent_fd, name, mode=0o600)
        try:
            try:
                _write_descriptor(temporary_fd, contents, mode=mode)
            finally:
                os.close(temporary_fd)
            os.replace(
                temporary_name,
                name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.fsync(parent_fd)
        finally:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


def _write_descriptor(descriptor: int, contents: bytes, *, mode: int) -> None:
    view = memoryview(contents)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise OSError("short write while publishing R5 evidence")
        offset += written
    os.fsync(descriptor)
    os.fchmod(descriptor, mode)


def _create_temporary_file(parent_fd: int, name: str, *, mode: int) -> tuple[str, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _attempt in range(100):
        temporary_name = f".{name}.{secrets.token_hex(12)}.tmp"
        try:
            descriptor = os.open(temporary_name, flags, mode, dir_fd=parent_fd)
        except FileExistsError:
            continue
        return temporary_name, descriptor
    raise OSError("unable to allocate an R5 publication temporary file")


def _read_regular_at(parent_fd: int, name: str) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"R5 output is not a regular file: {name}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError(f"R5 output changed while being read: {name}")
    contents = b"".join(chunks)
    if len(contents) != before.st_size:
        raise ValueError(f"R5 output changed while being read: {name}")
    return contents, before


def _relative_output_path(root: Path, path: Path) -> Path:
    base = Path(os.path.abspath(os.fspath(root)))
    candidate = Path(os.path.abspath(os.fspath(path if path.is_absolute() else base / path)))
    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"R5 output path escapes the repository: {path}") from exc
    if relative == Path(".") or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"R5 output path is unsafe: {path}")
    return relative


@contextmanager
def _open_output_directory(root: Path, path: Path, *, create: bool):
    relative = _relative_output_path(root, path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow
    descriptor = os.open(root, flags)
    try:
        for component in relative.parts:
            try:
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                os.fsync(descriptor)
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
            except OSError as exc:
                raise ValueError(f"R5 output has a symlinked or invalid ancestor: {path}") from exc
            os.close(descriptor)
            descriptor = next_descriptor
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _open_output_parent(root: Path, path: Path, *, create: bool):
    relative = _relative_output_path(root, path)
    name = relative.name
    parent = root / relative.parent
    with _open_output_directory(root, parent, create=create) as descriptor:
        yield descriptor, name


def _read_output_file_bytes(root: Path, path: Path) -> bytes:
    with _open_output_parent(root, path, create=False) as (parent_fd, name):
        contents, _metadata = _read_regular_at(parent_fd, name)
    return contents


def _list_output_directory(root: Path, path: Path, *, missing_ok: bool) -> list[str]:
    try:
        with _open_output_directory(root, path, create=False) as descriptor:
            return sorted(os.listdir(descriptor))
    except FileNotFoundError:
        if missing_ok:
            return []
        raise


def _ensure_output_directory(root: Path, path: Path) -> None:
    with _open_output_directory(root, path, create=True):
        return


def _output_directory_exists(root: Path, path: Path) -> bool:
    try:
        with _open_output_directory(root, path, create=False):
            return True
    except FileNotFoundError:
        return False


def _make_output_temp_directory(
    root: Path,
    parent: Path,
    *,
    prefix: str,
    suffix: str = "",
) -> Path:
    with _open_output_directory(root, parent, create=True) as descriptor:
        for _attempt in range(100):
            name = f"{prefix}{secrets.token_hex(12)}{suffix}"
            try:
                os.mkdir(name, 0o700, dir_fd=descriptor)
            except FileExistsError:
                continue
            os.fsync(descriptor)
            return parent / name
    raise OSError("unable to allocate an R5 publication staging directory")


def _rename_output_directory_atomic(root: Path, source: Path, destination: Path) -> None:
    source_relative = _relative_output_path(root, source)
    destination_relative = _relative_output_path(root, destination)
    if source_relative.parent != destination_relative.parent:
        raise ValueError("R5 evidence publication must remain within one parent directory")
    parent = root / source_relative.parent
    with _open_output_directory(root, parent, create=False) as descriptor:
        try:
            os.rename(
                source_relative.name,
                destination_relative.name,
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
            )
        except OSError as exc:
            if exc.errno in {getattr(os, "EEXIST", 17), getattr(os, "ENOTEMPTY", 39)}:
                raise FileExistsError(destination) from exc
            raise
        os.fsync(descriptor)


def _rename_directory_atomic(source: Path, destination: Path) -> None:
    root = _forward_output_root(source)
    if _forward_output_root(destination) != root:
        raise ValueError("R5 evidence rename crosses repository roots")
    _rename_output_directory_atomic(root, source, destination)


def _remove_output_tree(root: Path, path: Path, *, missing_ok: bool) -> None:
    try:
        with _open_output_parent(root, path, create=False) as (parent_fd, name):
            _remove_tree_at(parent_fd, name)
            os.fsync(parent_fd)
    except FileNotFoundError:
        if not missing_ok:
            raise


def _remove_tree_at(parent_fd: int, name: str) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        for child in os.listdir(descriptor):
            metadata = os.stat(child, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                _remove_tree_at(descriptor, child)
            else:
                os.unlink(child, dir_fd=descriptor)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.rmdir(name, dir_fd=parent_fd)


def _fsync_output_directory(root: Path, path: Path) -> None:
    with _open_output_directory(root, path, create=False) as descriptor:
        os.fsync(descriptor)


def _valid_weights(weights: Any, spec: StrategySpec) -> bool:
    if not isinstance(weights, dict) or set(weights) != set(spec.universe):
        return False
    values: list[float] = []
    for symbol, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        number = float(value)
        if not math.isfinite(number) or number < -1e-12:
            return False
        if symbol != RESERVE_SYMBOL and number > 0.34 + 1e-12:
            return False
        values.append(number)
    return abs(sum(values) - 1.0) <= 1e-9


def _target_hash(weights: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(weights)).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _expected_sessions(start: date, *, count: int) -> list[date]:
    sessions: list[date] = []
    current = start
    while len(sessions) < count:
        if us_equity_session_close(current) is not None:
            sessions.append(current)
        current += timedelta(days=1)
    return sessions


def _manifest_retrieved_at(manifest: dict[str, Any]) -> datetime:
    try:
        return _as_utc(datetime.fromisoformat(str(manifest["retrieved_at"]).replace("Z", "+00:00")))
    except (KeyError, ValueError) as exc:
        raise ValueError("R5 snapshot manifest retrieved_at is invalid") from exc


def _manifest_latest_complete_session(manifest: dict[str, Any]) -> date:
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != len(RANKABLE_SYMBOLS) + 1:
        raise ValueError("R5 snapshot manifest must contain exactly 14 items")
    latest: set[str] = set()
    for item in items:
        quality = item.get("quality") if isinstance(item, dict) else None
        sessions = quality.get("complete_sessions") if isinstance(quality, dict) else None
        if not isinstance(sessions, list) or not sessions:
            raise ValueError("R5 snapshot complete-session evidence is missing")
        latest.add(str(sessions[-1]))
    if len(latest) != 1:
        raise ValueError("R5 snapshot symbols end on different sessions")
    return date.fromisoformat(latest.pop())


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
        raise ValueError(f"R5 market session is not a trading day: {session.isoformat()}")
    return datetime.combine(session, close, tzinfo=NEW_YORK).astimezone(UTC)


def _snapshot_observation_window_valid(
    *,
    retrieved_at: datetime,
    session_close: datetime,
    observed_at: datetime,
) -> bool:
    return session_close + MIN_SNAPSHOT_AFTER_CLOSE_LAG <= retrieved_at <= observed_at


def _epoch_date(value: Any) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError("R5 forward epoch is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(NEW_YORK).date() if parsed.tzinfo else parsed.date()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("R5 forward timestamps must include timezone")
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        _json_ready(payload),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(_read_regular_file_bytes(path)).hexdigest()


def _relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _forward_dir(root: Path, strategy_name: str) -> Path:
    return root / "reports" / "forward" / strategy_name
