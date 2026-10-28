from datetime import UTC, date, datetime

import pytest

from open_composer.intraday_runner.source_method_controls import (
    buy_batch,
    cleanup_clock,
    live_quote_ok,
    owned_account_capacity,
    primary_calendar,
    require_primary_commit,
    require_window,
    risk_state,
)

START = datetime(2026, 10, 19, tzinfo=UTC)
END = datetime(2026, 11, 14, tzinfo=UTC)
DAY = date(2026, 11, 3)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("control rehearsal cannot use a network")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)


def test_primary_calendar_is_not_an_october19_adoption():
    clock = primary_calendar(date(2026, 10, 31))
    assert clock["decision"] == date(2026, 11, 2)
    assert clock["execution"] == DAY
    assert clock["commit_at"].astimezone(UTC) == datetime(2026, 11, 2, 21, 15, tzinfo=UTC)
    args = dict(
        source_cutoff=clock["signal_cutoff"],
        produced_at=clock["signal_cutoff"],
        committed_at=clock["commit_at"],
        authorized_at=START,
    )
    require_primary_commit(date(2026, 10, 31), DAY, **args)
    with pytest.raises(ValueError):
        require_primary_commit(date(2026, 10, 31), date(2026, 10, 19), **args)
    with pytest.raises(ValueError):
        primary_calendar(date(2026, 10, 30))


def test_late_october_reconstruction_is_not_authorized_contemporaneous_signal():
    clock = primary_calendar(date(2026, 9, 30))
    with pytest.raises(ValueError):
        require_primary_commit(
            date(2026, 9, 30),
            clock["execution"],
            source_cutoff=clock["signal_cutoff"],
            produced_at=datetime(2026, 10, 17, tzinfo=UTC),
            committed_at=clock["commit_at"],
            authorized_at=START,
        )


def test_missing_commit_before_execution_is_not_recovered_by_latest_forecast():
    clock = primary_calendar(date(2026, 10, 31))
    with pytest.raises(ValueError):
        require_primary_commit(
            date(2026, 10, 31),
            DAY,
            source_cutoff=clock["signal_cutoff"],
            produced_at=datetime(2026, 11, 3, tzinfo=UTC),
            committed_at=clock["commit_at"],
            authorized_at=START,
        )


def test_existing_account_envelope_and_other_reserved_cash_not_reused():
    args = dict(
        allocated=20000,
        account_unborrowed_available=50000,
        other_reserved_cash=40000,
        account_gross=90000,
        account_gross_cap=100000,
        sleeve_gross=6000,
        existing_own_buy_reservations=1000,
        conflicts=False,
        identity_matches=True,
        complete_observation=True,
    )
    assert owned_account_capacity(**args) == 9000
    assert owned_account_capacity(**{**args, "other_reserved_cash": 50000}) == 0
    assert owned_account_capacity(**{**args, "account_gross": 100000}) == 0
    for key, value in [
        ("conflicts", True),
        ("identity_matches", False),
        ("complete_observation", False),
        ("allocated", 20001),
    ]:
        with pytest.raises(ValueError):
            owned_account_capacity(**{**args, key: value})


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -1, True])
def test_unknown_capacity_does_not_turn_into_unencumbered_cash(value):
    with pytest.raises((ValueError, TypeError)):
        owned_account_capacity(
            allocated=20000,
            account_unborrowed_available=value,
            other_reserved_cash=0,
            account_gross=0,
            account_gross_cap=100000,
            sleeve_gross=0,
            existing_own_buy_reservations=0,
            conflicts=False,
            identity_matches=True,
            complete_observation=True,
        )


def test_ordinary_wave_in_wind_down_is_rejected():
    with pytest.raises(ValueError):
        require_window(
            datetime(2026, 11, 13, 14, 40, tzinfo=UTC),
            date(2026, 11, 13),
            "buy",
            authorized_at=START,
            expires_at=END,
        )


def test_dst_preserves_nine_thirty_five_ny_not_old_utc_hour():
    wave = require_window(
        datetime(2026, 11, 3, 14, 35, tzinfo=UTC),
        DAY,
        "sell",
        authorized_at=START,
        expires_at=END,
    )
    assert wave.astimezone(UTC).hour == 14
    with pytest.raises(ValueError):
        require_window(
            datetime(2026, 11, 3, 13, 35, tzinfo=UTC),
            DAY,
            "sell",
            authorized_at=START,
            expires_at=END,
        )


def test_expiry_and_close_cleanup_do_not_create_indefinite_exit_authority():
    day, start, last = cleanup_clock(END)
    assert day == date(2026, 11, 13)
    assert start.astimezone(UTC) == datetime(2026, 11, 13, 20, 30, tzinfo=UTC)
    assert last.astimezone(UTC) == datetime(2026, 11, 13, 20, 59, tzinfo=UTC)
    require_window(
        start, day, "sell", authorized_at=START, expires_at=END, cleanup=True, own_exit_allowed=True
    )
    with pytest.raises(ValueError):
        require_window(
            last,
            day,
            "sell",
            authorized_at=START,
            expires_at=END,
            cleanup=True,
            own_exit_allowed=True,
        )
    with pytest.raises(ValueError):
        require_window(
            END,
            date(2026, 11, 13),
            "sell",
            authorized_at=START,
            expires_at=END,
            cleanup=True,
            own_exit_allowed=True,
            killed=True,
        )


def test_early_close_cleanup_and_earlier_account_expiry_are_recomputed():
    day, start, last = cleanup_clock(datetime(2026, 11, 28, tzinfo=UTC))
    assert day == date(2026, 11, 27)
    assert start.astimezone(UTC).hour == 17
    assert last.astimezone(UTC).hour == 17
    assert cleanup_clock(datetime(2026, 11, 6, 20, 45, tzinfo=UTC))[0] == date(2026, 11, 5)


def test_five_percent_halts_new_risk_without_claiming_an_exit_or_loss_bound():
    r = risk_state(
        19000, 20000, 20000, marks_complete=True, prior_daily_halt=False, prior_kill=False
    )
    assert r["daily_halt"] and not r["kill"] and not r["new_risk_allowed"]
    recovered = risk_state(
        21000, 20000, 20000, marks_complete=True, prior_daily_halt=True, prior_kill=False
    )
    assert recovered["daily_halt"] and not recovered["new_risk_allowed"]


@pytest.mark.parametrize("nav", [15000, 0, -10])
def test_known_complete_nav_loss_latches_kill(nav):
    r = risk_state(nav, 20000, 20000, marks_complete=True, prior_daily_halt=False, prior_kill=False)
    assert r["kill"] and not r["new_risk_allowed"]


def test_missing_mark_is_not_zero_and_does_not_erase_prior_kill():
    r = risk_state(
        None, 20000, 20000, marks_complete=False, prior_daily_halt=False, prior_kill=True
    )
    assert r["kill"] and not r["new_risk_allowed"]
    assert r["high_water"] == 20000


def test_raw_validity_does_not_waive_actual_dispatch_age():
    wave = datetime(2026, 11, 3, 14, 40, tzinfo=UTC)
    timestamp = int(wave.timestamp()) * 10**9
    assert live_quote_ok({"valid": True, "timestamp_ns": timestamp}, wave, wave)
    assert not live_quote_ok({"valid": True, "timestamp_ns": timestamp + 1}, wave, wave)
    assert not live_quote_ok({"valid": False, "timestamp_ns": timestamp}, wave, wave)
    assert not live_quote_ok(
        {"valid": True, "timestamp_ns": timestamp - 5 * 10**9},
        wave.replace(second=1),
        wave,
    )


def test_batch_uniform_funding_and_single_display_cap_keep_unspent_remainder():
    wave = datetime(2026, 11, 3, 14, 40, tzinfo=UTC)
    quotes = {
        s: {"valid": True, "timestamp_ns": int(wave.timestamp()) * 10**9, "ask": p, "ask_shares": q}
        for s, p, q in [("A", 10, 10), ("B", 20, 4)]
    }
    args = dict(
        now=wave,
        wave=wave,
        owned_source_capacity=90,
        accepted_unborrowed_capacity=1000,
        sleeve_new_gross_capacity=20000,
        fee_buffer_rate=0,
        new_risk_allowed=True,
    )
    rows = buy_batch(
        [{"symbol": "A", "max_quantity": 10}, {"symbol": "B", "max_quantity": 10}], quotes, **args
    )
    assert [r["quantity"] for r in rows] == [5, 2]
    assert [r["scale"] for r in rows] == [0.5, 0.5]
    args["new_risk_allowed"] = False
    assert all(
        r["quantity"] == 0 for r in buy_batch([{"symbol": "A", "max_quantity": 10}], quotes, **args)
    )


@pytest.mark.parametrize("unknown", [None, "unknown", "false", 0, 1])
def test_R1_unknown_risk_evidence_cannot_reset_known_latches(unknown):
    for key in ("marks_complete", "prior_daily_halt", "prior_kill"):
        flags = dict(marks_complete=True, prior_daily_halt=True, prior_kill=True)
        flags[key] = unknown
        before = dict(flags)
        with pytest.raises(ValueError, match="unknown mark/latch"):
            risk_state(20000, 20000, 20000, **flags)
        assert flags == before


def test_R1_genuine_boolean_risk_flags_preserve_latches_and_mark_block():
    for marks in (False, True):
        for halt in (False, True):
            for kill in (False, True):
                row = risk_state(
                    20000,
                    20000,
                    20000,
                    marks_complete=marks,
                    prior_daily_halt=halt,
                    prior_kill=kill,
                )
                assert row["daily_halt"] is halt and row["kill"] is kill
                assert row["new_risk_allowed"] is (marks and not halt and not kill)
                assert row["high_water"] == 20000


@pytest.mark.parametrize("unknown", [None, "unknown", "false", 0, 1])
def test_R1_unknown_cleanup_flags_never_open_an_exit_window(unknown):
    for key in ("cleanup", "own_exit_allowed", "killed"):
        flags = dict(cleanup=True, own_exit_allowed=True, killed=True)
        flags[key] = unknown
        with pytest.raises(ValueError, match="unknown cleanup/exit/kill"):
            require_window(
                datetime(2026, 11, 3, 14, 31, tzinfo=UTC),
                DAY,
                "sell",
                authorized_at=START,
                expires_at=END,
                **flags,
            )


def test_R1_genuine_cleanup_true_and_false_keep_original_windows():
    now = datetime(2026, 11, 3, 14, 31, tzinfo=UTC)
    assert (
        require_window(
            now,
            DAY,
            "sell",
            authorized_at=START,
            expires_at=END,
            cleanup=True,
            own_exit_allowed=True,
            killed=True,
        )
        == now
    )
    for kwargs in [
        dict(own_exit_allowed=False, killed=True),
        dict(own_exit_allowed=True, killed=False),
    ]:
        with pytest.raises(ValueError):
            require_window(
                now, DAY, "sell", authorized_at=START, expires_at=END, cleanup=True, **kwargs
            )
    wave = now.replace(minute=35)
    assert (
        require_window(
            wave,
            DAY,
            "sell",
            authorized_at=START,
            expires_at=END,
            cleanup=False,
            own_exit_allowed=False,
            killed=False,
        )
        == wave
    )
