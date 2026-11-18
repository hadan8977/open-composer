"""Canonical JSON hashing and own-order classification for the six-policy service.

A broker observation is checked against the service's own request; a cumulative
quantity is never treated as a new fill, and no observation releases funds.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: dict) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def classify_own_order(request: dict, observed: dict) -> dict:
    """Validate ownership/quantities without treating cumulative qty as a new fill."""
    for field in ("client_order_id", "symbol", "side", "type", "time_in_force"):
        if observed.get(field) != request[field]:
            raise ValueError(f"broker observation does not match own {field}")
    if not isinstance(observed.get("id"), str) or not observed["id"]:
        raise ValueError("missing actual broker order identity")
    try:
        qty = Decimal(str(observed["qty"]))
        filled = Decimal(str(observed["filled_qty"]))
        limit = Decimal(str(observed["limit_price"]))
    except (KeyError, InvalidOperation) as exc:
        raise ValueError("invalid broker quantity/limit fields") from exc
    if not all(v.is_finite() for v in (qty, filled, limit)):
        raise ValueError("nonfinite broker quantity/limit")
    if qty != request["qty"] or limit != Decimal(str(request["limit_price"])):
        raise ValueError("observed quantity or limit differs from own request")
    if filled != filled.to_integral_value() or not 0 <= filled <= qty:
        raise ValueError("unreconciled nonwhole or excessive filled quantity")
    status = observed.get("status")
    terminal = status in {"filled", "canceled", "cancelled", "expired", "rejected"}
    working = status in {"new", "accepted", "pending_new", "partially_filled"}
    if not terminal and not working and status != "pending_cancel":
        raise ValueError("unknown/replaced order requires reconciliation, not new action")
    if status == "filled" and filled != qty:
        raise ValueError("filled status contradicts cumulative quantity")
    return {
        "broker_order_id": observed["id"],
        "status": status,
        "cumulative_filled": int(filled),
        "remaining": int(qty - filled),
        "terminal_observed": terminal,
        "cancel_eligible": working and filled < qty,
        "not_a_new_execution_delta": True,
        "funds_releasable": False,
    }
