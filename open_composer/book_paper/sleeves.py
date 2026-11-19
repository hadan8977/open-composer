"""Sleeve orders and ownership inside the Quant1 paper account.

Registry paths may use {decision_date} and {execution_date}. Each daily target has
decision_date, execution_date and weights. The owner authorization JSON names the
account and sleeve and sets max_capital, max_gross_leverage, stop_equity and
expires_at_utc. A disabled sleeve keeps its shares and cash until explicitly unwound.

The dated account plan fixes the allocation before orders are sent. The existing
atomic daily file is the ledger checkpoint, including each sleeve's fill journal.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

from open_composer.book_paper.plan import (
    AccountState,
    AssetInfo,
    OrderPlan,
    RiskLimits,
    _borrow_rejection,
    _frozen_reason,
    _plan_hash,
    _valid_price,
    build_plan,
    client_order_id,
    round_half_away,
)
from open_composer.book_paper.targets import BookTarget, book_dir

BOOK = "book"
SLEEVE_ORDER_PREFIX = "bk1-sl-"


def registry(root: Path, account: str) -> dict[str, dict[str, Any]]:
    path = root / "control.json"
    if account != "quant1" or not path.exists():
        return {}
    return {
        row["name"]: row
        for row in json.loads(path.read_text(encoding="utf-8"))["paper"].get("sleeves", [])
        if row["account"] == account
    }


def sleeve_history(root: Path, target: BookTarget) -> tuple[dict, dict]:
    base = book_dir(root, target.account)
    days = sorted(
        p for p in (base / "daily").glob("20??-??-??.json") if p.stem < str(target.execution_date)
    )
    last = _read(days[-1]).get("shared", {}) if days else {}
    settled = {p.stem for p in days}
    # A late repair of an old plan still needs to flow into the newest ledger.
    frozen = {
        s: reason
        for s, reason in last.get("freeze_reasons", {}).items()
        if reason in {"unreconciled_sleeve_plan", "unexplained_account_position"}
    } | dict.fromkeys(last.get("unexplained", {}), "unexplained_account_position")
    for path in (base / "plans").glob("20??-??-??.json"):
        if path.stem < str(target.execution_date) and path.stem not in settled:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for symbol, row in payload.get("shared", {}).get("allocation", {}).items():
                if set(row["deltas"]) - {BOOK}:
                    frozen[symbol] = "unreconciled_sleeve_plan"
    return last.get("sleeves", {}), frozen


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _authorization(root: Path, row: dict, ledger: dict, now: datetime) -> dict:
    auth = _read(root / row["authorization"])
    if (auth["account"], auth["sleeve"]) != (row["account"], row["name"]):
        raise ValueError("authorization_scope")
    if now >= datetime.fromisoformat(auth["expires_at_utc"]):
        raise ValueError("authorization_expired")
    if not math.isfinite(row["capital"]) or not 0 < row["capital"] <= auth["max_capital"]:
        raise ValueError("authorization_capital")
    if not (
        math.isfinite(auth["max_gross_leverage"])
        and auth["max_gross_leverage"] > 0
        and math.isfinite(auth["stop_equity"])
    ):
        raise ValueError("invalid_authorization_limits")
    equity = ledger.get("equity")
    if (ledger["capital"] if equity is None else equity) <= auth["stop_equity"]:
        raise ValueError("authorization_equity_stop")
    return auth


def _targets(root: Path, target: BookTarget, row: dict, ledger: dict, now: datetime) -> dict:
    auth = _authorization(root, row, ledger, now)
    path = root / row["target_file"].format(
        decision_date=target.decision_date, execution_date=target.execution_date
    )
    signal = _read(path)
    if (signal["decision_date"], signal["execution_date"]) != (
        str(target.decision_date),
        str(target.execution_date),
    ):
        raise ValueError("target_date_mismatch")
    raw_weights = signal["weights"]
    if not isinstance(raw_weights, dict):
        raise ValueError("invalid_target_weights")
    weights = {
        s: w if isinstance(w, (int, float)) and math.isfinite(w) else None
        for s, w in raw_weights.items()
    }
    if sum(abs(w) for w in weights.values() if w is not None) > auth["max_gross_leverage"]:
        raise ValueError("authorization_gross_cap")
    return weights


def live_freezes(root: Path, plan: OrderPlan, now: datetime) -> dict[str, str]:
    rows = registry(root, plan.payload["account"])
    stopped = {}
    for name, holding in plan.payload["shared"]["sleeves"].items():
        try:
            if not rows.get(name, {}).get("enabled"):
                raise ValueError("sleeve_disabled")
            if (rows[name]["capital"], rows[name]["authorization"]) != (
                holding["capital"],
                holding.get("authorization"),
            ):
                raise ValueError("sleeve_authorization_or_capital_changed")
            auth = _authorization(root, rows[name], holding, now)
            if (
                sum(abs(w) for w in holding["weights"].values() if w is not None)
                > auth["max_gross_leverage"]
            ):
                raise ValueError("authorization_gross_cap")
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            stopped[name] = str(exc)
    return {
        symbol: stopped[name]
        for symbol, row in plan.payload["shared"]["allocation"].items()
        for name in row["deltas"]
        if name in stopped
    }


def decision_closes(root: Path, day: date, symbols: set[str]) -> dict[str, float]:
    """Read extra symbols from the same dated current-units view as Quant1."""
    pointer = root / "data/live/equity_book_current.json"
    if not symbols or not pointer.exists():
        return {}
    current = _read(pointer)
    if current["decision_day"] != str(day):
        return {}
    import pandas as pd

    view = Path(current["consumer_view_root"])
    prices = view / "prices" / f"{day.year}.parquet"
    if not prices.is_file():
        return {}
    filters = [("trade_date", "==", pd.Timestamp(day)), ("symbol", "in", sorted(symbols))]
    frame = pd.read_parquet(prices, columns=["symbol", "close"], filters=filters)
    return {s: float(p) for s, p in zip(frame["symbol"], frame["close"], strict=True)}


def _add(positions: Mapping, deltas: Mapping) -> dict:
    out = dict(positions)
    for symbol, qty in deltas.items():
        out[symbol] = out.get(symbol, 0) + qty
    return {s: q for s, q in out.items() if abs(q) > 1e-9}


def _split_quantity(qty: int, requests: dict[str, int]) -> dict[str, int]:
    """Largest remainders preserve whole shares and the exact broker quantity."""
    total = sum(requests.values())
    if not qty:
        return {}
    quotas = {name: divmod(qty * amount, total) for name, amount in requests.items()}
    split = {name: count for name, (count, _) in quotas.items()}
    for name in sorted(quotas, key=lambda n: (-quotas[n][1], n))[: qty - sum(split.values())]:
        split[name] += 1
    return split


def allocations(deltas: dict[str, int], filled: int) -> tuple[dict[str, int], dict[str, int]]:
    buys = {n: q for n, q in deltas.items() if q > 0}
    sells = {n: -q for n, q in deltas.items() if q < 0}
    crossed = min(sum(buys.values()), sum(sells.values()))
    internal = _split_quantity(crossed, buys) | {
        n: -q for n, q in _split_quantity(crossed, sells).items()
    }
    sign = 1 if sum(deltas.values()) > 0 else -1
    remaining = {n: q - sign * internal.get(n, 0) for n, q in (buys if sign > 0 else sells).items()}
    return internal, {n: sign * q for n, q in _split_quantity(filled, remaining).items()}


def _opening(current: float, post: float) -> float:
    return max(abs(post) - abs(current), 0) if current * post > 0 else abs(post)


def build_shared_plan(
    root: Path,
    target: BookTarget,
    state: AccountState,
    *,
    rows: dict,
    history: tuple[dict, dict],
    as_of: date,
    now: datetime,
    asset_lookup: Callable[[str], AssetInfo | None],
    min_notional: float,
    kill_switch_check: Callable[[], None] | None = None,
) -> OrderPlan:
    ledgers, frozen = history
    foreign = dict.fromkeys((s for s, _ in state.open_orders), "conflicting_open_order")
    frozen = frozen | target.frozen_symbols | foreign
    carried = {n: h for n, h in ledgers.items() if h["positions"] or rows.get(n, {}).get("enabled")}
    book_qty = dict(state.positions)
    for h in carried.values():
        book_qty = _add(book_qty, {s: -q for s, q in h["positions"].items()})
    book_target = target.model_copy(update={"frozen_symbols": frozen})
    held_marks = {s: p for h in carried.values() for s, p in h.get("marks", {}).items()}
    book = build_plan(
        book_target,
        replace(state, positions=book_qty, position_prices=held_marks | state.position_prices),
        as_of=as_of,
        now=now,
        asset_lookup=asset_lookup,
        min_notional=min_notional,
        kill_switch_check=kill_switch_check,
        shared_account=True,
    )
    sleeves, signals = {}, {}
    symbols = set(book_qty)
    for name in sorted(set(carried) | {n for n, r in rows.items() if r["enabled"]}):
        row = rows.get(name, {})
        holding = carried.get(name)
        h = holding or {
            "capital": row["capital"],
            "cash": row["capital"],
            "positions": {},
            "equity": None,
        }
        sleeves[name] = {k: h[k] for k in ("capital", "cash", "positions", "equity")}
        sleeves[name]["frozen"] = {}
        symbols.update(h["positions"])
        try:
            if not row.get("enabled"):
                raise ValueError("sleeve_disabled")
            if name == BOOK or row["capital"] != h["capital"]:
                raise ValueError("invalid_sleeve_name_or_changed_capital")
            signals[name] = _targets(root, target, row, h, now)
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            sleeves[name]["hold_reason"] = str(exc)
            sleeves[name]["frozen"].update(dict.fromkeys(h["positions"], str(exc)))
            continue
        sleeves[name]["authorization"] = row["authorization"]
        sleeves[name]["weights"] = signals[name]
        symbols.update(signals[name])

    decision = target.reference_prices | decision_closes(
        root, target.decision_date, symbols - set(target.reference_prices)
    )
    decision = {s: p for s, p in decision.items() if _valid_price(p)}
    marks = held_marks | decision
    marks.update({s: p for s, p in state.position_prices.items() if _valid_price(p)})
    for order in book.orders:
        marks.setdefault(order["symbol"], order["reference_price"])

    book_orders = {o["symbol"]: o for o in book.orders} if book.status == "ok" else {}
    for symbol, order in list(book_orders.items()):
        current = state.positions.get(symbol, 0)
        physical_post = current + order["post_qty"] - order["current_qty"]
        if physical_post < min(current, 0):
            reason = _borrow_rejection(asset_lookup(symbol))
            if reason or not state.shorting_enabled:
                frozen[symbol] = reason or "account_shorting_disabled"
                del book_orders[symbol]
    deltas = {s: {BOOK: o["post_qty"] - o["current_qty"]} for s, o in book_orders.items()}
    gross_limit = state.equity * RiskLimits().max_gross_leverage
    buying_power = min(
        (p for p in (state.buying_power, state.regt_buying_power) if p is not None), default=0
    )

    opening_positions = {BOOK: book_qty} | {n: h["positions"] for n, h in sleeves.items()}
    starting_gross = sum(
        abs(q) * marks.get(s, 0)
        for holding in opening_positions.values()
        for s, q in holding.items()
    )

    def capacity(proposed: dict[str, dict[str, int]]) -> tuple[float, float, float]:
        change = growth = power = 0.0
        for s, ds in proposed.items():
            current = state.positions.get(s, 0)
            post = current + sum(ds.values())
            power += _opening(current, post) * marks[s] * (1.03 if post < 0 else 1)
            for name, delta in ds.items():
                held = opening_positions[name].get(s, 0)
                difference = (abs(held + delta) - abs(held)) * marks[s]
                change += difference
                growth += max(difference, 0)
        # A partial or rejected order cannot be counted on to release gross.
        return starting_gross + growth, power, starting_gross + change

    def fits(totals, limits):
        return all(value <= limit + 1e-8 for value, limit in zip(totals[:2], limits, strict=True))

    if not fits(capacity(deltas), (gross_limit, buying_power)):
        for symbol, order in book_orders.items():
            current, post = order["current_qty"], order["post_qty"]
            physical = state.positions.get(symbol, 0)
            if abs(post) > abs(current) or _opening(physical, physical + post - current):
                deltas.pop(symbol)
                frozen[symbol] = "account_capacity"
        book_orders = {s: o for s, o in book_orders.items() if s in deltas}

    reserve = max(
        state.equity
        - target.equity_basis
        - sum(h["capital"] for n, h in carried.items() if n not in signals),
        0,
    )
    for name, weights in signals.items():
        h = sleeves[name]
        positions = h["positions"]
        capital = min(h["capital"], reserve)
        reserve -= capital
        h["effective_capital"] = capital
        desired = {}
        for symbol in sorted(set(positions) | set(weights)):
            price = decision.get(symbol)
            weight, current = weights.get(symbol, 0), positions.get(symbol, 0)
            asset = asset_lookup(symbol)
            reason = frozen.get(symbol) or _frozen_reason(asset)
            if not price:
                reason = reason or "missing_decision_close"
            if weight is None:
                reason = reason or "invalid_target_weight"
            broker_qty = state.positions.get(symbol, 0)
            if abs(broker_qty - round(broker_qty)) > 1e-9:
                reason = reason or "fractional_position"
            if reason:
                h["frozen"][symbol] = reason
                continue
            delta = round_half_away(weight * capital / price) - current
            if abs(delta) <= abs(current) * 0.02 or abs(delta) * price < min_notional:
                continue
            post = broker_qty + sum(deltas.get(symbol, {}).values()) + delta
            if current + delta < min(current, 0) or post < min(broker_qty, 0):
                reason = _borrow_rejection(asset)
                if reason or not state.shorting_enabled:
                    h["frozen"][symbol] = reason or "account_shorting_disabled"
                    continue
            desired[symbol] = delta

        def proposal(
            scale: float, base: dict, requested: dict, participant: str, held: dict
        ) -> dict:
            proposed = dict(base)
            for symbol, delta in requested.items():
                qty = math.trunc(delta * scale)
                price = decision[symbol]
                parts = base.get(symbol, {}) | {participant: qty}
                net = abs(sum(parts.values()))
                if (
                    abs(qty) > abs(held.get(symbol, 0)) * 0.02
                    and abs(qty) * price >= min_notional
                    and (not net or net * price >= min_notional)
                ):
                    proposed[symbol] = parts
            return proposed

        ceiling = tuple(
            max(a, b)
            for a, b in zip(capacity(deltas)[:2], (gross_limit, buying_power), strict=True)
        )
        best, scale = proposal(1.0, deltas, desired, name, positions), 1.0
        if not fits(capacity(best), ceiling):
            lo, hi, best = 0.0, 1.0, deltas
            for _ in range(18):
                mid = (lo + hi) / 2
                trial = proposal(mid, deltas, desired, name, positions)
                if fits(capacity(trial), ceiling):
                    lo, best = mid, trial
                else:
                    hi = mid
            scale = lo
        for symbol in desired:
            if name not in best.get(symbol, {}):
                h["frozen"][symbol] = "account_capacity" if scale < 1 else "net_min_notional"
        h["scale"] = scale
        deltas = best

    worst_gross, power, gross = capacity(deltas)
    orders, allocation = [], {}
    account_post = dict(state.positions)
    book_post = dict(book_qty)
    for symbol, parts in sorted(deltas.items()):
        net = sum(parts.values())
        crossed = (sum(abs(q) for q in parts.values()) - abs(net)) // 2
        book_order = book_orders.get(symbol)
        price = book_order["reference_price"] if book_order else decision[symbol]
        side = "buy" if net > 0 else "sell"
        qty = abs(net)
        cid = client_order_id(
            target.book_id, target.account, target.execution_date, symbol, side, qty
        )
        if set(parts) != {BOOK}:
            cid = SLEEVE_ORDER_PREFIX + cid[4:]
        allocation[symbol] = {
            "client_order_id": cid,
            "deltas": parts,
            "crossed": crossed,
            "decision_price": decision.get(symbol, price),
        }
        current = state.positions.get(symbol, 0)
        account_post[symbol] = current + net
        book_post[symbol] = book_qty.get(symbol, 0) + parts.get(BOOK, 0)
        if net:
            orders.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "type": "market",
                    "time_in_force": "cls",
                    "reference_price": price,
                    "notional": round(qty * price, 2),
                    "current_qty": current,
                    "post_qty": current + net,
                    "client_order_id": cid,
                    "opens_or_increases_short": current + net < min(current, 0),
                    "already_submitted": False,
                }
            )

    book.payload.update(
        orders=list(book_orders.values()), post_trade_qty={s: q for s, q in book_post.items() if q}
    )
    payload = book.payload | {
        "orders": orders,
        "post_trade_qty": {s: q for s, q in account_post.items() if q},
        "shared": {
            "book_orders": book.orders,
            "book_start": book_qty,
            "book_post": book.payload["post_trade_qty"],
            "sleeves": sleeves,
            "allocation": allocation,
            "decision_prices": decision,
            "marks": marks,
            "frozen": frozen | {r["symbol"]: r["reason"] for r in book.payload.get("frozen", [])},
            "capacity": {
                "gross": gross,
                "gross_if_reductions_miss": worst_gross,
                "gross_limit": gross_limit,
                "buying_power_used": power,
                "buying_power": buying_power,
                "unpriced_positions": sorted(
                    (set(book_qty) | {s for h in sleeves.values() for s in h["positions"]})
                    - set(marks)
                ),
            },
        },
    }
    payload["summary"] = payload["summary"] | {
        "n_orders": len(orders),
        "n_buy": sum(o["side"] == "buy" for o in orders),
        "n_sell": sum(o["side"] == "sell" for o in orders),
        "buy_notional": sum(o["notional"] for o in orders if o["side"] == "buy"),
        "sell_notional": sum(o["notional"] for o in orders if o["side"] == "sell"),
    }
    payload["plan_sha256"] = _plan_hash(payload)
    return OrderPlan(payload)


def reconcile_shared(
    plan: OrderPlan,
    broker_orders: list[dict],
    broker_positions: dict,
    close_prices: dict,
    receipts: list[dict],
) -> tuple[OrderPlan, list[dict], dict, dict]:
    from open_composer.book_paper.reversal import reversal_legs

    shared = plan.payload["shared"]
    account_orders = {o["symbol"]: o for o in plan.orders}
    broker = {o["client_order_id"]: o for o in broker_orders}
    admitted = {
        cid: tif for receipt in receipts for cid, tif in receipt.get("internal_crosses", {}).items()
    }
    journal = defaultdict(list)
    frozen = dict(shared["frozen"])
    for symbol, row in shared["allocation"].items():
        cid = row["client_order_id"]
        order = account_orders.get(symbol)
        ids = [cid] + ([o["client_order_id"] for o in reversal_legs(order)] if order else [])
        external_orders = [broker[i] for i in ids if i in broker]
        filled = sum(o["filled_qty"] for o in external_orders)
        if filled != int(filled) or filled > abs(sum(row["deltas"].values())):
            raise ValueError(f"invalid fill quantity {filled:g} for net order {cid}")
        avg = (
            sum(o["filled_qty"] * o["filled_avg_price"] for o in external_orders if o["filled_qty"])
            / filled
            if filled
            else None
        )
        internal, external = allocations(row["deltas"], int(filled))
        if row["crossed"] and (filled or cid in admitted):
            close = _valid_price(close_prices.get(symbol))
            cross_price = (close if admitted.get(cid) == "cls" else avg) or close or avg
            if cross_price is None:
                frozen[symbol] = "missing_cross_settlement_price"
            else:
                for name, qty in internal.items():
                    if qty:
                        journal[name].append(
                            {
                                "symbol": symbol,
                                "qty": qty,
                                "price": cross_price,
                                "kind": "internal",
                                "client_order_id": cid,
                                "decision_price": row["decision_price"],
                            }
                        )
        for name, qty in external.items():
            if qty:
                journal[name].append(
                    {
                        "symbol": symbol,
                        "qty": qty,
                        "price": avg,
                        "kind": "broker",
                        "client_order_id": cid,
                        "decision_price": row["decision_price"],
                    }
                )

    def apply_fills(name: str, start: dict) -> dict:
        positions = dict(start)
        for fill in journal[name]:
            s = fill["symbol"]
            positions[s] = positions.get(s, 0) + fill["qty"]
        return {s: q for s, q in positions.items() if q}

    sleeves = {}
    for name, holding in shared["sleeves"].items():
        start = holding["positions"]
        positions = apply_fills(name, start)
        fills = journal[name]
        for fill in fills:
            fill["slippage_dollars"] = fill["qty"] * (fill["price"] - fill["decision_price"])
        trade_cash = -sum(f["qty"] * f["price"] for f in fills)
        cash = holding["cash"] + trade_cash
        opening = shared["decision_prices"]
        missing = sorted(
            {s for s in start if not _valid_price(opening.get(s))}
            | {s for s in positions if not _valid_price(close_prices.get(s))}
        )
        marks = {s: p for s in positions if (p := _valid_price(close_prices.get(s))) is not None}
        equity = (
            cash + sum(q * marks[s] for s, q in positions.items())
            if len(marks) == len(positions)
            else None
        )
        pnl = (
            equity - holding["cash"] - sum(q * opening[s] for s, q in start.items())
            if not missing
            else None
        )
        slippage = sum(f["slippage_dollars"] for f in fills)
        sleeves[name] = holding | {
            "positions": positions,
            "cash": cash,
            "equity": equity,
            "marks": {
                s: marks.get(s, shared["marks"].get(s))
                for s in positions
                if s in marks or s in shared["marks"]
            },
            "pnl": pnl,
            "missing_marks": missing,
            "fills": fills,
            "slippage_dollars": slippage,
            "summary": f"{name} pnl={pnl if pnl is None else round(pnl, 2)} "
            f"slippage={slippage:.2f} fills={len(fills)} positions={len(positions)}",
        }

    book_orders = shared["book_orders"]
    attributed_book = []
    for order in book_orders:
        symbol = order["symbol"]
        fills = [f for f in journal[BOOK] if f["symbol"] == symbol]
        qty = sum(abs(f["qty"]) for f in fills)
        if qty:
            attributed_book.append(
                order
                | {
                    "filled_qty": qty,
                    "filled_avg_price": sum(abs(f["qty"]) * f["price"] for f in fills) / qty,
                    "status": "filled" if qty == order["qty"] else "partially_filled",
                }
            )
        elif source := account_orders.get(symbol):
            observed = broker.get(source["client_order_id"])
            if observed:
                attributed_book.append(
                    order
                    | {
                        "filled_qty": 0,
                        "filled_avg_price": None,
                        "status": observed["status"],
                    }
                )

    book_positions = apply_fills(BOOK, shared["book_start"])
    frozen_positions = {s: q for s, q in book_positions.items() if s in frozen}
    book_positions = {s: q for s, q in book_positions.items() if s not in frozen_positions}
    expected = book_positions | frozen_positions
    actual_book = dict(broker_positions)
    for holding in sleeves.values():
        holdings = holding["positions"]
        expected = _add(expected, holdings)
        actual_book = _add(actual_book, {s: -q for s, q in holdings.items()})
    difference = _add(broker_positions, {s: -q for s, q in expected.items()})
    sleeve_names = (
        set(shared["frozen"])
        | {s for h in sleeves.values() for s in h["positions"]}
        | {s for s, row in shared["allocation"].items() if set(row["deltas"]) - {BOOK}}
    )
    payload = plan.payload | {"orders": book_orders, "post_trade_qty": shared["book_post"]}
    return (
        OrderPlan(payload),
        attributed_book,
        actual_book,
        {
            "sleeves": sleeves,
            "book_positions": book_positions,
            "frozen_positions": frozen_positions,
            "freeze_reasons": frozen,
            "broker_positions": broker_positions,
            "position_difference": difference,
            "unexplained": {s: q for s, q in difference.items() if s in sleeve_names},
            "broker_orders": broker_orders,
        },
    )
