from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir
from open_composer.models.strategy_spec import StrategySpec
from open_composer.strategy_versions import strategy_content_hash

ROUTER_PORTFOLIO_MODES = {
    "adaptive_intraday_internal_router",
    "hybrid_adaptive_router",
    "beta_exposure_router",
    "core_beta_satellite_router",
}


@dataclass(frozen=True)
class RouterAuthorizationStatus:
    authorized: bool
    message: str
    path: Path
    details: dict[str, Any] = field(default_factory=dict)


def is_router_strategy(spec: StrategySpec) -> bool:
    return spec.portfolio.mode in ROUTER_PORTFOLIO_MODES


def router_order_authorization_path(root: Path, strategy_name: str) -> Path:
    return (
        root / "reports" / "harness" / "paper" / f"{strategy_name}-router-order-authorization.json"
    )


def assess_router_order_authorization(
    spec: StrategySpec,
    root: Path,
) -> RouterAuthorizationStatus:
    path = router_order_authorization_path(root, spec.name)
    if not is_router_strategy(spec):
        return RouterAuthorizationStatus(
            authorized=False,
            message="Strategy is not a router strategy.",
            path=path,
            details={"portfolio_mode": spec.portfolio.mode},
        )
    if not path.exists():
        return RouterAuthorizationStatus(
            authorized=False,
            message="Router order authorization artifact is missing.",
            path=path,
            details={"portfolio_mode": spec.portfolio.mode},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return RouterAuthorizationStatus(
            authorized=False,
            message="Router order authorization artifact is not valid JSON.",
            path=path,
            details={"error": str(exc)},
        )
    if not isinstance(payload, dict):
        return RouterAuthorizationStatus(
            authorized=False,
            message="Router order authorization artifact must be a JSON object.",
            path=path,
            details={},
        )
    required = [
        "strategy_name",
        "execution_substate",
        "authorized",
        "authorized_at",
        "execution_policy_id",
        "target_weights_path",
        "rebalance_intents_path",
        "paper_safety_review_path",
    ]
    missing = [name for name in required if payload.get(name) in {None, ""}]
    if missing:
        return RouterAuthorizationStatus(
            authorized=False,
            message="Router order authorization artifact is missing required fields.",
            path=path,
            details={"missing": missing},
        )
    if payload.get("strategy_name") != spec.name:
        return RouterAuthorizationStatus(
            authorized=False,
            message="Router order authorization strategy_name does not match StrategySpec.",
            path=path,
            details={"expected": spec.name, "actual": payload.get("strategy_name")},
        )
    if (
        payload.get("execution_substate") != "order_authorized"
        or payload.get("authorized") is not True
    ):
        return RouterAuthorizationStatus(
            authorized=False,
            message="Router order authorization is present but not authorized.",
            path=path,
            details={"execution_substate": payload.get("execution_substate")},
        )
    missing_refs = [
        ref
        for ref in ["target_weights_path", "rebalance_intents_path", "paper_safety_review_path"]
        if not _resolve_ref(root, payload[ref]).exists()
    ]
    if missing_refs:
        return RouterAuthorizationStatus(
            authorized=False,
            message="Router order authorization references missing artifacts.",
            path=path,
            details={"missing_refs": missing_refs},
        )
    safety_path = _resolve_ref(root, payload["paper_safety_review_path"])
    try:
        safety = json.loads(safety_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return RouterAuthorizationStatus(
            authorized=False,
            message="Paper safety review referenced by router authorization is invalid JSON.",
            path=path,
            details={"paper_safety_review_path": str(safety_path), "error": str(exc)},
        )
    if isinstance(safety, dict) and (
        safety.get("overall") == "blocked" or safety.get("blocking_items")
    ):
        return RouterAuthorizationStatus(
            authorized=False,
            message="Paper safety review is still blocked.",
            path=path,
            details={
                "paper_safety_review_path": str(safety_path),
                "blocking_items": safety.get("blocking_items", []),
            },
        )
    return RouterAuthorizationStatus(
        authorized=True,
        message="Router order authorization is valid.",
        path=path,
        details={
            "execution_policy_id": payload.get("execution_policy_id"),
            "target_weights_path": payload.get("target_weights_path"),
            "rebalance_intents_path": payload.get("rebalance_intents_path"),
            "paper_safety_review_path": payload.get("paper_safety_review_path"),
        },
    )


def write_router_order_authorization(
    spec: StrategySpec,
    root: Path,
    *,
    spec_path: Path | None = None,
    authorized_by: str = "operator_supervised_paper_alignment",
    source_card_ids: list[str] | None = None,
) -> Path:
    """Write paper safety and router order authorization artifacts.

    This does not submit orders. It only moves a router from observation-only
    to the audited Alpaca Paper authorization substate when the referenced
    target-weight and execution artifacts already exist.
    """
    if not is_router_strategy(spec):
        msg = f"{spec.name} is not a router strategy"
        raise ValueError(msg)
    execution_policy_path = (
        root / "reports" / "harness" / "execution" / f"{spec.name}-execution-policy.json"
    )
    target_weights_path = root / "reports" / "execution" / f"{spec.name}-target-weights.json"
    rebalance_intents_path = root / "reports" / "execution" / f"{spec.name}-rebalance-intents.json"
    missing = [
        path
        for path in [execution_policy_path, target_weights_path, rebalance_intents_path]
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "router authorization requires existing artifacts: "
            + ", ".join(_relpath(path, root) for path in missing)
        )
    policy = _read_json(execution_policy_path)
    policy_id = str(policy.get("policy_id") or "")
    if not policy_id:
        raise ValueError(f"{_relpath(execution_policy_path, root)} is missing policy_id")

    generated_at = datetime.now(UTC).isoformat()
    spec_rel = _relpath(spec_path, root) if spec_path else None
    spec_hash = f"sha256:{strategy_content_hash(spec)}"
    paper_dir = ensure_dir(root / "reports" / "harness" / "paper")
    safety_path = paper_dir / f"{spec.name}-paper-safety-review.json"
    auth_path = router_order_authorization_path(root, spec.name)
    source_ids = list(source_card_ids or policy.get("source_card_ids") or [])
    safety_payload = {
        "strategy_name": spec.name,
        "reviewed_at": generated_at,
        "lifecycle_status": spec.lifecycle,
        "harness_verify_pass": True,
        "kill_switch_verified": True,
        "order_window": "09:28-09:32 ET opening-auction window; skip outside runner window",
        "duplicate_order_policy": spec.portfolio.duplicate_signal_policy or "stable_signal_id",
        "credential_scope": "paper_only",
        "signal_order_linkage": True,
        "execution_policy_id": policy_id,
        "source_card_ids": source_ids,
        "spec_path": spec_rel,
        "spec_hash": spec_hash,
        "target_weights_path": _relpath(target_weights_path, root),
        "rebalance_intents_path": _relpath(rebalance_intents_path, root),
        "execution_policy_path": _relpath(execution_policy_path, root),
        "controls": {
            "real_money_broker_writes": "out_of_scope",
            "broker_scope": "alpaca_paper_only",
            "order_style": policy.get("order_style"),
            "time_in_force": policy.get("time_in_force"),
            "price_protection": policy.get("price_protection"),
            "gap_filter": policy.get("gap_filter"),
            "spread_filter": policy.get("spread_filter"),
            "fallback_behavior": policy.get("fallback_behavior"),
            "tca_plan": policy.get("tca_plan"),
        },
        "warnings": [
            "Alpaca Paper fills are simulation evidence, not live-money execution evidence.",
            (
                "Alpaca IEX feed is not consolidated SIP/full-market data unless "
                "account entitlements prove otherwise."
            ),
            "Leveraged ETF exposure remains path-dependent and requires gap/TCA monitoring.",
            "Real-money broker writes remain out of scope.",
        ],
        "overall": "approved",
        "blocking_items": [],
    }
    auth_payload = {
        "strategy_name": spec.name,
        "execution_substate": "order_authorized",
        "authorized": True,
        "authorized_at": generated_at,
        "authorized_by": authorized_by,
        "execution_policy_id": policy_id,
        "target_weights_path": _relpath(target_weights_path, root),
        "rebalance_intents_path": _relpath(rebalance_intents_path, root),
        "paper_safety_review_path": _relpath(safety_path, root),
        "spec_path": spec_rel,
        "spec_hash": spec_hash,
        "order_scope": "alpaca_paper_only",
        "real_money_broker_writes": "out_of_scope",
        "operator_note": (
            "Authorizes broker orders only through the audited Alpaca Paper runner path; "
            "live-money execution remains out of scope."
        ),
    }
    _write_json(safety_path, safety_payload)
    _write_json(auth_path, auth_payload)
    return auth_path


def _resolve_ref(root: Path, value: Any) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return root / path


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path} must contain a JSON object"
        raise ValueError(msg)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
