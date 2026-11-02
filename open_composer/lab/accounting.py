"""Shared return-ledger arithmetic for the accepted ETF screening convention.

Weights earn yesterday-close to today's open before the rebalance, then today's
open to close. This linear-leg convention is deliberately retained; it is not
the share/cash, margin or intrabar-fill model used by the other native engines.
Signal clocks, eligibility and missing-price handling belong to the caller.
"""

from __future__ import annotations

from collections.abc import Callable, Collection

import numpy as np
import pandas as pd


def turnover_cost(turnover, cost_bps: float):
    """Per-side cost as a fraction of account capital; preserve native arithmetic."""
    return turnover * cost_bps / 10_000.0


def scaled_weights(weights: np.ndarray, scale: np.ndarray, cash_index: int) -> np.ndarray:
    risk = weights.copy()
    risk[:, cash_index] = 0.0
    effective = risk * scale[:, None]
    effective[:, cash_index] = weights[:, cash_index] + (1.0 - scale) * risk.sum(axis=1)
    return effective


def open_close_step(previous, current, overnight, intraday, cost_bps: float):
    gross = float(previous @ overnight + current @ intraday)
    turnover = float(np.abs(current - previous).sum())
    return gross - turnover_cost(turnover, cost_bps), turnover


def open_close_ledger(
    weights: np.ndarray,
    overnight: np.ndarray,
    intraday: np.ndarray,
    index: pd.Index,
    cost_bps: float,
    *,
    reduction: str = "sum",
) -> pd.DataFrame:
    """Compute one account path, retaining the source's sum/dot rounding order."""
    if weights.shape != overnight.shape or weights.shape != intraday.shape:
        raise ValueError("Weights and return legs must have matching shapes")
    if len(index) != len(weights):
        raise ValueError("Account calendar must match the weight rows")
    previous = np.vstack([np.zeros((1, weights.shape[1])), weights[:-1]])
    if reduction == "sum":
        gross = (previous * overnight).sum(axis=1) + (weights * intraday).sum(axis=1)
    elif reduction == "dot":
        gross = np.array(
            [
                float(p @ lo + w @ lc)
                for p, w, lo, lc in zip(previous, weights, overnight, intraday, strict=True)
            ]
        )
    else:
        raise ValueError("Unknown native reduction order")
    turnover = np.abs(weights - previous).sum(axis=1)
    cost = turnover_cost(turnover, cost_bps)
    return pd.DataFrame(
        {"gross": gross, "turnover": turnover, "cost": cost, "net": gross - cost},
        index=index,
    )


def simulate_effective(
    weights, columns, leg_open, leg_close, cost_bps, *, reduction="sum", index=None
):
    ledger = open_close_ledger(
        weights,
        leg_open[columns].to_numpy(dtype=float),
        leg_close[columns].to_numpy(dtype=float),
        leg_open.index if index is None else index,
        cost_bps,
        reduction=reduction,
    )
    return ledger["net"].rename(None), ledger["turnover"].rename(None)


def drift_ledger(
    returns: np.ndarray,
    index: pd.Index,
    rebalance_rows: Collection[int],
    target_at_close: Callable[[int], np.ndarray],
    cost_bps: float,
) -> pd.DataFrame:
    """Combine already-costed sleeves, charging only combination turnover.

    The target callback receives the preceding close position. Initial weights
    incur no combination entry fee, matching the accepted source convention.
    """
    gross = np.zeros(len(index))
    turnover = np.zeros(len(index))
    weights = target_at_close(-1)
    for i in range(len(index)):
        if i in rebalance_rows:
            target = target_at_close(i - 1)
            turnover[i] = float(np.abs(target - weights).sum())
            weights = target
        gross[i] = float(np.dot(weights, returns[i]))
        grown = weights * (1.0 + returns[i])
        total = float(grown.sum())
        weights = grown / total if total != 0.0 else weights
    cost = turnover_cost(turnover, cost_bps)
    return pd.DataFrame(
        {"gross": gross, "turnover": turnover, "cost": cost, "net": gross - cost}, index=index
    )
