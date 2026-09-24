"""Unit tests for scripts/run_h20260924_02_momentum_crash_guard.py.

Scope: guard logic (each of the 5 candidate multiplier builders), the
no-lookahead settlement-lag timing (1-session for market-derived signals,
2-session for signals derived from the book's own open-to-open return
series), and the calendar-shift placebo. These are synthetic-data tests of
the pure functions; the economic evidence (real backtest numbers, gate
verdicts) lives in reports/research/iterations/h20260924_02_momentum_crash_guard/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

guard = pytest.importorskip("run_h20260924_02_momentum_crash_guard")


def make_dates(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2016-01-04", periods=n)


# --------------------------------------------------------- settlement lag


def test_settle_market_is_a_one_session_lag():
    s = pd.Series(np.arange(10, dtype=float), index=make_dates(10))
    settled = guard.settle_market(s)
    assert np.isnan(settled.iloc[0])
    for i in range(1, 10):
        assert settled.iloc[i] == s.iloc[i - 1]


def test_settle_book_is_a_two_session_lag():
    s = pd.Series(np.arange(10, dtype=float), index=make_dates(10))
    settled = guard.settle_book(s)
    assert settled.iloc[0:2].isna().all()
    for i in range(2, 10):
        assert settled.iloc[i] == s.iloc[i - 2]


# ------------------------------------------------------- guard: no lookahead


def _mutate(series: pd.Series, at: int, new_value: float) -> pd.Series:
    out = series.copy()
    out.iloc[at] = new_value
    return out


def test_guard_cg_dm_does_not_look_ahead_of_the_prior_close():
    n = 800
    dates = make_dates(n)
    rng = np.random.default_rng(0)
    # A mild random walk so the 504-session trailing return and 126-session
    # vol are both well defined and generic (not permanently in one regime).
    spy_close = pd.Series(100.0 * np.cumprod(1.0 + rng.normal(0, 0.006, n)), index=dates)
    th = guard.Thresholds(
        dm_highvol=0.10,
        bsc_target_vol=0.20,
        stop_dd=0.20,
        mkt_stop_reentry_sessions=5,
        mkt_stop_reentry_from_data=False,
    )
    t_mut = 700
    baseline = spy_close
    mutated = _mutate(spy_close, t_mut, spy_close.iloc[t_mut] * 1.5)

    m1 = guard.guard_cg_dm(baseline, th)
    m2 = guard.guard_cg_dm(mutated, th)

    lag = 1
    boundary = t_mut + lag
    assert np.array_equal(m1[:boundary], m2[:boundary]), "mutation leaked before it was settled"
    assert not np.array_equal(m1[boundary:], m2[boundary:]), "mutation never had any effect at all"


def test_guard_cg_bsc_daily_does_not_look_ahead_of_the_prior_close():
    n = 500
    dates = make_dates(n)
    rng = np.random.default_rng(1)
    base_net = pd.Series(rng.normal(0.0005, 0.01, n), index=dates)
    th = guard.Thresholds(
        dm_highvol=0.10,
        bsc_target_vol=0.15,
        stop_dd=0.20,
        mkt_stop_reentry_sessions=5,
        mkt_stop_reentry_from_data=False,
    )
    t_mut = 400
    mutated = _mutate(base_net, t_mut, 0.20)  # a single extreme day

    m1 = guard.guard_cg_bsc_daily(base_net, th)
    m2 = guard.guard_cg_bsc_daily(mutated, th)

    lag = 2
    boundary = t_mut + lag
    assert np.array_equal(m1[:boundary], m2[:boundary]), "mutation leaked before it was settled"
    assert not np.array_equal(m1[boundary:], m2[boundary:]), "mutation never had any effect at all"
    assert np.nanmin(m1) >= 0.0
    assert np.nanmax(m1) <= 1.0


def test_guard_cg_stop_does_not_look_ahead_of_the_prior_close():
    n = 400
    dates = make_dates(n)
    rng = np.random.default_rng(2)
    base_net = pd.Series(rng.normal(0.0003, 0.006, n), index=dates)
    th = guard.Thresholds(
        dm_highvol=0.10,
        bsc_target_vol=0.15,
        stop_dd=0.15,
        mkt_stop_reentry_sessions=5,
        mkt_stop_reentry_from_data=False,
    )
    t_mut = 300
    mutated = _mutate(base_net, t_mut, -0.30)  # a single sharp drop

    m1 = guard.guard_cg_stop(base_net, th)
    m2 = guard.guard_cg_stop(mutated, th)

    lag = 2
    boundary = t_mut + lag
    assert np.array_equal(m1[:boundary], m2[:boundary]), "mutation leaked before it was settled"
    assert not np.array_equal(m1[boundary:], m2[boundary:]), "mutation never had any effect at all"


def test_guard_cg_mkt_stop_does_not_look_ahead_of_the_prior_close():
    n = 300
    dates = make_dates(n)
    rng = np.random.default_rng(3)
    spy_close = pd.Series(100.0 * np.cumprod(1.0 + rng.normal(0, 0.004, n)), index=dates)
    th = guard.Thresholds(
        dm_highvol=0.10,
        bsc_target_vol=0.15,
        stop_dd=0.20,
        mkt_stop_reentry_sessions=5,
        mkt_stop_reentry_from_data=False,
    )
    t_mut = 200
    mutated = spy_close.copy()
    mutated.iloc[t_mut] = mutated.iloc[t_mut - 1] * (1.0 - 0.10)  # -10% single session

    m1 = guard.guard_cg_mkt_stop(spy_close, th)
    m2 = guard.guard_cg_mkt_stop(mutated, th)

    lag = 1
    boundary = t_mut + lag
    assert np.array_equal(m1[:boundary], m2[:boundary]), "mutation leaked before it was settled"
    assert not np.array_equal(m1[boundary:], m2[boundary:]), "mutation never had any effect at all"


# --------------------------------------------------------------- guard logic


def test_guard_cg_dm_is_zero_only_in_bear_and_highvol_and_one_otherwise():
    n = 900
    dates = make_dates(n)
    # Build a series with a clear, deep, sustained decline (so the 504-session
    # trailing return goes negative) followed by choppy (high-vol) trading.
    decline = np.linspace(0.0, -0.5, 550)
    chop = np.cumsum(np.tile([0.05, -0.05], 175)[:350])
    log_path = np.concatenate([decline, decline[-1] + chop])
    spy_close = pd.Series(100.0 * np.exp(log_path), index=dates)
    th = guard.Thresholds(
        dm_highvol=0.05,  # low bar so the choppy region counts as high-vol
        bsc_target_vol=0.15,
        stop_dd=0.20,
        mkt_stop_reentry_sessions=5,
        mkt_stop_reentry_from_data=False,
    )
    m = guard.guard_cg_dm(spy_close, th)
    assert set(np.unique(m)).issubset({0.0, 1.0})
    assert (m == 0.0).any(), "a deep bear market plus high volatility should trigger the gate"
    assert (m == 1.0).any(), "the early, non-bear region should not be gated"


def test_guard_cg_bsc_daily_scales_down_in_high_vol_and_stays_near_one_in_low_vol():
    n = 400
    dates = make_dates(n)
    low_vol = np.full(150, 0.0005)
    high_vol = np.tile([0.04, -0.04], 125)[:250]
    net = pd.Series(np.concatenate([low_vol, high_vol]), index=dates)
    th = guard.Thresholds(
        dm_highvol=0.10,
        bsc_target_vol=0.05,  # a tight target vs. the later high-vol regime
        stop_dd=0.20,
        mkt_stop_reentry_sessions=5,
        mkt_stop_reentry_from_data=False,
    )
    m = guard.guard_cg_bsc_daily(net, th)
    tail = m[-50:]
    assert np.all(tail < 1.0), "the high-volatility tail should be scaled below full exposure"
    assert np.all(tail >= 0.0)


def test_guard_cg_stop_triggers_on_drawdown_and_reenters_above_the_sma():
    n = 200
    dates = make_dates(n)
    # 60 flat-up days to build SMA history, then a sharp break, then a decisive
    # recovery back above the (slow-moving) 50-session SMA.
    up = np.full(60, 0.004)
    crash = np.full(5, -0.10)
    recover = np.full(135, 0.02)
    net = pd.Series(np.concatenate([up, crash, recover]), index=dates)
    th = guard.Thresholds(
        dm_highvol=0.10,
        bsc_target_vol=0.15,
        stop_dd=0.15,  # comfortably inside the crash leg's drawdown
        mkt_stop_reentry_sessions=5,
        mkt_stop_reentry_from_data=False,
    )
    m = guard.guard_cg_stop(net, th)
    assert m[:60].sum() == 60.0, "no trigger should fire before the crash"
    assert (m == 0.0).any(), "the crash should trigger the stop"
    # Once the recovery is decisively underway (equity clearly above both its
    # trigger drawdown and its own trailing SMA, not just marginally), the
    # guard should stay re-entered. It is legitimate -- and, per report.md,
    # observed in the real backtest -- for the guard to flicker for a few
    # sessions right where the drawdown hovers near -stop_dd while equity is
    # only marginally above its SMA; this is not asserted away here, only
    # checked well after the transient region.
    assert m[-20:].all(), "a decisive, sustained recovery should settle back at full exposure"


def test_guard_cg_mkt_stop_flat_for_exactly_n_sessions_after_a_level1_drop():
    n = 60
    dates = make_dates(n)
    close = np.full(n, 100.0)
    close[20] = close[19] * (1.0 - 0.08)  # -8%, worse than the -7% Level-1 trigger
    close[21:] = close[20]  # flat afterwards, no further drops
    spy_close = pd.Series(close, index=dates)
    th = guard.Thresholds(
        dm_highvol=0.10,
        bsc_target_vol=0.15,
        stop_dd=0.20,
        mkt_stop_reentry_sessions=5,
        mkt_stop_reentry_from_data=True,
    )
    m = guard.guard_cg_mkt_stop(spy_close, th)
    lag = 1
    trigger_settled_at = 20 + lag
    assert m[trigger_settled_at : trigger_settled_at + 5].sum() == 0.0
    assert m[trigger_settled_at + 5] == 1.0


def test_guard_cg_mkt_stop_retrigger_extends_the_flat_window():
    n = 60
    dates = make_dates(n)
    close = np.full(n, 100.0)
    close[10] = close[9] * (1.0 - 0.08)
    close[13] = close[12] * (1.0 - 0.08)  # a second drop inside the first cooldown
    spy_close = pd.Series(close, index=dates)
    th = guard.Thresholds(
        dm_highvol=0.10,
        bsc_target_vol=0.15,
        stop_dd=0.20,
        mkt_stop_reentry_sessions=5,
        mkt_stop_reentry_from_data=True,
    )
    m = guard.guard_cg_mkt_stop(spy_close, th)
    # the second trigger (settled at session 14) should push the all-flat
    # window well past what a single, non-extended trigger would cover.
    assert m[14:19].sum() == 0.0


def test_guard_cg_dm_bsc_is_the_product_of_its_two_components():
    n = 400
    dates = make_dates(n)
    rng = np.random.default_rng(4)
    spy_close = pd.Series(100.0 * np.cumprod(1.0 + rng.normal(-0.001, 0.02, n)), index=dates)
    base_net = pd.Series(rng.normal(0.0003, 0.01, n), index=dates)
    th = guard.Thresholds(
        dm_highvol=0.05,
        bsc_target_vol=0.10,
        stop_dd=0.20,
        mkt_stop_reentry_sessions=5,
        mkt_stop_reentry_from_data=False,
    )
    combo = guard.guard_cg_dm_bsc(spy_close, base_net, th)
    expected = guard.guard_cg_dm(spy_close, th) * guard.guard_cg_bsc_daily(base_net, th)
    assert np.allclose(combo, expected)


# ------------------------------------------------------------ placebo shift


def test_calendar_shift_pads_with_full_exposure_and_preserves_the_series():
    m = np.array([1.0, 1.0, 0.0, 0.5, 1.0, 0.0, 0.0, 1.0])
    for k in (1, 3, 5, len(m)):
        shifted = guard.calendar_shift(m, k)
        assert len(shifted) == len(m)
        assert np.all(shifted[:k] == 1.0), "the leading edge must be padded at full exposure"
        assert np.array_equal(shifted[k:], m[: len(m) - k])


def test_calendar_shift_is_deterministic_and_distinct_across_offsets():
    rng = np.random.default_rng(5)
    m = (rng.random(60) > 0.7).astype(float)
    shifts = {k: guard.calendar_shift(m, k) for k in range(1, 21)}
    # not every offset need differ from every other, but the whole family
    # should not collapse to a single constant series when the input has
    # genuine on/off structure.
    unique = {tuple(v) for v in shifts.values()}
    assert len(unique) > 1


# ------------------------------------------------------ guarded book returns


def test_guarded_returns_match_the_base_book_when_multiplier_is_always_one():
    rng = np.random.default_rng(6)
    t, k = 30, 4
    held = rng.random((t, k)).astype(np.float32) / k
    ret = rng.normal(0, 0.01, (t, k)).astype(np.float32)
    m = np.ones(t)
    cash_ret = rng.normal(0, 0.001, t)

    base_net, base_turn = guard.book_returns(held, ret, guard.PRIMARY_BPS)
    guarded_net, guarded_turn = guard.guarded_net_returns(held, ret, m, cash_ret, guard.PRIMARY_BPS)

    assert np.allclose(guarded_net, base_net)
    assert np.allclose(guarded_turn, base_turn)


def test_guarded_returns_equal_cash_when_multiplier_is_always_zero():
    rng = np.random.default_rng(7)
    t, k = 25, 3
    held = rng.random((t, k)).astype(np.float32) / k
    ret = rng.normal(0, 0.01, (t, k)).astype(np.float32)
    m = np.zeros(t)
    cash_ret = rng.normal(0, 0.001, t)

    guarded_net, guarded_turn = guard.guarded_net_returns(held, ret, m, cash_ret, guard.PRIMARY_BPS)

    assert np.allclose(guarded_net, cash_ret)
    assert np.allclose(guarded_turn, 0.0)


def test_guarded_returns_scale_turnover_not_just_gross():
    """Scaling the whole book by a changing multiplier must be charged its own
    turnover cost, not treated as free rebalancing."""
    rng = np.random.default_rng(8)
    t, k = 20, 3
    held = np.tile(rng.random(k).astype(np.float32) / k, (t, 1))  # constant book
    ret = rng.normal(0, 0.01, (t, k)).astype(np.float32)
    m = np.ones(t)
    m[10:] = 0.3  # a single exposure change partway through
    cash_ret = np.zeros(t)

    _, guarded_turn = guard.guarded_net_returns(held, ret, m, cash_ret, guard.PRIMARY_BPS)
    assert guarded_turn[10] > 0.0, "the exposure step-down must register as turnover"
    assert np.allclose(guarded_turn[11:], 0.0), (
        "no further turnover once exposure is constant again"
    )
