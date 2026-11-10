"""Separate marked broker returns from incremental costs and simulation stress.

This module never fetches activities or changes cash. Callers must supply verified
flow/fee inclusion before a reconciled incremental-net number can be emitted.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def profit_ledgers(
    equity: float,
    last_equity: float,
    shadow: Mapping[str, Any],
    *,
    external_net_flow: float | None = None,
    fees_already_in_equity: float | None = None,
    borrow_already_in_equity: float | None = None,
    impact_already_in_equity: float | None = None,
    holdings_valuation_complete: bool = False,
) -> dict[str, Any]:
    """Retain the old stress arithmetic without presenting it as incremental net.

    Each modeled component uses a top-up only after its actual inclusion is
    reconciled. Unknown classification is not zero, including generic FEE rows.
    Crossing spread is already represented by actual fill prices; no second
    full spread charge is added. Unknown transfer/fee inputs remain unknown.
    """
    numbers = [equity, last_equity, *[shadow[k] for k in ("impact", "fees", "borrow", "total")]]
    if not all(math.isfinite(float(v)) for v in numbers):
        raise ValueError("non-finite accounting input")
    if any(float(shadow[k]) < 0 for k in ("impact", "fees", "borrow", "total")):
        raise ValueError("modeled expense must be nonnegative")
    included = {
        "fees": fees_already_in_equity,
        "borrow": borrow_already_in_equity,
        "impact": impact_already_in_equity,
    }
    for value in (external_net_flow, *included.values()):
        if value is not None and not math.isfinite(float(value)):
            raise ValueError("non-finite verified flow/fee")
    if any(value is not None and value < 0 for value in included.values()):
        raise ValueError("included cost must be a nonnegative expense")
    delta = equity - last_equity
    broker_profit = None if external_net_flow is None else delta - external_net_flow
    fee_topup = (
        None
        if fees_already_in_equity is None
        else max(float(shadow["fees"]) - fees_already_in_equity, 0.0)
    )
    topups = {
        key: None if value is None else max(float(shadow[key]) - value, 0.0)
        for key, value in included.items()
    }
    incremental = (
        None
        if any(v is None for v in topups.values())
        else sum(v for v in topups.values() if v is not None)
    )
    complete = broker_profit is not None and incremental is not None and holdings_valuation_complete
    return {
        "schema_version": 1,
        "broker_paper": {
            "equity_delta": delta,
            "external_net_flow": external_net_flow,
            "flow_adjusted_pnl": broker_profit,
            "fill_basis": "actual broker fills and broker account marks",
        },
        "broker_plus_incremental_model": {
            "complete": complete,
            "net_pnl": broker_profit - incremental if complete else None,
            "incremental_cost": incremental,
            "additional_full_spread": 0.0,
            "impact_scenario": float(shadow["impact"]),
            "borrow_scenario": float(shadow["borrow"]),
            "fees_already_in_equity": fees_already_in_equity,
            "borrow_already_in_equity": borrow_already_in_equity,
            "impact_already_in_equity": impact_already_in_equity,
            "fee_topup_to_model": fee_topup,
            "borrow_topup_to_model": topups["borrow"],
            "impact_topup_to_model": topups["impact"],
            "holdings_valuation_complete": holdings_valuation_complete,
            "scope": "Additional impact/borrow/fee-model scenario; not measured all-in cost",
        },
        "historical_simulation": None,
        "historical_simulation_note": (
            "Separate frozen research fill/cost ledger; not reconstructed from broker equity"
        ),
        "legacy_full_shadow": {
            "net_pnl": delta - float(shadow["total"]),
            "status": "retained full-shadow stress, not incremental-only net",
        },
    }
