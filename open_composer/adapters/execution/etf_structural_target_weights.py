from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.adapters.data.alpaca_snapshot import verify_alpaca_contract_snapshot
from open_composer.adapters.execution.router_target_weights import (
    write_router_execution_artifacts,
)
from open_composer.market_calendar import NEW_YORK, us_equity_session_close
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.etf_structural_r9 import compute_monthly_targets
from open_composer.storage import append_jsonl, write_json
from open_composer.strategy_versions import strategy_content_hash

FORWARD_SESSION_TARGET = 20
MAX_OBSERVATION_CLOCK_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class ETFStructuralTargetWeightResult:
    report_path: Path
    target_weights_path: Path
    rebalance_intents_path: Path
    observation_path: Path
    forward_ledger_path: Path
    forward_readiness_path: Path
    parity_status: str
    rebalance_sessions: int
    target_weight_count: int
    nonzero_target_rows: int


@dataclass(frozen=True)
class ForwardPreregistrationBinding:
    lock_path: Path
    lock_sha256: str
    implementation_bindings: list[dict[str, str]]


def run_etf_structural_target_weight_mapping(
    spec_path: Path,
    root: Path,
    *,
    snapshot_manifest_path: Path | None = None,
    as_of: datetime | None = None,
) -> ETFStructuralTargetWeightResult:
    base = root.resolve()
    resolved_spec_path = _resolve_root_file(base, spec_path, label="StrategySpec")
    spec = load_strategy_spec(resolved_spec_path)
    _require_observation_only_spec(spec)
    current_time = _utc_now()
    observed_at = _as_utc(as_of or current_time)
    if observed_at > current_time:
        raise ValueError("ETF structural observation as_of cannot be in the future")
    if current_time - observed_at > MAX_OBSERVATION_CLOCK_SKEW:
        raise ValueError("ETF structural observations cannot be backfilled")
    preregistration = _require_preregistration_binding(
        root=base,
        spec_path=resolved_spec_path,
        spec=spec,
        observed_at=observed_at,
    )
    manifest_path = _resolve_manifest_path(spec, root, snapshot_manifest_path)
    manifest = verify_alpaca_contract_snapshot(root, manifest_path)
    snapshot_retrieved_at = _manifest_retrieved_at(manifest)
    closes = _load_daily_close_panel(manifest_path, spec)
    expected_session = _latest_completed_session(observed_at)
    latest_session = closes.index.max().date()
    blockers = []
    if latest_session != expected_session:
        blockers.append(
            f"latest_complete_session={latest_session.isoformat()} "
            f"expected={expected_session.isoformat()}"
        )
    if snapshot_retrieved_at > observed_at:
        blockers.append(
            "snapshot_retrieved_at="
            f"{snapshot_retrieved_at.isoformat()} after observed_at={observed_at.isoformat()}"
        )

    targets, raw_records = compute_monthly_targets(closes, spec)
    design = spec.research_design.model_dump(mode="json") if spec.research_design else {}
    iter_id = str(design.get("iter_id") or "")
    records = [
        {
            **record,
            "iter_id": iter_id,
            "candidate_id": spec.portfolio.etf_structural.candidate_id,
        }
        for record in raw_records
    ]
    spec_hash = strategy_content_hash(spec)
    manifest_hash = _sha256_file(manifest_path)
    target_rows, intents = _execution_rows(
        spec,
        targets,
        records,
        spec_hash=spec_hash,
        manifest_hash=manifest_hash,
    )
    position_reconciliation = _position_reconciliation(root, spec, target_rows)
    parity = {
        "status": "blocked" if blockers else "ok",
        "blockers": blockers,
        "warnings": [
            "observation_only_no_broker_writes",
            "monthly targets use the frozen R9 reference implementation until generic "
            "parity is independently locked",
        ],
        "target_rows_match_monthly_reference": True,
        "latest_complete_session": latest_session.isoformat(),
        "expected_complete_session": expected_session.isoformat(),
    }
    artifacts = write_router_execution_artifacts(
        root=base,
        spec_path=resolved_spec_path,
        spec=spec,
        target_rows=target_rows,
        rebalance_intents=intents,
        data_profile={
            "source_mode": "immutable_alpaca_contract_snapshot",
            "provider": manifest.get("provider"),
            "feed": "sip",
            "adjustment": "all",
            "snapshot_manifest_path": _relpath(manifest_path, root),
            "snapshot_manifest_sha256": manifest_hash,
            "snapshot_retrieved_at": manifest.get("retrieved_at"),
            "latest_complete_session": latest_session.isoformat(),
            "position_reconciliation": position_reconciliation,
        },
        route_label=spec.portfolio.etf_structural.candidate_id,
        mapping_summary={
            "candidate_id": spec.portfolio.etf_structural.candidate_id,
            "spec_hash": spec_hash,
            "paper_order_authorization": False,
            "broker_writes": False,
            "position_reconciliation": position_reconciliation,
        },
        acquisition_tier="research_strict",
        parity_check=parity,
        target_backend="python_reference_observation",
        generated_at=observed_at,
    )
    epoch = _epoch_date(spec.notes.model_dump(mode="json"))
    countable_session = (
        not blockers and latest_session >= epoch and latest_session == expected_session
    )
    evidence_bindings = (
        _freeze_forward_evidence(
            root=base,
            spec=spec,
            market_session=latest_session,
            sources={
                "target_weights": artifacts["router_target_weights"],
                "rebalance_intents": artifacts["router_rebalance_intents"],
                "execution_observation": artifacts["router_execution_observation"],
                "preregistration_lock": preregistration.lock_path,
                "strategy_spec": resolved_spec_path,
            },
            position_reconciliation=position_reconciliation,
        )
        if countable_session
        else {}
    )
    forward_ledger = _append_forward_decision(
        root=base,
        spec=spec,
        target_rows=target_rows,
        observed_at=observed_at,
        latest_session=latest_session,
        expected_session=expected_session,
        spec_hash=spec_hash,
        manifest_path=manifest_path,
        manifest_hash=manifest_hash,
        blockers=blockers,
        preregistration=preregistration,
        evidence_bindings=evidence_bindings,
    )
    readiness_path, readiness = _write_forward_readiness(
        base,
        spec,
        forward_ledger,
        spec_hash=spec_hash,
        as_of=observed_at,
        preregistration=preregistration,
    )
    report_path = base / "reports" / "forward" / spec.name / "latest-observation.json"
    report = {
        "schema_version": 1,
        "report_type": "etf_structural_forward_observation",
        "strategy_name": spec.name,
        "iter_id": iter_id,
        "candidate_id": spec.portfolio.etf_structural.candidate_id,
        "generated_at": observed_at.isoformat(),
        "spec_hash": spec_hash,
        "snapshot_manifest_path": _relpath(manifest_path, base),
        "snapshot_manifest_sha256": manifest_hash,
        "preregistration_lock_path": _relpath(preregistration.lock_path, base),
        "preregistration_lock_sha256": preregistration.lock_sha256,
        "implementation_bindings": preregistration.implementation_bindings,
        "parity": parity,
        "position_reconciliation": position_reconciliation,
        "forward_readiness": readiness,
        "artifacts": {key: _relpath(value, base) for key, value in artifacts.items()},
        "evidence_bindings": evidence_bindings,
        "forward_ledger_path": _relpath(forward_ledger, base),
        "forward_readiness_path": _relpath(readiness_path, base),
        "workflow_pass": not blockers and bool(readiness["workflow_pass"]),
        "research_pass": False,
        "paper_ready_pass": False,
        "paper_order_authorization": False,
        "broker_writes": False,
    }
    write_json(report_path, report)
    summary = json.loads(artifacts["router_target_weights"].read_text(encoding="utf-8"))["summary"]
    return ETFStructuralTargetWeightResult(
        report_path=report_path,
        target_weights_path=artifacts["router_target_weights"],
        rebalance_intents_path=artifacts["router_rebalance_intents"],
        observation_path=artifacts["router_execution_observation"],
        forward_ledger_path=forward_ledger,
        forward_readiness_path=readiness_path,
        parity_status=str(parity["status"]),
        rebalance_sessions=int(summary["rebalance_sessions"]),
        target_weight_count=int(summary["target_weight_rows"]),
        nonzero_target_rows=int(summary["nonzero_target_rows"]),
    )


def _require_observation_only_spec(spec: StrategySpec) -> None:
    if spec.portfolio.mode != "etf_structural_family":
        raise ValueError("ETF structural mapping requires portfolio.mode=etf_structural_family")
    if spec.portfolio.etf_structural is None:
        raise ValueError("ETF structural mapping requires portfolio.etf_structural")
    if spec.lifecycle != "draft" or spec.execution.mode != "manual_signal":
        raise ValueError("ETF structural mapping requires draft manual_signal lifecycle")
    if spec.execution.broker != "none":
        raise ValueError("ETF structural mapping forbids broker access")


def _resolve_root_file(root: Path, path: Path, *, label: str) -> Path:
    base = root.resolve()
    candidate = path if path.is_absolute() else base / path
    try:
        lexical = Path(os.path.abspath(candidate))
        relative = lexical.relative_to(base)
        current = base
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise ValueError(f"{label} cannot use symlinks")
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(base)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} must be a regular file inside the project root") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    return resolved


def _require_preregistration_binding(
    *,
    root: Path,
    spec_path: Path,
    spec: StrategySpec,
    observed_at: datetime,
) -> ForwardPreregistrationBinding:
    design = spec.research_design
    if design is None or not design.preregistration_lock_path:
        raise ValueError("ETF structural observation requires a preregistration lock")
    lock_path = _resolve_root_file(
        root,
        Path(design.preregistration_lock_path),
        label="preregistration lock",
    )
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("preregistration lock is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("preregistration lock schema_version must be 1")
    if payload.get("iter_id") != design.iter_id:
        raise ValueError("preregistration lock iter_id does not match the StrategySpec")
    try:
        created_at = _as_utc(
            datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
        )
    except (KeyError, ValueError) as exc:
        raise ValueError("preregistration lock created_at is invalid") from exc
    if created_at > observed_at:
        raise ValueError("preregistration lock was created after the observation timestamp")

    spec_binding = payload.get("spec")
    if not isinstance(spec_binding, dict):
        raise ValueError("preregistration lock spec binding is missing")
    bound_spec = _verify_locked_file(root, spec_binding, label="locked StrategySpec")
    if bound_spec != spec_path:
        raise ValueError("preregistration lock points to a different StrategySpec")
    if spec_binding.get("semantic_sha256") != strategy_content_hash(spec):
        raise ValueError("preregistration lock StrategySpec semantic hash mismatch")

    contracts = payload.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise ValueError("preregistration lock contracts are missing")
    for index, binding in enumerate(contracts):
        _verify_locked_file(root, binding, label=f"locked contract {index + 1}")

    baseline = payload.get("baseline_data")
    if not isinstance(baseline, dict):
        raise ValueError("preregistration lock baseline data binding is missing")
    _verify_locked_file(root, baseline, label="locked baseline data")

    implementation = payload.get("implementation")
    if not isinstance(implementation, list) or not implementation:
        raise ValueError("preregistration lock implementation bindings are missing")
    normalized_implementation: list[dict[str, str]] = []
    paths: set[str] = set()
    for index, binding in enumerate(implementation):
        locked_path = _verify_locked_file(
            root,
            binding,
            label=f"locked implementation {index + 1}",
        )
        relative = locked_path.relative_to(root).as_posix()
        if relative in paths:
            raise ValueError("preregistration lock contains duplicate implementation paths")
        paths.add(relative)
        normalized_implementation.append({"path": relative, "sha256": str(binding["sha256"])})
    required_adapter = "open_composer/adapters/execution/etf_structural_target_weights.py"
    if required_adapter not in paths:
        raise ValueError("preregistration lock does not bind the target-weight adapter")
    return ForwardPreregistrationBinding(
        lock_path=lock_path,
        lock_sha256=_sha256_file(lock_path),
        implementation_bindings=normalized_implementation,
    )


def _verify_locked_file(root: Path, binding: Any, *, label: str) -> Path:
    if not isinstance(binding, dict):
        raise ValueError(f"{label} binding is invalid")
    raw_path = binding.get("path")
    expected_hash = binding.get("sha256") or binding.get("file_sha256")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError(f"{label} path is missing")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError(f"{label} sha256 is invalid")
    path = _resolve_root_file(root, Path(raw_path), label=label)
    if _sha256_file(path) != expected_hash:
        raise ValueError(f"{label} sha256 mismatch")
    return path


def _freeze_forward_evidence(
    *,
    root: Path,
    spec: StrategySpec,
    market_session: date,
    sources: dict[str, Path],
    position_reconciliation: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    evidence_dir = (
        root / "reports" / "forward" / spec.name / "evidence" / market_session.isoformat()
    )
    payloads: dict[str, tuple[str, bytes]] = {}
    for role, source in sources.items():
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"forward evidence source {role} is not a regular file")
        suffix = source.suffix if source.suffix in {".json", ".yaml", ".yml"} else ".bin"
        payloads[role] = (f"{role}{suffix}", source.read_bytes())
    payloads["position_reconciliation"] = (
        "position_reconciliation.json",
        _canonical_json_bytes(position_reconciliation),
    )
    bindings: dict[str, dict[str, Any]] = {}
    for role, (filename, contents) in sorted(payloads.items()):
        destination = evidence_dir / filename
        _write_immutable_bytes(destination, contents)
        bindings[role] = {
            "path": _relpath(destination, root),
            "sha256": hashlib.sha256(contents).hexdigest(),
            "size_bytes": len(contents),
        }
    return bindings


def _resolve_manifest_path(
    spec: StrategySpec,
    root: Path,
    override: Path | None,
) -> Path:
    if override is not None:
        path = override if override.is_absolute() else root / override
    else:
        raw = spec.data_assumptions.snapshot_manifest_path
        if not raw:
            raise ValueError("ETF structural observation requires snapshot_manifest_path")
        path = root / raw
    resolved = path.resolve(strict=True)
    resolved.relative_to(root.resolve())
    return resolved


def _load_daily_close_panel(manifest_path: Path, spec: StrategySpec) -> pd.DataFrame:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise AlpacaDataError("snapshot manifest items are missing")
    expected_symbols = set(spec.universe)
    actual_symbols = {str(item.get("symbol") or "") for item in items if isinstance(item, dict)}
    if actual_symbols != expected_symbols:
        raise AlpacaDataError("snapshot symbols do not match the StrategySpec universe")
    closes: dict[str, pd.Series] = {}
    complete_sessions: list[str] | None = None
    for item in items:
        if (
            not isinstance(item, dict)
            or item.get("timeframe") != "daily"
            or item.get("feed") != "sip"
            or item.get("adjustment") != "all"
        ):
            raise AlpacaDataError("ETF structural snapshot identity mismatch")
        quality = item.get("quality")
        sessions = quality.get("complete_sessions") if isinstance(quality, dict) else None
        if not isinstance(sessions, list) or not sessions:
            raise AlpacaDataError("ETF structural complete-session list is missing")
        if complete_sessions is None:
            complete_sessions = list(map(str, sessions))
        elif list(map(str, sessions)) != complete_sessions:
            raise AlpacaDataError("ETF structural complete-session lists differ")
        frame = pd.read_csv(manifest_path.parent / str(item["output_path"]))
        parsed = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        index = pd.DatetimeIndex(parsed.dt.tz_convert(NEW_YORK).dt.date)
        if index.has_duplicates or not index.is_monotonic_increasing:
            raise AlpacaDataError(f"invalid daily sessions for {item['symbol']}")
        closes[str(item["symbol"])] = pd.Series(
            pd.to_numeric(frame["close"], errors="raise").to_numpy(),
            index=index,
        )
    panel = pd.DataFrame(closes).reindex(columns=sorted(expected_symbols))
    values = panel.to_numpy(dtype=float)
    if (
        panel.empty
        or np.isnan(values).any()
        or not np.isfinite(values).all()
        or (values <= 0).any()
    ):
        raise AlpacaDataError("ETF structural close panel must be strict, finite, and positive")
    return panel


def _execution_rows(
    spec: StrategySpec,
    targets: pd.DataFrame,
    records: list[dict[str, Any]],
    *,
    spec_hash: str,
    manifest_hash: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    record_by_session = {str(row["execution_session"]): row for row in records}
    target_rows: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    previous = {symbol: 0.0 for symbol in targets.columns}
    for session, weights in targets.iterrows():
        session_text = session.date().isoformat()
        record = record_by_session[session_text]
        rebalance_id = f"{spec.name}:{session_text}:{record['target_sha256'][:16]}"
        for symbol in targets.columns:
            target = float(weights[symbol])
            prior = float(previous[symbol])
            delta = target - prior
            target_rows.append(
                {
                    "rebalance_id": rebalance_id,
                    "rebalance_session": session_text,
                    "signal_session": record["decision_session"],
                    "time_rule": "next_regular_session_open",
                    "symbol": symbol,
                    "target_weight": target,
                    "selected": target > 1e-12,
                    "candidate_id": record["candidate_id"],
                    "target_sha256": record["target_sha256"],
                    "spec_hash": spec_hash,
                    "snapshot_manifest_sha256": manifest_hash,
                }
            )
            if abs(delta) > 1e-12:
                intents.append(
                    {
                        "rebalance_id": rebalance_id,
                        "rebalance_session": session_text,
                        "time_rule": "next_regular_session_open",
                        "symbol": symbol,
                        "from_weight": prior,
                        "to_weight": target,
                        "delta_weight": delta,
                        "side": "buy" if delta > 0 else "sell",
                        "intent_type": "observation_set_target_weight",
                        "requires_order": True,
                        "paper_order_authorization": False,
                        "broker_writes": False,
                    }
                )
            previous[symbol] = target
    return target_rows, intents


def _position_reconciliation(
    root: Path,
    spec: StrategySpec,
    target_rows: list[dict[str, object]],
) -> dict[str, Any]:
    account_path = root / "reports" / "paper" / "account.json"
    positions_path = root / "reports" / "paper" / "positions.json"
    if not account_path.is_file() or not positions_path.is_file():
        return {"status": "unavailable", "reason": "paper_account_or_positions_missing"}
    try:
        account = json.loads(account_path.read_text(encoding="utf-8"))
        positions_payload = json.loads(positions_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "blocked", "reason": "paper_position_evidence_invalid_json"}
    if account.get("paper") is not True or positions_payload.get("paper") is not True:
        return {"status": "blocked", "reason": "position_evidence_not_paper"}
    denominator = float(account.get("portfolio_value") or account.get("equity") or 0.0)
    if not math.isfinite(denominator) or denominator <= 0:
        return {"status": "blocked", "reason": "paper_equity_invalid"}
    sessions = sorted({str(row["rebalance_session"]) for row in target_rows})
    latest = sessions[-1]
    expected = {
        str(row["symbol"]): float(row["target_weight"])
        for row in target_rows
        if row["rebalance_session"] == latest
    }
    actual = {
        str(row.get("symbol") or "").upper(): abs(float(row.get("market_value") or 0.0))
        / denominator
        for row in positions_payload.get("positions", [])
        if str(row.get("symbol") or "").upper() in spec.universe
    }
    differences = {
        symbol: actual.get(symbol, 0.0) - expected.get(symbol, 0.0)
        for symbol in sorted(set(expected) | set(actual))
    }
    return {
        "status": "observation_only",
        "latest_target_session": latest,
        "expected_weights": expected,
        "actual_paper_weights": actual,
        "weight_differences": differences,
        "orders_generated": False,
    }


def _append_forward_decision(
    *,
    root: Path,
    spec: StrategySpec,
    target_rows: list[dict[str, object]],
    observed_at: datetime,
    latest_session: date,
    expected_session: date,
    spec_hash: str,
    manifest_path: Path,
    manifest_hash: str,
    blockers: list[str],
    preregistration: ForwardPreregistrationBinding,
    evidence_bindings: dict[str, dict[str, Any]],
) -> Path:
    path = root / "reports" / "forward" / spec.name / "decisions.jsonl"
    notes = spec.notes.model_dump(mode="json")
    epoch = _epoch_date(notes)
    if blockers or latest_session < epoch or latest_session != expected_session:
        return path
    latest_target_session = max(str(row["rebalance_session"]) for row in target_rows)
    weights = {
        str(row["symbol"]): float(row["target_weight"])
        for row in target_rows
        if row["rebalance_session"] == latest_target_session
    }
    target_hash = hashlib.sha256(
        json.dumps(weights, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    row = {
        "schema_version": 1,
        "evidence_class": "forward_observation",
        "strategy_name": spec.name,
        "candidate_id": spec.portfolio.etf_structural.candidate_id,
        "spec_hash": spec_hash,
        "market_session": latest_session.isoformat(),
        "observed_at": observed_at.isoformat(),
        "snapshot_manifest_path": _relpath(manifest_path, root),
        "snapshot_manifest_sha256": manifest_hash,
        "preregistration_lock_path": _relpath(preregistration.lock_path, root),
        "preregistration_lock_sha256": preregistration.lock_sha256,
        "implementation_bindings": preregistration.implementation_bindings,
        "latest_target_session": latest_target_session,
        "target_sha256": target_hash,
        "weights": weights,
        "evidence_bindings": evidence_bindings,
        "paper_order_authorization": False,
        "broker_writes": False,
    }
    existing = _read_jsonl(path)
    key = (spec_hash, row["market_session"])
    for prior in existing:
        if (prior.get("spec_hash"), prior.get("market_session")) != key:
            continue
        comparable = {
            k: v for k, v in prior.items() if k not in {"observed_at", "forward_decision_receipt"}
        }
        current = {k: v for k, v in row.items() if k != "observed_at"}
        if comparable != current:
            raise ValueError("forward decision already exists with different bound contents")
        return path
    receipt_path = path.parent / "receipts" / f"{latest_session.isoformat()}.json"
    receipt_bytes = _canonical_json_bytes(row)
    _write_immutable_bytes(receipt_path, receipt_bytes)
    row["forward_decision_receipt"] = {
        "path": _relpath(receipt_path, root),
        "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "size_bytes": len(receipt_bytes),
    }
    append_jsonl(path, [row])
    return path


def _write_forward_readiness(
    root: Path,
    spec: StrategySpec,
    ledger_path: Path,
    *,
    spec_hash: str,
    as_of: datetime,
    preregistration: ForwardPreregistrationBinding,
) -> tuple[Path, dict[str, Any]]:
    rows = _read_jsonl(ledger_path)
    valid = []
    excluded = []
    seen: set[str] = set()
    verified_manifests: dict[Path, dict[str, Any] | None] = {}
    epoch = _epoch_date(spec.notes.model_dump(mode="json"))
    for index, row in enumerate(rows, start=1):
        reasons = []
        session_text = str(row.get("market_session") or "")
        try:
            session = date.fromisoformat(session_text)
            observed = _as_utc(datetime.fromisoformat(str(row["observed_at"])))
        except (KeyError, ValueError):
            reasons.append("identity_or_timestamp_invalid")
            session = None
            observed = None
        if row.get("spec_hash") != spec_hash:
            reasons.append("spec_hash_mismatch")
        if row.get("strategy_name") != spec.name:
            reasons.append("strategy_name_mismatch")
        if row.get("candidate_id") != spec.portfolio.etf_structural.candidate_id:
            reasons.append("candidate_id_mismatch")
        if row.get("preregistration_lock_sha256") != preregistration.lock_sha256:
            reasons.append("preregistration_lock_mismatch")
        if row.get("implementation_bindings") != preregistration.implementation_bindings:
            reasons.append("implementation_bindings_mismatch")
        if session is not None and session < epoch:
            reasons.append("before_forward_epoch")
        if session is not None and us_equity_session_close(session) is None:
            reasons.append("not_us_equity_session")
        if session_text in seen:
            reasons.append("duplicate_market_session")
        seen.add(session_text)
        if observed is not None and observed > as_of:
            reasons.append("future_observation")
        if session is not None and observed is not None:
            if _latest_completed_session(observed) != session:
                reasons.append("observation_session_mismatch")
        if (
            row.get("paper_order_authorization") is not False
            or row.get("broker_writes") is not False
        ):
            reasons.append("observation_safety_flag_invalid")
        try:
            manifest_path = (root / str(row.get("snapshot_manifest_path") or "")).resolve()
            manifest_path.relative_to(root.resolve())
        except (OSError, ValueError):
            manifest_path = None
        if (
            manifest_path is None
            or not manifest_path.is_file()
            or _sha256_file(manifest_path) != row.get("snapshot_manifest_sha256")
        ):
            reasons.append("snapshot_manifest_binding_invalid")
        elif manifest_path is not None:
            if manifest_path not in verified_manifests:
                try:
                    verified_manifests[manifest_path] = verify_alpaca_contract_snapshot(
                        root,
                        manifest_path,
                    )
                except (OSError, ValueError, AlpacaDataError):
                    verified_manifests[manifest_path] = None
            manifest = verified_manifests[manifest_path]
            if manifest is None:
                reasons.append("snapshot_bundle_invalid")
            else:
                try:
                    retrieved_at = _manifest_retrieved_at(manifest)
                    manifest_session = _manifest_latest_complete_session(manifest)
                except ValueError:
                    reasons.append("snapshot_timing_invalid")
                else:
                    if observed is not None and retrieved_at > observed:
                        reasons.append("snapshot_retrieved_after_observation")
                    if session is not None and manifest_session != session:
                        reasons.append("snapshot_session_mismatch")
        weights = row.get("weights")
        if not _valid_bound_weights(weights, spec):
            reasons.append("target_weights_invalid")
        elif _target_hash(weights) != row.get("target_sha256"):
            reasons.append("target_hash_mismatch")
        try:
            latest_target_session = date.fromisoformat(str(row.get("latest_target_session") or ""))
        except ValueError:
            reasons.append("latest_target_session_invalid")
        else:
            if session is not None and latest_target_session > session:
                reasons.append("latest_target_session_after_market_session")
        reasons.extend(
            _validate_frozen_evidence(
                root=root,
                spec=spec,
                row=row,
                expected_spec_hash=spec_hash,
            )
        )
        reasons.extend(_validate_forward_receipt(root=root, row=row))
        if reasons:
            excluded.append({"line": index, "market_session": session_text, "reasons": reasons})
        else:
            valid.append(row)
    valid_by_session = {str(row["market_session"]): row for row in valid}
    expected_sessions = _expected_sessions(epoch, _latest_completed_session(as_of))
    missing_sessions = [
        session.isoformat()
        for session in expected_sessions
        if session.isoformat() not in valid_by_session
    ]
    contiguous_valid = []
    for session in expected_sessions:
        row = valid_by_session.get(session.isoformat())
        if row is None:
            break
        contiguous_valid.append(row)
    passed = len(contiguous_valid) >= FORWARD_SESSION_TARGET
    payload = {
        "schema_version": 1,
        "report_type": "etf_structural_forward_readiness",
        "strategy_name": spec.name,
        "generated_at": as_of.isoformat(),
        "spec_hash": spec_hash,
        "forward_epoch": epoch.isoformat(),
        "minimum_bound_sessions": FORWARD_SESSION_TARGET,
        "valid_receipt_sessions": len(valid),
        "valid_bound_sessions": len(contiguous_valid),
        "coverage_expected_sessions": len(expected_sessions),
        "coverage_missing_sessions": missing_sessions,
        "coverage_contiguous_through": (
            str(contiguous_valid[-1]["market_session"]) if contiguous_valid else None
        ),
        "excluded_session_count": len(excluded),
        "excluded_sessions": excluded,
        "forward_observation_pass": passed,
        "workflow_pass": not excluded and not missing_sessions,
        "research_pass": False,
        "paper_ready_pass": False,
        "matched_paper_tca_required": int(
            spec.notes.model_dump(mode="json").get("minimum_matched_tca_observations", 0)
        ),
        "paper_order_authorization": False,
        "broker_writes": False,
        "preregistration_lock_path": _relpath(preregistration.lock_path, root),
        "preregistration_lock_sha256": preregistration.lock_sha256,
        "implementation_bindings": preregistration.implementation_bindings,
    }
    path = root / "reports" / "forward" / spec.name / "readiness.json"
    write_json(path, payload)
    return path, payload


def _validate_frozen_evidence(
    *,
    root: Path,
    spec: StrategySpec,
    row: dict[str, Any],
    expected_spec_hash: str,
) -> list[str]:
    bindings = row.get("evidence_bindings")
    if not isinstance(bindings, dict):
        return ["evidence_bindings_missing"]
    required_roles = {
        "target_weights",
        "rebalance_intents",
        "execution_observation",
        "position_reconciliation",
        "preregistration_lock",
        "strategy_spec",
    }
    if not required_roles.issubset(bindings):
        return ["evidence_roles_missing"]
    payloads: dict[str, bytes] = {}
    reasons: list[str] = []
    expected_prefix = (
        Path("reports") / "forward" / spec.name / "evidence" / str(row.get("market_session") or "")
    )
    for role in sorted(required_roles):
        try:
            path, contents = _read_bound_file(root, bindings[role], label=role)
            path.relative_to((root / expected_prefix).resolve())
        except (OSError, ValueError):
            reasons.append(f"{role}_binding_invalid")
            continue
        payloads[role] = contents
    if reasons:
        return reasons

    try:
        target_payload = json.loads(payloads["target_weights"])
        target_rows = target_payload["target_weights"]
        summary = target_payload["summary"]
        latest_target = str(row["latest_target_session"])
        frozen_weights = {
            str(item["symbol"]): float(item["target_weight"])
            for item in target_rows
            if str(item["rebalance_session"]) == latest_target
        }
        expected_weights = {str(key): float(value) for key, value in row["weights"].items()}
        if (
            target_payload.get("strategy_name") != spec.name
            or target_payload.get("portfolio_mode") != "etf_structural_family"
            or target_payload.get("target_backend") != "python_reference_observation"
            or summary.get("spec_hash") != expected_spec_hash
            or summary.get("paper_order_authorization") is not False
            or summary.get("broker_writes") is not False
            or frozen_weights != expected_weights
        ):
            reasons.append("target_weights_payload_mismatch")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        reasons.append("target_weights_payload_invalid")

    try:
        intents_payload = json.loads(payloads["rebalance_intents"])
        intents = intents_payload["intents"]
        summary = intents_payload["summary"]
        if (
            intents_payload.get("strategy_name") != spec.name
            or intents_payload.get("portfolio_mode") != "etf_structural_family"
            or intents_payload.get("execution_substate") != "observation_only"
            or summary.get("spec_hash") != expected_spec_hash
            or any(
                item.get("paper_order_authorization") is not False
                or item.get("broker_writes") is not False
                for item in intents
            )
        ):
            reasons.append("rebalance_intents_payload_mismatch")
    except (KeyError, TypeError, json.JSONDecodeError):
        reasons.append("rebalance_intents_payload_invalid")

    try:
        observation = json.loads(payloads["execution_observation"])
        if (
            observation.get("strategy_name") != spec.name
            or observation.get("portfolio_mode") != "etf_structural_family"
            or observation.get("execution_substate") != "observation_only"
            or observation.get("blockers")
        ):
            reasons.append("execution_observation_payload_mismatch")
    except (TypeError, json.JSONDecodeError):
        reasons.append("execution_observation_payload_invalid")

    try:
        reconciliation = json.loads(payloads["position_reconciliation"])
        if (
            not isinstance(reconciliation, dict)
            or reconciliation.get("status") not in {"unavailable", "observation_only"}
            or reconciliation.get("orders_generated") is True
        ):
            reasons.append("position_reconciliation_payload_mismatch")
    except (TypeError, json.JSONDecodeError):
        reasons.append("position_reconciliation_payload_invalid")
    return reasons


def _validate_forward_receipt(*, root: Path, row: dict[str, Any]) -> list[str]:
    binding = row.get("forward_decision_receipt")
    try:
        _, contents = _read_bound_file(root, binding, label="forward decision receipt")
        receipt = json.loads(contents)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return ["forward_decision_receipt_invalid"]
    expected = {key: value for key, value in row.items() if key != "forward_decision_receipt"}
    if receipt != expected:
        return ["forward_decision_receipt_mismatch"]
    return []


def _read_bound_file(
    root: Path,
    binding: Any,
    *,
    label: str,
) -> tuple[Path, bytes]:
    if not isinstance(binding, dict):
        raise ValueError(f"{label} binding is missing")
    raw_path = binding.get("path")
    expected_hash = binding.get("sha256")
    expected_size = binding.get("size_bytes")
    if (
        not isinstance(raw_path, str)
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
        or not isinstance(expected_size, int)
        or expected_size < 0
    ):
        raise ValueError(f"{label} binding fields are invalid")
    path = _resolve_root_file(root, Path(raw_path), label=label)
    contents = path.read_bytes()
    if len(contents) != expected_size or hashlib.sha256(contents).hexdigest() != expected_hash:
        raise ValueError(f"{label} binding does not match the file")
    return path, contents


def _valid_bound_weights(weights: Any, spec: StrategySpec) -> bool:
    if not isinstance(weights, dict) or set(weights) != set(spec.universe):
        return False
    normalized: list[float] = []
    for value in weights.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        number = float(value)
        if not math.isfinite(number) or number < -1e-12:
            return False
        normalized.append(number)
    max_weight = spec.portfolio.max_symbol_weight or spec.risk.max_position_weight
    return (
        all(value <= max_weight + 1e-12 for value in normalized)
        and abs(sum(normalized) - 1.0) <= 1e-9
    )


def _target_hash(weights: Any) -> str:
    return hashlib.sha256(
        json.dumps(weights, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _expected_sessions(start: date, end: date) -> list[date]:
    if end < start:
        return []
    sessions = []
    current = start
    while current <= end:
        if us_equity_session_close(current) is not None:
            sessions.append(current)
        current += timedelta(days=1)
    return sessions


def _canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_immutable_bytes(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.is_symlink() or path.read_bytes() != contents:
            raise ValueError(f"immutable forward evidence differs: {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if not path.is_file() or path.is_symlink() or path.read_bytes() != contents:
                raise ValueError(f"immutable forward evidence differs: {path}") from None
    finally:
        temporary.unlink(missing_ok=True)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _epoch_date(notes: dict[str, Any]) -> date:
    value = notes.get("forward_epoch_utc") or notes.get("paper_validation_start")
    if not value:
        raise ValueError("ETF structural observation requires a forward epoch")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.date()
    return parsed.astimezone(NEW_YORK).date()


def _manifest_retrieved_at(manifest: dict[str, Any]) -> datetime:
    try:
        return _as_utc(datetime.fromisoformat(str(manifest["retrieved_at"]).replace("Z", "+00:00")))
    except (KeyError, ValueError) as exc:
        raise ValueError("snapshot manifest retrieved_at is invalid") from exc


def _manifest_latest_complete_session(manifest: dict[str, Any]) -> date:
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("snapshot manifest items are missing")
    latest: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("snapshot manifest item is invalid")
        quality = item.get("quality")
        sessions = quality.get("complete_sessions") if isinstance(quality, dict) else None
        if not isinstance(sessions, list) or not sessions:
            raise ValueError("snapshot manifest complete sessions are missing")
        latest.add(str(sessions[-1]))
    if len(latest) != 1:
        raise ValueError("snapshot manifest items end on different sessions")
    try:
        return date.fromisoformat(next(iter(latest)))
    except ValueError as exc:
        raise ValueError("snapshot manifest latest session is invalid") from exc


def _latest_completed_session(as_of: datetime) -> date:
    local = as_of.astimezone(NEW_YORK)
    candidate = local.date()
    close = us_equity_session_close(candidate)
    if close is None or local.time() < close:
        candidate -= timedelta(days=1)
    while us_equity_session_close(candidate) is None:
        candidate -= timedelta(days=1)
    return candidate


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("ETF structural observation timestamps must include timezone")
    return value.astimezone(UTC)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path} contains a non-object record")
            rows.append(payload)
    return rows


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
