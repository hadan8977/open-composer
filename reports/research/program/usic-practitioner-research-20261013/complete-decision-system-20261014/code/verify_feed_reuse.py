"""Focused inert parity witnesses; no market files, fit or economic result."""

import json
from dataclasses import asdict, replace
from datetime import timedelta

from decision_system import read_parameters
from native_engine import make_engine
from native_events import causal_activity, native_month, source_intervals
from nautilus_policy_adapter import FrameDecoder, decode_frame
from nautilus_trader.model.identifiers import ClientId
from test_decision_system import SPEC, T, frame


def source(*, partial=False, missing=False, split=False):
    packets = []
    for minute in (0, 1, 2, 121, 122):
        start = T + timedelta(minutes=minute - 1)
        sofi = 9.5 if minute >= 2 else 10
        rows = [
            dict(
                symbol="SOFI",
                open=sofi,
                high=sofi + 0.1,
                low=sofi - 0.1,
                close=sofi,
                volume=4 if partial and minute == 1 else 400000,
            ),
            dict(
                symbol="LMND",
                open=12 + minute,
                high=12.1 + minute,
                low=11.9 + minute,
                close=12 + minute,
                volume=400000,
            ),
        ]
        frames = []
        if minute == 0:
            for symbol, leader in (("SOFI", True), ("LMND", False)):
                f = asdict(replace(frame(), symbol=symbol, leadership=leader))
                f = json.loads(json.dumps(f, default=lambda x: x.isoformat()))
                frames.append(dict(frame=f, leadership_score=1, prior_dollar_volume=1e7))
        packets.append(
            dict(
                start=start.isoformat(),
                session="2024-11-01",
                ordinal=0,
                minute=minute,
                session_minutes=123,
                prices=rows,
                missing=["SOFI"] if missing and minute == 2 else [],
                actions=[dict(kind="forward_split", symbol="SMCI", ratio=10, id="test-split")]
                if split and minute == 0
                else [],
                frames=frames,
            )
        )
    return packets


def canonical_audit(strategy):
    return [
        {k: v for k, v in r.items() if k not in {"event_id", "event_at_ns"}}
        for r in strategy.audit
        if r["action"] != "uninterpretable_native_event"
    ]


def replay(packets, route, optimized, scenario, candidate="P_SYSTEM"):
    engine, strategy = make_engine(
        read_parameters(SPEC),
        candidate,
        route,
        20,
        dict(spec="inert", input="synthetic", contract="inert"),
        {"SMCI": 0.1},
        optimize_runtime=optimized,
    )
    factors = {"SMCI": 0.1}
    try:
        intervals = source_intervals(packets, 120) if optimized else [(packets, False)]
        for rows, afternoon in intervals:
            active = causal_activity(strategy, rows[0], afternoon=afternoon) if optimized else None
            strategy.runtime_active_symbols = active
            books, quotes, boundaries, factors = native_month(
                rows, scenario, factors, active_symbols=active
            )
            if books:
                engine.add_data(books)
            if quotes:
                engine.add_data(quotes)
            engine.add_data(boundaries, client_id=ClientId("MARTIN"))
            engine.run(streaming=True)
            engine.clear_data()
        engine.end()
        return dict(
            audit=canonical_audit(strategy),
            snapshots=strategy.snapshots,
            closed_R=list(strategy.book.closed_R),
            unknown=strategy.book.first_unknown,
            cash=strategy._cash(),
            marks=dict(strategy.marks),
            quantities={s: st.quantity for s, st in strategy.policy.states.items()},
            lots={s: asdict(lot) for s, lot in strategy.book.lots.items()},
            unit_factors=dict(strategy.unit_factors),
        )
    finally:
        engine.dispose()


def main():
    import sys

    decoder = FrameDecoder()
    base = json.loads(json.dumps(asdict(frame()), default=lambda x: x.isoformat()))
    for change in (
        {},
        {"first_retest": False},
        {"trigger_price_eligible": False},
        {"minute": 1, "duration": 5},
    ):
        row = dict(base, **change)
        assert decoder.decode(row) == decode_frame(row)
    changed = json.loads(json.dumps(base))
    changed["anchors"][0]["past_touches"] += 1
    assert decoder.decode(changed) == decode_frame(changed)
    passed = []
    cases = [
        (route, case, scenario)
        for route in ("market", "capped")
        for case in ({}, {"partial": True}, {"missing": True}, {"split": True})
        for scenario in ("O-H-L-C", "O-L-H-C")
    ]
    if "--quick" in sys.argv:
        cases = [
            ("market", {}, "O-H-L-C"),
            ("market", {}, "O-L-H-C"),
            ("capped", {"partial": True}, "O-H-L-C"),
            ("market", {"missing": True, "split": True}, "O-L-H-C"),
        ]
    for route, case, scenario in cases:
        a = replay(source(**case), route, False, scenario)
        b = replay(source(**case), route, True, scenario)
        assert a == b, (route, case, scenario, [(k, a[k], b[k]) for k in a if a[k] != b[k]])
        passed.append(dict(route=route, case=case, scenario=scenario))
    print(
        json.dumps(
            dict(
                inert_feed_parity=passed,
                exact_field_decoder_checks=5,
                market_inputs=0,
                economic_result=False,
            )
        )
    )


if __name__ == "__main__":
    main()
