"""Extend the existing OHLC feed only at qualified absent-bar minutes.

Quote values retain actual nanosecond event time. Initial BBO is a declared
conditional carry state at the old opening phase; no new signal Frame/bar.
"""

from dataclasses import replace
from decimal import Decimal

from consumer_admission import P
from gap_adapter import actual_admission
from gap_source import SYNTHETIC_DEPTH_PHYSICAL_SHARES, integer_ns
from native_events5 import boundary, native_month
from nautilus_trader.model.data import BookOrder, OrderBookDelta, OrderBookDeltas, QuoteTick
from nautilus_trader.model.enums import BookAction, OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity


def quote_data(symbol, observation, factor, depth, sequence):
    assert observation.quote_problem() is None
    units = Decimal(depth) / Decimal(str(factor))
    assert units == units.to_integral_value() and units > 0
    b = observation.bid * Decimal(str(factor))
    a = observation.ask * Decimal(str(factor))
    assert all(p.quantize(Decimal("0.00001")) == p for p in (b, a))
    ident = InstrumentId.from_str(symbol + ".SIM")
    bid, ask = Price.from_str(f"{b:.5f}"), Price.from_str(f"{a:.5f}")
    size = Quantity.from_int(int(units))
    at = observation.event_ns
    book = OrderBookDeltas(
        ident,
        [
            OrderBookDelta(ident, BookAction.CLEAR, None, 0, sequence, at, at),
            OrderBookDelta(
                ident,
                BookAction.ADD,
                BookOrder(OrderSide.BUY, bid, size, 1),
                0,
                sequence + 1,
                at,
                at,
            ),
            OrderBookDelta(
                ident,
                BookAction.ADD,
                BookOrder(OrderSide.SELL, ask, size, 2),
                128,
                sequence + 2,
                at,
                at,
            ),
        ],
    )
    return book, QuoteTick(ident, bid, ask, size, size, at, at)


def gap_minute(
    packet, scenario, factors, trigger_masks, qualified, *, active_symbols=None, admitted_job=None
):
    # Qualified contains only the predeclared missing symbols at this minute.
    # Required gaps without source QA retain the original missing/unknown gate.
    if any(
        window.source_QA.get("source_provenance") != "fully_synthetic_inert"
        for window in qualified.values()
    ) or any(
        q.source_entity_sha != "synthetic"
        for window in qualified.values()
        for q in ((window.initial,) if window.initial else ()) + window.events
    ):
        actual_admission(
            admitted_job, P / "economic-results/source-consumer-v3/independent-review.json"
        )
    start = integer_ns(packet["start"])
    assert set(qualified) <= set(packet["missing"])
    baseline = dict(packet, missing=[s for s in packet["missing"] if s not in qualified])
    books, quotes, phases, next_factors = native_month(
        [baseline], scenario, factors, trigger_masks, active_symbols=active_symbols
    )
    for symbol, window in sorted(qualified.items()):
        assert (
            window.symbol == symbol
            and window.start_ns == start
            and window.end_ns == start + 60 * 10**9
        )
        phases.append(
            boundary(
                "source_bar_absent",
                start + 2,
                packet,
                [
                    dict(
                        symbol=symbol,
                        source_QA=window.source_QA,
                        source_initial_ns=window.initial.event_ns if window.initial else None,
                        firm_NBBO=False,
                        broker_stop_election="unknown",
                        synthetic_depth_physical_shares=SYNTHETIC_DEPTH_PHYSICAL_SHARES,
                    )
                ],
            )
        )
        if window.unresolved_ns is not None:
            phases.append(
                boundary(
                    "source_unresolved",
                    window.unresolved_ns,
                    packet,
                    [
                        dict(
                            symbol=symbol,
                            reason=window.unresolved_reason,
                            at_ns=window.unresolved_ns,
                        )
                    ],
                )
            )
        if window.initial is None or (
            window.unresolved_ns is not None and window.unresolved_ns <= start + 3
        ):
            continue
        observations = list(window.events)
        # Do not replace an actual early quote with an older carried state.
        if not any(q.event_ns <= start + 3 for q in observations):
            observations.insert(0, replace(window.initial, event_ns=start + 3))
        for i, q in enumerate(observations):
            if window.unresolved_ns is not None and q.event_ns >= window.unresolved_ns:
                break
            d, t = quote_data(
                symbol, q, next_factors.get(symbol, 1.0), SYNTHETIC_DEPTH_PHYSICAL_SHARES, 3 * i
            )
            books.append(d)
            quotes.append(t)
    return books, quotes, phases, next_factors


def holding_phase(packet, contexts):
    start = integer_ns(packet["start"])
    assert packet["minute"] == 0
    rows = contexts[packet["session"]]
    assert len(rows) == 6 and len({r["symbol"] for r in rows}) == 6
    return boundary("holding_daily", start + 5, packet, rows)
