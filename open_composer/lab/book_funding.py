"""Explicit opt-in long/cash purchase funding for the native daily book.

Sales are fixed; purchases share one coefficient. The cost callable must be
pure, nonnegative and monotone in purchase size. No probe is an execution.
"""
import math
import numpy as np


def fund_long_only_trades(trades, state, cost_fn):
    request = trades.dollar_trade.to_numpy(float)
    current = state.holdings.reindex(trades.symbol, fill_value=0).to_numpy(float)
    if (current < -1e-8).any() or (current + request < -1e-8).any() or state.cash < -1e-8:
        raise ValueError("Funding requires a solvent long/cash account")
    sales, buys = np.minimum(request, 0), np.maximum(request, 0)
    prepared = cost_fn.prepare(trades, state) if hasattr(cost_fn, "prepare") else None

    def cash_after(scale):
        q = sales + scale * buys
        if prepared is not None:
            parts = prepared(q)
        else:
            candidate = trades.copy()
            candidate["dollar_trade"] = q
            parts = cost_fn(candidate, state)
        values = list(parts.values()) if isinstance(parts, dict) else [parts]
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("Invalid funding costs")
        return state.cash - float(q.sum()) - sum(values)

    lo, hi = 0., 1.
    if cash_after(lo) < 0:
        raise ValueError("Sales and their fees cannot be funded")
    if cash_after(hi) >= 0:
        lo = 1.
    else:
        for _ in range(64):
            mid = (lo + hi) / 2
            if cash_after(mid) >= 0:
                lo = mid
            else:
                hi = mid
    out = trades.copy()
    out["requested_dollar_trade"] = request
    out["dollar_trade"] = sales + lo * buys
    out["funding_lambda"] = lo
    out["cash_after_execution"] = cash_after(lo)
    return out
