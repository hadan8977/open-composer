from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from open_composer.config import ensure_dir
from open_composer.execution_policy import (
    ExecutionPolicyBinding,
    require_orderable_execution_policy,
)
from open_composer.models.strategy_spec import StrategySpec
from open_composer.paper_lock import paper_control_lock
from open_composer.router_authorization import is_router_strategy
from open_composer.strategy_versions import strategy_content_hash, strategy_version_id

CANARY_MAX_DURATION_DAYS = 45
CANARY_MAX_ORDER_NOTIONAL = 1_000.0
CANARY_MAX_SESSION_NOTIONAL = 2_500.0
CANARY_MAX_TOTAL_NOTIONAL = 12_000.0
CANARY_MAX_ORDERS_PER_SESSION = 4
CANARY_MAX_TOTAL_ORDERS = 16
FULL_AUTHORIZATION_DISABLED_MESSAGE = (
    "Full paper order authorization is disabled; use explicit bounded canary authorization."
)
CANARY_ALLOWED_ORDER_STYLES = {"opg_limit", "loo_limit"}
CANARY_ALLOWED_TIME_IN_FORCE = {"opg", "day"}
AUTHORIZATION_RECEIPT_VERSION = 2


@dataclass(frozen=True)
class PaperOrderAuthorizationStatus:
    authorized: bool
    message: str
    path: Path
    content_hash: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    kind: Literal["none", "canary", "full"] = "none"


def paper_order_authorization_path(root: Path, spec: StrategySpec) -> Path:
    suffix = "router-order-authorization" if is_router_strategy(spec) else "order-authorization"
    return root / "reports" / "harness" / "paper" / f"{spec.name}-{suffix}.json"


def paper_canary_authorization_path(root: Path, spec: StrategySpec) -> Path:
    return root / "reports" / "harness" / "paper" / f"{spec.name}-canary-order-authorization.json"


def paper_canary_revocation_path(root: Path, spec: StrategySpec) -> Path:
    return root / "reports" / "harness" / "paper" / f"{spec.name}-canary-revocation.json"


def paper_authorization_archive_dir(root: Path, spec: StrategySpec) -> Path:
    return (
        root
        / "reports"
        / "paper"
        / "authorization_history"
        / _safe_strategy_component(spec.name)
        / "authorizations"
    )


def paper_authorization_archive_path(
    root: Path,
    spec: StrategySpec,
    authorization_id: str,
) -> Path:
    """Return the append-only location for one authorization payload."""
    return paper_authorization_archive_dir(root, spec) / (
        f"{_safe_immutable_id(authorization_id, prefix='auth_')}.json"
    )


def paper_canary_revocation_archive_dir(root: Path, spec: StrategySpec) -> Path:
    return (
        root
        / "reports"
        / "paper"
        / "authorization_history"
        / _safe_strategy_component(spec.name)
        / "revocations"
    )


def paper_canary_revocation_archive_path(
    root: Path,
    spec: StrategySpec,
    revocation_id: str,
) -> Path:
    return paper_canary_revocation_archive_dir(root, spec) / (
        f"{_safe_immutable_id(revocation_id, prefix='revoke_')}.json"
    )


def broker_account_id_hash(value: Any) -> str:
    account_id = str(value or "").strip()
    if not account_id:
        raise ValueError("Alpaca Paper account id is missing")
    return hashlib.sha256(account_id.encode("utf-8")).hexdigest()


def assess_paper_order_authorization(
    spec: StrategySpec,
    root: Path,
) -> PaperOrderAuthorizationStatus:
    path = paper_order_authorization_path(root, spec)
    return _status(False, FULL_AUTHORIZATION_DISABLED_MESSAGE, path)


def _assess_legacy_paper_order_authorization(
    spec: StrategySpec,
    root: Path,
) -> PaperOrderAuthorizationStatus:
    """Retained only to validate historical receipts; never grants execution authority."""
    path = paper_order_authorization_path(root, spec)
    if not path.exists():
        return _status(False, "Paper order authorization artifact is missing.", path)
    if path.is_symlink() or not path.is_file():
        return _status(False, "Paper order authorization artifact is not a regular file.", path)
    try:
        payload = _read_json(path)
        policy = require_orderable_execution_policy(spec, root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _status(False, str(exc), path)

    required = {
        "authorization_id",
        "authorization_kind",
        "authorization_receipt_version",
        "authorization_sequence",
        "authorized_at",
        "authorized_by",
        "data_manifest_hash",
        "data_manifest_path",
        "execution_policy_hash",
        "execution_policy_id",
        "execution_substate",
        "harness_verify_hash",
        "harness_verify_path",
        "paper_safety_review_hash",
        "paper_safety_review_path",
        "promotion_report_hash",
        "promotion_report_path",
        "research_contract_hash",
        "research_contract_path",
        "spec_hash",
        "strategy_name",
        "version_id",
    }
    missing = sorted(name for name in required if not _meaningful(payload.get(name)))
    missing.extend(
        name
        for name in ("previous_authorization_id", "previous_authorization_hash")
        if name not in payload
    )
    if missing:
        return _status(
            False,
            "Paper order authorization is missing required audit fields.",
            path,
            payload=payload,
            details={"missing": missing},
        )
    expected_spec_hash = strategy_content_hash(spec)
    mismatches: list[str] = []
    expected_values = {
        "strategy_name": spec.name,
        "version_id": strategy_version_id(spec),
        "spec_hash": expected_spec_hash,
        "execution_policy_id": policy.policy_id,
        "execution_policy_hash": policy.content_hash,
        "authorization_kind": "full",
        "authorization_receipt_version": AUTHORIZATION_RECEIPT_VERSION,
        "execution_substate": "order_authorized",
        "order_scope": "alpaca_paper_only",
        "real_money_broker_writes": "out_of_scope",
    }
    for field_name, expected in expected_values.items():
        if _normalize_hash(payload.get(field_name)) != _normalize_hash(expected):
            mismatches.append(field_name)
    if payload.get("authorized") is not True:
        mismatches.append("authorized")
    if (
        isinstance(payload.get("authorization_sequence"), bool)
        or not isinstance(payload.get("authorization_sequence"), int)
        or int(payload["authorization_sequence"]) < 1
    ):
        mismatches.append("authorization_sequence")
    payload_without_id = {key: value for key, value in payload.items() if key != "authorization_id"}
    if payload.get("authorization_id") != "auth_" + _canonical_hash(payload_without_id)[:16]:
        mismatches.append("authorization_id")
    mismatches.extend(_authorization_archive_mismatches(root, spec, payload))
    mismatches.extend(_authorization_lineage_mismatches(root, spec, payload))

    artifact_fields = {
        "paper_safety_review": ("paper_safety_review_path", "paper_safety_review_hash"),
        "promotion_report": ("promotion_report_path", "promotion_report_hash"),
        "research_contract": ("research_contract_path", "research_contract_hash"),
        "data_manifest": ("data_manifest_path", "data_manifest_hash"),
        "harness_verify": ("harness_verify_path", "harness_verify_hash"),
    }
    resolved: dict[str, Path] = {}
    for label, (path_field, hash_field) in artifact_fields.items():
        artifact_path = _resolve_ref(root, payload[path_field])
        resolved[label] = artifact_path
        if not artifact_path.is_file():
            mismatches.append(path_field)
        elif _sha256_file(artifact_path) != _normalize_hash(payload[hash_field]):
            mismatches.append(hash_field)

    if is_router_strategy(spec):
        for label in ("target_weights", "rebalance_intents"):
            path_field = f"{label}_path"
            hash_field = f"{label}_hash"
            if not _meaningful(payload.get(path_field)) or not _meaningful(payload.get(hash_field)):
                mismatches.append(path_field)
                continue
            artifact_path = _resolve_ref(root, payload[path_field])
            if not artifact_path.is_file() or _sha256_file(artifact_path) != _normalize_hash(
                payload[hash_field]
            ):
                mismatches.append(hash_field)

    if not mismatches:
        try:
            verify = _read_json(resolved["harness_verify"])
        except (OSError, ValueError, json.JSONDecodeError):
            mismatches.append("harness_verify")
        else:
            if verify.get("overall") != "ok":
                mismatches.append("harness_verify.overall")
    if not mismatches:
        mismatches.extend(
            _safety_review_mismatches(
                resolved["paper_safety_review"],
                spec,
                policy,
                payload,
            )
        )
    if mismatches:
        return _status(
            False,
            "Paper order authorization is stale or inconsistent.",
            path,
            payload=payload,
            details={"mismatches": sorted(set(mismatches))},
        )
    return _status(
        True,
        "Paper order authorization is valid for the current paper-only deployment.",
        path,
        payload=payload,
        details={
            "authorization_id": payload["authorization_id"],
            "authorization_archive_path": _relpath(
                paper_authorization_archive_path(root, spec, payload["authorization_id"]),
                root,
            ),
        },
        kind="full",
    )


def write_paper_order_authorization(
    spec: StrategySpec,
    root: Path,
    *,
    authorized_by: str,
    confirm_paper_only: bool,
) -> Path:
    raise ValueError(FULL_AUTHORIZATION_DISABLED_MESSAGE)


def _write_paper_order_authorization_locked(
    spec: StrategySpec,
    root: Path,
    *,
    authorized_by: str,
    confirm_paper_only: bool,
) -> Path:
    if not confirm_paper_only:
        raise ValueError("explicit paper-only authorization confirmation is required")
    if not authorized_by.strip():
        raise ValueError("authorized_by must identify the confirming operator")
    if spec.lifecycle != "active":
        raise ValueError("paper order authorization requires an active StrategySpec")
    if spec.execution.mode != "paper_auto" or spec.execution.broker != "alpaca_paper":
        raise ValueError("paper order authorization requires paper_auto with alpaca_paper")
    from open_composer.paper_readiness import assess_paper_strategy_readiness_for_spec

    readiness = assess_paper_strategy_readiness_for_spec(spec, root)
    unsafe = [
        check.name
        for check in readiness.checks
        if check.status != "ok"
        and not (check.status == "warning" and check.name == "order_authorization")
        and not (
            check.status == "warning"
            and check.name == "capability_report"
            and check.message
            == (
                "router strategies may run observation-only target-weight cycles before "
                "order authorization"
            )
        )
    ]
    if unsafe:
        raise ValueError(
            "paper authorization requires all prerequisite readiness checks: " + ", ".join(unsafe)
        )
    policy = require_orderable_execution_policy(spec, root)
    spec_hash = strategy_content_hash(spec)

    safety_path = root / "reports" / "harness" / "paper" / f"{spec.name}-paper-safety-review.json"
    promotion_path = root / "reports" / "research" / f"{spec.name}-promotion.json"
    verify_path = root / "reports" / "harness" / "verify" / f"{spec.name}.json"
    for required_path in (safety_path, promotion_path, verify_path):
        if not required_path.is_file():
            raise FileNotFoundError(f"required authorization artifact is missing: {required_path}")
    verify = _read_json(verify_path)
    if verify.get("overall") != "ok":
        raise ValueError("harness verify must be current and overall=ok before authorization")
    promotion = _read_json(promotion_path)
    promotion_binding = _promotion_binding(promotion, root, spec_hash)

    safety = _read_json(safety_path)
    expected_safety = {
        "strategy_name": spec.name,
        "spec_hash": spec_hash,
        "execution_policy_id": policy.policy_id,
        "execution_policy_hash": policy.content_hash,
        "promotion_report_hash": _sha256_file(promotion_path),
        "data_manifest_hash": promotion_binding["data_manifest_hash"],
    }
    safety_mismatches = [
        key
        for key, expected in expected_safety.items()
        if _normalize_hash(safety.get(key)) != _normalize_hash(expected)
    ]
    if (
        safety.get("overall") != "approved"
        or safety.get("blocking_items")
        or safety.get("harness_verify_pass") is not True
    ):
        safety_mismatches.append("paper_safety_review_status")
    if safety_mismatches:
        raise ValueError(
            "paper safety review is stale or incomplete: "
            + ", ".join(sorted(set(safety_mismatches)))
        )

    sequence, previous_id, previous_hash = _next_authorization_lineage(root, spec, "full")
    now = datetime.now(UTC).isoformat()
    payload: dict[str, Any] = {
        "strategy_name": spec.name,
        "authorization_kind": "full",
        "authorization_receipt_version": AUTHORIZATION_RECEIPT_VERSION,
        "authorization_sequence": sequence,
        "previous_authorization_id": previous_id,
        "previous_authorization_hash": previous_hash,
        "execution_substate": "order_authorized",
        "authorized": True,
        "authorized_at": now,
        "authorized_by": authorized_by.strip(),
        "version_id": strategy_version_id(spec),
        "spec_hash": spec_hash,
        "execution_policy_id": policy.policy_id,
        "execution_policy_hash": policy.content_hash,
        "paper_safety_review_path": _relpath(safety_path, root),
        "paper_safety_review_hash": _sha256_file(safety_path),
        "promotion_report_path": _relpath(promotion_path, root),
        "promotion_report_hash": _sha256_file(promotion_path),
        "research_contract_path": promotion_binding["research_contract_path"],
        "research_contract_hash": promotion_binding["research_contract_hash"],
        "data_manifest_path": promotion_binding["data_manifest_path"],
        "data_manifest_hash": promotion_binding["data_manifest_hash"],
        "harness_verify_path": _relpath(verify_path, root),
        "harness_verify_hash": _sha256_file(verify_path),
        "order_scope": "alpaca_paper_only",
        "real_money_broker_writes": "out_of_scope",
    }
    if is_router_strategy(spec):
        for label in ("target_weights", "rebalance_intents"):
            artifact_path = (
                root / "reports" / "execution" / f"{spec.name}-{label.replace('_', '-')}.json"
            )
            if not artifact_path.is_file():
                raise FileNotFoundError(f"required router artifact is missing: {artifact_path}")
            payload[f"{label}_path"] = _relpath(artifact_path, root)
            payload[f"{label}_hash"] = _sha256_file(artifact_path)
    payload["authorization_id"] = "auth_" + _canonical_hash(payload)[:16]
    path = paper_order_authorization_path(root, spec)
    _write_immutable_authorization(root, spec, payload)
    _atomic_write_json(path, payload)
    return path


def assess_paper_canary_authorization(
    spec: StrategySpec,
    root: Path,
    *,
    as_of: datetime | None = None,
) -> PaperOrderAuthorizationStatus:
    path = paper_canary_authorization_path(root, spec)
    if not path.is_file():
        return _status(False, "Paper canary authorization artifact is missing.", path)
    if path.is_symlink():
        return _status(False, "Paper canary authorization artifact is not a regular file.", path)
    try:
        payload = _read_json(path)
        policy = require_orderable_execution_policy(spec, root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _status(False, str(exc), path)

    required = {
        "authorization_id",
        "authorization_kind",
        "authorization_receipt_version",
        "authorization_sequence",
        "authorized_at",
        "authorized_by",
        "broker_account_id_hash",
        "canary_forward_sessions_required",
        "canary_safety_review_hash",
        "canary_safety_review_path",
        "data_manifest_hash",
        "data_manifest_path",
        "execution_policy_hash",
        "execution_policy_id",
        "execution_substate",
        "exclusive_account_writer",
        "expires_at",
        "harness_verify_hash",
        "harness_verify_path",
        "limits",
        "paper_account_snapshot_hash",
        "paper_account_snapshot_path",
        "paper_positions_snapshot_hash",
        "paper_positions_snapshot_path",
        "promotion_report_hash",
        "promotion_report_path",
        "research_contract_hash",
        "research_contract_path",
        "forward_sessions_observed",
        "full_forward_sessions_required",
        "spec_hash",
        "strategy_name",
        "version_id",
    }
    missing = sorted(name for name in required if not _meaningful(payload.get(name)))
    missing.extend(
        name
        for name in ("previous_authorization_id", "previous_authorization_hash")
        if name not in payload
    )
    if missing:
        return _status(
            False,
            "Paper canary authorization is missing required audit fields.",
            path,
            payload=payload,
            details={"missing": missing},
        )

    mismatches: list[str] = []
    expected = {
        "strategy_name": spec.name,
        "version_id": strategy_version_id(spec),
        "spec_hash": strategy_content_hash(spec),
        "execution_policy_id": policy.policy_id,
        "execution_policy_hash": policy.content_hash,
        "authorization_kind": "canary",
        "authorization_receipt_version": AUTHORIZATION_RECEIPT_VERSION,
        "execution_substate": "canary_authorized",
        "exclusive_account_writer": "open_composer_only",
        "order_scope": "alpaca_paper_only",
        "real_money_broker_writes": "out_of_scope",
        "allowed_symbols": sorted(spec.universe),
        "canary_forward_sessions_required": _canary_forward_session_requirement(spec),
        "full_forward_sessions_required": _full_forward_session_requirement(spec),
    }
    for field_name, value in expected.items():
        actual = payload.get(field_name)
        if field_name == "allowed_symbols":
            if sorted(str(item) for item in (actual or [])) != value:
                mismatches.append(field_name)
        elif _normalize_hash(actual) != _normalize_hash(value):
            mismatches.append(field_name)
    if payload.get("authorized") is not True:
        mismatches.append("authorized")
    if (
        isinstance(payload.get("authorization_sequence"), bool)
        or not isinstance(payload.get("authorization_sequence"), int)
        or int(payload["authorization_sequence"]) < 1
    ):
        mismatches.append("authorization_sequence")
    if (
        isinstance(payload.get("forward_sessions_observed"), bool)
        or not isinstance(payload.get("forward_sessions_observed"), int)
        or int(payload["forward_sessions_observed"]) < _canary_forward_session_requirement(spec)
    ):
        mismatches.append("forward_sessions_observed")
    without_id = {key: value for key, value in payload.items() if key != "authorization_id"}
    if payload.get("authorization_id") != "auth_" + _canonical_hash(without_id)[:16]:
        mismatches.append("authorization_id")
    mismatches.extend(_authorization_archive_mismatches(root, spec, payload))
    mismatches.extend(_authorization_lineage_mismatches(root, spec, payload))

    cutoff = _as_utc(as_of or datetime.now(UTC), field="as_of")
    try:
        authorized_at = _parse_timestamp(payload["authorized_at"], field="authorized_at")
        expires_at = _parse_timestamp(payload["expires_at"], field="expires_at")
    except ValueError as exc:
        mismatches.append(str(exc))
    else:
        if authorized_at > cutoff:
            mismatches.append("authorized_at")
        if expires_at <= cutoff:
            mismatches.append("expired")
        if expires_at <= authorized_at:
            mismatches.append("expires_at")
        if expires_at - authorized_at > timedelta(days=CANARY_MAX_DURATION_DAYS):
            mismatches.append("duration")
    mismatches.extend(_canary_limit_mismatches(payload.get("limits"), spec))

    artifact_fields = {
        "canary_safety_review": ("canary_safety_review_path", "canary_safety_review_hash"),
        "promotion_report": ("promotion_report_path", "promotion_report_hash"),
        "research_contract": ("research_contract_path", "research_contract_hash"),
        "data_manifest": ("data_manifest_path", "data_manifest_hash"),
        "harness_verify": ("harness_verify_path", "harness_verify_hash"),
        "paper_account_snapshot": (
            "paper_account_snapshot_path",
            "paper_account_snapshot_hash",
        ),
        "paper_positions_snapshot": (
            "paper_positions_snapshot_path",
            "paper_positions_snapshot_hash",
        ),
    }
    resolved: dict[str, Path] = {}
    for label, (path_field, hash_field) in artifact_fields.items():
        artifact_path = _resolve_ref(root, payload[path_field])
        resolved[label] = artifact_path
        if not artifact_path.is_file():
            mismatches.append(path_field)
        elif _sha256_file(artifact_path) != _normalize_hash(payload[hash_field]):
            mismatches.append(hash_field)

    if not mismatches:
        try:
            verify = _read_json(resolved["harness_verify"])
            promotion = _read_json(resolved["promotion_report"])
            account = _read_json(resolved["paper_account_snapshot"])
            positions = _read_json(resolved["paper_positions_snapshot"])
        except (OSError, ValueError, json.JSONDecodeError):
            mismatches.append("bound_artifact_json")
        else:
            if verify.get("overall") != "ok":
                mismatches.append("harness_verify.overall")
            try:
                promotion_binding = _promotion_binding(
                    promotion,
                    root,
                    strategy_content_hash(spec),
                )
            except (OSError, ValueError):
                mismatches.append("promotion_report.binding")
            else:
                for label in ("research_contract", "data_manifest"):
                    for suffix in ("path", "hash"):
                        key = f"{label}_{suffix}"
                        if _normalize_hash(payload.get(key)) != _normalize_hash(
                            promotion_binding[key]
                        ):
                            mismatches.append(key)
            if (
                account.get("paper") is not True
                or account.get("broker_account_id_hash") != payload["broker_account_id_hash"]
                or _account_status_name(account.get("status")) != "ACTIVE"
            ):
                mismatches.append("paper_account_snapshot.binding")
            if positions.get("paper") is not True or not isinstance(
                positions.get("positions"), list
            ):
                mismatches.append("paper_positions_snapshot.binding")
    if not mismatches:
        mismatches.extend(
            _canary_review_mismatches(
                resolved["canary_safety_review"],
                spec,
                policy,
                payload,
            )
        )

    mismatches.extend(_canary_revocation_mismatches(root, spec, payload))

    if mismatches:
        return _status(
            False,
            "Paper canary authorization is expired, revoked, stale, or inconsistent.",
            path,
            payload=payload,
            details={"mismatches": sorted(set(mismatches))},
        )
    return _status(
        True,
        "Bounded Alpaca Paper canary authorization is valid; full paper readiness remains false.",
        path,
        payload=payload,
        details={
            "authorization_id": payload["authorization_id"],
            "authorization_archive_path": _relpath(
                paper_authorization_archive_path(root, spec, payload["authorization_id"]),
                root,
            ),
            "expires_at": payload["expires_at"],
            "limits": payload["limits"],
        },
        kind="canary",
    )


def write_paper_canary_authorization(
    spec: StrategySpec,
    root: Path,
    *,
    authorized_by: str,
    confirm_paper_only: bool,
    confirm_canary_risk: bool,
    duration_days: int = 14,
    max_order_notional: float = CANARY_MAX_ORDER_NOTIONAL,
    max_session_notional: float = CANARY_MAX_SESSION_NOTIONAL,
    max_total_notional: float = 8_000.0,
    max_orders_per_session: int = CANARY_MAX_ORDERS_PER_SESSION,
    max_total_orders: int = 12,
    as_of: datetime | None = None,
) -> Path:
    with paper_control_lock(root):
        return _write_paper_canary_authorization_locked(
            spec,
            root,
            authorized_by=authorized_by,
            confirm_paper_only=confirm_paper_only,
            confirm_canary_risk=confirm_canary_risk,
            duration_days=duration_days,
            max_order_notional=max_order_notional,
            max_session_notional=max_session_notional,
            max_total_notional=max_total_notional,
            max_orders_per_session=max_orders_per_session,
            max_total_orders=max_total_orders,
            as_of=as_of,
        )


def _write_paper_canary_authorization_locked(
    spec: StrategySpec,
    root: Path,
    *,
    authorized_by: str,
    confirm_paper_only: bool,
    confirm_canary_risk: bool,
    duration_days: int = 14,
    max_order_notional: float = CANARY_MAX_ORDER_NOTIONAL,
    max_session_notional: float = CANARY_MAX_SESSION_NOTIONAL,
    max_total_notional: float = 8_000.0,
    max_orders_per_session: int = CANARY_MAX_ORDERS_PER_SESSION,
    max_total_orders: int = 12,
    as_of: datetime | None = None,
) -> Path:
    if not confirm_paper_only or not confirm_canary_risk:
        raise ValueError("explicit paper-only and bounded-canary risk confirmations are required")
    if not authorized_by.strip():
        raise ValueError("authorized_by must identify the confirming operator")
    if spec.lifecycle != "active":
        raise ValueError("paper canary authorization requires an active StrategySpec")
    if spec.execution.mode != "paper_auto" or spec.execution.broker != "alpaca_paper":
        raise ValueError("paper canary requires paper_auto with alpaca_paper")
    if spec.position_direction != "long_only":
        raise ValueError("paper canary authorization is long-only")
    if isinstance(duration_days, bool) or not isinstance(duration_days, int):
        raise ValueError("canary duration_days must be an integer")
    if duration_days < 1 or duration_days > CANARY_MAX_DURATION_DAYS:
        raise ValueError(f"canary duration_days must be between 1 and {CANARY_MAX_DURATION_DAYS}")

    limits = {
        "max_order_notional_usd": float(max_order_notional),
        "max_session_notional_usd": float(max_session_notional),
        "max_total_notional_usd": float(max_total_notional),
        "max_orders_per_session": max_orders_per_session,
        "max_total_orders": max_total_orders,
    }
    limit_mismatches = _canary_limit_mismatches(limits, spec)
    if limit_mismatches:
        raise ValueError("invalid paper canary limits: " + ", ".join(limit_mismatches))

    from open_composer.paper_readiness import assess_paper_strategy_readiness_for_spec

    readiness = assess_paper_strategy_readiness_for_spec(spec, root)
    permitted_bootstrap_gaps = {
        "canary_authorization",
        "matched_paper_tca",
        "order_authorization",
        "paper_validation",
    }
    unsafe = [
        check.name
        for check in readiness.checks
        if check.status != "ok"
        and not (check.status == "warning" and check.name in permitted_bootstrap_gaps)
    ]
    if unsafe:
        raise ValueError(
            "paper canary requires every non-bootstrap readiness check: " + ", ".join(unsafe)
        )
    full_forward_sessions = _full_forward_session_requirement(spec)
    canary_forward_sessions = _canary_forward_session_requirement(spec)
    validation_check = next(
        (check for check in readiness.checks if check.name == "paper_validation"),
        None,
    )
    observed_forward_sessions = (
        int(validation_check.details.get("forward_observation_progress_days") or 0)
        if validation_check is not None
        else 0
    )
    if validation_check is None or observed_forward_sessions < canary_forward_sessions:
        raise ValueError(
            "paper canary requires its bound broker-free forward observation threshold to pass"
        )

    policy = require_orderable_execution_policy(spec, root)
    style = str(policy.payload.get("order_style") or "").lower()
    time_in_force = str(policy.payload.get("time_in_force") or "").lower()
    if style not in CANARY_ALLOWED_ORDER_STYLES:
        raise ValueError("paper canary requires a price-protected limit order policy")
    if time_in_force not in CANARY_ALLOWED_TIME_IN_FORCE:
        raise ValueError("paper canary prohibits persistent order time-in-force")

    spec_hash = strategy_content_hash(spec)
    canary_review_path = (
        root / "reports" / "harness" / "paper" / f"{spec.name}-canary-safety-review.json"
    )
    promotion_path = root / "reports" / "research" / f"{spec.name}-promotion.json"
    verify_path = root / "reports" / "harness" / "verify" / f"{spec.name}.json"
    account_path = root / "reports" / "paper" / "account.json"
    positions_path = root / "reports" / "paper" / "positions.json"
    open_orders_path = root / "reports" / "paper" / "open_orders.json"
    sync_receipt_path = root / "reports" / "paper" / "broker_receipts" / "latest-sync.json"
    kill_switch_path = root / "reports" / "paper" / "kill_switch.json"
    for required_path in (
        canary_review_path,
        promotion_path,
        verify_path,
        account_path,
        positions_path,
        open_orders_path,
        sync_receipt_path,
        kill_switch_path,
    ):
        if not required_path.is_file():
            raise FileNotFoundError(f"required canary artifact is missing: {required_path}")

    verify = _read_json(verify_path)
    if verify.get("overall") != "ok":
        raise ValueError("harness verify must be current and overall=ok before canary")
    promotion = _read_json(promotion_path)
    promotion_binding = _promotion_binding(promotion, root, spec_hash)
    account = _read_json(account_path)
    positions = _read_json(positions_path)
    open_orders = _read_json(open_orders_path)
    sync_receipt = _read_json(sync_receipt_path)
    kill_switch = _read_json(kill_switch_path)
    account_id_hash = _normalize_hash(account.get("broker_account_id_hash"))
    if (
        not account_id_hash
        or account.get("paper") is not True
        or _account_status_name(account.get("status")) != "ACTIVE"
    ):
        raise ValueError("paper account snapshot must bind an active Alpaca Paper account id")
    if positions.get("paper") is not True or not isinstance(positions.get("positions"), list):
        raise ValueError("paper positions snapshot is invalid")
    if any(abs(float(item.get("qty") or 0)) > 1e-9 for item in positions["positions"]):
        raise ValueError("initial paper canary authorization requires a flat paper account")
    if open_orders.get("paper") is not True or open_orders.get("orders") != []:
        raise ValueError("initial paper canary authorization requires zero broker open orders")
    if (
        sync_receipt.get("receipt_version") != 1
        or sync_receipt.get("receipt_source") != "alpaca_paper_sync"
        or sync_receipt.get("paper") is not True
        or sync_receipt.get("broker_account_id_hash") != account_id_hash
    ):
        raise ValueError("paper canary requires a current account-bound broker sync receipt")
    if kill_switch.get("enabled") is not False:
        raise ValueError("paper canary requires an explicit clear kill-switch artifact")

    frozen_account = _freeze_authorization_evidence(root, spec.name, "account", account_path)
    frozen_positions = _freeze_authorization_evidence(
        root,
        spec.name,
        "positions",
        positions_path,
    )
    sequence, previous_id, previous_hash = _next_authorization_lineage(root, spec, "canary")
    now = _as_utc(as_of or datetime.now(UTC), field="as_of")
    payload: dict[str, Any] = {
        "strategy_name": spec.name,
        "authorization_kind": "canary",
        "authorization_receipt_version": AUTHORIZATION_RECEIPT_VERSION,
        "authorization_sequence": sequence,
        "previous_authorization_id": previous_id,
        "previous_authorization_hash": previous_hash,
        "execution_substate": "canary_authorized",
        "authorized": True,
        "authorized_at": now.isoformat(),
        "expires_at": (now + timedelta(days=duration_days)).isoformat(),
        "authorized_by": authorized_by.strip(),
        "version_id": strategy_version_id(spec),
        "spec_hash": spec_hash,
        "execution_policy_id": policy.policy_id,
        "execution_policy_hash": policy.content_hash,
        "canary_safety_review_path": _relpath(canary_review_path, root),
        "canary_safety_review_hash": _sha256_file(canary_review_path),
        "promotion_report_path": _relpath(promotion_path, root),
        "promotion_report_hash": _sha256_file(promotion_path),
        "research_contract_path": promotion_binding["research_contract_path"],
        "research_contract_hash": promotion_binding["research_contract_hash"],
        "data_manifest_path": promotion_binding["data_manifest_path"],
        "data_manifest_hash": promotion_binding["data_manifest_hash"],
        "harness_verify_path": _relpath(verify_path, root),
        "harness_verify_hash": _sha256_file(verify_path),
        "paper_account_snapshot_path": _relpath(frozen_account, root),
        "paper_account_snapshot_hash": _sha256_file(frozen_account),
        "paper_positions_snapshot_path": _relpath(frozen_positions, root),
        "paper_positions_snapshot_hash": _sha256_file(frozen_positions),
        "broker_account_id_hash": account_id_hash,
        "exclusive_account_writer": "open_composer_only",
        "allowed_symbols": sorted(spec.universe),
        "canary_forward_sessions_required": canary_forward_sessions,
        "forward_sessions_observed": observed_forward_sessions,
        "full_forward_sessions_required": full_forward_sessions,
        "limits": limits,
        "order_scope": "alpaca_paper_only",
        "real_money_broker_writes": "out_of_scope",
    }
    review_mismatches = _canary_review_mismatches(
        canary_review_path,
        spec,
        policy,
        payload,
    )
    if review_mismatches:
        raise ValueError(
            "paper canary safety review is stale or incomplete: "
            + ", ".join(sorted(set(review_mismatches)))
        )
    payload["authorization_id"] = "auth_" + _canonical_hash(payload)[:16]
    path = paper_canary_authorization_path(root, spec)
    _write_immutable_authorization(root, spec, payload)
    _atomic_write_json(path, payload)
    return path


def write_paper_canary_revocation(
    spec: StrategySpec,
    root: Path,
    *,
    revoked_by: str,
    reason: str,
    as_of: datetime | None = None,
) -> Path:
    with paper_control_lock(root):
        return _write_paper_canary_revocation_locked(
            spec,
            root,
            revoked_by=revoked_by,
            reason=reason,
            as_of=as_of,
        )


def _write_paper_canary_revocation_locked(
    spec: StrategySpec,
    root: Path,
    *,
    revoked_by: str,
    reason: str,
    as_of: datetime | None = None,
) -> Path:
    if not revoked_by.strip() or not reason.strip():
        raise ValueError("canary revocation requires revoked_by and reason")
    authorization_path = paper_canary_authorization_path(root, spec)
    if not authorization_path.is_file():
        raise FileNotFoundError("paper canary authorization artifact is missing")
    authorization = _read_json(authorization_path)
    archive_mismatches = _authorization_archive_mismatches(root, spec, authorization)
    if archive_mismatches:
        raise ValueError(
            "paper canary authorization cannot be revoked because its immutable receipt is "
            "missing or inconsistent: " + ", ".join(sorted(set(archive_mismatches)))
        )
    authorization_hash = _canonical_hash(authorization)
    payload = {
        "strategy_name": spec.name,
        "authorization_kind": "canary",
        "authorization_id": authorization.get("authorization_id"),
        "authorization_hash": authorization_hash,
        "revoked": True,
        "revoked_at": _as_utc(as_of or datetime.now(UTC), field="as_of").isoformat(),
        "revoked_by": revoked_by.strip(),
        "reason": reason.strip(),
    }
    payload["revocation_id"] = "revoke_" + _canonical_hash(payload)[:16]
    path = paper_canary_revocation_path(root, spec)
    _write_immutable_canary_revocation(root, spec, payload)
    _atomic_write_json(path, payload)
    return path


def revalidate_paper_submission_authorization(
    spec: StrategySpec,
    root: Path,
    expected: PaperOrderAuthorizationStatus,
) -> PaperOrderAuthorizationStatus:
    """Confirm that the authorization held by a pending submit is still current.

    The final broker-write path holds the paper control lock while calling this function.
    This catches direct filesystem mutation and guarantees that the authorization bound into
    an intent is the exact one still active immediately before a broker write.
    """
    if expected.kind == "full":
        current = assess_paper_order_authorization(spec, root)
    elif expected.kind == "canary":
        current = assess_paper_canary_authorization(spec, root)
    else:
        raise ValueError("paper submission has no recognized authorization kind")
    if not current.authorized:
        raise ValueError(current.message)

    expected_id = str(expected.payload.get("authorization_id") or "")
    current_id = str(current.payload.get("authorization_id") or "")
    mismatches: list[str] = []
    if not expected_id or current_id != expected_id:
        mismatches.append("authorization_id")
    if not expected.content_hash or current.content_hash != expected.content_hash:
        mismatches.append("authorization_hash")
    if current.kind != expected.kind:
        mismatches.append("authorization_kind")
    if mismatches:
        raise ValueError(
            "paper authorization changed after order intent reservation: " + ", ".join(mismatches)
        )
    return current


def require_paper_submission_authorization_effective_at(
    authorization: PaperOrderAuthorizationStatus,
    decision_at: datetime,
) -> None:
    if authorization.kind != "canary":
        return
    cutoff = _as_utc(decision_at, field="decision_at")
    try:
        authorized_at = _parse_timestamp(
            authorization.payload["authorized_at"],
            field="authorized_at",
        )
        expires_at = _parse_timestamp(
            authorization.payload["expires_at"],
            field="expires_at",
        )
    except (KeyError, ValueError) as exc:
        raise ValueError("paper canary authorization has an invalid effective interval") from exc
    if not authorized_at <= cutoff < expires_at:
        raise ValueError(
            "paper canary authorization is not effective at broker-write decision time"
        )


def _write_immutable_authorization(
    root: Path,
    spec: StrategySpec,
    payload: dict[str, Any],
) -> Path:
    authorization_id = _safe_immutable_id(payload.get("authorization_id"), prefix="auth_")
    path = paper_authorization_archive_path(root, spec, authorization_id)
    _write_immutable_json(path, payload)
    return path


def _write_immutable_canary_revocation(
    root: Path,
    spec: StrategySpec,
    payload: dict[str, Any],
) -> Path:
    revocation_id = _safe_immutable_id(payload.get("revocation_id"), prefix="revoke_")
    path = paper_canary_revocation_archive_path(root, spec, revocation_id)
    _write_immutable_json(path, payload)
    return path


def _authorization_archive_mismatches(
    root: Path,
    spec: StrategySpec,
    payload: dict[str, Any],
) -> list[str]:
    try:
        authorization_id = _safe_immutable_id(payload.get("authorization_id"), prefix="auth_")
        archive_path = paper_authorization_archive_path(root, spec, authorization_id)
    except ValueError:
        return ["authorization_archive_id"]
    if archive_path.is_symlink() or not archive_path.is_file():
        return ["authorization_archive_missing"]
    try:
        archived = _read_json(archive_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return ["authorization_archive_invalid"]
    if _canonical_hash(archived) != _canonical_hash(payload):
        return ["authorization_archive_hash"]
    return []


def _next_authorization_lineage(
    root: Path,
    spec: StrategySpec,
    kind: Literal["canary", "full"],
) -> tuple[int, str | None, str | None]:
    history = [
        row for row in _read_authorization_history(root, spec) if row["authorization_kind"] == kind
    ]
    if not history:
        return 1, None, None
    latest = max(history, key=lambda row: int(row["authorization_sequence"]))
    return (
        int(latest["authorization_sequence"]) + 1,
        str(latest["authorization_id"]),
        _canonical_hash(latest),
    )


def _authorization_lineage_mismatches(
    root: Path,
    spec: StrategySpec,
    payload: dict[str, Any],
) -> list[str]:
    try:
        history = _read_authorization_history(root, spec)
    except (OSError, ValueError, json.JSONDecodeError):
        return ["authorization_history_invalid"]
    kind = payload.get("authorization_kind")
    same_kind = [row for row in history if row.get("authorization_kind") == kind]
    if not same_kind:
        return ["authorization_history_missing"]
    latest = max(same_kind, key=lambda row: int(row["authorization_sequence"]))
    if latest.get("authorization_id") != payload.get("authorization_id"):
        return ["authorization_superseded"]
    return []


def _read_authorization_history(root: Path, spec: StrategySpec) -> list[dict[str, Any]]:
    directory = paper_authorization_archive_dir(root, spec)
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("immutable authorization history directory is invalid")
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise ValueError("immutable authorization history contains a non-regular file")
        payload = _read_json(path)
        authorization_id = _safe_immutable_id(payload.get("authorization_id"), prefix="auth_")
        if paper_authorization_archive_path(root, spec, authorization_id) != path:
            raise ValueError("immutable authorization history path does not match its id")
        if payload.get("strategy_name") != spec.name:
            raise ValueError("immutable authorization history strategy mismatch")
        if payload.get("authorization_kind") not in {"canary", "full"}:
            raise ValueError("immutable authorization history kind is invalid")
        if payload.get("authorization_receipt_version") != AUTHORIZATION_RECEIPT_VERSION:
            raise ValueError("immutable authorization history version is invalid")
        sequence = payload.get("authorization_sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("immutable authorization history sequence is invalid")
        if (
            "previous_authorization_id" not in payload
            or "previous_authorization_hash" not in payload
        ):
            raise ValueError("immutable authorization history previous binding is missing")
        without_id = {key: value for key, value in payload.items() if key != "authorization_id"}
        if authorization_id != "auth_" + _canonical_hash(without_id)[:16]:
            raise ValueError("immutable authorization history id is invalid")
        rows.append(payload)

    for kind in ("canary", "full"):
        lineage = sorted(
            (row for row in rows if row["authorization_kind"] == kind),
            key=lambda row: int(row["authorization_sequence"]),
        )
        if [int(row["authorization_sequence"]) for row in lineage] != list(
            range(1, len(lineage) + 1)
        ):
            raise ValueError("immutable authorization history sequence is not contiguous")
        previous: dict[str, Any] | None = None
        for row in lineage:
            expected_id = str(previous["authorization_id"]) if previous is not None else None
            expected_hash = _canonical_hash(previous) if previous is not None else None
            if row.get("previous_authorization_id") != expected_id:
                raise ValueError("immutable authorization history previous id mismatch")
            if row.get("previous_authorization_hash") != expected_hash:
                raise ValueError("immutable authorization history previous hash mismatch")
            previous = row
    return rows


def _canary_revocation_mismatches(
    root: Path,
    spec: StrategySpec,
    authorization: dict[str, Any],
) -> list[str]:
    authorization_id = str(authorization.get("authorization_id") or "")
    authorization_hash = _canonical_hash(authorization)
    mismatches: list[str] = []
    history_dir = paper_canary_revocation_archive_dir(root, spec)
    if history_dir.exists():
        if history_dir.is_symlink() or not history_dir.is_dir():
            mismatches.append("canary_revocation_history_invalid")
        else:
            for path in sorted(history_dir.glob("*.json")):
                if path.is_symlink() or not path.is_file():
                    mismatches.append("canary_revocation_history_invalid")
                    continue
                try:
                    revocation = _read_json(path)
                except (OSError, ValueError, json.JSONDecodeError):
                    mismatches.append("canary_revocation_history_invalid")
                    continue
                errors = _canary_revocation_payload_mismatches(revocation, spec)
                try:
                    expected_path = paper_canary_revocation_archive_path(
                        root,
                        spec,
                        str(revocation.get("revocation_id") or ""),
                    )
                except ValueError:
                    expected_path = None
                if expected_path != path:
                    errors.append("archive_path")
                if errors:
                    mismatches.append("canary_revocation_history_invalid")
                    continue
                mismatches.extend(
                    _canary_revocation_effects(
                        revocation,
                        authorization_id=authorization_id,
                        authorization_hash=authorization_hash,
                    )
                )

    pointer = paper_canary_revocation_path(root, spec)
    if pointer.is_symlink():
        mismatches.append("canary_revocation_pointer_invalid")
    elif pointer.is_file():
        try:
            revocation = _read_json(pointer)
        except (OSError, ValueError, json.JSONDecodeError):
            mismatches.append("canary_revocation_pointer_invalid")
        else:
            errors = _canary_revocation_payload_mismatches(revocation, spec)
            try:
                archive_path = paper_canary_revocation_archive_path(
                    root,
                    spec,
                    str(revocation.get("revocation_id") or ""),
                )
            except ValueError:
                archive_path = None
            archived = _read_json_or_none(archive_path) if archive_path is not None else None
            if (
                archive_path is None
                or not archive_path.is_file()
                or archived is None
                or _canonical_hash(archived) != _canonical_hash(revocation)
            ):
                errors.append("archive")
            if errors:
                mismatches.append("canary_revocation_pointer_invalid")
            else:
                mismatches.extend(
                    _canary_revocation_effects(
                        revocation,
                        authorization_id=authorization_id,
                        authorization_hash=authorization_hash,
                    )
                )
    return sorted(set(mismatches))


def _canary_revocation_payload_mismatches(
    payload: dict[str, Any],
    spec: StrategySpec,
) -> list[str]:
    required = {
        "strategy_name",
        "authorization_kind",
        "authorization_id",
        "authorization_hash",
        "revoked",
        "revoked_at",
        "revoked_by",
        "reason",
        "revocation_id",
    }
    mismatches = [name for name in required if not _meaningful(payload.get(name))]
    if payload.get("strategy_name") != spec.name:
        mismatches.append("strategy_name")
    if payload.get("authorization_kind") != "canary":
        mismatches.append("authorization_kind")
    if payload.get("revoked") is not True:
        mismatches.append("revoked")
    try:
        _safe_immutable_id(payload.get("authorization_id"), prefix="auth_")
        revocation_id = _safe_immutable_id(payload.get("revocation_id"), prefix="revoke_")
        without_id = {key: value for key, value in payload.items() if key != "revocation_id"}
        if revocation_id != "revoke_" + _canonical_hash(without_id)[:16]:
            mismatches.append("revocation_id")
        _parse_timestamp(payload.get("revoked_at"), field="revoked_at")
    except ValueError:
        mismatches.append("id_or_timestamp")
    if (
        not isinstance(payload.get("authorization_hash"), str)
        or len(str(payload.get("authorization_hash"))) != 64
    ):
        mismatches.append("authorization_hash")
    return mismatches


def _canary_revocation_effects(
    revocation: dict[str, Any],
    *,
    authorization_id: str,
    authorization_hash: str,
) -> list[str]:
    if revocation.get("authorization_id") != authorization_id:
        return []
    if revocation.get("authorization_hash") != authorization_hash:
        return ["canary_revocation_binding_mismatch"]
    return ["revoked"]


def _promotion_binding(
    promotion: dict[str, Any],
    root: Path,
    spec_hash: str,
) -> dict[str, str]:
    manifest = promotion.get("research_manifest")
    if not isinstance(manifest, dict):
        raise ValueError("promotion report is missing research_manifest")
    if _normalize_hash(manifest.get("spec_hash")) != spec_hash:
        raise ValueError("promotion report does not bind the current StrategySpec hash")
    if promotion.get("ready") is not True or str(promotion.get("status")) != "ok":
        raise ValueError("promotion report is not ready with status=ok")

    research_contract_ref = manifest.get("research_contract_path")
    if not _meaningful(research_contract_ref):
        raise ValueError("promotion report is missing research_contract_path")
    research_contract_path = _resolve_ref(root, research_contract_ref)
    if not research_contract_path.is_file():
        raise FileNotFoundError(f"research contract is missing: {research_contract_path}")

    data_ref = next(
        (
            manifest.get(name)
            for name in (
                "data_snapshot_manifest_path",
                "data_snapshot_binding_path",
                "data_manifest_path",
            )
            if _meaningful(manifest.get(name))
        ),
        None,
    )
    if data_ref is None:
        raise ValueError("promotion report is missing an immutable data manifest path")
    data_path = _resolve_ref(root, data_ref)
    if not data_path.is_file():
        raise FileNotFoundError(f"promotion data manifest is missing: {data_path}")
    recorded_data_hash = next(
        (
            _normalize_hash(manifest.get(name))
            for name in (
                "data_snapshot_manifest_hash",
                "data_snapshot_binding_hash",
                "data_manifest_hash",
                "data_path_hash",
            )
            if _meaningful(manifest.get(name))
        ),
        None,
    )
    actual_data_hash = _sha256_file(data_path)
    if recorded_data_hash != actual_data_hash:
        raise ValueError("promotion report immutable data manifest hash is missing or stale")
    return {
        "research_contract_path": _relpath(research_contract_path, root),
        "research_contract_hash": _sha256_file(research_contract_path),
        "data_manifest_path": _relpath(data_path, root),
        "data_manifest_hash": actual_data_hash,
    }


def _safety_review_mismatches(
    path: Path,
    spec: StrategySpec,
    policy: ExecutionPolicyBinding,
    authorization: dict[str, Any],
) -> list[str]:
    try:
        safety = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return ["paper_safety_review"]
    expected = {
        "strategy_name": spec.name,
        "spec_hash": strategy_content_hash(spec),
        "execution_policy_id": policy.policy_id,
        "execution_policy_hash": policy.content_hash,
        "promotion_report_hash": authorization.get("promotion_report_hash"),
        "data_manifest_hash": authorization.get("data_manifest_hash"),
    }
    mismatches = [
        f"paper_safety_review.{key}"
        for key, value in expected.items()
        if _normalize_hash(safety.get(key)) != _normalize_hash(value)
    ]
    if safety.get("overall") != "approved" or safety.get("blocking_items"):
        mismatches.append("paper_safety_review.status")
    return mismatches


def _canary_review_mismatches(
    path: Path,
    spec: StrategySpec,
    policy: ExecutionPolicyBinding,
    authorization: dict[str, Any],
) -> list[str]:
    try:
        review = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return ["canary_safety_review"]
    expected = {
        "strategy_name": spec.name,
        "spec_hash": strategy_content_hash(spec),
        "execution_policy_id": policy.policy_id,
        "execution_policy_hash": policy.content_hash,
        "promotion_report_hash": authorization.get("promotion_report_hash"),
        "data_manifest_hash": authorization.get("data_manifest_hash"),
        "harness_verify_hash": authorization.get("harness_verify_hash"),
    }
    mismatches = [
        f"canary_safety_review.{key}"
        for key, value in expected.items()
        if _normalize_hash(review.get(key)) != _normalize_hash(value)
    ]
    if review.get("overall") != "approved" or review.get("blocking_items"):
        mismatches.append("canary_safety_review.status")
    if review.get("harness_verify_pass") is not True:
        mismatches.append("canary_safety_review.harness_verify_pass")
    if review.get("kill_switch_verified") is not True:
        mismatches.append("canary_safety_review.kill_switch_verified")
    if review.get("signal_order_linkage") is not True:
        mismatches.append("canary_safety_review.signal_order_linkage")
    if str(review.get("credential_scope") or "") != "paper_only":
        mismatches.append("canary_safety_review.credential_scope")
    if str(review.get("exclusive_account_writer") or "") != "open_composer_only":
        mismatches.append("canary_safety_review.exclusive_account_writer")
    if _normalize_hash(review.get("broker_account_id_hash")) != _normalize_hash(
        authorization.get("broker_account_id_hash")
    ):
        mismatches.append("canary_safety_review.broker_account_id_hash")
    reviewed_limits = review.get("maximum_canary_limits")
    requested_limits = authorization.get("limits")
    if not isinstance(reviewed_limits, dict) or not isinstance(requested_limits, dict):
        mismatches.append("canary_safety_review.maximum_canary_limits")
    else:
        for key, requested in requested_limits.items():
            reviewed = reviewed_limits.get(key)
            if isinstance(requested, bool) or isinstance(reviewed, bool):
                mismatches.append(f"canary_safety_review.maximum_canary_limits.{key}")
                continue
            try:
                exceeds_review = float(requested) > float(reviewed)
            except (TypeError, ValueError):
                exceeds_review = True
            if exceeds_review:
                mismatches.append(f"canary_safety_review.maximum_canary_limits.{key}")
    return mismatches


def _canary_limit_mismatches(limits: Any, spec: StrategySpec) -> list[str]:
    if not isinstance(limits, dict):
        return ["limits"]
    numeric_maxima = {
        "max_order_notional_usd": CANARY_MAX_ORDER_NOTIONAL,
        "max_session_notional_usd": CANARY_MAX_SESSION_NOTIONAL,
        "max_total_notional_usd": CANARY_MAX_TOTAL_NOTIONAL,
    }
    integer_maxima = {
        "max_orders_per_session": min(
            CANARY_MAX_ORDERS_PER_SESSION,
            int(spec.risk.max_trades_per_day),
        ),
        "max_total_orders": CANARY_MAX_TOTAL_ORDERS,
    }
    mismatches: list[str] = []
    normalized: dict[str, float] = {}
    for key, maximum in numeric_maxima.items():
        value = limits.get(key)
        if isinstance(value, bool):
            mismatches.append(key)
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            mismatches.append(key)
            continue
        if not (0 < number <= maximum):
            mismatches.append(key)
        normalized[key] = number
    for key, maximum in integer_maxima.items():
        value = limits.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= maximum):
            mismatches.append(key)
        else:
            normalized[key] = float(value)
    if normalized.get("max_session_notional_usd", 0) < normalized.get(
        "max_order_notional_usd", float("inf")
    ):
        mismatches.append("max_session_notional_usd_below_order")
    if normalized.get("max_total_notional_usd", 0) < normalized.get(
        "max_session_notional_usd", float("inf")
    ):
        mismatches.append("max_total_notional_usd_below_session")
    if normalized.get("max_total_orders", 0) < normalized.get(
        "max_orders_per_session", float("inf")
    ):
        mismatches.append("max_total_orders_below_session")
    return sorted(set(mismatches))


def _full_forward_session_requirement(spec: StrategySpec) -> int:
    notes = spec.notes.model_dump(mode="json")
    value = notes.get("minimum_bound_forward_sessions")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            "paper canary requires notes.minimum_bound_forward_sessions as a positive integer"
        )
    return value


def _canary_forward_session_requirement(spec: StrategySpec) -> int:
    notes = spec.notes.model_dump(mode="json")
    full_requirement = _full_forward_session_requirement(spec)
    value = notes.get("minimum_canary_forward_sessions", full_requirement)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            "paper canary requires notes.minimum_canary_forward_sessions as a positive integer"
        )
    if value > full_requirement:
        raise ValueError(
            "notes.minimum_canary_forward_sessions cannot exceed "
            "notes.minimum_bound_forward_sessions"
        )
    return value


def _account_status_name(value: Any) -> str:
    return str(value or "").rsplit(".", 1)[-1].upper()


def _freeze_authorization_evidence(
    root: Path,
    strategy_name: str,
    label: str,
    source: Path,
) -> Path:
    source_resolved = source.resolve(strict=True)
    source_resolved.relative_to(root.resolve())
    digest = _sha256_file(source_resolved)
    destination = (
        root
        / "reports"
        / "paper"
        / "authorization_evidence"
        / strategy_name
        / f"{label}-{digest}.json"
    )
    ensure_dir(destination.parent)
    if destination.exists():
        if _sha256_file(destination) != digest:
            raise ValueError(f"immutable authorization evidence differs for {label}")
    else:
        destination.write_bytes(source_resolved.read_bytes())
    return destination


def _write_immutable_json(path: Path, payload: dict[str, Any]) -> None:
    """Publish one content-addressed authorization record without allowing overwrite."""
    encoded = _json_text(payload)
    ensure_dir(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file():
                raise ValueError(
                    f"immutable authorization record is not a regular file: {path}"
                ) from None
            try:
                existing = _read_json(path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"immutable authorization record is unreadable: {path}") from exc
            if _canonical_hash(existing) != _canonical_hash(payload):
                raise ValueError(f"immutable authorization record differs: {path}") from None
        else:
            os.chmod(path, 0o400)
            _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(_json_text(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _safe_strategy_component(value: str) -> str:
    name = str(value)
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValueError("strategy name cannot be used in an immutable authorization path")
    return name


def _safe_immutable_id(value: Any, *, prefix: str) -> str:
    identifier = str(value or "")
    suffix = identifier.removeprefix(prefix)
    if (
        not identifier.startswith(prefix)
        or len(suffix) != 16
        or any(char not in "0123456789abcdef" for char in suffix)
    ):
        raise ValueError(f"invalid immutable authorization identifier: {identifier!r}")
    return identifier


def _read_json_or_none(path: Path) -> dict[str, Any] | None:
    try:
        return _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _status(
    authorized: bool,
    message: str,
    path: Path,
    *,
    payload: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    kind: Literal["none", "canary", "full"] = "none",
) -> PaperOrderAuthorizationStatus:
    return PaperOrderAuthorizationStatus(
        authorized=authorized,
        message=message,
        path=path,
        content_hash=_canonical_hash(payload) if payload is not None else None,
        payload=payload or {},
        details=details or {},
        kind=kind,
    )


def _read_json(path: Path) -> dict[str, Any]:
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"authorization path cannot contain symlinks: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f"authorization artifact must be an unaliased regular file: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            payload = json.load(handle)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_ref(root: Path, value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else root / path


def _normalize_hash(value: Any) -> str:
    return str(value or "").removeprefix("sha256:").strip()


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field}_invalid")
    return parsed.astimezone(UTC)


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return value.astimezone(UTC)


def _meaningful(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
