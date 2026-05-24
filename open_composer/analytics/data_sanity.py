from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from open_composer.models.backtest import BacktestDataSanity, BacktestRun, Trade
from open_composer.models.strategy_spec import StrategySpec

MIN_BARS_BY_TIMEFRAME = {
    "1m": 500,
    "5m": 250,
    "15m": 200,
    "30m": 160,
    "1h": 120,
    "4h": 80,
    "daily": 100,
    "weekly": 52,
}
MIN_SIGNALS = 5
MIN_TRADES = 5
MAX_ABS_ANNUALIZED_RETURN_PCT = 200.0
MAX_ABS_SHARPE = 5.0


def evaluate_backtest_data_sanity(
    *,
    spec: StrategySpec,
    frame: pd.DataFrame,
    run: BacktestRun,
    trades: list[Trade] | None = None,
) -> BacktestDataSanity:
    data_source = str(frame.attrs.get("data_source_provider") or spec.data.source)
    data_source_mode = _data_source_mode(spec, frame)
    data_feed = _optional_str(frame.attrs.get("data_source_feed") or spec.data.feed)
    data_path = _optional_str(frame.attrs.get("data_source_path") or spec.data.path)
    first_timestamp, last_timestamp, data_span_days = _data_span(frame)
    average_holding_days = _average_holding_days(trades or [])
    warnings: list[str] = []

    mode_text = data_source_mode or ""
    if spec.data.source == "sample" or "sample" in mode_text:
        warnings.append(
            "sample data is workflow smoke-test evidence only; do not treat return metrics as "
            "market evidence."
        )
    if "fallback" in mode_text:
        warnings.append(
            "fallback data was used because requested provider data was unavailable; validate on "
            "the intended data source before promotion."
        )
    if "fixture" in mode_text:
        warnings.append(
            "fixture replay data is deterministic test evidence only, not production market data."
        )
    if "resampled" in mode_text:
        warnings.append(
            "provider bars were resampled from a local cache; validate the native provider "
            "timeframe before paper automation."
        )

    min_bars = MIN_BARS_BY_TIMEFRAME.get(spec.timeframe, 200)
    if run.bars < min_bars:
        warnings.append(
            f"short sample: {run.bars} bars is below the {min_bars}-bar minimum sanity "
            f"threshold for {spec.timeframe} research."
        )
    if run.signals < MIN_SIGNALS:
        warnings.append(
            f"low signal count: {run.signals} signals is below the {MIN_SIGNALS}-signal "
            "minimum sanity threshold."
        )
    if run.trades < MIN_TRADES:
        warnings.append(
            f"low closed trade count: {run.trades} trades is below the {MIN_TRADES}-trade "
            "minimum sanity threshold."
        )
    if _abs_exceeds(run.annualized_return_pct, MAX_ABS_ANNUALIZED_RETURN_PCT):
        warnings.append(
            "annualized return is unusually large for the available sample; use period return "
            "and out-of-sample checks for comparison."
        )
    if _abs_exceeds(run.sharpe_ratio, MAX_ABS_SHARPE):
        warnings.append(
            "Sharpe ratio is unusually large for the available sample; treat it as unstable "
            "until validated on longer out-of-sample data."
        )
    if run.trades > 0 and math.isclose(run.total_fees, 0.0, abs_tol=1e-9):
        warnings.append(
            "closed trades were generated with zero total fees; rerun with realistic commission "
            "and slippage before using this as research evidence."
        )

    evidence_level = (
        "E0_sample_smoke"
        if _is_smoke_data(spec.data.source, data_source_mode)
        else "E1_single_source_research"
    )
    return BacktestDataSanity(
        status="warning" if warnings else "ok",
        evidence_level=evidence_level,
        bars=run.bars,
        signals=run.signals,
        trades=run.trades,
        data_source=data_source,
        data_source_mode=data_source_mode,
        data_feed=data_feed,
        data_path=data_path,
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp,
        data_span_days=data_span_days,
        average_holding_days=average_holding_days,
        warnings=warnings,
    )


def _data_source_mode(spec: StrategySpec, frame: pd.DataFrame) -> str:
    value = frame.attrs.get("data_source_mode")
    if value:
        return str(value)
    return "sample" if spec.data.source == "sample" else "provider_cache_or_live"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _data_span(frame: pd.DataFrame) -> tuple[datetime | None, datetime | None, float | None]:
    if frame.empty or "timestamp" not in frame.columns:
        return None, None, None
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    first = timestamps.min()
    last = timestamps.max()
    if pd.isna(first) or pd.isna(last):
        return None, None, None
    return first.to_pydatetime(), last.to_pydatetime(), (last - first).total_seconds() / 86_400


def _average_holding_days(trades: list[Trade]) -> float | None:
    durations = [
        (trade.exit_time - trade.entry_time).total_seconds() / 86_400
        for trade in trades
        if trade.exit_time is not None
    ]
    if not durations:
        return None
    return sum(durations) / len(durations)


def _abs_exceeds(value: float | None, threshold: float) -> bool:
    return value is not None and abs(value) > threshold


def _is_smoke_data(data_source: str, data_source_mode: str | None) -> bool:
    mode = data_source_mode or ""
    return data_source == "sample" or "sample" in mode or "fixture" in mode or "fallback" in mode
