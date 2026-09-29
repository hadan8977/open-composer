"""Tests for T-20260929-12's two scripts:

``scripts/build_h20260929_12_ensembles.py``
    ``ranked_candidates`` must read only the select-window ICIR (never a
    ``test_*`` field), ``select_window_mask``/``pct_select_window`` must
    restrict strictly to the select window, and ``dense_pool``/
    ``greedy_dedup`` must not touch any 2024+ data.
``scripts/run_h20260929_12_hedged_books.py``
    ``build_top50_weights`` must shift formation dates by the given offset
    and fill next-session-open; ``hedge_weight_series`` must use only past
    (as-of-the-signal-close) returns and must reproduce the beta/(1+beta)
    SH-weight formula exactly, with the beta cap respected. ``simulate_book``
    (the close-to-close leg-mixing engine that replaced the first,
    subsequently-voided open-to-open convention) must reproduce
    ``run_h20260922_05_salvage.simulate`` -- the actual frozen lane engine --
    exactly for a single-instrument book, and ``stock_legs`` must match
    ``run_h20260922_05_salvage.legs``'s own formula.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_h20260929_12_ensembles as build_mod  # noqa: E402
import run_h20260922_05_salvage as salvage_mod  # noqa: E402
import run_h20260929_12_hedged_books as books_mod  # noqa: E402

# --------------------------------------------------------------------- build


def test_ranked_candidates_reads_only_select_window_icir(tmp_path, monkeypatch):
    """A candidate with a `select_21d.icir` of `None` (e.g. insufficient
    sample) is dropped; the sort must use `select_21d.icir`, never any
    `test_*` field, even if the fixture also carries one (2024+ leakage
    guard)."""
    fixture = {
        "results": {
            "zoo_a": {
                "select_21d": {"icir": 0.10, "n": 500},
                "sign_from_select": 1,
                "test_21d": {"icir": 99.0},  # must be ignored
            },
            "zoo_b": {"select_21d": {"icir": -0.30, "n": 500}, "sign_from_select": -1},
            "zoo_c": {"select_21d": {"icir": None, "n": 10}, "sign_from_select": 1},
            "card_comp_c1_mom_quality": {
                "select_21d": {"icir": 0.99, "n": 500},
                "sign_from_select": 1,
            },
        }
    }
    fixture_path = tmp_path / "select-results.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr(build_mod, "SELECT_RESULTS", fixture_path)

    ranked = build_mod.ranked_candidates()
    ids = [cid for cid, _icir, _sign in ranked]

    assert "zoo_c" not in ids, "candidate with icir=None must be dropped"
    assert "card_comp_c1_mom_quality" not in ids, "nested composite cards must be excluded"
    assert ids[0] == "zoo_b", "ranking must sort by |select_21d.icir|, not test_21d.icir"
    assert ranked[0][1] == -0.30
    assert ranked[0][2] == -1


def test_select_window_mask_excludes_test_window_dates():
    dates = pd.DatetimeIndex(
        ["2016-05-01", "2016-06-01", "2020-01-01", "2023-12-29", "2024-01-02", "2026-09-08"]
    )
    mask = build_mod.select_window_mask(dates)
    assert mask.tolist() == [False, True, True, True, False, False]


def test_greedy_dedup_skips_correlated_and_respects_icir_order():
    """Two identical (perfectly correlated) factors: the second must be
    skipped once the correlation threshold is exceeded, regardless of its
    own icir rank."""
    rng = np.random.default_rng(3)
    n_days, n_names = 200, 60
    base_pct = rng.uniform(0.0, 1.0, size=(n_days, n_names)).astype(np.float32)
    unrelated_pct = rng.uniform(0.0, 1.0, size=(n_days, n_names)).astype(np.float32)
    pool = [("dup_a", 0.30, 1), ("dup_b", 0.25, 1), ("distinct", 0.20, 1)]
    cache = {"dup_a": base_pct, "dup_b": base_pct.copy(), "distinct": unrelated_pct}
    chosen = build_mod.greedy_dedup(pool, cache, k=3)
    chosen_ids = [c for c, _s in chosen]
    assert "dup_a" in chosen_ids
    assert "dup_b" not in chosen_ids, "near-duplicate (corr>0.70) must be skipped"
    assert "distinct" in chosen_ids


def test_dense_pool_keeps_only_sufficiently_covered_factors(monkeypatch):
    """A sparse factor (low per-day coverage, like the real
    F10_quality_composite_roe_profitability_accruals case found during
    development) must be excluded from R40's pool even if it ranks first by
    |icir|; a dense factor must be kept."""

    class FakeMarket:
        def __init__(self):
            self.open_ = np.zeros((10, 4), dtype=np.float32)

        def member(self):
            return np.ones((10, 4), dtype=bool)

    market = FakeMarket()
    sparse = np.full((10, 4), np.nan, dtype=np.float32)
    sparse[0, 0] = 1.0  # covers 1 of 40 cells
    dense = np.ones((10, 4), dtype=np.float32)

    def fake_load_candidate(_market, cid):
        return {"sparse": sparse, "dense": dense}[cid]

    monkeypatch.setattr(build_mod.t15, "_load_candidate", fake_load_candidate)
    ranked = [("sparse", 0.99, 1), ("dense", 0.10, 1)]
    pool = build_mod.dense_pool(market, ranked, k=2, min_coverage=0.30, t0=0.0)
    ids = [c for c, _i, _s in pool]
    assert "sparse" not in ids
    assert "dense" in ids


# --------------------------------------------------------------------- books


def test_build_top50_weights_offset_shifts_formation_dates():
    """A larger offset must move the signal (and therefore the weight
    change) to a later session within the same month -- the whole point of
    the offset sweep."""
    dates = pd.bdate_range("2023-01-02", periods=80)
    rng = np.random.default_rng(5)
    score = rng.uniform(0.0, 1.0, size=(len(dates), 20)).astype(np.float32)
    w0, skipped0 = books_mod.build_top50_weights(score, dates, offset=0, top_k=5, min_eligible=5)
    w5, skipped5 = books_mod.build_top50_weights(score, dates, offset=5, top_k=5, min_eligible=5)
    assert skipped0 == 0
    assert skipped5 == 0
    first_change_0 = np.argmax(np.diff(w0.sum(axis=1) > 0))
    first_change_5 = np.argmax(np.diff(w5.sum(axis=1) > 0))
    assert first_change_5 > first_change_0, "offset=5 must push the first rebalance later"


def test_build_top50_weights_skips_month_with_too_few_eligible():
    dates = pd.bdate_range("2023-01-02", periods=40)
    score = np.full((len(dates), 10), np.nan, dtype=np.float32)
    score[:, :3] = 1.0  # only 3 eligible names, below min_eligible
    weights, skipped = books_mod.build_top50_weights(
        score, dates, offset=0, top_k=5, min_eligible=5
    )
    assert skipped >= 1
    assert weights.sum() == 0.0, "a skipped month must hold zero stock exposure"


def test_hedge_weight_series_uses_only_past_returns():
    """Perturbing a return strictly AFTER a signal date must not change the
    hedge weight that became effective at that signal date (no look-ahead)."""
    dates = pd.bdate_range("2023-01-02", periods=200)
    rng = np.random.default_rng(7)
    underlying = rng.normal(0.0, 0.01, size=len(dates))
    stock = 0.8 * underlying + rng.normal(0.0, 0.01, size=len(dates))
    sig_dates = [dates[60], dates[120]]

    hedge_w_a, scale_a = books_mod.hedge_weight_series(
        stock, underlying, dates, sig_dates, lookback=63, cap=(0.0, 1.5)
    )

    stock_perturbed = stock.copy()
    stock_perturbed[121:] += 5.0  # large shock strictly after the second signal date
    hedge_w_b, scale_b = books_mod.hedge_weight_series(
        stock_perturbed, underlying, dates, sig_dates, lookback=63, cap=(0.0, 1.5)
    )

    # Values up to and including the session the second signal takes effect
    # (index 121, the open right after sig_dates[1] at index 120) must be
    # identical; only later values may legitimately diverge because of the
    # *next* rebalance recomputing beta over a window that now includes the
    # shock. There is no later rebalance in this fixture, so everything
    # through the end must match up to the point the perturbation starts.
    np.testing.assert_array_equal(hedge_w_a[:121], hedge_w_b[:121])
    np.testing.assert_array_equal(scale_a[:121], scale_b[:121])


def test_hedge_weight_series_beta_formula_and_cap():
    """hedge_weight must equal beta/(1+beta) and stock_scale = 1/(1+beta)
    for a hand-computed beta, and must saturate at the cap for an extreme
    input."""
    dates = pd.bdate_range("2023-01-02", periods=100)
    rng = np.random.default_rng(11)
    underlying = rng.normal(0.0, 0.01, size=len(dates))
    true_beta = 0.6
    stock = true_beta * underlying  # noiseless -> beta estimate == true_beta exactly
    sig_dates = [dates[80]]

    hedge_w, scale = books_mod.hedge_weight_series(
        stock, underlying, dates, sig_dates, lookback=63, cap=(0.0, 1.5)
    )
    expected_hedge = true_beta / (1.0 + true_beta)
    expected_scale = 1.0 / (1.0 + true_beta)
    assert hedge_w[81] == pytest.approx(expected_hedge, abs=1e-6)
    assert scale[81] == pytest.approx(expected_scale, abs=1e-6)

    # Extreme negative co-movement must saturate at the lower cap (0.0), not
    # go negative.
    stock_inverted = -2.0 * underlying
    hedge_w2, scale2 = books_mod.hedge_weight_series(
        stock_inverted, underlying, dates, sig_dates, lookback=63, cap=(0.0, 1.5)
    )
    assert hedge_w2[81] == pytest.approx(0.0, abs=1e-9)
    assert scale2[81] == pytest.approx(1.0, abs=1e-9)

    # Extreme positive co-movement must saturate at the upper cap (1.5).
    stock_extreme = 10.0 * underlying
    hedge_w3, _scale3 = books_mod.hedge_weight_series(
        stock_extreme, underlying, dates, sig_dates, lookback=63, cap=(0.0, 1.5)
    )
    expected_hedge_capped = 1.5 / (1.0 + 1.5)
    assert hedge_w3[81] == pytest.approx(expected_hedge_capped, abs=1e-6)


def test_build_hedged_book_zero_hedge_weight_reduces_to_long_only():
    """With hedge_weight identically zero and stock_scale identically one,
    ``build_hedged_book`` must reduce to the plain long-only
    ``simulate_book`` result (sanity check that the hedge overlay adds
    nothing when beta is estimated as zero)."""
    dates = pd.bdate_range("2023-01-02", periods=30)
    rng = np.random.default_rng(13)
    n = len(dates)
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, size=(n, 5)), axis=0)
    open_ = close + rng.normal(0.0, 0.2, size=(n, 5))
    leg_open, leg_close = books_mod.stock_legs(open_, close)
    hedge_close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, size=n))
    hedge_open = hedge_close + rng.normal(0.0, 0.2, size=n)
    hedge_leg_open, hedge_leg_close = books_mod.stock_legs(
        hedge_open.reshape(-1, 1), hedge_close.reshape(-1, 1)
    )

    weights = np.zeros((n, 5), dtype=np.float64)
    weights[:, 0] = 0.5
    weights[:, 1] = 0.5
    hedge_w = np.zeros(n)
    stock_scale = np.ones(n)

    net_combined, _turn = books_mod.build_hedged_book(
        weights,
        leg_open,
        leg_close,
        hedge_leg_open[:, 0],
        hedge_leg_close[:, 0],
        hedge_w,
        stock_scale,
        10.0,
    )
    net_plain, _turn_plain = books_mod.simulate_book(weights, leg_open, leg_close, 10.0)
    np.testing.assert_allclose(net_combined, net_plain, atol=1e-10)


# ------------------------------------------------------------- alignment fix
#
# Second, deeper convention bug (coordinator review, 2026-09-29): S3
# (``screen_lane.s3_incumbent`` -> ``salvage.simulate``) is not an
# open-to-open series at all -- it splits every rebalance day at the open
# (old weights earn the overnight gap, new weights earn the intraday move),
# so row t of S3's own return is a CLOSE-TO-CLOSE realized return. These
# tests check the replacement leg-mixing engine (``simulate_book``,
# ``stock_legs``, ``build_hedged_book``) against the actual frozen lane
# engine (``run_h20260922_05_salvage``), not just against itself.


def test_stock_legs_matches_salvage_legs_formula():
    """``stock_legs`` (applied to a bare (T,N) numpy panel) must produce the
    identical leg_open/leg_close values as ``salvage.legs`` (applied to the
    equivalent pandas DataFrame), row 0 aside -- ``salvage.legs`` fills row
    0's undefined overnight leg with 0.0 via ``.fillna(0.0)``, while
    ``stock_legs`` leaves it NaN and lets ``simulate_book`` fill it (the
    same effective value, checked separately by the single-asset test
    below)."""
    dates = pd.bdate_range("2023-01-02", periods=10)
    rng = np.random.default_rng(29)
    close = rng.uniform(90.0, 110.0, size=(len(dates), 3))
    open_ = rng.uniform(90.0, 110.0, size=(len(dates), 3))
    leg_open, leg_close = books_mod.stock_legs(open_, close)

    close_df = pd.DataFrame(close, index=dates, columns=["a", "b", "c"])
    open_df = pd.DataFrame(open_, index=dates, columns=["a", "b", "c"])
    expected_leg_open, expected_leg_close = salvage_mod.legs(close_df, open_df)

    np.testing.assert_allclose(leg_open[1:], expected_leg_open.to_numpy()[1:], atol=1e-12)
    np.testing.assert_allclose(leg_close, expected_leg_close.to_numpy(), atol=1e-12)


def test_simulate_book_matches_salvage_simulate_for_single_asset():
    """The coordinator's required end-to-end regression: a synthetic book
    that holds only one instrument, run through this iteration's own
    ``simulate_book``, must exactly reproduce
    ``run_h20260922_05_salvage.simulate`` -- the actual frozen lane engine
    S3 itself is built from -- given the same inputs. With ``scale=1``
    everywhere, ``salvage.simulate``'s CASH-column remix is a no-op (`w`
    reduces to the raw target weights), so a 2-column [instrument, CASH]
    panel is the fair, literal comparison."""
    dates = pd.bdate_range("2023-01-02", periods=60)
    rng = np.random.default_rng(23)
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0, 0.01, size=len(dates)))), index=dates)
    close_df = pd.DataFrame({"SPY": px, salvage_mod.CASH: 1.0}, index=dates)
    open_df = pd.DataFrame(
        {
            "SPY": px * (1.0 + rng.normal(0.0, 0.002, size=len(dates))),
            salvage_mod.CASH: 1.0,
        },
        index=dates,
    )
    leg_open_df, leg_close_df = salvage_mod.legs(close_df, open_df)

    weights_df = pd.DataFrame(
        {"SPY": np.ones(len(dates)), salvage_mod.CASH: np.zeros(len(dates))}, index=dates
    )
    scale = np.ones(len(dates))
    expected_ret, expected_turn = salvage_mod.simulate(
        weights_df, leg_open_df, leg_close_df, scale, cost_bps=10.0
    )

    cols = ["SPY", salvage_mod.CASH]
    weights_arr = weights_df[cols].to_numpy(dtype=np.float64)
    leg_open_arr = leg_open_df[cols].to_numpy(dtype=np.float64)
    leg_close_arr = leg_close_df[cols].to_numpy(dtype=np.float64)
    got_ret, got_turn = books_mod.simulate_book(weights_arr, leg_open_arr, leg_close_arr, 10.0)

    np.testing.assert_allclose(got_ret, expected_ret.to_numpy(), atol=1e-12)
    np.testing.assert_allclose(got_turn, expected_turn.to_numpy(), atol=1e-12)
