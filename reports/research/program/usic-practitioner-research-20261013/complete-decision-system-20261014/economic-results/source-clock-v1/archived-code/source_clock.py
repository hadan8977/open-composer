"""Isolated source observations and stop necessary conditions, never a fill engine.

Current-vintage event time is an explicit observation assumption. No function
here certifies broker election, historical arrival, market coverage or liquidity.
"""

from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import groupby


def ns(value):
    """Same integer parser as the accepted source entry; no float conversion."""
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z", value)
    if not match:
        raise ValueError("unsupported_source_timestamp")
    whole = calendar.timegm(datetime.fromisoformat(match[1]).timetuple())
    return whole * 10**9 + int((match[2] or "0").ljust(9, "0"))


def number(value):
    d = Decimal(str(value))
    if not d.is_finite():
        raise ValueError("nonfinite_source_number")
    return d


@dataclass(frozen=True)
class Observation:
    kind: str
    event_ns: int
    source_ordinal: int
    timestamp: str
    conditions: tuple[str, ...]
    tape: str | None
    source_entity_sha: str
    raw_message: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size_raw_units: Decimal | None = None
    ask_size_raw_units: Decimal | None = None
    price: Decimal | None = None
    trade_size_raw_units: Decimal | None = None
    bid_exchange: str | None = None
    ask_exchange: str | None = None
    trade_exchange: str | None = None
    trade_id: str | None = None
    synthetic_then_nbbo: bool = False

    def quote_problem(self):
        if self.kind != "quotes":
            raise ValueError("not_a_quote")
        if self.bid is None or self.ask is None:
            return "missing_quote_price"
        if not self.bid.is_finite() or not self.ask.is_finite():
            return "nonfinite_quote"
        if self.bid <= 0 or self.ask <= 0:
            return "nonpositive_quote"
        if self.bid > self.ask:
            return "crossed_quote"
        if self.bid_size_raw_units is None or self.ask_size_raw_units is None:
            return "missing_size"
        if self.bid_size_raw_units <= 0 or self.ask_size_raw_units <= 0:
            return "nonpositive_size"
        if not self.synthetic_then_nbbo and self.conditions != ("R",):
            return "unsupported_quote_qualification"
        return None


def parse_source(body: bytes, kind: str, entity_sha: str):
    """All messages, including bad quotes and equal timestamps, remain present."""
    if kind not in {"quotes", "trades"}:
        raise ValueError("unsupported_source_kind")
    obj = json.loads(body, parse_float=Decimal)
    rows = obj[kind]["LMND"]
    records = []
    for index, row in enumerate(rows):
        common = dict(
            kind=kind,
            event_ns=ns(row["t"]),
            source_ordinal=index,
            timestamp=row["t"],
            conditions=tuple(row.get("c", ())),
            tape=row.get("z"),
            source_entity_sha=entity_sha,
            raw_message=json.dumps(row, sort_keys=True, default=str),
        )
        if kind == "quotes":
            common.update(
                bid=number(row["bp"]),
                ask=number(row["ap"]),
                bid_size_raw_units=number(row["bs"]),
                ask_size_raw_units=number(row["as"]),
                bid_exchange=row.get("bx"),
                ask_exchange=row.get("ax"),
            )
        else:
            common.update(
                price=number(row["p"]),
                trade_size_raw_units=number(row["s"]),
                trade_exchange=row.get("x"),
                trade_id=str(row.get("i")),
            )
        records.append(Observation(**common))
    if any(a.event_ns > b.event_ns for a, b in zip(records, records[1:], strict=False)):
        raise ValueError("unsorted_source_clock_preserve_raw_and_stop")
    return tuple(records), dict(
        page_token=obj.get("next_page_token"),
        page_parse_valid=True,
        coverage_certified=False,
        firm_nbbo_certified=False,
        historical_first_visible=None,
    )


@dataclass(frozen=True)
class StopSetup:
    stop: Decimal
    fill_ns: int | None
    protective_activation_ns: int | None
    quantity: int
    maximum_quote_age_ns: int

    def __post_init__(self):
        if (
            not self.stop.is_finite()
            or self.stop <= 0
            or type(self.quantity) is not int
            or self.quantity <= 0
        ):
            raise ValueError("invalid_stop_setup")
        if self.maximum_quote_age_ns < 0:
            raise ValueError("invalid_quote_age")
        if self.protective_activation_ns is not None and (
            self.fill_ns is None or self.protective_activation_ns < self.fill_ns
        ):
            raise ValueError("protection_before_actual_fill")


@dataclass(frozen=True)
class NecessaryCondition:
    event_ns: int
    source_ordinal: int
    observed_price_reference: bool | None
    reason: str
    quote_ns: int | None
    quote_ordinal: int | None
    quote_age_ns: int | None
    quote_conditions: tuple[str, ...]
    trade_conditions: tuple[str, ...]
    certified_then_nbbo_necessary_condition: bool | None
    broker_stop_election: str = "unknown_incomplete_broker_algorithm_and_source_evidence"


def stop_reference(quotes, trades, setup: StopSetup):
    """Pure chronological annotation; no order, cash, fill or P&L updates.

    Cross-stream equal timestamps have no invented order. A bad latest quote
    invalidates prior BBO knowledge until another qualified observation arrives.
    I affects source bar emission, not this reference's broker eligibility.
    """
    for rows in (quotes, trades):
        if any(a.event_ns > b.event_ns for a, b in zip(rows, rows[1:], strict=False)):
            raise ValueError("unsorted_reference_input")
    latest = None
    results = []
    # kind is only a stable serialization tie-break. Decisions process groups,
    # and expressly refuse to order trades against quotes inside the group.
    merged = sorted((*quotes, *trades), key=lambda r: (r.event_ns, r.kind, r.source_ordinal))
    for timestamp, group in groupby(merged, key=lambda r: r.event_ns):
        records = tuple(group)
        current_quotes = [r for r in records if r.kind == "quotes"]
        for trade in (r for r in records if r.kind == "trades"):
            q = latest
            age = timestamp - q.event_ns if q else None
            observed, certified = None, None
            if setup.protective_activation_ns is None or timestamp < setup.protective_activation_ns:
                reason = "protection_not_active"
            elif timestamp == setup.protective_activation_ns:
                reason = "unknown_activation_same_ns_order"
            elif current_quotes:
                reason = "unknown_cross_stream_same_ns_order"
            elif q is None:
                reason = "unknown_no_initial_bbo"
            elif q.quote_problem():
                reason = "unknown_" + q.quote_problem()
            elif age > setup.maximum_quote_age_ns:
                reason = "unknown_stale_observation"
            elif (
                trade.price is None
                or trade.price <= 0
                or trade.trade_size_raw_units is None
                or trade.trade_size_raw_units <= 0
            ):
                reason = "unknown_invalid_trade"
            else:
                observed = trade.price <= setup.stop and q.bid <= trade.price <= q.ask
                certified = observed if q.synthetic_then_nbbo else None
                reason = "observed_necessary_price_conditions_only"
            results.append(
                NecessaryCondition(
                    timestamp,
                    trade.source_ordinal,
                    observed,
                    reason,
                    q.event_ns if q else None,
                    q.source_ordinal if q else None,
                    age,
                    q.conditions if q else (),
                    trade.conditions,
                    certified,
                )
            )
        if current_quotes:
            latest = max(current_quotes, key=lambda r: r.source_ordinal)
    return tuple(results)


@dataclass(frozen=True)
class BarAvailabilityQA:
    state: str
    classified_at_ns: int
    interval_end_ns: int
    central_trade_count: int
    new_completed_signal_bar: bool
    price_path_certified: bool = False
    retrospective_qa_only: bool = True


def classify_absent_bar(trades, start_ns, end_ns, classified_at_ns, *, page_parse_valid, token):
    if not start_ns < end_ns:
        raise ValueError("invalid_interval")
    central = [r for r in trades if start_ns <= r.event_ns < end_ns]
    proven_condition = (
        classified_at_ns >= end_ns
        and page_parse_valid
        and token is None
        and central
        and all("I" in r.conditions for r in central)
    )
    state = (
        "source_not_emitted_with_actual_condition_evidence"
        if proven_condition
        else "unresolved_absence"
    )
    return BarAvailabilityQA(state, classified_at_ns, end_ns, len(central), False)


@dataclass(frozen=True)
class NoBarBoundary:
    event_ns: int
    new_frame: bool = False
    new_entry_or_trim_signal: bool = False
    calendar_order_actions_due: bool = True
    defer_session_month_for_unacknowledged_partial: bool = False
    execution_price_unresolved: bool = True


def no_bar_boundary(event_ns, *, unacknowledged_partial):
    return NoBarBoundary(
        event_ns, defer_session_month_for_unacknowledged_partial=unacknowledged_partial
    )
