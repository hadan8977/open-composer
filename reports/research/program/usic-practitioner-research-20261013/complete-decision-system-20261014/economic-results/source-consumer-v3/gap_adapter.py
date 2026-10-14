"""Existing Nautilus policy adapter with isolated gap and rejection lifecycles.

Broker election remains unknown. Synthetic depth and OHLC/observed-BBO stitching
are explicitly conditional experiments, not an executable broker certificate.
"""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from consumer_admission import bind, receipt, verify_bindings
from continuation_admission import current_grant, rearm
from decision_system import DecisionSystem, Intent
from nautilus_policy_adapter import MartinBoundaryData, MartinNativeStrategy
from nautilus_trader.model.identifiers import ClientOrderId


def actual_admission(job, review_path):
    if job is None:
        raise ValueError("actual_source_consumer_requires_bound_current_admission")
    current_grant()
    proof = json.loads(review_path.read_text())
    assert proof["verdict"] == "approve_implementation"
    assert proof["author"] != proof["reviewer"]
    assert proof["actual_source_consumer_admitted"] is True
    row = receipt(job)
    assert row["pid"] == __import__("os").getpid() and row["status"] == "running"
    assert row["binding"]["affected_review"] == bind(review_path)
    assert row["planned_entry"] in {"consumer_probe", "matched_block"}
    assert row["current_native"]["status"] == "ok"
    verify_bindings(row["current_native_dossier"])
    verify_bindings(proof["bindings"])
    rearm(job)  # Actual childCPU deducted before heavy work, including standalone.


class GapDecisionSystem(DecisionSystem):
    def step(self, frame, book):
        # Daily holding tests come from the independent official-daily event.
        # Original completed intraday entry/confluence/partial-strength is intact.
        frame = replace(
            frame, trail_daily_close=None, trail_daily_ema9=None, completed_sessions_since_entry=0
        )
        return super().step(frame, book)


class GapNativeStrategy(MartinNativeStrategy):
    def __init__(self, config):
        super().__init__(config)
        self.policy = GapDecisionSystem(
            config.parameters,
            config.candidate,
            route=config.route,
            cost_bps_per_side=config.cost_bps_per_side,
        )

    def _daily_holding(self, data):
        if self.book.path_unknown:
            return self._quarantine(data, "boundary:holding_daily")
        self.session, self.month = data.session_ordinal, data.month
        if self.partial_fills:
            return self.book.mark_unknown("partial remainder before holding daily event")
        for row in json.loads(data.frames_json):
            symbol = row["symbol"]
            state = self.policy.states.get(symbol)
            if state is None or state.quantity == 0:
                continue
            if row["status"] != "observed_causal_previous_vendor_daily":
                self.book.mark_unknown("unresolved completed holding daily: " + symbol)
                return
            available = datetime.fromisoformat(row["available_at"])
            now = datetime.fromtimestamp(data.ts_event // 10**9, UTC)
            if not available < now:
                raise ValueError("holding daily not available before current opening clock")
            reason = None
            if row["prior_daily_close"] < row["prior_daily_ema9"]:
                reason = "completed_daily_trend_failure"
            elif (
                self.config.candidate in {"P_HOLD", "P_FEEDBACK", "P_SYSTEM"}
                and self.session - self.entry_sessions[symbol]
                >= self.config.parameters["failure_sessions"]
                and row["prior_daily_close"] <= state.reference
            ):
                reason = "no_followthrough"
            if reason is None:
                continue
            if state.pending_exit:
                if state.pending_exit.id not in self.staged_exits:
                    self._log("holding_exit_already_native_working", state.pending_exit)
                    continue
                self.staged_exits.pop(state.pending_exit.id)
            key = json.dumps([self.config.cell_id, symbol, row["day"], reason, state.quantity])
            intent = Intent(
                hashlib.sha256(key.encode()).hexdigest()[:24],
                symbol,
                "sell",
                now,
                now,
                state.quantity,
                self.marks[symbol],
                None,
                None,
                reason,
                state.epoch,
            )
            state.pending_exit = intent
            self.staged_exits[intent.id] = intent
            self._log(
                "causal_official_daily_holding_exit",
                intent,
                input_reference=row,
                completed_sessions=self.session - self.entry_sessions[symbol],
            )

    def on_data(self, data):
        if not isinstance(data, MartinBoundaryData):
            return super().on_data(data)
        if data.stage == "open_entries" and not self.book.path_unknown:
            return self._open_entries_ask_guard(data)
        if data.stage == "holding_daily":
            return self._daily_holding(data)
        if data.stage not in {"source_bar_absent", "source_unresolved"}:
            return super().on_data(data)
        if self.book.path_unknown:
            return self._quarantine(data, "boundary:" + data.stage)
        self.session, self.month = data.session_ordinal, data.month
        if self.partial_fills:
            self.book.mark_unknown("partial remainder unacknowledged at source boundary")
            return
        for row in json.loads(data.frames_json):
            symbol = row["symbol"]
            state = self.policy.states.get(symbol)
            if state:
                state.touch_end = None  # Missing bars cannot manufacture support or an entry.
            active = bool(
                state
                and (state.quantity or state.pending or state.pending_exit or state.protective)
            )
            if data.stage == "source_unresolved" and active:
                self.book.mark_unknown(
                    "source price path unresolved: " + row["reason"] + ": " + symbol
                )
            self._log(
                data.stage,
                None,
                symbol=symbol,
                at_ns=data.ts_event,
                source_reference=row,
                active=active,
                sticky_unknown=self.book.path_unknown,
            )

    def on_order_rejected(self, event):
        if self.book.path_unknown:
            return self._quarantine(event, "rejected")
        native_id = str(event.client_order_id)
        intent = self.native_intents.get(native_id)
        state = self.policy.states.get(intent.symbol) if intent else None
        order = self.cache.order(event.client_order_id)
        # Only an identified, terminal rejected protective order has a known
        # reconciliation. All other rejections retain the original unknown gate.
        if not (
            intent
            and intent.action == "protect"
            and state
            and state.quantity > 0
            and state.protective
            and state.protective.id == native_id
            and order is not None
            and order.is_closed
            and order.filled_qty.as_double() == 0
            and intent.quantity == state.quantity == state.protective.quantity
            and state.pending_exit is None
            and state.submitted_planned_R0 > 0
        ):
            return super().on_order_rejected(event)
        state.protective = None
        now = datetime.fromtimestamp(event.ts_event // 10**9, UTC) + timedelta(
            microseconds=(event.ts_event % 10**9) // 1000
        )
        sell = Intent(
            native_id + "-rejection-liquidate",
            intent.symbol,
            "sell",
            now,
            now,
            state.quantity,
            state.fill_price,
            None,
            None,
            "protective_rejection_safety_liquidation",
            state.epoch,
        )
        state.pending_exit = sell
        self._log(
            "terminal_protective_rejection_safety_exit",
            intent,
            quantity=state.quantity,
            rejected_order_id=native_id,
            at_ns=event.ts_event,
        )
        self._submit(
            sell
        )  # Actual native acceptance/fill/partial/cancel reports, never a fabricated exit.

    def on_order_denied(self, event):
        # A denied order need not be in the native cache. It is not certified by
        # the protective-rejection branch and stays unknown unless terminal.
        self.on_order_rejected(event)

    def _terminal_fill(self, intent, qty, price, fee, now, report_id, *, cancelled_quantity):
        super()._terminal_fill(
            intent, qty, price, fee, now, report_id, cancelled_quantity=cancelled_quantity
        )
        state = self.policy.states[intent.symbol]
        if (
            intent.reason in {"completed_daily_trend_failure", "no_followthrough"}
            and cancelled_quantity > 0
            and state.quantity > 0
            and not self.book.path_unknown
            and state.pending_exit is None
        ):
            protective = state.protective
            order = self.cache.order(ClientOrderId(protective.id)) if protective else None
            if order is None or not order.is_open:
                self.book.mark_unknown("holding remainder lacks cancellable protection")
                return
            follow = Intent(
                intent.id + "-remain-" + str(state.quantity),
                intent.symbol,
                "sell",
                now,
                now,
                state.quantity,
                price,
                None,
                None,
                intent.reason,
                state.epoch,
            )
            state.pending_exit = follow
            self.cancel_then_sell[protective.id] = follow
            self.cancel_order(order)
            self._log(
                "full_holding_exit_remaining_native",
                follow,
                cancelled_previous_quantity=cancelled_quantity,
            )
        if intent.reason == "protective_rejection_safety_liquidation":
            state = self.policy.states[intent.symbol]
            if not state.quantity and not self.book.path_unknown:
                state.status = "stopped"
                state.last_stopout_at = now
                self._log(
                    "safety_liquidation_stopout",
                    intent,
                    at=now.isoformat(),
                    initial_R_basis="unchanged_exante_submitted_reference_minus_stop",
                )

    def _open_entries_ask_guard(self, data):
        self.session, self.month = data.session_ordinal, data.month
        if self.partial_fills:
            self.book.mark_unknown("partial remainder unacknowledged at opening source boundary")
            return
        now = datetime.fromtimestamp(data.ts_event / 1e9, tz=UTC)
        for intent in list(self.staged_entries.values()):
            tick = self.cache.quote_tick(self.ids[intent.symbol])
            mark = tick.ask_price.as_double() / self.unit_factors[intent.symbol] if tick else None
            guard = intent.reference * (1 + self.config.parameters["entry_price_cap_bps"] / 10000)
            if mark is None:
                self.book.mark_unknown("missing scheduled opening price")
                return
            if self.config.route == "market" and mark > guard:
                self.policy.entry_report(
                    intent.symbol,
                    now,
                    filled=False,
                    order_id=intent.id,
                    report_id=intent.id + "-guard-reject",
                    terminal=True,
                    cancelled_quantity=intent.quantity,
                )
                self.book.terminal_entry(intent.id, quantity=0, price=0, fee=0)
                self.staged_entries.pop(intent.id, None)
                self._log("guarded_open_nonfill", intent)
                continue
            if self.config.route == "capped":
                opened = intent.created_at.astimezone(ZoneInfo("America/New_York")).replace(
                    hour=9, minute=30, second=0, microsecond=0
                )
                deadline = int(
                    (opened.timestamp() + self.config.parameters["entry_cutoff_minute"] * 60) * 1e9
                )
                self.limit_expiry[intent.id] = min(
                    int(intent.created_at.timestamp() * 1e9) + 5 * 60 * 1_000_000_000, deadline
                )
            self._submit(intent)
            self.staged_entries.pop(intent.id, None)
            if intent.id in self.limit_expiry and self.limit_expiry[intent.id] <= data.ts_event:
                order = self.cache.order(ClientOrderId(intent.id))
                if order is not None and order.is_open:
                    self.cancel_order(order)
