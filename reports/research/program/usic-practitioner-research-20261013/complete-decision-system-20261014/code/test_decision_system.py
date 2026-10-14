from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from context_producer import leadership, market_state
from decision_system import (
    Anchor,
    Book,
    DecisionSystem,
    Frame,
    Support,
    read_parameters,
    select_anchor,
)
from geometry import Day, context, pivots

SPEC = (
    Path(__file__).resolve().parents[6]
    / "strategy_specs/drafts/martin_complete_system_20261014.yaml"
)
T = datetime(2024, 11, 1, 13, 31, tzinfo=UTC)


def frame():
    return Frame(
        "SOFI",
        T,
        T - timedelta(minutes=1),
        "2024-11-01",
        "base1",
        0,
        1,
        10,
        9.82,
        9.99,
        9.82,
        9.8,
        0.06,
        9.86,
        9.84,
        9.95,
        T - timedelta(days=1),
        True,
        "neutral",
        True,
        True,
        (Support("hourly:ema:9", 9.85, T - timedelta(days=1)),),
        (Anchor("base", T - timedelta(days=3), 9.85, 3, T - timedelta(days=1)),),
        ema9_previous=9.85,
        ema21_previous=9.83,
        past_minute_volume=100000,
        base_breakout_level=9.99,
    )


def book():
    return Book(20000, 20000, 0, 0, 0, 20000)


def system(candidate="P_SYSTEM", route="market"):
    return DecisionSystem(read_parameters(SPEC), candidate, route=route)


def report_entry(s, symbol, at, **kwargs):
    order = s.states[symbol].pending
    q = kwargs.get("quantity", 0)
    return s.entry_report(
        symbol,
        at,
        order_id=order.id,
        report_id=f"entry:{at.isoformat()}:{q}",
        terminal=True,
        cancelled_quantity=order.quantity - q,
        **kwargs,
    )


def report_exit(s, symbol, at, quantity, **kwargs):
    state = s.states[symbol]
    stopout = kwargs.get("stopout", False)
    order = state.protective if stopout else state.pending_exit
    cancelled = (
        (state.pending_exit.id,)
        if stopout and state.pending_exit
        else ((state.protective.id,) if not stopout and state.protective else ())
    )
    return s.exit_report(
        symbol,
        at,
        quantity,
        order_id=order.id,
        report_id=f"exit:{at.isoformat()}:{quantity}",
        terminal=True,
        cancelled_quantity=order.quantity - quantity,
        cancelled_order_ids=cancelled,
        **kwargs,
    )


def test_future_price_and_anchor_cannot_change_past_geometry():
    p = read_parameters(SPEC)
    hist = [
        Day(
            T - timedelta(days=40 - i),
            10,
            10.4 + (i % 5) / 10,
            9.5 + (i % 3) / 10,
            10 + (i % 4) / 10,
            10000,
            10,
        )
        for i in range(30)
    ]
    before = context(hist, T - timedelta(days=11), p)
    future = Day(T + timedelta(days=10), 9999, 20000, 1, 9999, 1e12, 9999)
    assert before == context(hist + [future], T - timedelta(days=11), p)
    known = Anchor("known", T - timedelta(days=1), 10, 1, None)
    unseen = Anchor("unseen", T + timedelta(days=1), 10, 1000, None)
    assert select_anchor((known, unseen), T, prior_respect=True, cap=3) == known


def test_pivot_is_unavailable_until_right_confirmation_closes():
    days = [Day(T + timedelta(days=i), 10, 11 if i == 2 else 10, 9, 10, 100, 10) for i in range(5)]
    assert not any(i == 2 and kind == "high" for i, _, kind in pivots(days[:4], 2, 2))
    assert (2, 4, "high") in pivots(days, 2, 2)


def test_intent_never_fills_on_decision_completion_and_quantity_is_frozen():
    s = system()
    f = frame()
    order = s.step(f, book())[0]
    assert order.quantity > 0 and order.stop < order.reference
    with pytest.raises(ValueError):
        report_entry(
            s,
            f.symbol,
            T - timedelta(microseconds=1),
            filled=True,
            price=10,
            quantity=order.quantity,
        )
    with pytest.raises(ValueError):
        report_entry(
            s,
            f.symbol,
            T + timedelta(seconds=1),
            filled=True,
            price=10,
            quantity=order.quantity + 1,
        )
    protect = report_entry(
        s, f.symbol, T + timedelta(seconds=1), filled=True, price=10, quantity=order.quantity
    )
    assert protect.stop == order.stop and protect.created_at == protect.eligible_after


def test_capped_fill_above_limit_rejected_but_nonfill_retained():
    s = system(route="capped")
    f = frame()
    order = s.step(f, book())[0]
    with pytest.raises(ValueError):
        report_entry(
            s,
            f.symbol,
            T + timedelta(seconds=1),
            filled=True,
            price=order.price_cap + 0.01,
            quantity=1,
        )
    report_entry(s, f.symbol, T + timedelta(seconds=1), filled=False)
    assert s.states[f.symbol].attempts_epoch == 1 and s.states[f.symbol].quantity == 0


def test_nearby_confluence_required_wide_candle_does_not_fake_it():
    s = system()
    f = replace(
        frame(),
        ema9=8,
        ema21=6,
        ema9_previous=7.9,
        ema21_previous=5.9,
        supports=(),
        anchors=(Anchor("x", T - timedelta(days=1), 4, 1, None),),
        low=3,
    )
    assert s.step(f, book()) == []
    assert s.states[f.symbol].audit[-1]["reason"] == "watchlist_without_support_confirmation"


def test_no_cash_no_entry_and_feedback_resumes_only_probe_after_pause():
    assert system().step(frame(), replace(book(), spendable_cash=0)) == []
    b = replace(book(), drawdown_from_recent_peak=0.06)
    assert system().step(frame(), b) == []
    s = system()
    f = replace(frame(), sessions_since_risk_pause=3)
    o = s.step(f, b)[0]
    assert o.quantity * (o.reference - o.stop) <= 20000 * 0.00125


def test_full_path_holds_overnight_and_partial_keeps_initial_R():
    s = system("P_HOLD")
    f = frame()
    o = s.step(f, book())[0]
    report_entry(s, f.symbol, T + timedelta(seconds=1), filled=True, price=10, quantity=o.quantity)
    initial = (s.states[f.symbol].reference, s.states[f.symbol].initial_stop)
    f2 = replace(
        f,
        start=T + timedelta(days=1),
        end=T + timedelta(days=1, minutes=1),
        session="2024-11-02",
        close=10.8,
        low=10.5,
        market="strong",
    )
    assert s.step(f2, book()) == []
    f3 = replace(f2, start=f2.end, end=f2.end + timedelta(minutes=1), market="neutral")
    trim = s.step(f3, book())[0]
    assert trim.quantity == int(o.quantity * 0.15)
    report_exit(s, f.symbol, trim.eligible_after, trim.quantity)
    assert (s.states[f.symbol].reference, s.states[f.symbol].initial_stop) == initial
    assert s.states[f.symbol].quantity == o.quantity - trim.quantity


def test_failed_partial_is_not_counted_as_profit_taken():
    s = system("P_HOLD")
    f = frame()
    o = s.step(f, book())[0]
    report_entry(s, f.symbol, T + timedelta(seconds=1), filled=True, price=10, quantity=o.quantity)
    f2 = replace(
        f, start=T + timedelta(minutes=1), end=T + timedelta(minutes=2), close=10.8, low=10.5
    )
    trim = s.step(f2, book())[0]
    report_exit(s, f.symbol, trim.eligible_after, 0, filled=False)
    assert not s.states[f.symbol].trimmed and s.states[f.symbol].quantity == o.quantity


def test_repeat_or_future_context_is_rejected():
    s = system()
    f = frame()
    s.step(f, book())
    with pytest.raises(ValueError):
        s.step(f, book())
    with pytest.raises(ValueError):
        system().step(replace(f, context_available_at=f.end), book())


def test_stopout_requires_fresh_support_before_reentry():
    s = system("P_REENTRY")
    f = frame()
    o = s.step(f, book())[0]
    at = T + timedelta(seconds=1)
    report_entry(s, f.symbol, at, filled=True, price=10, quantity=o.quantity)
    report_exit(s, f.symbol, at + timedelta(seconds=1), o.quantity, stopout=True)
    f2 = replace(
        f, start=T + timedelta(minutes=1), end=T + timedelta(minutes=2), close=10.5, low=10.4
    )
    assert s.step(f2, book()) == []
    f3 = replace(f, start=f2.end, end=f2.end + timedelta(minutes=1))
    assert s.step(f3, book())[0].quantity > 0


def test_trim_cannot_fill_more_than_the_outstanding_trim_intent():
    s = system("P_HOLD")
    f = frame()
    buy = s.step(f, book())[0]
    report_entry(s, f.symbol, T, filled=True, price=10, quantity=buy.quantity)
    next_frame = replace(f, start=T, end=T + timedelta(minutes=1), close=10.8, low=10.5)
    trim = s.step(next_frame, book())[0]
    assert trim.quantity < buy.quantity
    with pytest.raises(ValueError):
        report_exit(s, f.symbol, trim.eligible_after, buy.quantity)
    assert s.states[f.symbol].quantity == buy.quantity
    remaining_protection = report_exit(s, f.symbol, trim.eligible_after, trim.quantity)
    assert remaining_protection.quantity == buy.quantity - trim.quantity


def test_stopout_cannot_precede_actual_entry_fill():
    s = system()
    f = frame()
    buy = s.step(f, book())[0]
    report_entry(s, f.symbol, T, filled=True, price=10, quantity=buy.quantity)
    with pytest.raises(ValueError):
        report_exit(s, f.symbol, T - timedelta(days=1), buy.quantity, stopout=True)
    assert s.states[f.symbol].quantity == buy.quantity


def test_terminal_partial_requires_explicit_remainder_cancellation():
    s = system()
    f = frame()
    buy = s.step(f, book())[0]
    with pytest.raises(ValueError):
        s.entry_report(
            f.symbol,
            T,
            filled=True,
            price=10,
            quantity=1,
            order_id=buy.id,
            report_id="partial-no-cancel",
            terminal=False,
            cancelled_quantity=0,
        )
    assert s.states[f.symbol].pending == buy
    protect = report_entry(s, f.symbol, T, filled=True, price=10, quantity=1)
    assert protect.quantity == 1
    assert s.states[f.symbol].audit[-1]["cancelled_quantity"] == buy.quantity - 1
    assert s.states[f.symbol].submitted_planned_R0 == buy.quantity * (buy.reference - buy.stop)


def test_report_identity_and_replay_protection():
    s = system()
    f = frame()
    buy = s.step(f, book())[0]
    with pytest.raises(ValueError):
        s.entry_report(
            f.symbol,
            T,
            filled=True,
            price=10,
            quantity=buy.quantity,
            order_id="other",
            report_id="report",
            terminal=True,
            cancelled_quantity=0,
        )
    report_entry(s, f.symbol, T, filled=True, price=10, quantity=buy.quantity)
    with pytest.raises(ValueError):
        s.entry_report(
            f.symbol,
            T,
            filled=True,
            price=10,
            quantity=buy.quantity,
            order_id=buy.id,
            report_id="entry-replay",
            terminal=True,
            cancelled_quantity=0,
        )


def test_active_gap_is_sticky_despite_later_valid_prices():
    s = system()
    f = frame()
    buy = s.step(f, book())[0]
    gap = replace(f, start=T, end=T + timedelta(minutes=1), active_data_complete=False)
    assert s.step(gap, book()) == []
    later = replace(f, start=gap.end, end=gap.end + timedelta(minutes=1))
    assert s.step(later, book()) == []
    assert s.states[f.symbol].path_unknown
    assert s.states[f.symbol].audit[-1]["reason"] == "sticky_unknown_active_path"
    assert s.states[f.symbol].pending == buy


def test_all_eight_policies_have_both_independent_routes():
    f = frame()
    for name in [
        "B_BREAK",
        "P_EMA",
        "P_SHAPE",
        "P_ANCHOR",
        "P_REENTRY",
        "P_HOLD",
        "P_FEEDBACK",
        "P_SYSTEM",
    ]:
        market = system(name, route="market").step(f, book())[0]
        capped = system(name, route="capped").step(f, book())[0]
        assert market.quantity == capped.quantity
        assert market.price_cap is None and capped.price_cap is not None
        assert market.reserved_cash == capped.reserved_cash
        assert market.reserved_risk == capped.reserved_risk


def test_joint_capacity_and_cost_scenario_affect_pretrade_reservation():
    f = frame()
    assert system().step(f, replace(book(), held_or_reserved_names=4)) == []
    p = read_parameters(SPEC)
    primary = DecisionSystem(p, cost_bps_per_side=20).step(f, book())[0]
    stress = DecisionSystem(p, cost_bps_per_side=40).step(f, book())[0]
    assert stress.quantity < primary.quantity
    assert stress.reserved_risk <= book().equity * p["risk_probe"]


def test_touch_does_not_survive_new_session_and_epoch_counters_do():
    s = system("P_EMA")
    f = replace(frame(), close=9.9, previous_high=10)
    assert s.step(f, book()) == []
    assert s.states[f.symbol].touch_end
    nxt = replace(
        frame(),
        start=T + timedelta(days=1),
        end=T + timedelta(days=1, minutes=1),
        session="2024-11-04",
        low=10.3,
        close=10.4,
    )
    assert s.step(nxt, book()) == []
    assert s.states[f.symbol].touch_end is None


def test_leadership_uses_prior_snapshot_and_ties_are_deterministic():
    row = dict(
        status="observed",
        available_at=T - timedelta(days=1),
        average_dollar_volume=2e6,
        adr=0.06,
        return30=0.2,
        prior_return=0.01,
    )
    snapshot = {s: dict(row) for s in ["SOUN", "SOFI", "SMCI", "LMND", "GME", "COIN"]}
    prior = leadership(snapshot, T)
    assert prior[0] == ["COIN", "GME", "LMND"]
    snapshot["FUTURE"] = {**row, "available_at": T + timedelta(days=1), "return30": 999}
    assert leadership(snapshot, T) == prior


def test_unknown_index_context_cannot_become_neutral_or_enter():
    assert market_state({}, T) == "unknown"
    s = system()
    f = replace(frame(), market="unknown")
    assert s.step(f, book()) == []


def test_old_epoch_quota_cannot_be_reset_by_round_trip_epoch_labels():
    s = system("P_EMA")
    f = frame()
    s.step(f, book())
    report_entry(s, f.symbol, T, filled=False)
    nextf = replace(f, start=T + timedelta(minutes=1), end=T + timedelta(minutes=2), epoch="base2")
    o2 = s.step(nextf, book())[0]
    assert o2
    report_entry(s, f.symbol, nextf.end, filled=False)
    returned = replace(f, start=nextf.end, end=nextf.end + timedelta(minutes=1))
    assert s.step(returned, book()) == []
    assert s.states[f.symbol].audit[-1]["reason"] == "attempt_budget_exhausted"
