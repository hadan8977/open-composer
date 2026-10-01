from __future__ import annotations

import math

import numpy as np
import pandas as pd

from scripts import diag_s0_hedged_books as d


def _calendar(n: int = 90) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=n)


def test_spy_only_book_reproduces_spy_open_to_open_returns() -> None:
    cal = _calendar(90)
    rng = np.random.default_rng(1)
    spy_open = 100 * np.cumprod(1 + rng.normal(0, 0.01, len(cal)))
    spy_close = spy_open * (1 + rng.normal(0, 0.003, len(cal)))
    me = d.month_end_positions(cal)[:-1]  # complete months only
    e_pos = me + 1
    pairs = [(e, x) for e, x in zip(e_pos[:-1], me[1:] + 1, strict=True)]
    # the same call path used for stocks, applied to a one-column SPY matrix
    spy_ret = np.array(
        [
            d.open_to_open_returns(spy_open[:, None], spy_close[:, None], e, x)[0][0]
            for e, x in pairs
        ]
    )
    expected = np.array([spy_open[x] / spy_open[e] - 1.0 for e, x in pairs])
    np.testing.assert_array_equal(spy_ret, expected)

    n_total = 3  # two stocks + SPY at index 2
    weights = [np.array([0.0, 0.0, 1.0]) for _ in pairs]
    rets = [np.array([0.01, -0.02, r]) for r in spy_ret]
    gross, turn = d.simulate_book(weights, rets)
    np.testing.assert_allclose(gross, expected, rtol=0, atol=1e-15)
    assert n_total == len(weights[0])
    # first period builds the position, later periods only trade the drift back to 1
    assert turn[0] == 1.0
    for k in range(1, len(pairs)):
        r_prev = spy_ret[k - 1]
        drifted = (1.0 + r_prev) / (1.0 + r_prev)
        assert math.isclose(turn[k], abs(1.0 - drifted), abs_tol=1e-12)


def test_two_stock_panel_hand_computed_long_short_and_hedge() -> None:
    # slots: A=0, B=1, SPY=2. A is the top score, B the bottom score.
    ids = np.array([0, 1])
    score = np.array([2.0, -1.0])
    adv = np.array([1.0, 2.0])
    beta = np.array([1.5, 0.5])
    w, lg, sh = d.build_weights(3, ids, score, adv, beta, "LS_BH", 2)
    np.testing.assert_allclose(w, [1.0, -1.0, -(1.5 - 0.5)])
    assert lg.tolist() == [0] and sh.tolist() == [1]
    w_raw, _, _ = d.build_weights(3, ids, score, adv, beta, "LS_RAW", 2)
    np.testing.assert_allclose(w_raw, [1.0, -1.0, 0.0])
    w_lo, _, _ = d.build_weights(3, ids, score, adv, beta, "LONG_ONLY_TOP", 2)
    np.testing.assert_allclose(w_lo, [1.0, 0.0, 0.0])

    r1 = np.array([0.10, 0.02, 0.04])  # A +10%, B +2%, SPY +4%
    r2 = np.array([-0.05, 0.01, 0.00])
    gross, turn = d.simulate_book([w, w], [r1, r2])
    # period 1: +0.10 - 0.02 - 1.0 * 0.04 = 0.04
    assert math.isclose(gross[0], 0.04, abs_tol=1e-15)
    # period 2 with the same target weights: P&L = -0.05 - 0.01 - 0 = -0.06
    assert math.isclose(gross[1], -0.06, abs_tol=1e-15)
    assert math.isclose(turn[0], 3.0, abs_tol=1e-15)  # |1| + |-1| + |-1|
    drift = w * (1 + r1) / (1 + 0.04)
    assert math.isclose(turn[1], float(np.abs(w - drift).sum()), abs_tol=1e-15)
    net = gross - d.COST_10 * turn
    assert math.isclose(net[0], 0.04 - 0.0010 * 3.0, abs_tol=1e-15)


def test_size_neutral_selects_decile_inside_each_bucket() -> None:
    n = 100  # 5 buckets of 20 -> 2 long + 2 short each
    adv = np.arange(1, n + 1, dtype=float)
    rng = np.random.default_rng(3)
    score = rng.normal(size=n)
    lg, sh = d.select_legs(score, adv, size_neutral=True)
    assert len(lg) == 10 and len(sh) == 10
    for b in range(5):
        lo, hi = b * 20, (b + 1) * 20
        bucket = np.arange(lo, hi)
        order = bucket[np.argsort(score[bucket])]
        assert set(order[-2:]) <= set(lg.tolist())
        assert set(order[:2]) <= set(sh.tolist())
    lg2, sh2 = d.select_legs(score, adv, size_neutral=False)
    assert len(lg2) == 10 and set(lg2) == set(np.argsort(score)[-10:])


def test_open_to_open_uses_last_close_when_exit_open_missing() -> None:
    op = np.array([[10.0, 10.0], [11.0, 10.0], [12.0, 10.0], [13.0, np.nan]])
    cl = np.array([[10.5, 10.0], [11.5, 10.5], [12.5, 11.0], [13.5, np.nan]])
    ret, fb = d.open_to_open_returns(op, cl, 0, 3)
    assert math.isclose(ret[0], 13.0 / 10.0 - 1.0)
    assert math.isclose(ret[1], 11.0 / 10.0 - 1.0)  # last valid close in [0, 3) is 11.0
    assert fb.tolist() == [False, True]
    ret2, _ = d.open_to_open_returns(np.where(np.isnan(op), np.nan, op), cl, 1, 3)
    assert math.isclose(ret2[0], 13.0 / 11.0 - 1.0)


def test_split_like_ratio_detects_common_multiples_only() -> None:
    r = np.array([0.5, 2.0, 1.01, 0.97, 3.0, 1.35, np.nan, -1.0])
    out = d.is_split_like_ratio(r)
    assert out.tolist() == [True, True, False, False, True, False, False, False]


def test_comp4_missing_contributes_zero_and_all_missing_is_nan() -> None:
    mom = np.array([1.0, 2.0, 3.0, np.nan, 5.0])
    on = np.array([5.0, 4.0, 3.0, np.nan, 1.0])
    gp = np.array([np.nan, 1.0, 2.0, np.nan, 3.0])
    sue = np.array([np.nan, np.nan, np.nan, np.nan, 7.0])
    s = d.comp4(mom, on, gp, sue)
    assert np.isnan(s[3])
    z_m, z_o = d.zscore_winsor(mom), d.zscore_winsor(on)
    z_g = d.zscore_winsor(gp)
    assert math.isclose(s[0], (z_m[0] + z_o[0]) / 4.0)
    assert math.isclose(s[1], (z_m[1] + z_o[1] + z_g[1]) / 4.0)


def test_zscore_winsor_clips_at_three() -> None:
    x = np.concatenate([np.zeros(200), [1000.0]])
    z = d.zscore_winsor(x)
    assert z.max() == 3.0 and np.isfinite(z).all()


def test_newey_west_matches_plain_t_for_iid_noise_roughly_and_zero_lag() -> None:
    rng = np.random.default_rng(5)
    x = rng.normal(0.01, 0.05, 400)
    plain = x.mean() / (x.std(ddof=0) / math.sqrt(len(x)))
    assert abs(d.newey_west_t(x, lags=0) - plain) < 1e-9
    assert abs(d.newey_west_t(x, lags=3) - plain) < 0.5


def test_trailing_scaled_uses_only_returns_known_at_formation() -> None:
    rng = np.random.default_rng(7)
    net = rng.normal(0.0, 0.02, 60)
    base = d.trailing_scaled(net)
    assert np.isnan(base[:13]).all() and np.isfinite(base[14:]).all()
    changed = net.copy()
    k = 40
    changed[k - 1] += 0.5  # period k-1 exits at the period-k entry open: unknown at formation
    changed2 = net.copy()
    changed2[k + 1] += 0.5  # a future return
    assert math.isclose(d.trailing_scaled(changed)[k], base[k])
    assert math.isclose(d.trailing_scaled(changed2)[k], base[k])
    changed3 = net.copy()
    changed3[k - 2] += 0.5  # known: must move the scale
    assert not math.isclose(d.trailing_scaled(changed3)[k], base[k])


def test_series_stats_and_beta_corr() -> None:
    r = np.array([0.02, -0.01, 0.03, 0.01, -0.02, 0.04] * 4)
    st = d.series_stats(r)
    assert math.isclose(st["sharpe"], r.mean() / r.std(ddof=1) * math.sqrt(12))
    assert st["max_dd"] <= 0
    spy = r * 2.0
    b, c = d.beta_corr(r, spy)
    assert math.isclose(b, 0.5) and math.isclose(c, 1.0)
    assert d.max_drawdown(np.array([0.1, -0.5, 0.2])) == -0.5


def test_window_masks_partition_formations() -> None:
    dates = pd.date_range("2017-10-31", "2026-08-31", freq="ME")
    st, gp, an = (d.window_mask(dates.to_numpy(), w) for w in ("stress", "gap", "anchor"))
    assert (st.astype(int) + gp.astype(int) + an.astype(int)).tolist() == [1] * len(dates)
    assert gp.sum() == 5
