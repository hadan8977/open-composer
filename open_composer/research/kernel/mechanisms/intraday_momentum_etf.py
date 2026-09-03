"""Single-ETF intraday opening-range momentum, after Zarattini/Aziz/Barbon
(SSRN 4824172, "Beat the Market: An Effective Intraday Momentum Strategy for
S&P500 ETF (SPY)") and Maroy's follow-up on exit-rule sensitivity (SSRN
5095349). Both are source-carded in
``reports/harness/source_cards/goal_first_w7.jsonl``.

This is a causal simplification, not a byte-identical replication: the paper
initiates a position "as soon as there is an indication of abnormal
demand/supply imbalance", checked continuously through the session; this
mechanism checks the same volatility-scaled noise-band condition at every RTH
bar close and enters long the first time price clears the band above the
session's own open. It is long-only (this project's prevailing convention;
see the champion route's ``position_direction: long_only``) and flat
overnight (no position carried past the session close, so it carries no
overnight gap risk to model).

Every feature is computed from data strictly before the bar it is evaluated
at: the noise band uses only the ``lookback_sessions`` *prior* completed
sessions' true ranges, and the entry/exit decision at bar ``t`` uses only
bars up to and including ``t`` of the *current* session. There is no use of
that session's own close, high, or low ahead of when it is realized.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

COST_BPS_PER_SIDE = 3.0  # 2bps commission-equivalent + 1bps assumed half-spread


def _session_true_ranges(daily_ohlc: pd.DataFrame) -> pd.Series:
    """Prior-session true range (high-low) per session, used to size the noise band."""
    return (daily_ohlc["high"] - daily_ohlc["low"]).rename("true_range")


def daily_intraday_momentum_returns(
    bars: pd.DataFrame,
    params: Mapping[str, Any],
) -> pd.Series:
    """One return per RTH session: the day's realized P&L from this rule, or 0.0 if flat.

    ``bars`` must be RTH-resampled intraday bars for a single symbol (see
    ``open_composer.research.kernel.resample.resample_rth_bars``), columns
    ``timestamp, open, high, low, close``, sorted ascending, tz-aware UTC.

    Parameters (``params``):
        noise_multiplier: float -- noise band = multiplier x trailing mean
            session true range.
        lookback_sessions: int -- how many prior sessions the noise band's
            trailing mean is computed over.
        use_trailing_stop: bool -- exit early if price gives back
            ``trailing_stop_fraction`` of the noise band from its post-entry peak.
        trailing_stop_fraction: float -- fraction of the noise band used as
            the trailing-stop distance when ``use_trailing_stop`` is True.
        cost_bps_per_side: float -- override for :data:`COST_BPS_PER_SIDE`.
    """
    noise_multiplier = float(params["noise_multiplier"])
    lookback_sessions = int(params["lookback_sessions"])
    use_trailing_stop = bool(params["use_trailing_stop"])
    trailing_stop_fraction = float(params.get("trailing_stop_fraction", 0.5))
    cost_bps_per_side = float(params.get("cost_bps_per_side", COST_BPS_PER_SIDE))

    working = bars.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    working = working.sort_values("timestamp")
    working["session_date"] = working["timestamp"].dt.tz_convert("America/New_York").dt.date

    daily_ohlc = working.groupby("session_date").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    true_range = _session_true_ranges(daily_ohlc)
    # shift(1): the noise band available "as of" session S's open only ever
    # uses sessions strictly before S.
    trailing_true_range = true_range.rolling(
        lookback_sessions, min_periods=lookback_sessions
    ).mean()
    noise_band_by_session = (trailing_true_range * noise_multiplier).shift(1)

    session_dates = sorted(working["session_date"].unique())
    round_trip_cost = 2.0 * cost_bps_per_side / 10_000.0

    returns: dict[pd.Timestamp, float] = {}
    for session_date in session_dates:
        if session_date not in noise_band_by_session.index or pd.isna(
            noise_band_by_session.loc[session_date]
        ):
            continue  # not enough trailing history yet -- stay flat, not zero-filled-as-signal
        noise_band = float(noise_band_by_session.loc[session_date])
        if noise_band <= 0:
            continue
        session_bars = working.loc[working["session_date"] == session_date].reset_index(drop=True)
        session_open = float(session_bars["open"].iloc[0])
        breakout_level = session_open + noise_band

        entry_price: float | None = None
        exit_price: float | None = None
        peak_price: float | None = None
        for _, bar in session_bars.iterrows():
            price = float(bar["close"])
            if entry_price is None:
                if price >= breakout_level:
                    entry_price = price
                    peak_price = price
                continue
            peak_price = max(peak_price, price)
            if use_trailing_stop and price <= peak_price - noise_band * trailing_stop_fraction:
                exit_price = price
                break
        # A naive midnight Timestamp keyed on the session's calendar date, not
        # a tz-aware normalize() of the last intraday bar: benchmark daily
        # return series (see rolling_origin.returns_from_ohlcv) keep SIP's
        # native tz-aware time-of-day (e.g. 04:00 UTC), which a tz-aware
        # midnight index does not match on reindex even for the same day --
        # this is the same class of mismatch fixed in
        # scripts/evaluate_champion_route_sip.py's benchmark construction.
        session_end = pd.Timestamp(session_date)
        if entry_price is None:
            # Never broke out: flat for the day. Recorded as 0.0, not omitted --
            # omitting no-trade days would understate the elapsed-time basis the
            # harness annualizes Sharpe/CAGR over (rolling_origin_folds and
            # annualized_sharpe both scale by the *count* of observations, so a
            # sparse series of trade-days only would silently inflate both).
            returns[session_end] = 0.0
            continue
        if exit_price is None:
            exit_price = float(session_bars["close"].iloc[-1])  # hold to session close
        returns[session_end] = (exit_price / entry_price - 1.0) - round_trip_cost

    if not returns:
        raise ValueError("no session had enough trailing history for a noise band to be computed")
    # A parameter vector that never trades (e.g. an extreme noise_multiplier) is
    # not an error here -- it produces a legitimate all-zero return stream that
    # the promotion gates (Sharpe, DSR, MAR) will correctly score as unattractive
    # rather than something this mechanism should crash a whole grid search over.
    index = pd.DatetimeIndex(sorted(returns))
    return pd.Series([returns[ts] for ts in index], index=index, name="intraday_momentum_etf")


#: 18-combination bounded grid, per docs/plan-goal-first-verification-2026-09-02.zh.md
#: Wave W4: noise multiplier {0.5, 1.0, 1.5} x lookback {10, 14, 20} x stop {on, off}.
PARAMETER_SPACE: list[dict[str, Any]] = [
    {
        "noise_multiplier": noise_multiplier,
        "lookback_sessions": lookback_sessions,
        "use_trailing_stop": use_trailing_stop,
        "trailing_stop_fraction": 0.5,
    }
    for noise_multiplier in (0.5, 1.0, 1.5)
    for lookback_sessions in (10, 14, 20)
    for use_trailing_stop in (False, True)
]
