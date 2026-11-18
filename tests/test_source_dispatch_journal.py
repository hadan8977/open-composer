"""Own-order classification; no broker or provider transport."""

import pytest

from open_composer.intraday_runner.source_dispatch_journal import classify_own_order

CID = "dia-base-2026-11-03-sell-AAPL"
REQUEST = dict(
    client_order_id=CID,
    symbol="AAPL",
    side="sell",
    qty=6,
    type="limit",
    time_in_force="day",
    limit_price=10.0,
)
OBSERVED = dict(
    client_order_id=CID,
    symbol="AAPL",
    side="sell",
    qty="6",
    type="limit",
    time_in_force="day",
    limit_price="10",
    id="fixture-order",
    status="partially_filled",
    filled_qty="2",
)


def test_working_partial_fill_is_cancel_eligible_without_releasing_funds():
    result = classify_own_order(REQUEST, OBSERVED)
    assert result["cumulative_filled"] == 2 and result["remaining"] == 4
    assert result["cancel_eligible"] and not result["terminal_observed"]
    assert result["funds_releasable"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"client_order_id": "foreign"},
        {"symbol": "MSFT"},
        {"filled_qty": "7"},
        {"filled_qty": "NaN"},
        {"status": "filled"},
        {"status": "replaced"},
    ],
)
def test_nonmatching_or_inconsistent_observation_is_not_owned_cancel(change):
    with pytest.raises(ValueError):
        classify_own_order(REQUEST, {**OBSERVED, **change})


@pytest.mark.parametrize(
    "change",
    [{"status": "filled", "filled_qty": "6"}, {"status": "pending_cancel"}, {"status": "canceled"}],
)
def test_terminal_or_pending_cancel_observation_is_no_new_cancel(change):
    result = classify_own_order(REQUEST, {**OBSERVED, **change})
    assert not result["cancel_eligible"] and result["funds_releasable"] is False
