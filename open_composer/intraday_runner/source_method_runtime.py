"""Bounded source-method runtime assembly, never an authorization issuer.

The existing scheduler/control boundary may invoke this only after exact Main
integration and scoped native/input/account acceptance. No implicit source,
forecast, account, fee or settlement substitute is supplied. Cash-only operation
uses its distinct GET-only entry. This module joins accepted wave, journal,
receipt and checkpoint components without changing their financial arithmetic.
"""

from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from open_composer.adapters.broker.alpaca_paper import (
    _atomic_write_text,
    _require_kill_switch_clear,
)
from open_composer.intraday_runner.source_account_observation import (
    capture_current,
    held_quote_fresh,
)
from open_composer.intraday_runner.source_bounded_gateway import SourceBoundedGateway
from open_composer.intraday_runner.source_dispatch_journal import (
    SourceDispatchJournal,
    _ensure_durable_directory,
    _hash,
)
from open_composer.intraday_runner.source_execution_receipts import apply_bound_fill
from open_composer.intraday_runner.source_funding_clock import (
    application_path,
    eligible_reservation_copy,
    restore_excluded_proceeds,
)
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.source_method_controls import require_window
from open_composer.intraday_runner.source_method_wave import prepare_wave
from open_composer.intraday_runner.source_operation_lock import source_account_operation
from open_composer.intraday_runner.source_quantity_commit import confirm_continuity
from open_composer.intraday_runner.source_state_checkpoint import (
    SourceStateCheckpoint,
    restore,
    snapshot,
)
from open_composer.paper_lock import paper_control_lock, paper_submission_lock

KIND = "dia_base_sequential_quote_runtime_v1"
HARD_EXPIRY = datetime(2026, 11, 14, tzinfo=UTC)


def aware(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("aware actual clock required")
    return result.astimezone(UTC)


def load_scope(root: Path, binding: dict, now: datetime):
    auth = json.loads(bound_bytes(root, binding))
    if (
        auth.get("kind") != KIND
        or auth.get("account") != "quant2"
        or auth.get("paper_only") is not True
        or auth.get("active") is not True
        or auth.get("orders_permitted") is not True
        or auth.get("allocated_usd") != 20000
        or auth.get("policy") != "DIA_BASE"
        or auth.get("long_cash_only") is not True
        or auth.get("daily_loss_halt") != 0.05
        or auth.get("drawdown_kill") != 0.25
    ):
        raise ValueError("exact bounded source-method authority absent")
    if (
        not aware(auth["authorized_at"])
        <= now
        < min(aware(auth["expires_at"]), aware(auth["account_authority_expires_at"]), HARD_EXPIRY)
    ):
        raise ValueError("authority inactive/expired")
    for key in (
        "account_scope",
        "spec",
        "scientific_contract",
        "source_acceptance",
        "current_operating_input",
        "implementation_review",
        "native_acceptance",
    ):
        bound_bytes(root, auth["bindings"][key])
    account_scope = json.loads(bound_bytes(root, auth["bindings"]["account_scope"]))
    if (
        account_scope.get("status") != "accepted_account_sleeve_scope"
        or account_scope.get("account_hash") != auth.get("account_hash")
        or account_scope.get("capital_usd") != 20000
        or account_scope.get("foreign_positions") != auth.get("foreign_positions")
        or account_scope.get("scope_conflicts_verified") is not True
    ):
        raise ValueError("actual accepted account/funds/ownership scope absent")
    contract = json.loads(bound_bytes(root, auth["bindings"]["scientific_contract"]))
    if auth.get("universe") != contract.get("output_identity"):
        raise ValueError("runtime universe differs from exact scientific receiver")
    native = json.loads(bound_bytes(root, auth["bindings"]["native_acceptance"]))
    if (
        native.get("accepted") is not True
        or native.get("scope") != KIND
        or native.get("code_bindings") != auth["code_bindings"]
    ):
        raise ValueError("actual native acceptance not bound to this runtime")
    for b in auth["code_bindings"]:
        bound_bytes(root, b)
    if not any(
        Path(b["path"]).resolve() == Path(__file__).resolve() for b in auth["code_bindings"]
    ):
        raise ValueError("runtime code not in authority")
    source = json.loads(bound_bytes(root, auth["bindings"]["source_acceptance"]))
    if source.get("current_SIP_verified") is not True or source.get("feed") != "sip":
        raise ValueError("required current source is not accepted")
    current_input = json.loads(bound_bytes(root, auth["bindings"]["current_operating_input"]))
    from open_composer.market_sessions import NEW_YORK

    if (
        current_input.get("accepted") is not True
        or current_input.get("execution_units_checked") is not True
        or current_input.get("account_hash") != auth["account_hash"]
        or current_input.get("session_date") != now.astimezone(NEW_YORK).date().isoformat()
        or not aware(current_input["received_at"]) <= now < aware(current_input["valid_until"])
        or not current_input.get("source_bindings")
    ):
        raise ValueError("actual current-session unit/input reception absent or stale")
    for b in current_input["source_bindings"]:
        bound_bytes(root, b)
    _require_kill_switch_clear(root)
    return auth


class SourceMethodRuntime:
    """One supplied current batch; no retries or implicit historical adoption.

    A genuine authenticated observation receiver must produce the bound current
    account/input envelope. Its independent native acceptance is mandatory;
    arbitrary JSON booleans or old successful research hashes cannot replace it.
    """

    def __init__(
        self,
        root: Path,
        *,
        authority: dict,
        state_directory: Path,
        journal_directory: Path,
        client_factory,
        clock=lambda: datetime.now(UTC),
    ):
        self.root, self.authority, self.clock = root, copy.deepcopy(authority), clock
        self.auth = load_scope(root, self.authority, clock())
        if (
            state_directory.resolve() != Path(self.auth["state_directory"]).resolve()
            or journal_directory.resolve() != Path(self.auth["journal_directory"]).resolve()
        ):
            raise ValueError("runtime state/journal root differs from scoped owned book")
        self.store = SourceStateCheckpoint(
            state_directory, account_hash=self.auth["account_hash"], sleeve_id="dia-base"
        )
        self.journal = SourceDispatchJournal(journal_directory)
        self.client_factory = client_factory
        self.current = None
        self.gateway = None
        self.observed_binding = None
        self._operation_held = False

    @contextmanager
    def session(self):
        if self._operation_held:
            raise ValueError("nested account operation")
        with source_account_operation(self.root):
            self._operation_held = True
            try:
                yield self
            finally:
                self._operation_held = False
                if self.gateway is not None:
                    self.gateway.close()

    def connect(self):
        if not self._operation_held:
            raise ValueError("existing account lock required before client")
        self.auth = load_scope(self.root, self.authority, self.clock())
        from open_composer.intraday_runner.source_scientific_entry import kernel_evidence

        kernel_evidence()
        if self.store.load() is None:
            raise ValueError("accepted initial checkpoint absent")
        if self.gateway is None:
            self.gateway = SourceBoundedGateway(
                self.client_factory(),
                journal=self.journal,
                account_hash=self.auth["account_hash"],
                authorized_at=aware(self.auth["authorized_at"]),
                expires_at=min(
                    aware(self.auth["expires_at"]),
                    aware(self.auth["account_authority_expires_at"]),
                    HARD_EXPIRY,
                ),
                guard=self._guard,
                read_guard=self._read_guard,
                clock=self.clock,
            )
        elif self.gateway.closed:
            raise ValueError("one-shot gateway already closed")
        return self.gateway

    def capture_observation(self, *, quotes, directory):
        """Authenticate/reconcile using the SAME client later permitted to send."""
        if not self._operation_held:
            raise ValueError("existing account locks must cover observation through dispatch")
        with paper_submission_lock(self.root), paper_control_lock(self.root):
            self.connect()
            try:
                self.observed_binding = capture_current(
                    self.root,
                    self.gateway.client,
                    self.auth,
                    self.store.load(),
                    quotes=quotes,
                    journal=self.journal,
                    directory=directory,
                    clock=self.clock,
                )
            except BaseException:
                self.gateway.close()
                raise
            return copy.deepcopy(self.observed_binding)

    def _observation(self, binding):
        if self.gateway is None or binding != self.observed_binding:
            raise ValueError("current observation must use this exact live client instance")
        item = json.loads(bound_bytes(self.root, binding))
        admission = json.loads(bound_bytes(self.root, item["receiver_acceptance"]))
        if admission != json.loads(
            bound_bytes(self.root, self.auth["bindings"]["native_acceptance"])
        ):
            raise ValueError("observation receiver not accepted for current scope")
        if admission.get("accepted") is not True or admission.get("scope") != KIND:
            raise ValueError("authenticated current observation receiver unavailable")
        if (
            item.get("account_hash") != self.auth["account_hash"]
            or item.get("complete") is not True
        ):
            raise ValueError("current account identity/coverage unresolved")
        if item.get("conflicts") is not False or item.get("all_owned_events_applied") is not True:
            raise ValueError("cross-strategy ownership or actual fill prefix unresolved")
        if (
            not aware(item["started_at"])
            <= aware(item["completed_at"])
            <= self.clock()
            < aware(item["valid_until"])
        ):
            raise ValueError("current observation expired or future")
        if aware(item["valid_until"]) > aware(item["completed_at"]) + timedelta(seconds=15):
            raise ValueError("observation validity cannot exceed fifteen seconds")
        for b in item["captures"]:
            bound_bytes(self.root, b)
        return item

    def _read_guard(self):
        if load_scope(self.root, self.authority, self.clock()) != self.auth:
            raise ValueError("actual read scope changed")

    def _guard(self, request, *, cancellation=False):
        auth = load_scope(self.root, self.authority, self.clock())
        if auth != self.auth or self.current is None:
            raise ValueError("runtime scope changed or observation absent")
        obs = self._observation(self.current["binding"])
        if obs != self.current["value"]:
            raise ValueError("observation changed before transport")
        revision = self.store.load()
        if revision is None or _hash(revision) != self.current["head"]:
            raise ValueError("reservation checkpoint changed before transport")
        if (
            revision["snapshot"]["evidence"]
            .get("dispatch_intents", {})
            .get(request["client_order_id"], {})
            .get("attempted")
            is not True
        ):
            raise ValueError("durable attempt witness absent before transport")
        if request["client_order_id"] not in revision["snapshot"]["pending"]:
            raise ValueError("current own reservation missing")
        if not cancellation:
            if obs.get("tradable", {}).get(request["symbol"]) is not True:
                raise ValueError("actual asset not verified tradable")
            if request["side"] == "buy" and any(
                not held_quote_fresh(stamp, self.clock())
                for stamp in obs.get("held_quote_ns", {}).values()
            ):
                raise ValueError("held valuation quotes expired before new risk")
            if obs["new_risk_allowed"] is not True and request["side"] == "buy":
                raise ValueError("new-risk halt")
            require_window(
                self.clock(),
                date.fromisoformat(request["execution_day"]),
                request["side"],
                authorized_at=aware(auth["authorized_at"]),
                expires_at=min(
                    aware(auth["expires_at"]),
                    aware(auth["account_authority_expires_at"]),
                    HARD_EXPIRY,
                ),
                cleanup=request.get("cleanup", False),
                own_exit_allowed=request.get("own_exit_allowed", False),
                killed=request.get("killed", False),
            )
            if request.get("cleanup", False):
                if (
                    auth.get("controlled_exit_allowed") is not True
                    or request["side"] != "sell"
                    or request.get("killed") is not obs["risk"]["kill"]
                ):
                    raise ValueError("cleanup is not the current authorized own-risk reduction")

    def _record_intents(self, state, evidence, requests):
        _ensure_durable_directory(self.journal.directory)
        stat = self.journal.directory.stat()
        entries = evidence.setdefault("dispatch_intents", {})
        for request in requests:
            cid = request["client_order_id"]
            if cid in entries:
                raise ValueError("dispatch intent witness already exists")
            entries[cid] = dict(
                attempted=False,
                reservation_sha256=_hash(state.pending[cid]),
                journal_root=str(self.journal.directory),
                journal_identity=[stat.st_dev, stat.st_ino],
            )

    def _mark_attempt(self, cid):
        revision = self.store.load()
        state, fills, fees, evidence = restore(self.root, revision["snapshot"])
        record = evidence.get("dispatch_intents", {}).get(cid)
        if (
            not record
            or record.get("attempted") is not False
            or record.get("reservation_sha256") != _hash(state.pending[cid])
        ):
            raise ValueError("no untouched prepared intent witness")
        record["attempted"] = (
            True  # Durable before journal/callback; uncertainty never releases it.
        )
        saved = self.store.commit(
            snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(revision)
        )
        self.current["head"] = _hash(saved)
        return saved

    def abandon_local(self, cids):
        import fcntl

        from open_composer.intraday_runner.source_terminal_holds import abandon_never_attempted

        if not self._operation_held:
            raise ValueError("existing own account lock required")
        with paper_submission_lock(self.root), paper_control_lock(self.root):
            self.auth = load_scope(self.root, self.authority, self.clock())
            # No directory reconstruction: a missing journal is not absence proof.
            with (self.journal.directory / ".dispatch.lock").open("a+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                revision = self.store.load()
                state, fills, fees, evidence = restore(self.root, revision["snapshot"])
                for cid in cids:
                    state, evidence = abandon_never_attempted(
                        state,
                        fills,
                        fees,
                        evidence,
                        cid=cid,
                        journal=self.journal,
                        observed_at=self.clock().isoformat(),
                    )
                self.store.commit(
                    snapshot(state, fills, fees, evidence=evidence),
                    expected_head_sha256=_hash(revision),
                )
                return dict(
                    status="locally_abandoned_never_attempted_only",
                    ids=cids,
                    broker_calls=0,
                    intent_ids_reusable=False,
                )

    def wave(
        self,
        *,
        commit_binding,
        signal_binding,
        observation_binding,
        metadata_bindings,
        quote_response,
        prior_references,
        side,
        continuity_binding,
        continuity_completion_binding,
        quantity_completion_binding,
    ):
        """Persist all unique reservations before one-shot calls; unknown stays locked."""
        if not self._operation_held:
            raise ValueError("existing account operation lock not held")
        with paper_submission_lock(self.root), paper_control_lock(self.root):
            self.auth = load_scope(self.root, self.authority, self.clock())
            commit = json.loads(bound_bytes(self.root, commit_binding))
            # External committed packet binds original scientifically received
            # forecast, actual prior-close NAV/rawshares and mandatory rights.
            for key in ("forecast_reception", "quantity_input_reception"):
                evidence = json.loads(bound_bytes(self.root, commit[key]))
                if (
                    evidence.get("accepted") is not True
                    or evidence.get("formation_month") != "2026-10"
                ):
                    raise ValueError("actual committed input reception unavailable")
            for phase, completion_binding, input_binding, output_key in (
                ("quantity", quantity_completion_binding, commit_binding, "commit"),
                ("continuity", continuity_completion_binding, continuity_binding, "continuity"),
            ):
                completed = json.loads(bound_bytes(self.root, completion_binding))
                invoked = json.loads(bound_bytes(self.root, completed["job"]))
                produced = json.loads(bound_bytes(self.root, completed["result"]))
                if (
                    completed.get("exit_code") != 0
                    or completed.get("success") is not True
                    or invoked.get("phase") != phase
                    or invoked.get("authority") != self.authority
                    or invoked.get("code_bindings") != self.auth["code_bindings"]
                    or produced.get(output_key) != input_binding
                ):
                    raise ValueError("actual native input/output completion chain differs")
            proof = json.loads(bound_bytes(self.root, continuity_binding))
            completion = json.loads(bound_bytes(self.root, quantity_completion_binding))
            if (
                completion.get("exit_code") != 0
                or completion.get("commit_sha256") != _hash(commit)
                or aware(completion["completed_at"]) > aware(commit["committed_at"])
            ):
                raise ValueError("quantity native completion was missing/late")
            confirm_continuity(commit, proof, actual_sealed_at=completion["completed_at"])
            obs = self._observation(observation_binding)
            revision = self.store.load()
            if revision is None:
                raise ValueError("no accepted initial sleeve checkpoint")
            state, fills, fees, evidence = restore(self.root, revision["snapshot"])
            if obs["owned_state_sha256"] != _hash(revision):
                raise ValueError("account reconciliation differs from current owned checkpoint")
            original_state = copy.deepcopy(state)
            excluded = {}
            if side == "buy":
                from datetime import time

                from open_composer.market_sessions import NEW_YORK

                cutoff = datetime.combine(
                    date.fromisoformat(commit["execution_day"]), time(9, 40), NEW_YORK
                )
                state, fills, fees, evidence, excluded = eligible_reservation_copy(
                    self.root, self.store, revision, cutoff
                )
            prepared, wave = prepare_wave(
                root=self.root,
                metadata_bindings=metadata_bindings,
                state=state,
                commit=commit,
                commit_sha256=_hash(commit),
                universe=set(self.auth["universe"]),
                now=self.clock(),
                side=side,
                authorized_at=aware(self.auth["authorized_at"]),
                expires_at=min(
                    aware(self.auth["expires_at"]),
                    aware(self.auth["account_authority_expires_at"]),
                    HARD_EXPIRY,
                ),
                quote_response=quote_response,
                prior_references=prior_references,
                accepted_unborrowed_capacity=obs["unborrowed_new_capacity"],
                sleeve_new_gross_capacity=obs["sleeve_new_gross_capacity"],
                fee_buffer_rate=self.auth["fee_buffer_rate"],
                new_risk_allowed=obs["new_risk_allowed"],
                global_stop=obs["global_stop"],
            )
            if side == "buy":
                prepared = restore_excluded_proceeds(original_state, prepared, excluded)
            # Risk latches are durable even for a no-order observation.
            evidence.update({k: obs["risk"][k] for k in ("daily_halt", "kill", "high_water")})
            # No source request/order or client construction when no action.
            if not wave["requests"]:
                self.store.commit(
                    snapshot(prepared, fills, fees, evidence=evidence),
                    expected_head_sha256=_hash(revision),
                )
                return {
                    "status": "no_requested_orders",
                    "wave": wave,
                    "account_ready": True,
                    "fills_proven": False,
                }
            self._record_intents(prepared, evidence, wave["requests"])
            saved = self.store.commit(
                snapshot(prepared, fills, fees, evidence=evidence),
                expected_head_sha256=_hash(revision),
            )
            self.current = dict(
                binding=copy.deepcopy(observation_binding), value=obs, head=_hash(saved)
            )
            gateway = self.gateway
            if gateway is None:
                raise ValueError("same authenticated gateway absent")
            results = []
            try:
                for request in wave["requests"]:
                    request["execution_day"] = commit["execution_day"]
                    saved = self._mark_attempt(request["client_order_id"])
                    durable = {**saved["snapshot"], "account_hash": self.auth["account_hash"]}
                    row = self.journal.dispatch_once(
                        request,
                        reservation_snapshot=durable,
                        signal_binding=signal_binding,
                        execution_day=date.fromisoformat(commit["execution_day"]),
                        authorized_at=aware(self.auth["authorized_at"]),
                        expires_at=min(
                            aware(self.auth["expires_at"]),
                            aware(self.auth["account_authority_expires_at"]),
                            HARD_EXPIRY,
                        ),
                        submit=gateway.submit,
                        revalidate=lambda r: self._guard(r),
                        clock=self.clock,
                    )
                    results.append(row)
                    cid = request["client_order_id"]
                    self.journal.cancel_own_remainder_once(
                        cid,
                        authorized_at=aware(self.auth["authorized_at"]),
                        expires_at=min(
                            aware(self.auth["expires_at"]),
                            aware(self.auth["account_authority_expires_at"]),
                            HARD_EXPIRY,
                        ),
                        cancel=lambda broker_id, current_cid=cid: gateway.cancel(
                            current_cid, broker_id
                        ),
                        revalidate=lambda r: self._guard(r["request"], cancellation=True),
                        clock=self.clock,
                    )
            finally:
                gateway.close()
            return dict(
                status="attempted_reconciliation_required", journal=results, fills_proven=False
            )

    def closeout(self, *, observation_binding, quotes, quote_cutoff, signal_binding):
        """One bounded owned-only exit attempt; frozen names/rights stay outstanding."""
        import math

        from open_composer.intraday_runner.source_method_bindings import source_module
        from open_composer.intraday_runner.source_method_controls import live_quote_ok
        from open_composer.market_sessions import NEW_YORK

        if not self._operation_held:
            raise ValueError("existing account locks must cover closeout")
        with paper_submission_lock(self.root), paper_control_lock(self.root):
            auth = load_scope(self.root, self.authority, self.clock())
            if auth.get("controlled_exit_allowed") is not True:
                raise ValueError("owned cleanup authority absent")
            obs = self._observation(observation_binding)
            day = self.clock().astimezone(NEW_YORK).date()
            expiry = min(
                aware(auth["expires_at"]), aware(auth["account_authority_expires_at"]), HARD_EXPIRY
            )
            require_window(
                self.clock(),
                day,
                "sell",
                authorized_at=aware(auth["authorized_at"]),
                expires_at=expiry,
                cleanup=True,
                own_exit_allowed=True,
                killed=obs["risk"]["kill"],
            )
            revision = self.store.load()
            state, fills, fees, evidence = restore(self.root, revision["snapshot"])
            if obs["owned_state_sha256"] != _hash(revision):
                raise ValueError("closeout state drift")
            # Cancel/receipt reconciliation must finish first; an unknown or
            # pending order is not silently treated as released funded inventory.
            if any(v["side"] != "liability_hold" for v in state.pending.values()):
                raise ValueError("pending own orders require reconciliation before closeout")
            cash = source_module(self.root, "cash")
            due = cash.cash_due_date(day.isoformat(), cash.settlement_calendar())
            requests = []
            frozen = []
            for symbol in sorted(state.cashbook.lots):
                held = state.cashbook.quantity(symbol)
                if not held:
                    continue
                quote = quotes.get(symbol)
                if (
                    symbol not in auth["held_asset_universe"]
                    or not quote
                    or not live_quote_ok(quote, self.clock(), quote_cutoff)
                    or obs.get("tradable", {}).get(symbol) is not True
                ):
                    frozen.append(
                        dict(
                            symbol=symbol,
                            quantity=held,
                            reason="no verified tradable current own exit",
                        )
                    )
                    continue
                quantity = min(math.floor(held + 1e-9), quote["bid_shares"])
                if quantity <= 0:
                    frozen.append(
                        dict(symbol=symbol, quantity=held, reason="no whole displayed exit")
                    )
                    continue
                cid = f"dia-base-{day.isoformat()}-exit-{symbol}"
                reservation = state.reserve_sell(
                    cid,
                    symbol,
                    quantity,
                    quote["bid"],
                    day.isoformat(),
                    due,
                    fee_buffer_rate=auth["fee_buffer_rate"],
                )
                requests.append(
                    dict(
                        client_order_id=cid,
                        symbol=symbol,
                        side="sell",
                        qty=quantity,
                        type="limit",
                        time_in_force="day",
                        limit_price=quote["bid"],
                        reservation=reservation,
                        quote=quote,
                        execution_day=day.isoformat(),
                        cleanup=True,
                        own_exit_allowed=True,
                        killed=obs["risk"]["kill"],
                        quote_cutoff=quote_cutoff.isoformat(),
                    )
                )
            evidence.update({k: obs["risk"][k] for k in ("daily_halt", "kill", "high_water")})
            self._record_intents(state, evidence, requests)
            saved = self.store.commit(
                snapshot(state, fills, fees, evidence=evidence),
                expected_head_sha256=_hash(revision),
            )
            self.current = dict(binding=observation_binding, value=obs, head=_hash(saved))
            results = []
            for request in requests:
                saved = self._mark_attempt(request["client_order_id"])
                row = self.journal.dispatch_once(
                    request,
                    reservation_snapshot={
                        **saved["snapshot"],
                        "account_hash": auth["account_hash"],
                    },
                    signal_binding=signal_binding,
                    execution_day=day,
                    authorized_at=aware(auth["authorized_at"]),
                    expires_at=expiry,
                    submit=self.gateway.submit,
                    revalidate=lambda r: self._guard(r),
                    clock=self.clock,
                )
                results.append(row)
                cid = request["client_order_id"]
                self.journal.cancel_own_remainder_once(
                    cid,
                    authorized_at=aware(auth["authorized_at"]),
                    expires_at=expiry,
                    cancel=lambda bid, current_cid=cid: self.gateway.cancel(current_cid, bid),
                    revalidate=lambda r: self._guard(r["request"], cancellation=True),
                    clock=self.clock,
                )
            return dict(
                status="controlled_owned_exit_attempts_only",
                requests=results,
                frozen=frozen,
                flat_certified=False,
            )

    def receive_fill(self, *, capture_binding, ordinal, cid):
        """Apply one authenticated captured activity and checkpoint together."""
        if not self._operation_held:
            raise ValueError("existing account operation lock required for fill reception")
        with paper_submission_lock(self.root), paper_control_lock(self.root):
            # Read/receipt repair is separately permitted only within this scope;
            # expiry does not silently create indefinite order/exit permission.
            load_scope(self.root, self.authority, self.clock())
            revision = self.store.load()
            if revision is None:
                raise ValueError("missing original checkpoint")
            state, fills, fees, evidence = restore(self.root, revision["snapshot"])
            before_sales = {s["id"] for s in state.cashbook.sales}
            state, fills, result = apply_bound_fill(
                self.root,
                state,
                fills,
                receipt_binding=capture_binding,
                ordinal=ordinal,
                journal_record=self.journal.receive(cid),
                expected_account_hash=self.auth["account_hash"],
                observed_now=self.clock(),
            )
            if result["status"] == "already_applied":
                return result
            created_sales = [s for s in state.cashbook.sales if s["id"] not in before_sales]
            if created_sales:
                if len(created_sales) != 1:
                    raise ValueError("one actual sell fill must create one unique AR")
                fid = result["execution"]["fill_id"]
                evidence.setdefault("sale_origins", {})[created_sales[0]["id"]] = {
                    "fill_id": fid,
                    "generation": revision["generation"] + 1,
                }
            saved = self.store.commit(
                snapshot(state, fills, fees, evidence=evidence),
                expected_head_sha256=_hash(revision),
            )
            # This clock is sampled AFTER full checkpoint file/directory/head
            # publication returned. It is not the pure transition's pre-I/O clock.
            completed = self.clock()
            if created_sales:
                proof = dict(
                    fill_id=fid,
                    sale_id=created_sales[0]["id"],
                    revision_sha256=_hash(saved),
                    receipt_record_sha256=_hash(fills[fid]),
                    checkpoint_completed_at=completed.isoformat(),
                )
                path = application_path(self.store.directory, fid)
                _ensure_durable_directory(path.parent)
                if path.exists():
                    raise ValueError("application completion proof already exists")
                _atomic_write_text(path, json.dumps(proof, indent=2) + "\n")
            return result
