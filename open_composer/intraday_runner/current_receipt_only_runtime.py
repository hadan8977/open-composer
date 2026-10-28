"""Receipt-only mixed-attempt settlement; no submit, release or retry authority.

Acquisition and accounting reuse the installed capture and FILL engine. Unknown
armed attempts remain fully reserved; fresh financial eligibility is separate.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from datetime import UTC, datetime
from decimal import Decimal

from open_composer.intraday_runner.current_initialization_controls import (
    ACCOUNT,
    number,
    receive_observation,
)
from open_composer.intraday_runner.current_initialization_runtime import (
    CurrentInitializationRuntime,
)
from open_composer.intraday_runner.source_activity_reception import bind
from open_composer.intraday_runner.source_dispatch_journal import (
    _hash,
    classify_own_order,
)
from open_composer.intraday_runner.source_execution_receipts import apply_bound_fill
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.source_state_checkpoint import restore, snapshot


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
    order_observation_variants = {}
    for row in opened:
        old = orders.get(row["client_order_id"])
        if old is not None and old != row:
            receive_order_representation_pair(old, row)
            order_observation_variants[row["client_order_id"]] = dict(
                history=copy.deepcopy(old),
                open_orders=copy.deepcopy(row),
                canonical="original_history_row",
                new_risk_certificate=False,
            )
            continue  # Keep the original row; never merge or rewrite its clock.
        orders[row["client_order_id"]] = row
    books = runtime.partition.books()
    view = runtime.partition.account_view(books, runtime.task, positions, orders, activities)
    aggregate_orders, aggregate_positions, aggregate_activities = orders, positions, activities
    orders, positions, activities = (
        view["own_orders"],
        view["own_positions"],
        view["own_activities"],
    )
    known_guard_refusals, unknown_attempts = classify_missing_attempts(
        runtime, state, fills, fees, evidence, orders
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
    if unknown_attempts:
        activity_complete = False
        fee_complete = False
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
        unknown_attempts=unknown_attempts,
        order_observation_variants=order_observation_variants,
        receipt_only=True,
        new_risk_permitted=False,
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


def receive_order_representation_pair(history, opened):
    """Receive the observed SDK timestamp precision/source-label difference only.

    Every economic, identity, status and other metadata field remains exact.
    Both raw rows stay bound. These timestamps never set account freshness.
    """
    import re
    from decimal import ROUND_HALF_UP

    clocks = {"created_at", "submitted_at", "updated_at"}
    ignored = clocks | {"source"}
    if {k: v for k, v in history.items() if k not in ignored} != {
        k: v for k, v in opened.items() if k not in ignored
    }:
        raise ValueError("order economics/identity changed during receipt")
    if any(row.get("source") not in {None, "access_key"} for row in (history, opened)):
        raise ValueError("unreceived source representation")

    def micros(value):
        if not isinstance(value, str):
            raise ValueError("missing actual order timestamp")
        match = re.fullmatch(
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})", value
        )
        if not match:
            raise ValueError("unknown order timestamp representation")
        whole = datetime.fromisoformat(match[1] + match[3].replace("Z", "+00:00"))
        seconds = Decimal(int(whole.timestamp()))
        fraction = Decimal("0." + (match[2] or "0"))
        return ((seconds + fraction) * 1000000).quantize(Decimal(1), rounding=ROUND_HALF_UP)

    for key in clocks:
        if micros(history.get(key)) != micros(opened.get(key)):
            raise ValueError("actual order timestamp changed beyond received precision")
    return None


def classify_missing_attempts(runtime, state, fills, fees, evidence, orders):
    from open_composer.intraday_runner.source_activity_reception import bind
    from open_composer.intraday_runner.source_terminal_holds import (
        receive_never_attempted,
        receive_not_dispatched_guard_refusal,
    )

    known, unknown = {}, {}
    for cid, pending in state.pending.items():
        if pending["side"] == "liability_hold":
            if cid not in evidence.get("terminal_liability_holds", {}):
                raise ValueError("terminal liability provenance missing")
            continue
        if cid in orders:
            continue
        path = runtime.journal._path(cid)
        if path.is_symlink() or path.exists():
            record = runtime.journal.receive(cid)
            if record.get("stage") == "not_dispatched_guard_refusal":
                known[cid] = receive_not_dispatched_guard_refusal(
                    state, fills, fees, evidence, cid=cid, journal=runtime.journal
                )
                continue
            witness = evidence.get("dispatch_intents", {}).get(cid)
            if (
                record.get("stage") != "dispatch_boundary_consumed_ack_unknown"
                or not witness
                or witness.get("attempted") is not True
                or cid not in state.consumed_ids
                or record.get("request", {}).get("client_order_id") != cid
                or _hash(record["request"]) != record.get("request_sha256")
                or record["request"].get("reservation") != pending
                or _hash(pending) != witness.get("reservation_sha256")
                or record.get("reservation_snapshot", {}).get("pending", {}).get(cid) != pending
                or str(runtime.journal.directory) != witness.get("journal_root")
                or [
                    runtime.journal.directory.stat().st_dev,
                    runtime.journal.directory.stat().st_ino,
                ]
                != witness.get("journal_identity")
            ):
                raise ValueError("malformed or foreign unknown-attempt evidence")
            unknown[cid] = dict(
                client_order_id=cid,
                status="armed_attempt_outcome_unknown",
                journal=bind(path),
                reservation_sha256=_hash(pending),
                broker_absence_not_nonexecution=True,
                reservation_released=False,
                consumed_id_reusable=False,
                physical_submission_claim=None,
            )
        else:
            known[cid] = receive_never_attempted(
                state, fills, fees, evidence, cid=cid, journal=runtime.journal
            )
    return known, unknown


def corrected_single_source_lot(root, current, plan_binding):
    """Receive one exact saved arithmetic defect, never replay an execution."""
    plan = json.loads(bound_bytes(root, plan_binding))
    original = json.loads(bound_bytes(root, plan["prior_revision"]))
    if (
        plan.get("kind") != "exact_single_source_lot_quantity_correction"
        or plan.get("capital_flow_USD") != 0
        or plan.get("reservation_release") is not False
        or original != current
        or _hash(current) != plan.get("current_checkpoint_sha256")
        or current["identity"]["account_hash"] != ACCOUNT
        or current["identity"]["sleeve_id"] != plan.get("task_id")
    ):
        raise ValueError("correction lacks exact current owned predecessor")
    value = copy.deepcopy(current["snapshot"])
    fill_id = plan["fill_id"]
    record = value["fills"][fill_id]
    receipt = json.loads(bound_bytes(root, record["capture"]))
    events = json.loads(bound_bytes(root, record["body"]))
    event = events[record["ordinal"]]
    if (
        receipt.get("method") != "GET"
        or receipt.get("status") != 200
        or receipt.get("endpoint_kind") != "account_activities"
        or receipt.get("account_hash") != ACCOUNT
        or receipt.get("body") != record["body"]
        or event.get("id") != fill_id
        or _hash(event) != record["event_sha256"]
        or event.get("activity_type") != "FILL"
        or event.get("side") != "buy"
        or record.get("account_hash") != ACCOUNT
        or fill_id not in value["applied_fill_ids"]
    ):
        raise ValueError("correction lacks an already applied authenticated FILL")
    journal = record["journal_snapshot"]
    owned = classify_own_order(journal["request"], journal["observations"][-1])
    cid, symbol = record["client_order_id"], event["symbol"]
    quantity = number(event["qty"])
    if (
        journal["request"]["client_order_id"] != cid
        or journal["request"]["symbol"] != symbol
        or event["order_id"] != owned["broker_order_id"]
        or quantity != quantity.to_integral_value()
        or quantity <= 0
        or value["pending"][cid]["filled"] != int(quantity)
        or sum(r["client_order_id"] == cid for r in value["fills"].values()) != 1
    ):
        raise ValueError("correction requires one exact complete whole-share execution")
    purchases = [p for p in value["cashbook"]["purchases"] if p["symbol"] == symbol]
    lots = value["cashbook"]["lots"][symbol]
    if len(purchases) != 1 or len(lots) != 1 or len(purchases[0]["funding"]) != 1:
        raise ValueError("not the single-purchase single-funding defect")
    purchase, lot = purchases[0], lots[0]
    part = purchase["funding"][0]
    amount = int(quantity) * float(number(event["price"]))
    reproduced = int(quantity) * part["amount"] / amount
    if (
        part["amount"] != amount
        or purchase["amount"] != amount
        or lot["funded"] != part["funded"]
        or lot["quantity"] != reproduced
        or number(lot["quantity"]) == quantity
        or value["cashbook"]["sales"]
        or value["fees"]
    ):
        raise ValueError("saved lot is not the exact isolated arithmetic defect")
    before = copy.deepcopy(lot)
    lot["quantity"] = int(quantity)
    value["evidence"].setdefault("exact_lot_quantity_corrections", {})[plan_binding["sha256"]] = (
        dict(
            plan=plan_binding,
            prior_revision=plan["prior_revision"],
            applied_fill_id=fill_id,
            original_lot=before,
            corrected_lot=copy.deepcopy(lot),
            cash_funding_fees_risk_HWM_ids_unchanged=True,
            execution_replayed=False,
            reservation_released=False,
        )
    )
    return value


class ReceiptOnlyRuntime(CurrentInitializationRuntime):
    """Only the settlement method differs; original gateway denies broker writes."""

    def reconcile(self, output):
        """Retain all raw capture and apply actual FILL deltas before NAV acceptance."""
        self.connect()
        raw = capture(self, output / "account", clock=self.clock, monotonic=self.monotonic)
        current = self.store.load()
        value = current["snapshot"]
        correction = getattr(self, "lot_quantity_correction", None)
        if correction is not None:
            value = corrected_single_source_lot(self.root, current, correction)
        state, fills, fees, evidence = restore(self.root, value)
        orders = raw["orders"]
        receive_observation(
            raw["observation"],
            now=self.clock(),
            now_monotonic=self.monotonic(),
            account_hash=ACCOUNT,
            checkpoint_hash=_hash(current),
            purpose="owned_cancel",
        )
        if raw.get("unknown_attempts"):
            evidence.setdefault("unknown_attempt_holds", {}).update(raw["unknown_attempts"])
            evidence["initial_dispatch_blocked"] = True
            evidence["unresolved_actual_liabilities"] = True
        if raw.get("known_guard_refusals"):
            evidence.setdefault("known_pre_submit_refusals", {}).update(raw["known_guard_refusals"])
            evidence["initial_dispatch_blocked"] = True
        for cid, order in orders.items():
            journal = self.journal.receive(cid)
            classify_own_order(journal["request"], order)
            journal["observations"].append(order)
            self.write_text(self.journal._path(cid), json.dumps(journal, sort_keys=True) + "\n")
        body = self.save_capture(output / "activities.json", raw["activities"])
        receipt = self.save_capture(
            output / "activities-receipt.json",
            dict(
                method="GET",
                endpoint_kind="account_activities",
                status=200,
                account_hash=ACCOUNT,
                body=body,
                received_at=max(
                    v for k, v in raw["response_clocks"].items() if k.startswith("activities-")
                ),
                source_pages={
                    k: v for k, v in raw["bodies"].items() if k.startswith("activities-")
                },
                capture_basis=(
                    "Own-sleeve projection of SDK-decoded pages; "
                    "all original pages bound, not wire bytes"
                ),
            ),
        )
        order_map = {o["id"]: cid for cid, o in orders.items()}
        for i, item in enumerate(raw["activities"]):
            if item.get("activity_type") != "FILL":
                evidence["unresolved_actual_liabilities"] = True
                continue
            cid = order_map.get(item.get("order_id"))
            if cid is None:
                raise ValueError("unowned execution activity")
            state, fills, _ = apply_bound_fill(
                self.root,
                state,
                fills,
                receipt_binding=receipt,
                ordinal=i,
                journal_record=self.journal.receive(cid),
                expected_account_hash=ACCOUNT,
                observed_now=self.clock(),
            )
        for cid, order in orders.items():
            received = classify_own_order(self.journal.receive(cid)["request"], order)
            if received["terminal_observed"]:
                if (
                    cid not in state.pending
                    or state.pending[cid]["filled"] != received["cumulative_filled"]
                ):
                    raise ValueError("terminal receipt lacks complete owned fill prefix")
                # Receipt-only processing does not transform/release the original
                # reservation. Keep actual terminal provenance and all fee holds.
                evidence.setdefault("terminal_receipts_still_held", {})[cid] = dict(
                    actual_order=copy.deepcopy(order),
                    capture=body,
                    fees_reconciled=False,
                    reservation_released=False,
                )
        evidence["actual_fees_reconciled"] = (
            not fills and not raw["activities"] and not orders and not raw["unknown_attempts"]
        )
        receive_observation(
            raw["observation"],
            now=self.clock(),
            now_monotonic=self.monotonic(),
            account_hash=ACCOUNT,
            checkpoint_hash=_hash(current),
            purpose="owned_cancel",
        )
        previous_write_guard = self.store.write_guard

        def fresh_receipt_write(path, size, *, atomic=True):
            if previous_write_guard is not None:
                if previous_write_guard(path, size, atomic=atomic) is not None:
                    raise ValueError("financial write guard must raise")
            # All allocation scans precede the unchanged paired 15-second check.
            # No checkpoint read while the store lock is held.
            receive_observation(
                raw["observation"],
                now=self.clock(),
                now_monotonic=self.monotonic(),
                account_hash=ACCOUNT,
                checkpoint_hash=_hash(current),
                purpose="owned_cancel",
            )

        self.store.write_guard = fresh_receipt_write
        try:
            self.store.commit(
                snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(current)
            )
        finally:
            self.store.write_guard = previous_write_guard
        from open_composer.book_paper.cost_ledgers import profit_ledgers

        initial_scope = json.loads(bound_bytes(self.root, self.auth["initial_account_scope"]))
        ledgers = profit_ledgers(
            float(number(raw["account"]["equity"])),
            float(number(initial_scope["broker_reported_cash_equity_nonmarginable_USD"])),
            dict(impact=0.0, fees=0.0, borrow=0.0, total=0.0),
            holdings_valuation_complete=False,
        )
        # No friction model is calibrated for this new DAY-limit application.
        # Keep actual equity change, unknown flow/inclusion and no second spread.
        ledgers.pop("legacy_full_shadow")
        ledgers["current_modeled_cost_scenario_defined"] = False
        ledgers["historical_PnL_transferred_to_this_trial"] = False
        ledgers["account_level_only_not_sleeve_attribution"] = True
        # Reconcile the captured aggregate position rows to the newly received
        # fills without issuing another GET or representing old marks as fresh.
        post_view = self.partition.account_view(
            self.partition.books(),
            self.task,
            raw["aggregate_positions"],
            raw["aggregate_orders"],
            raw["aggregate_activities"],
        )
        scoped_accounting = dict(
            sleeve_id=self.task,
            initial_sleeve_capital=str(number(evidence["risk"]["initial_capital"])),
            net_external_allocation_flows=str(
                number(evidence["risk"].get("net_allocation_flows", 0))
            ),
            funded_sleeve_capital=str(self.cap),
            capital_flows_are_not_profit=True,
            marked_virtual_book_NAV_estimate=None,
            virtual_book_change_estimate=None,
            valuation_complete=False,
            captured_aggregate_quantities_match_complete_virtual_books=post_view["units_complete"],
            saved_mark_capture=bind(output / "account/capture.json"),
            marks_are_saved_capture_not_new_observation=True,
            certified_sleeve_PnL=None,
            incremental_only_net=None,
            reason=(
                "Complete current marked book, fees/rights/flows and settlement must reconcile; "
                "broker account equity is not either sleeve PnL."
            ),
            historical_simulation_net_not_current_broker_performance=True,
            no_modeled_spread_or_planning_buffer_debited=True,
        )
        return dict(
            status="actual_receipts_received_valuation_may_remain_incomplete",
            unknown_attempts=raw["unknown_attempts"],
            new_risk_permitted=False,
            holds_released=False,
            fill_ids=sorted(fills),
            cost_ledgers=ledgers,
            sleeve_accounting=scoped_accounting,
            fees_certified=evidence["actual_fees_reconciled"],
            raw=bind(output / "account/capture.json"),
            no_order_calls=True,
            post_application_positions=post_view["own_positions"]
            if post_view["units_complete"]
            else None,
            position_attribution_complete=post_view["units_complete"],
            post_application_checkpoint=bind(self.store._revision(current["generation"] + 1)),
        )

    def receipt_projection(self, output, result_binding):
        """Project the received ledger against the same saved broker observation."""
        result = json.loads(bound_bytes(self.root, result_binding))
        capture_receipt = json.loads(bound_bytes(self.root, result["raw"]))
        original = json.loads(bound_bytes(self.root, capture_receipt["captured_data"]))
        bound_bytes(self.root, result["post_application_checkpoint"])
        projection = self.save_capture(
            output / "after-receipts/account/capture-data.json",
            dict(
                orders=original["orders"],
                positions=result["post_application_positions"] or [],
                position_attribution_complete=result["position_attribution_complete"],
                empty_positions_is_not_zero_exposure=not result["position_attribution_complete"],
                original_capture=result["raw"],
                post_application_checkpoint=result["post_application_checkpoint"],
                kind="saved_broker_observation_after_actual_receipt_application",
                new_account_observation=False,
            ),
        )
        return self.save_capture(
            output / "after-receipts/result.json",
            dict(result, projection_account_view=projection),
        )

    def cancel(self, output):
        """Existing owned-remainder cancellation; unknown attempts are not orders."""
        self.require_phase("cancel")
        self.reconcile(output / "reconcile")
        raw = capture(self, output / "fresh-orders", clock=self.clock, monotonic=self.monotonic)
        rows = self.cancel_observed(raw)
        return dict(
            cancel_observations=rows,
            cancellation_response_is_not_terminal=True,
            unknown_attempts=raw["unknown_attempts"],
            holds_released=False,
        )
