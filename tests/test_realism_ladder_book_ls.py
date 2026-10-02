"""Tests for the pure rules of scripts/realism_ladder_book_ls.py (synthetic data)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import realism_ladder_book_ls as L


def test_target_weights_industry_neutral_long_short_one():
    names = list("abcdefgh")
    score = pd.Series([3.0, 1.0, -1.0, -3.0, 2.0, 0.0, -2.0, 5.0], index=names)
    ind = pd.Series([1, 1, 1, 1, 2, 2, 2, 2], index=names)
    w = L.target_weights(score, ind)
    assert w.abs().sum() == pytest.approx(2.0)
    assert w[w > 0].sum() == pytest.approx(1.0)
    assert w[w < 0].sum() == pytest.approx(-1.0)
    assert w.groupby(ind).sum().abs().max() < 1e-12  # industry neutral


def test_target_weights_drops_nan_and_handles_flat():
    s = pd.Series([1.0, np.nan, -1.0, 0.5], index=list("abcd"))
    w = L.target_weights(s, pd.Series(0, index=s.index))
    assert "b" not in w.index
    assert w.abs().sum() == pytest.approx(2.0)
    flat = L.target_weights(
        pd.Series([1.0, 1.0], index=["x", "y"]), pd.Series([0, 0], index=["x", "y"])
    )
    assert (flat == 0).all()


def test_restrict_shorts_renormalises_short_leg_to_minus_one():
    w = pd.Series([0.5, 0.5, -0.25, -0.5, -0.25], index=list("abcde"))
    elig = pd.Series([True, True, True, False, True], index=w.index)
    out = L.restrict_shorts(w, elig)
    assert out["d"] == 0.0
    assert out[out < 0].sum() == pytest.approx(-1.0)
    assert out["c"] == pytest.approx(-0.5) and out["e"] == pytest.approx(-0.5)
    assert out[["a", "b"]].tolist() == [0.5, 0.5]  # longs untouched


def test_restrict_shorts_no_eligible_short_leaves_zero_short_leg():
    w = pd.Series([1.0, -1.0], index=["a", "b"])
    out = L.restrict_shorts(w, pd.Series([False, False], index=w.index))
    assert out["b"] == 0.0 and out["a"] == 1.0


def test_hedge_size_offsets_weighted_beta():
    w = np.array([0.5, 0.5, -1.0])
    beta = np.array([1.0, 1.4, 0.8])
    h = L.hedge_size(w, beta)
    assert h == pytest.approx(-(0.5 + 0.7 - 0.8))
    assert (w * beta).sum() + h == pytest.approx(0.0)


def test_vix_scale_halves_only_above_threshold_and_ignores_nan():
    assert L.vix_scale(20.60) == 1.0
    assert L.vix_scale(20.61) == 0.5
    assert L.vix_scale(float("nan")) == 1.0


def test_decision_positions_weekly_offsets_partition_the_days():
    allp = []
    for o in range(5):
        p = L.decision_positions(100, 7, 90, 5, o)
        assert all(x % 5 == o and 7 <= x <= 90 for x in p)
        assert np.diff(p).tolist() == [5] * (len(p) - 1)
        allp += p
    assert sorted(allp) == list(range(7, 91))
    assert L.decision_positions(100, 7, 90, 1, 0) == list(range(7, 91))


def test_hold_block_drift_and_fixed_shares():
    # one long (w=1) with returns +10%, +10%: P&L 0.10 then 0.11 (position drifts up)
    w0 = np.array([1.0, 0.0])
    r = np.array([[0.1, 0.0], [0.1, 0.0]])
    spy = np.array([0.0, 0.0])
    b = L.hold_block(w0, r, spy)
    assert b["pnl"].tolist() == pytest.approx([0.10, 0.11])
    assert b["w_end"].tolist() == pytest.approx([1.21, 0.0])
    # a short drifts the other way: -10% price -> short value shrinks
    s = L.hold_block(np.array([-1.0]), np.array([[-0.1], [0.0]]), np.zeros(2))
    assert s["pnl"].tolist() == pytest.approx([0.1, 0.0])
    assert s["w_end"][0] == pytest.approx(-0.9)
    assert s["short_notional"].tolist() == pytest.approx([1.0, 0.9])


def test_hold_block_spy_hedge_in_fixed_shares_and_stock_beta_hedge():
    w0 = np.array([1.0])
    r = np.array([[0.02], [0.02]])
    spy = np.array([0.01, 0.01])
    # SPY hedge of -0.8 in shares: gains/losses scale with SPY's own growth
    b = L.hold_block(w0, r, spy, h0=-0.8)
    assert b["hedge_pnl"].tolist() == pytest.approx([-0.8 * 0.01, -0.8 * 1.01 * 0.01])
    assert b["h_end"] == pytest.approx(-0.8 * 1.01 * 1.01)
    # per-stock beta hedge (R0 convention): pnl = w G (r - beta r_spy)
    c = L.hold_block(w0, r, spy, beta=np.array([1.5]))
    assert c["pnl"][0] == pytest.approx(0.02 - 1.5 * 0.01)
    assert c["pnl"][1] == pytest.approx(1.02 * (0.02 - 1.5 * 0.01))


def test_hold_block_missing_return_counts_as_zero():
    b = L.hold_block(np.array([1.0, -1.0]), np.array([[np.nan, 0.01]]), np.zeros(1))
    assert b["pnl"][0] == pytest.approx(-0.01)
    assert b["w_end"][0] == pytest.approx(1.0)
