"""Step 12 Group B recent-regime metrics: hit rate, profit factor, calendar
quarter/week framing, and the disclosure-only risk-shape helpers.

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 1. Pure synthetic fixtures -- no real market data, no ledger, no
gate contract -- this file tests only the arithmetic in
``open_composer.research.regime.metrics``.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from open_composer.research.regime import metrics


def test_hit_rate_counts_only_positive_holding_periods() -> None:
    assert metrics.hit_rate([1.0, -1.0, 2.0, 3.0, -0.5]) == pytest.approx(0.6)


def test_hit_rate_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        metrics.hit_rate([])


def test_profit_factor_ratio_of_gains_to_absolute_losses() -> None:
    assert metrics.profit_factor([1.0, -1.0, 2.0, -0.5]) == pytest.approx(3.0 / 1.5)


def test_profit_factor_is_infinite_with_no_losses() -> None:
    assert metrics.profit_factor([1.0, 2.0, 3.0]) == math.inf


def test_profit_factor_is_zero_with_no_gains() -> None:
    assert metrics.profit_factor([-1.0, -2.0]) == 0.0


def test_profit_factor_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        metrics.profit_factor([])


def _daily_series(start: str, values: list[float]) -> pd.Series:
    index = pd.bdate_range(start, periods=len(values), tz="UTC")
    return pd.Series(values, index=index, name="return")


def test_quarterly_returns_compounds_within_each_calendar_quarter() -> None:
    # 2024-02-01..2024-02-05 (Q1) and 2024-04-01..2024-04-05 (Q2), business days.
    index = pd.DatetimeIndex(
        [
            "2024-02-01",
            "2024-02-02",
            "2024-02-05",
            "2024-04-01",
            "2024-04-02",
        ],
        tz="UTC",
    )
    values = [0.01, 0.01, -0.005, 0.02, -0.01]
    series = pd.Series(values, index=index)
    result = metrics.quarterly_returns(series)
    assert set(result) == {"2024Q1", "2024Q2"}
    expected_q1 = (1.01 * 1.01 * 0.995) - 1.0
    expected_q2 = (1.02 * 0.99) - 1.0
    assert result["2024Q1"] == pytest.approx(expected_q1)
    assert result["2024Q2"] == pytest.approx(expected_q2)


def test_quarterly_returns_rejects_empty_series() -> None:
    with pytest.raises(ValueError):
        metrics.quarterly_returns(pd.Series([], dtype=float))


def test_positive_quarter_fraction_counts_quarters_not_days() -> None:
    index = pd.DatetimeIndex(["2024-02-01", "2024-04-01", "2024-07-01"], tz="UTC")
    # Q1 positive, Q2 negative, Q3 positive -> 2/3.
    series = pd.Series([0.05, -0.05, 0.02], index=index)
    assert metrics.positive_quarter_fraction(series) == pytest.approx(2.0 / 3.0)


def test_return_skewness_requires_at_least_three_observations() -> None:
    with pytest.raises(ValueError):
        metrics.return_skewness(_daily_series("2024-01-02", [0.01, -0.01]))


def test_return_skewness_is_near_zero_for_symmetric_data() -> None:
    series = _daily_series("2024-01-02", [0.01, -0.01, 0.02, -0.02, 0.0])
    assert metrics.return_skewness(series) == pytest.approx(0.0, abs=1e-9)


def test_return_skewness_is_negative_for_small_wins_occasional_big_loss() -> None:
    # The exact "high hit rate, negative skew" shape the plan warns about:
    # many small wins, one large loss.
    values = [0.01] * 20 + [-0.30]
    series = _daily_series("2024-01-02", values)
    assert metrics.return_skewness(series) < 0.0


def test_worst_single_week_return_finds_the_minimum_compounded_week() -> None:
    index = pd.DatetimeIndex(
        [
            "2024-01-01",  # Mon, week 1 -- small gain
            "2024-01-02",
            "2024-01-08",  # Mon, week 2 -- bad week
            "2024-01-09",
        ],
        tz="UTC",
    )
    values = [0.01, 0.01, -0.10, -0.05]
    series = pd.Series(values, index=index)
    expected_worst = (0.9 * 0.95) - 1.0
    assert metrics.worst_single_week_return(series) == pytest.approx(expected_worst)


def test_worst_single_week_return_rejects_empty_series() -> None:
    with pytest.raises(ValueError):
        metrics.worst_single_week_return(pd.Series([], dtype=float))


def test_annualized_trade_count_normalizes_by_years() -> None:
    assert metrics.annualized_trade_count(10, years=2.0) == pytest.approx(5.0)


def test_annualized_trade_count_rejects_nonpositive_years() -> None:
    with pytest.raises(ValueError):
        metrics.annualized_trade_count(10, years=0.0)


def test_window_years_measures_calendar_span() -> None:
    series = _daily_series("2024-01-02", [0.0] * 253)  # ~one trading year
    assert metrics.window_years(series) == pytest.approx(1.0, rel=0.05)


def test_window_years_rejects_empty_series() -> None:
    with pytest.raises(ValueError):
        metrics.window_years(pd.Series([], dtype=float))


def test_replay_year_return_compounds_the_named_calendar_year() -> None:
    index = pd.DatetimeIndex(["2021-06-01", "2022-01-05", "2022-06-01", "2023-01-05"], tz="UTC")
    series = pd.Series([0.5, -0.10, -0.10, 0.5], index=index)
    expected_2022 = (0.9 * 0.9) - 1.0
    assert metrics.replay_year_return(series, 2022) == pytest.approx(expected_2022)


def test_replay_year_return_is_none_when_year_absent() -> None:
    series = _daily_series("2024-01-02", [0.01, 0.02])
    assert metrics.replay_year_return(series, 2019) is None
