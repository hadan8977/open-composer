"""Strategy plugin interface and two example plugins.

A plugin sees only what existed at the decision time: completed bars of the current session at
its own timeframe (``bar_close_ts <= decision_ts``), prior-session minute bars when it asks for
history, its own virtual position and its own persisted state.  It returns target positions
(shares or notional per symbol); symbols it does not mention keep their standing target.  The
engine enforces the point-in-time rule (``assert_point_in_time``) before every call.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, ClassVar, Protocol

import pandas as pd

from open_composer.market_calendar import NEW_YORK


class PluginError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    """Desired signed position: exactly one of ``shares`` / ``notional_usd`` (negative = short)."""

    shares: float | None = None
    notional_usd: float | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if (self.shares is None) == (self.notional_usd is None):
            raise PluginError("Target needs exactly one of shares / notional_usd")


@dataclass(frozen=True)
class PluginContext:
    strategy: str
    session: date
    decision_ts: pd.Timestamp  # UTC, close of the bar that just completed
    timeframe: str
    bars: pd.DataFrame  # symbol, bar_close_ts, open..volume, feed; today only, completed bars
    history: pd.DataFrame  # prior-session RTH minute bars (symbol, timestamp, ohlcv); may be empty
    positions: Mapping[str, float]
    last_prices: Mapping[str, float]
    state: Mapping[str, Any]
    capital_usd: float
    day_pnl_usd: float
    # official previous-session close, unadjusted (daily bar, raw, SIP); falls back to the last
    # minute close of that session (flagged in the event log); only the strategy's own symbols
    prev_close_raw: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginDecision:
    targets: dict[str, Target] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    note: str = ""


class StrategyPlugin(Protocol):
    history_days: int

    def decide(self, ctx: PluginContext) -> PluginDecision: ...


class IntradayPlugin:
    """Base class: ``decide`` is the only required method."""

    history_days: ClassVar[int] = 0

    def __init__(self, params: Mapping[str, Any], symbols: tuple[str, ...], timeframe: str):
        self.params = dict(params)
        self.symbols = symbols
        self.timeframe = timeframe

    def decide(self, ctx: PluginContext) -> PluginDecision:  # pragma: no cover - interface
        raise NotImplementedError


def assert_point_in_time(ctx: PluginContext) -> None:
    """Refuse a context that contains data from the future of ``decision_ts``."""
    if not ctx.bars.empty and ctx.bars["bar_close_ts"].max() > ctx.decision_ts:
        raise PluginError("look-ahead: bars contain a bar closing after the decision time")
    if not ctx.history.empty:
        ts = pd.to_datetime(ctx.history["timestamp"], utc=True)
        sessions = ts.dt.tz_convert(NEW_YORK).dt.date
        if (sessions >= ctx.session).any():
            raise PluginError("look-ahead: history contains the current or a later session")


_REGISTRY: dict[str, type[IntradayPlugin]] = {}


def register_plugin(name: str):
    def wrap(cls: type[IntradayPlugin]) -> type[IntradayPlugin]:
        _REGISTRY[name] = cls
        return cls

    return wrap


def build_plugin(
    name: str, params: Mapping[str, Any], symbols: tuple[str, ...], timeframe: str
) -> IntradayPlugin:
    """``name`` is a registered short name or ``package.module:ClassName`` (T-15 / T-21 specs)."""
    if name in _REGISTRY:
        return _REGISTRY[name](params, symbols, timeframe)
    if ":" in name:
        module_name, _, class_name = name.partition(":")
        if not module_name.startswith("open_composer."):
            raise PluginError("dotted plugin paths must live under open_composer.")
        cls = getattr(importlib.import_module(module_name), class_name)
        return cls(params, symbols, timeframe)
    raise PluginError(f"unknown plugin {name!r}; registered: {sorted(_REGISTRY)}")


def _et_minutes(ts: pd.Timestamp) -> int:
    local = ts.tz_convert(NEW_YORK)
    return local.hour * 60 + local.minute


def _hhmm(value: str) -> int:
    hour, minute = (int(part) for part in str(value).split(":"))
    return hour * 60 + minute


@register_plugin("timed_trade")
class TimedTrade(IntradayPlugin):
    """Test plugin: hold ``side`` ``shares`` of ``symbol`` from ``enter_et`` until ``exit_et``."""

    def decide(self, ctx: PluginContext) -> PluginDecision:
        symbol = str(self.params["symbol"]).upper()
        shares = float(self.params["shares"])
        sign = -1.0 if str(self.params.get("side", "long")) == "short" else 1.0
        now = _et_minutes(ctx.decision_ts)
        holding = _hhmm(self.params["enter_et"]) <= now < _hhmm(self.params["exit_et"])
        target = Target(shares=sign * shares if holding else 0.0, reason="timed")
        return PluginDecision(targets={symbol: target}, note="hold" if holding else "flat")


@register_plugin("noise_band_example")
class NoiseBandExample(IntradayPlugin):
    """Example only (not a research spec): noise-area breakout in the style of Zarattini, Aziz
    and Barbon (2024).  Per minute-of-day sigma = mean over the previous ``lookback_days``
    sessions of |close/open_of_that_session - 1|; upper = max(open, prev_close)*(1+m*sigma),
    lower = min(open, prev_close)*(1-m*sigma).  Long above upper, short below lower, exit when
    price falls back through the band or the session VWAP."""

    history_days = 14

    def decide(self, ctx: PluginContext) -> PluginDecision:
        symbol = str(self.params.get("symbol", "SPY")).upper()
        mult = float(self.params.get("band_mult", 1.0))
        notional = float(self.params.get("notional_usd", 100_000.0))
        lookback = int(self.params.get("lookback_days", self.history_days))
        bars = ctx.bars[ctx.bars["symbol"] == symbol]
        hist = ctx.history[ctx.history["symbol"] == symbol]
        if bars.empty or hist.empty:
            return PluginDecision(state=dict(ctx.state), note="no_data")
        open_today = float(bars.iloc[0]["open"])
        close_now = float(bars.iloc[-1]["close"])
        offset = _et_minutes(ctx.decision_ts) - (9 * 60 + 30)
        hist = hist.assign(
            ts=pd.to_datetime(hist["timestamp"], utc=True).dt.tz_convert(NEW_YORK)
        ).assign(day=lambda f: f["ts"].dt.date)
        days = sorted(hist["day"].unique())[-lookback:]
        moves: list[float] = []
        prev_close = None
        for day in days:
            frame = hist[hist["day"] == day].sort_values("ts")
            minutes = frame["ts"].dt.hour * 60 + frame["ts"].dt.minute - (9 * 60 + 30)
            frame = frame[(minutes >= 0) & (minutes < 390)]
            if frame.empty:
                continue
            upto = frame[(frame["ts"].dt.hour * 60 + frame["ts"].dt.minute - 570) <= offset - 1]
            if not upto.empty:
                moves.append(abs(float(upto.iloc[-1]["close"]) / float(frame.iloc[0]["open"]) - 1))
            prev_close = float(frame.iloc[-1]["close"])
        if not moves or prev_close is None:
            return PluginDecision(state=dict(ctx.state), note="no_history")
        sigma = sum(moves) / len(moves)
        upper = max(open_today, prev_close) * (1 + mult * sigma)
        lower = min(open_today, prev_close) * (1 - mult * sigma)
        typical = (bars["high"] + bars["low"] + bars["close"]) / 3
        volume = bars["volume"].astype(float)
        vwap = float((typical * volume).sum() / volume.sum()) if volume.sum() > 0 else close_now
        side = int(ctx.state.get("side", 0))
        if side == 0:
            side = 1 if close_now > upper else -1 if close_now < lower else 0
        elif side == 1 and (close_now < upper or close_now < vwap):
            side = 0
        elif side == -1 and (close_now > lower or close_now > vwap):
            side = 0
        target = Target(notional_usd=side * notional, reason=f"band[{lower:.2f},{upper:.2f}]")
        return PluginDecision(
            targets={symbol: target},
            state={"side": side},
            note=f"close={close_now:.2f} lower={lower:.2f} upper={upper:.2f} vwap={vwap:.2f}",
        )
