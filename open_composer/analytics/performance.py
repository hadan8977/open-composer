from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import fmean, stdev

from open_composer.timeframes import bars_per_year


@dataclass(frozen=True)
class PerformanceMetrics:
    annualized_return_pct: float | None
    sharpe_ratio: float | None


def build_performance_metrics(
    equity_curve: list[float],
    timeframe: str,
) -> PerformanceMetrics:
    returns = _period_returns(equity_curve)
    annualized_return_pct = _annualized_return_pct(equity_curve, timeframe)
    sharpe_ratio = _sharpe_ratio(returns, timeframe)
    return PerformanceMetrics(
        annualized_return_pct=annualized_return_pct,
        sharpe_ratio=sharpe_ratio,
    )


def _annualized_return_pct(equity_curve: list[float], timeframe: str) -> float | None:
    if len(equity_curve) < 2:
        return None
    start = equity_curve[0]
    end = equity_curve[-1]
    if start <= 0 or end <= 0:
        return None
    periods = len(equity_curve) - 1
    annual_bars = bars_per_year(timeframe)
    if periods <= 0 or annual_bars <= 0:
        return None
    return ((end / start) ** (annual_bars / periods) - 1) * 100


def _sharpe_ratio(returns: list[float], timeframe: str) -> float | None:
    if len(returns) < 2:
        return None
    volatility = stdev(returns)
    if volatility == 0:
        return None
    annual_bars = bars_per_year(timeframe)
    if annual_bars <= 0:
        return None
    return (fmean(returns) / volatility) * sqrt(annual_bars)


def _period_returns(equity_curve: list[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:], strict=False):
        if previous <= 0:
            continue
        returns.append((current / previous) - 1)
    return returns
