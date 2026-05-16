from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import fmean, stdev

from open_composer.timeframes import bars_per_year


@dataclass(frozen=True)
class PerformanceMetrics:
    annualized_return_pct: float | None
    sharpe_ratio: float | None
    annualized_volatility_pct: float | None = None
    max_drawdown_pct: float = 0.0
    downside_volatility_pct: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    win_rate_pct: float | None = None
    profit_factor: float | None = None
    average_trade_return_pct: float | None = None
    exposure_pct: float | None = None
    turnover_ratio: float | None = None


def build_performance_metrics(
    equity_curve: list[float],
    timeframe: str,
    *,
    trade_pnls: list[float] | None = None,
    trade_return_pcts: list[float] | None = None,
    exposure_pct: float | None = None,
    turnover_ratio: float | None = None,
) -> PerformanceMetrics:
    returns = _period_returns(equity_curve)
    annualized_return_pct = _annualized_return_pct(equity_curve, timeframe)
    sharpe_ratio = _sharpe_ratio(returns, timeframe)
    max_drawdown_pct = _max_drawdown_pct(equity_curve)
    return PerformanceMetrics(
        annualized_return_pct=annualized_return_pct,
        sharpe_ratio=sharpe_ratio,
        annualized_volatility_pct=_annualized_volatility_pct(returns, timeframe),
        max_drawdown_pct=max_drawdown_pct,
        downside_volatility_pct=_downside_volatility_pct(returns, timeframe),
        sortino_ratio=_sortino_ratio(returns, timeframe),
        calmar_ratio=_calmar_ratio(annualized_return_pct, max_drawdown_pct),
        win_rate_pct=_win_rate_pct(trade_pnls or []),
        profit_factor=_profit_factor(trade_pnls or []),
        average_trade_return_pct=_average_trade_return_pct(trade_return_pcts or []),
        exposure_pct=exposure_pct,
        turnover_ratio=turnover_ratio,
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


def _annualized_volatility_pct(returns: list[float], timeframe: str) -> float | None:
    if len(returns) < 2:
        return None
    annual_bars = bars_per_year(timeframe)
    if annual_bars <= 0:
        return None
    return stdev(returns) * sqrt(annual_bars) * 100


def _downside_volatility_pct(returns: list[float], timeframe: str) -> float | None:
    downside = [value for value in returns if value < 0]
    if len(downside) < 2:
        return None
    annual_bars = bars_per_year(timeframe)
    if annual_bars <= 0:
        return None
    return stdev(downside) * sqrt(annual_bars) * 100


def _sortino_ratio(returns: list[float], timeframe: str) -> float | None:
    downside = [value for value in returns if value < 0]
    if len(returns) < 2 or len(downside) < 2:
        return None
    volatility = stdev(downside)
    if volatility == 0:
        return None
    annual_bars = bars_per_year(timeframe)
    if annual_bars <= 0:
        return None
    return (fmean(returns) / volatility) * sqrt(annual_bars)


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    peak: float | None = None
    max_drawdown = 0.0
    for value in equity_curve:
        if value <= 0:
            continue
        peak = value if peak is None else max(peak, value)
        if peak:
            max_drawdown = min(max_drawdown, (value / peak - 1) * 100)
    return max_drawdown


def _calmar_ratio(
    annualized_return_pct: float | None,
    max_drawdown_pct: float,
) -> float | None:
    if annualized_return_pct is None or max_drawdown_pct >= 0:
        return None
    return annualized_return_pct / abs(max_drawdown_pct)


def _win_rate_pct(trade_pnls: list[float]) -> float | None:
    if not trade_pnls:
        return None
    wins = sum(1 for pnl in trade_pnls if pnl > 0)
    return wins / len(trade_pnls) * 100


def _profit_factor(trade_pnls: list[float]) -> float | None:
    gross_profit = sum(pnl for pnl in trade_pnls if pnl > 0)
    gross_loss = abs(sum(pnl for pnl in trade_pnls if pnl < 0))
    if gross_profit <= 0 or gross_loss <= 0:
        return None
    return gross_profit / gross_loss


def _average_trade_return_pct(trade_return_pcts: list[float]) -> float | None:
    if not trade_return_pcts:
        return None
    return fmean(trade_return_pcts)


def _period_returns(equity_curve: list[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:], strict=False):
        if previous <= 0:
            continue
        returns.append((current / previous) - 1)
    return returns
