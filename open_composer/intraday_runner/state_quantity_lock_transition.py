"""The October STATE AAPL sell whose share lock was retired on 2026-10-26.

The one-time capture and transition that retired it have completed; the native
checkpoint keeps its marker. A late broker observation of that order is accepted
only as a matching zero-fill terminal; anything else blocks its book.
"""

from __future__ import annotations

from open_composer.intraday_runner.source_dispatch_journal import classify_own_order

CID = "six-53ee69b0f53f4186bf6593b7b133ed0a41d1"
BOOK = "BASE_STATE_BUDGET"
KIND = "received_current_STATE_share_lock_retirement_v1"


def retired(cid, record):
    """The order carries the retired share-lock marker, never a terminal status."""
    proof = record.get("current_quantity_lock_reconciliation")
    return cid == CID and isinstance(proof, dict) and proof.get("kind") == KIND


def receive_retired_late_order(cid, record, observed):
    """Only full matching zero-fill terminal facts may enter the legacy path."""
    if not isinstance(observed, dict):
        raise ValueError("late order observation is not an object")
    original = record["current_quantity_lock_reconciliation"]["original_order"]
    for key in ("book", "symbol", "side", "qty", "limit_price"):
        if record[key] != original[key]:
            raise ValueError("retained original request differs from current order")
    request = dict(
        client_order_id=cid,
        symbol=original["symbol"],
        side=original["side"],
        qty=original["qty"],
        limit_price=original["limit_price"],
        type="limit",
        time_in_force="day",
    )
    fact = classify_own_order(request, observed)
    for prior in (original.get("observation"), record.get("observation")):
        if prior is not None and (
            not isinstance(prior, dict) or prior.get("id") != fact["broker_order_id"]
        ):
            raise ValueError("late broker identity differs from received identity")
    if not fact["terminal_observed"] or fact["cumulative_filled"] != 0:
        raise ValueError("late active or executed order conflicts with retired share lock")
    return fact
