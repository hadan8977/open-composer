"""Extend the published paper history and overview to the last closed session.

The two published artifacts were sealed through 2026-10-26. This reads that
sealed state, applies the owned fills the books actually received after it, and
marks the resulting positions with raw daily closes up to the newest completed
session. Positions nobody traded are simply carried and valued: no order is
invented, and a session without a usable mark stays an explicit gap.

Inputs come from ``scripts/capture_paper_forward_inputs.py`` receipts. Output is
a new history artifact plus a caller-reconciled v1 overview handed to
``scripts/publish_paper_overview.py``, which validates and switches the binding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

D = Decimal
CENT = D("0.01")
SIX_BOOK_PREFIX = "six/"
SESSIONS = "open_composer.market_sessions"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def bound(root: Path, config: str) -> tuple[dict, dict, Path]:
    binding = load_json(root / config)
    path = (root / binding["path"]).resolve()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise SystemExit(f"sealed artifact changed: {path}")
    return json.loads(raw), binding, path


def parse_stamp(value) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def num(value) -> D | None:
    return None if value is None else D(str(value))


def sessions_between(start: date, end: date, session_dates) -> list[date]:
    return [day for day in session_dates if start < day <= end]


def session_day(stamp: str):
    from zoneinfo import ZoneInfo

    return (
        datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        .astimezone(ZoneInfo("America/New_York"))
        .date()
    )


def executions_by_pool(root: Path, inputs: Path, after: date) -> dict[str, list[dict]]:
    """Owned fills after ``after``, per pool, with the broker's own prices."""
    result: dict[str, list[dict]] = {}
    for path in sorted((root / "reports/paper/rehearsal").glob("*-fills.jsonl")):
        name = path.name[: -len("-fills.jsonl")]
        rows = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get("status")) != "filled" or not row.get("filled_qty"):
                continue
            day = date.fromisoformat(str(row["session"]))
            if day <= after:
                continue
            rows.append(
                dict(
                    pool="legacy/" + name,
                    symbol=str(row["symbol"]).upper(),
                    side=str(row["side"]).lower(),
                    quantity=num(row["filled_qty"]),
                    price=num(row["filled_avg_price"]),
                    day=day,
                    source="retained_rehearsal_fill_ledger",
                )
            )
        if rows:
            result.setdefault("legacy/" + name, []).extend(rows)
    state = load_json(root / "runtime/paper/six/runtime-state.json")
    by_order = {}
    for order in state["orders"].values():
        broker_id = (order.get("observation") or {}).get("id")
        if broker_id and order.get("book"):
            by_order[broker_id] = order["book"]
    activities = load_json(inputs / "activities-six.json")["rows"]
    for row in activities:
        if row.get("activity_type") != "FILL":
            continue
        book = by_order.get(row.get("order_id"))
        if not book:
            raise SystemExit(f"unattributed six FILL {row.get('order_id')}")
        day = session_day(row["transaction_time"])
        if day <= after:
            continue
        result.setdefault("six/" + book, []).append(
            dict(
                pool="six/" + book,
                symbol=str(row["symbol"]).upper(),
                side=str(row["side"]).lower(),
                quantity=num(row["qty"]),
                price=num(row["price"]),
                day=day,
                source="alpaca_paper_activity_FILL",
            )
        )
    for rows in result.values():
        rows.sort(key=lambda r: (r["day"], r["symbol"]))
    return result


def extend_component(row: dict, executions: list[dict], closes, days) -> list[dict]:
    """Carry the sealed book forward with owned fills and raw closes."""
    seed = row["points"][-1]
    quantity = {str(s): num(q) for s, q in (seed.get("quantity") or {}).items()}
    capital = num(seed.get("capital_usd"))
    seed_cash = num(seed.get("cash_from_principal_usd"))
    realized = num(seed.get("realized_fifo_usd")) or D(0)
    remaining = num(seed.get("remaining_fifo_cost_usd")) or D(0)
    # Sealed identity: pnl = holdings + realized - remaining_cost, and
    # cash = capital - net_cost, so either form recovers the same net cost.
    net_cost = (
        capital - seed_cash
        if capital is not None and seed_cash is not None
        else remaining - realized
    )
    points = []
    pending = list(executions)
    for day in days:
        while pending and pending[0]["day"] <= day:
            fill = pending.pop(0)
            symbol, qty, price = fill["symbol"], fill["quantity"], fill["price"]
            if fill["side"] in {"buy", "buy_to_cover"}:
                quantity[symbol] = quantity.get(symbol, D(0)) + qty
                net_cost += qty * price
                remaining += qty * price
            else:
                held = quantity.get(symbol, D(0))
                if qty > held:
                    raise SystemExit(f"{row['id']}: sell {qty} exceeds held {held} of {symbol}")
                basis = (remaining / held) if held else D(0)
                quantity[symbol] = held - qty
                net_cost -= qty * price
                realized += qty * price - basis * qty
                remaining -= basis * qty
        marks, missing = {}, []
        holdings = D(0)
        for symbol, qty in quantity.items():
            if not qty:
                continue
            price = closes.get((symbol, day))
            if price is None:
                missing.append("Missing raw daily close: " + symbol)
                continue
            marks[symbol] = dict(price=price)
            holdings += qty * price
        if missing:
            value = None
        else:
            value = holdings
        pnl = None if value is None else value - net_cost
        cash = None if capital is None else capital - net_cost
        points.append(
            dict(
                day=str(day),
                capital_usd=capital,
                cash_from_principal_usd=cash,
                holdings_value_usd=value,
                nav_before_unverified_items_usd=None
                if value is None or cash is None
                else cash + value,
                trading_pnl_usd=pnl,
                tracking_return_pct=None if pnl is None or not capital else pnl / capital * 100,
                net_pnl_usd=None,
                quantity={s: float(q) for s, q in quantity.items()},
                marks={s: dict(price=float(v["price"])) for s, v in marks.items()},
                realized_fifo_usd=realized,
                remaining_fifo_cost_usd=remaining,
                valuation="reconstructed_from_owned_executions_and_raw_close",
                missing=missing,
            )
        )
    return points


def extend_parent(row: dict, histories: dict, days, session_dates) -> list[dict]:
    points = []
    for day in days:
        members = []
        for child in row["children"]:
            series = histories[child]
            by_day = {p["day"]: p for p in series["points"]}
            point = by_day.get(str(day))
            if point is None:
                members = []
                break
            members.append(point)
        if not members:
            points.append(
                dict(
                    day=str(day),
                    capital_usd=None,
                    cash_from_principal_usd=None,
                    holdings_value_usd=None,
                    nav_before_unverified_items_usd=None,
                    trading_pnl_usd=None,
                    tracking_return_pct=None,
                    net_pnl_usd=None,
                    valuation="sum_of_same_date_separately_funded_children_once",
                    missing=["Missing child/date valuation; no stale carry"],
                )
            )
            continue
        fields = (
            "capital_usd",
            "cash_from_principal_usd",
            "holdings_value_usd",
            "nav_before_unverified_items_usd",
            "trading_pnl_usd",
        )
        point = {
            field: sum(num(m[field]) for m in members if m.get(field) is not None)
            if all(m.get(field) is not None for m in members)
            else None
            for field in fields
        }
        point.update(
            day=str(day),
            tracking_return_pct=None
            if point["trading_pnl_usd"] is None or not point["capital_usd"]
            else point["trading_pnl_usd"] / point["capital_usd"] * 100,
            net_pnl_usd=None,
            valuation="sum_of_same_date_separately_funded_children_once",
            missing=[],
        )
        points.append(point)
    return points


def extend_account(row: dict, capture: dict, days) -> list[dict]:
    """Broker daily equity for each session, plus one post-close live snapshot.

    Alpaca's paper ``portfolio_history`` lags: on 2026-11-10 06:09 UTC it still
    ended 2026-11-06 while the 11-09 session had closed, and an explicit window
    answered a 0.0 placeholder for 11-09. The account endpoint does carry the
    current equity, so a session the daily series has not posted yet is closed
    with that snapshot -- only when the capture really happened after the
    session's close, and never from a zero/degenerate value.
    """
    from open_composer.cockpit.data.paper_books import latest_completed_session

    history = capture["portfolio_history"]
    stamps, values = history.get("timestamp") or [], history.get("equity") or []
    by_day = {}
    for stamp, equity in zip(stamps, values, strict=True):
        if equity is None or float(equity) <= 0:
            continue
        at = datetime.fromtimestamp(stamp, UTC)
        by_day[session_day(at.isoformat())] = (at.isoformat(), float(equity))
    captured_at = parse_stamp(capture["captured_at"])
    snapshot_day = str(latest_completed_session(captured_at))
    account = capture.get("account") or {}
    live_equity = float(account.get("equity") or 0.0)
    snapshot = None
    if snapshot_day not in by_day and live_equity > 0:
        snapshot = (capture["captured_at"], live_equity)
    points = []
    previous = None
    for day in days:
        hit = by_day.get(day)
        if hit is None and snapshot is not None and str(day) == snapshot_day:
            hit = snapshot
            valuation, source = "broker_account_snapshot_after_close", "alpaca_account_snapshot"
        else:
            valuation, source = "broker_daily_equity_snapshot", "alpaca_portfolio_history_1D"
        if hit is not None and previous is not None and hit[1] <= previous * 0.1:
            hit = None  # provider zero/placeholder: keep the day as an explicit gap
        if hit is not None:
            previous = hit[1]
        points.append(
            dict(
                day=str(day),
                at=hit[0] if hit else None,
                equity_usd=hit[1] if hit else None,
                source=source if hit else "alpaca_portfolio_history_1D",
                valuation=valuation if hit else "broker_daily_equity_snapshot",
                net_pnl_usd=None,
                missing=[]
                if hit
                else ["No same-session broker equity; no stale carry"],
            )
        )
    return points


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument(
        "--sealed-history",
        type=Path,
        required=True,
        help="The sealed 2026-10-27 history, never the live binding (re-runs must be idempotent)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    inputs = args.inputs.resolve()

    from open_composer.market_sessions import us_equity_session_dates

    history = load_json(args.sealed_history)
    overview, _, overview_path = bound(root, "config/paper-overview-dashboard.json")
    bars = load_json(inputs / "bars.json")["symbols"]
    closes = {
        (symbol, date.fromisoformat(row["day"])): num(row["close"])
        for symbol, rows in bars.items()
        for row in rows
    }
    last_sealed = date.fromisoformat(history["through_session"])
    stamped = sorted({day for (_, day) in closes})
    accounts = {
        alias: load_json(inputs / f"account-{alias}.json") for alias in ("legacy", "quant1", "six")
    }
    from open_composer.cockpit.data.paper_books import latest_completed_session

    posted = []
    for capture in accounts.values():
        days_with_equity = [
            session_day(datetime.fromtimestamp(stamp, UTC).isoformat())
            for stamp, equity in zip(
                capture["portfolio_history"]["timestamp"],
                capture["portfolio_history"]["equity"],
                strict=True,
            )
            if float(equity or 0) > 0
        ]
        if days_with_equity:
            posted.append(max(days_with_equity))
    snapshots = [
        latest_completed_session(parse_stamp(capture["captured_at"]))
        for capture in accounts.values()
        if float((capture.get("account") or {}).get("equity") or 0) > 0
    ]
    newest = max(posted + snapshots)
    through = min(newest, max(stamped))
    days = sessions_between(last_sealed, through, us_equity_session_dates(last_sealed, through))
    if not days:
        raise SystemExit("nothing to extend")
    print(f"extending {last_sealed} -> {through} ({len(days)} sessions)")

    executions = executions_by_pool(root, inputs, last_sealed)
    print("owned fills after the cut-off:", {k: len(v) for k, v in executions.items()})

    histories = {row["id"]: row for row in history["histories"]}
    added: dict[str, list] = {}
    for row in history["histories"]:
        if row["kind"] == "trading_component":
            added[row["id"]] = extend_component(
                row, executions.get(row["id"], []), closes, days
            )
        elif row["kind"] == "account":
            alias = next(
                (a for a in accounts if row["id"].startswith(f"account/{a}")), None
            )
            added[row["id"]] = extend_account(row, accounts[alias], days) if alias else []
        elif row["kind"] == "composite_parent":
            continue
        else:
            added[row["id"]] = []
        # Children must be current before the parents are summed.
        row["points"] = list(row["points"]) + added[row["id"]]
    for row in history["histories"]:
        if row["kind"] == "composite_parent":
            added[row["id"]] = extend_parent(row, histories, days, us_equity_session_dates)
            row["points"] = list(row["points"]) + added[row["id"]]

    gaps = []
    for row in history["histories"]:
        points_added = added[row["id"]] or []
        missing = [p["day"] for p in points_added if p.get("missing")]
        if missing:
            gaps.append((row["id"], missing))
        if row["kind"] == "trading_component":
            last = row["points"][-1]
            print(
                f"  {row['id'][:48]:48s} {last['day']} pnl={num(last['trading_pnl_usd'])}"
            )
    if gaps:
        print("explicit gaps:", gaps)
    history.update(
        through_session=str(through),
        generated_at=datetime.now(UTC).isoformat(),
        forward_extension=dict(
            from_session=str(last_sealed),
            to_session=str(through),
            method=(
                "carry the sealed quantity/cash state, apply only owned broker FILLs, "
                "mark at raw SIP daily closes; no order is invented"
            ),
            unclosed_intent_20261103_20261106=(
                "the ETF sleeves' intended rebalances for 2026-11-03..2026-11-06 were "
                "blocked_by_submission_window (23:5x UTC = 18:5x ET after DST) and never "
                "reached the broker; the books therefore hold their 2026-11-02 positions "
                "and the pending targets are carried into the next accepted open"
            ),
            inputs=sorted(str(p) for p in inputs.glob("*.json")),
        ),
    )
    history["source_bindings"] = list(history.get("source_bindings") or []) + [
        dict(
            path=str(path),
            bytes=len(path.read_bytes()),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(inputs.glob("*.json"))
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(history, indent=2, default=str, ensure_ascii=False, allow_nan=False) + "\n"
    )
    print("history written:", args.output)

    rows = []
    for row in overview["snapshot"]["rows"]:
        series = histories.get(row["id"])
        if row["id"] == "F1" or row["pool"] == "F1":
            rows.append(dict(row))
            continue
        last = series["points"][-1]
        pnl = num(last.get("trading_pnl_usd"))
        capital = num(last.get("capital_usd"))
        updated = dict(row)
        updated["capital_usd"] = None if capital is None else float(capital)
        updated["precise_pnl_usd"] = None if pnl is None else float(pnl)
        updated["pnl_usd"] = None if pnl is None else float(pnl.quantize(CENT))
        updated["return_pct"] = (
            float(pnl / capital * 100) if pnl is not None and capital else None
        )
        updated["missing"] = [last["day"]] if pnl is None else []
        rows.append(updated)
    print("rows updated from the extended books:", len(rows))
    json.dump(
        dict(rows=rows, through=str(through), overview_path=str(overview_path)),
        open(args.output.with_suffix(".rows.json"), "w"),
        indent=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
