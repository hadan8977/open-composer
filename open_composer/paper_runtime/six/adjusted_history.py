"""Append received adjusted bars while retaining the accepted price history.

Dividend revisions must be explained by the received cash action. A cent-rounded
revision can pass only the explicit two-observation rounding bound; other
nonuniform revisions remain unavailable. This module never fetches or publishes.
"""

import math

import pandas as pd


def cash_actions(pages):
    actions = {}
    for page in pages:
        for row in page["corporate_actions"].get("cash_dividends", []):
            identity = row["id"]
            if identity in actions and actions[identity] != row:
                raise ValueError("Conflicting dividend receipt")
            actions[identity] = row
    return list(actions.values())


def append_adjusted_history(
    prior_open, prior_close, old_bars, new_bars, scales, actions,
    *, prior_reference, reference,
):
    """Return canonical open/close, raw-to-canonical divisors, and source QA.

    Prior canonical cells are immutable. Divisors connect new observations to
    their units; they are carried explicitly, never re-estimated from a rounded
    old anchor after a dividend. The rounding bound is half a cent per observed
    price, applied only to cent-rounded changed historical observations.
    """
    if not prior_open.index.equals(prior_close.index) or not prior_open.columns.equals(prior_close.columns):
        raise ValueError("Unaligned accepted history")
    if str(prior_close.index[-1].date()) != prior_reference or not prior_reference < reference:
        raise ValueError("Wrong accepted history endpoint")
    opening, close = prior_open.copy(), prior_close.copy()
    received_scales, qa = {}, {}
    for symbol in close.columns:
        keys = sorted(k for k in old_bars if k[0] == symbol and k[1] <= prior_reference)
        if not keys or any(k not in new_bars for k in keys):
            raise ValueError("Missing previously received source cells")
        anchor = keys[0]
        factor = float(new_bars[anchor]["c"]) / float(old_bars[anchor]["c"])
        errors = [
            abs(float(new_bars[k][field]) / factor / float(old_bars[k][field]) - 1)
            for k in keys for field in ("o", "c")
        ]
        method, action_ids, residual = "uniform_source_basis", [], 0.0
        if max(errors) > 1e-7:
            relevant = [a for a in actions if a["symbol"] == symbol and prior_reference < a["ex_date"] <= reference]
            # A daily append has one new reference session. A longer unreceived
            # action chain requires its own source closure, not a guessed factor.
            if not relevant or any(a["ex_date"] != reference for a in relevant):
                raise ValueError(f"Unexplained adjusted-history revision: {symbol}")
            previous_price = float(old_bars[symbol, prior_reference]["c"])
            dividend = sum(float(a["rate"]) for a in relevant)
            if not math.isfinite(dividend) or not 0 < dividend < previous_price:
                raise ValueError("Invalid received dividend")
            factor = 1 - dividend / previous_price
            bound = 0.005 * (1 + factor) + 1e-12
            for key in keys:
                for field in ("o", "c"):
                    before, current = float(old_bars[key][field]), float(new_bars[key][field])
                    if abs(current * 100 - round(current * 100)) > 1e-7:
                        raise ValueError("Dividend revision is not cent rounded")
                    gap = abs(current - before * factor)
                    if gap > bound:
                        raise ValueError(f"Dividend does not explain source revision: {symbol}")
                    residual = max(residual, gap)
            method, action_ids = "received_dividend_and_cent_rounding", [a["id"] for a in relevant]
        scale = float(scales[symbol]) * factor
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("Invalid canonical price divisor")
        received_scales[symbol] = scale
        for (name, day), row in new_bars.items():
            if name == symbol and prior_reference < day <= reference:
                opening.loc[pd.Timestamp(day), symbol] = float(row["o"]) / scale
                close.loc[pd.Timestamp(day), symbol] = float(row["c"]) / scale
        qa[symbol] = dict(
            method=method, prior_divisor=float(scales[symbol]), divisor=scale,
            source_basis_factor=factor, compared_OC_cells=len(keys) * 2,
            raw_relative_error_before_receipt=max(errors), action_ids=action_ids,
            max_rounding_residual_dollars=residual,
            prior_canonical_cells_replaced=0,
        )
    return opening.sort_index(), close.sort_index(), received_scales, qa
