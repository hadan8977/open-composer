from __future__ import annotations

import numpy as np

from open_composer.research.equity_book import book_v12 as bv
from open_composer.research.equity_book import engine_v2 as ev


def _data(seed: int = 0, length: int = 5, n: int = 40):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.02, (length, n))
    r[1, 3] = np.nan
    spy = rng.normal(0, 0.01, length)
    beta = rng.uniform(0.5, 1.5, n)
    x_old = rng.normal(0, 0.02, n)
    w = rng.normal(0, 0.02, n)
    return r, spy, beta, x_old, w


def test_no_deferral_equals_hold_block():
    r, spy, beta, x_old, w = _data()
    h0 = float(-np.nansum(w * beta))
    ref = bv.hold_block(w, r, spy, h0=h0)
    out = ev.deferred_block(x_old, w, np.zeros(len(w), dtype=int), r, spy, beta, h_prev=0.3)
    assert np.max(np.abs(out["pnl"] - ref["pnl"])) < 1e-15
    assert np.max(np.abs(out["w_end"] - ref["w_end"])) < 1e-15
    assert abs(out["h_end"] - ref["h_end"]) < 1e-15
    assert np.max(np.abs(out["short_notional"] - ref["short_notional"])) < 1e-15
    assert np.allclose(out["d_w"][0], w - x_old, atol=0, rtol=0)
    assert not out["d_w"][1:].any()
    assert abs(out["d_h"][0] - (h0 - 0.3)) < 1e-15
    assert not out["d_h"][1:].any()


def test_deferred_trade_conserves_target_and_pnl_split():
    r, spy, beta, x_old, w = _data(1)
    ex = np.zeros(len(w), dtype=int)
    ex[:10] = 3
    out = ev.deferred_block(x_old, w, ex, r, spy, beta, h_prev=0.0)
    # deferred names are held at the old size until day 3, then at the target (drifted)
    g = np.cumprod(1.0 + np.where(np.isfinite(r), r, 0.0), axis=0)
    gb = np.vstack([np.ones((1, r.shape[1])), g[:-1]])
    assert np.isclose(out["d_w"][3, 0], w[0] - x_old[0] * gb[3, 0])
    assert out["d_w"][0, 0] == 0.0 and out["d_w"][0, 20] == w[20] - x_old[20]
    assert np.isclose(out["w_end"][0], w[0] * g[-1, 0] / gb[3, 0])
    assert out["d_h"][1] == 0.0 and out["d_h"][3] != 0.0


def test_defer_days_rule():
    delta = np.array([1.0, -1.0, 1.0, 0.0, 1.0])
    zf = np.zeros((5, 5))
    zf[0] = [
        -2.0,
        2.0,
        2.0,
        -2.0,
        -0.2,
    ]  # buy vs z<0: wait; sell vs z>0: wait; ok; delta 0: go; weak
    zf[1] = [-2.0, 2.0, 0.0, 0.0, 0.0]
    zf[2] = [0.0, 2.0, 0.0, 0.0, 0.0]
    zf[3] = [0.0, 2.0, 0.0, 0.0, 0.0]
    zf[4] = [0.0, 2.0, 0.0, 0.0, 0.0]
    d = ev.defer_days(delta, zf, 0.5)
    assert d.tolist() == [2, 4, 0, 0, 0]
    d0 = ev.defer_days(delta, zf, 0.0)
    assert d0.tolist() == [2, 4, 0, 0, 1]  # c = 0 also waits on the weak -0.2
    assert ev.defer_days(delta, zf, None).tolist() == [0] * 5
    assert ev.defer_days(delta, zf[:2], 0.5).tolist() == [1, 1, 0, 0, 0]  # cap = L - 1 = 1


def test_partial_adjust_and_gp_weights():
    x_old = np.array([0.1, -0.1, 0.2, 0.0])
    aim = np.array([0.3, 0.1, 0.0, 0.2])
    el = np.array([True, False, True, True])
    ok = np.array([True, True, False, True])
    x = ev.partial_adjust(x_old, aim, 0.5, el, ok)
    assert np.allclose(x, [0.2, 0.0, 0.0, 0.1])
    w = ev.gp_weights({"slow": 0.015, "fast": 0.0034}, {"slow": 0.0, "fast": 0.3689}, 0.1)
    assert np.isclose(w["slow"], 0.015) and np.isclose(w["fast"], 0.0034 / (1 + 3.689))
    assert abs(ev.phi_from_half_life(2.0) - 0.34657359) < 1e-8
    s = ev.combine_score(np.array([1.0, np.nan, 0.5]), np.array([np.nan, 1.0, 1.0]), 0.5)
    assert np.isnan(s[1]) and s[0] == 1.0 and s[2] == 1.0


def test_hash_rank_placebo_keeps_values_and_is_quarter_stable():
    import pandas as pd

    from scripts import t0701_engine as eng

    names = pd.Index([f"S{i}" for i in range(50)])
    z = pd.Series(np.linspace(-2, 2, 50), index=names)
    z.iloc[3] = np.nan
    t1, t2 = pd.Timestamp("2024-01-10"), pd.Timestamp("2024-02-20")  # same quarter
    a = eng.hash_rank_assign(z, 5, t1, 1)
    b = eng.hash_rank_assign(z, 5, t2, 1)
    c = eng.hash_rank_assign(z, 6, t1, 1)
    assert np.allclose(np.sort(a.dropna()), np.sort(z.dropna()))
    assert a.isna().equals(z.isna())
    assert a.equals(b) and not a.equals(c)
    assert not a.equals(z)
