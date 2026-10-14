from dataclasses import replace
from datetime import timedelta

import pytest
from context_producer import ContextProducer
from decision_system import Anchor, Support, read_parameters
from native_book_view import NativeBookView
from test_decision_system import SPEC, T, book, frame, system


def daily(**changes):
    row = dict(
        status="observed",
        available_at=T - timedelta(days=1),
        average_dollar_volume=2e6,
        adr=0.06,
        return30=0.2,
        prior_return=0.01,
        strength="lead",
        close=10,
        ema={9: 9.86, 21: 8, 50: 7},
        previous_ema={9: 9.85, 21: 7.9, 50: 6.9},
        shape_ok=True,
        base_start=None,
        base_recognized_at=None,
        base_age=None,
        base_floor=None,
        base_breakout_level=None,
    )
    return {**row, **changes}


def update(producer, ordinal, **changes):
    at = T + timedelta(days=ordinal)
    row = daily(available_at=at - timedelta(hours=12), **changes)
    producer.prior_session_update({"SOFI": row}, at, ordinal)
    return row


def test_actual_compiled_frame_duplicate_measure_invariance():
    producer = ContextProducer()
    d = update(
        producer,
        0,
        base_start=T - timedelta(days=8),
        base_recognized_at=T - timedelta(days=6),
        base_age=8,
        base_floor=9,
        base_breakout_level=11,
    )
    f = frame()
    lower = dict(
        start=T + timedelta(minutes=1),
        end=T + timedelta(minutes=2),
        minute=0,
        duration=1,
        close=10,
        low=9.82,
        day_low=9.8,
        complete=True,
    )
    prev = dict(end=lower["start"], duration=1, high=9.99, low=9.82)
    compiled = producer.compile_frame(
        symbol="SOFI",
        daily=d,
        hourly=dict(status="observed", available_at=d["available_at"], ema={9: 7, 21: 6}),
        weekly=None,
        indexes={},
        watchlist={"SOFI"},
        lower=lower,
        previous_lower=prev,
        session=f.session,
        session_index=0,
        anchors=(Anchor("remote", d["available_at"], 20, 1, None),),
        past_minute_volume=100000,
        pause_sessions=0,
    )
    compiled = replace(compiled, market="neutral")
    s = system("P_ANCHOR")
    assert s.step(compiled, book()) == []
    repeated = replace(compiled, supports=compiled.supports * 3)
    assert system("P_ANCHOR").step(repeated, book()) == []
    distinct = replace(
        compiled, supports=compiled.supports + (Support("hourly:ema:50", 9.86, d["available_at"]),)
    )
    assert len(system("P_ANCHOR").step(distinct, book())) == 1


def test_incarnation_transitions_to_actual_base_without_rebirth():
    p = ContextProducer()
    update(p, 0)
    fallback = p.epochs["SOFI"].id
    origin, known = T - timedelta(days=8), T - timedelta(days=6)
    update(
        p,
        1,
        base_start=origin,
        base_recognized_at=known,
        base_age=8,
        base_floor=9,
        base_breakout_level=11,
    )
    epoch = p.epochs["SOFI"]
    assert epoch.id != fallback and epoch.origin == origin and epoch.known_at == known
    update(
        p,
        2,
        base_start=origin,
        base_recognized_at=known,
        base_age=9,
        base_floor=8,
        base_breakout_level=12,
    )
    assert p.epochs["SOFI"] is epoch and epoch.floor == 9


def test_invalidated_origin_cannot_recreate_or_restore_quota():
    p = ContextProducer()
    origin, known = T - timedelta(days=8), T - timedelta(days=6)
    args = dict(
        base_start=origin,
        base_recognized_at=known,
        base_floor=9,
        base_breakout_level=11,
        base_age=8,
    )
    update(p, 0, **args)
    epoch = p.epochs["SOFI"]
    update(p, 1, **args, close=8)
    update(p, 2, **args, close=8)
    assert epoch.invalid
    update(p, 3, **args)
    assert p.epochs["SOFI"] is epoch and epoch.invalid
    assert origin in p.invalidated_origins["SOFI"]
    new_origin = T + timedelta(days=1)
    update(
        p,
        5,
        base_start=new_origin,
        base_recognized_at=T + timedelta(days=3),
        base_age=3,
        base_floor=9,
        base_breakout_level=11,
    )
    assert p.epochs["SOFI"].origin == new_origin


def test_expiry_uses_original_origin_not_observation_birth():
    p = ContextProducer()
    origin, known = T - timedelta(days=59), T - timedelta(days=57)
    args = dict(
        base_start=origin,
        base_recognized_at=known,
        base_floor=9,
        base_breakout_level=11,
        base_origin_session=-59,
        base_age=58,
    )
    update(p, 0, **args)
    epoch = p.epochs["SOFI"]
    update(p, 1, **args)
    assert epoch.invalid and p.epochs["SOFI"] is epoch


def test_reservation_failed_validation_is_nonmutating_and_sale_T1():
    p = read_parameters(SPEC)
    b = NativeBookView(p, 20)
    order = system().step(frame(), book())[0]
    b.reserve(order)
    with pytest.raises(ValueError):
        b.terminal_entry(order.id, quantity=order.quantity + 1, price=10, fee=1)
    assert order.id in b.reserved
    b.terminal_entry(order.id, quantity=1, price=10, fee=0.02)
    b.terminal_exit("SOFI", quantity=1, price=11, fee=0.022, session=0)
    view, _ = b.view(native_cash=20000.958, marks={}, states={}, session=0, month="2024-11")
    assert view.spendable_cash == pytest.approx(19989.98)
    view, _ = b.view(native_cash=20000.958, marks={}, states={}, session=1, month="2024-11")
    assert view.spendable_cash == pytest.approx(20000.958)
    assert b.closed_R == [pytest.approx(0.958 / (order.quantity * (order.reference - order.stop)))]


def test_native_book_unknown_never_heals():
    b = NativeBookView(read_parameters(SPEC), 20)
    b.mark_unknown("active gap")
    with pytest.raises(ValueError):
        b.view(native_cash=20000, marks={}, states={}, session=0, month="2024-11")
