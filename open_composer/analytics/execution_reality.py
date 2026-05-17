from __future__ import annotations

from statistics import fmean

import pandas as pd

from open_composer.models.backtest import ExecutionRealityMetrics, Trade

BAR_PARTICIPATION_WARNING_PCT = 5.0
BAR_PARTICIPATION_BLOCK_PCT = 10.0
ADV_PARTICIPATION_WARNING_PCT = 10.0
MIN_AVERAGE_DOLLAR_VOLUME = 1_000_000.0
MIN_BAR_DOLLAR_VOLUME = 100_000.0
CAPACITY_ADV_PARTICIPATION_PCT = 5.0
CAPACITY_CURVE_PCTS = (1.0, 2.5, 5.0, 10.0)


def evaluate_execution_reality(
    frame: pd.DataFrame,
    trades: list[Trade],
) -> ExecutionRealityMetrics:
    """Build conservative OHLCV-only liquidity diagnostics for a backtest."""
    warnings: list[str] = []
    dollar_volume = _dollar_volume(frame)
    if dollar_volume is None or dollar_volume.empty:
        return ExecutionRealityMetrics(
            status="warning",
            warnings=["OHLCV frame lacks usable close/volume data for liquidity checks."],
        )

    average_dollar_volume = float(dollar_volume.mean())
    median_dollar_volume = float(dollar_volume.median())
    min_dollar_volume = float(dollar_volume.min())
    timestamp_to_dv = _timestamp_to_dollar_volume(frame, dollar_volume)
    trade_notional = _trade_notional(trades)
    max_trade_notional = max(trade_notional, default=None)
    participations = [
        notional / bar_dv * 100
        for timestamp, notional in _trade_events(trades)
        if (bar_dv := timestamp_to_dv.get(timestamp)) and bar_dv > 0
    ]
    max_bar_participation_pct = max(participations, default=None)
    average_bar_participation_pct = fmean(participations) if participations else None
    max_adv_participation_pct = (
        max_trade_notional / average_dollar_volume * 100
        if max_trade_notional is not None and average_dollar_volume > 0
        else None
    )
    estimated_capacity_notional = average_dollar_volume * (CAPACITY_ADV_PARTICIPATION_PCT / 100)
    capacity_curve = {
        f"{pct:g}%_adv": average_dollar_volume * (pct / 100) for pct in CAPACITY_CURVE_PCTS
    }
    recommended_max_participation_pct = min(
        BAR_PARTICIPATION_WARNING_PCT,
        ADV_PARTICIPATION_WARNING_PCT,
    )
    slippage_stress_bps = _slippage_stress_bps(max_bar_participation_pct)

    if average_dollar_volume < MIN_AVERAGE_DOLLAR_VOLUME:
        warnings.append(
            "average dollar volume is low; backtest fills may overstate executable capacity."
        )
    if min_dollar_volume < MIN_BAR_DOLLAR_VOLUME:
        warnings.append(
            "at least one bar has very low dollar volume; review bar-level fill assumptions."
        )
    if max_bar_participation_pct is not None:
        if max_bar_participation_pct > BAR_PARTICIPATION_BLOCK_PCT:
            warnings.append(
                "max bar participation exceeds the conservative block threshold; partial fills "
                "or delayed execution should be modeled before promotion."
            )
        elif max_bar_participation_pct > BAR_PARTICIPATION_WARNING_PCT:
            warnings.append(
                "max bar participation is elevated; run capacity and slippage sensitivity."
            )
    if (
        max_adv_participation_pct is not None
        and max_adv_participation_pct > ADV_PARTICIPATION_WARNING_PCT
    ):
        warnings.append("trade size is large versus average dollar volume.")

    status = "ok"
    if any("block threshold" in warning for warning in warnings):
        status = "blocked"
    elif warnings:
        status = "warning"

    return ExecutionRealityMetrics(
        status=status,
        average_dollar_volume=average_dollar_volume,
        median_dollar_volume=median_dollar_volume,
        min_dollar_volume=min_dollar_volume,
        max_trade_notional=max_trade_notional,
        max_bar_participation_pct=max_bar_participation_pct,
        average_bar_participation_pct=average_bar_participation_pct,
        max_adv_participation_pct=max_adv_participation_pct,
        estimated_capacity_notional=estimated_capacity_notional,
        capacity_curve=capacity_curve,
        recommended_max_participation_pct=recommended_max_participation_pct,
        slippage_stress_bps=slippage_stress_bps,
        warnings=warnings,
    )


def _dollar_volume(frame: pd.DataFrame) -> pd.Series | None:
    if "close" not in frame.columns or "volume" not in frame.columns:
        return None
    close = pd.to_numeric(frame["close"], errors="coerce")
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    dollar_volume = (close * volume).dropna()
    return dollar_volume[dollar_volume > 0]


def _timestamp_to_dollar_volume(
    frame: pd.DataFrame,
    dollar_volume: pd.Series,
) -> dict[pd.Timestamp, float]:
    if "timestamp" not in frame.columns:
        return {}
    timestamps = pd.to_datetime(frame.loc[dollar_volume.index, "timestamp"], utc=True)
    return dict(zip(timestamps, dollar_volume.astype(float), strict=False))


def _trade_events(trades: list[Trade]) -> list[tuple[pd.Timestamp, float]]:
    events: list[tuple[pd.Timestamp, float]] = []
    for trade in trades:
        entry_notional = trade.entry_price * trade.shares
        events.append((_utc_timestamp(trade.entry_time), entry_notional))
        if trade.exit_time is not None and trade.exit_price is not None:
            exit_notional = trade.exit_price * trade.shares
            events.append((_utc_timestamp(trade.exit_time), exit_notional))
    return events


def _trade_notional(trades: list[Trade]) -> list[float]:
    notionals: list[float] = []
    for trade in trades:
        notionals.append(trade.entry_price * trade.shares)
        if trade.exit_price is not None:
            notionals.append(trade.exit_price * trade.shares)
    return notionals


def _utc_timestamp(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _slippage_stress_bps(max_bar_participation_pct: float | None) -> dict[str, float]:
    participation = max(max_bar_participation_pct or 0.0, 0.0)
    base = 2.5 + participation * 0.5
    return {
        "low": round(base, 4),
        "medium": round(base * 2, 4),
        "high": round(base * 4, 4),
    }
