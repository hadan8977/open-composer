from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from open_composer.models.strategy_spec import StrategySpec

ORDERABLE_PAPER_STYLES = {
    "day_market": "day",
    "loo_limit": "opg",
    "moo_market": "opg",
    "opg_limit": "opg",
}


@dataclass(frozen=True)
class ExecutionPolicyBinding:
    policy_id: str
    content_hash: str
    payload: dict[str, Any]
    source: str


def resolve_execution_policy(
    spec: StrategySpec,
    root: Path,
) -> ExecutionPolicyBinding | None:
    if spec.execution_policy is not None:
        payload = spec.execution_policy.model_dump(mode="json")
        source = "strategy_spec"
    else:
        path = root / "reports" / "harness" / "execution" / f"{spec.name}-execution-policy.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"execution policy is invalid JSON: {path}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"execution policy must be a JSON object: {path}")
        payload = raw
        source = path.as_posix()

    policy_id = payload.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id.strip():
        raise ValueError("execution policy requires a non-empty policy_id")
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return ExecutionPolicyBinding(
        policy_id=policy_id.strip(),
        content_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        payload=payload,
        source=source,
    )


def require_orderable_execution_policy(
    spec: StrategySpec,
    root: Path,
) -> ExecutionPolicyBinding:
    binding = resolve_execution_policy(spec, root)
    if binding is None:
        raise ValueError("paper order submission requires an explicit execution policy")
    payload = binding.payload
    if payload.get("execution_authorized") is False:
        raise ValueError("execution policy explicitly marks order execution unauthorized")
    order_style = str(payload.get("order_style") or "").strip().lower()
    if order_style not in ORDERABLE_PAPER_STYLES:
        raise ValueError(f"unsupported paper order_style: {order_style or 'missing'}")
    expected_tif = ORDERABLE_PAPER_STYLES[order_style]
    actual_tif = str(payload.get("time_in_force") or "").strip().lower()
    if actual_tif != expected_tif:
        raise ValueError(
            f"order_style={order_style} requires time_in_force={expected_tif}; "
            f"received {actual_tif or 'missing'}"
        )
    if (
        order_style == "day_market"
        and not str(payload.get("naked_market_justification") or "").strip()
    ):
        raise ValueError("day_market execution requires naked_market_justification")
    return binding
