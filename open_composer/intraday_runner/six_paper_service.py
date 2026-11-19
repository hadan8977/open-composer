"""Direct six-policy paper adapter over existing cash/reservation accounting.

Original checkpoints/journals remain immutable migration evidence. Complete
snapshots continue in an atomic service state. Old IDs are never resubmitted;
ambiguous new submissions are queried by ID, never blindly retried.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from open_composer.intraday_runner.current_initialization_controls import (
    ACCOUNT,
    ENV_PATH,
    limit_price,
    session,
)
from open_composer.intraday_runner.source_method_bindings import source_module
from open_composer.intraday_runner.source_reservations import SourceReservations
from open_composer.intraday_runner.source_state_checkpoint import restore, snapshot
from open_composer.market_sessions import NEW_YORK

#: Policy -> dashboard task id.
POLICIES = {
    "BASE": "BASE-CURRENT-INITIALIZATION-20261019",
    "H5": "H5-LEARNED-SWING-PAPER-VALIDATION-20261019",
    "LSTM": "CROSS-ASSET-LSTM-PAPER-VALIDATION-20261019",
}
#: Policy -> original October book directory under reports/paper/intraday/.
ORIGINAL_BOOKS = {
    "BASE": "dia-base-initialization-20261019",
    "H5": "h5-learned-swing-validation-20261019",
    "LSTM": "lstm-crossasset-validation-20261019",
}
RETIRING_POLICIES = ("BASE",)
TERMINAL = {"filled", "expired", "canceled", "cancelled", "rejected"}
#: Share drift worth trading on a ``hold`` instruction, as a fraction of the
#: book's capital. ``hold`` used to mean "never touch this book", and because the
#: flag compares the new target with the previous target file (not the book), any
#: rebalance that failed to execute stayed ``hold`` forever: BASE kept its
#: October roster for four sessions and H5 stayed in cash for a week. The same
#: 5% band the deployed ETF sleeves use is the reference for the churn floor.
HOLD_DRIFT_TOLERANCE_FRACTION = 0.05
#: Resizes of a held, still-targeted name below this fraction of book capital
#: are skipped (1-share round trips were pure rounding noise).
MIN_RESIZE_FRACTION = 0.02
#: Limit orders are priced this far through the reference so they fill.
MARKETABLE_BUFFER = 0.02


def whole_share_delta(quantity):
    nearest = round(quantity)
    return nearest if abs(quantity - nearest) <= 1e-9 else int(quantity)


def hold_drift(desired, held, references, *, capital, nav, tolerance=HOLD_DRIFT_TOLERANCE_FRACTION):
    """Share deltas large enough to trade even though the instruction says hold.

    Measured in whole shares against the instruction's target quantities, so
    integer rounding never looks like drift; a delta must also clear the
    tolerance band in dollars to avoid churning on price noise.
    """
    floor = float(tolerance) * min(float(capital), float(nav))
    drift: dict[str, int] = {}
    for symbol, target_qty in desired.items():
        delta = whole_share_delta(target_qty - held.get(symbol, 0))
        price = float(references.get(symbol) or 0.0)
        if not delta or price <= 0:
            continue
        if abs(delta) * price > floor:
            drift[symbol] = delta
    return drift


def instant(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result.astimezone(UTC)


def plain(value):
    return (
        json.loads(value.model_dump_json())
        if hasattr(value, "model_dump_json")
        else copy.deepcopy(value)
    )


def order_lookup_failure(exc):
    """Error type and HTTP status of a failed order GET; never a no-submit proof.

    Exception text, URLs, headers and response bodies are not recorded.
    """
    from alpaca.common.exceptions import APIError

    response = getattr(exc, "response", None) if isinstance(exc, APIError) else None
    status = getattr(response, "status_code", None)
    return dict(
        kind="native_order_lookup_failure_v1",
        error_type=type(exc).__name__,
        http_status=status if type(status) is int else None,
    )


def write_state(path, state):
    path = Path(path)
    temp = path.with_suffix(".tmp")
    with temp.open("w") as stream:
        json.dump(state, stream, indent=2, sort_keys=True, allow_nan=False, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def validate_target(value, policy, now):
    if value["policy"] != policy or not instant(value["as_of"]) <= now < instant(
        value["valid_until"]
    ):
        raise ValueError("wrong, future or expired target")
    if value["portfolio_action"] not in {"hold", "rebalance"}:
        raise ValueError("unknown portfolio action")
    symbols, weights = value["symbols"], value["weights"]
    if len(symbols) != len(set(symbols)) or len(symbols) != len(weights):
        raise ValueError("duplicate/incomplete targets")
    if any(not isinstance(s, str) or not s or len(s) > 10 for s in symbols):
        raise ValueError("invalid symbol")
    if (
        any(
            isinstance(w, bool)
            or not math.isfinite(float(w))
            or not 0 <= float(w) <= 0.2 + 1e-12
            for w in weights
        )
        or sum(map(float, weights)) > 1 + 1e-12
    ):
        raise ValueError("target concentration/gross differs")
    return value


def terminal_principal(state, evidence, cid, observed, request):
    """End a proved terminal quantity lock; retain the original fee allowance.

    Supports the original single-cash buy branch; a terminal sell only ends
    its unfilled share lock and stays undisposed. No final fee, cash
    settlement or profit is certified. Source/date and all consumed IDs survive.
    """
    from open_composer.intraday_runner.source_dispatch_journal import classify_own_order

    fact = classify_own_order(request, observed)
    row = state.pending[cid]
    if not fact["terminal_observed"] or row["filled"] != fact["cumulative_filled"]:
        raise ValueError("terminal execution prefix differs")
    if row["side"] == "sell":
        # A terminal sell (canceled/expired) must stop locking the shares it
        # never sold; otherwise every later sell of that symbol fails with
        # "sell exceeds unreserved funded own shares" and the whole policy is
        # blocked (2026-11-10..12: four policies stuck on canceled CRM sells).
        # The row and its fee hold stay open as before (disposition False);
        # only the unfilled share quantity is released, once.
        unfilled = row["quantity"] - row["filled"]
        if unfilled > 0:
            evidence.setdefault("service_terminal_sell_releases", {})[cid] = dict(
                original_reservation=copy.deepcopy(row),
                actual_terminal_order=copy.deepcopy(observed),
                released_unfilled_shares=unfilled,
            )
            row["quantity"] = row["filled"]
        return False
    if row["side"] != "buy":
        return False
    original, remaining = row["original_funding"], row["remaining_funding"]
    if (
        len(original) != 1
        or len(remaining) != 1
        or original[0]["source"] != "cash"
        or remaining[0]["source"] != "cash"
    ):
        return False
    allowance = float(original[0]["amount"]) - row["quantity"] * row["limit_price"]
    expected = row["quantity"] * row["limit_price"] * 0.001
    if (
        not math.isclose(allowance, expected, rel_tol=1e-7, abs_tol=1e-7)
        or allowance < 0
        or remaining[0]["amount"] + 1e-7 < allowance
    ):
        raise ValueError("unreceived original fee allowance")
    # Retain a cent-rounded-up allowance; never release subcent residual dust.
    hold = min(remaining[0]["amount"], math.ceil((allowance + 1e-9) * 100) / 100)
    evidence.setdefault("service_terminal_dispositions", {})[cid] = dict(
        original_reservation=copy.deepcopy(row),
        actual_terminal_order=copy.deepcopy(observed),
        retained_fee_allowance=hold,
        final_fees_certified=False,
    )
    row.update(side="liability_hold", quantity=0, filled=0)
    row["remaining_funding"][0]["amount"] = hold
    return True


def new_book(root, capital):
    state = SourceReservations(source_module(root, "cash").CashState(cash=capital))
    return snapshot(
        state,
        {},
        {},
        evidence={
            "risk": {
                "high_water": str(capital),
                "initial_capital": str(capital),
                "halted": False,
                "killed": False,
            }
        },
    )


def initialize(root):
    value = {
        "schema_version": 1,
        "books": {},
        "orders": {},
        "cycles": {},
        "policy_status": {},
        "baseline": {},
    }
    for policy in POLICIES:
        directory = Path(root) / "reports/paper/intraday" / ORIGINAL_BOOKS[policy] / ACCOUNT
        head = directory / "checkpoints/head.json"
        if head.exists():
            generation = json.loads(head.read_text())["generation"]
            revision = head.parent / f"revision-{generation:08d}.json"
            value["books"][policy] = json.loads(revision.read_text())["snapshot"]
            value["baseline"][policy] = {
                "path": str(revision),
                "journal": str(directory / "dispatch"),
            }
        else:
            value["books"][policy] = new_book(root, 20000)
    return value


class SixPaperService:
    def __init__(self, root, config, state_path, client, *, clock=lambda: datetime.now(UTC)):
        self.root, self.config, self.path, self.client, self.clock = (
            Path(root),
            config,
            Path(state_path),
            client,
            clock,
        )
        self.state = (
            json.loads(self.path.read_text()) if self.path.exists() else initialize(self.root)
        )
        from open_composer.intraday_runner.ratelimit import RateLimiter

        self.limiter = RateLimiter()
        self.save()

    def call(self, method, *args, **kwargs):
        self.limiter.acquire()
        return getattr(self.client, method)(*args, **kwargs)

    def save(self):
        write_state(self.path, self.state)

    def event(self, kind, **values):
        from open_composer.storage import append_jsonl

        append_jsonl(
            self.path.with_suffix(".events.jsonl"),
            [dict(type=kind, at=self.clock().isoformat(), **values)],
        )

    def allowed(self):
        hold = json.loads(
            (self.root / "reports/research/control/owner-compute-hold.json").read_text()
        )
        auth = json.loads(Path(self.config["authorization"]).read_text())
        return (
            hold.get("existing_paper_operations_allowed") is True
            and auth.get("paper_only") is True
            and self.clock() < instant(self.config["expires_at"])
        )

    def preflight(self):
        from open_composer.adapters.broker.alpaca_paper import _require_verified_paper_client

        _require_verified_paper_client(self.client)
        account = plain(self.call("get_account"))
        if hashlib.sha256(str(account["id"]).encode()).hexdigest() != ACCOUNT:
            raise ValueError("wrong paper account")
        if str(account["status"]).upper() != "ACTIVE" or any(
            account.get(k)
            for k in ("trading_blocked", "account_blocked", "trade_suspended_by_user")
        ):
            raise ValueError("paper account blocked")
        positions = {p["symbol"]: p for p in map(plain, self.call("get_all_positions"))}
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        opened = list(
            map(
                plain,
                self.call("get_orders", GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)),
            )
        )
        known = set(self.state["orders"]) | {
            cid for b in self.state["books"].values() for cid in b["consumed_ids"]
        }
        foreign = [o["client_order_id"] for o in opened if o["client_order_id"] not in known]
        self.state["open_orders"], self.state["foreign_open_orders"] = opened, foreign
        self.state["account"] = {
            "account_hash": ACCOUNT,
            "cash": account["cash"],
            "equity": account["equity"],
            "positions": positions,
            "observed_at": self.clock().isoformat(),
        }
        expected = {}
        for book in self.state["books"].values():
            for symbol, lots in book["cashbook"]["lots"].items():
                expected[symbol] = expected.get(symbol, 0.0) + sum(
                    float(lot["quantity"]) for lot in lots
                )
        actual = {s: float(p["qty"]) for s, p in positions.items()}
        mismatch = {
            s: (expected.get(s, 0), actual.get(s, 0))
            for s in expected.keys() | actual.keys()
            if abs(expected.get(s, 0) - actual.get(s, 0)) > 1e-6
        }
        self.state["position_mismatch"] = mismatch
        if len(opened) >= 500:
            raise ValueError("broker open-order page is saturated")
        foreign_ids = set(foreign)
        for order in opened:
            if order["client_order_id"] in foreign_ids:
                mismatch.setdefault(order["symbol"], "foreign_open_order")
        self.save()
        return positions, mismatch

    def disposition(self):
        """Proven no-submit reservations can end; consumed IDs remain immutable."""
        from open_composer.intraday_runner.source_terminal_holds import (
            receive_never_attempted,
            receive_not_dispatched_guard_refusal,
        )

        for policy, baseline in self.state["baseline"].items():
            state, fills, fees, evidence = restore(self.root, self.state["books"][policy])
            directory = Path(baseline["journal"])
            journal = SimpleNamespace(
                directory=directory, _path=lambda cid, base=directory: base / (cid + ".json")
            )
            for cid, row in list(state.pending.items()):
                if row["side"] == "liability_hold":
                    continue
                try:
                    if row.get("filled"):
                        raise ValueError("filled prefix requires actual terminal observation")
                    if journal._path(cid).exists():
                        proof = receive_not_dispatched_guard_refusal(
                            state, fills, fees, evidence, cid=cid, journal=journal
                        )
                    else:
                        proof = receive_never_attempted(
                            state, fills, fees, evidence, cid=cid, journal=journal
                        )
                    evidence.setdefault("service_no_submit_dispositions", {})[cid] = proof
                    state.release(cid, terminal_confirmed=True, fees_reconciled=True)
                except ValueError:
                    try:
                        record = json.loads(journal._path(cid).read_text())
                        if record.get("stage") == "prepared_no_dispatch":
                            from open_composer.intraday_runner import (
                                current_local_intent_disposition,
                            )

                            receipt = (
                                self.root
                                / "reports/research/program/owner-profit-delivery-plan-20261017"
                                / "paper-delivery/preopen-20261020/next-session-whole-runtime"
                                / "accounting-clock-capacity-M1"
                                / "independent-bound-unreached-tail-evidence-66ad.json"
                            )
                            original = json.loads(Path(baseline["path"]).read_text())
                            current = dict(
                                identity=original["identity"],
                                snapshot=snapshot(state, fills, fees, evidence=evidence),
                            )
                            proof = current_local_intent_disposition.receive_original_unreached(
                                self.root,
                                current,
                                receipt_binding=dict(
                                    path=str(receipt),
                                    sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
                                ),
                                cid=cid,
                                journal=journal,
                            )
                            evidence.setdefault("service_no_submit_dispositions", {})[cid] = proof
                            state.release(cid, terminal_confirmed=True, fees_reconciled=True)
                        elif record.get("observations"):
                            observed = plain(self.call("get_order_by_client_id", cid))
                            if terminal_principal(
                                state, evidence, cid, observed, record["request"]
                            ):
                                self.event(
                                    "old_terminal_principal_disposition",
                                    policy=policy,
                                    client_order_id=cid,
                                    actual_terminal_order=observed,
                                    final_fees_certified=False,
                                )
                    except (ValueError, KeyError, FileNotFoundError):
                        continue
            self.state["books"][policy] = snapshot(state, fills, fees, evidence=evidence)
        self.save()

    def sync_orders(self):
        from open_composer.intraday_runner.state_quantity_lock_transition import (
            receive_retired_late_order,
            retired,
        )

        for cid, record in self.state["orders"].items():
            if record.get("terminal_disposition"):
                continue
            started_at = self.clock().isoformat()
            try:
                observed = plain(self.call("get_order_by_client_id", cid))
            except Exception as exc:
                record["query_error"] = type(exc).__name__
                failure = order_lookup_failure(exc)
                prior = record.get("last_query_failure", {})
                same = all(prior.get(k) == v for k, v in failure.items())
                failure.update(
                    first_observed_at=prior["first_observed_at"] if same else started_at,
                    matching_observations=prior["matching_observations"] + 1 if same else 1,
                )
                record["last_query_failure"] = failure
                # Save even when a later order fails. Identical repeated errors
                # retain first/latest clocks and count without growing a journal
                # on every tick; a changed outcome is retained as a new event.
                self.save()
                if not same:
                    self.event(
                        "order_lookup_failure_evidence",
                        client_order_id=cid,
                        evidence=failure,
                    )
                continue
            if retired(cid, record):
                try:
                    receive_retired_late_order(cid, record, observed)
                except (KeyError, TypeError, ArithmeticError, ValueError):
                    # An always-true typed blocker is separate from raw payload,
                    # including empty objects/null and nonfinite decoded values.
                    raw = json.dumps(observed, sort_keys=True, default=str)
                    prior = record.get("current_quantity_lock_conflict", {})
                    conflict = dict(
                        kind="retired_STATE_order_conflict_v1",
                        blocking=True,
                        received_at=self.clock().isoformat(),
                        raw_observation_json=raw,
                        raw_observation_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                        basis="SDK-decoded value; not original wire bytes",
                    )
                    record["current_quantity_lock_conflict"] = conflict
                    self.save()
                    if (
                        prior.get("raw_observation_json") != raw
                        or prior.get("blocking") is not True
                    ):
                        self.event(
                            "STATE_current_quantity_reconciliation_conflict",
                            client_order_id=cid,
                            conflict=conflict,
                        )
                    continue
            if (
                observed["client_order_id"] != cid
                or observed["symbol"] != record["symbol"]
                or str(observed["side"]) != record["side"]
                or float(observed["qty"]) != record["qty"]
            ):
                raise ValueError("order ownership changed")
            record["observation"] = observed
            state, fills, fees, evidence = restore(self.root, self.state["books"][record["book"]])
            filled, prior = float(observed["filled_qty"]), state.pending[cid]["filled"]
            if filled < prior or not filled.is_integer():
                raise ValueError("nonwhole/reversed cumulative fill")
            if filled > prior:
                # Broker quantities/prices are decimal strings. Binary arithmetic
                # can fabricate a limit breach when differencing partial fills.
                total = Decimal(str(observed["filled_qty"])) * Decimal(
                    str(observed["filled_avg_price"])
                )
                quantity = int(filled - prior)
                price = float((total - Decimal(str(record.get("applied_notional", 0)))) / quantity)
                receipt = cid + ":cumulative:" + str(int(filled))
                state.confirmed_fill(
                    cid,
                    receipt,
                    quantity,
                    price,
                    self.clock().astimezone(NEW_YORK).date().isoformat(),
                )
                fills[receipt] = {
                    "client_order_id": cid,
                    "source": "broker_order_cumulative_delta",
                    "order_id": observed["id"],
                    "quantity": quantity,
                    "price": price,
                }
                record["applied_notional"] = str(total)
                self.event(
                    "confirmed_order_fill_delta",
                    client_order_id=cid,
                    observation=observed,
                    quantity=quantity,
                    price=price,
                )
            record["status"] = str(observed["status"])
            if record["status"] in TERMINAL:
                request = dict(
                    client_order_id=cid,
                    symbol=record["symbol"],
                    side=record["side"],
                    qty=record["qty"],
                    limit_price=record["limit_price"],
                    type="limit",
                    time_in_force="day",
                )
                record["terminal_disposition"] = terminal_principal(
                    state, evidence, cid, observed, request
                )
            self.state["books"][record["book"]] = snapshot(state, fills, fees, evidence=evidence)
            self.save()

    def target_books(self, policy, target, now):
        validate_target(target, policy, now)
        return [(policy, target, 20000.0, 0.25)]

    def submit(
        self,
        book,
        symbol,
        side,
        qty,
        reference,
        cycle,
        *,
        valid_until=None,
        application_day=None,
        protective=False,
    ):
        cid = "six-" + hashlib.sha256(f"{book}:{symbol}:{side}:{cycle}".encode()).hexdigest()[:36]
        if cid in self.state["orders"]:
            return

        from alpaca.common.exceptions import APIError
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest

        from open_composer.paper_lock import paper_submission_lock

        state, fills, fees, evidence = restore(self.root, self.state["books"][book])
        day = self.clock().astimezone(NEW_YORK).date().isoformat()
        cash = source_module(self.root, "cash")
        due = cash.cash_due_date(day, cash.settlement_calendar())
        # Marketable limit: fills through an ordinary gap but caps a bad print.
        price = round(
            float(reference) * (1 - MARKETABLE_BUFFER if side == "sell" else 1 + MARKETABLE_BUFFER),
            2,
        )
        if side == "buy":
            qty = min(qty, math.floor(state.available(due) / (price * 1.001)))
            if qty <= 0:
                return
            state.reserve_buy(cid, symbol, qty, price, qty * price * 0.001, day, due)
        else:
            state.reserve_sell(cid, symbol, qty, price, day, due, fee_buffer_rate=0.001)
        self.state["books"][book] = snapshot(state, fills, fees, evidence=evidence)
        self.state["orders"][cid] = dict(
            book=book,
            symbol=symbol,
            side=side,
            qty=qty,
            limit_price=price,
            status="prepared_unknown_until_queried",
            created_at=self.clock().isoformat(),
        )
        self.event(
            "signal_and_order_intent", client_order_id=cid, cycle=cycle, **self.state["orders"][cid]
        )
        self.save()
        with paper_submission_lock(self.root):
            if not self.allowed():
                raise ValueError("paper operations paused before POST")
            from open_composer.paper_controls import load_paper_kill_switch

            if load_paper_kill_switch(self.root, require_control_file=True).enabled:
                raise ValueError("global kill switch blocks submission")
            if not plain(self.call("get_clock"))["is_open"]:
                raise ValueError("RTH broker clock closed")
            now = self.clock()
            opening, close = session(now.astimezone(NEW_YORK).date())
            if not opening <= now < close or (
                side == "buy"
                and not opening + timedelta(minutes=10) <= now < close - timedelta(minutes=30)
            ):
                raise ValueError("outside actual execution window")
            account = plain(self.call("get_account"))
            if hashlib.sha256(str(account["id"]).encode()).hexdigest() != ACCOUNT or any(
                account.get(k)
                for k in ("trading_blocked", "account_blocked", "trade_suspended_by_user")
            ):
                raise ValueError("account changed or blocked before POST")
            if side == "buy" and float(account["cash"]) < qty * price * 1.001:
                raise ValueError("insufficient actual account cash")
            request = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                limit_price=price,
                client_order_id=cid,
            )
            # The limiter can wait: take its slot BEFORE final wall-clock checks.
            self.limiter.acquire()
            final_now = self.clock()
            final_open, final_close = session(final_now.astimezone(NEW_YORK).date())
            if (
                not self.allowed()
                or not final_open <= final_now < final_close
                or load_paper_kill_switch(self.root, require_control_file=True).enabled
            ):
                raise ValueError("paper authority or RTH expired before POST")
            if not protective:
                if (
                    valid_until is None
                    or application_day is None
                    or final_now.astimezone(NEW_YORK).date().isoformat() != application_day
                    or not final_open + timedelta(minutes=10)
                    <= final_now
                    < min(final_close - timedelta(minutes=30), instant(valid_until))
                ):
                    raise ValueError("dated target expired before POST")
            try:
                response = plain(self.client.submit_order(request))
            except APIError as exc:
                message = str(exc).lower()
                if not any(
                    term in message
                    for term in ("not tradable", "asset not found", "inactive asset")
                ):
                    raise
                reason = "broker_asset_unavailable"
                self.state.setdefault("symbol_freezes", {})[f"{book}/{symbol}"] = {
                    "day": day,
                    "reason": reason,
                }
                self.event("symbol_frozen", book=book, symbol=symbol, reason=reason)
                self.save()
                return
            self.state["orders"][cid].update(observation=response, status=str(response["status"]))
            self.event("order_acknowledgement", client_order_id=cid, observation=response)
            self.save()

    def operate(self, policy, target, positions, now, *, new_risk, frozen_symbols=None):
        from open_composer.book_paper.plan import _frozen_reason, _valid_price
        from open_composer.intraday_runner.state_quantity_lock_transition import retired

        rows = self.target_books(policy, target, now)
        conflicting = {
            record["symbol"]: "unresolved_order_quantity"
            for record in self.state["orders"].values()
            if record.get("current_quantity_lock_conflict")
        }
        cycle = hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()
        retiring = policy in RETIRING_POLICIES
        liquidating = (
            retiring and target["portfolio_action"] == "rebalance" and not target["symbols"]
        )
        marks = {
            s: mark
            for s, p in positions.items()
            if (frozen_symbols or {}).get(s) != "broker_quantity_mismatch"
            and (mark := _valid_price(p.get("current_price"))) is not None
        }
        day = now.astimezone(NEW_YORK).date().isoformat()
        for book, instruction, capital, drawdown in rows:
            state, fills, fees, evidence = restore(self.root, self.state["books"][book])
            held = {s: state.cashbook.quantity(s) for s in state.cashbook.lots}
            references = instruction["reference_marks"]
            frozen = (
                dict(frozen_symbols or {}) | instruction.get("frozen_symbols", {}) | conflicting
            )
            active = {s for s, q in held.items() if q} | set(instruction["symbols"])
            for symbol in active - frozen.keys():
                reason = ""
                if held.get(symbol) and symbol not in marks:
                    reason = "missing_position_mark"
                elif symbol in instruction["symbols"]:
                    mark = _valid_price(references.get(symbol))
                    if mark is None or mark < 1:
                        reason = "invalid_reference_price"
                lookup = getattr(self, "_asset_lookup", None)
                if not reason and lookup is not None:
                    reason = _frozen_reason(lookup(symbol))
                if reason:
                    frozen[symbol] = reason
            seen = self.state.setdefault("symbol_freezes", {})
            for symbol in sorted(active):
                key = f"{book}/{symbol}"
                if symbol in frozen and seen.get(key, {}).get("day") != day:
                    seen[key] = dict(day=day, reason=frozen[symbol])
                    self.event("symbol_frozen", book=book, symbol=symbol, reason=frozen[symbol])
                elif seen.get(key, {}).get("day") == day:
                    frozen[symbol] = seen[key]["reason"]
            unmarked = any(q and s not in marks for s, q in held.items())
            nav = state.cashbook.nav_cash() + sum(q * marks.get(s, 0.0) for s, q in held.items())
            risk = evidence["risk"]
            if not unmarked and risk.get("day") != day:
                risk.update(day=day, day_open_nav=nav, halted=bool(risk.get("killed")))
            if not unmarked:
                risk["high_water"] = max(float(risk["high_water"]), nav)
            risk["killed"] = (
                bool(risk.get("killed"))
                or (not unmarked and nav <= risk["high_water"] * (1 - drawdown))
            )
            risk["halted"] = (
                bool(risk.get("halted"))
                or risk["killed"]
                or (not unmarked and nav <= float(risk["day_open_nav"]) * 0.95)
            )
            if not unmarked:
                risk["last_nav"] = nav
            self.state["books"][book] = snapshot(state, fills, fees, evidence=evidence)
            self.save()
            if risk["killed"] or (liquidating and new_risk):
                desired = {s: 0 for s in held}
            elif retiring or not new_risk or risk["halted"]:
                continue
            else:
                import numpy as np

                symbols = sorted(active - frozen.keys())
                if not symbols:
                    continue
                weights = dict(zip(instruction["symbols"], instruction["weights"], strict=True))
                references = {
                    s: float(instruction["reference_marks"].get(s, marks.get(s, 0)))
                    for s in symbols
                }
                result, _ = source_module(self.root, "cash").target_quantities(
                    max(
                        0.0,
                        min(capital, nav)
                        - state.cash_reserved()
                        - sum(held.get(s, 0.0) * marks.get(s, 0.0) for s in frozen),
                    ),
                    np.array([held.get(s, 0.0) for s in symbols]),
                    np.array(
                        [
                            float(limit_price(references[s])) if references[s] else 1.0
                            for s in symbols
                        ]
                    ),
                    np.array([weights.get(s, 0.0) for s in symbols]),
                    0.001,
                    True,
                )
                desired = dict(zip(symbols, map(int, result), strict=True))
                if instruction["portfolio_action"] == "hold":
                    drift = hold_drift(
                        desired,
                        held,
                        references,
                        capital=capital,
                        nav=nav,
                    )
                    if not drift:
                        self.state["cycles"][policy] = cycle
                        continue
                    # Distinct cycle id keeps these orders auditable and apart
                    # from a scheduled rebalance of the same target.
                    self.state.setdefault("hold_drift", {})[book] = {
                        "observed_at": now.isoformat(),
                        "capital": capital,
                        "nav": nav,
                        "drift": drift,
                        "tolerance": HOLD_DRIFT_TOLERANCE_FRACTION,
                    }
                    self.event(
                        "hold_drift_rebalance",
                        book=book,
                        capital=capital,
                        nav=nav,
                        drift=drift,
                        tolerance=HOLD_DRIFT_TOLERANCE_FRACTION,
                    )
                    cycle = cycle + ":drift"
                    desired = {s: held.get(s, 0) + d for s, d in drift.items()}
            for symbol in sorted(desired, key=lambda s: desired[s] - held.get(s, 0)):
                if symbol in frozen:
                    continue
                delta = whole_share_delta(desired[symbol] - held.get(symbol, 0))
                reference = instruction["reference_marks"].get(symbol, marks.get(symbol))
                # No-trade band: small resizes of a name that is held and stays held.
                if (
                    delta
                    and held.get(symbol)
                    and desired[symbol]
                    and abs(delta) * float(reference or 0) < MIN_RESIZE_FRACTION * capital
                ):
                    continue
                if not delta or any(
                    r["book"] == book
                    and r["symbol"] == symbol
                    and r["status"] not in TERMINAL
                    and not retired(cid, r)
                    for cid, r in self.state["orders"].items()
                ):
                    continue
                self.submit(
                    book,
                    symbol,
                    "buy" if delta > 0 else "sell",
                    abs(delta),
                    reference,
                    cycle + (":stop" if risk["killed"] else ""),
                    valid_until=instruction["valid_until"],
                    application_day=instruction.get(
                        "application_day",
                        instant(instruction["valid_until"]).astimezone(NEW_YORK).date().isoformat(),
                    ),
                    protective=risk["killed"],
                )
        self.state["cycles"][policy] = cycle

    def cancel_due(self, now, close):
        """Protective cancellation never depends on a new scientific signal."""
        if now < close - timedelta(minutes=10):
            return
        for cid, record in self.state["orders"].items():
            if (
                record["book"] not in POLICIES
                or record["status"] in TERMINAL
                or record.get("cancel_attempted")
                or not record.get("observation", {}).get("id")
            ):
                continue
            record["cancel_attempted"] = now.isoformat()
            self.event("cancel_intent", client_order_id=cid)
            self.save()
            self.call("cancel_order_by_id", record["observation"]["id"])
            self.event("cancel_acknowledgement_not_terminal", client_order_id=cid)

    def protective(self, policy, positions, now, *, frozen_symbols=None):
        target = dict(
            policy=policy,
            as_of=now.isoformat(),
            valid_until=(now + timedelta(minutes=1)).isoformat(),
            portfolio_action="hold",
            symbols=[],
            weights=[],
            reference_marks={},
        )
        self.operate(policy, target, positions, now, new_risk=False, frozen_symbols=frozen_symbols)

    def publish_dashboard(self):
        """Project actual service/account state; uncertified money remains N/A."""
        folder = self.root / "reports/paper/validation"
        folder.mkdir(parents=True, exist_ok=True)
        checkpoint = dict(
            path=str(self.path), sha256=hashlib.sha256(self.path.read_bytes()).hexdigest()
        )
        for policy, task in POLICIES.items():
            current = self.state["policy_status"].get(policy, {"status": "blocked"})
            selected = [
                b
                for name, b in self.state["books"].items()
                if name == policy or name.startswith(policy + "/")
            ]
            holdings = {}
            for book in selected:
                for symbol, lots in book["cashbook"]["lots"].items():
                    holdings[symbol] = holdings.get(symbol, 0.0) + sum(
                        float(lot["quantity"]) for lot in lots
                    )
            target_path = Path(self.config["targets_root"]) / (policy + ".json")
            sources = dict(checkpoint=checkpoint, reconciliation=checkpoint)
            if target_path.exists():
                sources["decision"] = dict(
                    path=str(target_path),
                    sha256=hashlib.sha256(target_path.read_bytes()).hexdigest(),
                )
            status = (
                "running"
                if current["status"] == "operating"
                else "starting"
                if current["status"] == "ready_waiting_rth"
                else "failed"
            )
            value = dict(
                schema_version=1,
                task_id=task,
                mode="paper",
                status=status,
                observed_at_utc=self.state["heartbeat_at"],
                reconciled_at_utc=self.state.get("account", {}).get("observed_at"),
                market_as_of=instant(current["signal_as_of"]).date().isoformat()
                if current.get("signal_as_of")
                else None,
                capital_usd=20000.0,
                nav_usd=None,
                net_pnl_usd=None,
                net_return_pct=None,
                net_pnl_status="unknown",
                positions=[
                    dict(symbol=s, qty=q, market_value=None) for s, q in holdings.items() if q
                ],
                source_bindings=sources,
                note="Service process: "
                + current["status"]
                + ". Broker exposure checked against preserved books; fee/NAV/PnL uncertified.",
                service_state=str(self.path),
                service_pid=self.state["pid"],
            )
            write_state(folder / (policy + ".json"), value)

    def tick(self):
        now = self.clock()
        self.state.update(pid=os.getpid(), heartbeat_at=now.isoformat(), status="process_online")
        if not self.allowed():
            self.state["status"] = "paused_or_expired"
            self.save()
            return False
        self.sync_orders()
        positions, mismatch = self.preflight()
        self.disposition()
        market = plain(self.call("get_clock"))
        try:
            opening, close = session(now.astimezone(NEW_YORK).date())
        except ValueError:
            opening = close = now
        rth = bool(market["is_open"]) and opening <= now < close
        new_risk = rth and opening + timedelta(minutes=10) <= now < close - timedelta(minutes=30)
        frozen = {
            symbol: detail if isinstance(detail, str) else "broker_quantity_mismatch"
            for symbol, detail in mismatch.items()
        }
        if rth:
            from open_composer.book_paper.plan import make_asset_lookup

            self.cancel_due(now, close)
            if hasattr(self.client, "get_all_assets"):
                self._asset_lookup = make_asset_lookup(self.client)
        for policy in POLICIES:
            try:
                path = Path(self.config["targets_root"]) / (policy + ".json")
                target = json.loads(path.read_text()) if path.exists() else {}
                policy_frozen = frozen
                if target.get("application_day") == now.astimezone(NEW_YORK).date().isoformat():
                    policy_frozen = frozen | target.get("frozen_symbols", {})
                if rth:
                    self.protective(policy, positions, now, frozen_symbols=policy_frozen)
                self.target_books(policy, target, now)
                if rth:
                    self.operate(
                        policy, target, positions, now, new_risk=new_risk, frozen_symbols=frozen
                    )
                self.state["policy_status"][policy] = {
                    "status": "ready_waiting_rth" if not rth else "operating",
                    "observed_at": now.isoformat(),
                    "signal_as_of": target["as_of"],
                    "net_pnl_certified": False,
                }
            except Exception as exc:
                previous = self.state["policy_status"].get(policy, {})
                error = str(exc)[:200]
                self.state["policy_status"][policy] = {
                    "status": "blocked",
                    "error_type": type(exc).__name__,
                    "error": error,
                    "observed_at": now.isoformat(),
                }
                # One event per change, not one per tick.
                if previous.get("status") != "blocked" or previous.get("error") != error:
                    self.event(
                        "policy_blocked", policy=policy, error_type=type(exc).__name__, error=error
                    )
        self.state["heartbeat_at"] = self.clock().isoformat()
        self.save()
        self.publish_dashboard()
        return True


def _load_input_refresh(root):
    from open_composer.paper_runtime.six.run_dated_refresh import poll_refresh

    return poll_refresh


def service_loop(service, *, once=False, sleep=time.sleep, max_tick_failures=30):
    """Tick until the service stops; a transport error is logged, not fatal.

    ``tick`` talks to the broker on every pass, so an unreachable or silent peer
    raises instead of returning False. Thirty consecutive failures still end the
    process so a genuinely broken state cannot spin here forever (systemd
    restarts it).
    """
    refresh, input_job = None, None
    failures = 0
    while True:
        try:
            alive = service.tick()
        except Exception as exc:
            failures += 1
            service.event("tick_blocked", error_type=type(exc).__name__, consecutive=failures)
            if failures >= max_tick_failures:
                raise
            sleep(15)
            continue
        failures = 0
        if not alive or once:
            return
        try:
            if refresh is None:
                refresh = _load_input_refresh(service.root)
            input_job = refresh(input_job, now=service.clock())
        except Exception as exc:
            # An unavailable input never stops the next carried-risk tick.
            service.event("input_refresh_blocked", error_type=type(exc).__name__)
        sleep(15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    for key in ("authorization", "targets_root"):
        path = Path(config[key])
        if not path.is_absolute():
            config[key] = str(args.root / path)
    # Never initialize fresh books when the production ledger is absent.
    from open_composer.paper_runtime.paths import RUNTIME

    if args.state.parent.resolve() == (args.root / RUNTIME).resolve() and not args.state.exists():
        raise ValueError("six-policy runtime state is missing; refusing to create fresh capital")
    args.state.parent.mkdir(parents=True, exist_ok=True)
    import fcntl  # Linux service host only.

    with args.state.with_suffix(".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from open_composer.book_paper.accounts import make_trading_client

        client = make_trading_client("quant2", env_path=Path(ENV_PATH))
        service = SixPaperService(args.root, config, args.state, client)
        service_loop(service, once=args.once)


if __name__ == "__main__":
    main()
