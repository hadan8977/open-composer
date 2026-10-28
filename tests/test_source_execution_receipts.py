"""Invented captured FILL fixtures; no account/provider/API calls or strategy replay."""

import copy
import hashlib
import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from open_composer.intraday_runner.source_dispatch_journal import _hash
from open_composer.intraday_runner.source_execution_receipts import apply_bound_fill
from open_composer.intraday_runner.source_method_bindings import source_module
from open_composer.intraday_runner.source_reservations import SourceReservations

CID = "dia-base-2026-11-03-sell-AAPL"


@pytest.fixture
def case(tmp_path, monkeypatch):
    def deny(*a, **k):
        raise AssertionError("no network in receipt fixture")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    root = tmp_path
    state = SourceReservations(
        source_module(Path(root), "cash").CashState(
            cash=100,
            lots={"AAPL": [{"quantity": 10, "funded": "2026-10-19"}]},
        )
    )
    reservation = state.reserve_sell(
        CID, "AAPL", 6, 10.0, "2026-11-03", "2026-11-04", fee_buffer_rate=0.001
    )
    request = dict(
        client_order_id=CID,
        symbol="AAPL",
        side="sell",
        qty=6,
        type="limit",
        time_in_force="day",
        limit_price=10.0,
        reservation=reservation,
    )
    ack = {
        **{k: v for k, v in request.items() if k != "reservation"},
        "id": "owned-broker-id",
        "status": "new",
        "filled_qty": "0",
    }
    journal = dict(
        client_order_id=CID,
        request=request,
        request_sha256=_hash(request),
        stage="transport_returned_reconciliation_required",
        observations=[ack],
        dispatch_created_at="2026-11-03T14:35:00Z",
    )
    event = dict(
        id="activity-1",
        activity_type="FILL",
        type="partial_fill",
        order_id="owned-broker-id",
        symbol="AAPL",
        side="sell",
        qty="2",
        price="10.1",
        cum_qty="2",
        transaction_time="2026-11-03T14:35:01Z",
    )
    sequence = []

    def binding(p):
        raw = p.read_bytes()
        return dict(path=str(p), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

    def capture(events, **changes):
        sequence.append(1)
        body = tmp_path / f"body-{len(sequence)}.json"
        body.write_text(json.dumps(events))
        receipt = dict(
            method="GET",
            endpoint_kind="account_activities",
            status=200,
            account_hash="a" * 64,
            received_at="2026-11-03T14:35:02Z",
            body=binding(body),
        )
        receipt.update(changes)
        path = tmp_path / f"capture-{len(sequence)}.json"
        path.write_text(json.dumps(receipt))
        return binding(path)

    args = dict(
        root=Path(root),
        state=state,
        applied_records={},
        receipt_binding=capture([event]),
        ordinal=0,
        journal_record=journal,
        expected_account_hash="a" * 64,
        observed_now=datetime(2026, 11, 3, 14, 35, 3, tzinfo=UTC),
    )
    return args, event, capture


def test_partial_execution_uses_delta_once_without_fee_or_release(case):
    args, _, _ = case
    state, receipts, result = apply_bound_fill(**args)
    assert args["state"].cashbook.quantity("AAPL") == 10
    assert state.cashbook.quantity("AAPL") == 8 and state.pending[CID]["filled"] == 2
    assert state.cashbook.sales[0]["amount"] == pytest.approx(20.2)
    assert not result["fees_reconciled"] and not result["reservation_released"]
    assert receipts["activity-1"]["journal_snapshot"] == args["journal_record"]
    same, same_receipts, duplicate = apply_bound_fill(
        **{**args, "state": state, "applied_records": receipts}
    )
    assert same == state and same_receipts == receipts and duplicate["status"] == "already_applied"


def test_next_actual_delta_is_not_cumulative_quantity_as_another_fill(case):
    args, event, capture = case
    state, receipts, _ = apply_bound_fill(**args)
    event.update(id="activity-2", qty="4", cum_qty="6", type="fill")
    state, receipts, _ = apply_bound_fill(
        **{**args, "state": state, "applied_records": receipts, "receipt_binding": capture([event])}
    )
    assert state.cashbook.quantity("AAPL") == 4 and state.pending[CID]["filled"] == 6
    assert sum(s["amount"] for s in state.cashbook.sales) == pytest.approx(60.6)
    assert len(receipts) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"order_id": "foreign"},
        {"symbol": "MSFT"},
        {"side": "buy"},
        {"activity_type": "FEE"},
        {"qty": "0"},
        {"qty": "1.5"},
        {"price": "NaN"},
        {"cum_qty": "3"},
        {"price": "9.99"},
    ],
)
def test_bad_or_unmatched_execution_preserves_original_state(case, change):
    args, event, capture = case
    before = copy.deepcopy(args["state"])
    args["receipt_binding"] = capture([{**event, **change}])
    with pytest.raises(ValueError):
        apply_bound_fill(**args)
    assert args["state"] == before and args["applied_records"] == {}


def test_same_id_with_changed_payload_or_inconsistent_checkpoint_blocks(case):
    args, event, capture = case
    state, receipts, _ = apply_bound_fill(**args)
    altered = capture([{**event, "price": "10.2"}])
    with pytest.raises(ValueError, match="ID changed"):
        apply_bound_fill(
            **{**args, "state": state, "applied_records": receipts, "receipt_binding": altered}
        )
    with pytest.raises(ValueError, match="checkpoint is inconsistent"):
        apply_bound_fill(**{**args, "applied_records": receipts})
    with pytest.raises(ValueError, match="missing receipt map"):
        apply_bound_fill(**{**args, "state": state})


@pytest.mark.parametrize(
    "capture_change",
    [
        {"account_hash": "b" * 64},
        {"method": "POST"},
        {"status": 401},
        {"received_at": "2026-11-03T14:35:04Z"},
    ],
)
def test_capture_identity_and_actual_clock_are_not_implicit(case, capture_change):
    args, event, capture = case
    args["receipt_binding"] = capture([event], **capture_change)
    with pytest.raises(ValueError):
        apply_bound_fill(**args)


def test_changed_bound_body_does_not_apply(case):
    args, _, _ = case
    receipt = json.loads(Path(args["receipt_binding"]["path"]).read_text())
    Path(receipt["body"]["path"]).write_text("[]")
    with pytest.raises(ValueError, match="hash changed"):
        apply_bound_fill(**args)


@pytest.mark.parametrize("change", ["request", "stage"])
def test_unlinked_or_known_not_dispatched_journal_cannot_supply_a_fill(case, change):
    args, _, _ = case
    if change == "request":
        args["journal_record"]["request"]["limit_price"] = 9.9
    else:
        args["journal_record"]["stage"] = "not_dispatched_guard_refusal"
    with pytest.raises(ValueError, match="acknowledged order linkage"):
        apply_bound_fill(**args)
    assert args["state"].pending[CID]["filled"] == 0


def test_late_processed_receipt_does_not_unlock_later_funded_lots(case):
    args, event, capture = case
    # Originally six shares were funded when the earlier DAY sell was reserved.
    args["state"].cashbook.lots["AAPL"] = [
        {"quantity": 2, "funded": "2026-11-04"},
        {"quantity": 6, "funded": "2026-10-19"},
    ]
    event.update(transaction_time="2026-11-04T14:35:01Z")
    args.update(
        receipt_binding=capture([event], received_at="2026-11-04T14:35:02Z"),
        observed_now=datetime(2026, 11, 4, 14, 35, 3, tzinfo=UTC),
    )
    state, _, _ = apply_bound_fill(**args)
    assert state.cashbook.lots["AAPL"][0] == {"quantity": 2, "funded": "2026-11-04"}
    assert state.cashbook.lots["AAPL"][1]["quantity"] == 4


@pytest.mark.parametrize(
    "key,value",
    [("symbol", "MSFT"), ("limit_price", 9.0), ("due", "2026-11-05"), ("filled", False)],
)
def test_pending_identity_cannot_be_rebound_while_receiving_a_fill(case, key, value):
    args, _, _ = case
    args["state"].pending[CID][key] = value
    before = copy.deepcopy(args["state"])
    with pytest.raises(ValueError, match="reservation differs"):
        apply_bound_fill(**args)
    assert args["state"] == before
