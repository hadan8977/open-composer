"""Causal Martin-method policy producing intents for an existing execution adapter.

This is a signal/position policy, not a second fill or account engine. Book state
and actual execution reports are supplied by the reference/native consumer.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Anchor:
    id: str
    available_at: datetime
    price: float
    past_touches: int
    last_touch_at: datetime | None


@dataclass(frozen=True)
class Support:
    measure_id: str
    price: float
    available_at: datetime


@dataclass(frozen=True)
class Frame:
    symbol: str
    end: datetime
    start: datetime
    session: str
    epoch: str
    minute: int
    duration: int
    close: float
    low: float
    previous_high: float
    previous_low: float
    day_low: float
    adr: float
    ema9: float
    ema21: float
    previous_daily_close: float
    context_available_at: datetime
    leadership: bool
    market: str
    shape_ok: bool
    first_retest: bool
    supports: tuple[Support, ...]
    anchors: tuple[Anchor, ...] = ()
    trail_daily_close: float | None = None
    trail_daily_ema9: float | None = None
    completed_sessions_since_entry: int = 0
    trigger_price_eligible: bool = True
    past_minute_volume: float = 0
    active_data_complete: bool = True
    base_breakout_level: float | None = None
    sessions_since_risk_pause: int = 0
    ema9_previous: float | None = None
    ema21_previous: float | None = None
    epoch_valid: bool = True


@dataclass(frozen=True)
class Book:
    equity: float
    spendable_cash: float
    gross_notional: float
    initial_risk_dollars: float
    month_entry_risk_dollars: float
    month_start_equity: float
    drawdown_from_recent_peak: float = 0
    prior_closed_R: tuple[float, ...] = ()
    held_or_reserved_names: int = 0


@dataclass(frozen=True)
class Intent:
    id: str
    symbol: str
    action: str
    created_at: datetime
    eligible_after: datetime
    quantity: int
    reference: float
    stop: float | None
    price_cap: float | None
    reason: str
    epoch: str
    reserved_cash: float = 0
    reserved_risk: float = 0


@dataclass
class State:
    status: str = "observe"
    epoch: str = ""
    session: str = ""
    attempts_day: int = 0
    attempts_epoch: int = 0
    touch_end: datetime | None = None
    last_end: datetime | None = None
    pending: Intent | None = None
    quantity: int = 0
    initial_quantity: int = 0
    reference: float = 0
    initial_stop: float = 0
    hard_stop: float = 0
    fill_price: float | None = None
    trimmed: bool = False
    pending_exit: Intent | None = None
    last_stopout_at: datetime | None = None
    audit: list[dict] = field(default_factory=list)
    protective: Intent | None = None
    last_execution_at: datetime | None = None
    report_ids: set[str] = field(default_factory=set)
    path_unknown: bool = False
    submitted_planned_R0: float = 0


def read_parameters(spec: Path) -> dict:
    obj = yaml.safe_load(spec.read_text())
    assert obj["lifecycle"] == "draft" and obj["execution"]["broker"] == "none"
    return obj["notes"]["decision_system"]


def clock_minutes(p: dict, minute: int) -> int | None:
    return next((width for lo, hi, width in p["entry_clock"] if lo <= minute < hi), None)


def select_anchor(
    anchors: tuple[Anchor, ...], at: datetime, *, prior_respect: bool, cap: int
) -> Anchor | None:
    # Caller may supply retrospective candidates; future recognition or touch
    # cannot influence ranking, even if its eventual price fits perfectly.
    known = [
        a
        for a in anchors
        if a.available_at <= at and (a.last_touch_at is None or a.last_touch_at <= at)
    ]
    known = sorted(known, key=lambda a: (a.available_at, a.id), reverse=True)[:cap]
    if not known:
        return None
    return sorted(
        known,
        key=lambda a: (-a.past_touches if prior_respect else 0, -a.available_at.timestamp(), a.id),
    )[0]


class DecisionSystem:
    def __init__(
        self,
        parameters: dict,
        candidate: str = "P_SYSTEM",
        *,
        route: str = "market",
        cost_bps_per_side: float | None = None,
    ):
        self.p = parameters
        self.candidate = candidate
        assert route in {"market", "capped"}
        self.route = route
        self.cost_bps = (
            parameters["primary_cost_per_side_bps"]
            if cost_bps_per_side is None
            else cost_bps_per_side
        )
        self.states: dict[str, State] = {}
        self.epoch_attempts: dict[tuple[str, str], int] = {}
        assert candidate in {
            "B_BREAK",
            "P_EMA",
            "P_SHAPE",
            "P_ANCHOR",
            "P_REENTRY",
            "P_HOLD",
            "P_FEEDBACK",
            "P_SYSTEM",
        }

    def note(self, s: State, f: Frame, reason: str):
        s.audit.append(dict(at=f.end.isoformat(), state=s.status, reason=reason, epoch=f.epoch))

    def intent(
        self, f: Frame, action: str, q: int, ref: float, stop: float | None, reason: str
    ) -> Intent:
        key = json.dumps(
            [
                self.candidate,
                self.route,
                self.cost_bps,
                f.symbol,
                f.end.isoformat(),
                action,
                f.epoch,
                reason,
            ]
        )
        return Intent(
            hashlib.sha256(key.encode()).hexdigest()[:24],
            f.symbol,
            action,
            f.end,
            f.end,
            q,
            ref,
            stop,
            ref * (1 + self.p["entry_price_cap_bps"] / 10000)
            if action == "buy" and self.route == "capped"
            else None,
            reason,
            f.epoch,
        )

    def step(self, f: Frame, book: Book) -> list[Intent]:
        p = self.p
        if (
            f.end.tzinfo is None
            or f.start.tzinfo is None
            or f.context_available_at.tzinfo is None
            or f.context_available_at > f.start
        ):
            raise ValueError("context must be timezone-aware and available before decision bar")
        if f.end <= f.start:
            raise ValueError("empty or reversed completed bar")
        numbers = [
            f.close,
            f.low,
            f.previous_high,
            f.previous_low,
            f.day_low,
            f.adr,
            f.ema9,
            f.ema21,
            book.equity,
        ]
        if any(not math.isfinite(v) or v <= 0 for v in numbers):
            raise ValueError("invalid positive finite decision inputs")
        s = self.states.setdefault(f.symbol, State())
        if s.last_end is not None and f.end <= s.last_end:
            raise ValueError("nonmonotonic/repeated frame; consume each completion once")
        s.last_end = f.end
        if s.path_unknown:
            self.note(s, f, "sticky_unknown_active_path")
            return []
        if s.session != f.session:
            s.session, s.attempts_day = f.session, 0
            s.touch_end = None
        if s.touch_end is not None and f.start - s.touch_end > timedelta(
            minutes=p.get("touch_expiry_minutes", 15)
        ):
            s.touch_end = None
        if s.epoch != f.epoch and s.quantity == 0 and s.pending is None:
            s.epoch, s.attempts_epoch, s.touch_end = (
                f.epoch,
                self.epoch_attempts.get((f.symbol, f.epoch), 0),
                None,
            )
        if not f.active_data_complete:
            if s.quantity or s.pending or s.pending_exit or s.protective:
                s.path_unknown = True
                s.status = "unknown"
            self.note(
                s,
                f,
                "unknown_active_data" if s.quantity or s.pending else "missing_flat_data_no_signal",
            )
            return []
        if s.pending is not None or s.pending_exit:
            self.note(s, f, "await_execution_report")
            return []
        if s.quantity:
            # Protective stop is a standing intent issued on fill, handled by
            # the adapter including adverse gaps. This close policy cannot
            # certify which intrabar stop/target was touched first.
            if (
                f.trail_daily_close is not None
                and f.trail_daily_ema9 is not None
                and f.trail_daily_close < f.trail_daily_ema9
            ):
                s.pending_exit = self.intent(
                    f, "sell", s.quantity, f.close, None, "completed_daily_trend_failure"
                )
                return [s.pending_exit]
            full_path = self.candidate in {"P_HOLD", "P_FEEDBACK", "P_SYSTEM"}
            initial_unit_R = s.reference - s.initial_stop
            if (
                full_path
                and f.completed_sessions_since_entry >= p["failure_sessions"]
                and f.close <= s.reference
            ):
                s.pending_exit = self.intent(
                    f, "sell", s.quantity, f.close, None, "no_followthrough"
                )
                return [s.pending_exit]
            if (
                full_path
                and not s.trimmed
                and f.market == "neutral"
                and f.close >= s.reference + p["partial_R"] * initial_unit_R
            ):
                q = min(s.quantity, math.floor(s.initial_quantity * p["partial_fraction"]))
                if q:
                    s.pending_exit = self.intent(f, "sell", q, f.close, None, "partial_strength")
                    return [s.pending_exit]
                s.trimmed = True
                self.note(s, f, "partial_below_whole_share")
            return []
        if not f.epoch_valid or not f.leadership or f.market in {"weak", "unknown"}:
            s.status, s.touch_end = "observe", None
            self.note(s, f, "not_leader_or_adverse_market")
            return []
        if not f.trigger_price_eligible:
            s.touch_end = None
            self.note(s, f, "split_like_trigger_session_excluded")
            return []
        if book.held_or_reserved_names >= p.get("max_held_names", 4):
            self.note(s, f, "joint_book_name_capacity")
            return []
        if self.candidate != "P_EMA" and not (
            f.shape_ok and (self.candidate == "B_BREAK" or f.first_retest)
        ):
            s.status, s.touch_end = "watch", None
            self.note(s, f, "base_geometry_or_retest_not_ready")
            return []
        if (
            f.ema9_previous is None
            or f.ema21_previous is None
            or not (f.ema9 > f.ema9_previous or f.ema21 > f.ema21_previous)
        ):
            self.note(s, f, "rising_EMA_context_missing_or_false")
            return []
        required = clock_minutes(p, f.minute)
        if (
            required is None
            or f.duration != required
            or f.minute + f.duration > p["entry_cutoff_minute"]
        ):
            self.note(s, f, "outside_source_clock_or_incomplete_timeframe")
            return []
        reentry = self.candidate in {"P_REENTRY", "P_HOLD", "P_FEEDBACK", "P_SYSTEM"}
        cap_epoch = p["attempts_per_epoch"] if reentry else 1
        if s.attempts_epoch >= cap_epoch or s.attempts_day >= p["attempts_per_day"]:
            self.note(s, f, "attempt_budget_exhausted")
            return []
        measures = {
            "daily:ema:9": f.ema9,
            "daily:ema:21": f.ema21,
        }
        if self.candidate not in {"B_BREAK", "P_EMA", "P_SHAPE"}:
            a = select_anchor(
                f.anchors, f.start, prior_respect=self.candidate == "P_SYSTEM", cap=p["anchor_cap"]
            )
            if a is None:
                self.note(s, f, "no_causally_available_anchor")
                return []
            measures["avwap:" + a.id] = a.price
            for support in f.supports:
                if not isinstance(support, Support):
                    raise ValueError("confluence requires typed support measure identities")
                if support.available_at > f.start:
                    continue
                if support.measure_id in measures and not math.isclose(
                    measures[support.measure_id], support.price, rel_tol=1e-12
                ):
                    raise ValueError("same support measure has conflicting values")
                measures[support.measure_id] = support.price
        levels = list(measures.values())
        radius = f.adr * f.close * p["support_radius_ADR"]
        touched = [v for v in levels if f.low <= v + radius and f.close >= v]
        minimum = (
            p["minimum_confluence"] if self.candidate not in {"B_BREAK", "P_EMA", "P_SHAPE"} else 1
        )
        # Confluence requires nearby levels, not merely a wide bar crossing
        # two unrelated distant levels.
        cluster_size = max(
            (sum(abs(v - anchor) <= radius for v in touched) for anchor in touched), default=0
        )
        if touched and cluster_size >= minimum:
            s.touch_end, s.status = f.end, "touched"
        breakout = (
            f.close > (f.base_breakout_level or math.inf)
            if self.candidate == "B_BREAK"
            else f.close > f.previous_high
        )
        if self.candidate != "B_BREAK" and s.touch_end is None:
            self.note(s, f, "watchlist_without_support_confirmation")
            return []
        if not breakout:
            self.note(s, f, "await_previous_bar_high_confirmation")
            return []
        if s.last_stopout_at is not None and (
            s.touch_end is None or s.touch_end <= s.last_stopout_at
        ):
            self.note(s, f, "reentry_needs_new_support_confirmation")
            return []
        ref = f.close
        max_width = min(p["max_stop_pct"], p["max_stop_ADR"] * f.adr)
        stop = f.day_low if 0 < (ref - f.day_low) / ref <= max_width else f.previous_low
        stop = math.floor((stop - p["price_tick"]) / p["price_tick"]) * p["price_tick"]
        width = (ref - stop) / ref
        if not p["minimum_stop_bps"] / 10000 <= width <= max_width:
            self.note(s, f, "no_defined_source_width_stop")
            return []
        risk = p["risk_normal"]
        if self.candidate in {"P_FEEDBACK", "P_SYSTEM"}:
            past = book.prior_closed_R[-p["feedback_closed_trades"] :]
            if (
                book.drawdown_from_recent_peak >= p["feedback_pause_drawdown"]
                and f.sessions_since_risk_pause < p["feedback_pause_sessions"]
            ):
                self.note(s, f, "causal_feedback_pause")
                return []
            if (
                book.drawdown_from_recent_peak >= p["feedback_pause_drawdown"]
                or len(past) < p["feedback_closed_trades"]
                or sum(past) < p["feedback_probe_if_net_R_below"]
            ):
                risk = p["risk_probe"]
        room = min(
            book.equity * risk,
            max(0, book.equity * p["aggregate_risk_cap"] - book.initial_risk_dollars),
        )
        if self.candidate in {"P_FEEDBACK", "P_SYSTEM"}:
            room = min(
                room,
                max(
                    0,
                    book.month_start_equity * p["monthly_new_risk_cap"]
                    - book.month_entry_risk_dollars,
                ),
            )
        fee = self.cost_bps / 10000
        worst_entry = ref * (1 + p["entry_price_cap_bps"] / 10000)
        # Both routes reserve the same finite cap price. Market entries with
        # an opening price above this research cap are rejected, not resized.
        reserved_unit_risk = worst_entry - stop + fee * (worst_entry + stop)
        q = min(
            math.floor(room / reserved_unit_risk),
            math.floor(book.equity * p["position_cap"] / worst_entry),
            math.floor(max(0, book.equity * p["gross_cap"] - book.gross_notional) / worst_entry),
            math.floor(max(0, book.spendable_cash) / (worst_entry * (1 + fee))),
        )
        if not math.isfinite(f.past_minute_volume) or f.past_minute_volume <= 0:
            self.note(s, f, "prior_observed_volume_missing")
            return []
        q = min(q, math.floor(f.past_minute_volume * p["participation_fraction"]))
        if q < 1:
            self.note(s, f, "cash_risk_capacity_or_whole_share_reject")
            return []
        order = self.intent(
            f,
            "buy",
            q,
            ref,
            stop,
            "completed_reversal" if self.candidate != "B_BREAK" else "completed_breakout",
        )
        order = replace(
            order,
            reserved_cash=q * worst_entry * (1 + fee),
            reserved_risk=q * reserved_unit_risk,
        )
        s.pending, s.status = order, "pending"
        s.attempts_day += 1
        s.attempts_epoch += 1
        self.epoch_attempts[(f.symbol, f.epoch)] = s.attempts_epoch
        s.touch_end = None
        self.note(s, f, "submitted_causal_intent")
        return [order]

    def entry_report(
        self,
        symbol: str,
        at: datetime,
        *,
        filled: bool,
        price: float | None = None,
        quantity: int = 0,
        order_id: str,
        report_id: str,
        terminal: bool,
        cancelled_quantity: int,
        phase: str = "next_scheduled_open",
    ) -> Intent | None:
        s = self.states[symbol]
        order = s.pending
        if (
            order is None
            or order.id != order_id
            or at.tzinfo is None
            or at < order.eligible_after
            or phase
            not in (
                {"next_scheduled_open", "capped_resting_fill", "terminal_cancel"}
                if self.route == "capped"
                else {"next_scheduled_open", "terminal_cancel"}
            )
            or (s.last_execution_at is not None and at < s.last_execution_at)
            or not report_id
            or report_id in s.report_ids
        ):
            raise ValueError("execution needs matching pending order after signal completion")
        if filled and (
            price is None
            or not math.isfinite(price)
            or price <= 0
            or type(quantity) is not int
            or not 0 < quantity <= order.quantity
        ):
            raise ValueError("invalid execution price/whole quantity")
        if not filled and quantity != 0:
            raise ValueError("nonfill cannot carry shares")
        if not terminal or cancelled_quantity != order.quantity - quantity:
            raise ValueError("conditional fill must explicitly cancel entire unfilled remainder")
        shared_price_guard = order.reference * (1 + self.p["entry_price_cap_bps"] / 10000)
        if filled and price > shared_price_guard + 1e-10:
            raise ValueError("fill exceeds frozen cash/risk price guard")
        s.pending = None
        s.last_execution_at = at
        s.report_ids.add(report_id)
        s.audit.append(
            dict(
                at=at.isoformat(),
                order_id=order_id,
                report_id=report_id,
                terminal=True,
                filled_quantity=quantity,
                cancelled_quantity=cancelled_quantity,
            )
        )
        if not filled:
            s.status = "watch"
            return None
        s.quantity = s.initial_quantity = quantity
        s.reference, s.initial_stop, s.hard_stop = order.reference, order.stop, order.stop
        s.submitted_planned_R0 = order.quantity * (order.reference - order.stop)
        s.fill_price, s.trimmed, s.status = price, False, "held"
        # Activated on the actual fill event, not a later bar. The consumer
        # must test stop-gap/latency/ambiguity rather than guarantee this price.
        s.protective = Intent(
            order.id + "-protect",
            symbol,
            "protect",
            at,
            at,
            quantity,
            price,
            order.stop,
            None,
            "initial_protective_stop",
            order.epoch,
        )
        return s.protective

    def exit_report(
        self,
        symbol: str,
        at: datetime,
        quantity: int,
        *,
        stopout: bool = False,
        filled: bool = True,
        order_id: str,
        report_id: str,
        terminal: bool,
        cancelled_quantity: int,
        cancelled_order_ids: tuple[str, ...] = (),
    ):
        s = self.states[symbol]
        order = s.protective if stopout else s.pending_exit
        if (
            order is None
            or order.id != order_id
            or at.tzinfo is None
            or at < order.eligible_after
            or s.last_execution_at is None
            or at < s.last_execution_at
            or not report_id
            or report_id in s.report_ids
        ):
            raise ValueError("exit execution needs a causally prior sell intent")
        if type(quantity) is not int or quantity < 0 or quantity > min(order.quantity, s.quantity):
            raise ValueError("exit quantity exceeds outstanding intent or held shares")
        if not terminal or cancelled_quantity != order.quantity - quantity:
            raise ValueError("conditional exit must acknowledge all unfilled remainder")
        if stopout and s.pending_exit is not None and s.pending_exit.id not in cancelled_order_ids:
            raise ValueError("protective fill requires pending sell cancellation acknowledgment")
        if (
            filled
            and not stopout
            and s.protective is not None
            and s.protective.id not in cancelled_order_ids
        ):
            raise ValueError(
                "sell fill requires old protective order cancel/replace acknowledgment"
            )
        if filled != (quantity > 0):
            raise ValueError("fill flag and quantity disagree")
        s.report_ids.add(report_id)
        s.last_execution_at = at
        s.audit.append(
            dict(
                at=at.isoformat(),
                order_id=order_id,
                report_id=report_id,
                terminal=True,
                filled_quantity=quantity,
                cancelled_quantity=cancelled_quantity,
                cancelled_order_ids=list(cancelled_order_ids),
            )
        )
        if not filled:
            s.pending_exit = None
            return None
        s.quantity -= quantity
        if order is not None and order.reason == "partial_strength":
            s.trimmed = True
        s.pending_exit = None
        s.protective = None
        if s.quantity == 0:
            s.status = "stopped" if stopout else "watch"
            s.touch_end = None
            if stopout:
                s.last_stopout_at = at
            return None
        s.protective = Intent(
            order.id + "-resize-" + report_id,
            symbol,
            "protect",
            at,
            at,
            s.quantity,
            s.fill_price,
            s.hard_stop,
            None,
            "resized_protective_stop",
            s.epoch,
        )
        return s.protective
