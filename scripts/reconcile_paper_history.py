"""Reconcile retained paper history offline; never create a broker/source client.

This is a dated projection of evidence, not a trading engine or a backtest.
FIFO is reused from the accepted six-paper projection. Original records remain
untouched. Raw prices and account observations retain distinct provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from open_composer.cockpit.data.paper_history import account_performance
from open_composer.market_sessions import NEW_YORK, us_equity_session_dates
from scripts.reconcile_six_paper_performance import fifo, project

D = Decimal
LEGACY = {
    "us_etf_sector_rotation_252_top2_weekly": ("S1", D(15000)),
    "us_etf_growth_rotation_blend_top2_monthly": ("S2", D(15000)),
    "us_etf_levered_rotation_63_top2_monthly": ("S3", D(15000)),
    "us_etf_eom_sector_blend_monthly": ("C2", D(15000)),
    "us_recent_high_return_top50": ("Retired top50", None),
}
OLD_ACCOUNT = "d9589fb0319a7f1a740d40c4c1bd209568c0e6609e72d02a4be5a6b5545592d7"
SIX_ACCOUNT = "fa6147de4f85f4f14f225c59eebb9ecc4c764e87571f413afebcb63aa76c81d4"
NY26_UNSUPPORTED_TAILS = {
    "legacy": "6d6da717558a2a432c501c1e2a80d76d1863a8cb362d41e8e2139b2179cb9db7",
    "six": "6780e8f9b5a6ac68eb551b48f320e0e5d4bb1db26d0be14a0baccf5d8416533d",
    "F1": "aa2951e3200c6cfb7487ca28ad09007a6b7ef566b6c9edae48defc4521eaaf5d",
}


def stamp(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def day_of(value):
    return stamp(value).astimezone(NEW_YORK).date()


def read(path, consumed):
    raw = path.read_bytes()
    if len(raw) > 16_777_216:
        raise ValueError(f"oversized history input: {path.name}")
    consumed[str(path)] = dict(
        path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()
    )
    return json.loads(raw, parse_float=D)


def raw_sources(root, consumed, additional=()):
    directories = [root / "reports/research/program/paper-launch-20min-20261021/source"]
    directories += sorted(
        (root / "reports/paper/diagnostics/dated-target-refresh").glob("*/source")
    )
    directories += [root / "reports/paper/diagnostics/resume-20261022/target-refresh/source"]

    def records():
        for directory in directories:
            for metadata in sorted(directory.glob("*.json")):
                body_path = metadata.with_suffix(".raw")
                if metadata.name.endswith(".started.json") or not body_path.exists():
                    continue
                meta = read(metadata, consumed)
                if meta.get("status_code") != 200:
                    continue
                raw = read(body_path, consumed)
                consumed[str(metadata)].update(
                    kind="source_request_receipt",
                    params=meta.get("params"),
                    requested_at=meta.get("started_at"),
                    received_at=meta.get("received_at"),
                    response_next_page_token=raw.get("next_page_token"),
                )
                yield meta, raw, str(body_path)
        for receipt, body in additional:
            yield (
                {"params": receipt["request"]["params"], "received_at": receipt["received_at"]},
                body,
                receipt["body"]["path"],
            )

    prices, revisions, unit_events = {}, [], []
    seen_actions = set()
    for meta, raw, source in records():
        params = meta.get("params", {})
        if params.get("adjustment") == "raw" and params.get("timeframe") == "1Day":
            for symbol, bars in raw.get("bars", {}).items():
                for bar in bars:
                    day, price = day_of(bar["t"]), D(str(bar["c"]))
                    if not price.is_finite() or price <= 0:
                        revisions.append(
                            dict(
                                kind="invalid_raw_close", symbol=symbol, day=str(day), source=source
                            )
                        )
                        continue
                    key = (symbol, day)
                    point = dict(
                        price=price, at=bar["t"], received_at=meta.get("received_at"), source=source
                    )
                    if key in prices and prices[key]["price"] != point["price"]:
                        revisions.append(
                            dict(symbol=symbol, day=str(day), before=prices[key], after=point)
                        )
                    if key not in prices or str(point["received_at"]) > str(
                        prices[key]["received_at"]
                    ):
                        prices[key] = point
        if "corporate_actions" in raw:
            for kind, rows in raw["corporate_actions"].items():
                if kind in {"cash_dividends", "capital_gain_distributions"}:
                    continue
                for row in rows:
                    symbol = row.get("symbol") or row.get("initiating_symbol")
                    effective = row.get("ex_date") or row.get("effective_date")
                    key = (kind, row.get("id"), symbol, str(effective)[:10])
                    if symbol and effective and key not in seen_actions:
                        seen_actions.add(key)
                        unit_events.append(
                            dict(
                                symbol=symbol,
                                day=str(effective)[:10],
                                kind=kind,
                                id=row.get("id"),
                                source=source,
                            )
                        )
    return prices, revisions, unit_events


def legacy_executions(path, consumed):
    raw = path.read_bytes()
    consumed[str(path)] = dict(
        path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()
    )
    by_order, conflicts = {}, []
    for index, line in enumerate(raw.decode().splitlines()):
        if not line.strip():
            continue
        row = json.loads(line, parse_float=D)
        quantity = D(str(row.get("filled_qty") or 0))
        if quantity <= 0 or not row.get("filled_avg_price"):
            continue
        identity = row.get("broker_order_id") or row.get("client_order_id")
        if not identity:
            raise ValueError("filled order lacks identity")
        event = dict(
            id=identity,
            order_id=identity,
            symbol=row["symbol"],
            side=row["side"],
            quantity=quantity,
            price=D(str(row["filled_avg_price"])),
            time=str(row.get("filled_at") or row["session"]).replace(" ", "T"),
            session=row["session"],
            basis="retained_order_cumulative_average",
        )
        previous = by_order.get(identity)
        if previous and (previous["symbol"], previous["side"], previous["session"]) != (
            event["symbol"],
            event["side"],
            event["session"],
        ):
            raise ValueError("order identity reused across economic events")
        if previous and quantity == previous["quantity"] and event["price"] != previous["price"]:
            conflicts.append(
                dict(
                    order_id=identity,
                    line=index + 1,
                    before=previous["price"],
                    after=event["price"],
                )
            )
        if previous is None or quantity >= previous["quantity"]:
            by_order[identity] = event
    return sorted(by_order.values(), key=lambda x: (x["time"], x["id"])), conflicts


def historical_book(identity, label, executions, initial, flows, prices, end, unit_events=()):
    """Principal/FIFO identity at each real session; absent raw marks stay gaps."""
    start = min(
        (date.fromisoformat(x.get("session") or str(x["time"])[:10]) for x in executions),
        default=None,
    )
    points = []
    if start is None:
        return dict(
            id=identity,
            label=label,
            kind="trading_component",
            points=[],
            missing=["No retained executed trade"],
            net_status="unverified",
        )
    for day in us_equity_session_dates(start, end):
        prefix = [
            x
            for x in executions
            if date.fromisoformat(x.get("session") or str(x["time"])[:10]) <= day
        ]
        basis = fifo(prefix)
        capital = (
            None
            if initial is None
            else initial
            + sum((D(str(f["amount_USD"])) for f in flows if day_of(f["observed_at"]) <= day), D(0))
        )
        missing = []
        marks = {}
        for symbol, quantity in basis["quantity"].items():
            if not quantity:
                continue
            if (symbol, day) not in prices:
                missing.append("Missing raw daily close: " + symbol)
            else:
                marks[symbol] = prices[(symbol, day)]
        for event in unit_events:
            if start <= date.fromisoformat(event["day"]) <= day:
                before = [
                    x for x in prefix if str(x.get("session") or x["time"][:10]) < event["day"]
                ]
                if before and fifo(before)["quantity"].get(event["symbol"], D(0)):
                    missing.append(
                        "Held corporate action needs verified unit/basis bridge: "
                        + event["symbol"]
                        + ":"
                        + event["kind"]
                    )
        value = (
            None
            if missing
            else sum((q * marks[s]["price"] for s, q in basis["quantity"].items() if q), D(0))
        )
        pnl = None if value is None else value + basis["sales"] - basis["buys"]
        cash = None if capital is None else capital + basis["sales"] - basis["buys"]
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
                quantity=basis["quantity"],
                marks=marks,
                realized_fifo_usd=basis["realized"],
                remaining_fifo_cost_usd=sum(basis["cost"].values(), D(0)),
                valuation="reconstructed_from_owned_executions_and_raw_close",
                missing=missing,
            )
        )
    return dict(
        id=identity,
        label=label,
        kind="trading_component",
        first_fill=str(start),
        initial_allocation_usd=initial,
        allocation_flows=flows,
        execution_count=len(executions),
        execution_basis=sorted({x.get("basis", "unknown") for x in executions}),
        net_status="Actual attributable fees/income/settlement not completely received",
        points=points,
    )


def aggregate_parent(identity, children, histories):
    rows = [next(x for x in histories if x["id"] == child) for child in children]
    days = sorted({p["day"] for row in rows for p in row["points"]})
    points = []
    fields = (
        "capital_usd",
        "cash_from_principal_usd",
        "holdings_value_usd",
        "nav_before_unverified_items_usd",
        "trading_pnl_usd",
    )
    for day in days:
        members = [next((p for p in row["points"] if p["day"] == day), None) for row in rows]
        # No carry before a child's supported first fill; parent remains incomplete.
        point = {
            field: sum((m[field] for m in members), D(0))
            if all(m is not None and m[field] is not None for m in members)
            else None
            for field in fields
        }
        point.update(
            day=day,
            tracking_return_pct=None
            if point["trading_pnl_usd"] is None or not point["capital_usd"]
            else point["trading_pnl_usd"] / point["capital_usd"] * 100,
            net_pnl_usd=None,
            valuation="sum_of_same_date_separately_funded_children_once",
            missing=[]
            if all(m and not m.get("missing") for m in members)
            else ["Missing child/date valuation; no stale carry"],
        )
        points.append(point)
    return dict(
        id=identity,
        label=identity,
        kind="composite_parent",
        children=children,
        capital_counts_children_once=True,
        points=points,
    )


def account_observations(root, consumed, end):
    result = []
    # Genuine canonical daily records remain separate from missing-plan account observations.
    for alias in ("quant1", "quant2"):
        points = []
        directory = root / "reports/paper/book" / alias
        for path in sorted((directory / "daily").glob("????-??-??.json")):
            row = read(path, consumed)
            pnl = row.get("pnl", {})
            if pnl.get("equity") is not None and date.fromisoformat(row["execution_date"]) <= end:
                points.append(
                    dict(
                        day=row["execution_date"],
                        at=row.get("generated_at_utc"),
                        equity_usd=pnl["equity"],
                        source=str(path),
                        valuation="original_canonical_daily_account_observation",
                        net_pnl_usd=None,
                    )
                )
        for path in sorted((directory / "account-valuations").glob("*.json")):
            row = read(path, consumed)
            account = row["account"]
            if day_of(row["observed_at_UTC"]) > end:
                continue
            if row.get("account_alias") != alias or row.get("readonly") is not True:
                raise ValueError("account observation binding mismatch")
            residual = (
                D(str(account["equity"]))
                - D(str(account["cash"]))
                - D(str(account["long_market_value"]))
                - D(str(account["short_market_value"]))
            )
            points.append(
                dict(
                    day=str(day_of(row["observed_at_UTC"])),
                    at=row["observed_at_UTC"],
                    equity_usd=D(str(account["equity"])),
                    cash_usd=D(str(account["cash"])),
                    positions_value_usd=D(str(account["long_market_value"]))
                    + D(str(account["short_market_value"])),
                    equity_identity_residual_usd=residual,
                    source=str(path),
                    valuation="original_account_observation_without_strategy_plan",
                    net_pnl_usd=None,
                )
            )
        result.append(
            dict(
                id="account/" + alias,
                label=alias + " account observations",
                kind="account",
                points=points,
                identity_basis=(
                    "original account alias receipt; daily/valuation is not proof "
                    "of current strategy operation"
                ),
            )
        )
    return result


def bound_json(root, binding, consumed):
    path = Path(binding["path"]).resolve()
    if not path.is_relative_to((root / "reports").resolve()):
        raise ValueError("recovery evidence outside reports")
    data = read(path, consumed)
    actual = consumed[str(path)]
    if actual["bytes"] != binding["bytes"] or actual["sha256"] != binding["sha256"]:
        raise ValueError("recovery evidence binding changed")
    return data


def activity_signature(row):
    """Compare the actual economics across overlapping decoded/wire captures."""
    result = dict(row)
    for key in ("qty", "cum_qty", "leaves_qty", "price", "net_amount"):
        if result.get(key) is not None:
            result[key] = str(D(str(result[key])).normalize())
    return result


def receive_activities(root, index, identity, consumed, page):
    coverage = index["objects"].get("activities", {})
    acquisitions = coverage.get("acquisitions", [])
    complete = coverage.get("complete") is True and bool(acquisitions)
    by_id = {}
    intervals = []

    def add(rows):
        for row in rows:
            previous = by_id.get(row["id"])
            if previous and activity_signature(previous) != activity_signature(row):
                raise ValueError("activity ID revision needs explicit reconciliation")
            by_id[row["id"]] = row

    prefix = index["objects"].get("saved_activity_prefix")
    if prefix:
        bindings = {Path(x["path"]).name: x for x in prefix["bindings"]}
        for binding in bindings.values():
            bound_json(root, binding, consumed)
        if prefix.get("account_hash") != identity:
            raise ValueError("saved activity prefix belongs to another account")
        if "000-body.json" in bindings:
            # The original F1 reader retained wire/account IDs and one complete
            # all-type page for its middle interval, unlike the six SDK prefix.
            account = bound_json(root, bindings["000-body.json"], consumed)
            if hashlib.sha256(str(account["id"]).encode()).hexdigest() != identity:
                raise ValueError("saved F1 identity mismatch")
            receipt = bound_json(root, bindings["005-response.json"], consumed)
            request = bound_json(root, bindings["005-request.json"], consumed)
            rows = bound_json(root, receipt["body"], consumed)
            params = request["params"]
            if (
                request != receipt["request"]
                or receipt.get("status_code") != 200
                or request.get("method") != "GET"
                or request.get("path") != "/v2/account/activities"
                or params.get("activity_types")
                or params.get("category")
                or params.get("direction") != "asc"
                or params.get("page_token")
                or len(rows) != prefix["rows"]
                or len(rows) >= 100
                or not prefix.get("all_types")
                or not prefix.get("terminal")
            ):
                raise ValueError("saved F1 activity middle interval invalid")
            intervals.append((stamp(params["after"]), stamp(params["until"])))
            add(rows)
        else:
            account = bound_json(root, bindings["account-after.body.json"], consumed)
            if account.get("account_hash") != identity:
                raise ValueError("saved six identity mismatch")
        if "account-after.body.json" in bindings:
            receive_six_prefix(root, prefix, bindings, consumed, intervals, add)

    for acquisition in acquisitions:
        pages = acquisition.get("pages", [])
        complete = complete and acquisition.get("complete") is True and bool(pages)
        previous = None
        for entry in pages:
            receipt, rows = page(entry["receipt"], identity)
            params = receipt["request"]["params"]
            lo, hi = acquisition["creation_time_interval"]
            if (
                receipt["request"].get("endpoint")
                != "https://paper-api.alpaca.markets/v2/account/activities"
                or params.get("activity_types")
                or params.get("category")
                or params.get("direction") != "asc"
                or params.get("after") != lo
                or params.get("until") != hi
                or params.get("page_token") != previous
            ):
                raise ValueError("all-type activity interval or cursor mismatch")
            add(rows)
            previous = rows[-1]["id"] if rows else previous
        complete = complete and bool(pages) and pages[-1].get("terminal") is True
        intervals.append(tuple(stamp(x) for x in acquisition["creation_time_interval"]))
    # Multiple saved and new acquisition intervals must cover the entire
    # requested creation-time window. An empty terminal page can be evidence.
    cursor = stamp(index["source_interval"][0])
    for lo, hi in sorted(intervals):
        if lo > cursor:
            complete = False
        cursor = max(cursor, hi)
    cutoff = coverage.get("actual_entry_cutoff")
    complete = complete and bool(cutoff) and cursor >= stamp(cutoff)
    return list(by_id.values()), complete


def receive_six_prefix(root, prefix, bindings, consumed, intervals, add):
    previous, start = None, None
    for number, expected_size in enumerate(prefix["page_lengths"]):
        receipt = bound_json(root, bindings[f"activities-{number}.receipt.json"], consumed)
        intent = bound_json(root, receipt["intent"], consumed)
        rows = bound_json(root, receipt["body"], consumed)
        endpoint, params = intent["args"]
        if (
            intent.get("method") != "get"
            or endpoint != "/account/activities"
            or params.get("activity_types")
            or params.get("category")
            or params.get("direction") != "asc"
            or params.get("page_token") != previous
            or len(rows) != expected_size
        ):
            raise ValueError("saved all-type activity prefix cursor mismatch")
        start = params["after"] if start is None else start
        if params["after"] != start:
            raise ValueError("saved activity prefix interval changed")
        previous = rows[-1]["id"] if rows else previous
        add(rows)
    if not prefix.get("all_types") or not prefix.get("terminal") or expected_size >= 100:
        raise ValueError("saved activity prefix is not terminal all-type coverage")
    intervals.append((stamp(start), stamp(prefix["new_after"])))


def receive_saved_market(root, plan, consumed):
    result = []
    for group in plan.get("reuse", []):
        previous = None
        for entry in group["pages"]:
            metadata = bound_json(root, entry["metadata"], consumed)
            body = bound_json(root, entry["raw"], consumed)
            if (
                metadata.get("status_code") != 200
                or metadata["params"].get("page_token") != previous
            ):
                raise ValueError("saved market pagination changed")
            if metadata.get("response") and metadata["response"] != entry["raw"]:
                raise ValueError("saved market raw response binding differs")
            if metadata.get("capture_context"):
                bound_json(root, metadata["capture_context"], consumed)
            result.append(
                (
                    dict(
                        request=dict(params=metadata["params"]),
                        received_at=metadata["received_at"],
                        body=entry["raw"],
                    ),
                    body,
                )
            )
            previous = body.get("next_page_token")
        if previous is not None:
            raise ValueError("saved market page chain is not terminal")
    return result


def portfolio_points(history, receipt, identity, end):
    points = []
    for tick, value in zip(history["timestamp"], history["equity"], strict=True):
        if value is None:
            continue
        at = datetime.fromtimestamp(tick, UTC)
        day = at.astimezone(NEW_YORK).date()
        if day > end or not us_equity_session_dates(day, day):
            continue
        points.append(
            dict(
                day=str(day),
                at=at.isoformat(),
                equity_usd=D(str(value)),
                source=receipt["body"]["path"],
                account_hash=identity,
                valuation="recovered_broker_1D_account_equity",
                net_pnl_usd=None,
                request_received_at=receipt["received_at"],
            )
        )
    return points


def quarantine_reviewed_NY26_tail(alias, history, receipt, points):
    """Quarantine three exact unsupported source objects, never losses generally."""
    if receipt["body"]["sha256"] != NY26_UNSUPPORTED_TAILS.get(alias):
        return points
    assert history["timestamp"] == [1793059200]
    assert history["equity"] == [0]
    assert D(str(history["profit_loss"][0])) == -D(str(history["base_value"]))
    assert history["profit_loss_pct"] == [-1]
    assert len(points) == 1 and points[0]["day"] == "2026-10-26"
    return [
        {
            **points[0],
            "equity_usd": None,
            "raw_equity_usd": history["equity"][0],
            "raw_profit_loss_usd": history["profit_loss"][0],
            "raw_profit_loss_pct": history["profit_loss_pct"][0],
            "separate_tail_base_value_usd": history["base_value"],
            "valuation": "quarantined_specific_unsupported_official_NY26_zero",
            "source_body_sha256": receipt["body"]["sha256"],
            "missing": [
                "Exact official NY26 zero/-100% source conflicts with received cash/positions "
                "and activity evidence; provider cause UNKNOWN. Raw source retained; "
                "no zero NAV, current-mark substitution or carry."
            ],
        }
    ]


def f1_order_ownership(root, index, identity, activities, consumed, page):
    retained = {}
    plan_mismatches = []
    probes = {}
    directory = root / "reports/paper/book/quant1"
    for path in sorted((directory / "orders").glob("????-??-??.json")):
        record = read(path, consumed)
        daily = read(directory / "daily" / path.name, consumed)
        if daily["account"] != "quant1":
            raise ValueError("F1 original account alias mismatch")
        if record["plan_sha256"] != daily["plan_sha256"]:
            plan_mismatches.append(
                dict(
                    day=path.stem,
                    submitted_plan_sha256=record["plan_sha256"],
                    canonical_daily_plan_sha256=daily["plan_sha256"],
                )
            )
        for row in record["sent"]:
            retained[row["broker_order_id"]] = row["client_order_id"]
    for path in sorted((directory / "probes").glob("*.jsonl")):
        raw = path.read_bytes()
        consumed[str(path)] = dict(
            path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()
        )
        for line in raw.decode().splitlines():
            row = json.loads(line)
            order = row.get("order") or {}
            if (
                row.get("account") == "quant1"
                and order.get("id")
                and order.get("client_order_id") == row.get("client_order_id")
            ):
                probes[order["id"]] = order["client_order_id"]
    coverage = index["objects"]["orders"]
    actual, intervals = {}, []
    for acquisition in coverage["acquisitions"]:
        lo, hi = acquisition["interval"]
        previous = None
        pages = acquisition["pages"]
        for entry in pages:
            receipt, rows = page(entry["receipt"], identity)
            request = receipt["request"]
            params = request["params"]
            if (
                request["endpoint"] != "https://paper-api.alpaca.markets/v2/orders"
                or params.get("status") != "all"
                or params.get("direction") != "desc"
                or (previous is None and (params.get("after"), params.get("until")) != (lo, hi))
                or (
                    previous is not None
                    and (
                        params.get("before_order_id") != previous
                        or params.get("after")
                        or params.get("until")
                    )
                )
            ):
                raise ValueError("F1 order interval/cursor changed")
            for row in rows:
                if stamp(lo) < stamp(row["submitted_at"]) < stamp(hi):
                    prior = actual.get(row["id"])
                    if prior and prior != row:
                        raise ValueError("F1 order revision across retained pages")
                    actual[row["id"]] = row
            previous = rows[-1]["id"] if rows else previous
        if not acquisition.get("complete") or not pages[-1].get("terminal"):
            raise ValueError("F1 order pages incomplete")
        if len(rows) >= 500 and not any(stamp(r["submitted_at"]) <= stamp(lo) for r in rows):
            raise ValueError("F1 order page ended without terminal boundary")
        intervals.append((stamp(lo), stamp(hi)))
    middle = coverage.get("saved_middle_interval")
    if middle:
        bindings = {Path(x["path"]).name: x for x in middle["bindings"]}
        for binding in bindings.values():
            bound_json(root, binding, consumed)
        account = bound_json(root, bindings["000-body.json"], consumed)
        response = bound_json(root, bindings["003-response.json"], consumed)
        request = bound_json(root, bindings["003-request.json"], consumed)
        rows = bound_json(root, response["body"], consumed)
        params = request["params"]
        if (
            hashlib.sha256(str(account["id"]).encode()).hexdigest() != identity
            or response["request"] != request
            or response.get("status_code") != 200
            or request.get("path") != "/v2/orders"
            or params.get("status") != "all"
            or rows != []
            or middle.get("rows") != 0
            or not middle.get("terminal")
        ):
            raise ValueError("F1 saved empty order interval changed")
        intervals.append((stamp(params["after"]), stamp(params["until"])))
    cursor = stamp(index["source_interval"][0])
    for lo, hi in sorted(intervals):
        if lo > cursor:
            raise ValueError("F1 order coverage gap")
        cursor = max(cursor, hi)
    if cursor < stamp(index["source_interval"][1]):
        raise ValueError("F1 order coverage ends early")
    fills = [row for row in activities if row["activity_type"] == "FILL"]
    orders = {row["order_id"] for row in fills}
    mismatches = [
        order
        for order in orders
        if order in retained
        and (order not in actual or actual[order]["client_order_id"] != retained[order])
    ]
    if mismatches:
        raise ValueError("F1 filled order/client identity differs from original receipts")
    probe_ids = orders & probes.keys()
    for order in probe_ids:
        if order not in actual or actual[order]["client_order_id"] != probes[order]:
            raise ValueError("F1 actual probe order identity mismatch")
    probe_executions = [
        dict(
            id=row["id"],
            order_id=row["order_id"],
            symbol=row["symbol"],
            side=row["side"],
            quantity=D(str(row["qty"])),
            price=D(str(row["price"])),
            time=row["transaction_time"],
        )
        for row in fills
        if row["order_id"] in probe_ids
    ]
    probe_basis = fifo(probe_executions)
    return dict(
        complete_order_interval=True,
        retained_native_order_count=len(retained),
        recovered_order_count=len(actual),
        distinct_filled_order_count=len(orders),
        individual_FILL_count=len(fills),
        first_native_strategy_FILL_at=min(
            (row["transaction_time"] for row in fills if row["order_id"] in retained), default=None
        ),
        canonical_daily_vs_submitted_plan_mismatches=plan_mismatches,
        canonical_strategy_attribution_complete=not plan_mismatches,
        saved_probe_order_ids=sorted(probe_ids),
        probe_executions=probe_executions,
        probe_realized_trading_pnl_before_fees_usd=probe_basis["realized"],
        probe_remaining_quantities=probe_basis["quantity"],
        filled_orders_without_original_strategy_or_probe_receipt=sorted(
            orders - retained.keys() - probe_ids
        ),
        ownership_basis=(
            "Exact original plan/order receipt and recovered broker order/client IDs; "
            "no CID-prefix inference"
        ),
    )


def recovered_evidence(root, consumed, end):
    """Receive the original operator's closed local receipts, never GET again."""
    directory = (
        root
        / "reports/paper/diagnostics/fresh-dashboard-owner-audit-20261027"
        / "history-v1/recovered-evidence"
    )
    result = {
        "accounts": {},
        "market": [],
        "pending": [],
        "saved_six_activities": [],
        "native_outcome": None,
        "quarantined_account_points": [],
    }
    prefix_path = directory / "saved-native-six-activity-prefix.json"
    if prefix_path.exists():
        prefix = read(prefix_path, consumed)
        result["saved_six_activities"], _ = receive_activities(
            root,
            dict(
                source_interval=["2026-10-19T00:00:00Z", "2026-10-26T23:59:59Z"],
                objects=dict(saved_activity_prefix=prefix),
            ),
            SIX_ACCOUNT,
            consumed,
            lambda *_: None,  # This saved-prefix-only branch cannot fetch a page.
        )
    started = directory / "run.started.json"
    if not started.exists():
        saved_plan = directory / "saved-coverage-and-missing-market-plan-M2.json"
        if saved_plan.exists():
            result["market"] += receive_saved_market(root, read(saved_plan, consumed), consumed)
        result["pending"].append("Original historical collector has not published a native start")
        return result
    config = bound_json(root, read(started, consumed)["config"], consumed)
    outcome = read(directory / "actual-outcome.json", consumed)
    if outcome.get("complete") is not True:
        result["pending"].append("Original recovery has no successful whole-route terminal")
    for account in outcome.get("accounts", []):
        bound_json(root, account["coverage"], consumed)
    if outcome.get("market"):
        bound_json(root, outcome["market"]["coverage"], consumed)
    result["native_outcome"] = {
        k: outcome.get(k)
        for k in ("started_at", "completed_at", "complete", "physical_GET_attempts", "errors")
    }
    expected = {x["alias"]: x["account_hash"] for x in config["accounts"]}
    plan = bound_json(root, config["market_plan"], consumed)
    result["market"] += receive_saved_market(root, plan, consumed)

    def page(binding, identity):
        receipt = bound_json(root, binding, consumed)
        request = receipt["request"]
        if (
            receipt.get("status_code") != 200
            or receipt.get("complete") is not True
            or request.get("method") != "GET"
            or request.get("identity") != identity
        ):
            raise ValueError("incomplete or wrong-identity recovery receipt")
        body = bound_json(root, receipt["body"], consumed)
        return receipt, body

    for alias in ("legacy", "six", "F1"):
        path = directory / "accounts" / (alias + ".json")
        if not path.exists():
            result["pending"].append(alias + ": account coverage index not yet published")
            continue
        index = read(path, consumed)
        identity = expected[alias]
        if index.get("account_hash") != identity or index.get("alias") != alias:
            raise ValueError("account recovery identity changed")
        identity_receipt, account = page(index["identity"]["receipt"], identity)
        if (
            identity_receipt["request"].get("endpoint")
            != "https://paper-api.alpaca.markets/v2/account"
            or hashlib.sha256(str(account["id"]).encode()).hexdigest() != identity
            or account.get("currency") != "USD"
        ):
            raise ValueError("account body identity or currency mismatch")
        positions_receipt, positions = page(index["objects"]["positions"]["receipt"], identity)
        history_receipt, history = page(index["objects"]["portfolio_history"]["receipt"], identity)
        if (
            positions_receipt["request"].get("endpoint")
            != "https://paper-api.alpaca.markets/v2/positions"
            or history_receipt["request"].get("endpoint")
            != "https://paper-api.alpaca.markets/v2/account/portfolio/history"
            or history_receipt["request"]["params"].get("timeframe") != "1D"
            or history_receipt["request"]["params"].get("cashflow_types") != "ALL"
            or history.get("timeframe") != "1D"
            or len(history["timestamp"]) != len(history["equity"])
        ):
            raise ValueError("daily account history arrays/timeframe invalid")
        points = portfolio_points(history, history_receipt, identity, end)
        activities, complete = receive_activities(root, index, identity, consumed, page)
        order_ownership = (
            f1_order_ownership(root, index, identity, activities, consumed, page)
            if alias == "F1"
            else None
        )
        if order_ownership and order_ownership["first_native_strategy_FILL_at"]:
            before = [
                point
                for point in points
                if stamp(point["at"]) < stamp(order_ownership["first_native_strategy_FILL_at"])
            ]
            if before:
                baseline = before[-1]
                order_ownership["last_account_observation_before_first_native_FILL"] = baseline
                order_ownership["current_account_observation_change_from_that_baseline_usd"] = (
                    D(str(account["equity"])) - baseline["equity_usd"]
                )
        flows = []
        ambiguous = []
        for row in activities:
            kind = row.get("activity_type")
            if kind != "FILL" and row.get("status") != "executed":
                ambiguous.append(row["id"])
                continue
            if kind in {"CSD", "CSW", "ACATC"}:
                flows.append(
                    dict(
                        id=row["id"],
                        day=str(row.get("date"))[:10],
                        at=row.get("transaction_time"),
                        amount_usd=row["net_amount"],
                        kind=kind,
                    )
                )
            elif kind in {"JNLC", "JNL", "JNLS", "ACATS", "FOPT"}:
                ambiguous.append(row["id"])
        performance = account_performance(
            points, flows, flow_coverage_complete=complete and not ambiguous
        )
        for number, point in enumerate(points):
            if point.get("equity_usd") is None:
                continue
            prefix_performance = account_performance(
                points[: number + 1], flows, flow_coverage_complete=complete and not ambiguous
            )
            point["account_change_ex_external_flows_usd"] = prefix_performance.get(
                "net_change_ex_external_flows_usd"
            )
            point["account_return_pct"] = prefix_performance.get("return_pct")
        result["accounts"][alias] = dict(
            index=index,
            account_hash=identity,
            points=points,
            activities=activities,
            external_flows=flows,
            ambiguous_flow_ids=ambiguous,
            activity_coverage_complete=complete,
            performance=performance,
            current_account=dict(
                equity=account.get("equity"),
                cash=account.get("cash"),
                created_at=account.get("created_at"),
                long_market_value=account.get("long_market_value"),
                short_market_value=account.get("short_market_value"),
                observed_at=identity_receipt["received_at"],
            ),
            fee_income_statement_status=index.get("statements_confirmations"),
            positions=positions,
            positions_observed_at=positions_receipt["received_at"],
            portfolio_base_value=history.get("base_value"),
            order_ownership=order_ownership,
        )
    market_path = directory / "market-coverage.json"
    if market_path.exists():
        market = read(market_path, consumed)
        if market["saved_plan"] != config["market_plan"]:
            raise ValueError("market coverage differs from entered saved plan")
        for group in market.get("fetched_groups", []):
            if group.get("complete") is not True or not group["pages"][-1].get("terminal"):
                raise ValueError("market page coverage incomplete")
            previous = None
            for entry in group["pages"]:
                receipt, body = page(entry["receipt"], "configured_original_SIP")
                if receipt["request"]["params"].get("page_token") != previous:
                    raise ValueError("market cursor does not follow retained page")
                result["market"].append((receipt, body))
                previous = body.get("next_page_token")
            if previous is not None:
                raise ValueError("market terminal token not exhausted")
    else:
        result["pending"].append("Missing-market coverage not yet published")
    handoff_path = directory / "complete-operator-evidence-handoff.json"
    if handoff_path.exists():
        handoff = read(handoff_path, consumed)
        assert (
            consumed[str(handoff_path)]["sha256"]
            == "ae64ba05ab50e76bfdb1fb0b8c1145b3d211cf89bc7346aa75f0c221efeece76"
        )
        bound_json(root, handoff["tail_outcome"], consumed)
        bound_json(root, handoff["accepted_original_and_tail_scope"], consumed)
        for entry in handoff["accounts"]:
            alias = entry["alias"]
            assert entry["account_hash"] == expected[alias]
            receipt, body = page(entry["receipt"], expected[alias])
            assert receipt["body"] == entry["body"]
            assert (
                receipt["request"]["endpoint"]
                == "https://paper-api.alpaca.markets/v2/account/portfolio/history"
            )
            assert receipt["request"]["params"]["timeframe"] == "1D"
            points = portfolio_points(body, receipt, expected[alias], end)
            points = quarantine_reviewed_NY26_tail(alias, body, receipt, points)
            assert all(point["equity_usd"] is None for point in points)
            result["accounts"][alias]["points"] += points
            result["quarantined_account_points"] += [
                dict(account=alias, **point) for point in points
            ]
    return result


def receive_full_fills(executions, activities):
    """Prefer individual fills once complete; never add them to their summary."""
    by_order = defaultdict(list)
    for row in activities:
        if row.get("activity_type") == "FILL":
            by_order[row["order_id"]].append(row)
    result = []
    for event in executions:
        rows = by_order.get(event["order_id"], [])
        total = sum((D(str(row["qty"])) for row in rows), D(0))
        if rows and total == event["quantity"]:
            for row in rows:
                if row["symbol"] != event["symbol"] or row["side"] != event["side"]:
                    raise ValueError("FILL attribution differs from retained owning order")
                result.append(
                    dict(
                        id=row["id"],
                        order_id=row["order_id"],
                        symbol=row["symbol"],
                        side=row["side"],
                        quantity=D(str(row["qty"])),
                        price=D(str(row["price"])),
                        time=row["transaction_time"],
                        session=str(day_of(row["transaction_time"])),
                        basis="recovered_broker_individual_FILL",
                    )
                )
        elif rows and total != event["quantity"]:
            raise ValueError("recovered individual fills differ from retained cumulative quantity")
        else:
            result.append(event)
    return result


def recovered_account_reconciliation(received):
    """Receive actual account identities without inventing an opening cash balance.

    The signed fill identity supports long and short positions equally. An
    implied opening cash balance is a reconciliation result, not a funding
    certificate, and unallocated nontrade entries remain account-level items.
    """
    quantities = defaultdict(lambda: D(0))
    recorded_units = defaultdict(lambda: D(0))
    unit_rows = []
    principal = D(0)
    nontrade = D(0)
    nontrade_unverified_cash = []
    fill_count = 0
    for row in received["activities"]:
        if row["activity_type"] == "FILL":
            side = row["side"]
            if side not in {"buy", "sell", "sell_short", "buy_to_cover"}:
                raise ValueError("unknown FILL side")
            quantity, price = D(str(row["qty"])), D(str(row["price"]))
            sign = D(1) if side in {"buy", "buy_to_cover"} else D(-1)
            quantities[row["symbol"]] += sign * quantity
            principal -= sign * quantity * price
            fill_count += 1
        elif row.get("net_amount") is not None and row.get("status") == "executed":
            nontrade += D(str(row["net_amount"]))
        else:
            nontrade_unverified_cash.append(
                dict(id=row["id"], kind=row["activity_type"], status=row.get("status"))
            )
        if (
            row["activity_type"] == "MA"
            and row.get("status") == "executed"
            and row.get("qty") is not None
            and row.get("symbol")
        ):
            # The observed signed MA entries remove the exact acquired long/
            # short holdings. Their separate net_amount entries supply cash;
            # qty*price is never added as another trade or cash posting.
            recorded_units[row["symbol"]] += D(str(row["qty"]))
            unit_rows.append(
                {
                    k: row.get(k)
                    for k in ("id", "activity_type", "date", "symbol", "qty", "net_amount")
                }
            )
    actual = {row["symbol"]: D(str(row["qty"])) for row in received["positions"]}
    account = received["current_account"]
    market_value = sum((D(str(row["market_value"])) for row in received["positions"]), D(0))
    cash, equity = D(str(account["cash"])), D(str(account["equity"]))
    return dict(
        account_hash=received["account_hash"],
        observed_at=account["observed_at"],
        positions_observed_at=received["positions_observed_at"],
        account_created_at=account["created_at"],
        individual_fill_count=fill_count,
        position_count=len(actual),
        quantity_mismatches={
            symbol: dict(
                signed_fills=quantities[symbol],
                posted_MA_units=recorded_units[symbol],
                actual_positions=actual.get(symbol, D(0)),
            )
            for symbol in set(quantities) | set(actual) | set(recorded_units)
            if quantities[symbol] + recorded_units[symbol] != actual.get(symbol, D(0))
        },
        quantity_mismatches_before_recorded_MA={
            symbol: dict(signed_fills=quantities[symbol], actual_positions=actual.get(symbol, D(0)))
            for symbol in set(quantities) | set(actual)
            if quantities[symbol] != actual.get(symbol, D(0))
        },
        observed_signed_MA_quantity_entries=unit_rows,
        actual_cash_usd=cash,
        actual_equity_usd=equity,
        actual_positions_market_value_usd=market_value,
        account_equity_identity_residual_usd=equity - cash - market_value,
        fill_principal_cash_change_usd=principal,
        nontrade_signed_cash_change_usd=nontrade,
        implied_opening_cash_usd=cash - principal - nontrade,
        opening_cash_status=(
            "implied by observed cash and retained activity interval; not a funding certificate"
        ),
        reported_portfolio_history_base_value=received["portfolio_base_value"],
        activity_coverage_complete=received["activity_coverage_complete"],
        nontrade_unverified_cash_effect=nontrade_unverified_cash,
    )


def build(root, frozen_state, activities, end, captured_inputs=None):
    consumed = {}
    state = read(frozen_state, consumed)
    acts = read(activities, consumed)
    recovered = recovered_evidence(root, consumed, end)
    new_fills = recovered["saved_six_activities"] + recovered["accounts"].get("six", {}).get(
        "activities", []
    )
    by_id = {x["id"]: x for x in acts["activities"]}
    for row in new_fills:
        if row.get("activity_type") != "FILL" or day_of(row["transaction_time"]) > end:
            continue
        if row["id"] in by_id:
            previous = by_id[row["id"]]
            assert all(
                previous[k] == row[k] for k in ("order_id", "symbol", "side", "transaction_time")
            )
            assert all(D(str(previous[k])) == D(str(row[k])) for k in ("qty", "price"))
        else:
            by_id[row["id"]] = row
    acts = {**acts, "activities": list(by_id.values())}
    performance = project(root, state, acts, generated_at=datetime.now(UTC).isoformat())
    for binding in performance["consumed_bindings"]:
        consumed[binding["path"]] = binding
    six_nontrade = {}
    for row in new_fills:
        if row.get("activity_type") != "FILL":
            six_nontrade[row["id"]] = row
    six_signed_nontrade = sum(
        (
            D(str(row["net_amount"]))
            for row in six_nontrade.values()
            if row.get("net_amount") is not None and row.get("status") == "executed"
        ),
        D(0),
    )
    six_nontrade_by_type = defaultdict(lambda: D(0))
    for row in six_nontrade.values():
        if row.get("net_amount") is not None and row.get("status") == "executed":
            six_nontrade_by_type[row["activity_type"]] += D(str(row["net_amount"]))
    prices, revisions, unit_events = raw_sources(root, consumed, recovered["market"])
    histories, duplicates = [], []
    for name, (label, budget) in LEGACY.items():
        path = (
            captured_inputs / "fills" if captured_inputs else root / "reports/paper/rehearsal"
        ) / (name + "-fills.jsonl")
        if not path.exists():
            continue
        spec_path = (
            captured_inputs / "specs" if captured_inputs else root / "strategy_specs/drafts"
        ) / (name + ".yaml")
        spec = spec_path.read_bytes()
        consumed[str(spec_path)] = dict(
            path=str(spec_path), bytes=len(spec), sha256=hashlib.sha256(spec).hexdigest()
        )
        if budget is not None:
            match = re.search(r"^\s*notional_budget_usd:\s*([0-9_.]+)", spec.decode(), re.M)
            if match is None or D(match[1].replace("_", "")) != budget:
                raise ValueError("retained sleeve allocation differs from reviewed budget")
        executions, conflicts = legacy_executions(path, consumed)
        executions = receive_full_fills(
            executions, recovered["accounts"].get("legacy", {}).get("activities", [])
        )
        history = historical_book(
            "legacy/" + name, label, executions, budget, [], prices, end, unit_events
        )
        history.update(
            account_hash=OLD_ACCOUNT, retired=name == "us_recent_high_return_top50", label=label
        )
        histories.append(history)
        duplicates += conflicts
    for name, book in state["books"].items():
        evidence = book["evidence"]
        histories.append(
            historical_book(
                "six/" + name,
                name,
                performance["executions"][name],
                D(str(evidence["risk"]["initial_capital"])),
                evidence.get("allocation_flows", []),
                prices,
                end,
                unit_events,
            )
        )
        histories[-1].update(
            account_hash=state["account"]["account_hash"],
            recorded_fee_entries=book["fees"],
            recorded_income_receivables=book["cashbook"]["dividends"],
            unresolved_settlement_reservations=len(book["pending"]),
            fee_income_statement_complete=False,
        )
    for parent in ("MULTI_EQUAL", "MULTI_HIERARCHICAL"):
        children = ["six/" + n for n in state["books"] if n.startswith(parent + "/")]
        histories.append(aggregate_parent("six/" + parent, children, histories))
    histories += account_observations(root, consumed, end)
    recovery_summary = {}
    for alias, received in recovered["accounts"].items():
        entity = "quant1" if alias == "F1" else alias
        histories.append(
            dict(
                id="account/" + entity + "/broker-daily",
                label=entity + " recovered broker daily account",
                kind="account",
                account_hash=received["account_hash"],
                points=received["points"],
                performance=received["performance"],
                external_flows=received["external_flows"],
                activity_coverage_complete=received["activity_coverage_complete"],
                order_ownership=received["order_ownership"],
            )
        )
        amounts = defaultdict(lambda: D(0))
        for activity in received["activities"]:
            if activity.get("net_amount") is not None and activity.get("status") == "executed":
                amounts[activity["activity_type"]] += D(str(activity["net_amount"]))
        recovery_summary[alias] = dict(
            account_hash=received["account_hash"],
            activity_count=len(received["activities"]),
            activity_coverage_complete=received["activity_coverage_complete"],
            nontrade_signed_amounts_by_type=dict(amounts),
            ambiguous_flow_ids=received["ambiguous_flow_ids"],
            fee_income_statement_status=received["fee_income_statement_status"],
            current_account=received["current_account"],
            performance=received["performance"],
            reconciliation=recovered_account_reconciliation(received),
            order_ownership=received["order_ownership"],
        )

    # Retain every original account chart observation and its exact source path.
    audit_directory = root / "reports/paper/diagnostics/fresh-dashboard-owner-audit-20261027"
    old_points = read(audit_directory / "legacy-account-observations.json", consumed)
    history = []
    for day, (at, value, path) in old_points["days"].items():
        source = Path(path) if Path(path).is_absolute() else root / path
        if source.exists():
            read(source, consumed)
        history.append(
            dict(
                day=day,
                at=at,
                equity_usd=D(str(value)),
                source=path,
                valuation="original_account_snapshot",
                net_pnl_usd=None,
            )
        )
    histories.append(
        dict(
            id="account/legacy",
            label="Legacy account observations",
            kind="account",
            account_hash=OLD_ACCOUNT,
            points=history,
            original_missing_sessions=old_points["missing_sessions"],
        )
    )
    # Account identities are independent. Residuals stay explicit instead of
    # being silently allocated as fees, income, deposits or sleeve profit.
    legacy_positions = read(
        (captured_inputs or root / "reports/paper") / "positions.json", consumed
    )
    legacy_account = read((captured_inputs or root / "reports/paper") / "account.json", consumed)
    old_books = [h for h in histories if h["id"].startswith("legacy/")]
    expected_quantities = defaultdict(lambda: D(0))
    principal_delta = D(0)
    for h in old_books:
        if h["points"]:
            latest = h["points"][-1]
            principal_delta += latest["realized_fifo_usd"] - latest["remaining_fifo_cost_usd"]
            for symbol, quantity in latest["quantity"].items():
                expected_quantities[symbol] += quantity
    actual_quantities = {row["symbol"]: D(str(row["qty"])) for row in legacy_positions["positions"]}
    baseline_equity = D(str(old_points["first"][1]))
    expected_cash = baseline_equity + principal_delta
    legacy_nontrade = (
        recovery_summary.get("legacy", {})
        .get("reconciliation", {})
        .get("nontrade_signed_cash_change_usd")
    )
    six_principal = sum(
        (
            h["points"][-1]["realized_fifo_usd"] - h["points"][-1]["remaining_fifo_cost_usd"]
            for h in histories
            if h["id"].startswith("six/") and h["kind"] == "trading_component" and h["points"]
        ),
        D(0),
    )
    six_capital = sum((b["allocated_capital_usd"] for b in performance["books"].values()), D(0))
    six_opening = recovered["accounts"].get("six", {}).get("portfolio_base_value")
    account_checks = {
        "legacy": {
            "as_observed": legacy_account["generated_at"],
            "cash_if_only_retained_trades_since_first_observation": expected_cash,
            "actual_saved_cash": legacy_account["cash"],
            "trade_only_cash_difference_usd": D(str(legacy_account["cash"])) - expected_cash,
            "actual_posted_nontrade_amount_usd": legacy_nontrade,
            "unattributed_cash_residual_usd": None
            if legacy_nontrade is None
            else D(str(legacy_account["cash"])) - expected_cash - legacy_nontrade,
            "quantity_mismatches": {
                s: {
                    "retained_executions": expected_quantities[s],
                    "broker": actual_quantities.get(s, D(0)),
                }
                for s in set(expected_quantities) | set(actual_quantities)
                if expected_quantities[s] != actual_quantities.get(s, D(0))
            },
            "scope": (
                "All retained old-account contributors including retired top50; "
                "no assumed zero nontrade flow"
            ),
        },
        "six": {
            "as_observed": state["account"]["observed_at"],
            "recorded_allocated_capital": sum(
                (b["allocated_capital_usd"] for b in performance["books"].values()), D(0)
            ),
            "recorded_virtual_cash": sum(
                (b["recorded_book_economic_cash_usd"] for b in performance["books"].values()), D(0)
            ),
            "actual_broker_cash": state["account"]["cash"],
            "saved_nontrade_entries": [
                {
                    key: row.get(key)
                    for key in ("id", "activity_type", "date", "net_amount", "status")
                }
                for row in six_nontrade.values()
            ],
            "saved_signed_nontrade_amount_usd": six_signed_nontrade,
            "saved_posted_nontrade_by_type": dict(six_nontrade_by_type),
            "confirmed_execution_cash_in_allocated_books_usd": six_capital + six_principal,
            "inferred_unused_cash_from_reported_base_usd": None
            if six_opening is None
            else D(str(six_opening)) - six_capital,
            "cash_residual_after_confirmed_fills_and_posted_nontrade_usd": None
            if six_opening is None
            else D(str(state["account"]["cash"]))
            - D(str(six_opening))
            - six_principal
            - six_signed_nontrade,
            "implied_opening_cash_from_owned_fill_principal_and_saved_nontrade_usd": (
                D(str(state["account"]["cash"])) - six_principal - six_signed_nontrade
            ),
            "scope": (
                "16 primitive books only; composite parents not counted again; "
                "posted account-level nontrade amounts retained, not allocated to sleeves; "
                "opening cash and later-posting completeness remain qualified separately"
            ),
        },
    }
    coverage = []
    for h in histories:
        first = min((p["day"] for p in h["points"]), default=None)
        valid_days = {
            p["day"]
            for p in h["points"]
            if p.get("trading_pnl_usd", p.get("equity_usd")) is not None and not p.get("missing")
        }
        expected = us_equity_session_dates(date.fromisoformat(first), end) if first else []
        coverage.append(
            dict(
                id=h["id"],
                kind=h["kind"],
                first=first,
                last=max((p["day"] for p in h["points"]), default=None),
                observations=len(h["points"]),
                supported_values=len(valid_days),
                expected_sessions=len(expected),
                missing_days=[str(day) for day in expected if str(day) not in valid_days],
            )
        )
    return dict(
        schema_version=1,
        generated_at=datetime.now(UTC).isoformat(),
        through_session=str(end),
        histories=histories,
        coverage=coverage,
        raw_price_points=len(prices),
        raw_price_revisions=revisions,
        unit_events=unit_events,
        cumulative_order_revisions=duplicates,
        unattributed_six_FILL_ids=performance["unattributed_saved_FILL_ids"],
        original_snapshot_gaps_preserved=old_points["missing_sessions"],
        reconciliation=performance["quantity_reconciliation"],
        market_value_reconciliation=performance["market_value_reconciliation"],
        account_reconciliations=account_checks,
        source_bindings=list(consumed.values()),
        limits=[
            "No account or strategy fills/prices/fees/income are invented",
            "Raw-close component is distinct from original account equity snapshots",
            "Complete actual fees/income/flows and unit bridges govern net certification",
        ],
        broker_or_source_API_calls=0,
        recovery_summary=recovery_summary,
        recovery_pending=recovered["pending"],
        native_recovery_outcome=recovered["native_outcome"],
        quarantined_account_points=recovered["quarantined_account_points"],
        code_bindings=[
            dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            for path in (
                Path(__file__),
                Path(project.__code__.co_filename),
                Path(account_performance.__code__.co_filename),
                Path(us_equity_session_dates.__code__.co_filename),
            )
        ],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--activities", type=Path, required=True)
    parser.add_argument("--through", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--captured-inputs", type=Path)
    args = parser.parse_args()
    payload = build(args.root, args.state, args.activities, args.through, args.captured_inputs)
    with args.output.open("x") as handle:
        json.dump(payload, handle, indent=2, default=str, allow_nan=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
