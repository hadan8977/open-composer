"""Apply one bound account FILL activity to the accepted own-sleeve cashbook.

No client, source fetch, fee inference or account authorization. The caller must
first capture a verified account's actual GET response and persist the returned
cashbook plus receipt map together under its existing account lock. This pure
transition is not that durable global checkpoint or a live input certificate.
Any rejected record is an unresolved real position/liability for the caller to
halt and reconcile, never evidence that the recorded trade did not happen.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from open_composer.intraday_runner.source_dispatch_journal import _hash, classify_own_order
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.source_reservations import SourceReservations
from open_composer.market_sessions import NEW_YORK


def _clock(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("actual activity/receipt clocks must be aware")
    return parsed.astimezone(UTC)


def _number(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid execution number") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError("nonpositive or nonfinite execution number")
    return number


def apply_bound_fill(
    root: Path,
    state: SourceReservations,
    applied_records: dict[str, dict],
    *,
    receipt_binding: dict,
    ordinal: int,
    journal_record: dict,
    expected_account_hash: str,
    observed_now: datetime | None = None,
) -> tuple[SourceReservations, dict, dict]:
    """Use execution qty, never cumulative snapshot qty or a requested sale.

    Responses are captured as a JSON list. The small capture receipt contains
    method, endpoint_kind, status, account_hash, received_at and a raw body hash.
    The capture/authenticated gateway remains an independently reviewed runtime
    dependency; hashes alone cannot establish broker provenance.
    """
    if not isinstance(expected_account_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_account_hash
    ):
        raise ValueError("verified expected account identity required")
    receipt = json.loads(bound_bytes(root, receipt_binding))
    if (
        receipt.get("method") != "GET"
        or receipt.get("endpoint_kind") != "account_activities"
        or receipt.get("status") != 200
        or receipt.get("account_hash") != expected_account_hash
    ):
        raise ValueError("activity capture does not match verified account/route")
    payload = json.loads(bound_bytes(root, receipt["body"]))
    if not isinstance(payload, list) or type(ordinal) is not int or not 0 <= ordinal < len(payload):
        raise ValueError("missing actual activity ordinal")
    event = payload[ordinal]
    if (
        not isinstance(event, dict)
        or event.get("activity_type") != "FILL"
        or event.get("type") not in {"fill", "partial_fill"}
    ):
        raise ValueError("not an execution FILL; generic fees/receivables are not fills")
    activity_id = event.get("id")
    if not isinstance(activity_id, str) or not activity_id:
        raise ValueError("actual unique execution activity ID required")
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    event_hash = hashlib.sha256(canonical).hexdigest()
    now = datetime.now(UTC) if observed_now is None else observed_now
    if not isinstance(now, datetime):
        raise ValueError("receipt application clock must be a datetime")
    if now.tzinfo is None:
        raise ValueError("receipt application clock must be aware")
    trade_at = _clock(event["transaction_time"])
    received = _clock(receipt["received_at"])
    if not _clock(journal_record["dispatch_created_at"]) <= trade_at <= received <= now:
        raise ValueError("execution/receipt clock outside actual causal chain")
    request = journal_record["request"]
    cid = request["client_order_id"]
    if (
        journal_record["client_order_id"] != cid
        or _hash(request) != journal_record["request_sha256"]
        or journal_record["stage"]
        not in {
            "dispatch_boundary_consumed_ack_unknown",
            "transport_returned_reconciliation_required",
        }
        or not journal_record["observations"]
    ):
        raise ValueError("missing owned acknowledged order linkage")
    order = classify_own_order(request, journal_record["observations"][-1])
    if any(
        event.get(field) != expected
        for field, expected in (
            ("order_id", order["broker_order_id"]),
            ("symbol", request["symbol"]),
            ("side", request["side"]),
        )
    ):
        raise ValueError("activity belongs to a different order or position")
    if activity_id in applied_records:
        old = applied_records[activity_id]
        if (
            old["event_sha256"] != event_hash
            or old["client_order_id"] != cid
            or old["account_hash"] != expected_account_hash
        ):
            raise ValueError("execution ID changed; retain both raw versions and halt")
        if activity_id not in state.applied_fill_ids:
            raise ValueError("receipt/cashbook checkpoint is inconsistent")
        return copy.deepcopy(state), copy.deepcopy(applied_records), {"status": "already_applied"}
    if activity_id in state.applied_fill_ids or cid not in state.pending:
        raise ValueError("missing receipt map or pending reservation; no speculative replay")
    pending = state.pending[cid]
    original = request["reservation"]
    mutable = {"filled", "remaining_funding", "confirmed_fee_funding"}
    if (
        set(pending) != set(original)
        or any(pending[key] != value for key, value in original.items() if key not in mutable)
        or type(pending["filled"]) is not int
        or pending["filled"] < 0
    ):
        raise ValueError("cashbook reservation differs from the owned journal intent")
    qty, price, cumulative = (_number(event[k]) for k in ("qty", "price", "cum_qty"))
    if qty != qty.to_integral_value() or cumulative != cumulative.to_integral_value():
        raise ValueError("whole-share execution required")
    if int(cumulative) != state.pending[cid]["filled"] + int(qty):
        raise ValueError("missing/out-of-order execution prefix; do not infer a fill delta")
    working = copy.deepcopy(state)
    # The broker transaction processing clock is not an independent exchange
    # timestamp. A delayed receipt must not unlock a later-funded lot for an
    # earlier DAY sell. Preserve the originally committed order's funding date.
    order_day = _clock(journal_record["dispatch_created_at"]).astimezone(NEW_YORK).date()
    result = working.confirmed_fill(cid, activity_id, int(qty), float(price), order_day.isoformat())
    records = copy.deepcopy(applied_records)
    records[activity_id] = {
        "event_sha256": event_hash,
        "account_hash": expected_account_hash,
        "client_order_id": cid,
        "capture": copy.deepcopy(receipt_binding),
        "body": copy.deepcopy(receipt["body"]),
        "ordinal": ordinal,
        "transaction_time": trade_at.isoformat(),
        "received_at": received.isoformat(),
        "applied_at": now.isoformat(),
        "journal_snapshot": copy.deepcopy(journal_record),
        "timestamp_interpretation": (
            "broker processing clock, not independently certified exchange time"
        ),
    }
    return (
        working,
        records,
        {
            "status": "applied",
            "execution": result,
            "fees_reconciled": False,
            "reservation_released": False,
        },
    )
