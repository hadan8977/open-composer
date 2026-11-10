"""Funding kernel for native fractional economic-unit accounts.

Corporate entitlements, availability, mark clocks and return realization stay
with the source-native adapter. This kernel never marks or spends a right.
"""

from __future__ import annotations

import numpy as np

from open_composer.lab.accounting import turnover_cost


def funded_target(previous, desired, nav, cost_bps, *, receivable=0.0):
    """Solve the accepted after-fee target root, reserving fixed receivables.

    Preserve the native iteration order and tolerances. A receivable restricts
    allocation only on a rebalance; callers pass zero on ordinary drift rows.
    """
    previous, desired = np.asarray(previous, float), np.asarray(desired, float)
    if previous.shape != desired.shape or not np.isfinite([previous, desired]).all():
        raise ValueError("Invalid aligned economic-unit weights")
    if not 0 <= cost_bps < 1000 or nav <= 0 or not 0 <= receivable <= nav + 1e-7:
        raise ValueError("Invalid funding, costs or fixed receivable")
    q, funding = desired.copy(), 1.0
    for _ in range(100):
        if receivable:
            q = desired * max(0.0, 1 - receivable / (nav * funding))
        updated = 1 - turnover_cost(np.abs(funding * q - previous).sum(), cost_bps)
        if abs(updated - funding) < 1e-13:
            funding = updated
            break
        funding = updated
    turnover = float(np.abs(funding * q - previous).sum())
    cost = float(turnover_cost(turnover, cost_bps))
    if funding <= 0 or abs(funding - (1 - cost)) > 1e-10:
        raise ValueError("Funded target root failed")
    return q, float(funding), turnover
