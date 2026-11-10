"""Two DAY-market legs for one immutable logical book order; no independent order loop."""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
from typing import Any

from open_composer.book_paper.plan import (
    BookEngineError,
    OrderLookup,
    _borrow_rejection,
    _text,
    broker_error_text,
    make_asset_lookup,
)

# Bounded within the existing submit invocation; pending work remains in its receipt.
CLOSE_OBSERVATIONS = 5
CLOSE_POLL_SECONDS = 1.0
TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced", "done_for_day"}


def reversal_legs(order: dict[str, Any]) -> list[dict[str, Any]]:
    current, post = float(order.get("current_qty", 0)), float(order.get("post_qty", 0))
    if current * post >= 0:
        return []
    sign = 1 if order["side"] == "buy" else -1
    if (
        not all(math.isfinite(q) and q.is_integer() for q in (current, post))
        or current + sign * order["qty"] != post
    ):
        raise BookEngineError("inconsistent whole-share reversal")
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


def _evidence(order: Any, expected: dict[str, Any]) -> dict[str, Any] | None:
    if order is None:
        return None
    # Deterministic IDs are also checked against the actual request, never trusted alone.
    if (
        str(order.client_order_id) != expected["client_order_id"]
        or str(order.symbol) != expected["symbol"]
        or _text(order.side) != expected["side"]
        or float(order.qty) != expected["qty"]
        or _text(order.time_in_force) != "day"
    ):
        raise BookEngineError("broker leg identity differs from frozen request")
    filled = float(getattr(order, "filled_qty", 0) or 0)
    if not math.isfinite(filled) or not 0 <= filled <= expected["qty"]:
        raise BookEngineError("invalid broker filled quantity")
    return {
        "client_order_id": expected["client_order_id"],
        "stage": expected["stage"],
        "qty": expected["qty"],
        "filled_qty": filled,
        "filled_avg_price": getattr(order, "filled_avg_price", None),
        "status": _text(getattr(order, "status", "")),
    }


def _position(client: Any, symbol: str) -> float:
    try:
        position = client.get_open_position(symbol)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            return 0.0
        raise
    qty = float(position.qty)
    if _text(getattr(position, "side", "")) == "short":
        qty = -abs(qty)
    if not math.isfinite(qty):
        raise BookEngineError("nonfinite broker position")
    return qty


def submit_reversal(
    client: Any,
    order: dict[str, Any],
    *,
    lookup: OrderLookup,
    send: Callable[[dict[str, Any]], Any],
    guard: Callable[[], None],
    report: dict[str, Any],
    save: Callable[[], None],
    pace_seconds: float,
) -> None:
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

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
        save()

    def read(call: Callable[[], Any]) -> Any:
        if pace_seconds > 0:
            time.sleep(pace_seconds)
        return call()

    def observe(leg: dict[str, Any]) -> dict[str, Any] | None:
        evidence = _evidence(read(lambda: lookup.find(leg["client_order_id"], fresh=True)), leg)
        row["legs"] = [e for e in row["legs"] if e["stage"] != leg["stage"]]
        if evidence is not None:
            row["legs"].append(evidence)
        save()
        return evidence

    def ready(expected_qty: float, *, opens_short: bool) -> None:
        account = read(client.get_account)
        if (
            _text(getattr(account, "status", "")).upper() != "ACTIVE"
            or bool(getattr(account, "trading_blocked", True))
            or (opens_short and not bool(getattr(account, "shorting_enabled", False)))
        ):
            raise BookEngineError("account no longer permits this leg")
        if opens_short:
            reason = read(lambda: _borrow_rejection(make_asset_lookup(client)(order["symbol"])))
            if reason:
                raise BookEngineError(f"short opening blocked: {reason}")
        working = read(
            lambda: client.get_orders(
                filter=GetOrdersRequest(
                    status=QueryOrderStatus.OPEN, symbols=[order["symbol"]], limit=500
                )
            )
        )
        if working:
            raise BookEngineError("existing open order on reversal symbol")
        qty = read(lambda: _position(client, order["symbol"]))
        row["last_observed_position_qty"] = qty
        if qty != expected_qty:
            raise BookEngineError(
                f"broker position changed: expected {expected_qty:g}, got {qty:g}"
            )
        guard()
        save()

    if report["time_in_force"] != "day":
        defer("staged reversal unsupported for CLS; closing-auction TIF preserved; no legs sent")
        return
    try:
        # A prior legacy single order must never be supplemented with two new orders.
        if read(lambda: lookup.find(order["client_order_id"], fresh=True)) is not None:
            defer("legacy logical order exists at broker; no staged retry")
            return
        existing_open = observe(opening)
        close_state = observe(close)
        if existing_open is not None:
            report["skipped_existing"].append(
                {
                    "symbol": order["symbol"],
                    "client_order_id": opening["client_order_id"],
                    "reason": "opening leg at broker",
                }
            )
            if (
                close_state is not None
                and close_state["status"] == "filled"
                and close_state["filled_qty"] == close["qty"]
                and existing_open["status"] == "filled"
                and existing_open["filled_qty"] == opening["qty"]
            ):
                row["status"] = "filled"
                save()
            else:
                defer("existing opening leg is incomplete or lacks complete close evidence")
            return
        if close_state is None:
            ready(order["current_qty"], opens_short=False)
            result = send(close)
            if result is None:
                defer("close submission not acknowledged; opening deferred")
                return
            # Accepted != filled. Always obtain a fresh order observation before opening.
        for attempt in range(CLOSE_OBSERVATIONS):
            close_state = observe(close)
            if close_state is not None and close_state["status"] in TERMINAL:
                break
            if attempt + 1 < CLOSE_OBSERVATIONS:
                time.sleep(CLOSE_POLL_SECONDS)
        if (
            close_state is None
            or close_state["status"] != "filled"
            or close_state["filled_qty"] != close["qty"]
        ):
            defer("close not confirmed fully filled; opening deferred")
            return
        ready(0.0, opens_short=opening["side"] == "sell")
        result = send(opening)
        if result is None:
            defer(
                "opening submission not acknowledged; flat/remaining target requires reconciliation"
            )
            return
        open_state = observe(opening)
        if (
            open_state is not None
            and open_state["status"] == "filled"
            and open_state["filled_qty"] == opening["qty"]
        ):
            row["status"] = "filled"
            save()
        else:
            defer("opening acknowledged; not confirmed fully filled; reconciliation required")
    except Exception as exc:
        defer(f"{exc.__class__.__name__}: {broker_error_text(exc)}")
