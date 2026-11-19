"""Two DAY-market legs for a book order that flips a position between long and short.

Alpaca does not flip a position in one order, so the close leg is sent first, observed briefly
until it is filled, and only then is the opening leg sent.  Anything not confirmed is deferred to
the submission receipt; the deterministic leg ids make a rerun skip what the broker already has.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Any

from open_composer.book_paper.plan import OrderLookup, _text, broker_error_text

# Bounded within the existing submit invocation; pending work remains in its receipt.
CLOSE_OBSERVATIONS = 5
CLOSE_POLL_SECONDS = 1.0
TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced", "done_for_day"}


def reversal_legs(order: dict[str, Any]) -> list[dict[str, Any]]:
    current, post = float(order.get("current_qty", 0)), float(order.get("post_qty", 0))
    if current * post >= 0:
        return []
    parent = order["client_order_id"]
    return [
        {
            **order,
            "qty": abs(qty),
            "stage": stage,
            "logical_client_order_id": parent,
            "client_order_id": "bk1-"
            + hashlib.sha256(f"{parent}|{stage}".encode()).hexdigest()[:40],
        }
        for stage, qty in (("close", current), ("open", post))
    ]


def _leg_state(order: Any, leg: dict[str, Any]) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "client_order_id": leg["client_order_id"],
        "stage": leg["stage"],
        "qty": leg["qty"],
        "filled_qty": float(getattr(order, "filled_qty", 0) or 0),
        "filled_avg_price": getattr(order, "filled_avg_price", None),
        "status": _text(getattr(order, "status", "")),
    }


def _filled(state: dict[str, Any] | None, leg: dict[str, Any]) -> bool:
    return state is not None and state["status"] == "filled" and state["filled_qty"] == leg["qty"]


def submit_reversal(
    order: dict[str, Any],
    *,
    lookup: OrderLookup,
    send: Callable[[dict[str, Any]], Any],
    guard: Callable[[], None],
    report: dict[str, Any],
    pace_seconds: float,
) -> None:
    close, opening = reversal_legs(order)
    row: dict[str, Any] = {
        "symbol": order["symbol"],
        "client_order_id": order["client_order_id"],
        "current_qty": order["current_qty"],
        "target_qty": order["post_qty"],
        "status": "pending",
        "legs": [],
    }
    report["reversals"].append(row)

    def defer(reason: str) -> None:
        row.update(status="deferred", reason=reason)
        report["deferred"].append(
            {
                "symbol": order["symbol"],
                "client_order_id": order["client_order_id"],
                "reason": reason,
            }
        )

    def observe(leg: dict[str, Any]) -> dict[str, Any] | None:
        if pace_seconds > 0:
            time.sleep(pace_seconds)
        state = _leg_state(lookup.find(leg["client_order_id"], fresh=True), leg)
        row["legs"] = [e for e in row["legs"] if e["stage"] != leg["stage"]]
        if state is not None:
            row["legs"].append(state)
        return state

    def settle(opened: dict[str, Any] | None) -> None:
        if _filled(opened, opening):
            row["status"] = "filled"
        elif opened is not None and opened["status"] in TERMINAL:
            defer(f"opening leg {opened['status']}")
        else:
            # An accepted DAY market order fills in the session; reconcile confirms it.
            row["status"] = "sent"

    if report["time_in_force"] != "day":
        defer("staged reversal needs DAY orders; CLS reversal not sent")
        return
    try:
        if (opened := observe(opening)) is not None:
            report["skipped_existing"].append(
                {
                    "symbol": order["symbol"],
                    "client_order_id": opening["client_order_id"],
                    "reason": "opening leg at broker",
                }
            )
            settle(opened)
            return
        if observe(close) is None:
            guard()
            if send(close) is None:
                defer("close submission not acknowledged; opening deferred")
                return
        # Accepted != filled: observe the close before opening.
        for attempt in range(CLOSE_OBSERVATIONS):
            closed = observe(close)
            if closed is not None and closed["status"] in TERMINAL:
                break
            if attempt + 1 < CLOSE_OBSERVATIONS:
                time.sleep(CLOSE_POLL_SECONDS)
        if not _filled(closed, close):
            defer("close not confirmed fully filled; opening deferred")
            return
        guard()
        if send(opening) is None:
            defer("opening submission not acknowledged; reconciliation required")
            return
        settle(observe(opening))
    except Exception as exc:
        defer(f"{exc.__class__.__name__}: {broker_error_text(exc)}")
