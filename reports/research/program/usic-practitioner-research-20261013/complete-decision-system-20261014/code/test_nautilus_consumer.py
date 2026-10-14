"""Inert native protocol witnesses. No historical market input or return test."""

import json
from dataclasses import asdict, replace

import pytest
from decision_system import read_parameters
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
from test_decision_system import SPEC, T, frame


def pack(stage, ns, rows=()):
    d = MartinBoundaryData(
        stage=stage,
        frames_json=json.dumps(rows, default=lambda x: x.isoformat()),
        session_ordinal=0,
        month="2024-11",
        ts_event=ns,
        ts_init=ns,
    )
    return CustomData(DataType(MartinBoundaryData), d)


def make_engine(route="market", cost=20, initial_factors=None):
    from native_engine import make_engine as actual_builder

    return actual_builder(
        read_parameters(SPEC),
        "P_SYSTEM",
        route,
        cost,
        {"spec": "inert", "input": "synthetic-no-market", "contract": "test-only"},
        initial_factors,
    )


def quote(symbol, ns, price=10.0, size=100000):
    return QuoteTick(
        InstrumentId.from_str(symbol + ".SIM"),
        Price(price, 4),
        Price(price, 4),
        Quantity.from_int(size),
        Quantity.from_int(size),
        ns,
        ns,
    )


def bookdata(symbol, ns, price=10.0, size=100000):
    id = InstrumentId.from_str(symbol + ".SIM")
    return OrderBookDeltas(
        id,
        [
            OrderBookDelta(id, BookAction.CLEAR, None, 0, 0, ns, ns),
            OrderBookDelta(
                id,
                BookAction.ADD,
                BookOrder(OrderSide.BUY, Price(price, 4), Quantity.from_int(size), 1),
                0,
                0,
                ns,
                ns,
            ),
            OrderBookDelta(
                id,
                BookAction.ADD,
                BookOrder(OrderSide.SELL, Price(price, 4), Quantity.from_int(size), 2),
                128,
                0,
                ns,
                ns,
            ),
        ],
    )


def run_inert(route="market", size=100000, stop=False):
    engine, strategy = make_engine(route)
    ns = int(T.timestamp() * 1e9)
    rows = []
    for symbol in ("SOFI", "COIN"):
        rows.append(
            dict(
                frame=asdict(replace(frame(), symbol=symbol)),
                leadership_score=1,
                prior_dollar_volume=1e7,
            )
        )
    prices = [quote(s, ns - 1) for s in ("SOFI", "COIN")]
    prices += [quote(s, ns + 2, size=size) for s in ("SOFI", "COIN")]
    prices += [quote(s, ns + 20_000_000_000, 9.5 if stop else 10.1) for s in ("SOFI", "COIN")]
    phases = [pack("close", ns + 1, rows), pack("open_exits", ns + 3), pack("open_entries", ns + 4)]
    engine.add_data(
        [
            bookdata(
                x.instrument_id.symbol.value,
                x.ts_event - 1,
                x.bid_price.as_double(),
                int(x.bid_size.as_double()),
            )
            for x in prices
        ]
    )
    engine.add_data(prices)
    engine.add_data(phases, client_id=ClientId("MARTIN"))
    engine.run()
    return engine, strategy


def test_native_shared_cash_order_identity_and_fee():
    engine, s = run_inert()
    try:
        assert not s.book.path_unknown, s.book.unknown_reasons
        assert len(s.book.lots) == 2 and not s.book.reserved
        assert all(st.quantity > 0 and st.protective for st in s.policy.states.values())
        assert (
            len({x["intent_id"] for x in s.audit if x["action"] == "signal_before_native_order"})
            == 2
        )
        assert all(lot.fees > 0 for lot in s.book.lots.values())
        native_positions = engine.cache.positions_open()
        assert len(native_positions) == 2
        for p in native_positions:
            assert p.quantity.as_double() == s.policy.states[p.instrument_id.symbol.value].quantity
    finally:
        engine.dispose()


@pytest.mark.parametrize("route", ["market", "capped"])
def test_actual_native_terminal_partial_cancel_and_immediate_protection(route):
    engine, s = run_inert(route, size=1)
    try:
        assert not s.book.path_unknown, s.book.unknown_reasons
        assert all(
            st.quantity == 1 and st.pending is None and st.protective.quantity == 1
            for st in s.policy.states.values()
        )
        assert any(a["action"] == "terminal_partial_cancel_ack" for a in s.audit)
        assert not s.book.reserved
        assert all(lot.quantity == 1 for lot in s.book.lots.values())
        assert all(lot.submitted_R0 > 0.2 for lot in s.book.lots.values())
    finally:
        engine.dispose()


def test_protective_gap_uses_actual_native_price_and_closes_original_lot():
    engine, s = run_inert(stop=True)
    try:
        assert not s.book.path_unknown, s.book.unknown_reasons
        assert all(st.quantity == 0 and st.status == "stopped" for st in s.policy.states.values())
        sales = [
            a
            for a in s.audit
            if a["action"] == "native_full_fill" and a["intent_id"].endswith("-protect")
        ]
        assert len(sales) == 2 and all(a["price"] == 9.5 for a in sales)
        assert len(s.book.closed_R) == 2 and not s.book.lots
    finally:
        engine.dispose()


def test_native_split_coordinate_preserves_cash_NAV_R0_and_stop_order():
    engine, s = make_engine(initial_factors={"SOFI": 0.1})
    ns = int(T.timestamp() * 1e9)
    row = dict(frame=asdict(frame()), leadership_score=1, prior_dollar_volume=1e7)
    prices = [
        quote("SOFI", ns - 1, 1),
        quote("SOFI", ns + 4, 1),
        quote("SOFI", ns + 20_000_000_000, 1),
    ]
    phases = [
        pack("close", ns + 1, [row]),
        pack("open_exits", ns + 5),
        pack("open_entries", ns + 6),
        pack(
            "actions",
            ns + 10_000_000_000,
            [dict(kind="forward_split", symbol="SOFI", ratio=10, id="inert-split")],
        ),
    ]
    engine.add_data(
        [
            bookdata(x.instrument_id.symbol.value, x.ts_event - 1, x.bid_price.as_double())
            for x in prices
        ]
    )
    engine.add_data(prices)
    engine.add_data(phases, client_id=ClientId("MARTIN"))
    engine.run()
    try:
        assert not s.book.path_unknown, s.book.unknown_reasons
        state = s.policy.states["SOFI"]
        assert state.quantity == state.initial_quantity == s.book.lots["SOFI"].quantity
        assert state.reference == 1 and s.unit_factors["SOFI"] == 1
        native = engine.cache.positions_open()[0]
        assert native.quantity.as_double() == state.quantity
        assert s.book.lots["SOFI"].submitted_R0 == pytest.approx(state.submitted_planned_R0)
        stop = engine.cache.order(
            __import__(
                "nautilus_trader.model.identifiers", fromlist=["ClientOrderId"]
            ).ClientOrderId(state.protective.id)
        )
        assert stop.trigger_price.as_double() == pytest.approx(state.hard_stop, abs=0.00005)
        assert s.marks["SOFI"] == 1
        assert s.book.lots["SOFI"].bought_dollars == pytest.approx(state.quantity)
    finally:
        engine.dispose()


def test_native_missing_active_minute_freezes_R_feedback_and_holding_after_adverse_quote():
    engine, s = make_engine()
    ns = int(T.timestamp() * 1e9)
    row = dict(frame=asdict(frame()), leadership_score=1, prior_dollar_volume=1e7)
    prices = [quote("SOFI", ns - 1), quote("SOFI", ns + 4)]
    engine.add_data([bookdata("SOFI", x.ts_event - 1) for x in prices])
    engine.add_data(prices)
    engine.add_data(
        [pack("close", ns + 1, [row]), pack("open_exits", ns + 5), pack("open_entries", ns + 6)],
        client_id=ClientId("MARTIN"),
    )
    engine.run(streaming=True)
    engine.clear_data()
    assert s.policy.states["SOFI"].quantity > 0
    known_quantity = s.policy.states["SOFI"].quantity
    known_marks = dict(s.marks)
    known_closed_R = list(s.book.closed_R)
    engine.add_data(
        [
            pack("missing", ns + 60_000_000_000, ["SOFI"]),
            pack("mark", ns + 120_000_000_000, {"daily_close": True}),
        ],
        client_id=ClientId("MARTIN"),
    )
    engine.add_data(
        [bookdata("SOFI", ns + 100_000_000_000, 9.5), quote("SOFI", ns + 100_000_000_001, 9.5)]
    )
    engine.run(streaming=True)
    engine.end()
    try:
        assert s.book.path_unknown and s.policy.states["SOFI"].path_unknown
        assert s.snapshots == []
        assert s.policy.states["SOFI"].quantity == s.book.lots["SOFI"].quantity == known_quantity
        assert s.marks == known_marks and s.book.closed_R == known_closed_R
        assert s.book.first_unknown["at_ns"] == ns + 60_000_000_000
        assert s.book.first_unknown["known_prefix_closed_R"] == known_closed_R
        assert s.book.pause_session == s.book.first_unknown["feedback"]["pause_session"]
        assert s.uninterpretable_counts["filled"] == 1
        assert (
            engine.cache.positions_open() == []
        )  # Native mechanic is quarantined, not a known exit.
    finally:
        engine.dispose()
