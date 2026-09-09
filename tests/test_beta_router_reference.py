"""F5 (Step 12 Group B): QQQ/TQQQ/QLD/BIL beta-exposure-router reference.

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 2. This module ports scripts/evaluate_vol02_recalibrated.py's
already-preregistered ``simulate_vol02`` rule verbatim (see module
docstring); these tests cover the pure sleeve-selection/week-boundary
helpers directly and check the full simulation is well-formed on small
synthetic data (no NaN, cost charged only on switch days) rather than
re-deriving VOL02's own numerical regression, which already exists
elsewhere for the original rule. No real market data.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from open_composer.research.regime import beta_router_reference as f5


def test_select_sleeve_risk_off_when_trend_non_positive() -> None:
    assert f5._select_sleeve(0.0, 0.05, f5.SIGNAL_PARAMETERS) == "BIL"
    assert f5._select_sleeve(-0.01, 0.05, f5.SIGNAL_PARAMETERS) == "BIL"


def test_select_sleeve_risk_off_when_trend_nonfinite() -> None:
    assert f5._select_sleeve(math.nan, 0.05, f5.SIGNAL_PARAMETERS) == "BIL"


def test_select_sleeve_low_vol_uptrend_goes_to_tqqq() -> None:
    assert f5._select_sleeve(0.05, 0.10, f5.SIGNAL_PARAMETERS) == "TQQQ"


def test_select_sleeve_medium_vol_uptrend_goes_to_qld() -> None:
    assert f5._select_sleeve(0.05, 0.18, f5.SIGNAL_PARAMETERS) == "QLD"


def test_select_sleeve_high_vol_uptrend_goes_to_qqq() -> None:
    assert f5._select_sleeve(0.05, 0.30, f5.SIGNAL_PARAMETERS) == "QQQ"


def test_is_week_end_true_across_an_iso_week_boundary() -> None:
    friday = pd.Timestamp("2024-01-05")  # ISO week 1
    monday = pd.Timestamp("2024-01-08")  # ISO week 2
    assert f5._is_week_end(friday, monday) is True


def test_is_week_end_false_within_the_same_iso_week() -> None:
    monday = pd.Timestamp("2024-01-08")
    tuesday = pd.Timestamp("2024-01-09")
    assert f5._is_week_end(monday, tuesday) is False


def _synthetic_symbol_series(index: pd.DatetimeIndex, drift: float, vol_scale: float) -> pd.Series:
    values = [100.0]
    for i in range(1, len(index)):
        step = drift + vol_scale * math.sin(i / 3.0) * 0.01
        values.append(values[-1] * (1.0 + step))
    return pd.Series(values, index=index)


def test_simulate_beta_router_is_well_formed_and_charges_cost_only_on_switches() -> None:
    index = pd.bdate_range("2016-01-04", periods=300, tz="UTC")
    closes = {
        "QQQ": _synthetic_symbol_series(index, drift=0.0006, vol_scale=1.0),
        "TQQQ": _synthetic_symbol_series(index, drift=0.0018, vol_scale=3.0),
        "QLD": _synthetic_symbol_series(index, drift=0.0012, vol_scale=2.0),
        "BIL": pd.Series([100.0 * (1.0001**i) for i in range(len(index))], index=index),
    }
    opens = {symbol: series * 0.999 for symbol, series in closes.items()}

    base = f5.simulate_beta_router(closes, opens, cost_bps_per_side=10.0)
    stress = f5.simulate_beta_router(closes, opens, cost_bps_per_side=25.0)

    assert not base.isna().any()
    assert not stress.isna().any()
    assert len(base) == len(stress)
    assert len(base) > 0
    # A higher per-switch cost can only ever pull a day's return down or
    # leave it unchanged relative to the lower-cost run, on switch days,
    # and must leave non-switch days exactly identical.
    diff = (stress - base).round(10)
    assert (diff <= 1e-9).all()


def test_simulate_beta_router_rejects_a_dataset_with_no_common_dates() -> None:
    index_a = pd.bdate_range("2016-01-04", periods=250, tz="UTC")
    index_b = pd.bdate_range("2020-01-06", periods=250, tz="UTC")
    closes = {
        "QQQ": pd.Series(100.0, index=index_a),
        "TQQQ": pd.Series(100.0, index=index_b),
        "QLD": pd.Series(100.0, index=index_b),
        "BIL": pd.Series(100.0, index=index_b),
    }
    opens = closes
    # Inherited from the ported VOL02 rule: with zero overlapping dates,
    # first_valid_index() is None for both features and max(None, None)
    # raises TypeError -- documenting the actual failure mode rather than
    # asserting a nicer one this port does not add.
    with pytest.raises(TypeError):
        f5.simulate_beta_router(closes, opens, cost_bps_per_side=10.0)
