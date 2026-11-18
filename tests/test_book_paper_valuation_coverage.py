"""Missing held marks must remain visible without changing risk or order policy."""

import pytest
from test_book_paper import all_etb_client, make_target, plan_for

from open_composer.book_paper.post_close import (
    realized_exposures,
    reconcile,
    shadow_costs,
    tca,
)


def test_unpriced_held_short_is_not_hidden_by_exposure_completeness():
    target = make_target()
    result = realized_exposures(
        target,
        {"L1": 10, "SGOV": 100, "ACVA": -53, "ZERO": 0},
        {"L1": 50, "SGOV": 100},
        1_000_000,
    )
    assert result["beta"] == pytest.approx(0.0005)
    assert result["names_without_exposure"] == []  # Only the priced subset has exposures.
    coverage = result["valuation_coverage"]
    assert coverage["position_count"] == 3
    assert coverage["priced_position_count"] == 2
    assert coverage["unpriced_positions"] == {"ACVA": -53}
    assert not coverage["complete"]
    assert coverage["equity"] == 1_000_000
    assert coverage["denominator"] == "broker_account_equity"
    assert coverage["exposure_target_decision_date"] == str(target.decision_date)


@pytest.mark.parametrize("equity,complete", [(1_000_000, True), (0, False)])
def test_complete_marks_do_not_hide_invalid_equity_denominator(equity, complete):
    result = realized_exposures(make_target(), {"L1": 10}, {"L1": 50}, equity)
    assert result["valuation_coverage"]["complete"] is complete


@pytest.mark.parametrize("mark", [0, -1, float("nan"), float("inf")])
def test_invalid_mark_is_reported_without_imputation(mark):
    result = realized_exposures(make_target(), {"L1": 10}, {"L1": mark}, 1_000_000)
    assert result["valuation_coverage"]["invalid_price_names"] == ["L1"]
    assert not result["valuation_coverage"]["complete"]


def test_drift_discloses_old_reference_fallback_separately_from_quantity_drift():
    base = make_target()
    target = make_target(reference_prices={**base.reference_prices, "ACVA": 10.5})
    plan = plan_for(target, all_etb_client(positions={"ACVA": -53}))
    result = reconcile(plan, target, [], {"ACVA": -53}, base.reference_prices)
    coverage = result["weight_drift_valuation"]
    assert coverage["target_reference_fallback"] == ["ACVA"]
    assert coverage["unpriced_names"] == []
    assert coverage["target_reference_date"] == str(target.decision_date)
    assert coverage["equity_basis"] == target.equity_basis
    assert not coverage["complete_at_official_close"]
    assert result["n_position_drift_names"] > 0  # No claim that mark fallback reconciles quantity.


def test_missing_mark_without_fallback_remains_explicit():
    target = make_target()
    result = reconcile(plan_for(target), target, [], {"ACVA": -53}, target.reference_prices)
    assert result["weight_drift_valuation"]["unpriced_names"] == ["ACVA"]
    assert result["weight_drift_valuation"]["target_reference_fallback"] == []


def test_borrow_model_reports_unvalued_short_without_inventing_notional():
    target = make_target()
    result = shadow_costs(
        [],
        target,
        {"S1": -10, "ACVA": -53, "OTHER": 5},
        {"S1": 50},
        trade_date=target.execution_date,
    )
    assert result["short_notional_at_close"] == 500
    assert result["unpriced_short_positions"] == {"ACVA": -53}


def test_tca_declares_logical_row_unit_and_retains_partial_reference_counts():
    fills = [
        {"symbol": "A", "side": "buy", "filled_qty": 2, "filled_avg_price": 10},
        {"symbol": "B", "side": "sell", "filled_qty": 1, "filled_avg_price": 20},
    ]
    result = tca(fills, {"A": 10}, {})
    assert result["row_unit"] == "logical_order_aggregate"
    assert result["n_fills"] == 2
    assert result["n_with_reference_vs_official_close_bp"] == 1
    assert result["n_with_reference_vs_snapshot_1545_bp"] == 0


@pytest.mark.parametrize("equity", [0.0, -1.0, float("nan"), float("inf"), None])
def test_incomplete_account_equity_cannot_grant_pretrade_permission(equity):
    from test_book_paper import EXECUTION, NOW

    from open_composer.book_paper.plan import AccountState, AssetInfo, build_plan

    plan = build_plan(
        make_target(),
        AccountState(equity=equity, positions={}),
        as_of=EXECUTION,
        now=NOW,
        asset_lookup=lambda symbol: AssetInfo(symbol, True, True, True, "active"),
    )
    assert plan.status == "blocked"
    check = next(c for c in plan.payload["checks"] if c["name"] == "account_ready")
    assert not check["passed"]
    assert "finite and positive" in check["detail"]
