"""Bounded, immutable account observations for the isolated initialization.

Uses the admitted gateway only. No key lookup, activation, submission or implicit
fee certification. SDK-decoded bodies are not represented as raw wire records.
"""

from __future__ import annotations

import copy
import hashlib
import time
from datetime import UTC, datetime
from decimal import Decimal

from open_composer.intraday_runner.current_initialization_controls import ACCOUNT, number
from open_composer.intraday_runner.source_dispatch_journal import (
    _hash,
)
from open_composer.intraday_runner.source_state_checkpoint import restore


def capture(runtime, directory, *, clock=lambda: datetime.now(UTC), monotonic=time.monotonic):
    """One complete fixed request chain. Saturated order pages refuse, not truncate."""
    save = runtime.save_capture
    runtime.prepare_capture(directory)
    started, mono = clock(), monotonic()
    client = runtime.gateway.client
    bodies = {}
    response_clocks = {}
    last_response = started

    def get(name, endpoint, params=None):
        nonlocal last_response
        if runtime.current_request is not None or runtime.current_response is not None:
            raise ValueError("nested account capture request")
        # The physical transport publishes this intent together with its own
        # prepared record before sending. Do not publish the same intent twice.
        runtime.current_request = dict(
            name=name,
            endpoint=endpoint,
            params=copy.deepcopy(params or {}),
            at=clock().isoformat(),
            monotonic=monotonic(),
        )
        sealed = False
        try:
            value = client.get(endpoint, params or {})
            last_response = clock()
            response_clocks[name] = last_response.isoformat()
            receipt = runtime.current_response
            if receipt is None or receipt["request"] != runtime.current_request:
                raise ValueError("SDK reply lacks exact captured transport metadata")
            if runtime.gateway.last_read_status != 200:
                raise ValueError("unreceived broker response")
            # Keep identity binding, never account number/credentials in a report.
            if endpoint == "/account":
                value = dict(value)
                actual_hash = hashlib.sha256(str(value.pop("id", "")).encode()).hexdigest()
                value.pop("account_number", None)
                value["account_hash"] = actual_hash
            bodies[name] = save(
                directory / f"{name}.json", dict(**receipt, decoded_body=value, usable=True)
            )
            sealed = True
            return value
        except Exception as exc:
            if runtime.current_response is not None and not sealed:
                save(
                    directory / f"{name}.unusable-response.json",
                    dict(
                        **runtime.current_response,
                        decoded_body=None,
                        error_type=type(exc).__name__,
                        usable=False,
                    ),
                )
            raise
        finally:
            runtime.current_request = None
            runtime.current_response = None

    account = get("account", "/account")
    if account.get("account_hash") != ACCOUNT:
        raise ValueError("replacement account identity changed")
    market_clock = get("market-clock", "/clock")
    positions = get("positions", "/positions")
    history = get(
        "orders",
        "/orders",
        dict(status="all", after=runtime.auth["reconciliation_after"], limit=500, direction="asc"),
    )
    opened = get("open-orders", "/orders", dict(status="open", limit=500, direction="asc"))
    if (
        not all(isinstance(x, list) for x in (positions, history, opened))
        or max(len(history), len(opened)) >= 500
    ):
        raise ValueError("order/position completeness not established")
    activities, token, seen = [], None, set()
    while True:
        params = dict(after=runtime.auth["reconciliation_after"], direction="asc", page_size=100)
        if token is not None:
            params["page_token"] = token
        page = get(f"activities-{len(seen):03d}", "/account/activities", params)
        if not isinstance(page, list):
            raise ValueError("activity schema")
        activities.extend(page)
        if len(page) < 100:
            break
        token = page[-1].get("id")
        if not token or token in seen:
            raise ValueError("nonprogressing activity chain")
        seen.add(token)
    assets = {}
    selected = set(runtime.required_symbols)
    selected.update(p["symbol"] for p in positions)
    for symbol in sorted(selected):
        asset = get("asset-" + symbol, "/assets/" + symbol)
        if asset.get("symbol") != symbol or asset.get("class") != "us_equity":
            raise ValueError("asset identity/class mismatch")
        assets[symbol] = asset
    current = runtime.store.load()
    state, fills, fees, evidence = restore(runtime.root, current["snapshot"])
    orders = {o["client_order_id"]: o for o in history}
    if len(orders) != len(history):
        raise ValueError("duplicate history identities")
    for row in opened:
        old = orders.get(row["client_order_id"])
        if old is not None and old != row:
            raise ValueError("order changed during observation; retained, not merged")
        orders[row["client_order_id"]] = row
    books = runtime.partition.books()
    view = runtime.partition.account_view(books, runtime.task, positions, orders, activities)
    aggregate_orders, aggregate_positions, aggregate_activities = orders, positions, activities
    orders, positions, activities = (
        view["own_orders"],
        view["own_positions"],
        view["own_activities"],
    )
    known_guard_refusals = {}
    for cid, pending in state.pending.items():
        if pending["side"] == "liability_hold":
            if cid not in evidence.get("terminal_liability_holds", {}):
                raise ValueError("terminal liability provenance missing")
            continue
        path = runtime.journal._path(cid)
        if (path.is_symlink() or path.exists()) and cid not in orders:
            from open_composer.intraday_runner.source_terminal_holds import (
                receive_not_dispatched_guard_refusal,
            )

            # Only the exact durable pre-submit refusal is distinguishable
            # from an unknown/missing broker order. Keep every reservation.
            known_guard_refusals[cid] = receive_not_dispatched_guard_refusal(
                state, fills, fees, evidence, cid=cid, journal=runtime.journal
            )
        elif cid not in orders:
            from open_composer.intraday_runner.source_terminal_holds import receive_never_attempted

            known_guard_refusals[cid] = receive_never_attempted(
                state, fills, fees, evidence, cid=cid, journal=runtime.journal
            )
    units_complete, holds = view["units_complete"], view["holdings"]
    # Unapplied or non-FILL activity is retained as a liability/control hold.
    known_ids = set(fills) | set(fees)
    activity_complete = view["all_activities_known"] and all(
        isinstance(x, dict) and x.get("id") in known_ids for x in activities
    )
    fee_complete = not fills and not activities and not orders
    if evidence.get("actual_fees_reconciled") is True:
        fee_complete = activity_complete
    purchases = sum(number(p["amount"]) for p in state.cashbook.purchases)
    sales = sum(number(s["amount"]) for s in state.cashbook.sales)
    cash = number(state.cashbook.cash)
    rights_complete = (
        not state.cashbook.dividends
        and evidence.get("actions_current") is True
        and evidence.get("actions_observation_day") == clock().astimezone(UTC).date().isoformat()
    )
    # The empty BASE funding predecessor retains its historical Oct19 evidence.
    # Receive today's real scientific action proof without mutating that book
    # before the authenticated funding predicate/append-only successor commits.
    package = getattr(runtime, "current_scientific_package", None)
    if package is not None and not positions and not state.cashbook.lots:
        from open_composer.intraday_runner.current_initialization_episode import (
            DAY,
            POLICIES,
            normalize_received,
        )

        component = package["received_scientific_component"]
        normalize_received(component, POLICIES[runtime.task])
        for key in ("review", "package", "source", "source_complete"):
            from open_composer.intraday_runner.source_method_bindings import bound_bytes

            bound_bytes(runtime.root, component[key])
        if component["review"] != runtime.auth["scientific_acceptance"]:
            raise ValueError("empty-book actions lack accepted current provenance")
        rights_complete = not state.cashbook.dividends and clock().date().isoformat() == DAY
    marked = sum(number(x["market_value"]) for x in holds)
    nav = cash + sales + marked - purchases
    baseline = number(evidence["account_initial_cash"])
    for book in books.values():
        if number(book["snapshot"]["evidence"]["account_initial_cash"]) != baseline:
            raise ValueError("different account cash baseline across sleeves")
    expected_account_cash = baseline - view["totals"]["allocated"] + view["totals"]["net_cash"]
    cash_complete = abs(number(account["cash"]) - expected_account_cash) <= Decimal(".01")
    funding = min(
        number(account["cash"]),
        number(account["non_marginable_buying_power"]),
        max(Decimal(0), cash - purchases - number(state.cash_reserved())),
    )
    completed, mend = clock(), monotonic()
    observation = dict(
        started_at=started.isoformat(),
        oldest_response_at=min(response_clocks.values()),
        last_response_at=last_response.isoformat(),
        completed_at=completed.isoformat(),
        started_monotonic=mono,
        completed_monotonic=mend,
        account_hash=ACCOUNT,
        checkpoint_hash=_hash(current),
        currency=account["currency"],
        account_status=account["status"],
        trading_blocked=account.get("trading_blocked"),
        account_blocked=account.get("account_blocked"),
        trade_suspended=account.get("trade_suspended_by_user"),
        positions_complete=True,
        orders_complete=True,
        activities_complete=activity_complete,
        cash_reconciled=cash_complete,
        actions_complete=rights_complete,
        fees_complete=fee_complete,
        units_reconciled=units_complete,
        holdings=holds,
        own_cash=str(cash),
        trade_receivables=str(sales),
        valued_rights="0",
        purchase_payables=str(purchases),
        fee_liabilities="0",
        other_liabilities="0",
        unborrowed_available=str(funding),
        own_nav=str(nav),
        decoded_capture_bindings=bodies,
        decoded_capture_format="request_response_body_envelope_v1",
        mark_basis="broker current_price/market_value receipt; exchange time unknown",
        unresolved_nonfill_or_unapplied_activity=not activity_complete,
        zero_fee_amount_is_certified=fee_complete,
        assets=assets,
        broker_clock=market_clock,
        broker_clock_received_at=response_clocks["market-clock"],
        account_marked_value=str(view["account_marked_value"]),
        account_unborrowed_available=str(
            min(number(account["cash"]), number(account["non_marginable_buying_power"]))
        ),
        other_checkpoint_hashes=view["other_checkpoint_hashes"],
        unassigned_account_activities=view["unassigned_activities"],
    )
    result = dict(
        observation=observation,
        known_guard_refusals=known_guard_refusals,
        account=account,
        positions=positions,
        orders=orders,
        activities=activities,
        bodies=bodies,
        aggregate_orders=aggregate_orders,
        aggregate_positions=aggregate_positions,
        aggregate_activities=aggregate_activities,
        cash_is_not_independently_certified_settled_cash=True,
        response_clocks=response_clocks,
    )
    data = save(directory / "capture-data.json", result)
    # Completion follows actual durable data publication; downstream age checks
    # also include this final completion-marker I/O, never a backdated timestamp.
    observation["completed_at"] = clock().isoformat()
    observation["completed_monotonic"] = monotonic()
    result["observation"] = observation
    save(
        directory / "capture.json",
        dict(
            captured_data=data,
            observation=observation,
            data_publication_completed_at=observation["completed_at"],
        ),
    )
    return result
