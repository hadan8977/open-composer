"""Python port of ``docs/inputs/pine/reversal_trend_0522.pine`` (Pine v6,
indicator "Reversal Trend").

Plan: ``docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md``
section 1. That section is the authoritative Python-semantics restatement of the
Pine source and this module must follow it literally -- do not "improve" or
symmetrize the formulas (for example ``bear`` deliberately has no MACD-histogram
confirmation term while ``bull`` does; that asymmetry is in the original script,
line 112-113 vs 109-110, and is preserved here on purpose).

Base primitives (``ta.ema``/``ta.rma``/``ta.rsi``/``ta.atr``/``ta.dmi``/
``ta.crossover``/``ta.highest``/``ta.lowest``) are vectorized with pandas/numpy.
The event state machine (dwell counters aside -- see :func:`_consecutive_true_run`)
has genuine cross-bar feedback (armed/locked flags and cooldown timers that
depend on whether a signal fired on a *previous* bar) and is therefore run as an
explicit bar-by-bar loop, once per symbol, per the plan's instruction ("状态机按
symbol 顺序循环，其余向量化"). ``bars`` must already be sorted ascending by
timestamp within each symbol -- this module never re-sorts input, only checks it.

``barstate.isconfirmed`` is always true on historical bars (plan section 1), so it
is not modeled as a separate flag here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")

_HIST_MODES = ("Off", "1 Bar", "2 Bars")


@dataclass(frozen=True)
class ReversalTrendParams:
    """Indicator inputs, defaulted to the Pine script's own default values.

    Plan section 1: "参数（全部沿用脚本默认值，本周不调）" -- these defaults must
    not be tuned; the preregistered grids in sections A3/3 only search exit-rule
    and holding-period dimensions, never these fields.
    """

    ema_fast_len: int = 20
    ema_mid_len: int = 50
    ema_slow_len: int = 200
    rsi_len: int = 14
    rsi_ob: float = 70.0
    rsi_os: float = 30.0
    rsi_bull_min: float = 40.0
    rsi_bull_max: float = 65.0
    rsi_bear_min: float = 35.0
    rsi_bear_max: float = 60.0
    extreme_lookback: int = 15
    recs_rsi_peak: float = 78.0
    arm_max_bars: int = 35
    rsi_reset_long: float = 45.0
    rsi_reset_short: float = 55.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    hist_mode: str = "1 Bar"
    adx_len: int = 14
    adx_min_bull: float = 18.0
    adx_min_bear: float = 15.0
    dwell_min: int = 5
    atr_len: int = 14
    recs_min_atr_ext: float = 0.35
    bull_cooldown: int = 30
    bear_cooldown: int = 20
    recl_cooldown: int = 8
    recs_cooldown: int = 8

    def __post_init__(self) -> None:
        if self.hist_mode not in _HIST_MODES:
            raise ValueError(f"hist_mode must be one of {_HIST_MODES}, got {self.hist_mode!r}")


def compute_reversal_trend(
    bars: pd.DataFrame, params: ReversalTrendParams | None = None
) -> pd.DataFrame:
    """Compute every Reversal Trend indicator/state/signal column for ``bars``.

    Parameters
    ----------
    bars:
        Must contain ``open, high, low, close, volume``. An optional ``symbol``
        column groups the frame and runs the state machine independently per
        symbol (order-preserving groupby, no re-sort). An optional ``timestamp``
        column is used only to validate ascending order, never to resample.
        Works on any bar period (daily, hourly, minute) -- the formulas are the
        same, only the meaning of "1 bar" changes.
    params:
        Defaults to the Pine script's own defaults; see :class:`ReversalTrendParams`.

    Returns
    -------
    A copy of ``bars`` with indicator columns (``ema_fast``, ``ema_mid``,
    ``ema_slow``, ``rsi``, ``atr``, ``macd_line``, ``macd_signal``, ``macd_hist``,
    ``di_plus``, ``di_minus``, ``adx``, ``rsi_lowest_15``, ``rsi_highest_15``,
    ``macd_bull_cross``, ``macd_bear_cross``), state columns (``dwell_os``,
    ``dwell_ob``, ``os_armed``, ``ob_armed``, ``os_locked``, ``ob_locked``,
    ``os_active``, ``ob_active``, ``bars_since_os_event``, ``bars_since_ob_event``,
    plus the pre-cooldown raw signals ``bull_raw``/``bear_raw``/``recl_raw``/
    ``recs_raw``), and the four final signal columns ``f_bull``, ``f_bear``,
    ``f_recl``, ``f_recs`` (Pine's ``fBull``/``fBear``/``fRecL``/``fRecS``)
    appended.
    """
    if params is None:
        params = ReversalTrendParams()
    missing = [column for column in REQUIRED_COLUMNS if column not in bars.columns]
    if missing:
        raise ValueError(f"bars is missing required columns: {missing}")
    if bars.empty:
        raise ValueError("compute_reversal_trend requires at least one row")
    _validate_sorted(bars)

    if "symbol" in bars.columns:
        parts = [_compute_single(group, params) for _, group in bars.groupby("symbol", sort=False)]
        return pd.concat(parts, axis=0)
    return _compute_single(bars, params)


def _validate_sorted(bars: pd.DataFrame) -> None:
    if "timestamp" not in bars.columns:
        return
    timestamps = pd.to_datetime(bars["timestamp"])
    if "symbol" in bars.columns:
        ok = timestamps.groupby(bars["symbol"], sort=False).is_monotonic_increasing
        if not bool(ok.all()):
            raise ValueError("bars must be sorted ascending by timestamp within each symbol")
    elif not timestamps.is_monotonic_increasing:
        raise ValueError("bars must be sorted ascending by timestamp")


def _compute_single(group: pd.DataFrame, params: ReversalTrendParams) -> pd.DataFrame:
    n = len(group)
    out = group.copy()
    close = group["close"].astype(float)
    high = group["high"].astype(float)
    low = group["low"].astype(float)

    ema_fast = _ema(close, params.ema_fast_len)
    ema_mid = _ema(close, params.ema_mid_len)
    ema_slow = _ema(close, params.ema_slow_len)
    rsi = _rsi(close, params.rsi_len)
    atr = _atr(high, low, close, params.atr_len)
    macd_line, macd_signal, macd_hist = _macd(
        close, params.macd_fast, params.macd_slow, params.macd_signal
    )
    di_plus, di_minus, adx = _dmi(high, low, close, params.adx_len)

    rsi_lowest_15 = _rolling_lowest(rsi, params.extreme_lookback)
    rsi_highest_15 = _rolling_highest(rsi, params.extreme_lookback)

    macd_bull_cross = _crossover(macd_line, macd_signal)
    macd_bear_cross = _crossunder(macd_line, macd_signal)

    hist_up_ok, hist_dn_ok = _hist_confirmation(macd_hist, params.hist_mode)

    r_cross_up_os = _crossover_level(rsi, params.rsi_os)
    r_cross_dn_ob = _crossunder_level(rsi, params.rsi_ob)

    rsi_prev = rsi.shift(1)
    in_os = rsi <= params.rsi_os
    in_ob = rsi >= params.rsi_ob
    enter_os = in_os & (rsi_prev.isna() | (rsi_prev > params.rsi_os))
    enter_ob = in_ob & (rsi_prev.isna() | (rsi_prev < params.rsi_ob))

    dwell_os = _consecutive_true_run((rsi <= params.rsi_os).to_numpy())
    dwell_ob = _consecutive_true_run((rsi >= params.rsi_ob).to_numpy())
    dwell_os_prev = np.concatenate(([0], dwell_os[:-1])) if n else dwell_os
    dwell_ob_prev = np.concatenate(([0], dwell_ob[:-1])) if n else dwell_ob

    bull_cond_no_active = (
        macd_bull_cross
        & (rsi > params.rsi_bull_min)
        & (rsi < params.rsi_bull_max)
        & (close > ema_fast)
        & (adx > params.adx_min_bull)
        & hist_up_ok
    )
    # Note: no histogram confirmation term for bear -- matches Pine lines 112-113
    # exactly, an intentional asymmetry versus bull (lines 109-110).
    bear_cond_no_active = (
        macd_bear_cross
        & (rsi > params.rsi_bear_min)
        & (rsi < params.rsi_bear_max)
        & (close < ema_fast)
        & (adx > params.adx_min_bear)
    )
    recl_cond_no_active = (
        r_cross_up_os & (dwell_os_prev >= params.dwell_min) & (close < ema_mid) & hist_up_ok
    )

    atr_positive = atr > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        atr_extension = (close - ema_fast) / atr
    recs_extended = atr_positive & (atr_extension >= params.recs_min_atr_ext)
    recs_hot = (
        (rsi_highest_15 >= params.recs_rsi_peak)
        & (close > ema_fast)
        & (close > ema_mid)
        & recs_extended
    )
    recs_cond_no_active = (
        r_cross_dn_ob & (dwell_ob_prev >= params.dwell_min) & recs_hot & hist_dn_ok
    )

    state = _run_state_machine(
        n=n,
        rsi=rsi.to_numpy(),
        enter_os=enter_os.to_numpy(),
        enter_ob=enter_ob.to_numpy(),
        bull_cond_no_active=bull_cond_no_active.to_numpy(),
        bear_cond_no_active=bear_cond_no_active.to_numpy(),
        recl_cond_no_active=recl_cond_no_active.to_numpy(),
        recs_cond_no_active=recs_cond_no_active.to_numpy(),
        params=params,
    )

    out["ema_fast"] = ema_fast
    out["ema_mid"] = ema_mid
    out["ema_slow"] = ema_slow
    out["rsi"] = rsi
    out["atr"] = atr
    out["macd_line"] = macd_line
    out["macd_signal"] = macd_signal
    out["macd_hist"] = macd_hist
    out["di_plus"] = di_plus
    out["di_minus"] = di_minus
    out["adx"] = adx
    out["rsi_lowest_15"] = rsi_lowest_15
    out["rsi_highest_15"] = rsi_highest_15
    out["macd_bull_cross"] = macd_bull_cross.to_numpy()
    out["macd_bear_cross"] = macd_bear_cross.to_numpy()

    out["dwell_os"] = dwell_os
    out["dwell_ob"] = dwell_ob
    out["os_armed"] = state["os_armed"]
    out["ob_armed"] = state["ob_armed"]
    out["os_locked"] = state["os_locked"]
    out["ob_locked"] = state["ob_locked"]
    out["os_active"] = state["os_active"]
    out["ob_active"] = state["ob_active"]
    out["bars_since_os_event"] = state["bars_since_os_event"]
    out["bars_since_ob_event"] = state["bars_since_ob_event"]
    out["bull_raw"] = state["bull_raw"]
    out["bear_raw"] = state["bear_raw"]
    out["recl_raw"] = state["recl_raw"]
    out["recs_raw"] = state["recs_raw"]

    out["f_bull"] = state["f_bull"]
    out["f_bear"] = state["f_bear"]
    out["f_recl"] = state["f_recl"]
    out["f_recs"] = state["f_recs"]

    return out


# ---------------------------------------------------------------------------
# Base primitives -- Pine's exact recursive definitions (plan section 1).
# ---------------------------------------------------------------------------


def _ema(x: pd.Series, length: int) -> pd.Series:
    """``ta.ema``: alpha=2/(n+1), seeded with the first non-NA value of ``x``.

    ``pandas.Series.ewm(adjust=False)`` implements exactly this recursion,
    including seeding at the first non-NA value when ``x`` has leading NaNs.
    """
    alpha = 2.0 / (length + 1)
    return x.ewm(alpha=alpha, adjust=False).mean()


def _rma(x: pd.Series, length: int) -> pd.Series:
    """``ta.rma`` (Wilder smoothing): alpha=1/n, seeded with the SMA of the
    first ``n`` non-NA values of ``x`` (plan section 1). This is *not* the same
    seed rule as ``ta.ema``, so it cannot be computed with a plain ``.ewm()`` call
    -- the seed is injected manually, then the remaining tail is filtered with
    ``ewm(adjust=False)`` starting from that seed as its initial value.
    """
    values = x.to_numpy(dtype=float)
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    valid = ~np.isnan(values)
    if not valid.any():
        return pd.Series(out, index=x.index)
    first_valid = int(np.argmax(valid))
    seed_end = first_valid + length  # exclusive index of the seed window
    if seed_end > n:
        return pd.Series(out, index=x.index)
    seed = float(values[first_valid:seed_end].mean())
    out[seed_end - 1] = seed
    remaining = n - seed_end
    if remaining > 0:
        alpha = 1.0 / length
        tail = np.empty(remaining + 1, dtype=float)
        tail[0] = seed
        tail[1:] = values[seed_end:]
        smoothed = pd.Series(tail).ewm(alpha=alpha, adjust=False).mean().to_numpy()
        out[seed_end - 1 :] = smoothed
    return pd.Series(out, index=x.index)


def _rsi(close: pd.Series, length: int) -> pd.Series:
    """``ta.rsi(close, length) = 100 - 100/(1 + rma(max(delta,0),n)/rma(max(-delta,0),n))``."""
    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)
    avg_gain = _rma(gains, length)
    avg_loss = _rma(losses, length)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """``TR = max(high-low, |high-close[1]|, |low-close[1]|)``.

    The first bar has no ``close[1]``; ``DataFrame.max(axis=1, skipna=True)``
    then naturally falls back to ``high-low`` for that row (the other two terms
    are NaN and are skipped), matching Pine's ``ta.atr``/``ta.dmi`` internal
    true-range computation (handle_na=true) without a special-cased branch.
    """
    prev_close = close.shift(1)
    ranges = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1, skipna=True)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    return _rma(_true_range(high, low, close), length)


def _macd(
    close: pd.Series, fast: int, slow: int, signal: int
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """``ta.macd``: ``m = ema(close,fast) - ema(close,slow)``, ``s = ema(m,signal)``,
    ``hist = m - s``."""
    macd_line = _ema(close, fast) - _ema(close, slow)
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _dmi(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """``ta.dmi(length, length)``: classic Wilder +DM/-DM/+DI/-DI/ADX, reusing the
    same handle_na-style true range as :func:`_atr` per the plan's unified TR
    definition. Includes Pine's built-in ADX zero-sum guard (``sum==0 ? 1 : sum``)
    so a fully flat +DI/-DI pair (e.g. degenerate, unmoving OHLC) yields DX=0
    rather than 0/0; this never changes the result for any non-degenerate bar.
    """
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
    )
    plus_dm[up_move.isna()] = np.nan
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=low.index
    )
    minus_dm[down_move.isna()] = np.nan

    tr_rma = _rma(_true_range(high, low, close), length)
    plus_di = 100.0 * _rma(plus_dm, length) / tr_rma
    minus_di = 100.0 * _rma(minus_dm, length) / tr_rma

    denom = plus_di + minus_di
    denom_safe = denom.where(denom != 0, 1.0)
    dx = 100.0 * (plus_di - minus_di).abs() / denom_safe
    adx = _rma(dx, length)
    return plus_di, minus_di, adx


def _crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    """``ta.crossover(a, b) = a > b and a[1] <= b[1]``, both series time-varying."""
    return (a > b) & (a.shift(1) <= b.shift(1))


def _crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    """``ta.crossunder(a, b) = a < b and a[1] >= b[1]``, both series time-varying."""
    return (a < b) & (a.shift(1) >= b.shift(1))


def _crossover_level(a: pd.Series, level: float) -> pd.Series:
    """Crossover of a series above a fixed constant (e.g. ``crossover(r, 30)``).

    The constant is not itself a historical series, so only ``a`` is shifted --
    shifting the constant too (as :func:`_crossover` does for two real series)
    would wrongly introduce a spurious NaN at bar 0.
    """
    return (a > level) & (a.shift(1) <= level)


def _crossunder_level(a: pd.Series, level: float) -> pd.Series:
    """Crossunder of a series below a fixed constant (e.g. ``crossunder(r, 70)``)."""
    return (a < level) & (a.shift(1) >= level)


def _rolling_highest(x: pd.Series, length: int) -> pd.Series:
    """``ta.highest(x, n)``: rolling max including the current bar."""
    return x.rolling(window=length, min_periods=length).max()


def _rolling_lowest(x: pd.Series, length: int) -> pd.Series:
    """``ta.lowest(x, n)``: rolling min including the current bar."""
    return x.rolling(window=length, min_periods=length).min()


def _hist_confirmation(hist: pd.Series, mode: str) -> tuple[pd.Series, pd.Series]:
    """``histUpOk``/``histDnOk`` per ``histMode`` (default "1 Bar")."""
    if mode == "Off":
        true_series = pd.Series(True, index=hist.index)
        return true_series, true_series.copy()
    hist_prev1 = hist.shift(1)
    if mode == "1 Bar":
        return hist > hist_prev1, hist < hist_prev1
    # "2 Bars"
    hist_prev2 = hist.shift(2)
    up = (hist > hist_prev1) & (hist_prev1 > hist_prev2)
    down = (hist < hist_prev1) & (hist_prev1 < hist_prev2)
    return up, down


def _consecutive_true_run(cond: np.ndarray) -> np.ndarray:
    """Vectorized "consecutive True count ending at this index" (dwell counters).

    Equivalent to the recursion ``run[t] = cond[t] ? run[t-1] + 1 : 0`` with
    ``run[-1] = 0``, computed without a Python-level loop: for each position,
    find the index of the most recent False (a "reset point") via a running
    max over reset-position markers, then the run length is simply the distance
    from that reset point.
    """
    n = len(cond)
    idx = np.arange(n)
    reset_positions = np.where(~cond, idx, -1)
    last_reset = np.maximum.accumulate(reset_positions)
    run = np.where(cond, idx - last_reset, 0)
    return run.astype(np.int64)


def _run_state_machine(
    *,
    n: int,
    rsi: np.ndarray,
    enter_os: np.ndarray,
    enter_ob: np.ndarray,
    bull_cond_no_active: np.ndarray,
    bear_cond_no_active: np.ndarray,
    recl_cond_no_active: np.ndarray,
    recs_cond_no_active: np.ndarray,
    params: ReversalTrendParams,
) -> dict[str, np.ndarray]:
    """The arm/expire/lock/cooldown state machine, plan section 1 steps 1-7.

    Genuinely sequential: ``osArmed``/``osLocked``/cooldown timers at bar ``t``
    depend on whether a signal fired at some ``t' < t``, which itself depended on
    the armed/active state at ``t'``. Everything that does *not* need this
    cross-bar feedback (crossovers, dwell counts, RSI/ADX/close range checks) is
    precomputed vectorized by the caller and passed in as plain boolean arrays.
    """
    os_armed_out = np.zeros(n, dtype=bool)
    ob_armed_out = np.zeros(n, dtype=bool)
    os_locked_out = np.zeros(n, dtype=bool)
    ob_locked_out = np.zeros(n, dtype=bool)
    os_active_out = np.zeros(n, dtype=bool)
    ob_active_out = np.zeros(n, dtype=bool)
    bars_since_os_event = np.full(n, np.nan, dtype=float)
    bars_since_ob_event = np.full(n, np.nan, dtype=float)
    bull_raw = np.zeros(n, dtype=bool)
    bear_raw = np.zeros(n, dtype=bool)
    recl_raw = np.zeros(n, dtype=bool)
    recs_raw = np.zeros(n, dtype=bool)
    f_bull = np.zeros(n, dtype=bool)
    f_bear = np.zeros(n, dtype=bool)
    f_recl = np.zeros(n, dtype=bool)
    f_recs = np.zeros(n, dtype=bool)

    os_locked = False
    ob_locked = False
    os_armed = False
    ob_armed = False
    os_bar = -1
    ob_bar = -1
    last_bull = -1
    last_bear = -1
    last_recl = -1
    last_recs = -1

    reset_long = params.rsi_reset_long
    reset_short = params.rsi_reset_short
    arm_max = params.arm_max_bars
    bull_cd = params.bull_cooldown
    bear_cd = params.bear_cooldown
    recl_cd = params.recl_cooldown
    recs_cd = params.recs_cooldown

    for t in range(n):
        r_t = rsi[t]

        # 1. unlock
        if os_locked and r_t >= reset_long:
            os_locked = False
        if ob_locked and r_t <= reset_short:
            ob_locked = False

        # 2. arm on entering an extreme (mutually exclusive in practice: RSI
        # cannot be both <= os and >= ob on the same bar).
        if enter_os[t] and not os_locked:
            os_armed = True
            ob_armed = False
            os_bar = t
        if enter_ob[t] and not ob_locked:
            ob_armed = True
            os_armed = False
            ob_bar = t

        # 3. expire (strictly greater than arm_max bars since the arming bar)
        if os_armed and os_bar != -1 and (t - os_bar) > arm_max:
            os_armed = False
        if ob_armed and ob_bar != -1 and (t - ob_bar) > arm_max:
            ob_armed = False

        os_active = os_armed and os_bar != -1 and (t - os_bar) <= arm_max
        ob_active = ob_armed and ob_bar != -1 and (t - ob_bar) <= arm_max

        # 5. raw signals (recL/recS still need osActive/obActive, but only at
        # the final fRecL/fRecS gate -- plan section 1 step 5 parenthetical).
        bull_t = bool(bull_cond_no_active[t] and os_active)
        bear_t = bool(bear_cond_no_active[t] and ob_active)
        recl_t = bool(recl_cond_no_active[t])
        recs_t = bool(recs_cond_no_active[t])

        # 6. cooldown
        ok_bull = last_bull == -1 or (t - last_bull) >= bull_cd
        ok_bear = last_bear == -1 or (t - last_bear) >= bear_cd
        ok_recl = last_recl == -1 or (t - last_recl) >= recl_cd
        ok_recs = last_recs == -1 or (t - last_recs) >= recs_cd

        f_bull_t = bull_t and ok_bull
        f_bear_t = bear_t and ok_bear
        f_recl_t = recl_t and ok_recl and os_active and not f_bull_t
        f_recs_t = recs_t and ok_recs and ob_active and not f_bear_t

        if f_bull_t:
            last_bull = t
        if f_bear_t:
            last_bear = t
        if f_recl_t:
            last_recl = t
        if f_recs_t:
            last_recs = t

        # 7. trigger locks the extreme out until the RSI reset threshold.
        if f_bull_t or f_recl_t:
            os_armed = False
            os_locked = True
        if f_bear_t or f_recs_t:
            ob_armed = False
            ob_locked = True

        os_armed_out[t] = os_armed
        ob_armed_out[t] = ob_armed
        os_locked_out[t] = os_locked
        ob_locked_out[t] = ob_locked
        os_active_out[t] = os_active
        ob_active_out[t] = ob_active
        if os_bar != -1:
            bars_since_os_event[t] = t - os_bar
        if ob_bar != -1:
            bars_since_ob_event[t] = t - ob_bar
        bull_raw[t] = bull_t
        bear_raw[t] = bear_t
        recl_raw[t] = recl_t
        recs_raw[t] = recs_t
        f_bull[t] = f_bull_t
        f_bear[t] = f_bear_t
        f_recl[t] = f_recl_t
        f_recs[t] = f_recs_t

    return {
        "os_armed": os_armed_out,
        "ob_armed": ob_armed_out,
        "os_locked": os_locked_out,
        "ob_locked": ob_locked_out,
        "os_active": os_active_out,
        "ob_active": ob_active_out,
        "bars_since_os_event": bars_since_os_event,
        "bars_since_ob_event": bars_since_ob_event,
        "bull_raw": bull_raw,
        "bear_raw": bear_raw,
        "recl_raw": recl_raw,
        "recs_raw": recs_raw,
        "f_bull": f_bull,
        "f_bear": f_bear,
        "f_recl": f_recl,
        "f_recs": f_recs,
    }
