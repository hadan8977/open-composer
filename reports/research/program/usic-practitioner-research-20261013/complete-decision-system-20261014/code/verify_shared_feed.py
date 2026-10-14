"""Inert independent-account/source immutability and feedback parity."""

import json
from dataclasses import asdict

import native_shared_feed
from decision_system import read_parameters
from native_engine import make_engine
from native_events import source_intervals
from test_decision_system import SPEC
from verify_feed_reuse import canonical_audit, replay, source


def snapshot(strategy):
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


def verify_case(case, scenario):
    packets = source(**case)
    expected = [
        replay(packets, route, True, scenario, candidate=candidate)
        for candidate, route in (("P_SYSTEM", "market"), ("P_EMA", "capped"))
    ]
    accounts = [
        make_engine(
            read_parameters(SPEC),
            candidate,
            route,
            20,
            dict(spec="inert", input="synthetic", contract="inert"),
            {"SMCI": 0.1},
        )
        for candidate, route in (("P_SYSTEM", "market"), ("P_EMA", "capped"))
    ]
    factors = {"SMCI": 0.1}
    generated = []
    original = native_shared_feed.native_month

    def observed(*args, **kwargs):
        data = original(*args, **kwargs)
        quotes = data[1]
        before = [(q.ts_event, q.bid_price.as_double(), q.bid_size.as_double()) for q in quotes]
        generated.append((quotes, before))
        return data

    native_shared_feed.native_month = observed
    try:
        for interval, afternoon in source_intervals(packets, 120):
            factors, _ = native_shared_feed.feed(
                accounts, interval, scenario, factors, None, afternoon=afternoon
            )
        actual = []
        for engine, strategy in accounts:
            engine.end()
            actual.append(snapshot(strategy))
        assert actual == expected, [
            (i, k) for i in range(2) for k in actual[i] if actual[i][k] != expected[i][k]
        ]
        for quotes, before in generated:
            assert before == [
                (q.ts_event, q.bid_price.as_double(), q.bid_size.as_double()) for q in quotes
            ]
        assert accounts[0][1].policy is not accounts[1][1].policy
        assert accounts[0][1].book is not accounts[1][1].book
        assert accounts[0][0].cache is not accounts[1][0].cache
        return dict(
            case=case, scenario=scenario, independent_accounts_equal=True, quote_data_immutable=True
        )
    finally:
        native_shared_feed.native_month = original
        for e, _s in accounts:
            e.dispose()


def main():
    rows = []
    for case, scenario in (
        ({}, "O-H-L-C"),
        ({"partial": True}, "O-L-H-C"),
        ({"missing": True, "split": True}, "O-H-L-C"),
    ):
        rows.append(verify_case(case, scenario))
    from types import SimpleNamespace

    from native_book_view import NativeBookView
    from nautilus_policy_adapter import MartinNativeStrategy

    def book():
        b = NativeBookView(read_parameters(SPEC), 20)
        b.month = "2024-11"
        b.month_peak = 22000
        b.pause_session = 0
        b.resume_session = 3
        b.resume_peak = 20000
        b.closed_at_pause = 0
        b.closed_R = [1.0] * 6
        return b

    ref = book()
    optimized = book()
    cache = None
    reference = []
    reused = []
    for _ in range(3):
        reference.append(
            ref.view(native_cash=20000, marks={}, states={}, session=3, month="2024-11")
        )
        proxy = SimpleNamespace(book=optimized)
        if cache is None:
            before = MartinNativeStrategy._view_controller_key(proxy)
            value = optimized.view(
                native_cash=20000, marks={}, states={}, session=3, month="2024-11"
            )
            if before == MartinNativeStrategy._view_controller_key(proxy):
                cache = value
        else:
            value = cache
        reused.append(value)
    assert reference == reused and reference[0][0].drawdown_from_recent_peak == 0
    assert reference[1][0].drawdown_from_recent_peak > 0
    print(
        json.dumps(
            dict(
                shared_feed_inert=rows,
                feedback_recovery_repause_exact=True,
                market_files_read=0,
                full_economic_cells=0,
            )
        )
    )


if __name__ == "__main__":
    main()
