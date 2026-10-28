"""Finite actual-write guard regressions; synthetic state, no external operations."""

import ast
import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner import current_initialization_runtime as runtime
from open_composer.intraday_runner import source_state_checkpoint as checkpoint
from open_composer.intraday_runner.current_initialization_controls import ACCOUNT, DAY, NAMESPACE
from open_composer.intraday_runner.current_initialization_dispatch import CurrentDispatchJournal
from open_composer.intraday_runner.source_activity_reception import bind
from open_composer.intraday_runner.source_method_bindings import source_module
from open_composer.intraday_runner.source_reservations import SourceReservations

ROOT = Path("/root/codex-test/open-composer")


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("no network in write-budget fixtures")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def test_exact_reconcile_witness_now_refuses_before_activity_write(tmp_path, monkeypatch):
    r = runtime.CurrentInitializationRuntime.__new__(runtime.CurrentInitializationRuntime)
    r.root = tmp_path
    r.clock = lambda: datetime(2026, 10, 19, 14, tzinfo=UTC)
    r.monotonic = lambda: 100
    r.connect = lambda: None
    r.store = SimpleNamespace(load=lambda: {"snapshot": {}})
    checks = []

    def refuse(**kw):
        checks.append(kw)
        raise ValueError("zero room")

    r.entry_guard = refuse
    monkeypatch.setattr(
        runtime, "capture", lambda *a, **k: dict(orders={}, activities=[{"text": "x" * 100000}])
    )
    monkeypatch.setattr(runtime, "restore", lambda *a: (None, {}, {}, {}))
    with pytest.raises(ValueError, match="zero room"):
        r.reconcile(tmp_path / "output")
    assert not (tmp_path / "output").exists()
    assert len(checks) == 1 and checks[0]["extra_write_bytes"] > 200000
    assert checks[0]["write_path"] == str(tmp_path / "output/activities.json")


def test_runtime_all_save_rewrite_and_directory_paths_guarded(tmp_path):
    r = runtime.CurrentInitializationRuntime.__new__(runtime.CurrentInitializationRuntime)
    checks = []

    def refuse(**kw):
        checks.append(kw)
        raise ValueError("zero room")

    r.entry_guard = refuse
    for name in ["initial-decision.json", "activities-receipt.json", "AAPL.exit-signal.json"]:
        with pytest.raises(ValueError):
            r.save_capture(tmp_path / name, {"text": "中" * 10000})
    with pytest.raises(ValueError):
        r.write_text(tmp_path / "journal.json", "x" * 100001)
    with pytest.raises(ValueError):
        r.ensure_directory(tmp_path / "nested/dir")
    assert len(checks) == 5 and list(tmp_path.iterdir()) == []
    assert all(x["local_only"] is True for x in checks)


def state_value():
    state = SourceReservations(source_module(ROOT, "cash").CashState(cash=10000))
    return checkpoint.snapshot(state, {}, {}, evidence={"invented": True})


@pytest.mark.parametrize("boundary", ["lock", "revision", "head"])
def test_checkpoint_each_write_refuses_and_preserves_exact_prefix(tmp_path, boundary):
    checks = []

    def guard(path, size, *, atomic=True):
        checks.append((path.name, size, atomic))
        if (
            (boundary == "lock" and path.name == "checkpoint.lock")
            or (boundary == "revision" and path.name.startswith("revision"))
            or (boundary == "head" and path.name == "head.json")
        ):
            raise ValueError("budget refusal")

    store = checkpoint.SourceStateCheckpoint(
        tmp_path / "state", account_hash=ACCOUNT, sleeve_id="test", write_guard=guard
    )
    value = state_value()
    with pytest.raises(ValueError, match="budget refusal"):
        store.commit(value, expected_head_sha256=None)
    if boundary == "lock":
        assert not store.directory.exists()
    elif boundary == "revision":
        assert not list(store.directory.glob("revision-*"))
    else:
        revision = store._read(store._revision(0))
        assert revision["snapshot"] == value and not (store.directory / "head.json").exists()
        store.write_guard = lambda *a, **k: None
        with pytest.raises(ValueError, match="unpublished"):
            store.load()
        assert store.recover(exact_revision_sha256=checkpoint._hash(revision)) == revision
    assert all(size > 0 for name, size, _ in checks if name != "checkpoint.lock")


def test_checkpoint_default_economics_and_bytes_match_current_production(tmp_path):
    # Same old production class body in a private namespace; no receiver/model.
    tree = ast.parse(
        (ROOT / "open_composer/intraday_runner/source_state_checkpoint.py").read_text()
    )
    old_class = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SourceStateCheckpoint"
    )
    ns = dict(vars(checkpoint))
    exec(compile(ast.Module(body=[old_class], type_ignores=[]), "<old-class>", "exec"), ns)
    old = ns["SourceStateCheckpoint"](tmp_path / "old", account_hash=ACCOUNT, sleeve_id="test")
    checks = []
    new = checkpoint.SourceStateCheckpoint(
        tmp_path / "new",
        account_hash=ACCOUNT,
        sleeve_id="test",
        write_guard=lambda p, n, **kw: checks.append((p.name, n)),
    )
    value = state_value()
    a = old.commit(value, expected_head_sha256=None)
    b = new.commit(value, expected_head_sha256=None)
    assert a == b
    value["evidence"]["next"] = True
    assert old.commit(value, expected_head_sha256=checkpoint._hash(a)) == new.commit(
        value, expected_head_sha256=checkpoint._hash(b)
    )
    for name in ["revision-00000000.json", "revision-00000001.json", "head.json"]:
        assert (old.directory / name).read_bytes() == (new.directory / name).read_bytes()
    assert any(name == "head.json" for name, size in checks)


def journal_arguments(tmp_path):
    cid = f"{NAMESPACE}-{DAY:%m%d}-buy-AAPL"
    reservation = dict(side="buy", symbol="AAPL", quantity=2, filled=0, limit_price=10.0)
    request = dict(
        client_order_id=cid,
        symbol="AAPL",
        side="buy",
        qty=2,
        type="limit",
        time_in_force="day",
        limit_price=10.0,
        execution_day=DAY.isoformat(),
        reference_day="2026-10-19",
        reference_price=10.009,
        reference_valid=True,
        reservation=reservation,
        cleanup=False,
        killed=False,
    )
    signal = tmp_path / "signal.json"
    signal.write_text('{"invented":true}')
    calls = []
    args = dict(
        prepared=request,
        reservation_snapshot=dict(
            pending={cid: reservation}, consumed_ids=[cid], account_hash=ACCOUNT
        ),
        signal_binding=bind(signal),
        execution_day=DAY,
        authorized_at=datetime(2026, 10, 19, tzinfo=UTC),
        expires_at=datetime(2026, 11, 14, tzinfo=UTC),
        clock=lambda: datetime(2026, 10, 20, 13, 40, tzinfo=UTC),
        revalidate=lambda r: None,
        submit=lambda r: calls.append(r) or {"large_reply": "x" * 100000},
    )
    return cid, args, calls


@pytest.mark.parametrize("boundary", ["directory", "marker", "response"])
def test_dispatch_write_refusal_retains_consumption_and_never_retries(tmp_path, boundary):
    cid, args, calls = journal_arguments(tmp_path)
    seen = []

    def guard(path, size, *, atomic=True):
        seen.append((path.name, size, atomic))
        if (
            (boundary == "directory" and path.name == ".dispatch.lock")
            or (boundary == "marker" and not atomic and size > 0)
            or (boundary == "response" and size > 100000)
        ):
            raise ValueError("no space")

    journal = CurrentDispatchJournal(tmp_path / "journal", write_guard=guard)
    with pytest.raises(ValueError, match="no space"):
        journal.dispatch_once(**args)
    if boundary == "directory":
        assert not journal.directory.exists() and not calls
    elif boundary == "marker":
        assert not journal._path(cid).exists() and not calls
    else:
        assert len(calls) == 1
        row = journal.receive(cid)
        assert (
            row["stage"] == "dispatch_boundary_consumed_ack_unknown" and row["observations"] == []
        )
        with pytest.raises(FileExistsError):
            journal.dispatch_once(**args)
        assert len(calls) == 1


def test_cancel_marker_capacity_refusal_keeps_previous_record(tmp_path):
    cid, args, calls = journal_arguments(tmp_path)
    args["submit"] = lambda r: dict(
        **{
            k: r[k]
            for k in [
                "client_order_id",
                "symbol",
                "side",
                "qty",
                "type",
                "time_in_force",
                "limit_price",
            ]
        },
        id="invented",
        status="new",
        filled_qty="0",
    )
    journal = CurrentDispatchJournal(tmp_path / "journal")
    journal.dispatch_once(**args)
    before = journal._path(cid).read_bytes()

    def refuse(path, size, **kw):
        if size > 0:
            raise ValueError("no atomic room")

    journal.write_guard = refuse
    with pytest.raises(ValueError, match="no atomic room"):
        journal.cancel_own_remainder_once(
            cid,
            authorized_at=args["authorized_at"],
            expires_at=args["expires_at"],
            cancel=lambda bid: calls.append(bid),
            revalidate=lambda row: None,
            clock=args["clock"],
        )
    assert not calls and journal._path(cid).read_bytes() == before


def test_runtime_constructor_wires_all_mutating_stores(tmp_path, monkeypatch):
    auth = dict(
        ledger_root=str(tmp_path / "ledger"),
        task_id=runtime.BASE,
        namespace=NAMESPACE,
        partition={},
    )
    monkeypatch.setattr(runtime, "load_authority", lambda *a: auth)
    monkeypatch.setattr(
        runtime, "ValidationAccountPartition", lambda *a, **kw: SimpleNamespace(**kw)
    )
    r = runtime.CurrentInitializationRuntime(tmp_path, {}, entry_guard=lambda **kw: None)
    assert r.store.write_guard == r.guard_write
    assert r.journal.write_guard == r.guard_write
    assert r.partition.write_guard == r.guard_write
    assert not (tmp_path / "ledger").exists()


def test_shared_slot_registry_refuses_before_any_publication(tmp_path):
    from open_composer.intraday_runner.validation_account_partition import (
        BASE,
        ValidationAccountPartition,
        slot,
    )
    from tests.test_current_validation_authority import authority

    _, invented = authority(tmp_path, BASE)
    p = ValidationAccountPartition.__new__(ValidationAccountPartition)
    p.root, p.binding, p.directory, p.held = (
        tmp_path,
        invented["partition"],
        tmp_path / "registry",
        True,
    )
    ledger, namespace = slot(tmp_path, BASE)
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            dict(
                task_id=BASE,
                account_hash=ACCOUNT,
                capital_usd=10000,
                namespace=namespace,
                ledger_root=str(ledger),
                partition=p.binding,
            )
        )
    )
    calls = []

    def guard(path, size, **kw):
        calls.append((str(path), size))
        raise ValueError("registry room refused")

    p.write_guard = guard
    with pytest.raises(ValueError, match="registry room"):
        p.register(BASE, bind(auth))
    assert len(calls) == 1 and calls[0][1] > 0 and not p.directory.exists()


def test_missing_global_lock_is_not_created_by_sleeve(tmp_path):
    r = runtime.CurrentInitializationRuntime.__new__(runtime.CurrentInitializationRuntime)
    r.root, r.directory = tmp_path, tmp_path / "ledger"
    r.entry_guard = lambda **kw: None
    with pytest.raises(FileNotFoundError):
        with r.operation():
            pytest.fail("missing production locks cannot be created")
    assert not (tmp_path / "reports/paper").exists()
