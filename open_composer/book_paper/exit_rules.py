"""RF1 failure signals and exit rules (hypotheses.md section 7, addendum 1), as a pure function.

Computed on a supplied daily net-return series (the stitched record from 2026-07-01):

* failure signals: rolling 63-session net Sharpe < -1.0, or drawdown from the high > 4.3%, or the
  21-session realized beta |beta| > 0.25;
* any failure signal -> ``halve`` (halve the total exposure, lead reviews);
* drawdown > 8%, or the beta signal persisting for more than 5 sessions -> ``stop`` (flatten, write
  the cause of death);
* otherwise ``continue``.

The beta signal needs the market return series aligned with the strategy returns; without it the
beta signal is reported as not evaluated rather than assumed clear.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

SHARPE_WINDOW = 63
SHARPE_FLOOR = -1.0
DRAWDOWN_HALVE = 0.043
DRAWDOWN_STOP = 0.08
BETA_WINDOW = 21
BETA_LIMIT = 0.25
BETA_STOP_SESSIONS = 5
ANNUALIZATION = 252


@dataclass(frozen=True)
class ExitDecision:
    action: Literal["continue", "halve", "stop"]
    signals: tuple[str, ...]
    stop_reasons: tuple[str, ...]
    metrics: dict[str, float | int | None] = field(default_factory=dict)
    not_evaluated: tuple[str, ...] = ()


def rolling_sharpe(returns: Sequence[float], window: int = SHARPE_WINDOW) -> float | None:
    if len(returns) < window:
        return None
    tail = returns[-window:]
    mean = sum(tail) / window
    var = sum((r - mean) ** 2 for r in tail) / (window - 1)
    if var <= 0:
        return None
    return mean / math.sqrt(var) * math.sqrt(ANNUALIZATION)


def max_drawdown_from_high(returns: Sequence[float]) -> float:
    """Current drawdown from the running high of the compounded equity curve (starts at 1.0)."""
    equity, high = 1.0, 1.0
    for r in returns:
        equity *= 1.0 + r
        high = max(high, equity)
    return 1.0 - equity / high


def worst_drawdown(returns: Sequence[float]) -> float:
    equity, high, worst = 1.0, 1.0, 0.0
    for r in returns:
        equity *= 1.0 + r
        high = max(high, equity)
        worst = max(worst, 1.0 - equity / high)
    return worst


def _beta(strategy: Sequence[float], market: Sequence[float]) -> float | None:
    n = len(strategy)
    ms, mm = sum(strategy) / n, sum(market) / n
    var = sum((m - mm) ** 2 for m in market)
    if var <= 0:
        return None
    return sum((s - ms) * (m - mm) for s, m in zip(strategy, market, strict=True)) / var


def evaluate_exit_rules(
    net_returns: Sequence[float], market_returns: Sequence[float] | None = None
) -> ExitDecision:
    """Return continue, halve or stop for the supplied daily net-return series."""
    if market_returns is not None and len(market_returns) != len(net_returns):
        raise ValueError("market_returns must align with net_returns")
    signals: list[str] = []
    stops: list[str] = []
    not_evaluated: list[str] = []
    metrics: dict[str, float | int | None] = {"n_sessions": len(net_returns)}

    sharpe = rolling_sharpe(net_returns)
    metrics["rolling_63_net_sharpe"] = sharpe
    if sharpe is None:
        not_evaluated.append("rolling_63_net_sharpe")
    elif sharpe < SHARPE_FLOOR:
        signals.append("rolling_63_net_sharpe_below_-1.0")

    drawdown = max_drawdown_from_high(net_returns)
    metrics["drawdown_from_high"] = drawdown
    if drawdown > DRAWDOWN_HALVE:
        signals.append("drawdown_above_4.3pct")
    if drawdown > DRAWDOWN_STOP:
        stops.append("drawdown_above_8pct")

    if market_returns is None or len(net_returns) < BETA_WINDOW:
        not_evaluated.append("realized_beta_21")
        metrics["realized_beta_21"] = None
    else:
        betas = [
            _beta(net_returns[i - BETA_WINDOW : i], market_returns[i - BETA_WINDOW : i])
            for i in range(BETA_WINDOW, len(net_returns) + 1)
        ]
        latest = betas[-1]
        metrics["realized_beta_21"] = latest
        run = 0
        for b in reversed(betas):
            if b is not None and abs(b) > BETA_LIMIT:
                run += 1
            else:
                break
        metrics["beta_breach_run_sessions"] = run
        if run > 0:
            signals.append("realized_beta_21_above_0.25")
        if run > BETA_STOP_SESSIONS:
            stops.append("beta_breach_more_than_5_sessions")

    action: Literal["continue", "halve", "stop"] = "continue"
    if stops:
        action = "stop"
    elif signals:
        action = "halve"
    return ExitDecision(action, tuple(signals), tuple(stops), metrics, tuple(not_evaluated))
