"""Snapshot/restore of one book's reservations, receipts and evidence.

One complete snapshot holds cash/lots/rights, pending reservations, consumed IDs
and separately typed fill/fee provenance. The six-policy service stores these
snapshots inside its own atomic runtime state.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path

from open_composer.intraday_runner.source_dispatch_journal import _canonical
from open_composer.intraday_runner.source_method_bindings import source_module
from open_composer.intraday_runner.source_reservations import SourceReservations


def snapshot(state: SourceReservations, fills: dict, fees: dict, *, evidence: dict) -> dict:
    """Copy all state; fee IDs share the legacy applied_fill_ids namespace."""
    if set(vars(state)) != {"cashbook", "pending", "consumed_ids", "applied_fill_ids"}:
        raise ValueError("unhandled reservation state fields")
    value = {
        "cashbook": asdict(state.cashbook),
        "pending": copy.deepcopy(state.pending),
        "consumed_ids": sorted(state.consumed_ids),
        "applied_fill_ids": sorted(state.applied_fill_ids),
        "fills": copy.deepcopy(fills),
        "fees": copy.deepcopy(fees),
        "evidence": copy.deepcopy(evidence),
    }
    _validate(value)
    return json.loads(_canonical(value))


def _validate(value: dict) -> None:
    if set(value) != {
        "cashbook",
        "pending",
        "consumed_ids",
        "applied_fill_ids",
        "fills",
        "fees",
        "evidence",
    }:
        raise ValueError("incomplete checkpoint fields")
    if set(value["cashbook"]) != {"cash", "sales", "purchases", "dividends", "lots", "next_id"}:
        raise ValueError("unhandled cashbook fields")
    for key in ("consumed_ids", "applied_fill_ids"):
        ids = value[key]
        if not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids):
            raise ValueError("invalid checkpoint IDs")
        if ids != sorted(set(ids)):
            raise ValueError("duplicate or noncanonical checkpoint IDs")
    for key in ("pending", "fills", "fees", "evidence"):
        if not isinstance(value[key], dict):
            raise ValueError("invalid checkpoint map")
    fills, fees = value["fills"], value["fees"]
    if set(fills) & set(fees) or set(fills) | set(fees) != set(value["applied_fill_ids"]):
        raise ValueError("typed receipt maps and applied IDs disagree")
    if not set(value["pending"]) <= set(value["consumed_ids"]):
        raise ValueError("pending order lacks consumed ID")
    for row in (*fills.values(), *fees.values()):
        if not isinstance(row, dict) or row.get("client_order_id") not in value["consumed_ids"]:
            raise ValueError("receipt lacks consumed own intent")


def restore(root: Path, value: dict) -> tuple[SourceReservations, dict, dict, dict]:
    """Snapshots were checked when written; restore only copies them back."""
    v = copy.deepcopy(value)
    return (
        SourceReservations(
            source_module(root, "cash").CashState(**v["cashbook"]),
            pending=v["pending"],
            consumed_ids=set(v["consumed_ids"]),
            applied_fill_ids=set(v["applied_fill_ids"]),
        ),
        v["fills"],
        v["fees"],
        v["evidence"],
    )
