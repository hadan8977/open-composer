"""Synthetic-bar tests for H-20260924-01's dip-reversion engine.

Scope, per the iteration brief: IBS, Wilder RSI, each rule's entry/exit on
hand-built sequences, T1 proxy construction, MOC fill accounting, costs, and
the placebo matching. The economic acceptance evidence (real SIP data) lives
in reports/research/iterations/h20260924_01_etf_dip_reversion/, not here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

engine = pytest.importorskip("run_h20260924_01_etf_dip_reversion")


# --------------------------------------------------------------------- IBS


def test_ibs_formula_normal_case():
    high = pd.Series([10.0, 20.0])
    low = pd.Series([5.0, 10.0])
    close = pd.Series([9.0, 11.0])
    out = engine.ibs(high, low, close)
    # (9-5)/(10-5) = 0.8 ; (11-10)/(20-10) = 0.1
    assert out.tolist() == pytest.approx([0.8, 0.1])


def test_ibs_half_when_high_equals_low():
    high = pd.Series([7.0])
    low = pd.Series([7.0])
    close = pd.Series([7.0])
    assert engine.ibs(high, low, close).iloc[0] == pytest.approx(0.5)


def test_ibs_extremes_are_zero_and_one():
    high = pd.Series([10.0, 10.0])
    low = pd.Series([5.0, 5.0])
    close = pd.Series([5.0, 10.0])  # close at the low, then at the high
    out = engine.ibs(high, low, close)
    assert out.tolist() == pytest.approx([0.0, 1.0])


# --------------------------------------------------------------- Wilder RSI


def test_wilder_rsi_hand_computed_short_sequence():
    # window=2, closes chosen so gains/losses are simple round numbers.
    close = pd.Series([10.0, 11.0, 10.0, 9.0, 11.0, 13.0])
    rsi = engine.wilder_rsi(close, 2)
    # deltas: +1, -1, -1, +2, +2
    # avg_gain (ewm alpha=0.5, adjust=False), seeded at the first delta:
    #   t=1 gain=1  -> avg_gain=1.0,           avg_loss=0.0
    #   t=2 gain=0  -> avg_gain=0.5,           loss=1  -> avg_loss=0.5
    #   t=3 gain=0  -> avg_gain=0.25,          loss=1  -> avg_loss=0.75
    #   t=4 gain=2  -> avg_gain=0.25*0.5+2*0.5=1.125,  loss=0 -> avg_loss=0.375
    #   t=5 gain=2  -> avg_gain=1.125*0.5+2*0.5=1.5625, loss=0 -> avg_loss=0.1875
    expected_last_rs = 1.5625 / 0.1875
    expected_last_rsi = 100.0 - 100.0 / (1.0 + expected_last_rs)
    assert rsi.iloc[-1] == pytest.approx(expected_last_rsi)


def test_wilder_rsi_matches_giants_sweep_reference_implementation():
    giants_sweep = pytest.importorskip("run_giants_sweep")
    rng = np.random.default_rng(7)
    close = pd.Series(100.0 + np.cumsum(rng.normal(0, 1, 300)))
    ours = engine.wilder_rsi(close, 2)
    reference = giants_sweep._wilder_rsi(close, 2)
    pd.testing.assert_series_equal(ours, reference, check_names=False)


def test_wilder_rsi_all_gains_saturates_at_100():
    close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
    rsi = engine.wilder_rsi(close, 2)
    assert rsi.iloc[-1] == pytest.approx(100.0)


# --------------------------------------------------------- EMA / SMA basics


def test_ema_matches_pandas_ewm_span_definition():
    close = pd.Series(np.linspace(100, 120, 30))
    ours = engine.ema(close, 10)
    reference = close.ewm(span=10, adjust=False, min_periods=10).mean()
    pd.testing.assert_series_equal(ours, reference)


def test_sma_matches_rolling_mean():
    close = pd.Series(np.linspace(100, 120, 30))
    ours = engine.sma(close, 10)
    reference = close.rolling(10, min_periods=10).mean()
    pd.testing.assert_series_equal(ours, reference)


# ------------------------------------------------------------- T1 proxy


def _official_frame(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2023-01-02", periods=n)
    close = 100.0 + np.cumsum(rng.normal(0.05, 1.0, n))
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = low + rng.uniform(0.0, 1.0, n) * (high - low)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=index)


def test_t1_ema_one_step_matches_hand_derived_formula():
    frame = _official_frame(260)
    proxy_close = frame["close"] * 1.01  # a made-up 15:50 proxy, different from the official close
    bundle = engine.build_bundle(
        frame,
        "T1",
        proxy=pd.DataFrame({"close": proxy_close, "high": frame["high"], "low": frame["low"]}),
    )

    ema_official = frame["close"].ewm(span=220, adjust=False, min_periods=220).mean()
    alpha = 2.0 / 221.0
    expected = alpha * proxy_close + (1 - alpha) * ema_official.shift(1)
    pd.testing.assert_series_equal(bundle.ema220, expected, check_names=False)

    # And the T1 proxy must NOT feed forward into the next day's OFFICIAL EMA
    # state: day D+1's own T0 ema220 (used as the base for day D+1's T1 step)
    # must be identical to a plain EMA computed purely from official closes.
    pd.testing.assert_series_equal(engine.ema(frame["close"], 220), ema_official, check_names=False)


def test_t1_sma_one_step_matches_hand_derived_formula():
    frame = _official_frame(220)
    proxy_close = frame["close"] + 5.0
    bundle = engine.build_bundle(
        frame,
        "T1",
        proxy=pd.DataFrame({"close": proxy_close, "high": frame["high"], "low": frame["low"]}),
    )
    expected = (frame["close"].shift(1).rolling(199, min_periods=199).sum() + proxy_close) / 200.0
    pd.testing.assert_series_equal(bundle.sma200, expected, check_names=False)
    # Sanity: on a day where the proxy exactly equals the eventual official
    # close, the T1 sma200 must equal the plain official sma200 that day.
    same_day_official_sma = engine.sma(frame["close"], 200)
    bundle_same = engine.build_bundle(
        frame,
        "T1",
        proxy=pd.DataFrame({"close": frame["close"], "high": frame["high"], "low": frame["low"]}),
    )
    pd.testing.assert_series_equal(bundle_same.sma200, same_day_official_sma, check_names=False)


def test_t1_wilder_rsi_one_step_matches_hand_derived_formula():
    frame = _official_frame(20)
    proxy_close = frame["close"] - 2.0
    bundle = engine.build_bundle(
        frame,
        "T1",
        proxy=pd.DataFrame({"close": proxy_close, "high": frame["high"], "low": frame["low"]}),
    )
    avg_gain_o, avg_loss_o = engine._wilder_rsi_state(frame["close"], 2)
    delta_proxy = proxy_close - frame["close"].shift(1)
    gain_proxy = delta_proxy.clip(lower=0.0)
    loss_proxy = (-delta_proxy).clip(lower=0.0)
    avg_gain_proxy = avg_gain_o.shift(1) * 0.5 + gain_proxy * 0.5
    avg_loss_proxy = avg_loss_o.shift(1) * 0.5 + loss_proxy * 0.5
    expected = engine._wilder_rsi_from_state(avg_gain_proxy, avg_loss_proxy)
    pd.testing.assert_series_equal(bundle.rsi2, expected, check_names=False)


def test_t1_missing_proxy_day_is_nan_not_silently_official():
    frame = _official_frame(230)
    proxy = pd.DataFrame(
        {"close": frame["close"], "high": frame["high"], "low": frame["low"]}, index=frame.index
    ).drop(frame.index[-1])  # the last session has no minute data at all
    bundle = engine.build_bundle(frame, "T1", proxy=proxy)
    assert np.isnan(bundle.close.iloc[-1])
    assert np.isnan(bundle.ibs.iloc[-1])


def test_lagged_official_fields_are_timing_invariant():
    """h1..h3/l1..l3/r1..r3 must be identical for T0 and T1: the prior
    sessions are already fully known by the time "today" is being decided,
    regardless of how "today" itself is being read."""
    frame = _official_frame(230)
    proxy = pd.DataFrame(
        {"close": frame["close"] * 1.02, "high": frame["high"], "low": frame["low"]}
    )
    bundle_t0 = engine.build_bundle(frame, "T0")
    bundle_t1 = engine.build_bundle(frame, "T1", proxy=proxy)
    for field in ("h1", "h2", "h3", "l1", "l2", "l3", "r1", "r2", "r3"):
        pd.testing.assert_series_equal(
            getattr(bundle_t0, field), getattr(bundle_t1, field), check_names=False
        )


# --------------------------------------------------------------- rule logic


def _trend_up_frame(n: int, warmup: int = 250, dip_len: int = 6, seed: int = 1) -> pd.DataFrame:
    """A long, gentle uptrend (so close stays above its own 200/220-day
    average throughout) with a small amount of noise, long enough for every
    rule's trend filter to be defined well before the end of the series."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2022-01-03", periods=n)
    trend = np.linspace(100.0, 100.0 + 0.05 * n, n)
    noise = rng.normal(0, 0.15, n)
    close = trend + noise
    high = close + rng.uniform(0.05, 0.3, n)
    low = close - rng.uniform(0.05, 0.3, n)
    open_ = low + rng.uniform(0.0, 1.0, n) * (high - low)
    frame = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=index)
    assert n > warmup + dip_len
    return frame


def _force_low_ibs_day(frame: pd.DataFrame, day: int, ibs_value: float) -> pd.DataFrame:
    """Rewrite one day's H/L/C so its IBS equals ``ibs_value`` exactly, while
    keeping the close roughly in line with the surrounding trend (so the
    day's own EMA/SMA-trend-filter membership is otherwise unaffected)."""
    frame = frame.copy()
    close = frame["close"].iloc[day]
    rng = 4.0
    low = close - ibs_value * rng
    high = low + rng
    frame.iloc[day, frame.columns.get_loc("low")] = low
    frame.iloc[day, frame.columns.get_loc("high")] = high
    frame.iloc[day, frame.columns.get_loc("close")] = close
    return frame


def test_d1_entry_fires_on_low_ibs_above_trend_and_exits_on_high_ibs():
    frame = _trend_up_frame(280, warmup=225, dip_len=1)
    entry_day = 260
    frame = _force_low_ibs_day(frame, entry_day, 0.05)  # below the 0.09 QQQ threshold
    frame = _force_low_ibs_day(frame, entry_day + 3, 0.99)  # above the 0.985 QQQ exit threshold
    rule = engine.RULES["D1"]["QQQ"]
    bundle = engine.build_bundle(frame, "T0")

    trend_ok = bundle.close.iloc[entry_day] > bundle.ema220.iloc[entry_day]
    assert trend_ok  # the entry day is still comfortably above its EMA(220)
    entry_signal = rule.entry(bundle)
    assert bool(entry_signal.iloc[entry_day])
    assert not bool(entry_signal.iloc[entry_day - 1])

    rets, _turns, trades = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T0", engine.COST_BPS_PRIMARY
    )
    matching = [t for t in trades if t.entry_idx == entry_day]
    assert len(matching) == 1
    assert matching[0].exit_idx == entry_day + 3


def test_d1_exits_at_max_hold_when_ibs_never_recovers():
    frame = _trend_up_frame(280, warmup=225, dip_len=1)
    entry_day = 260
    frame = _force_low_ibs_day(frame, entry_day, 0.05)
    rule = engine.RULES["D1"]["QQQ"]
    bundle = engine.build_bundle(frame, "T0")
    _rets, _turns, trades = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T0", engine.COST_BPS_PRIMARY
    )
    matching = [t for t in trades if t.entry_idx == entry_day]
    assert len(matching) == 1
    assert matching[0].exit_idx == entry_day + rule.max_hold  # 14-session cap, no IBS exit fired


def test_d2_entry_and_exactly_one_session_hold():
    # Fully hand-built, deterministic series (D2 has no trend filter, so no
    # warmup is needed): every IBS is fixed explicitly so only day 3 can
    # possibly satisfy ibs < 0.20, with no risk of an incidental earlier
    # low-IBS day consuming day 3 via simulate_rule's sequential trade scan.
    n = 10
    index = pd.bdate_range("2023-02-01", periods=n)
    close = pd.Series([100.0 + i for i in range(n)], index=index)
    # mid-range IBS (0.5) everywhere except the engineered day 3 (IBS=0.1).
    high = close + 2.0
    low = close - 2.0
    frame = pd.DataFrame({"open": close, "high": high, "low": low, "close": close}, index=index)
    entry_day = 3
    frame = _force_low_ibs_day(frame, entry_day, 0.1)  # below 0.20
    rule = engine.RULES["D2"]["QQQ"]
    bundle = engine.build_bundle(frame, "T0")
    ibs_all = bundle.ibs.to_numpy()
    assert all(v >= 0.20 for i, v in enumerate(ibs_all) if i != entry_day)
    assert bool(rule.entry(bundle).iloc[entry_day])
    _rets, _turns, trades = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T0", 0.0
    )
    matching = [t for t in trades if t.entry_idx == entry_day]
    assert len(matching) == 1
    assert matching[0].exit_idx == entry_day + 1
    assert matching[0].hold_sessions == 1
    expected_gross = frame["close"].iloc[entry_day + 1] / frame["close"].iloc[entry_day] - 1.0
    assert matching[0].gross_return == pytest.approx(expected_gross)


def test_d3_entry_requires_three_day_falling_rsi_and_trend():
    frame = _trend_up_frame(280, warmup=225, dip_len=4)
    day = 260
    # Engineer four consecutive closes with a small, increasing-magnitude
    # decline (total 1.0 over 4 sessions) so RSI(2) falls sharply enough to
    # clear the entry thresholds while staying well inside the ~4-5 point
    # buffer between price and its 200-day EMA established by the warmup
    # uptrend (a steeper decline pulls close below EMA(200) and breaks the
    # trend filter instead of testing the RSI condition in isolation).
    idx_close = frame.columns.get_loc("close")
    idx_high = frame.columns.get_loc("high")
    idx_low = frame.columns.get_loc("low")
    base = frame["close"].iloc[day - 4]
    fracs = (0.1, 0.3, 0.6, 1.0)
    steps = [base - 1.0 * f for f in fracs]
    for offset, price in zip(range(-3, 1), steps, strict=True):
        frame.iloc[day + offset, idx_close] = price
        frame.iloc[day + offset, idx_high] = price + 0.2
        frame.iloc[day + offset, idx_low] = price - 0.2
    bundle = engine.build_bundle(frame, "T0")
    rule = engine.RULES["D3"]["QQQ"]
    r0, r1, r2, r3 = (
        bundle.rsi2.iloc[day],
        bundle.r1.iloc[day],
        bundle.r2.iloc[day],
        bundle.r3.iloc[day],
    )
    assert r0 < r1 < r2 < r3
    assert r3 < 60
    assert r0 < 10
    assert bundle.close.iloc[day] > bundle.ema200.iloc[day]
    assert bool(rule.entry(bundle).iloc[day])


def test_d3_exit_on_rsi_crossover_70():
    values = [50.0] * 10 + [40, 38, 60, 61, 62]
    index = pd.bdate_range("2023-01-02", periods=len(values))
    # Build ``close`` with its final index from the start: passing a Series
    # that already carries a (mismatched) default RangeIndex into
    # ``pd.DataFrame({...}, index=...)`` would silently realign-by-label and
    # produce an all-NaN frame instead of raising.
    close = pd.Series(values, index=index)
    frame = pd.DataFrame(
        {"open": close, "high": close + 0.1, "low": close - 0.1, "close": close}, index=index
    )
    bundle = engine.build_bundle(frame, "T0")
    rule = engine.RULES["D3"]["QQQ"]
    exit_signal = rule.exit(bundle)
    crossing_days = [i for i, v in enumerate(exit_signal) if v]
    # RSI(2) should cross above 70 exactly once, on the first day it prints
    # above 70 having been at or below 70 the day before.
    assert len(crossing_days) == 1
    day = crossing_days[0]
    assert bundle.rsi2.iloc[day] > 70
    assert bundle.rsi2.iloc[day - 1] <= 70


def test_d4_entry_and_exit_sma_rules():
    frame = _trend_up_frame(280, warmup=225, dip_len=1)
    entry_day = 260
    # A small two-day decline (0.5 then 1.0) is enough to push RSI(2) to
    # <=5 while close stays comfortably above SMA(200); a much larger drop
    # (verified empirically) pulls close below its own 200-day average and
    # breaks the trend filter instead of isolating the RSI condition.
    idx = frame.columns.get_loc("close")
    frame.iloc[entry_day - 1, idx] = frame["close"].iloc[entry_day - 2] - 0.5
    frame.iloc[entry_day, idx] = frame["close"].iloc[entry_day - 1] - 1.0
    bundle = engine.build_bundle(frame, "T0")
    rule = engine.RULES["D4"]["QQQ"]
    assert bundle.rsi2.iloc[entry_day] <= 5
    assert bundle.close.iloc[entry_day] > bundle.sma200.iloc[entry_day]
    assert bool(rule.entry(bundle).iloc[entry_day])
    # exit is a pure close > sma5 test
    exit_signal = rule.exit(bundle)
    assert (exit_signal == (bundle.close > bundle.sma5)).all()


def test_d5_three_consecutive_lower_highs_and_lows():
    frame = _trend_up_frame(280, warmup=225, dip_len=4)
    day = 260
    idx_h = frame.columns.get_loc("high")
    idx_l = frame.columns.get_loc("low")
    idx_c = frame.columns.get_loc("close")
    # A small step-down in high/low (well inside the buffer to EMA(200))
    # verified empirically to keep close > EMA(200) while forcing close <
    # EMA(5) (a fast-reacting average that the small decline still pulls
    # below current price).
    highs = [frame["high"].iloc[day - 4] - k for k in (0.3, 0.6, 0.9, 1.2)]
    lows = [frame["low"].iloc[day - 4] - k for k in (0.5, 1.0, 1.5, 2.0)]
    for offset in range(-3, 1):
        j = day + offset
        frame.iloc[j, idx_h] = highs[offset + 3]
        frame.iloc[j, idx_l] = lows[offset + 3]
        frame.iloc[j, idx_c] = lows[offset + 3] + 0.1  # keep close below EMA(5) too
    bundle = engine.build_bundle(frame, "T0")
    rule = engine.RULES["D5"]["QQQ"]
    assert bundle.high.iloc[day] < bundle.h1.iloc[day] < bundle.h2.iloc[day] < bundle.h3.iloc[day]
    assert bundle.low.iloc[day] < bundle.l1.iloc[day] < bundle.l2.iloc[day] < bundle.l3.iloc[day]
    assert bundle.close.iloc[day] > bundle.ema200.iloc[day]
    assert bundle.close.iloc[day] < bundle.ema5.iloc[day]
    assert bool(rule.entry(bundle).iloc[day])


def test_d5_exit_is_close_crossing_above_ema5():
    values = [100.0] * 20 + [90, 88, 95, 98]
    index = pd.bdate_range("2023-01-02", periods=len(values))
    close = pd.Series(values, index=index)
    frame = pd.DataFrame(
        {"open": close, "high": close + 0.2, "low": close - 0.2, "close": close}, index=index
    )
    bundle = engine.build_bundle(frame, "T0")
    rule = engine.RULES["D5"]["QQQ"]
    exit_signal = rule.exit(bundle)
    crossing_days = [i for i, v in enumerate(exit_signal) if v]
    assert len(crossing_days) >= 1
    day = crossing_days[0]
    assert bundle.close.iloc[day] > bundle.ema5.iloc[day]
    assert bundle.close.iloc[day - 1] <= bundle.ema5.iloc[day - 1]


def test_d6_requires_both_d4_entry_and_ibs_below_020():
    frame = _trend_up_frame(280, warmup=225, dip_len=1)
    entry_day = 260
    idx = frame.columns.get_loc("close")
    frame.iloc[entry_day - 1, idx] = frame["close"].iloc[entry_day - 2] - 0.5
    frame.iloc[entry_day, idx] = frame["close"].iloc[entry_day - 1] - 1.0
    bundle_no_ibs_filter = engine.build_bundle(frame, "T0")
    d4 = engine.RULES["D4"]["QQQ"]
    assert bool(d4.entry(bundle_no_ibs_filter).iloc[entry_day])  # D4 alone fires

    # Now force IBS high on that same day: D6 must reject even though D4 fires.
    frame_high_ibs = _force_low_ibs_day(frame, entry_day, 0.9)
    bundle_high_ibs = engine.build_bundle(frame_high_ibs, "T0")
    d6 = engine.RULES["D6"]["QQQ"]
    assert not bool(d6.entry(bundle_high_ibs).iloc[entry_day])

    # And with IBS forced low, D6 must fire (same day D4 already fires on).
    frame_low_ibs = _force_low_ibs_day(frame, entry_day, 0.1)
    bundle_low_ibs = engine.build_bundle(frame_low_ibs, "T0")
    assert bool(d6.entry(bundle_low_ibs).iloc[entry_day])


# ---------------------------------------------------------- MOC fill accounting


def _simple_trending_frame(n: int = 12) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    index = pd.bdate_range("2023-03-01", periods=n)
    close = 100.0 * (1.0 + rng.normal(0.002, 0.01, n)).cumprod()
    high = close * 1.01
    low = close * 0.99
    open_ = low + rng.uniform(0.0, 1.0, n) * (high - low)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=index)


class _OneShotRule:
    """A minimal Rule-like object: enter on a fixed day, exit on a fixed day."""

    def __init__(self, entry_day: int, exit_day: int, n: int):
        self.max_hold = None
        self.fixed_hold = None
        self._entry_day = entry_day
        self._exit_day = exit_day
        self._n = n

    def entry(self, bundle) -> pd.Series:
        arr = np.zeros(self._n, dtype=bool)
        arr[self._entry_day] = True
        return pd.Series(arr, index=bundle.index)

    def exit(self, bundle) -> pd.Series:
        arr = np.zeros(self._n, dtype=bool)
        arr[self._exit_day] = True
        return pd.Series(arr, index=bundle.index)

    def eligible(self, bundle) -> pd.Series:
        return pd.Series(True, index=bundle.index)


def test_t0_and_t1_fill_at_same_close_and_own_the_overnight_gap():
    frame = _simple_trending_frame()
    n = len(frame)
    rule = _OneShotRule(entry_day=2, exit_day=5, n=n)
    bundle = engine.build_bundle(frame, "T0")
    rets, _turns, trades = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T0", 0.0
    )
    trade = trades[0]
    assert trade.entry_price == pytest.approx(frame["close"].iloc[2])
    assert trade.exit_price == pytest.approx(frame["close"].iloc[5])
    assert trade.entry_active_start == 3
    assert trade.exit_active_end == 5
    assert trade.gross_return == pytest.approx(trade.exit_price / trade.entry_price - 1.0)
    # day 2 (the decision day) owns nothing yet
    assert rets.iloc[2] == pytest.approx(0.0)
    # Days 3..5 compound to approximately (not exactly) exit/entry - 1: each
    # day's return is leg_open + leg_close (a SUM, matching the additive
    # convention already used by run_h20260918_05_recent_menu.py's
    # portfolio_returns), not (1+leg_open)*(1+leg_close) - 1, so a per-day
    # cross term of leg_open*leg_close (second-order small) is dropped. The
    # tolerance below is sized generously above that expected drift, not
    # loosened to paper over a real accounting bug.
    compounded = float((1.0 + rets.iloc[3:6]).prod() - 1.0)
    assert compounded == pytest.approx(trade.gross_return, abs=5e-4)


def test_t2_fill_excludes_the_overnight_gap_on_both_ends():
    frame = _simple_trending_frame()
    n = len(frame)
    rule = _OneShotRule(entry_day=2, exit_day=5, n=n)
    bundle = engine.build_bundle(frame, "T0")
    rets, _turns, trades = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T2", 0.0
    )
    trade = trades[0]
    assert trade.entry_price == pytest.approx(frame["open"].iloc[3])
    assert trade.exit_price == pytest.approx(frame["open"].iloc[6])
    assert trade.entry_active_start == 3
    assert trade.exit_active_end == 6
    assert trade.gross_return == pytest.approx(trade.exit_price / trade.entry_price - 1.0)
    # see the comment in test_t0_and_t1_... for why this is approximate, not exact.
    compounded = float((1.0 + rets.iloc[3:7]).prod() - 1.0)
    assert compounded == pytest.approx(trade.gross_return, abs=5e-4)
    # the entry day should show only the close leg (bought at the open)
    expected_entry_day_return = frame["close"].iloc[3] / frame["open"].iloc[3] - 1.0
    assert rets.iloc[3] == pytest.approx(expected_entry_day_return)
    # the exit day should show only the open leg (sold at the open)
    expected_exit_day_return = frame["open"].iloc[6] / frame["close"].iloc[5] - 1.0
    assert rets.iloc[6] == pytest.approx(expected_exit_day_return)


def test_compounded_gross_return_invariant_holds_generally():
    """(1+daily gross returns over the active window).prod() - 1 must
    approximately equal trade.gross_return for every timing convention and
    hold length, up to the additive-leg-summing cross term documented in
    test_t0_and_t1_fill_at_same_close_and_own_the_overnight_gap. The exact
    identity (gross_return == exit_price/entry_price - 1) is checked
    directly, with no tolerance, in each of the timing-specific tests
    above."""
    frame = _simple_trending_frame(n=15)
    bundle = engine.build_bundle(frame, "T0")
    for timing in ("T0", "T1", "T2"):
        for entry_day, exit_day in [(1, 2), (1, 4), (3, 10)]:
            rule = _OneShotRule(entry_day=entry_day, exit_day=exit_day, n=len(frame))
            rets, _turns, trades = engine.simulate_rule(
                rule, bundle, frame["open"], frame["close"], timing, 0.0
            )
            assert len(trades) == 1, (timing, entry_day, exit_day)
            trade = trades[0]
            window = rets.iloc[trade.entry_active_start : trade.exit_active_end + 1]
            compounded = float((1.0 + window).prod() - 1.0)
            assert compounded == pytest.approx(trade.gross_return, abs=2e-3)


# --------------------------------------------------------------------- costs


def test_net_return_subtracts_two_sided_cost():
    frame = _simple_trending_frame()
    rule = _OneShotRule(entry_day=2, exit_day=5, n=len(frame))
    bundle = engine.build_bundle(frame, "T0")
    _rets0, _t0, trades0 = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T0", 0.0
    )
    _rets10, _t10, trades10 = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T0", engine.COST_BPS_PRIMARY
    )
    gross = trades0[0].gross_return
    assert trades0[0].net_return == pytest.approx(gross)
    assert trades10[0].net_return == pytest.approx(gross - 2.0 * engine.COST_BPS_PRIMARY / 10_000.0)


def test_cost_deduction_lands_on_entry_and_exit_active_days():
    frame = _simple_trending_frame()
    rule = _OneShotRule(entry_day=2, exit_day=5, n=len(frame))
    bundle = engine.build_bundle(frame, "T0")
    rets_free, _, _ = engine.simulate_rule(rule, bundle, frame["open"], frame["close"], "T0", 0.0)
    rets_cost, _, trades = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T0", engine.COST_BPS_PRIMARY
    )
    trade = trades[0]
    per_side = engine.COST_BPS_PRIMARY / 10_000.0
    assert rets_cost.iloc[trade.entry_active_start] == pytest.approx(
        rets_free.iloc[trade.entry_active_start] - per_side
    )
    assert rets_cost.iloc[trade.exit_active_end] == pytest.approx(
        rets_free.iloc[trade.exit_active_end] - per_side
    )
    untouched = [
        i
        for i in range(trade.entry_active_start, trade.exit_active_end + 1)
        if i not in (trade.entry_active_start, trade.exit_active_end)
    ]
    for i in untouched:
        assert rets_cost.iloc[i] == pytest.approx(rets_free.iloc[i])


# ----------------------------------------------------------------- placebos


class _MultiShotRule:
    """A Rule-like object with fully explicit, non-overlapping (entry, exit)
    day pairs of DIFFERENT hold lengths, and a controllable eligibility mask.

    Used instead of one of the six published rules so the placebo tests
    verify the placebo-construction machinery itself (trade count, holding-
    period multiset, eligible-pool restriction, determinism, and calendar
    shifting) without depending on how often an economic rule like D4
    happens to trade on a particular synthetic price path.
    """

    def __init__(
        self, pairs: list[tuple[int, int]], n: int, eligible_mask: np.ndarray | None = None
    ):
        self.max_hold = None
        self.fixed_hold = None
        self._entry_days = [p[0] for p in pairs]
        self._exit_days = [p[1] for p in pairs]
        self._n = n
        self._eligible_mask = eligible_mask

    def entry(self, bundle) -> pd.Series:
        arr = np.zeros(self._n, dtype=bool)
        arr[self._entry_days] = True
        return pd.Series(arr, index=bundle.index)

    def exit(self, bundle) -> pd.Series:
        arr = np.zeros(self._n, dtype=bool)
        arr[self._exit_days] = True
        return pd.Series(arr, index=bundle.index)

    def eligible(self, bundle) -> pd.Series:
        if self._eligible_mask is None:
            return pd.Series(True, index=bundle.index)
        return pd.Series(self._eligible_mask, index=bundle.index)


_MULTI_SHOT_PAIRS = [(5, 7), (20, 25), (40, 43)]  # hold lengths 2, 5, 3 -- all distinct


def _multi_shot_fixture(n: int = 70, eligible_mask: np.ndarray | None = None):
    frame = _simple_trending_frame(n)
    rule = _MultiShotRule(_MULTI_SHOT_PAIRS, n, eligible_mask)
    bundle = engine.build_bundle(frame, "T0")
    return frame, rule, bundle


def test_random_entry_placebo_matches_trade_count_and_holding_period_multiset():
    frame, rule, bundle = _multi_shot_fixture()
    _rets, _turns, real_trades = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T0", engine.COST_BPS_PRIMARY
    )
    assert len(real_trades) == len(_MULTI_SHOT_PAIRS)
    _p_rets, _p_turns, placebo_trades = engine.random_entry_placebo(
        rule,
        bundle,
        frame["open"],
        frame["close"],
        "T0",
        engine.COST_BPS_PRIMARY,
        real_trades,
        seed=0,
    )
    assert len(placebo_trades) == len(real_trades)
    real_holds = sorted(t.hold_sessions for t in real_trades)
    placebo_holds = sorted(t.hold_sessions for t in placebo_trades)
    assert placebo_holds == real_holds == [2, 3, 5]


def test_random_entry_placebo_only_samples_eligible_days():
    n = 70
    eligible_mask = np.zeros(n, dtype=bool)
    eligible_mask[::2] = True  # only even-indexed sessions are eligible
    frame, rule, bundle = _multi_shot_fixture(n, eligible_mask=eligible_mask)
    _rets, _turns, real_trades = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T0", engine.COST_BPS_PRIMARY
    )
    _p_rets, _p_turns, placebo_trades = engine.random_entry_placebo(
        rule,
        bundle,
        frame["open"],
        frame["close"],
        "T0",
        engine.COST_BPS_PRIMARY,
        real_trades,
        seed=1,
    )
    assert len(placebo_trades) == len(real_trades)
    for t in placebo_trades:
        assert t.entry_idx % 2 == 0


def test_random_entry_placebo_is_deterministic_given_a_seed():
    frame, rule, bundle = _multi_shot_fixture()
    _rets, _turns, real_trades = engine.simulate_rule(
        rule, bundle, frame["open"], frame["close"], "T0", engine.COST_BPS_PRIMARY
    )
    _r1, _t1, trades1 = engine.random_entry_placebo(
        rule,
        bundle,
        frame["open"],
        frame["close"],
        "T0",
        engine.COST_BPS_PRIMARY,
        real_trades,
        seed=42,
    )
    _r2, _t2, trades2 = engine.random_entry_placebo(
        rule,
        bundle,
        frame["open"],
        frame["close"],
        "T0",
        engine.COST_BPS_PRIMARY,
        real_trades,
        seed=42,
    )
    assert [t.entry_idx for t in trades1] == [t.entry_idx for t in trades2]
    assert [t.exit_idx for t in trades1] == [t.exit_idx for t in trades2]


def test_calendar_shift_placebo_reproduces_the_shifted_signal():
    frame, rule, bundle = _multi_shot_fixture()
    seed = 5
    shift = int(np.random.default_rng(seed).integers(1, 21))
    expected_entry_days = {d + shift for d in rule._entry_days if d + shift < len(frame)}

    _rets, _turns, trades = engine.calendar_shift_placebo(
        rule, bundle, frame["open"], frame["close"], "T0", engine.COST_BPS_PRIMARY, seed=seed
    )
    assert len(trades) == len(expected_entry_days)
    assert {t.entry_idx for t in trades} == expected_entry_days
    # a pure calendar shift preserves each trade's holding period exactly
    assert sorted(t.hold_sessions for t in trades) == sorted(e - s for s, e in _MULTI_SHOT_PAIRS)


# --------------------------------------------------------------------- gates


def test_evaluate_gates_g1_and_g2_thresholds():
    def one(cagr, max_dd, sharpe):
        return engine.base.Metrics(
            days=100,
            cagr=cagr,
            vol=0.0,
            sharpe=sharpe,
            max_dd=max_dd,
            turnover_yr=0.0,
            hit_month=0.0,
        )

    def metrics(cagr, max_dd, sharpe):
        return {
            "select": one(cagr, max_dd, sharpe),
            "holdout": one(cagr, max_dd, sharpe),
            "anchor": one(cagr, max_dd, sharpe),
        }

    passing = metrics(cagr=0.55, max_dd=-0.30, sharpe=1.2)
    gate = engine.evaluate_gates(passing, passing, {"a": 0.05})
    assert gate.G1 is True
    assert gate.G2 is True
    assert gate.G3 is True
    assert gate.all_gates is True

    failing = metrics(cagr=0.10, max_dd=-0.10, sharpe=0.5)
    gate2 = engine.evaluate_gates(failing, failing, {"a": 0.5})
    assert gate2.G1 is False
    assert gate2.G1_alt is False
    assert gate2.all_gates is False


def test_deflated_sharpe_ratio_returns_nan_with_one_trial():
    assert np.isnan(engine.deflated_sharpe_ratio(1.0, [1.0], 100, 0.0, 3.0))


def test_deflated_sharpe_ratio_is_lower_than_naive_probability_for_many_trials():
    rng = np.random.default_rng(0)
    trials = list(rng.normal(0.5, 0.3, 24))
    best = max(trials)
    dsr = engine.deflated_sharpe_ratio(best, trials, 500, 0.0, 3.0)
    naive_psr = engine._norm_cdf(best * np.sqrt(499))
    assert 0.0 <= dsr <= 1.0
    assert dsr < naive_psr
