"""After the close: reconcile orders -> fills -> positions, TCA, shadow costs, daily P&L.

Pure functions over plain dicts so the arithmetic is testable without a broker.  Paper fills carry
neither market impact nor borrow fees, so the net P&L subtracts shadow costs from cost model v1
(half spread at the close snapshot, square-root impact at the traded size, 0.5 bp fees) plus borrow
at 25 bp a year on the short notional.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.book_paper.plan import OrderLookup, OrderPlan, write_json_atomic
from open_composer.book_paper.targets import BookTarget, book_dir
from open_composer.research.equity_book.costfn import make_cost_fn
from open_composer.research.equity_book.costs import (
    BORROW_BP_PER_YEAR_BASE,
    borrow_cost_dollars_per_day,
)


def normalize_broker_order(order: Any) -> dict[str, Any]:
    status = getattr(order, "status", "")
    return {
        "client_order_id": str(getattr(order, "client_order_id", "") or ""),
        "symbol": str(getattr(order, "symbol", "")),
        "side": str(
            getattr(getattr(order, "side", ""), "value", getattr(order, "side", ""))
        ).lower(),
        "qty": float(getattr(order, "qty", 0) or 0),
        "filled_qty": float(getattr(order, "filled_qty", 0) or 0),
        "filled_avg_price": _optional(getattr(order, "filled_avg_price", None)),
        "status": str(getattr(status, "value", status)).lower(),
    }


def fetch_broker_orders(client: Any, plan: OrderPlan) -> list[dict[str, Any]]:
    """The plan's orders as the broker holds them (read-only), by client_order_id."""
    lookup = OrderLookup(client, plan.execution_date)
    found = []
    from open_composer.book_paper.reversal import reversal_legs

    for order in plan.orders:
        for request in [order, *reversal_legs(order)]:
            broker_order = lookup.find(request["client_order_id"])
            if broker_order is not None:
                found.append(normalize_broker_order(broker_order))
    return found


# --------------------------------------------------------------------------------------
# reconcile
# --------------------------------------------------------------------------------------


def reconcile(
    plan: OrderPlan,
    target: BookTarget,
    broker_orders: list[dict[str, Any]],
    positions: dict[str, float],
    close_prices: dict[str, float],
    submission_receipts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Orders -> fills -> positions against the plan and the target weights."""
    from open_composer.book_paper.reversal import reversal_legs

    by_id = {o["client_order_id"]: o for o in broker_orders}
    attempts: dict[str, dict[str, Any]] = {}
    deferrals = set()
    for receipt in submission_receipts or []:
        attempts.update(receipt.get("attempts", {}))
        for failed in receipt.get("failed", []):
            attempts[failed["client_order_id"]] = failed
        deferrals.update(r["client_order_id"] for r in receipt.get("deferred", []))
    rows: list[dict[str, Any]] = []
    for order in plan.orders:
        legs = reversal_legs(order)
        requests = [order, *legs]
        brokers = [by_id[r["client_order_id"]] for r in requests if r["client_order_id"] in by_id]
        filled = sum(b["filled_qty"] for b in brokers)
        evidence = [
            attempts[r["client_order_id"]] for r in requests if r["client_order_id"] in attempts
        ]
        rejected = any(
            e.get("outcome") == "submission_rejected"
            or (
                e.get("error") == "APIError"
                and '"code":40310000' in str(e.get("message", "")).replace(" ", "")
            )
            for e in evidence
        ) or any(b["status"] == "rejected" for b in brokers)
        submission_state = "acknowledged" if brokers else "missing_acknowledgement"
        if rejected:
            submission_state = "submission_rejected"
        elif evidence and not brokers:
            submission_state = "acknowledgement_unknown"
        elif filled < order["qty"] and any(r["client_order_id"] in deferrals for r in requests):
            submission_state = "deferred"
        if filled >= order["qty"]:
            state = "filled"
        elif filled > 0:
            state = "partial"
        elif brokers or submission_state in ("submission_rejected", "deferred"):
            state = "unfilled"
        else:
            state = "missing"
        priced = [b for b in brokers if b["filled_qty"] > 0]
        avg = (
            sum(b["filled_qty"] * b["filled_avg_price"] for b in priced) / filled
            if filled and all(b["filled_avg_price"] is not None for b in priced)
            else None
        )
        row = {
            "symbol": order["symbol"],
            "side": order["side"],
            "qty": order["qty"],
            "filled_qty": filled,
            "fill_state": state,
            "submission_state": submission_state,
            "broker_status": (
                brokers[0]["status"] if len(brokers) == 1 else "staged" if brokers else None
            ),
            "unfilled_qty": max(order["qty"] - filled, 0.0),
            "filled_avg_price": avg,
            "client_order_id": order["client_order_id"],
        }
        if legs:
            row["leg_evidence"] = [
                {
                    **r,
                    "broker": by_id.get(r["client_order_id"]),
                    "submission": attempts.get(r["client_order_id"]),
                }
                for r in legs
            ]
        if evidence:
            row["submission_evidence"] = evidence
        if filled > order["qty"]:
            row["overfilled_qty"] = filled - order["qty"]
        rows.append(row)

    expected = {s: float(q) for s, q in plan.payload["post_trade_qty"].items()}
    frozen_names = {row["symbol"] for row in plan.payload.get("frozen", [])}  # T-20261002-40
    drift_rows = []
    basis = target.equity_basis
    for symbol in sorted(set(expected) | set(positions)):
        exp, act = expected.get(symbol, 0.0), positions.get(symbol, 0.0)
        if abs(act - exp) > 1e-9:
            price = close_prices.get(symbol) or target.reference_prices.get(symbol)
            drift_rows.append(
                {
                    "symbol": symbol,
                    "expected_qty": exp,
                    "actual_qty": act,
                    "drift_qty": act - exp,
                    "drift_weight": (act - exp) * price / basis if price else None,
                }
                | ({"frozen": True} if symbol in frozen_names else {})
            )
    weight_gap = 0.0
    for symbol in set(target.weights) | set(positions):
        price = close_prices.get(symbol) or target.reference_prices.get(symbol)
        if price:
            weight_gap += abs(
                positions.get(symbol, 0.0) * price / basis - target.weights.get(symbol, 0.0)
            )
    states = [r["fill_state"] for r in rows]
    drift_names = {
        s for s in set(target.weights) | set(positions) if target.weights.get(s) or positions.get(s)
    }
    fallback_names = sorted(
        s for s in drift_names if not close_prices.get(s) and target.reference_prices.get(s)
    )
    return {
        "n_orders": len(rows),
        "n_filled": states.count("filled"),
        "n_partial": states.count("partial"),
        "n_unfilled": states.count("unfilled"),
        "n_missing": states.count("missing"),
        "n_submission_rejected": sum(r["submission_state"] == "submission_rejected" for r in rows),
        "n_acknowledgement_unknown": sum(
            r["submission_state"] == "acknowledgement_unknown" for r in rows
        ),
        "n_deferred": sum(r["submission_state"] == "deferred" for r in rows),
        "orders": rows,
        "unfilled_orders": [r for r in rows if r["fill_state"] in ("unfilled", "missing")],
        "partial_fills": [r for r in rows if r["fill_state"] == "partial"],
        "position_drift_vs_plan": drift_rows,
        "n_position_drift_names": len(drift_rows),
        "realized_vs_target_one_sided_drift": round(weight_gap / 2.0, 8),
        "weight_drift_valuation": {
            "denominator": "target_equity_basis",
            "equity_basis": basis,
            "target_reference_date": target.decision_date.isoformat(),
            "target_reference_fallback": fallback_names,
            "unpriced_names": sorted(
                s
                for s in drift_names
                if not (close_prices.get(s) or target.reference_prices.get(s))
            ),
            "complete_at_official_close": all(
                _usable_mark(close_prices.get(s)) for s in drift_names
            ),
        },
    } | ({"frozen_names": sorted(frozen_names)} if frozen_names else {})


# --------------------------------------------------------------------------------------
# TCA
# --------------------------------------------------------------------------------------


def tca(
    fills: list[dict[str, Any]],
    official_close: dict[str, float],
    snapshot_1545: dict[str, float],
) -> dict[str, Any]:
    """Slippage of fills in bp, positive = worse for the trader, against the official close and the
    15:45 snapshot proxy; notional-weighted means over fills with a reference price."""
    rows: list[dict[str, Any]] = []
    for fill in fills:
        qty, price = float(fill["filled_qty"]), fill.get("filled_avg_price")
        if qty <= 0 or not price:
            continue
        sign = 1.0 if fill["side"] == "buy" else -1.0
        row = {"symbol": fill["symbol"], "side": fill["side"], "notional": qty * price}
        for key, ref in (
            ("vs_official_close_bp", official_close),
            ("vs_snapshot_1545_bp", snapshot_1545),
        ):
            r = ref.get(fill["symbol"])
            row[key] = sign * (price - r) / r * 1e4 if r else None
        rows.append(row)
    out: dict[str, Any] = {
        "n_fills": len(rows),
        "fills": rows,
        "row_unit": "logical_order_aggregate",
    }
    for key in ("vs_official_close_bp", "vs_snapshot_1545_bp"):
        valid = [(r["notional"], r[key]) for r in rows if r[key] is not None]
        total = sum(n for n, _ in valid)
        out[f"mean_{key}"] = sum(n * v for n, v in valid) / total if total else None
        out[f"n_with_reference_{key}"] = len(valid)
    return out


# --------------------------------------------------------------------------------------
# shadow costs
# --------------------------------------------------------------------------------------


def shadow_costs(
    fills: list[dict[str, Any]],
    target: BookTarget,
    close_positions: dict[str, float],
    close_prices: dict[str, float],
    *,
    trade_date: date,
) -> dict[str, Any]:
    """Cost model v1 at the close snapshot for the fills, plus borrow on the closing short book."""
    rows = []
    for fill in fills:
        qty, price = float(fill["filled_qty"]), fill.get("filled_avg_price")
        if qty <= 0 or not price:
            continue
        exposure = target.exposures.get(fill["symbol"])
        sign = 1.0 if fill["side"] == "buy" else -1.0
        rows.append(
            {
                "symbol": fill["symbol"],
                "dollar_trade": sign * qty * price,
                "price": price,
                "trade_date": pd.Timestamp(trade_date),
                "dollar_adv_21": exposure.dollar_adv_21 if exposure else None,
                "vol_21": exposure.vol_21 if exposure else None,
                "prior_close": target.reference_prices.get(fill["symbol"]),
            }
        )
    frame = pd.DataFrame(rows)
    traded = float(frame["dollar_trade"].abs().sum()) if len(frame) else 0.0
    costs = (
        make_cost_fn("close")(frame) if len(frame) else {"spread": 0.0, "impact": 0.0, "fees": 0.0}
    )
    short_notional = sum(
        -q * close_prices[s] for s, q in close_positions.items() if q < 0 and s in close_prices
    )
    borrow = float(borrow_cost_dollars_per_day(np.array([short_notional]), True).sum())
    total = costs["spread"] + costs["impact"] + costs["fees"] + borrow
    return {
        "model": "cost_model_v1 close snapshot",
        "traded_notional": traded,
        "half_spread": costs["spread"],
        "impact": costs["impact"],
        "fees": costs["fees"],
        "borrow": borrow,
        "borrow_bp_per_year": BORROW_BP_PER_YEAR_BASE,
        "short_notional_at_close": short_notional,
        "unpriced_short_positions": {
            s: q
            for s, q in sorted(close_positions.items())
            if q < 0 and not _usable_mark(close_prices.get(s))
        },
        "total": total,
    }


# --------------------------------------------------------------------------------------
# realized exposures and daily record
# --------------------------------------------------------------------------------------


def _usable_mark(value: Any) -> bool:
    """Coverage only: do not replace or impute prices in the existing arithmetic."""
    try:
        price = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(price) and price > 0


def realized_exposures(
    target: BookTarget, positions: dict[str, float], close_prices: dict[str, float], equity: float
) -> dict[str, Any]:
    non_stock = target.non_stock_symbols
    all_weights = {
        s: q * close_prices[s] / equity
        for s, q in positions.items()
        if s in close_prices and equity > 0
    }
    weights = {s: w for s, w in all_weights.items() if s not in non_stock}
    hedge_weight = 0.0
    if target.hedge_symbol is not None:
        hedge_weight = all_weights.get(target.hedge_symbol, 0.0) - (
            target.core_weight if target.hedge_symbol == target.core_symbol else 0.0
        )
    industry: dict[str, float] = defaultdict(float)
    beta = size = 0.0
    for symbol, w in weights.items():
        e = target.exposures.get(symbol)
        if e is None:
            continue
        beta += e.beta * w
        size += e.size * w
        industry[e.industry] += w
    beta += hedge_weight  # SPY hedge, beta 1.0
    missing = sorted(s for s in weights if s not in target.exposures)
    held = {s: q for s, q in positions.items() if q}
    unpriced = {s: q for s, q in sorted(held.items()) if s not in close_prices}
    invalid = sorted(s for s in held if s in close_prices and not _usable_mark(close_prices[s]))
    return {
        "net_weight": sum(weights.values()),
        "gross_weight": sum(abs(w) for w in weights.values()),
        "beta": beta,
        "hedge_weight": hedge_weight,
        "size_weighted": size,
        "industry_net": dict(sorted(industry.items())),
        "names_without_exposure": missing,
        "valuation_coverage": {
            "position_count": len(held),
            "priced_position_count": len(held) - len(unpriced) - len(invalid),
            "unpriced_positions": unpriced,
            "invalid_price_names": invalid,
            "complete": not unpriced and not invalid and math.isfinite(equity) and equity > 0,
            "price_basis": "supplied_official_close",
            "denominator": "broker_account_equity",
            "equity": equity,
            "exposure_target_decision_date": target.decision_date.isoformat(),
            "scope": (
                "existing metrics use priced positions; coverage does not grant pretrade permission"
            ),
        },
    }


def build_daily_record(
    plan: OrderPlan,
    target: BookTarget,
    *,
    broker_orders: list[dict[str, Any]],
    positions: dict[str, float],
    equity: float,
    last_equity: float,
    official_close: dict[str, float],
    snapshot_1545: dict[str, float],
    generated_at_utc: str,
    submission_receipts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rec = reconcile(plan, target, broker_orders, positions, official_close, submission_receipts)
    fills = rec["orders"]
    costs = shadow_costs(fills, target, positions, official_close, trade_date=plan.execution_date)
    gross = equity - last_equity
    from open_composer.book_paper.cost_ledgers import profit_ledgers

    # This legacy caller has no verified activity-flow/fee inclusion inputs.
    # Do not turn a raw equity difference into a certified incremental-net PnL.
    exposures = realized_exposures(target, positions, official_close, equity)
    ledgers = profit_ledgers(
        equity,
        last_equity,
        costs,
        holdings_valuation_complete=exposures["valuation_coverage"]["complete"],
    )
    return {
        "generated_at_utc": generated_at_utc,
        "account": plan.payload["account"],
        "book_id": plan.payload["book_id"],
        "execution_date": plan.payload["execution_date"],
        "target_sha256": target.payload_sha256,
        "plan_sha256": plan.payload["plan_sha256"],
        "reconciliation": rec,
        "tca": tca(fills, official_close, snapshot_1545),
        "shadow_costs": costs,
        "pnl": {
            "equity": equity,
            "last_equity": last_equity,
            "gross_pnl_broker": gross,
            "shadow_costs_total": costs["total"],
            "net_pnl": gross - costs["total"],
            "net_return": (gross - costs["total"]) / last_equity if last_equity else None,
            "legacy_net_basis": "full_shadow_stress_not_incremental_net",
        },
        "profit_ledgers": ledgers,
        "realized_exposures": exposures,
    }


def daily_path(root: Path, account: str, execution_date: date) -> Path:
    return book_dir(root, account) / "daily" / f"{execution_date.isoformat()}.json"


def write_daily_file(root: Path, record: dict[str, Any]) -> Path:
    return write_json_atomic(
        daily_path(root, record["account"], date.fromisoformat(record["execution_date"])), record
    )


def _optional(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
