"""Funding eligibility from actual fill capture and completed checkpoint clocks.

Excluded proceeds remain real AR/positions. Only their temporary reservable
amount is zeroed; restoration never replaces the whole mutated cashbook.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

from open_composer.intraday_runner.source_dispatch_journal import _hash
from open_composer.intraday_runner.source_state_checkpoint import restore


def _clock(value):
    if not isinstance(value, str) or re.search(r"\.\d{7,}", value):
        raise ValueError("funding clock precision must not truncate a late instant")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("missing funding clock timezone")
    return t


def application_path(directory: Path, fill_id: str):
    return directory / "applications" / (hashlib.sha256(fill_id.encode()).hexdigest() + ".json")


def eligible_reservation_copy(root, store, revision, cutoff):
    state, fills, fees, evidence = restore(root, revision["snapshot"])
    excluded = {}
    origins = evidence.get("sale_origins", {})
    for sale in state.cashbook.sales:
        try:
            origin = origins[sale["id"]]
            fid = origin["fill_id"]
            record = fills[fid]
            first = store._read(store._revision(origin["generation"]))
            origin_sale = next(
                s for s in first["snapshot"]["cashbook"]["sales"] if s["id"] == sale["id"]
            )
            if (
                first["snapshot"]["fills"][fid] != record
                or origin_sale["amount"] != sale["amount"]
                or len([o for o in origins.values() if o["fill_id"] == fid]) != 1
            ):
                raise ValueError("sale delta identity changed")
        except (KeyError, TypeError, FileNotFoundError, StopIteration) as exc:
            raise ValueError(
                "unresolved actual sale/quantity lineage; zeroing AR is not reconciliation"
            ) from exc
        path = application_path(store.directory, fid)
        valid = False
        if path.exists():
            proof = json.loads(path.read_text())
            if (
                proof.get("fill_id") != fid
                or proof.get("sale_id") != sale["id"]
                or proof.get("revision_sha256") != _hash(first)
                or proof.get("receipt_record_sha256") != _hash(record)
            ):
                raise ValueError("contradictory actual application proof")
            valid = (
                _clock(record["received_at"]) <= _clock(proof["checkpoint_completed_at"]) <= cutoff
            )
        if not valid:
            excluded[sale["id"]] = sale["unreserved"]
            sale["unreserved"] = 0.0
    return state, fills, fees, evidence, excluded


def restore_excluded_proceeds(before, prepared, excluded):
    """Restore only excluded entries, preserving every eligible decrement/new lock."""
    result = copy.deepcopy(prepared)
    if (
        result.cashbook.purchases != before.cashbook.purchases
        or result.cashbook.lots != before.cashbook.lots
        or result.cashbook.dividends != before.cashbook.dividends
        or result.cashbook.cash != before.cashbook.cash
    ):
        raise ValueError("reservation preparation unexpectedly changed economic holdings/cash")
    old = {s["id"]: s for s in before.cashbook.sales}
    if (
        len(old) != len(before.cashbook.sales)
        or len(result.cashbook.sales) != len(old)
        or {s["id"] for s in result.cashbook.sales} != set(old)
    ):
        raise ValueError("reservation preparation changed AR identities")
    if any(k not in old or v != old[k]["unreserved"] for k, v in excluded.items()):
        raise ValueError("excluded restoration differs from original unavailable proceeds")
    if any(result.pending.get(cid) != row for cid, row in before.pending.items()):
        raise ValueError("reservation preparation released or changed an old liability")
    for cid, row in result.pending.items():
        # An unchanged SELL fee encumbrance is an old liability, not new BUY
        # funding. Keep even zero-valued source records and their provenance.
        old_pending = before.pending.get(cid)
        unchanged_sell_liability = (
            row.get("side") in {"sell", "liability_hold"} and old_pending == row
        )
        if not unchanged_sell_liability and any(
            p["source"] in excluded
            for key in ("original_funding", "remaining_funding")
            for p in row.get(key, [])
        ):
            raise ValueError("unproven/late proceeds entered new or changed funding")
    for sale in result.cashbook.sales:
        if {k: v for k, v in sale.items() if k != "unreserved"} != {
            k: v for k, v in old[sale["id"]].items() if k != "unreserved"
        }:
            raise ValueError("AR economics changed during reservation")
        if sale["id"] in excluded:
            if sale["unreserved"] != 0:
                raise ValueError("excluded AR was unexpectedly changed")
            sale["unreserved"] = excluded[sale["id"]]

    def reserved(state, source):
        parts = [
            p["amount"]
            for row in state.pending.values()
            for p in row.get("remaining_funding", [])
            if p["source"] == source
        ]
        if any(not math.isfinite(x) or x < 0 for x in parts):
            raise ValueError("invalid spendable reservation")
        return sum(parts)

    for sale in result.cashbook.sales:
        sid = sale["id"]
        if not math.isfinite(sale["unreserved"]) or sale["unreserved"] < 0:
            raise ValueError("invalid unreserved proceeds")
        if not math.isclose(
            old[sid]["unreserved"] + reserved(before, sid),
            sale["unreserved"] + reserved(result, sid),
            rel_tol=0,
            abs_tol=1e-7,
        ):
            raise ValueError("sale reservation conservation failed")
    if reserved(result, "cash") > result.cashbook.free_cash() + 1e-7:
        raise ValueError("cash reservation conservation failed")
    return result
