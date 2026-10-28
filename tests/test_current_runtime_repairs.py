"""Finite offline witnesses against frozen WT8441; all external I/O denied.

Affected regression fixtures; no live account/source/native admission.
"""

import copy
import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner import current_initialization_runtime as runtime
from open_composer.intraday_runner.current_initialization_controls import (
    ACCOUNT,
    DAY,
    NAMESPACE,
)
from open_composer.intraday_runner.current_initialization_dispatch import CurrentBoundedGateway
from open_composer.intraday_runner.source_dispatch_journal import _hash
from open_composer.intraday_runner.source_method_bindings import source_module
from open_composer.intraday_runner.source_reservations import SourceReservations
from open_composer.intraday_runner.source_state_checkpoint import (
    SourceStateCheckpoint,
    restore,
    snapshot,
)

ROOT = Path("/root/codex-test/open-composer")
P = ROOT / "reports/research/program/owner-profit-delivery-plan-20261017"
CAPACITY = ROOT / "reports/ops/disk-audit-20261015/capacity-BASE-H5-22MiB-admission-20261019.json"
BUY = f"{NAMESPACE}-1020-buy-AAPL"


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("network prohibited in finite reviewer fixtures")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def bound(path):
    import hashlib

    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def owned_observation(now, current, *, oldest_age=3):
    return dict(
        started_at=(now - timedelta(seconds=max(4, oldest_age + 1))).isoformat(),
        oldest_response_at=(now - timedelta(seconds=oldest_age)).isoformat(),
        last_response_at=(now - timedelta(seconds=2)).isoformat(),
        completed_at=(now - timedelta(seconds=1)).isoformat(),
        started_monotonic=100 - max(4, oldest_age + 1),
        completed_monotonic=99,
        account_hash=ACCOUNT,
        checkpoint_hash=_hash(current),
        currency="USD",
        account_status="ACTIVE",
        trading_blocked=False,
        account_blocked=False,
        trade_suspended=False,
        positions_complete=True,
        orders_complete=True,
        actions_complete=True,
        units_reconciled=True,
        activities_complete=False,
        cash_reconciled=False,
        fees_complete=False,
        holdings=[
            dict(symbol="AAPL", quantity=5, owned=True, current_price="100", market_value="500")
        ],
        broker_clock=dict(is_open=True, timestamp=(now - timedelta(seconds=3)).isoformat()),
        broker_clock_received_at=(now - timedelta(seconds=2)).isoformat(),
        assets=dict(AAPL=dict(status="active", tradable=True)),
    )


def make_runtime(tmp_path, monkeypatch, now):
    state = SourceReservations(source_module(ROOT, "cash").CashState(cash=10000))
    state.reserve_buy(BUY, "AAPL", 10, 100, 1, DAY.isoformat(), "2026-10-20")
    state.confirmed_fill(BUY, "invented-fill", 5, 100, DAY.isoformat())
    evidence = dict(
        risk=dict(
            initial_capital="10000",
            high_water="10000",
            day=DAY.isoformat(),
            day_open_nav="10000",
            halted=True,
            killed=True,
        ),
        allocated_capital=10000,
        account_initial_cash=1000000,
        dispatch_intents={BUY: dict(attempted=True)},
    )
    store = SourceStateCheckpoint(tmp_path / "state", account_hash=ACCOUNT, sleeve_id="invented")
    current = store.commit(
        snapshot(
            state,
            {"invented-fill": {"client_order_id": BUY, "account_hash": ACCOUNT}},
            {},
            evidence=evidence,
        ),
        expected_head_sha256=None,
    )
    r = runtime.CurrentInitializationRuntime.__new__(runtime.CurrentInitializationRuntime)
    r.root, r.directory, r.store = ROOT, tmp_path, store
    r.namespace = NAMESPACE
    r.auth = dict(authorized_at="2026-10-19T00:00:00Z", expires_at="2026-11-14T00:00:00Z")
    r.clock, r.monotonic = lambda: now, lambda: 100
    r.current_phase = "exit"
    r.entry_guard = lambda **kwargs: None
    r.read_guard = lambda: None
    r.connect = lambda: None
    r.observation = owned_observation(now, current)
    monkeypatch.setattr(runtime, "_require_kill_switch_clear", lambda root: None)
    return r, current


def fake_gateway(r):
    g = CurrentBoundedGateway.__new__(CurrentBoundedGateway)
    g.guard, g.clock = r.order_guard, r.clock
    g.authorized_at, g.expires_at = r.auth["authorized_at"], r.auth["expires_at"]
    g.journal = SimpleNamespace(namespace=NAMESPACE)
    g.cancel_window = r.cancel_window
    return g


@pytest.mark.parametrize("defect", ["oldest", "capture", "paired", "head", "future", "valid"])
def test_final_delete_full_temporal_guard(tmp_path, monkeypatch, defect):
    now = datetime(2026, 10, 20, 14, 1, tzinfo=UTC)
    r, current = make_runtime(tmp_path, monkeypatch, now)
    r.current_phase = "cancel"
    if defect == "oldest":
        r.observation.update(
            started_at=(now - timedelta(seconds=17)).isoformat(),
            oldest_response_at=(now - timedelta(seconds=16)).isoformat(),
            last_response_at=(now - timedelta(seconds=7)).isoformat(),
            completed_at=(now - timedelta(seconds=6)).isoformat(),
            started_monotonic=83,
            completed_monotonic=94,
        )
    elif defect == "capture":
        r.observation.update(
            started_at=(now - timedelta(seconds=17)).isoformat(), started_monotonic=83
        )
    elif defect == "paired":
        r.observation["completed_monotonic"] = 98
    elif defect == "head":
        r.observation["checkpoint_hash"] = "wrong"
    elif defect == "future":
        r.observation["completed_at"] = (now + timedelta(seconds=1)).isoformat()
    request = dict(client_order_id=BUY, symbol="AAPL", side="buy", cleanup=False)
    if defect == "valid":
        # Fees/NAV remain incomplete: owned cancellation does not release them.
        assert fake_gateway(r)._check_guard(request, cancellation=True) is None
    else:
        with pytest.raises(ValueError):
            fake_gateway(r)._check_guard(request, cancellation=True)


@pytest.mark.parametrize(
    "phase,killed,when,allowed",
    [
        ("exit", True, "2026-10-20T13:45:00+00:00", True),
        ("exit", False, "2026-10-20T13:45:00+00:00", False),
        ("cancel", True, "2026-10-20T13:45:00+00:00", False),
        ("exit", False, "2026-11-13T20:46:00+00:00", True),
        ("exit", True, "2026-10-20T19:59:00+00:00", False),
    ],
)
def test_cancel_trigger_not_original_request_mutation(
    tmp_path, monkeypatch, phase, killed, when, allowed
):
    now = datetime.fromisoformat(when)
    r, current = make_runtime(tmp_path, monkeypatch, now)
    state, fills, fees, evidence = restore(ROOT, current["snapshot"])
    evidence["risk"]["killed"] = killed
    current = r.store.commit(
        snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(current)
    )
    r.observation = owned_observation(now, current)
    r.current_phase = phase
    request = dict(client_order_id=BUY, symbol="AAPL", side="buy", cleanup=False)
    before = copy.deepcopy(request)
    if allowed:
        fake_gateway(r)._check_guard(request, cancellation=True)
    else:
        with pytest.raises(ValueError):
            fake_gateway(r)._check_guard(request, cancellation=True)
    assert request == before


@pytest.mark.parametrize("terminal,racing_fill", [(False, False), (True, False), (True, True)])
def test_kill_cancels_then_reconciles_before_any_exit(tmp_path, monkeypatch, terminal, racing_fill):
    from open_composer.intraday_runner.source_terminal_holds import retain_terminal_liability

    now = datetime(2026, 10, 20, 13, 45, tzinfo=UTC)
    r, initial = make_runtime(tmp_path, monkeypatch, now)
    request = dict(
        client_order_id=BUY,
        symbol="AAPL",
        side="buy",
        qty=10,
        type="limit",
        time_in_force="day",
        limit_price=100,
        cleanup=False,
    )
    order = dict(**request, id="invented-bid", filled_qty="5", status="partially_filled")
    journal = dict(request=request, observations=[copy.deepcopy(order)])
    events = []

    def reconcile(path):
        events.append(path.name)
        if path.name == "after-cancel" and terminal:
            current = r.store.load()
            state, fills, fees, evidence = restore(ROOT, current["snapshot"])
            if racing_fill:
                state.confirmed_fill(BUY, "racing-fill", 1, 100, DAY.isoformat())
                fills["racing-fill"] = dict(client_order_id=BUY, account_hash=ACCOUNT)
                order["filled_qty"] = "6"
            order["status"] = "canceled"
            journal["observations"].append(copy.deepcopy(order))
            state, evidence = retain_terminal_liability(
                state,
                evidence,
                journal=journal,
                observed_order=order,
                capture_binding={"invented": True},
            )
            r.store.commit(
                snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(current)
            )

    r.reconcile = reconcile

    def capture(*args, **kwargs):
        obs = owned_observation(now, r.store.load())
        quantity = 6 if terminal and racing_fill else 5
        obs["holdings"][0].update(quantity=quantity, market_value=str(quantity * 100))
        return dict(observation=obs, orders={BUY: copy.deepcopy(order)})

    monkeypatch.setattr(runtime, "capture", capture)

    def cancel(cid, **kwargs):
        kwargs["revalidate"](journal)
        events.append("cancel")
        journal["cancel_attempt"] = {"state": "request_returned_not_cancel_confirmation"}
        return {"cancel_requested": True, "funds_releasable": False}

    def dispatch(req, **kwargs):
        events.append("sell")
        kwargs["revalidate"](req)
        assert events.index("after-cancel") < events.index("sell")
        return {"request": req, "synthetic_only": True}

    r.journal = SimpleNamespace(
        directory=tmp_path / "journal",
        receive=lambda cid: journal,
        cancel_own_remainder_once=cancel,
        dispatch_once=dispatch,
    )
    r.gateway = SimpleNamespace(cancel=lambda *a: None, submit=lambda *a: None)
    result = r.closeout(tmp_path / "exit")
    assert events[:3] == ["before-cancel", "cancel", "after-cancel"]
    state, _, _, evidence = restore(ROOT, r.store.load()["snapshot"])
    if terminal:
        assert result["orders"][0]["request"]["qty"] == (6 if racing_fill else 5)
        hold = evidence["terminal_liability_holds"]["liability-" + BUY]
        assert hold["cash_released"] == 0 and not hold["fees_reconciled"]
        assert "liability-" + BUY in state.pending
    else:
        assert "sell" not in events and result["orders"] == []
        assert state.pending[BUY] == initial["snapshot"]["pending"][BUY]
    assert result["flat_certified"] is False


def test_active22_exact_receipt_and_stale14_refused(tmp_path):
    from open_composer.intraday_runner.current_initialization_storage import capacity

    receipt = json.loads(CAPACITY.read_text())
    proposal = json.loads((ROOT / receipt["proposal"]["path"]).read_text())
    owned = tmp_path / "owned"
    owned.mkdir()
    proposal["current_root_allocation"] = [{"root": str(owned)}]
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(proposal))
    receipt["proposal"] = bound(proposal_path)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    job = dict(
        task_id="BASE-CURRENT-INITIALIZATION-20261019",
        whole_route_bytes=23068672,
        protected_normal_bytes=10918819017,
        terminal_bytes=65536,
        capacity_receipt=bound(receipt_path),
        owned_roots=[r["root"] for r in proposal["current_root_allocation"]],
    )
    assert capacity(ROOT, job)["remaining_current"] >= 0
    job["whole_route_bytes"] = 14680064
    with pytest.raises(ValueError, match="storage scope"):
        capacity(ROOT, job)


def prepared(tmp_path, monkeypatch):
    from open_composer.intraday_runner import current_initialization_storage as storage

    monkeypatch.setattr(
        storage, "capacity", lambda *a: dict(remaining_current=sum(storage.SLOTS.values()) + 65536)
    )
    job = dict(owned_roots=[str(tmp_path)], invocation_id="invented")
    manager = storage.NativeStorage(tmp_path, job)
    binding = {"invented": True}
    output = tmp_path / "ledger" / "invented"
    directory = manager.prepare(output, binding)
    return storage, manager, output, directory, binding


def test_zero_remaining_no_launcher_or_metadata(tmp_path, monkeypatch):
    from open_composer.intraday_runner import current_initialization_storage as storage

    monkeypatch.setattr(storage, "capacity", lambda *a: dict(remaining_current=0))
    manager = storage.NativeStorage(
        tmp_path, dict(owned_roots=[str(tmp_path)], invocation_id="one")
    )
    with pytest.raises(ValueError, match="remaining"):
        manager.prepare(tmp_path / "out", {})
    with pytest.raises(ValueError, match="remaining"):
        manager.save(tmp_path / "failure.json", {"failed": True})
    assert list(tmp_path.iterdir()) == []


def test_preallocated_failure_slot_without_new_allocation(tmp_path, monkeypatch):
    storage, manager, output, directory, binding = prepared(tmp_path, monkeypatch)
    before = {
        p.name: (p.stat().st_blocks, p.stat().st_ino, p.stat().st_size) for p in directory.iterdir()
    }
    monkeypatch.setattr(storage, "capacity", lambda *a: dict(remaining_current=0))
    with pytest.raises(ValueError):
        manager.save(output / "failure.json", {"failure": "capacity"})
    storage.fixed_record(
        directory, "entry-emergency.json", {"failure": "capacity", "outcome": "UNKNOWN"}
    )
    after = {
        p.name: (p.stat().st_blocks, p.stat().st_ino, p.stat().st_size) for p in directory.iterdir()
    }
    assert before == after
    assert json.loads((directory / "entry-emergency.json").read_text())["outcome"] == "UNKNOWN"
    with pytest.raises(FileExistsError):
        monkeypatch.setattr(
            storage,
            "capacity",
            lambda *a: dict(remaining_current=sum(storage.SLOTS.values()) + 65536),
        )
        manager.prepare(output, binding)


def test_log_overflow_kills_and_reaps_owned_child(tmp_path, monkeypatch):
    import sys

    from open_composer.intraday_runner.current_initialization_launcher import bounded_process

    storage, manager, output, directory, binding = prepared(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="overflow"):
        bounded_process(
            [sys.executable, "-c", "import os,time; os.write(1,b'x'*70000); time.sleep(60)"],
            directory,
            "scope.log",
            timeout_seconds=5,
        )
    result = json.loads((directory / "scope.log.resource.json").read_text())
    assert result["reaped"] and result["exit_code"] == -9
    assert result["failure_type"] == "ValueError" and result["log_bytes"] <= 65536
    assert (directory / "scope.log").stat().st_size == 65536


def test_child_timeout_reaped_and_recorded(tmp_path, monkeypatch):
    import sys

    from open_composer.intraday_runner.current_initialization_launcher import bounded_process

    storage, manager, output, directory, binding = prepared(tmp_path, monkeypatch)
    with pytest.raises(TimeoutError):
        bounded_process(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            directory,
            "scope.log",
            timeout_seconds=0.1,
        )
    result = json.loads((directory / "scope.log.resource.json").read_text())
    assert result["reaped"] and result["exit_code"] == -9


def test_identity_publication_failure_prevents_entry_and_reaps(tmp_path, monkeypatch):
    import sys

    from open_composer.intraday_runner.current_initialization_launcher import bounded_process

    storage, manager, output, directory, binding = prepared(tmp_path, monkeypatch)

    def refuse(process):
        raise ValueError("identity publication refused")

    with pytest.raises(ValueError, match="publication"):
        bounded_process(
            [sys.executable, "-c", "import sys; sys.stdin.buffer.readline(); print('unsafe')"],
            directory,
            "run.log",
            timeout_seconds=2,
            before_run=refuse,
        )
    result = json.loads((directory / "run.log.resource.json").read_text())
    assert result["reaped"] and result["log_bytes"] == 0


def test_wrong_reused_worker_identity_never_signals(tmp_path, monkeypatch):
    from open_composer.intraday_runner import current_initialization_launcher as launcher

    storage, manager, output, directory, binding = prepared(tmp_path, monkeypatch)
    identity = dict(pid=1234, start="10", cgroup="invented", pgid=1234)
    storage.fixed_record(directory, "worker.json", dict(job=binding, entry=identity, worker=None))
    monkeypatch.setattr(launcher, "process_identity", lambda pid: {**identity, "start": "11"})
    signals = []
    monkeypatch.setattr(launcher.os, "killpg", lambda *a: signals.append(a))
    with pytest.raises(ValueError, match="changed"):
        launcher.stop_recorded_worker(directory, binding)
    assert not signals


def test_fixed_slot_refuses_directory_alias(tmp_path, monkeypatch):
    storage, manager, output, directory, binding = prepared(tmp_path, monkeypatch)
    alias = tmp_path / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    with pytest.raises(ValueError, match="aliased"):
        storage.fixed_record(alias, "completion.json", {"success": False})


def test_scope_orphan_is_adopted_signalled_by_identity_and_reaped(tmp_path, monkeypatch):
    import subprocess
    import sys

    storage, manager, output, directory, binding = prepared(tmp_path, monkeypatch)
    code = r"""
import json,os,sys,time
from pathlib import Path
from open_composer.intraday_runner.current_initialization_launcher import (
    enable_subreaper, process_identity, stop_recorded_worker, reap_recorded_children)
from open_composer.intraday_runner.current_initialization_storage import fixed_record
enable_subreaper()
r,w=os.pipe()
pid=os.fork()
if pid==0:
    os.close(r)
    child=os.fork()
    if child==0:
        os.setsid()
        os.write(w,json.dumps(process_identity(os.getpid())).encode()+b'\n')
        os.close(w)
        time.sleep(60)
        os._exit(5)
    os.close(w)
    os._exit(0)
os.close(w)
with os.fdopen(r) as f: identity=json.loads(f.readline())
os.waitpid(pid,0)
directory=Path(sys.argv[1]); binding={'invented':True}
fixed_record(directory,'worker.json',dict(job=binding,entry=identity,worker=None))
stop_recorded_worker(directory,binding)
reap_recorded_children(directory,binding)
assert not Path('/proc/'+str(identity['pid'])).exists()
# Lifecycle assertions are complete; avoid unrelated interpreter finalizers.
print('owned orphan reaped',flush=True)
os._exit(0)
"""
    # Include interpreter imports and durable slot barriers in the harness
    # allowance; ownership, signalling and actual OS reap remain asserted below.
    result = subprocess.run(
        [sys.executable, "-c", code, str(directory)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "owned orphan reaped"
