"""Tests for the Reversal Trend Pine port.

Plan: ``docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md``
section 4 test list: (a) synthetic sequences hand-tracing every state-machine
branch (crossover/dwell/arm/expire/lock/cooldown), (b) EMA/RMA/RSI/ATR/ADX
against independent hand-written reference implementations at ``rtol=1e-9``,
(c) a real SPY daily segment that runs end to end, has a bounded/finite signal
count, and does not repeat (bar-by-bar incremental recomputation matches the
full run).

The reference implementations in this file are deliberately plain Python loops
(no pandas ``.ewm``/``.rolling``) so they cross-check the production module's
vectorized seeding/alignment logic with an independently-coded path, not a
restatement of the same pandas calls.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from open_composer.adapters.data.sip_parquet import default_sip_root, load_sip_bars
from open_composer.research.pine_port.reversal_trend import (
    ReversalTrendParams,
    _consecutive_true_run,
    _crossover,
    _crossover_level,
    _crossunder,
    _crossunder_level,
    _hist_confirmation,
    _rolling_highest,
    _rolling_lowest,
    _run_state_machine,
    compute_reversal_trend,
)

# ---------------------------------------------------------------------------
# Independent reference implementations (plain Python, no pandas/numpy calls
# for the recursive parts) -- deliberately not a copy of the production code.
# ---------------------------------------------------------------------------


def _ref_ema(values: list[float], length: int) -> list[float | None]:
    alpha = 2.0 / (length + 1)
    out: list[float | None] = [None] * len(values)
    prev: float | None = None
    for i, v in enumerate(values):
        prev = v if prev is None else alpha * v + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _ref_rma(values: list[float | None], length: int) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    first = None
    for i, v in enumerate(values):
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            first = i
            break
    if first is None or first + length > n:
        return out
    seed = sum(values[first : first + length]) / length  # type: ignore[misc]
    out[first + length - 1] = seed
    prev = seed
    alpha = 1.0 / length
    for i in range(first + length, n):
        prev = alpha * values[i] + (1.0 - alpha) * prev  # type: ignore[operator]
        out[i] = prev
    return out


def _ref_rsi(closes: list[float], length: int) -> list[float | None]:
    n = len(closes)
    gains: list[float | None] = [None] * n
    losses: list[float | None] = [None] * n
    for i in range(1, n):
        delta = closes[i] - closes[i - 1]
        gains[i] = max(delta, 0.0)
        losses[i] = max(-delta, 0.0)
    avg_gain = _ref_rma(gains, length)
    avg_loss = _ref_rma(losses, length)
    out: list[float | None] = [None] * n
    for i in range(n):
        g, loss = avg_gain[i], avg_loss[i]
        if g is None or loss is None:
            continue
        if loss == 0.0:
            out[i] = 100.0 if g > 0.0 else float("nan")
        else:
            rs = g / loss
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def _ref_true_range(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    n = len(highs)
    out = [0.0] * n
    for i in range(n):
        if i == 0:
            out[i] = highs[i] - lows[i]
        else:
            out[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
    return out


def _ref_atr(
    highs: list[float], lows: list[float], closes: list[float], length: int
) -> list[float | None]:
    return _ref_rma(_ref_true_range(highs, lows, closes), length)


def _ref_macd(
    closes: list[float], fast: int, slow: int, signal: int
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    ema_fast = _ref_ema(closes, fast)
    ema_slow = _ref_ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow, strict=True)]  # never None
    signal_line = _ref_ema(macd_line, signal)  # type: ignore[arg-type]
    hist = [m - s for m, s in zip(macd_line, signal_line, strict=True)]  # type: ignore[operator]
    return macd_line, signal_line, hist  # type: ignore[return-value]


def _ref_dmi(
    highs: list[float], lows: list[float], closes: list[float], length: int
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    n = len(highs)
    plus_dm: list[float | None] = [None] * n
    minus_dm: list[float | None] = [None] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
    tr_rma = _ref_rma(_ref_true_range(highs, lows, closes), length)
    plus_dm_rma = _ref_rma(plus_dm, length)
    minus_dm_rma = _ref_rma(minus_dm, length)

    plus_di: list[float | None] = [None] * n
    minus_di: list[float | None] = [None] * n
    for i in range(n):
        tr_v = tr_rma[i]
        if plus_dm_rma[i] is not None and tr_v is not None:
            plus_di[i] = 100.0 * plus_dm_rma[i] / tr_v  # type: ignore[operator]
        if minus_dm_rma[i] is not None and tr_v is not None:
            minus_di[i] = 100.0 * minus_dm_rma[i] / tr_v  # type: ignore[operator]

    dx: list[float | None] = [None] * n
    for i in range(n):
        p, m = plus_di[i], minus_di[i]
        if p is None or m is None:
            continue
        denom = p + m
        if denom == 0.0:
            denom = 1.0
        dx[i] = 100.0 * abs(p - m) / denom
    adx = _ref_rma(dx, length)
    return plus_di, minus_di, adx


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------


def _synthetic_ohlcv(n: int, *, seed: int = 0, start_price: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=0.0002, scale=0.012, size=n)
    close = start_price * np.cumprod(1.0 + steps)
    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]
    spread = np.abs(rng.normal(loc=0.004, scale=0.002, size=n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.integers(1_000_000, 5_000_000, size=n).astype(float)
    timestamps = pd.date_range("2020-01-02", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _assert_matches_reference(
    actual: pd.Series, expected: list[float | None], *, rtol: float = 1e-9
) -> None:
    actual_values = actual.to_numpy(dtype=float)
    assert len(actual_values) == len(expected)
    for i, exp in enumerate(expected):
        if exp is None or (isinstance(exp, float) and math.isnan(exp)):
            assert math.isnan(actual_values[i]), f"index {i}: expected NaN, got {actual_values[i]}"
        else:
            assert actual_values[i] == pytest.approx(exp, rel=rtol, abs=1e-12), (
                f"index {i}: {actual_values[i]} != {exp}"
            )


# ---------------------------------------------------------------------------
# (b) Indicator formulas vs. independent reference, rtol=1e-9
# ---------------------------------------------------------------------------


def test_ema_rma_rsi_atr_macd_adx_match_independent_reference() -> None:
    bars = _synthetic_ohlcv(160, seed=1)
    params = ReversalTrendParams()
    result = compute_reversal_trend(bars, params)

    closes = bars["close"].tolist()
    highs = bars["high"].tolist()
    lows = bars["low"].tolist()

    _assert_matches_reference(result["ema_fast"], _ref_ema(closes, params.ema_fast_len))
    _assert_matches_reference(result["ema_mid"], _ref_ema(closes, params.ema_mid_len))
    _assert_matches_reference(result["ema_slow"], _ref_ema(closes, params.ema_slow_len))
    _assert_matches_reference(result["rsi"], _ref_rsi(closes, params.rsi_len))
    _assert_matches_reference(result["atr"], _ref_atr(highs, lows, closes, params.atr_len))

    ref_macd_line, ref_signal, ref_hist = _ref_macd(
        closes, params.macd_fast, params.macd_slow, params.macd_signal
    )
    _assert_matches_reference(result["macd_line"], ref_macd_line)
    _assert_matches_reference(result["macd_signal"], ref_signal)
    _assert_matches_reference(result["macd_hist"], ref_hist)

    ref_plus_di, ref_minus_di, ref_adx = _ref_dmi(highs, lows, closes, params.adx_len)
    _assert_matches_reference(result["di_plus"], ref_plus_di)
    _assert_matches_reference(result["di_minus"], ref_minus_di)
    _assert_matches_reference(result["adx"], ref_adx)

    # RSI/ATR/ADX all have a real warmup gap (not defined from bar 0) -- pin the
    # exact lengths down so a future change to the seeding logic is caught even
    # if it happens to leave values numerically close downstream.
    assert result["rsi"].isna().sum() == params.rsi_len
    assert result["atr"].isna().sum() == params.atr_len - 1
    assert result["adx"].isna().sum() == 2 * params.adx_len - 1
    # EMA has no warmup gap: seeded at the first bar.
    assert result["ema_fast"].isna().sum() == 0


def test_rsi_is_100_when_there_are_gains_and_zero_losses() -> None:
    # Strictly increasing closes for long enough that avg_loss's RMA seed is 0.
    closes = [100.0 + i for i in range(30)]
    bars = pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.1 for c in closes],
            "low": [c - 0.1 for c in closes],
            "close": closes,
            "volume": [1_000.0] * len(closes),
        }
    )
    result = compute_reversal_trend(bars)
    assert result["rsi"].iloc[-1] == pytest.approx(100.0)


def test_crossover_and_crossunder_primitives() -> None:
    a = pd.Series([1.0, 2.0, 3.0, 2.0, 1.0])
    b = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0])
    # a: 1,2,3,2,1 vs b constant 2 -> crosses over at index2 (3>2, prev 2<=2)
    assert list(_crossover(a, b)) == [False, False, True, False, False]
    # crosses under at index4 (1<2, prev(index3)=2>=2)
    assert list(_crossunder(a, b)) == [False, False, False, False, True]


def test_crossover_level_does_not_falsely_trigger_at_bar_zero() -> None:
    # A constant level must not be treated as a shiftable series: bar 0 has no
    # real "previous bar" for `a`, so a[1] is NaN and the crossover must be
    # False there regardless of the level, never true-by-default.
    a = pd.Series([25.0, 35.0, 20.0, 40.0])
    up = _crossover_level(a, 30.0)
    down = _crossunder_level(a, 30.0)
    assert list(up) == [False, True, False, True]
    assert list(down) == [False, False, True, False]


def test_rolling_highest_and_lowest_include_current_bar_and_need_full_window() -> None:
    x = pd.Series([1.0, 5.0, 3.0, 9.0, 2.0])
    highest = _rolling_highest(x, 3)
    lowest = _rolling_lowest(x, 3)
    assert highest.isna().sum() == 2  # first two bars: insufficient history
    assert list(highest.iloc[2:]) == [5.0, 9.0, 9.0]
    assert list(lowest.iloc[2:]) == [1.0, 3.0, 2.0]


def test_hist_confirmation_modes() -> None:
    hist = pd.Series([0.0, 1.0, 2.0, 1.5, 1.0, 0.5])
    off_up, off_dn = _hist_confirmation(hist, "Off")
    assert off_up.all() and off_dn.all()

    up1, dn1 = _hist_confirmation(hist, "1 Bar")
    assert list(up1) == [False, True, True, False, False, False]
    assert list(dn1) == [False, False, False, True, True, True]

    up2, dn2 = _hist_confirmation(hist, "2 Bars")
    # up2 requires hist>hist[1] and hist[1]>hist[2]: only index2 (2>1, 1>0)
    assert list(up2) == [False, False, True, False, False, False]
    # dn2 requires hist<hist[1] and hist[1]<hist[2]: index4 (1<1.5, 1.5<2.0) and
    # index5 (0.5<1.0, 1.0<1.5)
    assert list(dn2) == [False, False, False, False, True, True]


def test_unknown_hist_mode_rejected() -> None:
    with pytest.raises(ValueError):
        ReversalTrendParams(hist_mode="Weird")


# ---------------------------------------------------------------------------
# (a) State machine branches, hand-traced on synthetic boolean sequences
# ---------------------------------------------------------------------------


def _make_bool_array(n: int, true_at: list[int] | None) -> np.ndarray:
    arr = np.zeros(n, dtype=bool)
    for i in true_at or []:
        arr[i] = True
    return arr


def _run(
    n: int,
    *,
    rsi: list[float],
    enter_os: list[int] | None = None,
    enter_ob: list[int] | None = None,
    bull: list[int] | None = None,
    bear: list[int] | None = None,
    recl: list[int] | None = None,
    recs: list[int] | None = None,
    params: ReversalTrendParams | None = None,
) -> dict[str, np.ndarray]:
    assert len(rsi) == n
    return _run_state_machine(
        n=n,
        rsi=np.array(rsi, dtype=float),
        enter_os=_make_bool_array(n, enter_os),
        enter_ob=_make_bool_array(n, enter_ob),
        bull_cond_no_active=_make_bool_array(n, bull),
        bear_cond_no_active=_make_bool_array(n, bear),
        recl_cond_no_active=_make_bool_array(n, recl),
        recs_cond_no_active=_make_bool_array(n, recs),
        params=params or ReversalTrendParams(),
    )


def test_consecutive_true_run_dwell_counter() -> None:
    cond = np.array([False, True, True, True, False, True, False, False, True, True], dtype=bool)
    expected = [0, 1, 2, 3, 0, 1, 0, 0, 1, 2]
    assert list(_consecutive_true_run(cond)) == expected


def test_bull_requires_active_arm_not_just_the_macd_condition() -> None:
    n = 10
    state = _run(n, rsi=[50.0] * n, enter_os=[2], bull=[1, 5])
    # Bar 1: bull condition true, but not armed yet (enter_os fires at bar 2).
    assert not state["f_bull"][1]
    assert not state["os_active"][1]
    # Bar 2: armed, os_active true from this bar on (0 <= 35).
    assert state["os_active"][2]
    # Bar 5: armed (5-2=3<=35) and bull condition true -> fires.
    assert state["f_bull"][5]
    assert state["os_locked"][5]
    assert not state["os_armed"][6]  # cleared by the fire


def test_expire_boundary_is_strictly_greater_than_arm_max_bars() -> None:
    # os armed at bar 0; bull condition true only at the boundary bar 35
    # (35-0=35 <= 35, still active) must fire.
    n = 40
    state_boundary = _run(n, rsi=[50.0] * n, enter_os=[0], bull=[35])
    assert state_boundary["os_active"][35]
    assert state_boundary["f_bull"][35]

    # Same setup but the condition only becomes true one bar later (36-0=36>35):
    # armed context has expired, must not fire.
    n2 = 40
    state_expired = _run(n2, rsi=[50.0] * n2, enter_os=[0], bull=[36])
    assert not state_expired["os_active"][36]
    assert not state_expired["os_armed"][36]
    assert not state_expired["f_bull"][36]


def test_lock_blocks_rearm_until_rsi_reset_threshold_then_rearms() -> None:
    n = 30
    rsi = [40.0] * n
    rsi[19] = 44.9  # just under the 45 reset threshold: must stay locked
    rsi[20] = 45.0  # exactly at threshold: must unlock (>=)
    state = _run(
        n,
        rsi=rsi,
        enter_os=[2, 10, 25],  # bar10 attempted re-arm while locked; bar25 after unlock
        bull=[5],
    )
    assert state["f_bull"][5]
    assert state["os_locked"][5]
    # Attempted re-arm at bar 10 while still locked must be rejected.
    assert not state["os_armed"][10]
    assert state["os_locked"][19]
    # Unlocks exactly at bar 20 (r=45.0 >= reset_long=45).
    assert not state["os_locked"][20]
    # Re-arms successfully at bar 25 now that the lock is clear.
    assert state["os_armed"][25]
    assert state["bars_since_os_event"][25] == 0.0


def test_cooldown_blocks_repeat_fire_then_releases_at_threshold() -> None:
    n = 45
    rsi = [40.0] * n
    rsi[6] = 45.0  # unlock immediately after the first fire
    state = _run(
        n,
        rsi=rsi,
        enter_os=[0, 7],  # re-arm at bar 7, right after unlocking
        bull=[5, 15, 35],
    )
    # First fire at bar 5 (bull_cooldown default 30, last_bull was unset).
    assert state["f_bull"][5]
    # Bar 15: armed (15-7=8<=35) and condition true, but only 10 bars since the
    # last fire (< bull_cooldown=30) -- must be blocked by cooldown, not by
    # inactivity (os_active is explicitly checked to isolate the cause).
    assert state["os_active"][15]
    assert not state["f_bull"][15]
    # Bar 35: still armed (35-7=28<=35) and exactly 30 bars since the last fire
    # (>=30) -- cooldown has elapsed, must fire again.
    assert state["os_active"][35]
    assert state["f_bull"][35]


def test_recl_suppressed_when_bull_fires_on_the_same_bar() -> None:
    n = 10
    state = _run(n, rsi=[50.0] * n, enter_os=[0], bull=[5], recl=[5])
    assert state["f_bull"][5]
    assert not state["f_recl"][5]


def test_recl_fires_alone_when_bull_condition_is_absent() -> None:
    n = 10
    state = _run(n, rsi=[50.0] * n, enter_os=[0], recl=[7])
    assert state["os_active"][7]
    assert state["f_recl"][7]


def test_bear_and_recs_mirror_the_bull_and_recl_branches() -> None:
    n = 45
    rsi = [60.0] * n
    rsi[19] = 55.1  # just above the 55 reset threshold: stays locked
    rsi[20] = 55.0  # exactly at threshold: unlocks (<=)
    state = _run(n, rsi=rsi, enter_ob=[3], bear=[10])
    assert state["ob_active"][10]
    assert state["f_bear"][10]
    assert state["ob_locked"][10]
    assert state["ob_locked"][19]
    assert not state["ob_locked"][20]

    # recS suppressed by a simultaneous bear fire, but fires alone otherwise.
    state_suppressed = _run(n, rsi=[60.0] * n, enter_ob=[0], bear=[5], recs=[5])
    assert state_suppressed["f_bear"][5]
    assert not state_suppressed["f_recs"][5]

    state_alone = _run(n, rsi=[60.0] * n, enter_ob=[0], recs=[7])
    assert state_alone["ob_active"][7]
    assert state_alone["f_recs"][7]


def test_enter_os_and_enter_ob_mutually_clear_each_other() -> None:
    n = 12
    state = _run(n, rsi=[50.0] * n, enter_ob=[0, 8], enter_os=[4])
    # bar4: enter_os arms OS and clears any armed OB.
    assert state["os_armed"][4]
    assert not state["ob_armed"][4]
    # bar8: enter_ob re-arms OB and clears OS back.
    assert state["ob_armed"][8]
    assert not state["os_armed"][8]


# ---------------------------------------------------------------------------
# No-repaint: incremental bar-by-bar recomputation must match the full run.
# ---------------------------------------------------------------------------

_NO_REPAINT_COLUMNS = [
    "ema_fast",
    "ema_mid",
    "ema_slow",
    "rsi",
    "atr",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "di_plus",
    "di_minus",
    "adx",
    "dwell_os",
    "dwell_ob",
    "os_armed",
    "ob_armed",
    "os_locked",
    "ob_locked",
    "os_active",
    "ob_active",
    "f_bull",
    "f_bear",
    "f_recl",
    "f_recs",
]


def _assert_last_row_matches(full: pd.DataFrame, k: int, partial: pd.DataFrame) -> None:
    for col in _NO_REPAINT_COLUMNS:
        expected = full[col].iloc[k - 1]
        actual = partial[col].iloc[-1]
        if pd.isna(expected):
            assert pd.isna(actual), f"k={k} col={col}: expected NaN, got {actual}"
        elif isinstance(expected, (bool, np.bool_)):
            assert bool(expected) == bool(actual), f"k={k} col={col}: {expected} != {actual}"
        else:
            assert actual == pytest.approx(float(expected), rel=1e-9, abs=1e-12), (
                f"k={k} col={col}: {expected} != {actual}"
            )


def test_no_repaint_incremental_recomputation_matches_full_run() -> None:
    bars = _synthetic_ohlcv(130, seed=7)
    full = compute_reversal_trend(bars)
    for k in range(20, len(bars) + 1):
        partial = compute_reversal_trend(bars.iloc[:k])
        _assert_last_row_matches(full, k, partial)


# ---------------------------------------------------------------------------
# Validation and multi-symbol grouping
# ---------------------------------------------------------------------------


def test_missing_required_column_raises() -> None:
    bars = _synthetic_ohlcv(20).drop(columns=["volume"])
    with pytest.raises(ValueError, match="missing required columns"):
        compute_reversal_trend(bars)


def test_empty_bars_raises() -> None:
    bars = _synthetic_ohlcv(5).iloc[0:0]
    with pytest.raises(ValueError, match="at least one row"):
        compute_reversal_trend(bars)


def test_unsorted_timestamps_raise() -> None:
    bars = _synthetic_ohlcv(10)
    shuffled = bars.iloc[[0, 2, 1, 3, 4, 5, 6, 7, 8, 9]].reset_index(drop=True)
    with pytest.raises(ValueError, match="sorted ascending"):
        compute_reversal_trend(shuffled)


def test_symbol_grouping_runs_state_machine_independently_per_symbol() -> None:
    a = _synthetic_ohlcv(80, seed=11, start_price=50.0)
    b = _synthetic_ohlcv(80, seed=97, start_price=400.0)
    a["symbol"] = "AAA"
    b["symbol"] = "BBB"

    result_a_alone = compute_reversal_trend(a.drop(columns=["symbol"]))
    result_b_alone = compute_reversal_trend(b.drop(columns=["symbol"]))
    combined = compute_reversal_trend(pd.concat([a, b], axis=0))

    combined_a = combined[combined["symbol"] == "AAA"].reset_index(drop=True)
    combined_b = combined[combined["symbol"] == "BBB"].reset_index(drop=True)

    for col in _NO_REPAINT_COLUMNS:
        np.testing.assert_allclose(
            combined_a[col].to_numpy(dtype=float),
            result_a_alone[col].to_numpy(dtype=float),
            rtol=1e-9,
            atol=1e-12,
            equal_nan=True,
        )
        np.testing.assert_allclose(
            combined_b[col].to_numpy(dtype=float),
            result_b_alone[col].to_numpy(dtype=float),
            rtol=1e-9,
            atol=1e-12,
            equal_nan=True,
        )


# ---------------------------------------------------------------------------
# (c) Real SPY daily data: finite/bounded signal count, no repaint.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (default_sip_root() / "daily").is_dir(),
    reason="local SIP daily archive (data/sip/daily) is not present",
)
def test_real_spy_daily_signal_count_is_bounded_and_no_repaint() -> None:
    frame = load_sip_bars("SPY", frequency="daily", start="2018-01-01", end="2025-06-30")
    params = ReversalTrendParams()
    result = compute_reversal_trend(frame, params)
    n_bars = len(result)

    # Signal count must be finite and is provably bounded by the cooldown: two
    # fires of the same signal type can never be closer than its cooldown, so
    # the count can never exceed n_bars // cooldown + 1 regardless of the
    # actual price path.
    for column, cooldown in (
        ("f_bull", params.bull_cooldown),
        ("f_bear", params.bear_cooldown),
        ("f_recl", params.recl_cooldown),
        ("f_recs", params.recs_cooldown),
    ):
        count = int(result[column].sum())
        assert 0 <= count <= n_bars // cooldown + 1

    total_signals = int(result[["f_bull", "f_bear", "f_recl", "f_recs"]].to_numpy().sum())
    assert total_signals > 0, "expected at least one signal over a multi-year SPY daily window"

    # No-repaint spot check over the last 25 bars: recomputing from scratch on a
    # truncated frame must reproduce the full run's last row exactly.
    for k in range(n_bars - 25, n_bars + 1):
        partial = compute_reversal_trend(frame.iloc[:k], params)
        _assert_last_row_matches(result, k, partial)
