"""Offline fixtures against frozen reader artifacts, never a paper activation test.

Versioned readers use private bound metadata; no external research tree is required.
No credentials, quote fetches, model fits, orders or account snapshots are used.
"""

import copy
import hashlib
import json
import socket
from datetime import UTC, datetime

import pytest

from open_composer.intraday_runner.source_method_bindings import bound_bytes, source_module
from open_composer.intraday_runner.source_method_wave import prepare_wave
from open_composer.intraday_runner.source_reservations import SourceReservations
from tests.source_method_fixtures import source_reference


def seal(commit):
    return hashlib.sha256(
        json.dumps(commit, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@pytest.fixture
def args(monkeypatch, tmp_path):
    def deny(*a, **kw):
        raise AssertionError("No network in source-method rehearsal")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    root = source_reference(tmp_path / "reference")
    cash = source_module(root, "cash").CashState
    meta = json.loads(
        (
            root
            / (
                "reports/research/program/owner-profit-delivery-plan-20261017/"
                "paper-delivery/runtime-reader-bindings.json"
            )
        ).read_text()
    )["bindings"]
    commit = {
        "formation_month_end": "2026-10-31",
        "execution_day": "2026-11-03",
        "source_cutoff": "2026-11-02T09:35:00-05:00",
        "produced_at": "2026-11-02T10:00:00-05:00",
        "committed_at": "2026-11-02T16:15:00-05:00",
        "settlement_due": "2026-11-04",
        "sell": [{"symbol": "AAPL", "max_quantity": 10}],
        "buy": [{"symbol": "MSFT", "max_quantity": 15}],
    }
    quote = {
        "t": "2026-11-03T14:35:00Z",
        "bp": 10.0,
        "ap": 10.1,
        "bs": 6,
        "as": 30,
        "bx": "Q",
        "ax": "Q",
        "z": "C",
        "c": ["R", "R"],
    }
    ref = {
        "session_date": "2026-11-02",
        "close": 10.0,
        "hygiene_valid": True,
        "split_session": False,
        "completed_before_execution": True,
    }
    return dict(
        root=root,
        metadata_bindings=meta,
        state=SourceReservations(
            cash(
                cash=100,
                lots={
                    "AAPL": [{"quantity": 10, "funded": "2026-10-19"}],
                },
            )
        ),
        commit=commit,
        commit_sha256=seal(commit),
        universe={"AAPL", "MSFT"},
        now=datetime(2026, 11, 3, 14, 35, tzinfo=UTC),
        side="sell",
        authorized_at=datetime(2026, 10, 19, tzinfo=UTC),
        expires_at=datetime(2026, 11, 14, tzinfo=UTC),
        quote_response={"status": 200, "feed": "sip", "quotes": {"AAPL": [quote]}},
        prior_references={"AAPL": ref, "MSFT": copy.deepcopy(ref)},
        accepted_unborrowed_capacity=20000,
        sleeve_new_gross_capacity=20000,
        fee_buffer_rate=0.001,
        new_risk_allowed=True,
        global_stop=False,
    )


def as_buy(args):
    args = copy.deepcopy(args)
    args["side"] = "buy"
    args["now"] = datetime(2026, 11, 3, 14, 40, tzinfo=UTC)
    quote = args["quote_response"]["quotes"]["AAPL"][0]
    quote.update(t="2026-11-03T14:40:00Z", bp=9.9, ap=10.0)
    args["quote_response"]["quotes"] = {"MSFT": [quote]}
    return args


def test_preparation_is_not_sale_fill_and_input_state_is_untouched(args):
    state, out = prepare_wave(**args)
    assert out["broker_calls"] == 0 and len(out["requests"]) == 1
    req = out["requests"][0]
    assert (req["qty"], req["type"], req["time_in_force"], req["limit_price"]) == (
        6,
        "limit",
        "day",
        10.0,
    )
    assert not args["state"].pending and not args["state"].consumed_ids
    assert state.cashbook.quantity("AAPL") == 10 and not state.cashbook.sales
    assert state.available("2026-11-04") == 100
    assert state.pending[req["client_order_id"]]["filled"] == 0


def test_only_confirmed_earlier_partial_sale_can_increase_buy_reservation(args):
    state, sell = prepare_wave(**args)
    buy = as_buy(args)
    buy["state"] = state
    before, out = prepare_wave(**buy)
    assert out["requests"][0]["qty"] == 9
    assert before.cashbook.quantity("MSFT") == 0
    state.confirmed_fill(
        sell["requests"][0]["client_order_id"], "actual-fixture-fill", 6, 10.0, "2026-11-03"
    )
    after, out = prepare_wave(**buy)
    assert out["requests"][0]["qty"] == 15
    assert after.cashbook.quantity("AAPL") == 4
    assert after.cashbook.quantity("MSFT") == 0
    assert after.available("2026-11-04") < 10


def test_duplicate_request_rejected_and_pending_cancel_reserves_funds(args):
    args = as_buy(args)
    state, out = prepare_wave(**args)
    args["state"] = state
    with pytest.raises(ValueError, match="already consumed"):
        prepare_wave(**args)
    with pytest.raises(ValueError, match="unknown/cancel-pending"):
        state.release(
            out["requests"][0]["client_order_id"], terminal_confirmed=False, fees_reconciled=True
        )


@pytest.mark.parametrize("status", [401, 403, 429, 500, None])
def test_unavailable_source_preserves_state_and_produces_no_intents(args, status):
    args["quote_response"]["status"] = status
    state, out = prepare_wave(**args)
    assert out["blocked"] == "required_source_unavailable"
    assert out["requests"] == [] and not state.pending and state.cashbook.cash == 100


def test_iex_is_not_a_fallback_and_global_stop_never_creates_orders(args):
    args["quote_response"]["feed"] = "iex"
    assert not prepare_wave(**args)[1]["requests"]
    args["quote_response"]["feed"] = "sip"
    args["global_stop"] = True
    assert prepare_wave(**args)[1]["blocked"] == "global_stop"


@pytest.mark.parametrize("change", ["late", "future", "nonregular", "ambiguous", "split", "prior"])
def test_bad_latest_state_does_not_search_back_for_a_good_quote(args, change):
    q = args["quote_response"]["quotes"]["AAPL"][0]
    if change == "late":
        args["now"] = args["now"].replace(second=1)
        q["t"] = "2026-11-03T14:34:55Z"
    elif change == "future":
        q["t"] = "2026-11-03T14:35:00.000000001Z"
    elif change == "nonregular":
        q["c"] = ["N"]
    elif change == "ambiguous":
        args["quote_response"]["quotes"]["AAPL"].append({**q, "bp": 9.9})
    elif change == "split":
        args["prior_references"]["AAPL"]["split_session"] = True
    else:
        args["prior_references"]["AAPL"]["completed_before_execution"] = False
    assert not prepare_wave(**args)[1]["requests"]


def test_daily_halt_blocks_buy_without_manufacturing_a_forced_sale(args):
    args["new_risk_allowed"] = False
    assert len(prepare_wave(**args)[1]["requests"]) == 1  # the original committed sale only
    buy = as_buy(args)
    assert not prepare_wave(**buy)[1]["requests"]


def test_foreign_or_unfunded_holding_cannot_supply_sell_leg(args):
    args["state"].cashbook.lots.clear()
    with pytest.raises(ValueError, match="funded own shares"):
        prepare_wave(**args)
    assert not args["state"].pending


def test_binding_rejection_is_before_any_state_mutation(args, tmp_path):
    args["commit_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="binding mismatch"):
        prepare_wave(**args)
    assert not args["state"].pending
    p = tmp_path / "source.py"
    p.write_bytes(b"original")
    binding = {"path": str(p), "bytes": 8, "sha256": hashlib.sha256(b"original").hexdigest()}
    assert bound_bytes(tmp_path, binding) == b"original"
    p.write_bytes(b"modified")
    with pytest.raises(ValueError, match="hash changed"):
        bound_bytes(tmp_path, binding)


def test_settlement_due_cannot_be_extended_to_borrow_later_proceeds(args):
    args["commit"]["settlement_due"] = "2026-11-05"
    args["commit_sha256"] = seal(args["commit"])
    with pytest.raises(ValueError, match="settlement date differs"):
        prepare_wave(**args)
    assert not args["state"].pending


@pytest.mark.parametrize("unknown", [False, None, "unknown", "false", 0, 1])
def test_R1_nonaffirmative_confirmations_preserve_every_reservation_and_AR(args, unknown):
    state = args["state"]
    state.reserve_buy("r1", "MSFT", 10, 10.0, 0.0, "2026-11-03", "2026-11-04")
    state.cashbook.sales.append(
        {"id": "fixture-sale", "due": "2026-11-04", "amount": 10.0, "unreserved": 10.0}
    )
    before = copy.deepcopy(state)
    for key in ("terminal_confirmed", "fees_reconciled"):
        flags = dict(terminal_confirmed=True, fees_reconciled=True)
        flags[key] = unknown
        with pytest.raises(ValueError, match="cannot release reservation"):
            state.release("r1", **flags)
        assert state == before
    with pytest.raises(ValueError, match="cannot certify actual broker settlement"):
        state.settle("2026-11-04", broker_settlement_verified=unknown, received_cash_ids=set())
    assert state == before and state.cashbook.cash == 100
    assert state.pending["r1"]["remaining_funding"][0]["amount"] == 100


def test_R1_explicit_confirmations_keep_actual_fill_fee_release_and_settlement(args):
    state = args["state"]
    state.reserve_buy("r1", "MSFT", 1, 10.0, 0.01, "2026-11-03", "2026-11-04")
    state.confirmed_fill("r1", "r1-fill", 1, 10.0, "2026-11-03")
    state.confirmed_fee("r1", "r1-fee", 0.01)
    state.release("r1", terminal_confirmed=True, fees_reconciled=True)
    assert "r1" not in state.pending and "r1" in state.consumed_ids
    state.settle("2026-11-04", broker_settlement_verified=True, received_cash_ids=set())
    assert state.cashbook.cash == pytest.approx(89.99)
    assert state.cashbook.quantity("MSFT") == 1
    assert not state.cashbook.purchases
