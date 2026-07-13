from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from open_composer.research.mom_minute_round import _atr_pct

LABEL_RE = re.compile(
    r"^momentum:signal(?P<signal>[A-Z]+)_target(?P<target>[A-Z]+)_tf(?P<timeframe>30m)"
    r"_lookback(?P<lookback>\d+)_atr(?P<atr>\d+(?:\.\d+)?)_weight(?P<weight>\d+(?:\.\d+)?)$"
)


@dataclass(frozen=True)
class MomentumSignalRoute:
    label: str
    signal_symbol: str
    target_symbol: str
    timeframe: str
    lookback_bars: int
    atr_filter_multiplier: float
    target_weight: float


def momentum_route_from_label(label: str) -> MomentumSignalRoute:
    match = LABEL_RE.fullmatch(label)
    if not match:
        raise ValueError(f"unsupported momentum signal route label: {label}")
    route = MomentumSignalRoute(
        label=label,
        signal_symbol=match.group("signal"),
        target_symbol=match.group("target"),
        timeframe=match.group("timeframe"),
        lookback_bars=int(match.group("lookback")),
        atr_filter_multiplier=float(match.group("atr")),
        target_weight=float(match.group("weight")),
    )
    if route.lookback_bars < 2:
        raise ValueError("momentum route lookback_bars must be >= 2")
    if not 0 < route.target_weight <= 1:
        raise ValueError("momentum route target_weight must be in (0, 1]")
    return route


def momentum_target_position(
    frame: pd.DataFrame,
    *,
    lookback_bars: int,
    atr_filter_multiplier: float,
) -> pd.Series:
    close = frame["signal_close"]
    momentum = close / close.shift(lookback_bars) - 1.0
    atr_pct = _atr_pct(frame, lookback_bars)
    threshold = close.rolling(lookback_bars, min_periods=lookback_bars).max() * (
        1 - atr_filter_multiplier * atr_pct
    )
    return ((momentum > 0) & (close > threshold)).astype(float)
