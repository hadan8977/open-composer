"""F2 (Step 12 Group B): trend-filtered momentum + cash switch.

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 2. Pure synthetic-data unit tests for
``open_composer.research.regime.trend_filtered_momentum`` -- the
schedule-level overlay logic (risk-on/off flags, vol-target equity weight,
weight scaling + cash residual). No real feature panel, no loop.py
walk-forward computation: those are exercised by the (not-yet-run, blocked
on Group A's feature-grid job finishing) driver script.
"""

from __future__ import annotations

import pandas as pd
import pytest

from open_composer.research.kernel.loop import RebalanceEvent
from open_composer.research.regime import trend_filtered_momentum as f2


def test_parameter_space_has_four_preregistered_cells() -> None:
    assert len(f2.PARAMETER_SPACE) == 4
    assert len({f2.cell_id(i) for i in range(4)}) == 4
    sma_days = {cell["trend_sma_days"] for cell in f2.PARAMETER_SPACE}
    target_vols = {cell["target_vol_annual"] for cell in f2.PARAMETER_SPACE}
    assert sma_days == {100, 200}
    assert target_vols == {None, 0.15}


def test_compute_risk_on_flags_true_above_and_false_below_sma() -> None:
    index = pd.bdate_range("2024-01-01", periods=10, tz="UTC")
    # A rising series: close ends up above its own trailing SMA once warm.
    close = pd.Series([100.0 + i for i in range(10)], index=index)
    rebalance_dates = [index[3], index[9]]
    risk_on = f2.compute_risk_on_flags(close, sma_days=3, rebalance_dates=rebalance_dates)
    assert bool(risk_on.loc[index[3]])
    assert bool(risk_on.loc[index[9]])


def test_compute_risk_on_flags_false_during_warmup() -> None:
    index = pd.bdate_range("2024-01-01", periods=5, tz="UTC")
    close = pd.Series([100.0] * 5, index=index)
    risk_on = f2.compute_risk_on_flags(close, sma_days=200, rebalance_dates=[index[0]])
    assert bool(risk_on.loc[index[0]]) is False


def test_compute_risk_on_flags_false_when_close_below_sma() -> None:
    index = pd.bdate_range("2024-01-01", periods=6, tz="UTC")
    close = pd.Series([100.0, 100.0, 100.0, 100.0, 90.0, 80.0], index=index)
    risk_on = f2.compute_risk_on_flags(close, sma_days=3, rebalance_dates=[index[5]])
    assert bool(risk_on.loc[index[5]]) is False


def test_compute_equity_weight_binary_switch_without_vol_target() -> None:
    index = pd.bdate_range("2024-01-01", periods=3, tz="UTC")
    risk_on = pd.Series([True, False, True], index=index)
    weight = f2.compute_equity_weight(risk_on, target_vol_annual=None)
    assert list(weight) == [1.0, 0.0, 1.0]


def test_compute_equity_weight_scales_by_target_over_trailing_vol_capped_at_one() -> None:
    index = pd.bdate_range("2024-01-01", periods=3, tz="UTC")
    risk_on = pd.Series([True, True, True], index=index)
    # trailing vol 0.30 -> 0.15/0.30 = 0.5; trailing vol 0.05 -> capped at 1.0.
    trailing_vol = pd.Series([0.30, 0.05, 0.30], index=index)
    weight = f2.compute_equity_weight(
        risk_on, target_vol_annual=0.15, trailing_vol_annual=trailing_vol
    )
    assert weight.iloc[0] == pytest.approx(0.5)
    assert weight.iloc[1] == pytest.approx(1.0)
    assert weight.iloc[2] == pytest.approx(0.5)


def test_compute_equity_weight_zero_when_risk_off_even_with_low_vol() -> None:
    index = pd.bdate_range("2024-01-01", periods=1, tz="UTC")
    risk_on = pd.Series([False], index=index)
    trailing_vol = pd.Series([0.01], index=index)  # would imply >1x leverage if risk-on
    weight = f2.compute_equity_weight(
        risk_on, target_vol_annual=0.15, trailing_vol_annual=trailing_vol
    )
    assert weight.iloc[0] == 0.0


def test_compute_equity_weight_zero_when_trailing_vol_unmeasurable() -> None:
    index = pd.bdate_range("2024-01-01", periods=2, tz="UTC")
    risk_on = pd.Series([True, True], index=index)
    trailing_vol = pd.Series([float("nan"), 0.0], index=index)
    weight = f2.compute_equity_weight(
        risk_on, target_vol_annual=0.15, trailing_vol_annual=trailing_vol
    )
    assert list(weight) == [0.0, 0.0]


def test_compute_equity_weight_target_vol_without_trailing_series_raises() -> None:
    risk_on = pd.Series([True])
    with pytest.raises(ValueError):
        f2.compute_equity_weight(risk_on, target_vol_annual=0.15, trailing_vol_annual=None)


def test_apply_regime_overlay_scales_weights_and_adds_cash_residual() -> None:
    schedule = [
        RebalanceEvent(
            date="2024-01-05",
            universe_size=2,
            selected={"AAA": 0.5, "BBB": 0.5},
            portfolio_beta=None,
        ),
        RebalanceEvent(
            date="2024-01-12",
            universe_size=2,
            selected={"AAA": 0.5, "BBB": 0.5},
            portfolio_beta=None,
        ),
    ]
    equity_weight = {pd.Timestamp("2024-01-05"): 0.5, pd.Timestamp("2024-01-12"): 0.0}
    overlaid = f2.apply_regime_overlay(schedule, equity_weight)
    assert overlaid[0].selected == {"AAA": 0.25, "BBB": 0.25, "BIL": 0.5}
    assert overlaid[1].selected == {"AAA": 0.0, "BBB": 0.0, "BIL": 1.0}
    # Non-selected fields pass through unchanged.
    assert overlaid[0].date == "2024-01-05"
    assert overlaid[0].universe_size == 2


def test_apply_regime_overlay_full_weight_does_not_add_a_cash_entry() -> None:
    schedule = [
        RebalanceEvent(
            date="2024-01-05", universe_size=1, selected={"AAA": 1.0}, portfolio_beta=None
        )
    ]
    equity_weight = {pd.Timestamp("2024-01-05"): 1.0}
    overlaid = f2.apply_regime_overlay(schedule, equity_weight)
    assert overlaid[0].selected == {"AAA": 1.0}
    assert "BIL" not in overlaid[0].selected


def test_apply_regime_overlay_missing_date_defaults_to_all_cash() -> None:
    schedule = [
        RebalanceEvent(
            date="2024-01-05", universe_size=1, selected={"AAA": 1.0}, portfolio_beta=None
        )
    ]
    overlaid = f2.apply_regime_overlay(schedule, equity_weight={})
    assert overlaid[0].selected == {"AAA": 0.0, "BIL": 1.0}
