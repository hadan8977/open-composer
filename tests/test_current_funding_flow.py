"""Finite capital-flow checks; invented account facts, no provider calls."""

import copy
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from open_composer.intraday_runner.current_initialization_controls import identity, risk_transition
from open_composer.intraday_runner.current_initialization_funding import MAIN_SHA, funding_snapshot
from open_composer.intraday_runner.source_activity_reception import save
from open_composer.intraday_runner.source_dispatch_journal import _hash
from open_composer.intraday_runner.validation_account_partition import (
    ACCOUNT,
    SLOTS,
    allocation_map,
    receive_partition,
)


def context():
    now = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
    state = dict(
        cashbook=dict(cash=10000, sales=[], purchases=[], dividends=[], lots={}, next_id=0),
        pending={},
        consumed_ids=[],
        applied_fill_ids=[],
        fills={},
        fees={},
        evidence=dict(
            allocated_capital="10000",
            unresolved_actual_liabilities=False,
            risk=dict(
                initial_capital="10000",
                high_water="10000",
                day=None,
                day_open_nav=None,
                halted=False,
                killed=False,
            ),
        ),
    )
    current = dict(generation=0, snapshot=state)
    o = dict(
        started_at=now.isoformat(),
        oldest_response_at=now.isoformat(),
        last_response_at=now.isoformat(),
        completed_at=now.isoformat(),
        started_monotonic=1,
        completed_monotonic=1,
        account_hash=ACCOUNT,
        checkpoint_hash=_hash(current),
        currency="USD",
        account_status="ACTIVE",
        trading_blocked=False,
        account_blocked=False,
        trade_suspended=False,
        holdings=[],
        own_cash="10000",
        trade_receivables="0",
        valued_rights="0",
        purchase_payables="0",
        fee_liabilities="0",
        other_liabilities="0",
        unborrowed_available="10000",
        own_nav="10000",
        account_unborrowed_available="1000000",
        account_marked_value="0",
        other_checkpoint_hashes={},
    )
    for k in (
        "positions_complete",
        "orders_complete",
        "actions_complete",
        "units_reconciled",
        "activities_complete",
        "cash_reconciled",
        "fees_complete",
    ):
        o[k] = True
    return (
        current,
        o,
        dict(
            now=now,
            monotonic=1,
            account_hash=ACCOUNT,
            main={"sha256": MAIN_SHA},
            capture_binding={"sha256": "capture"},
        ),
    )


def test_flow_is_not_profit_or_history_reset():
    c, o, kw = context()
    original = copy.deepcopy(c)
    result = funding_snapshot(c, o, **kw)
    assert c == original and result["cashbook"]["cash"] == 20000
    e = result["evidence"]
    assert e["allocated_capital"] == "20000"
    assert e["risk"]["initial_capital"] == "10000" and e["risk"]["net_allocation_flows"] == "10000"
    assert e["allocation_flows"][0]["profit_USD"] == "0"
    assert e["risk"]["high_water"] == "20000" and e["risk"]["day_open_nav"] is None
    assert result["pending"] == c["snapshot"]["pending"]
    with pytest.raises(ValueError):
        funding_snapshot(dict(generation=1, snapshot=result), o, **kw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_unborrowed_available", "119999"),
        ("cash_reconciled", False),
        ("orders_complete", "unknown"),
        ("activities_complete", False),
    ],
)
def test_invalid_current_funding_keeps_predecessor(field, value):
    c, o, kw = context()
    old = copy.deepcopy(c)
    o[field] = value
    with pytest.raises(ValueError):
        funding_snapshot(c, o, **kw)
    assert c == old


def test_funding_clock_and_latches_cannot_reset():
    c, o, kw = context()
    kw["monotonic"] = 17
    with pytest.raises(ValueError):
        funding_snapshot(c, o, **kw)
    kw["monotonic"] = 1
    c["snapshot"]["evidence"]["risk"].update(killed=True, halted=True, high_water="12000")
    o["checkpoint_hash"] = _hash(c)
    result = funding_snapshot(c, o, **kw)
    assert result["evidence"]["risk"]["killed"] is True
    assert result["evidence"]["risk"]["high_water"] == "24000"
    p = result["evidence"]["risk"]
    p.update(day="2026-10-19", day_open_nav="20000")
    assert (
        risk_transition(p, dict(verified_nav="18000"), now=kw["now"], capital=20000)["killed"]
        is True
    )


def test_six_scope_exact_selected_cash_commitments(tmp_path):
    b = save(tmp_path / "owner.json", {})
    value = dict(
        event_id="main-existing-paper-six-candidate-allocation-20261019",
        candidate_inventory=[dict(task_id=t, initial_allocation_USD=20000) for t in SLOTS],
        funding=dict(
            selected_six_initial_allocations_total_USD=120000,
            account_hash=ACCOUNT,
            paper_only=True,
            long_cash=True,
            per_portfolio_gross_max_own_NAV_multiple=1,
            no_cross_trial_idle_cash_lending=True,
            no_double_reserved_account_cash_or_sale_AR=True,
        ),
        owner_directive=b,
        supersedes_allocation_only=b,
    )
    bound = save(tmp_path / "main.json", value)
    assert sum(allocation_map(tmp_path, bound).values()) == Decimal(120000)
    value["candidate_inventory"][2]["initial_allocation_USD"] = 20001
    with pytest.raises(ValueError):
        receive_partition(tmp_path, save(tmp_path / "bad.json", value))


def test_lstm_actual_order_namespace_is_admitted_only_exact():
    namespace = SLOTS["CROSS-ASSET-LSTM-PAPER-VALIDATION-20261019"][1]
    identity(namespace + "-1019-buy-SPY", "SPY", "buy", namespace=namespace)
    with pytest.raises(ValueError):
        identity("arbitrary", "SPY", "buy", namespace=namespace)
