"""Snapshot/restore of invented own-sleeve books; no account/source/network operations."""

import pytest

from open_composer.intraday_runner import source_state_checkpoint as mod
from open_composer.intraday_runner.source_method_bindings import source_module
from open_composer.intraday_runner.source_reservations import SourceReservations

CID = "dia-base-2026-11-03-sell-AAPL"
ACCOUNT = "a" * 64


@pytest.fixture
def case(tmp_path):
    cash = source_module(tmp_path, "cash").CashState(
        cash=100,
        lots={"AAPL": [{"quantity": 10, "funded": "2026-10-19"}]},
        dividends=[dict(id="unreceived-right", amount=2.55, due="2026-11-04")],
    )
    state = SourceReservations(cash)
    state.reserve_sell(CID, "AAPL", 4, 10.0, "2026-11-03", "2026-11-04", fee_buffer_rate=0.01)
    return tmp_path, state


def snap(state, fills=None, fees=None):
    return mod.snapshot(
        state, fills or {}, fees or {}, evidence={"fixture_only": True, "broker_complete": False}
    )


def test_roundtrip_preserves_pending_unknown_and_unreceived_right(case):
    root, state = case
    restored, fills, fees, evidence = mod.restore(root, snap(state))
    assert restored == state and fills == fees == {}
    assert restored.pending[CID]["filled"] == 0 and not restored.cashbook.sales
    assert restored.cashbook.dividends == state.cashbook.dividends
    assert evidence["broker_complete"] is False


def test_fill_and_fee_maps_are_typed(case):
    root, state = case
    state.confirmed_fill(CID, "fill-1", 2, 10.0, "2026-11-03")
    state.confirmed_fee(CID, "fee-1", 0.10)
    fills = {"fill-1": dict(client_order_id=CID, account_hash=ACCOUNT, raw="fixture-fill")}
    fees = {"fee-1": dict(client_order_id=CID, account_hash=ACCOUNT, raw="fixture-classified-fee")}
    saved = snap(state, fills, fees)
    assert set(saved["applied_fill_ids"]) == {"fill-1", "fee-1"}
    assert len(saved["fills"]) == len(saved["fees"]) == 1
    assert mod.restore(root, saved)[0] == state
    with pytest.raises(ValueError, match="typed receipt"):
        snap(state, fills)


def test_nonfinite_snapshot_is_refused(case):
    _, state = case
    state.cashbook.cash = float("nan")
    with pytest.raises(ValueError):
        snap(state)
