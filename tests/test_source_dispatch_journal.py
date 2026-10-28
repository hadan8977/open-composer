"""Durability/clock/ownership fixtures only; no broker or provider transport."""

import copy
import hashlib
import json
import socket
import stat
from datetime import UTC, date, datetime, timedelta

import pytest

from open_composer.intraday_runner import source_dispatch_journal as module
from open_composer.intraday_runner.source_dispatch_journal import (
    SourceDispatchJournal,
    classify_own_order,
)

NOW = datetime(2026, 11, 3, 14, 35, tzinfo=UTC)
START = datetime(2026, 10, 19, tzinfo=UTC)
END = datetime(2026, 11, 14, tzinfo=UTC)
CID = "dia-base-2026-11-03-sell-AAPL"


@pytest.fixture
def case(tmp_path, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("No network in dispatch journal fixture")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    signal = tmp_path / "logged-signal.json"
    signal.write_bytes(b'{"fixture":true}')
    reservation = dict(side="sell", symbol="AAPL", quantity=6, filled=0, limit_price=10.0)
    request = dict(
        client_order_id=CID,
        symbol="AAPL",
        side="sell",
        qty=6,
        type="limit",
        time_in_force="day",
        limit_price=10.0,
        reservation=reservation,
        quote=dict(
            valid=True,
            timestamp_ns=int(NOW.timestamp()) * 10**9,
            bid=10.0,
            ask=10.1,
            bid_shares=6,
            ask_shares=10,
        ),
    )
    snapshot = dict(
        pending={CID: copy.deepcopy(reservation)},
        consumed_ids=[CID],
        cashbook={"cash": 100.0, "lots": {"AAPL": 6}},
    )
    observed = dict(
        client_order_id=CID,
        symbol="AAPL",
        side="sell",
        qty="6",
        type="limit",
        time_in_force="day",
        limit_price="10",
        id="fixture-order",
        status="partially_filled",
        filled_qty="2",
    )
    calls = []

    def submit(row):
        calls.append(copy.deepcopy(row))
        return copy.deepcopy(observed)

    args = dict(
        prepared=request,
        reservation_snapshot=snapshot,
        signal_binding=dict(
            path=str(signal),
            bytes=signal.stat().st_size,
            sha256=hashlib.sha256(signal.read_bytes()).hexdigest(),
        ),
        execution_day=date(2026, 11, 3),
        authorized_at=START,
        expires_at=END,
        submit=submit,
        revalidate=lambda row: None,
        clock=lambda: NOW,
    )
    return SourceDispatchJournal(tmp_path / "journal"), args, calls, observed


def test_durable_consumption_before_callback_and_no_restart_retry(case):
    journal, args, calls, observed = case
    original = copy.deepcopy(args["reservation_snapshot"])
    submit = args["submit"]

    def inspect_then_submit(row):
        saved = journal.receive(CID)
        assert saved["stage"] == "dispatch_boundary_consumed_ack_unknown"
        assert saved["reservation_snapshot"] == original
        return submit(row)

    args["submit"] = inspect_then_submit
    result = journal.dispatch_once(**args)
    assert result["observations"] == [observed] and len(calls) == 1
    assert args["reservation_snapshot"] == original
    with pytest.raises(FileExistsError):
        SourceDispatchJournal(journal.directory).dispatch_once(**args)
    assert len(calls) == 1


def test_transport_exception_retains_unknown_and_prevents_resend(case):
    journal, args, calls, _ = case

    def fail(row):
        calls.append(row)
        raise TimeoutError("invented transport uncertainty")

    args["submit"] = fail
    with pytest.raises(TimeoutError):
        journal.dispatch_once(**args)
    saved = journal.receive(CID)
    assert saved["stage"] == "dispatch_boundary_consumed_ack_unknown"
    assert saved["error_type"] == "TimeoutError" and not saved["observations"]
    with pytest.raises(FileExistsError):
        journal.dispatch_once(**args)
    assert len(calls) == 1


def test_torn_consumed_file_is_not_retry_permission(case):
    journal, args, calls, _ = case
    journal.directory.mkdir()
    (journal.directory / f"{CID}.json").write_text('{"torn":')
    with pytest.raises(FileExistsError):
        journal.dispatch_once(**args)
    with pytest.raises(json.JSONDecodeError):
        journal.receive(CID)
    assert not calls


def test_journal_fsync_failure_retains_marker_and_never_calls_transport(case, monkeypatch):
    journal, args, calls, _ = case

    original_fsync = module.os.fsync

    def fail(fd):
        if stat.S_ISREG(module.os.fstat(fd).st_mode):
            raise OSError("invented marker-file fsync failure")
        original_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", fail)
    with pytest.raises(OSError):
        journal.dispatch_once(**args)
    assert (journal.directory / f"{CID}.json").exists() and not calls


def test_clock_after_durable_write_can_expire_quote_without_send(case, monkeypatch):
    journal, args, calls, _ = case
    current = [NOW]
    args["clock"] = lambda: current[0]
    actual = module._atomic_write_text

    def write_and_delay(path, content):
        actual(path, content)
        current[0] = NOW + timedelta(seconds=6)

    monkeypatch.setattr(module, "_atomic_write_text", write_and_delay)
    with pytest.raises(ValueError, match="dispatch interval"):
        journal.dispatch_once(**args)
    assert journal.receive(CID)["stage"] == "not_dispatched_guard_refusal"
    assert not calls


@pytest.mark.parametrize("value", [False, True, "approved", {}, 1])
def test_guard_status_is_not_actual_exception_guard(case, value):
    journal, args, calls, _ = case
    args["revalidate"] = lambda row: value
    with pytest.raises(ValueError, match="guard must raise"):
        journal.dispatch_once(**args)
    assert not calls and not journal.directory.exists()


@pytest.mark.parametrize(
    "field,value", [("type", "market"), ("qty", 7), ("limit_price", 9.0), ("symbol", "MSFT")]
)
def test_mutated_or_unprotected_request_never_sends(case, field, value):
    journal, args, calls, _ = case
    args["prepared"][field] = value
    with pytest.raises(ValueError):
        journal.dispatch_once(**args)
    assert not calls


def test_owned_partial_cancel_does_not_release_and_never_repeats(case):
    journal, args, _, _ = case
    journal.dispatch_once(**args)
    before = journal.receive(CID)["reservation_snapshot"]
    cancels = []
    kwargs = dict(
        authorized_at=START,
        expires_at=END,
        cancel=cancels.append,
        revalidate=lambda row: None,
        clock=lambda: NOW,
    )
    result = journal.cancel_own_remainder_once(CID, **kwargs)
    assert cancels == ["fixture-order"] and result["funds_releasable"] is False
    assert result["order"]["remaining"] == 4
    assert journal.receive(CID)["reservation_snapshot"] == before
    with pytest.raises(ValueError, match="already attempted"):
        journal.cancel_own_remainder_once(CID, **kwargs)
    assert len(cancels) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"client_order_id": "foreign"},
        {"symbol": "MSFT"},
        {"filled_qty": "7"},
        {"filled_qty": "NaN"},
        {"status": "filled"},
        {"status": "replaced"},
    ],
)
def test_nonmatching_or_inconsistent_observation_is_not_owned_cancel(case, change):
    _, args, _, observed = case
    with pytest.raises(ValueError):
        classify_own_order(args["prepared"], {**observed, **change})


@pytest.mark.parametrize(
    "change",
    [{"status": "filled", "filled_qty": "6"}, {"status": "pending_cancel"}, {"status": "canceled"}],
)
def test_terminal_or_pending_cancel_observation_is_no_new_cancel(case, change):
    _, args, _, observed = case
    result = classify_own_order(args["prepared"], {**observed, **change})
    assert not result["cancel_eligible"] and result["funds_releasable"] is False


def test_cancel_expiry_or_transport_failure_has_no_retry_or_cash_release(case):
    journal, args, _, _ = case
    journal.dispatch_once(**args)
    calls = []

    def fail(bid):
        calls.append(bid)
        raise TimeoutError("cancel unknown")

    kwargs = dict(
        authorized_at=START,
        expires_at=END,
        cancel=fail,
        revalidate=lambda row: None,
        clock=lambda: END,
    )
    with pytest.raises(ValueError, match="expired"):
        journal.cancel_own_remainder_once(CID, **kwargs)
    assert not calls and "cancel_attempt" not in journal.receive(CID)
    kwargs["clock"] = lambda: NOW
    with pytest.raises(TimeoutError):
        journal.cancel_own_remainder_once(CID, **kwargs)
    with pytest.raises(ValueError, match="already attempted"):
        journal.cancel_own_remainder_once(CID, **kwargs)
    assert len(calls) == 1


def test_mutating_callback_cannot_change_journal_request(case):
    journal, args, _, _ = case
    old = copy.deepcopy(args["prepared"])

    def guard(row):
        row["qty"] = 10000

    args["revalidate"] = guard
    result = journal.dispatch_once(**args)
    assert result["request"] == old


def test_signal_drift_during_journaling_is_rejected_before_transport(case, monkeypatch):
    journal, args, calls, _ = case
    actual = module._atomic_write_text

    def write_and_mutate(path, content):
        actual(path, content)
        module.Path(args["signal_binding"]["path"]).write_bytes(b'{"changed":true}')

    monkeypatch.setattr(module, "_atomic_write_text", write_and_mutate)
    with pytest.raises(ValueError, match="signal changed"):
        journal.dispatch_once(**args)
    assert not calls
    assert journal.receive(CID)["stage"] == "not_dispatched_guard_refusal"


def test_receipt_write_failure_preserves_uncertainty_and_prevents_second_send(case, monkeypatch):
    journal, args, calls, observed = case
    actual = module._atomic_write_text
    failed = []

    def fail_one_receipt_write(path, content):
        if json.loads(content)["stage"] == "transport_returned_reconciliation_required":
            failed.append(True)
            raise OSError("invented receipt publication failure")
        actual(path, content)

    monkeypatch.setattr(module, "_atomic_write_text", fail_one_receipt_write)
    with pytest.raises(OSError):
        journal.dispatch_once(**args)
    saved = journal.receive(CID)
    assert failed and len(calls) == 1
    assert saved["stage"] == "dispatch_boundary_consumed_ack_unknown"
    assert saved["observations"] == [observed]
    with pytest.raises(FileExistsError):
        journal.dispatch_once(**args)
    assert len(calls) == 1


def test_D1_all_new_directory_links_are_synced_before_transport(case, monkeypatch):
    journal, args, calls, _ = case
    journal.directory = journal.directory / "nested" / "orders"
    barriers = []
    original = module._sync_directory

    def sync(path):
        original(path)
        barriers.append(path)

    monkeypatch.setattr(module, "_sync_directory", sync)
    submit = args["submit"]
    expected = [journal.directory, *journal.directory.parents]

    def submit_after_barriers(request):
        assert barriers[: len(expected)] == expected
        assert (journal.directory / f"{CID}.json").exists()
        return submit(request)

    args["submit"] = submit_after_barriers
    journal.dispatch_once(**args)
    assert len(calls) == 1


def test_D1_parent_barrier_failure_stops_and_existing_partial_tree_is_resynced(case, monkeypatch):
    journal, args, calls, _ = case
    journal.directory = journal.directory / "nested" / "orders"
    failed_parent = journal.directory.parent
    original = module._sync_directory
    seen = []

    def fail_parent(path):
        seen.append(path)
        if path == failed_parent:
            raise OSError("invented parent barrier failure")
        original(path)

    monkeypatch.setattr(module, "_sync_directory", fail_parent)
    with pytest.raises(OSError, match="parent barrier"):
        journal.dispatch_once(**args)
    assert not calls and journal.directory.exists()
    assert not (journal.directory / f"{CID}.json").exists()
    seen.clear()

    def sync_existing(path):
        original(path)
        seen.append(path)

    monkeypatch.setattr(module, "_sync_directory", sync_existing)
    # Explicit new fixture invocation after repair, not an internal order retry.
    journal.dispatch_once(**args)
    assert seen[: len(journal.directory.parents) + 1] == [
        journal.directory,
        *journal.directory.parents,
    ]
    assert failed_parent in seen and len(calls) == 1


def test_D1_barrier_latency_does_not_waive_dispatch_expiry(case, monkeypatch):
    journal, args, calls, _ = case
    current = [NOW]
    args["clock"] = lambda: current[0]
    original = module._sync_directory

    def sync_and_delay(path):
        original(path)
        current[0] = NOW + timedelta(seconds=6)

    monkeypatch.setattr(module, "_sync_directory", sync_and_delay)
    with pytest.raises(ValueError, match="dispatch interval"):
        journal.dispatch_once(**args)
    assert not calls
    assert journal.receive(CID)["stage"] == "not_dispatched_guard_refusal"


def test_D1_canonical_absolute_root_is_fixed_before_callbacks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    journal = SourceDispatchJournal(module.Path("owned"))
    assert journal.directory == tmp_path / "owned"
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    module._ensure_durable_directory(journal.directory)
    assert (tmp_path / "owned").is_dir() and not (other / "owned").exists()
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path / "owned", target_is_directory=True)
    with pytest.raises(ValueError, match="canonical nonsymlink"):
        module._ensure_durable_directory(alias / "new")
    assert not (tmp_path / "owned" / "new").exists()
