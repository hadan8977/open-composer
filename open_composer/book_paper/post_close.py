"""After the close: reconcile orders -> fills -> positions, TCA, shadow costs, daily P&L.

Pure functions over plain dicts so the arithmetic is testable without a broker.  Paper fills carry
neither market impact nor borrow fees, so the net P&L subtracts shadow costs from cost model v1
(half spread at the close snapshot, square-root impact at the traded size, 0.5 bp fees) plus borrow
at 25 bp a year on the short notional.
"""

from __future__ import annotations

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
    for order in plan.orders:
        broker_order = lookup.find(order["client_order_id"])
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
) -> dict[str, Any]:
    """Orders -> fills -> positions against the plan and the target weights."""
    by_id = {o["client_order_id"]: o for o in broker_orders}
    rows: list[dict[str, Any]] = []
    for order in plan.orders:
        broker = by_id.get(order["client_order_id"])
        filled = broker["filled_qty"] if broker else 0.0
        if broker is None:
            state = "missing"
        elif filled >= order["qty"]:
            state = "filled"
        elif filled > 0:
            state = "partial"
        else:
            state = "unfilled"
        rows.append(
            {
                "symbol": order["symbol"],
                "side": order["side"],
                "qty": order["qty"],
                "filled_qty": filled,
                "fill_state": state,
                "broker_status": broker["status"] if broker else None,
                "unfilled_qty": max(order["qty"] - filled, 0.0),
                "filled_avg_price": broker["filled_avg_price"] if broker else None,
                "client_order_id": order["client_order_id"],
            }
        )

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
    return {
        "n_orders": len(rows),
        "n_filled": states.count("filled"),
        "n_partial": states.count("partial"),
        "n_unfilled": states.count("unfilled"),
        "n_missing": states.count("missing"),
        "orders": rows,
        "unfilled_orders": [r for r in rows if r["fill_state"] in ("unfilled", "missing")],
        "partial_fills": [r for r in rows if r["fill_state"] == "partial"],
        "position_drift_vs_plan": drift_rows,
        "n_position_drift_names": len(drift_rows),
        "realized_vs_target_one_sided_drift": round(weight_gap / 2.0, 8),
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
    out: dict[str, Any] = {"n_fills": len(rows), "fills": rows}
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
        "total": total,
    }


# --------------------------------------------------------------------------------------
# realized exposures and daily record
# --------------------------------------------------------------------------------------


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
    return {
        "net_weight": sum(weights.values()),
        "gross_weight": sum(abs(w) for w in weights.values()),
        "beta": beta,
        "hedge_weight": hedge_weight,
        "size_weighted": size,
        "industry_net": dict(sorted(industry.items())),
        "names_without_exposure": missing,
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
) -> dict[str, Any]:
    rec = reconcile(plan, target, broker_orders, positions, official_close)
    fills = rec["orders"]
    costs = shadow_costs(fills, target, positions, official_close, trade_date=plan.execution_date)
    gross = equity - last_equity
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
        },
        "realized_exposures": realized_exposures(target, positions, official_close, equity),
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
