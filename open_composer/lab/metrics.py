"""Account metrics and explicitly selected existing DSR definitions."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Literal

import numpy as np
import pandas as pd

from open_composer.lab.models import checked_series
from open_composer.research.campaign_statistics import deflated_sharpe_probability
from open_composer.research.scorecard_v2 import annual_sharpe, dsr


@dataclass(frozen=True)
class DSRConfig:
    # No implicit conversion between the two established estimators.
    method: Literal["scorecard_v2", "campaign_statistics", "none"] = "none"
    benchmark: pd.Series | None = None
    benchmark_note: str = "Not supplied"
    var_sr_annual: float | None = None
    n_eff: float | None = None
    hac_lag: int | None = None
    assumptions: str = ""


def session_returns(returns: pd.Series, *, timezone: str) -> pd.Series:
    """Compound bar returns per declared local session date; never add nontrading days."""
    series = checked_series(returns)
    if series.index.tz is None:
        raise ValueError("Bar timestamps must have a timezone before session aggregation")
    dates = series.index.tz_convert(timezone).normalize()
    return (1 + series).groupby(dates, sort=True).prod() - 1


def return_metrics(returns: pd.Series, initial_equity: float) -> dict:
    series = checked_series(returns)
    equity = initial_equity * (1 + series).cumprod()
    peak = equity.cummax().clip(lower=initial_equity)
    sharpe = annual_sharpe(series)
    return {
        "sessions": len(series),
        "net_profit_usd": float(equity.iloc[-1] - initial_equity),
        "total_return": float(equity.iloc[-1] / initial_equity - 1),
        "sharpe_annual_252": float(sharpe) if math.isfinite(sharpe) else None,
        "max_drawdown": float((equity / peak - 1).min()),
        "frequency": "observed sessions; annualization assumes 252 sessions",
    }


def dsr_summary(returns: pd.Series | None, *, n_trials: int, config: DSRConfig) -> dict:
    """Null is explicit; missing history/benchmark is never guessed as zero."""
    parameters = {
        item.name: getattr(config, item.name) for item in fields(config) if item.name != "benchmark"
    }
    result = {
        "method": config.method,
        "dsr": None,
        "n_trials": n_trials,
        "parameters": parameters,
        "reason": None,
    }
    reason = None
    if config.method == "none":
        reason = "No DSR estimator was declared"
    elif config.method not in ("scorecard_v2", "campaign_statistics"):
        raise ValueError("Unknown DSR method")
    elif returns is None:
        reason = "Native engine did not expose a session return ledger"
    elif config.benchmark is None:
        reason = "An aligned daily benchmark and its interpretation are required"
    elif not config.assumptions.strip():
        reason = "Trial-count/dispersion and serial-dependence assumptions are required"
    elif n_trials < 1:
        reason = "No selectable trial exposure was recorded"
    if reason:
        result["reason"] = reason
        return result
    assert returns is not None and config.benchmark is not None
    series, benchmark = checked_series(returns), checked_series(config.benchmark)
    if not series.index.equals(benchmark.index):
        result["reason"] = "Benchmark calendar differs; no silent reindexing or zero fill"
        return result
    excess = (series - benchmark).to_numpy()
    result["sessions"] = len(excess)
    result["frequency"] = "daily/session, 252 annualization"
    try:
        if len(excess) < 4 or float(np.std(excess, ddof=1)) <= 0:
            raise ValueError("DSR needs at least four variable excess-return observations")
        if config.method == "scorecard_v2":
            variance, effective = config.var_sr_annual, config.n_eff
            if variance is None or effective is None:
                raise ValueError("scorecard_v2 requires declared var_sr_annual and n_eff")
            if not math.isfinite(variance) or variance < 0:
                raise ValueError("Sharpe dispersion variance must be finite and nonnegative")
            if not math.isfinite(effective) or not 1 <= effective <= n_trials:
                raise ValueError("n_eff must be between one and cumulative n_trials")
            result["statistics"] = dsr(excess, var_sr_annual=variance, n_eff=effective)
            value = result["statistics"]["dsr"]
        else:
            if config.hac_lag is None:
                raise ValueError("campaign_statistics requires its frozen HAC lag")
            value = deflated_sharpe_probability(
                excess, trial_count=n_trials, hac_lag=config.hac_lag
            )
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("DSR estimator returned a nonfinite or invalid probability")
        result["dsr"] = float(value)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        result["reason"] = str(exc)
    return result


def longest_underwater_sessions(equity, initial_equity: float, *, tolerance: float = 1e-8) -> int:
    """Longest observed streak below the running peak including initial capital.

    This counts ledger observations, not calendar days. Recovery within the native
    absolute dollar tolerance ends the streak; an unrecovered tail is included.
    """
    values = np.asarray(equity, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("Equity must be a finite one-dimensional sequence")
    if not math.isfinite(initial_equity) or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Initial equity and nonnegative tolerance must be finite")
    peak, streak, longest = initial_equity, 0, 0
    for value in values:
        peak = max(peak, value)
        streak = streak + 1 if value < peak - tolerance else 0
        longest = max(longest, streak)
    return longest
