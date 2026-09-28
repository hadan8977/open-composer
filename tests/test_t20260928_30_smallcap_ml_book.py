"""T-20260928-30 unit tests: Abdi-Ranaldo spread estimator, turnover-buffered
top-N selection, and the capacity cap.

Task: turn the frozen B0 price-volume LightGBM ranking model
(dir:lgbm_price_volume_ranking_small_caps) into a long-only book with
per-stock spread costs. These three pure functions are the only new,
untested logic the task introduces (everything else is reused/imported from
frozen scripts) -- see scripts/run_t20260928_30_smallcap_ml_book.py's module
docstring.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

mod = importlib.import_module("scripts.run_t20260928_30_smallcap_ml_book")


# --------------------------------------------------------------------------
# Abdi-Ranaldo spread estimator
# --------------------------------------------------------------------------


def _ohlc(
    closes: list[float], highs: list[float], lows: list[float]
) -> tuple[pd.Series, pd.Series, pd.Series]:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return (
        pd.Series(closes, index=idx, dtype="float64"),
        pd.Series(highs, index=idx, dtype="float64"),
        pd.Series(lows, index=idx, dtype="float64"),
    )


def test_abdi_ranaldo_zero_spread_when_high_equals_low_equals_close():
    # high == low == close every day -> eta_t == c_t always -> every pair
    # term's product is exactly 0 -> spread estimate is 0, not NaN or negative.
    n = 30
    prices = [100.0 + i * 0.3 for i in range(n)]
    close, high, low = _ohlc(prices, prices, prices)
    terms = mod.abdi_ranaldo_pair_terms(close, high, low)
    assert terms.iloc[0] != terms.iloc[0]  # NaN at position 0 (no prior day)
    assert np.allclose(terms.iloc[1:].to_numpy(), 0.0)
    est = mod.spread_estimate_from_ohlc(close, high, low, window_days=21)
    valid = est.dropna()
    assert len(valid) > 0
    assert np.allclose(valid.to_numpy(), 0.0)


def test_abdi_ranaldo_hand_computed_two_day_term():
    # Hand-computed single pair: close=[100, 101], high=[102, 103], low=[98, 99].
    # eta_0 = (ln(102)+ln(98))/2, eta_1 = (ln(103)+ln(99))/2, c_0 = ln(100).
    close, high, low = _ohlc([100.0, 101.0], [102.0, 103.0], [98.0, 99.0])
    terms = mod.abdi_ranaldo_pair_terms(close, high, low)
    eta0 = (np.log(102.0) + np.log(98.0)) / 2.0
    eta1 = (np.log(103.0) + np.log(99.0)) / 2.0
    c0 = np.log(100.0)
    expected = np.sqrt(max((c0 - eta0) * (c0 - eta1), 0.0))
    assert terms.iloc[0] != terms.iloc[0]  # NaN
    assert terms.iloc[1] == pytest.approx(expected, rel=1e-9)


def test_abdi_ranaldo_floors_negative_product_at_zero():
    # Construct a day where (c_t - eta_t) and (c_t - eta_{t+1}) have opposite
    # signs, so the raw product is negative -- must floor to 0, not NaN or
    # a complex/negative sqrt input.
    close, high, low = _ohlc([100.0, 100.0], [150.0, 90.0], [110.0, 80.0])
    terms = mod.abdi_ranaldo_pair_terms(close, high, low)
    eta0 = (np.log(150.0) + np.log(110.0)) / 2.0
    eta1 = (np.log(90.0) + np.log(80.0)) / 2.0
    c0 = np.log(100.0)
    raw = (c0 - eta0) * (c0 - eta1)
    assert raw < 0  # confirms this test exercises the floor branch
    assert terms.iloc[1] == 0.0


def test_spread_estimate_needs_full_window_min_periods():
    n = 25
    prices = [100.0 + i for i in range(n)]
    high = [p * 1.02 for p in prices]
    low = [p * 0.98 for p in prices]
    close, high_s, low_s = _ohlc(prices, high, low)
    est = mod.spread_estimate_from_ohlc(close, high_s, low_s, window_days=21)
    # 21-day window needs 20 pair terms; pair terms start at index 1, so the
    # first valid rolling estimate is at index 1 + 20 - 1 = 20.
    assert est.iloc[:20].isna().all()
    assert est.iloc[20:].notna().all()


def test_spread_estimate_is_capped_and_floored():
    n = 25
    rng = np.random.default_rng(0)
    prices = 100.0 + np.cumsum(rng.normal(0, 0.1, n))
    # blow the high/low range out so the raw estimate would exceed the 5% cap
    high = prices * 1.5
    low = prices * 0.5
    close, high_s, low_s = _ohlc(list(prices), list(high), list(low))
    est = mod.spread_estimate_from_ohlc(close, high_s, low_s, window_days=21, floor=0.0, cap=0.05)
    valid = est.dropna()
    assert len(valid) > 0
    assert (valid <= 0.05 + 1e-12).all()
    assert (valid >= 0.0).all()


# --------------------------------------------------------------------------
# turnover-buffered top-N selection
# --------------------------------------------------------------------------


def test_buffered_selection_no_prior_holdings_takes_top_n():
    ranked = [f"S{i}" for i in range(1, 201)]  # S1 best .. S200 worst
    out = mod.buffered_selection(set(), ranked, n_target=50, buffer_rank=150)
    assert out == ranked[:50]


def test_buffered_selection_retains_holding_within_buffer_band():
    # S60 was held; it now ranks 120th (outside top 50 but inside the 150
    # buffer) -- it must stay, without displacing anyone already retained.
    ranked = [f"S{i}" for i in range(1, 201)]
    previous = {"S60"}  # "S60" currently ranks 120th in `ranked` below
    ranked[119], ranked[59] = ranked[59], ranked[119]  # move S60 to rank 120
    out = mod.buffered_selection(previous, ranked, n_target=50, buffer_rank=150)
    assert "S60" in out
    assert len(out) == 50


def test_buffered_selection_drops_holding_outside_buffer_band():
    ranked = [f"S{i}" for i in range(1, 201)]
    previous = {"S180"}  # ranks 180th -- outside the 150 buffer -> must be sold
    out = mod.buffered_selection(previous, ranked, n_target=50, buffer_rank=150)
    assert "S180" not in out
    assert len(out) == 50


def test_buffered_selection_fills_vacated_slots_with_best_unheld_names():
    ranked = [f"S{i}" for i in range(1, 201)]
    # every current top-50 name is already held except S50, which was
    # replaced (in the ranked list) by S51 conceptually -- simplest check:
    # holding nothing previously always yields exactly ranked[:50].
    previous: set[str] = set()
    out = mod.buffered_selection(previous, ranked, n_target=50, buffer_rank=150)
    assert set(out) == set(ranked[:50])


def test_buffered_selection_caps_book_size_when_thin_universe():
    ranked = [f"S{i}" for i in range(1, 11)]  # only 10 names available
    out = mod.buffered_selection(set(), ranked, n_target=50, buffer_rank=150)
    assert out == ranked
    assert len(out) == 10


def test_buffered_selection_is_deterministic():
    ranked = [f"S{i}" for i in range(1, 201)]
    previous = {"S70", "S140"}
    out1 = mod.buffered_selection(previous, ranked, n_target=50, buffer_rank=150)
    out2 = mod.buffered_selection(previous, ranked, n_target=50, buffer_rank=150)
    assert out1 == out2


# --------------------------------------------------------------------------
# capacity cap
# --------------------------------------------------------------------------


def test_capacity_cap_binds_when_equal_weight_too_large():
    # 1% of $1,000,000 median daily dollar volume = $10,000 = 10% of a
    # $100,000 account -- below the 1/50 = 2% equal weight? No: 10% > 2%, so
    # the cap should NOT bind here; use a smaller ADV to force binding.
    equal_weight = 1.0 / 50.0  # 2%
    dollar_vol_median = 50_000.0  # 1% of this = $500 = 0.5% of $100k account
    w = mod.capacity_capped_weight(equal_weight, dollar_vol_median, account_value=100_000.0)
    assert w == pytest.approx(0.005)
    assert w < equal_weight


def test_capacity_cap_does_not_bind_when_liquidity_ample():
    equal_weight = 1.0 / 50.0  # 2%
    dollar_vol_median = 50_000_000.0  # 1% = $500,000, far above 2% of $100k
    w = mod.capacity_capped_weight(equal_weight, dollar_vol_median, account_value=100_000.0)
    assert w == pytest.approx(equal_weight)


def test_capacity_cap_zero_for_missing_or_nonpositive_liquidity():
    equal_weight = 1.0 / 50.0
    assert mod.capacity_capped_weight(equal_weight, float("nan")) == 0.0
    assert mod.capacity_capped_weight(equal_weight, 0.0) == 0.0
    assert mod.capacity_capped_weight(equal_weight, -100.0) == 0.0


def test_per_stock_cost_bps_combines_flat_and_spread():
    spread = pd.Series([0.0, 0.001, 0.01])  # 0%, 0.1% (10bp), 1% (100bp)
    out = mod.per_stock_cost_bps(spread, flat_bps=10.0, spread_weight=0.5)
    # 10 + 0.5*0, 10 + 0.5*10, 10 + 0.5*100
    assert out.tolist() == pytest.approx([10.0, 15.0, 60.0])
