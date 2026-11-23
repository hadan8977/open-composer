"""Revalue the existing homepage comparison with today's paper fills and marks."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from open_composer.market_sessions import (
    NEW_YORK,
    previous_us_equity_session,
    us_equity_session_close,
)
from open_composer.reports.paper_equity import parse_stamp
from scripts.extend_paper_projection_forward import extend_component, num, session_day


def _owners(root: Path, alias: str) -> dict:
    if alias == "six":
        state = json.loads((root / "runtime/paper/six/runtime-state.json").read_text())
        return {
            order["observation"]["id"]: "six/" + order["book"]
            for order in state["orders"].values()
            if (order.get("observation") or {}).get("id") and order.get("book")
        }
    return {
        row["broker_order_id"]: "legacy/" + path.name.removesuffix("-orders.jsonl")
        for path in (root / "reports/paper/rehearsal").glob("*-orders.jsonl")
        for line in path.read_text().splitlines()
        if line.strip()
        if (row := json.loads(line)).get("broker_order_id")
    }


def _component_returns(root: Path, histories: dict, receipt: dict, day: date) -> dict:
    alias = receipt["account"]
    owners = _owners(root, alias) if receipt["activities"] else {}
    executions: dict[str, list] = {}
    for fill in receipt["activities"]:
        identity = owners.get(fill["order_id"])
        if not identity or session_day(fill["transaction_time"]) != day:
            continue
        executions.setdefault(identity, []).append(
            dict(
                day=day,
                symbol=fill["symbol"],
                side=fill["side"],
                quantity=num(fill["qty"]),
                price=num(fill["price"]),
            )
        )
    closes = {
        (symbol, day): num(price)
        for symbol, price in receipt["marks"].items()
        if price is not None and num(price) > 0
    }
    returns = {}
    for identity, series in histories.items():
        if not identity.startswith(alias + "/") or series["kind"] != "trading_component":
            continue
        try:
            point = extend_component(series, executions.get(identity, []), closes, [day])[0]
        except SystemExit:
            # The projector rejects sells unsupported by the closed starting inventory.
            continue
        value = point["tracking_return_pct"]
        if value is not None:
            returns[identity] = float(value)
    return returns


def apply_home_intraday(
    comparison: dict, history: dict, overview: dict, root: Path, now: datetime | None = None
) -> None:
    now = now or datetime.now(UTC)
    local = now.astimezone(NEW_YORK)
    day = local.date()
    close = us_equity_session_close(day)
    prior = comparison["through_session"]
    if close is None or local.time() < time(9, 30):
        return
    if prior != previous_us_equity_session(day).isoformat() or not comparison["days"]:
        return
    histories = {series["id"]: series for series in history["histories"]}
    strategies = {row["id"]: row for row in comparison["strategies"]}
    as_of = min(now, datetime.combine(day, close, tzinfo=NEW_YORK))
    values, stamps = {}, []
    for alias in ("legacy", "six", "quant1"):
        try:
            receipt = json.loads((root / f"runtime/paper/home-{alias}.json").read_text())
            at = parse_stamp(receipt["at"])
            if at.astimezone(NEW_YORK).date() != day or not timedelta() <= as_of - at < timedelta(
                minutes=3
            ):
                continue
            if alias == "quant1":
                f1 = strategies.get("F1")
                points = histories.get("account/quant1/broker-daily", {}).get("points", [])
                prior_equity = next(
                    (num(p["equity_usd"]) for p in points if p["day"] == prior), None
                )
                capital = num(overview.get("initial_pool_capital", {}).get("F1"))
                if (
                    f1
                    and f1["latest_return_pct"] is not None
                    and prior_equity is not None
                    and capital
                ):
                    flows = sum((num(entry["net_amount"]) for entry in receipt["activities"]), 0)
                    change = (num(receipt["equity_usd"]) - prior_equity - flows) / capital
                    values["F1"] = f1["latest_return_pct"] + float(change * 100)
            else:
                values.update(_component_returns(root, histories, receipt, day))
            stamps.append(at)
        except (OSError, ValueError, TypeError, KeyError, ArithmeticError, AttributeError):
            continue
    if not any(identity in values for identity in strategies):
        return

    session, stamp = day.isoformat(), min(stamps).isoformat()
    comparison.update(snapshot_at=stamp, intraday_day=session)
    comparison["days"].append(session)
    for identity, row in strategies.items():
        pct = row["latest_return_pct"] if row["archived"] else values.get(identity)
        row["latest_return_pct"] = pct
        row["points"].append(
            dict(
                day=session,
                return_pct=pct,
                source_at=stamp,
                state="observed" if pct is not None else "missing",
            )
        )
