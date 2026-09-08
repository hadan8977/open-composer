"""Whole-share sizing for the $100k paper account."""

from __future__ import annotations

import pytest

from open_composer.adapters.execution.whole_share_sizing import size_whole_share_portfolio


def test_exact_division_needs_no_rounding() -> None:
    result = size_whole_share_portfolio(
        {"AAA": 0.5, "BBB": 0.5}, {"AAA": 100.0, "BBB": 50.0}, equity=10_000.0
    )
    assert result.shares == {"AAA": 50, "BBB": 100}
    assert result.idle_cash == pytest.approx(0.0)
    assert result.weight_deviation == pytest.approx(0.0)
    assert result.unaffordable == ()


def test_remainder_allocation_reduces_idle_cash_and_deviation() -> None:
    # 3 names, prices that do not divide the budget evenly.
    weights = {"AAA": 1 / 3, "BBB": 1 / 3, "CCC": 1 / 3}
    prices = {"AAA": 317.0, "BBB": 91.0, "CCC": 43.0}
    floored = size_whole_share_portfolio(weights, prices, 10_000.0, allocate_remainder=False)
    topped = size_whole_share_portfolio(weights, prices, 10_000.0, allocate_remainder=True)
    assert topped.idle_cash < floored.idle_cash
    # Weights are measured against equity, so idle cash is itself a deviation:
    # spending the remainder can only move realized weights toward target.
    assert topped.weight_deviation < floored.weight_deviation
    # Never spends more than the account holds.
    assert topped.invested_cash <= 10_000.0


def test_name_too_expensive_for_its_slot_is_reported_not_silently_dropped() -> None:
    result = size_whole_share_portfolio(
        {"CHEAP": 0.5, "PRICEY": 0.5},
        {"CHEAP": 10.0, "PRICEY": 9_000.0},
        equity=10_000.0,
        allocate_remainder=False,
    )
    assert result.shares["PRICEY"] == 0
    assert "PRICEY" in result.unaffordable
    assert result.realized_weights["PRICEY"] == pytest.approx(0.0)


def test_missing_price_is_unaffordable_rather_than_a_crash() -> None:
    result = size_whole_share_portfolio({"AAA": 1.0}, {}, equity=10_000.0)
    assert result.shares == {"AAA": 0}
    assert result.unaffordable == ("AAA",)


def test_hedge_leg_rounds_toward_a_smaller_short_not_a_larger_one() -> None:
    result = size_whole_share_portfolio(
        {"AAA": 1.0, "SPY": -0.35},
        {"AAA": 100.0, "SPY": 620.0},
        equity=10_000.0,
        allocate_remainder=False,
    )
    # 0.35 * 10000 / 620 = 5.6 -> 5 shares short, not 6.
    assert result.shares["SPY"] == -5
    assert result.realized_weights["SPY"] < 0


def test_zero_or_negative_equity_raises() -> None:
    with pytest.raises(ValueError, match="equity must be positive"):
        size_whole_share_portfolio({"AAA": 1.0}, {"AAA": 10.0}, equity=0.0)


def test_realized_weights_sum_to_one_for_a_long_only_book() -> None:
    weights = {f"S{i}": 1 / 50 for i in range(50)}
    prices = {f"S{i}": 20.0 + 7.0 * i for i in range(50)}
    result = size_whole_share_portfolio(weights, prices, 100_000.0)
    # Against equity, realized weights sum to the invested fraction, not to 1.
    assert sum(result.realized_weights.values()) == pytest.approx(result.invested_cash / 100_000.0)
    # A realistic $100k top-50 book should stay well inside 5% deviation.
    assert result.weight_deviation < 0.05
    assert result.idle_cash_fraction < 0.05
