"""Native order/account mapping for the reviewed policy, no autonomous entry.

An admitted driver supplies explicit close, open-exit and open-entry boundary
packets around declared price-path data. This module never invents price data,
calls a broker, or starts a backtest. Partial fills require actual remainder
cancellation before the next price event and immediate actual-share protection.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import msgspec
from decision_system import Anchor, DecisionSystem, Frame, Intent, Support
from native_book_view import NativeBookView
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.data import Data
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.data import DataType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId
from nautilus_trader.model.objects import Currency
from nautilus_trader.trading.strategy import Strategy


class MartinBoundaryData(Data):
    __annotations__ = {
        "stage": str,
        "frames_json": str,
        "session_ordinal": int,
        "month": str,
    }


MartinBoundaryData = customdataclass(MartinBoundaryData)


class MartinAdapterConfig(StrategyConfig, frozen=True):
    instrument_ids: list[str]
    parameters: dict
    candidate: str
    route: str
    cost_bps_per_side: float
    spec_sha256: str
    input_sha256: str
    contract_sha256: str
    cell_id: str = "inert"
    initial_physical_shares_per_native_unit: dict = {}
    optimize_runtime: bool = True


def decode_frame(row: dict) -> Frame:
    row = dict(row)
    for k in ("start", "end", "context_available_at"):
        row[k] = datetime.fromisoformat(row[k])
    row["supports"] = tuple(
        Support(s["measure_id"], s["price"], datetime.fromisoformat(s["available_at"]))
        for s in row["supports"]
    )
    anchors = []
    for obj in row.get("anchors", []):
        a = dict(obj)
        a["available_at"] = datetime.fromisoformat(a["available_at"])
        if a.get("last_touch_at"):
            a["last_touch_at"] = datetime.fromisoformat(a["last_touch_at"])
        anchors.append(Anchor(**a))
    row["anchors"] = tuple(anchors)
    return Frame(**row)


class FrameDecoder:
    """Reuse only exactly identical immutable values; six latest symbols."""

    def __init__(self):
        self.latest = {}

    def decode(self, source):
        row = dict(source)
        key = (
            row["context_available_at"],
            tuple(tuple(s.items()) for s in row["supports"]),
            tuple(tuple(a.items()) for a in row.get("anchors", [])),
        )
        cached = self.latest.get(row["symbol"])
        if cached is None or cached[0] != key:
            parsed = decode_frame(source)
            cached = (key, parsed.context_available_at, parsed.supports, parsed.anchors)
            self.latest[row["symbol"]] = cached
        row["start"] = datetime.fromisoformat(row["start"])
        row["end"] = datetime.fromisoformat(row["end"])
        row["context_available_at"], row["supports"], row["anchors"] = cached[1:]
        return Frame(**row)


class MartinNativeStrategy(Strategy):
    def __init__(self, config: MartinAdapterConfig):
        super().__init__(config)
        self.policy = DecisionSystem(
            config.parameters,
            config.candidate,
            route=config.route,
            cost_bps_per_side=config.cost_bps_per_side,
        )
        self.book = NativeBookView(config.parameters, config.cost_bps_per_side)
        self.ids = {
            InstrumentId.from_str(x).symbol.value: InstrumentId.from_str(x)
            for x in config.instrument_ids
        }
        self.venue = next(iter(self.ids.values())).venue
        if any(x.venue != self.venue for x in self.ids.values()):
            raise ValueError("one common simulated cash venue required")
        self.marks: dict[str, float] = {}
        self.staged_entries: dict[str, Intent] = {}
        self.staged_exits: dict[str, Intent] = {}
        self.native_intents: dict[str, Intent] = {}
        self.cancel_then_sell: dict[str, Intent] = {}
        self.limit_expiry: dict[str, int] = {}
        self.session = 0
        self.month = ""
        self.audit: list[dict] = []
        self.partial_fills: dict[str, dict] = {}
        self.cancel_ack_ids: set[str] = set()
        self.entry_sessions: dict[str, int] = {}
        self.unit_factors = {
            s: config.initial_physical_shares_per_native_unit.get(s, 1.0) for s in self.ids
        }
        self.snapshots = []
        self.last_known_snapshot = None
        self.uninterpretable_counts = Counter()
        self.book.unknown_callback = self._capture_known_prefix
        self.frame_decoder = FrameDecoder() if config.optimize_runtime else None
        self.runtime_active_symbols = None  # None is the unchanged full feed.
        self.runtime_prior_leadership = {}

    def _capture_known_prefix(self, receipt):
        receipt.update(
            at_ns=self.clock.timestamp_ns(),
            session=self.session,
            quantities={s: st.quantity for s, st in self.policy.states.items()},
            statuses={s: st.status for s, st in self.policy.states.items()},
            prices=dict(self.marks),
            last_known_NAV=self.last_known_snapshot,
        )
        self._log("first_unknown", None, first_unknown=receipt)

    def _quarantine(self, event, kind):
        self.uninterpretable_counts[kind] += 1
        if sum(self.uninterpretable_counts.values()) > 64:
            return  # Bounded event witnesses; complete diagnostic counts retained.
        self._log(
            "uninterpretable_native_event",
            None,
            event_kind=kind,
            event_id=str(getattr(event, "id", "")),
            native_order_id=str(getattr(event, "client_order_id", "")),
            event_at_ns=getattr(event, "ts_event", None),
            first_unknown_at_ns=self.book.first_unknown["at_ns"],
        )

    def on_start(self):
        for instrument_id in self.ids.values():
            if self.cache.instrument(instrument_id) is None:
                raise ValueError("missing native instrument")
            self.subscribe_quote_ticks(instrument_id)
        self.subscribe_data(DataType(MartinBoundaryData))

    def on_quote_tick(self, tick):
        if self.book.path_unknown:
            self._quarantine(tick, "quote")
            return
        symbol = tick.instrument_id.symbol.value
        self.marks[symbol] = (tick.bid_price.as_double() + tick.ask_price.as_double()) / (
            2 * self.unit_factors[symbol]
        )

    def _cash(self):
        account = self.portfolio.account(self.venue)
        if account is None:
            raise ValueError("missing native CASH account")
        balance = account.balance_total(Currency.from_str("USD"))
        if balance is None:
            raise ValueError("missing native USD balance")
        return balance.as_double()

    def _view(self, native_cash=None):
        return self.book.view(
            native_cash=self._cash() if native_cash is None else native_cash,
            marks=self.marks,
            states=self.policy.states,
            session=self.session,
            month=self.month,
        )

    def _view_controller_key(self):
        b = self.book
        return (
            b.month,
            b.month_start,
            b.month_peak,
            b.month_new_risk,
            b.pause_session,
            b.closed_at_pause,
            b.resume_session,
            b.resume_peak,
            tuple(b.unsettled),
        )

    def _log(self, action: str, intent: Intent | None, **extra):
        self.audit.append(
            dict(
                action=action,
                intent_id=intent.id if intent else None,
                signal_id=self.config.cell_id + "::" + intent.id if intent else None,
                cell_id=self.config.cell_id,
                spec_sha256=self.config.spec_sha256,
                input_sha256=self.config.input_sha256,
                contract_sha256=self.config.contract_sha256,
                native_at_ns=self.clock.timestamp_ns(),
                **extra,
            )
        )

    def on_data(self, data):
        if not isinstance(data, MartinBoundaryData):
            return
        if self.book.path_unknown:
            self._quarantine(data, "boundary:" + data.stage)
            return
        if data.stage == "inactive_marks":
            for row in msgspec.json.decode(data.frames_json):
                symbol = row["symbol"]
                assert self.runtime_active_symbols is not None
                assert symbol not in self.runtime_active_symbols
                state = self.policy.states.get(symbol)
                assert state is None or not (state.quantity or state.pending or state.pending_exit)
                self.marks[symbol] = row["price"]
            return
        # This mark group has the original quote-only side effects. It must
        # not advance the session/partial-terminal clock ahead of the next
        # original boundary, even on an uninterpretable partial path.
        self.session, self.month = data.session_ordinal, data.month
        if self.partial_fills:
            self.book.mark_unknown("partial remainder unacknowledged at next event boundary")
            return
        if data.stage == "actions":
            for action in json.loads(data.frames_json):
                symbol = action["symbol"]
                state = self.policy.states.get(symbol)
                if action["kind"] != "forward_split":
                    if state and (state.quantity or state.pending):
                        state.path_unknown = True
                        self.book.mark_unknown(
                            "unpriced or unpayable corporate right: " + action["id"]
                        )
                    self._log(
                        "corporate_right",
                        None,
                        action_id=action["id"],
                        symbol=symbol,
                        entitlement=bool(state and state.quantity),
                    )
                    if self.book.path_unknown:
                        return
                    continue
                ratio = action["ratio"]

                def transform(intent, ratio=ratio):
                    if intent is None:
                        return None
                    q = intent.quantity * ratio
                    if not float(q).is_integer():
                        raise ValueError(
                            "fractional corporate right needs separate accepted valuation"
                        )
                    return replace(
                        intent,
                        quantity=int(q),
                        reference=intent.reference / ratio,
                        stop=intent.stop / ratio if intent.stop is not None else None,
                        price_cap=intent.price_cap / ratio
                        if intent.price_cap is not None
                        else None,
                    )

                self.unit_factors[symbol] *= ratio
                if state:
                    state.quantity = int(state.quantity * ratio)
                    state.initial_quantity = int(state.initial_quantity * ratio)
                    for key in ("reference", "initial_stop", "hard_stop"):
                        setattr(state, key, getattr(state, key) / ratio)
                    if state.fill_price is not None:
                        state.fill_price /= ratio
                    state.pending = transform(state.pending)
                    state.pending_exit = transform(state.pending_exit)
                    state.protective = transform(state.protective)
                    state.touch_end = None
                for mapping in (
                    self.native_intents,
                    self.staged_entries,
                    self.staged_exits,
                    self.book.reserved,
                    self.cancel_then_sell,
                ):
                    for key, intent in list(mapping.items()):
                        if intent.symbol == symbol:
                            mapping[key] = transform(intent)
                if symbol in self.book.lots:
                    self.book.lots[symbol].quantity = int(self.book.lots[symbol].quantity * ratio)
                if symbol in self.marks:
                    self.marks[symbol] /= ratio
                self._log(
                    "native_unit_split_coordinate",
                    None,
                    symbol=symbol,
                    ratio=ratio,
                    physical_per_native=self.unit_factors[symbol],
                    action_id=action["id"],
                )
            return
        if data.stage == "missing":
            for symbol in json.loads(data.frames_json):
                state = self.policy.states.get(symbol)
                if state:
                    state.touch_end = None
                    if state.quantity or state.pending or state.pending_exit:
                        state.path_unknown = True
                        self.book.mark_unknown("missing scheduled active minute: " + symbol)
                self._log(
                    "missing_scheduled_minute",
                    None,
                    symbol=symbol,
                    at_ns=data.ts_event,
                    sticky_unknown=self.book.path_unknown,
                )
            return
        if data.stage == "mark":
            cash = self._cash()
            view, _ = self._view(cash)
            self.snapshots.append(
                dict(
                    at_ns=data.ts_event,
                    session=self.session,
                    equity=view.equity,
                    cash=cash,
                    quantities={s: st.quantity for s, st in self.policy.states.items()},
                    daily_close=bool(json.loads(data.frames_json).get("daily_close")),
                    prices=dict(self.marks),
                )
            )
            self.last_known_snapshot = self.snapshots[-1]
            return
        if data.stage == "close":
            for native_id, expiry in list(self.limit_expiry.items()):
                if data.ts_event >= expiry:
                    order = self.cache.order(ClientOrderId(native_id))
                    if order is not None:
                        self.cancel_order(order)
            rows = (
                msgspec.json.decode(data.frames_json)
                if self.frame_decoder
                else json.loads(data.frames_json)
            )
            # Driver binds prior-snapshot ranking, not current event arrival.
            rows.sort(
                key=lambda r: (
                    -r["leadership_score"],
                    -r["prior_dollar_volume"],
                    r["frame"]["symbol"],
                )
            )
            # Synchronous expiry cancellations above have already completed.
            # No close-policy intent is submitted until the next open phase,
            # so cash is constant here; reservations/view still update per row.
            cash = self._cash() if self.frame_decoder else None
            cached_view = None
            for row in rows:
                f = (
                    self.frame_decoder.decode(row["frame"])
                    if self.frame_decoder
                    else decode_frame(row["frame"])
                )
                # All these necessary entry fields are frozen daily context.
                # first_retest, hourly supports, touches and live risk are
                # deliberately excluded: they can change later in this day.
                possible_entry = (
                    f.leadership
                    and f.epoch_valid
                    and f.market not in {"weak", "unknown"}
                    and f.trigger_price_eligible
                    and (self.config.candidate == "P_EMA" or f.shape_ok)
                    and f.ema9_previous is not None
                    and f.ema21_previous is not None
                    and (f.ema9 > f.ema9_previous or f.ema21 > f.ema21_previous)
                )
                self.runtime_prior_leadership[f.symbol] = (f.session, possible_entry, f.end)
                st = self.policy.states.get(f.symbol)
                if (
                    not f.active_data_complete
                    and st is not None
                    and (st.quantity or st.pending or st.pending_exit)
                ):
                    self.policy.step(f, self._view(cash)[0])
                    self.book.mark_unknown("active input interval missing")
                    return
                if cached_view is None:
                    before_controller = self._view_controller_key()
                    view, pause = self._view(cash)
                    # Reuse only an idempotent view. In particular a feedback
                    # pause/recovery transition must be applied again exactly
                    # as in the reference, rather than cached across rows.
                    if self.frame_decoder and self._view_controller_key() == before_controller:
                        cached_view = (view, pause)
                else:
                    view, pause = cached_view
                # Freeze producer/controller correspondence; no ad hoc pause.
                overrides = dict(
                    sessions_since_risk_pause=pause,
                    completed_sessions_since_entry=max(
                        0, self.session - self.entry_sessions.get(f.symbol, self.session)
                    )
                    + int(f.trail_daily_close is not None),
                )
                f = (
                    Frame(**dict(vars(f), **overrides))
                    if self.frame_decoder
                    else replace(f, **overrides)
                )
                for intent in self.policy.step(f, view):
                    if self.runtime_active_symbols is not None:
                        assert intent.symbol in self.runtime_active_symbols, (
                            "causal activity envelope violated"
                        )
                    self._log("signal_before_native_order", intent, at=f.end.isoformat())
                    if intent.action == "buy":
                        self.book.reserve(intent)
                        cached_view = None
                        self.staged_entries[intent.id] = intent
                    else:
                        self.staged_exits[intent.id] = intent
        elif data.stage == "open_exits":
            for intent in sorted(
                self.staged_exits.values(),
                key=lambda i: (
                    i.reason != "completed_daily_trend_failure",
                    i.created_at,
                    i.symbol,
                    i.id,
                ),
            ):
                state = self.policy.states[intent.symbol]
                if state.quantity == 0:
                    self.staged_exits.pop(intent.id, None)
                    continue
                if state.protective is not None:
                    old = state.protective.id
                    order = self.cache.order(ClientOrderId(old))
                    if order is None:
                        self.book.mark_unknown("missing outstanding protective native order")
                        return
                    self.cancel_then_sell[old] = intent
                    self.cancel_order(order)
                else:
                    self.book.mark_unknown("held lot without a protective native order")
                    return
        elif data.stage == "open_entries":
            now = datetime.fromtimestamp(data.ts_event / 1e9, tz=UTC)
            for intent in list(self.staged_entries.values()):
                mark = self.marks.get(intent.symbol)
                guard = intent.reference * (
                    1 + self.config.parameters["entry_price_cap_bps"] / 10000
                )
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
                        (opened.timestamp() + self.config.parameters["entry_cutoff_minute"] * 60)
                        * 1e9
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
        else:
            raise ValueError("unregistered native event phase")

    def _submit(self, intent: Intent):
        if self.book.path_unknown:
            raise ValueError("cannot submit after first unknown")
        if self.runtime_active_symbols is not None:
            assert intent.symbol in self.runtime_active_symbols, "causal activity envelope violated"
        instrument = self.cache.instrument(self.ids[intent.symbol])
        factor = self.unit_factors[intent.symbol]
        units = intent.quantity / factor
        if not float(units).is_integer():
            raise ValueError("native coordinate cannot exactly represent whole physical shares")
        qty = instrument.make_qty(units)
        args = dict(
            instrument_id=instrument.id,
            quantity=qty,
            client_order_id=ClientOrderId(intent.id),
            tags=[intent.reason, self.config.spec_sha256],
        )
        if intent.action == "protect":
            order = self.order_factory.stop_market(
                order_side=OrderSide.SELL,
                trigger_price=instrument.make_price(intent.stop * factor),
                reduce_only=True,
                **args,
            )
        elif intent.action == "buy" and intent.price_cap is not None:
            order = self.order_factory.limit(
                order_side=OrderSide.BUY,
                price=instrument.make_price(intent.price_cap * factor),
                **args,
            )
        else:
            order = self.order_factory.market(
                order_side=OrderSide.BUY if intent.action == "buy" else OrderSide.SELL,
                reduce_only=intent.action == "sell",
                time_in_force=TimeInForce.IOC,
                **args,
            )
        self.native_intents[intent.id] = intent
        self._log("native_submission", intent)
        self.submit_order(order)

    def on_order_canceled(self, event):
        if self.book.path_unknown:
            self._quarantine(event, "canceled")
            return
        native_id = str(event.client_order_id)
        self.cancel_ack_ids.add(native_id)
        now = datetime.fromtimestamp(event.ts_event / 1e9, tz=UTC)
        if native_id in self.partial_fills:
            row = self.partial_fills.pop(native_id)
            self._terminal_fill(
                self.native_intents[native_id],
                row["quantity"],
                row["dollars"] / row["quantity"],
                row["fee"],
                now,
                str(event.id),
                cancelled_quantity=self.native_intents[native_id].quantity - row["quantity"],
            )
            self._log(
                "terminal_partial_cancel_ack",
                self.native_intents[native_id],
                cancelled_quantity=self.native_intents[native_id].quantity - row["quantity"],
            )
            return
        if native_id in self.cancel_then_sell:
            intent = self.cancel_then_sell.pop(native_id)
            self._log("protective_cancel_ack", intent, cancelled_order_id=native_id)
            # Actual cancel acknowledgment precedes sell submission. The
            # policy report later carries this matching canceled order ID.
            self._submit(intent)
            self.staged_exits.pop(intent.id, None)
            return
        intent = self.native_intents.get(native_id)
        if intent is not None and intent.action == "buy":
            state = self.policy.states[intent.symbol]
            if state.quantity:
                self.book.mark_unknown(
                    "nonterminal entry partial requires separate protection acceptance"
                )
                return
            self.policy.entry_report(
                intent.symbol,
                now,
                filled=False,
                order_id=intent.id,
                report_id=str(event.id),
                terminal=True,
                cancelled_quantity=intent.quantity,
                phase="terminal_cancel",
            )
            self.book.terminal_entry(intent.id, quantity=0, price=0, fee=0)
            self.limit_expiry.pop(native_id, None)

    def on_order_filled(self, event):
        if self.book.path_unknown:
            self._quarantine(event, "filled")
            return
        native_id = str(event.client_order_id)
        intent = self.native_intents.get(native_id)
        if intent is None:
            self.book.mark_unknown("unidentified native fill")
            return
        factor = self.unit_factors[intent.symbol]
        qty_value = event.last_qty.as_double() * factor
        if not qty_value.is_integer() or qty_value <= 0:
            self.book.mark_unknown("native quantity does not represent whole physical shares")
            return
        qty = int(qty_value)
        price = event.last_px.as_double() / factor
        fee = event.commission.as_double()
        now = datetime.fromtimestamp(event.ts_event / 1e9, tz=UTC)
        row = self.partial_fills.setdefault(native_id, dict(quantity=0, dollars=0.0, fee=0.0))
        row["quantity"] += qty
        row["dollars"] += qty * price
        row["fee"] += fee
        if row["quantity"] > intent.quantity:
            self.book.mark_unknown("native cumulative fill exceeds frozen quantity")
            return
        if row["quantity"] < intent.quantity:
            order = self.cache.order(event.client_order_id)
            if order is None:
                self.book.mark_unknown("partial fill without cancellable native remainder")
                return
            # The driver binds synchronous zero-latency native cancellation.
            # Its acknowledgment calls _terminal_fill and activates/resizes
            # protection before this price-event callback returns. A driver
            # with deferred cancellation is refused by the consumer seal.
            self.cancel_order(order)
            self._log("native_partial", intent, last_quantity=qty)
            return
        self.partial_fills.pop(native_id)
        self._terminal_fill(
            intent,
            row["quantity"],
            row["dollars"] / row["quantity"],
            row["fee"],
            now,
            str(event.id),
            cancelled_quantity=0,
        )

    def _terminal_fill(self, intent, qty, price, fee, now, report_id, *, cancelled_quantity):
        if self.book.path_unknown:
            raise ValueError("cannot interpret terminal fill after first unknown")
        state = self.policy.states[intent.symbol]
        if intent.action == "buy":
            protective = self.policy.entry_report(
                intent.symbol,
                now,
                filled=True,
                price=price,
                quantity=qty,
                order_id=intent.id,
                report_id=report_id,
                terminal=True,
                cancelled_quantity=cancelled_quantity,
                phase="capped_resting_fill"
                if self.config.route == "capped"
                else "next_scheduled_open",
            )
            self.book.terminal_entry(intent.id, quantity=qty, price=price, fee=fee)
            self.entry_sessions[intent.symbol] = self.session
            self._submit(protective)
        else:
            stopout = intent.action == "protect"
            cancel_ids = (
                (state.pending_exit.id,)
                if stopout and state.pending_exit
                else (
                    (state.protective.id,)
                    if not stopout
                    and state.protective
                    and state.protective.id in self.cancel_ack_ids
                    else ()
                )
            )
            if stopout and state.pending_exit:
                self.staged_exits.pop(state.pending_exit.id, None)
            resized = self.policy.exit_report(
                intent.symbol,
                now,
                qty,
                stopout=stopout,
                order_id=intent.id,
                report_id=report_id,
                terminal=True,
                cancelled_quantity=cancelled_quantity,
                cancelled_order_ids=cancel_ids,
            )
            self.book.terminal_exit(
                intent.symbol, quantity=qty, price=price, fee=fee, session=self.session
            )
            if resized is not None:
                self._submit(resized)
        self.limit_expiry.pop(intent.id, None)
        self._log(
            "native_full_fill", intent, quantity=qty, price=price, fee=fee, at=now.isoformat()
        )

    def on_order_rejected(self, event):
        if self.book.path_unknown:
            self._quarantine(event, "rejected")
            return
        self.book.mark_unknown(
            "native order rejection needs classified terminal/resource reconciliation"
        )
        self._log(
            "unresolved_native_rejection", self.native_intents.get(str(event.client_order_id))
        )

    def on_order_denied(self, event):
        self.on_order_rejected(event)

    def on_stop(self):
        # No terminal liquidation: preserve open tail and order history in the
        # result. A terminal engine stop is not a source exit signal.
        for instrument_id in self.ids.values():
            self.unsubscribe_quote_ticks(instrument_id)
