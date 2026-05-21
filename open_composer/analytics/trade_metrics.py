from __future__ import annotations

import pandas as pd

from open_composer.models.backtest import Trade


def trade_pnls(trades: list[Trade]) -> list[float]:
    return [float(trade.pnl) for trade in trades]


def trade_return_pcts(trades: list[Trade]) -> list[float]:
    return [float(trade.return_pct) for trade in trades]


def exposure_pct_from_trades(trades: list[Trade], frame: pd.DataFrame) -> float | None:
    if not trades or frame.empty or "timestamp" not in frame.columns:
        return None
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    first = timestamps.min()
    last = timestamps.max()
    if pd.isna(first) or pd.isna(last):
        return None
    total_seconds = (last - first).total_seconds()
    if total_seconds <= 0:
        return None
    held_seconds = 0.0
    for trade in trades:
        if trade.exit_time is None:
            continue
        entry = _utc_timestamp(trade.entry_time)
        exit_time = _utc_timestamp(trade.exit_time)
        held_seconds += max((exit_time - entry).total_seconds(), 0.0)
    return min(held_seconds / total_seconds * 100, 100.0)


def turnover_ratio_from_trades(trades: list[Trade], start_equity: float) -> float | None:
    if not trades or start_equity <= 0:
        return None
    traded_notional = 0.0
    for trade in trades:
        traded_notional += abs(trade.entry_price * trade.shares)
        if trade.exit_price is not None:
            traded_notional += abs(trade.exit_price * trade.shares)
    return traded_notional / start_equity


def _utc_timestamp(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")
