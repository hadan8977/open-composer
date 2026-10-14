"""Thin controlled component using the existing native engine and order adapter.

No actual-market entry point is admitted by importing this module. The offline
caller supplies exclusively handcrafted prices; actual source replay waits for
separate bound input/implementation/current-native/resource acceptance.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from consumer_admission import ROOT, P, bind, phase_admission, receipt, verify_bindings
from decision_system import Intent, State, read_parameters
from native_engine import make_engine
from nautilus_policy_adapter import MartinBoundaryData
from nautilus_trader.model.data import (
    BookOrder,
    CustomData,
    DataType,
    OrderBookDelta,
    OrderBookDeltas,
    QuoteTick,
)
from nautilus_trader.model.enums import BookAction, OrderSide
from nautilus_trader.model.identifiers import ClientId, InstrumentId
from nautilus_trader.model.objects import Price, Quantity


def policy_time(ns):
    # The inherited policy accepts microsecond datetime. Native event integers
    # are retained separately; this truncation is not a nanosecond clock proof.
    return datetime.fromtimestamp(ns // 10**9, UTC) + timedelta(microseconds=(ns % 10**9) // 1000)


def boundary(stage, ns, rows=(), session=0, month="2024-01"):
    return CustomData(
        DataType(MartinBoundaryData),
        MartinBoundaryData(
            stage=stage,
            frames_json=json.dumps(rows),
            session_ordinal=session,
            month=month,
            ts_event=ns,
            ts_init=ns,
        ),
    )


def source_quote_data(observation, depth, sequence):
    """Observed price values plus explicitly synthetic L2 quantities.

    The two arrays have the same event timestamp. Native book processing before
    the diagnostic quote is an adapter convention, not cross-stream evidence.
    """
    if observation.quote_problem():
        raise ValueError("invalid_observation_cannot_be_native_book")
    if any(p.quantize(Decimal("0.0001")) != p for p in (observation.bid, observation.ask)):
        raise ValueError("source_price_not_exact_native_tick")
    ident = InstrumentId.from_str("LMND.SIM")
    ns = observation.event_ns
    bid, ask = Price.from_str(f"{observation.bid:.4f}"), Price.from_str(f"{observation.ask:.4f}")
    size = Quantity.from_int(depth)
    delta = OrderBookDeltas(
        ident,
        [
            OrderBookDelta(ident, BookAction.CLEAR, None, 0, sequence, ns, ns),
            OrderBookDelta(
                ident,
                BookAction.ADD,
                BookOrder(OrderSide.BUY, bid, size, 1),
                0,
                sequence + 1,
                ns,
                ns,
            ),
            OrderBookDelta(
                ident,
                BookAction.ADD,
                BookOrder(OrderSide.SELL, ask, size, 2),
                128,
                sequence + 2,
                ns,
                ns,
            ),
        ],
    )
    return delta, QuoteTick(ident, bid, ask, size, size, ns, ns)


def real_source_admission(job, quotes, fixture):
    if job is None:
        raise ValueError("actual_source_requires_independent_component_native_admission")
    path = P / "economic-results/source-clock-component-independent-review.json"
    proof = json.loads(path.read_text())
    assert proof["verdict"] == "approve_implementation"
    assert proof["author"] != proof["reviewer"]
    assert proof["real_market_native_probe_admitted"] is True
    assert 0 < proof["allocation"]["technical_source_window_CPU"] <= 180
    row = receipt(job)
    assert row["component_review"] == bind(path)
    assert row["combined_CPU_upper"] <= proof["allocation"]["technical_source_window_CPU"]
    verify_bindings(proof["bindings"])
    phase_admission(job, "empirical")  # current owner/hold/PID/native dossier/pool
    contract = json.loads((ROOT / proof["bindings"]["fixtures"]["path"]).read_text())
    matched = [f for f in contract["fixtures"] if f["id"] == fixture["id"]]
    assert len(matched) == 1 and matched[0] == fixture
    from source_clock import parse_source

    source = next(b for b in fixture["source_versions"] if "_quotes.bin" in b["path"])
    verify_bindings(source)
    expected, _ = parse_source((ROOT / source["path"]).read_bytes(), "quotes", source["sha256"])
    assert quotes == expected


def run_component(quotes, fixture, spec, *, provenance, admitted_job=None):
    """No signals/Frame. Initial order is an explicitly controlled intervention."""
    assert provenance in {"fully_synthetic_inert", "separately_admitted_real_source_component"}
    if provenance == "fully_synthetic_inert":
        assert all(q.source_entity_sha == "synthetic" for q in quotes)
    else:
        real_source_admission(admitted_job, quotes, fixture)
    qty = fixture["quantity"]
    declared_positive = fixture["initial_R0_status"] == "positive"
    positive = (
        type(qty) is int
        and qty > 0
        and (Decimal(fixture["initial_reference"]) > Decimal(fixture["stop"]) > 0)
    )
    if positive != declared_positive:
        raise ValueError("fixture_R0_status_conflicts_with_frozen_numeric_values")
    if fixture["initial_R0_status"] != "positive":
        return dict(status="invalid_initial_R0_no_native_run", native_engines=0, R=None)
    engine, strategy = make_engine(
        read_parameters(spec),
        "P_SYSTEM",
        "market",
        20,
        dict(spec="component", input=provenance, contract="source-clock-component"),
    )
    entry_ns = fixture["entry_submit_ns"]
    at = policy_time(entry_ns)
    ref, stop = float(fixture["initial_reference"]), float(fixture["stop"])
    order = Intent(
        fixture["id"] + "-entry",
        "LMND",
        "buy",
        at,
        at,
        qty,
        ref,
        stop,
        None,
        "controlled_component_initial_order",
        "component",
        qty * ref * 1.01,
        qty * (ref - stop),
    )
    strategy.policy.states["LMND"] = State(status="pending", epoch="component", pending=order)
    strategy.staged_entries[order.id] = order
    strategy.book.reserve(order)
    # Capture exact native report clocks/IDs; retain inherited callbacks.
    native_reports = []
    original = strategy.on_order_filled

    def capture(event):
        native_reports.append(
            dict(
                ns=event.ts_event,
                order_id=str(event.client_order_id),
                report_id=str(event.id),
                quantity=str(event.last_qty),
                price=str(event.last_px),
                commission=str(event.commission),
            )
        )
        original(event)

    strategy.on_order_filled = capture
    try:
        books, ticks = [], []
        for i, observation in enumerate(quotes):
            d, t = source_quote_data(observation, fixture["synthetic_L2_depth_shares"], i * 3)
            books.append(d)
            ticks.append(t)
        engine.add_data(books)
        engine.add_data(ticks)
        # Independent calendar/order boundary, no completed bar or entry Frame.
        phases = [boundary("open_entries", entry_ns)]
        if fixture.get("first_unresolved_price_ns") is not None:
            phases.append(boundary("missing", fixture["first_unresolved_price_ns"], ["LMND"]))
        engine.add_data(phases, client_id=ClientId("MARTIN"))
        engine.run()
        st = strategy.policy.states["LMND"]
        output = dict(
            status="conditional_native_quote_proxy_component",
            native_engines=1,
            quantity=st.quantity,
            pending=st.pending is not None,
            protective_quantity=st.protective.quantity if st.protective else None,
            initial_R0=st.submitted_planned_R0,
            closed_R=list(strategy.book.closed_R),
            native_reports=native_reports,
            unknown=strategy.book.path_unknown,
            firstunknown=strategy.book.first_unknown,
            quarantined=dict(strategy.uninterpretable_counts),
            audit=strategy.audit,
            broker_stop_election="unknown",
            firm_nbbo=False,
            R=None,
            native_cash=None if strategy.book.path_unknown else strategy._cash(),
            snapshots=strategy.snapshots,
            feedback_after=dict(
                pause_session=strategy.book.pause_session,
                resume_session=strategy.book.resume_session,
                resume_peak=strategy.book.resume_peak,
                closed_at_pause=strategy.book.closed_at_pause,
                month=strategy.book.month,
                month_peak=strategy.book.month_peak,
                month_new_risk=strategy.book.month_new_risk,
            ),
        )
        return output
    finally:
        engine.dispose()
