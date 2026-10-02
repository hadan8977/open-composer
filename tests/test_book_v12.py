"""Tests for open_composer.research.equity_book.book_v12 (synthetic data only)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.book_paper.plan import round_half_away
from open_composer.research.equity_book import book_v12 as bv
from scripts import realism_ladder_book_ls as t25


# ---------------------------------------------------------------------------
# T-bill leg and scaling
# ---------------------------------------------------------------------------
def test_tbill_fraction_basic_is_gross_cap_limited():
    # L = S = 0.5: the cap leaves 0.8, cash allows 1.0 -> 0.8
    assert bv.tbill_fraction(0.5, 0.5) == pytest.approx(0.8)


def test_tbill_fraction_cash_limited_and_debit_case():
    # long heavy, little short: cash 1 - 1.2 + 0.1 < 0 -> no T-bill, never negative
    assert bv.tbill_fraction(1.2, 0.1) == 0.0
    # cash binds before the cap: L 0.6, S 0.1 -> min(1.1, 0.5) = 0.5
    assert bv.tbill_fraction(0.6, 0.1) == pytest.approx(0.5)


def test_tbill_fraction_negative_hedge_enters_short_leg_and_vix_halved_case():
    # hedge h < 0 is a SPY short: it adds to S; unit book L = 0.5, S = 0.5 + 0.2
    assert bv.tbill_fraction(0.5, 0.7) == pytest.approx(min(1.8 - 1.2, 1 - 0.5 + 0.7))
    # VIX halved: every weight halves, the T-bill leg grows
    full = bv.tbill_fraction(0.6, 0.6)
    half = bv.tbill_fraction(0.3, 0.3)
    assert half > full
    assert half == pytest.approx(min(1.8 - 0.6, 1.0))


def test_tbill_fraction_zero_book_is_capped_by_cash_one():
    assert bv.tbill_fraction(0.0, 0.0) == pytest.approx(1.0)


def test_gross_cap_presses_k_eff_when_hedge_is_large():
    # normal hedge: 0.5 * (2 + 1.27) = 1.635 < 1.8 -> unchanged
    assert bv.f1_k_eff(1.0, 1.27) == pytest.approx(0.5)
    # |h| = 2: 0.5 * 4 = 2 > 1.8 -> k = 1.8 / 4
    assert bv.f1_k_eff(1.0, 2.0) == pytest.approx(0.45)
    assert bv.f1_k_eff(1.0, -2.0) == pytest.approx(0.45)  # sign of the hedge does not matter
    assert bv.f1_k_eff(0.5, 2.0) == pytest.approx(0.25)  # VIX halved stays below the cap


def test_f2_overlay_scale_formula_and_vix():
    # h = 0.7: min(0.3, 0.8 / 2.7 = 0.2963)
    assert bv.f2_k2_eff(1.0, 0.7) == pytest.approx(0.8 / 2.7)
    # h = 0.1: 0.8 / 2.1 = 0.381 -> capped at 0.3
    assert bv.f2_k2_eff(1.0, 0.1) == pytest.approx(0.3)
    assert bv.f2_k2_eff(0.5, 0.1) == pytest.approx(0.15)


def test_gross_scale_only_when_above_cap():
    assert bv.gross_scale(1.0, 0.7) == 1.0
    assert bv.gross_scale(1.2, 0.9) == pytest.approx(1.8 / 2.1)


# ---------------------------------------------------------------------------
# margin
# ---------------------------------------------------------------------------
def test_maintenance_short_prices_3_8_20():
    qty = np.array([-100.0, -100.0, -100.0])
    price = np.array([3.0, 8.0, 20.0])
    # $3: max(2.5 * 100, 100% * 300) = 300; $8: max(5 * 100, 0.3 * 800 = 240) = 500;
    # $20: max(500, 0.3 * 2000 = 600) = 600
    assert bv.maintenance_requirement(qty, price) == pytest.approx(300 + 500 + 600)
    # boundaries: $5 is on the per-share $5 side, $16.67 crosses to 30%
    assert bv.maintenance_requirement(np.array([-10.0]), np.array([5.0])) == pytest.approx(50.0)
    assert bv.maintenance_requirement(np.array([-10.0]), np.array([2.0])) == pytest.approx(25.0)


def test_maintenance_long_prices_2_4_10():
    qty = np.array([100.0, 100.0, 100.0])
    price = np.array([2.0, 4.0, 10.0])
    # $2: 100% = 200; $4: 50% = 200; $10: 30% = 300
    assert bv.maintenance_requirement(qty, price) == pytest.approx(200 + 200 + 300)
    # boundary prices fall on the stricter side
    assert bv.maintenance_requirement(np.array([10.0]), np.array([2.5])) == pytest.approx(12.5)
    assert bv.maintenance_requirement(np.array([10.0]), np.array([6.0])) == pytest.approx(30.0)


def test_maintenance_ignores_nan_prices_and_flat_positions():
    qty = np.array([100.0, 0.0, -50.0])
    price = np.array([10.0, np.nan, 20.0])
    assert bv.maintenance_requirement(qty, price) == pytest.approx(300.0 + max(250.0, 300.0))


def test_initial_margin_is_half_of_gross():
    assert bv.initial_margin_requirement(900.0, 700.0) == pytest.approx(800.0)


# ---------------------------------------------------------------------------
# whole shares, $100 drop, netting
# ---------------------------------------------------------------------------
def test_round_half_away_array_matches_engine_function():
    xs = np.array([-2.5, -1.5, -0.5, -0.49, 0.0, 0.49, 0.5, 1.5, 2.5, 123.4999, -123.5])
    got = bv.round_half_away_array(xs)
    assert got.tolist() == [round_half_away(float(x)) for x in xs]


def test_aggregate_targets_rounds_and_drops_small_orders():
    p_ref = np.array([50.0, 200.0, 3.0])
    virtual = np.array([1.4, 0.7, 30.0])  # target 1, 1, 30
    current = np.zeros(3, dtype="int64")
    post, order, dropped = bv.aggregate_targets(virtual, p_ref, current)
    # 1 share of the $50 name is a $50 order -> dropped; 1 share of $200 kept; $90 order dropped
    assert order.tolist() == [0, 1, 0]
    assert dropped.tolist() == [True, False, True]
    assert post.tolist() == [0, 1, 0]


def test_aggregate_targets_shorts_round_away_from_zero():
    p_ref = np.array([400.0])
    post, order, _ = bv.aggregate_targets(np.array([-1.5]), p_ref, np.zeros(1, dtype="int64"))
    assert post.tolist() == [-2] and order.tolist() == [-2]


def test_netting_only_one_tranche_refreshes():
    n = 3
    p_ref = np.array([100.0, 100.0, 100.0])
    tranches = np.zeros((5, n))
    for o in range(5):
        tranches[o] = [0.4, -0.2, 0.0]  # every tranche holds 0.4 / -0.2 shares of a name
    qty = bv.aggregate_targets(tranches.sum(axis=0), p_ref, np.zeros(n, dtype="int64"))[0]
    assert qty.tolist() == [2, -1, 0]
    # one tranche refreshes: its names change, the other four stay as virtual shares
    tranches[3] = [0.0, 0.0, 0.6]
    post, order, dropped = bv.aggregate_targets(tranches.sum(axis=0), p_ref, qty)
    # new virtual sum: 1.6, -0.8, 0.6 -> 2, -1, 1; only the third name needs an order
    assert post.tolist() == [2, -1, 1]
    assert order.tolist() == [0, 0, 1]
    assert not dropped.any()


def test_virtual_shares_scale_and_missing_price():
    w = np.array([0.5, -0.5, 0.2])
    p = np.array([100.0, np.nan, 50.0])
    v = bv.virtual_shares(w, 0.5, 1_000_000.0, p)
    assert v[0] == pytest.approx(0.5 * 0.5 * 200_000.0 / 100.0)
    assert v[1] == 0.0  # no reference price
    assert v[2] == pytest.approx(0.2 * 0.5 * 200_000.0 / 50.0)


# ---------------------------------------------------------------------------
# delisting bound
# ---------------------------------------------------------------------------
def test_delist_adjustment_long_minus_30_short_zero():
    assert bv.delist_adjustment(100.0, 10.0) == pytest.approx(-300.0)
    assert bv.delist_adjustment(-100.0, 10.0) == 0.0
    assert bv.delist_adjustment(0.0, 10.0) == 0.0


def test_delist_flags_guard_of_five_sessions():
    close = np.full((20, 4), np.nan)
    close[:, 0] = 10.0  # alive to the end
    close[:10, 1] = 10.0  # last close at session 9 -> flagged (9 <= 14)
    close[:15, 2] = 10.0  # last close at session 14 -> flagged (boundary)
    close[:16, 3] = 10.0  # last close at session 15 -> inside the guard, not flagged
    last, flagged = bv.delist_flags(close)
    assert last.tolist() == [19, 9, 14, 15]
    assert flagged.tolist() == [False, True, True, False]


def test_debit_interest_is_actual_360_on_negative_cash_only():
    assert bv.debit_interest(100.0, 3) == 0.0
    assert bv.debit_interest(-10_000.0, 3) == pytest.approx(10_000 * 0.065 / 360 * 3)


# ---------------------------------------------------------------------------
# strategy rules identical to T-25
# ---------------------------------------------------------------------------
def _toy(n: int = 40, seed: int = 0):
    rng = np.random.default_rng(seed)
    names = pd.Index([f"S{i}" for i in range(n)])
    score = pd.Series(rng.standard_normal(n), index=names)
    ind = pd.Series(rng.integers(0, 4, n), index=names)
    elig = pd.Series(rng.random(n) > 0.3, index=names)
    beta = pd.Series(rng.uniform(0.3, 1.8, n), index=names)
    return names, score, ind, elig, beta


def test_rules_match_t25_copies():
    names, score, ind, elig, beta = _toy()
    pd.testing.assert_series_equal(bv.target_weights(score, ind), t25.target_weights(score, ind))
    w = bv.target_weights(score, ind)
    pd.testing.assert_series_equal(bv.restrict_shorts(w, elig), t25.restrict_shorts(w, elig))
    assert bv.hedge_size(w.to_numpy(), beta.to_numpy()) == t25.hedge_size(
        w.to_numpy(), beta.to_numpy()
    )
    for v in (float("nan"), 15.0, 20.6, 20.61, 40.0):
        assert bv.vix_scale(v) == t25.vix_scale(v)


def test_tranche_target_hedge_scales_exactly_with_vix_and_zeroes_missing_fills():
    names, score, ind, elig, beta = _toy()
    symbols = names.append(pd.Index(["X1", "X2"]))  # two names never in the universe
    fill_ok = np.ones(len(symbols), dtype=bool)
    fill_ok[3] = False
    calm = bv.tranche_target(score, ind, elig, symbols, fill_ok, beta, 15.0)
    storm = bv.tranche_target(score, ind, elig, symbols, fill_ok, beta, 30.0)
    assert calm.vscale == 1.0 and storm.vscale == 0.5
    assert calm.w_unit[3] == 0.0
    np.testing.assert_array_equal(storm.w_unit, calm.w_unit)
    assert storm.h == calm.h * 0.5  # exact: the VIX scale is a power of two
    assert storm.h_unit == calm.h_unit
    # short leg after the ETB restriction is -1 before the missing-fill zeroing
    assert calm.w_unit[calm.w_unit < 0].sum() <= 0.0
    assert calm.n_members == len(names)


# ---------------------------------------------------------------------------
# placebo arithmetic and regression helper (scripts)
# ---------------------------------------------------------------------------
def test_placebo_weights_match_tranche_target_on_permuted_scores():
    from scripts.book_v12_placebo import placebo_weights

    names, score, ind, elig, beta = _toy(60, seed=3)
    symbols = names
    fill_ok = np.ones(len(symbols), dtype=bool)
    fill_ok[[5, 17]] = False
    rng = np.random.default_rng(11)
    perm = score.copy()
    perm[:] = score.to_numpy()[rng.permutation(len(score))]
    ref = bv.tranche_target(perm, ind, elig, symbols, fill_ok, beta, 25.0)
    codes, uniq = pd.factorize(ind.reindex(names).fillna(-1).to_numpy())
    w0, h = placebo_weights(
        perm.to_numpy(),
        codes,
        len(uniq),
        elig.to_numpy(),
        fill_ok,
        beta.clip(-1.0, 4.0).to_numpy(),
        0.5,
    )
    np.testing.assert_allclose(w0, ref.w, atol=1e-14)
    assert h == pytest.approx(ref.h, abs=1e-13)


def test_newey_west_ols_recovers_exact_line_and_reports_r2_one():
    from scripts.book_v12_score import nw_ols

    rng = np.random.default_rng(1)
    x = rng.standard_normal((200, 2))
    y = 0.001 + x @ np.array([0.5, -0.3])
    out = nw_ols(y, x, lag=5)
    np.testing.assert_allclose(out["beta"], [0.001, 0.5, -0.3], atol=1e-10)
    assert out["r2"] == pytest.approx(1.0)
    noisy = nw_ols(y + 0.01 * rng.standard_normal(200), x, lag=5)
    assert noisy["t"][1] > 10
