from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from open_composer.models.strategy_spec import StrategySpec

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


def _resolve_ref(root: Path, value: Any) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return root / path
