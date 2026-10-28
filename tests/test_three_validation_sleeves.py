"""Prospective partition and temporal-consumer controls; invented accounts only."""

import copy
import json
import socket
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

from open_composer.intraday_runner import current_initialization_runtime as runtime
from open_composer.intraday_runner import current_lstm_component as component
from open_composer.intraday_runner.current_initialization_controls import risk_transition
from open_composer.intraday_runner.source_activity_reception import bind, save
from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint
from open_composer.intraday_runner.validation_account_partition import (
    ACCOUNT,
    BASE,
    H5,
    LSTM,
    allocation_map,
    slot,
)
from open_composer.intraday_runner.validation_account_partition import (
    ValidationAccountPartition as Partition,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("no source/broker network")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def make_partition(root):
    owner = save(root / "owner.json", {"invented": True})
    account = save(root / "account-scope.json", {"invented": True})
    prior = save(root / "prior.json", {"invented": True})
    return save(
        root / "partition.json",
        dict(
            selected_task=LSTM,
            selected_tasks=[BASE, H5, LSTM],
            allocation_by_task_USD={BASE: 10000, H5: 6000, LSTM: 4000},
            owner_instruction=owner,
            account_binding=account,
            prior_partition=prior,
            BASE_partition_continuation={"explicitly_authorized_affected_extension": True},
            capital=dict(
                BASE_USD=10000,
                H5_swing_USD=6000,
                LSTM_USD=4000,
                combined_max_USD=20000,
                gross_max=1,
                long_cash_only=True,
                same_verified_isolated_account=True,
                no_inter_sleeve_transfer_or_borrowed_idleallocation=True,
            ),
        ),
    )


def snapshot(cap):
    return dict(
        cashbook=dict(cash=cap, sales=[], purchases=[], dividends=[], lots={}, next_id=0),
        pending={},
        consumed_ids=[],
        applied_fill_ids=[],
        fills={},
        fees={},
        evidence=dict(allocated_capital=str(cap), account_initial_cash="1000000"),
    )


def test_actual_registry_capital_and_complete_checkpoint_invariants(tmp_path):
    partition = make_partition(tmp_path)
    p = Partition(tmp_path, partition)
    caps = allocation_map(tmp_path, partition)
    with p.locked():
        for task, cap in caps.items():
            ledger, namespace = slot(tmp_path, task)
            auth = dict(
                task_id=task,
                account_hash=ACCOUNT,
                capital_usd=int(cap),
                namespace=namespace,
                ledger_root=str(ledger),
                partition=partition,
            )
            binding = save(tmp_path / (task + ".json"), auth)
            p.register(task, binding)
            SourceStateCheckpoint(
                ledger / "checkpoints", account_hash=ACCOUNT, sleeve_id=task
            ).commit(snapshot(float(cap)), expected_head_sha256=None)
        books = p.books()
        assert Partition.totals(books)["allocated"] == 20000
        assert [books[t]["snapshot"]["cashbook"]["cash"] for t in (BASE, H5, LSTM)] == [
            10000,
            6000,
            4000,
        ]
        changed = dict(auth, capital_usd=10000)
        with pytest.raises(ValueError):
            p.register(LSTM, save(tmp_path / "expanded.json", changed))
        h5 = slot(tmp_path, H5)[0]
        store = SourceStateCheckpoint(h5 / "checkpoints", account_hash=ACCOUNT, sleeve_id=H5)
        before = store.load()
        from open_composer.intraday_runner.source_dispatch_journal import _hash

        bad = copy.deepcopy(before["snapshot"])
        bad["evidence"]["allocated_capital"] = "10000"
        store.commit(bad, expected_head_sha256=_hash(before))
        with pytest.raises(ValueError, match="reset"):
            p.books()


def test_three_books_cannot_borrow_aggregate_or_duplicate_ids():
    books = {
        task: dict(snapshot=snapshot(cap), namespace=task, revision=task)
        for task, cap in [(BASE, 10000), (H5, 6000), (LSTM, 4000)]
    }
    assert Partition.totals(books)["allocated"] == 20000
    books[H5]["snapshot"]["evidence"]["allocated_capital"] = "10000"
    with pytest.raises(ValueError, match="aggregate"):
        Partition.totals(books)
    books[H5]["snapshot"]["evidence"]["allocated_capital"] = "6000"
    books[BASE]["snapshot"]["consumed_ids"] = ["same"]
    books[LSTM]["snapshot"]["consumed_ids"] = ["same"]
    with pytest.raises(ValueError, match="duplicate"):
        Partition.totals(books)


@pytest.mark.parametrize("cap", [6000, 4000])
def test_risk_uses_own_opening_and_high_water_not_broker_equity(cap):
    prior = dict(
        initial_capital=str(cap),
        high_water=str(cap),
        day="2026-10-19",
        day_open_nav=str(cap),
        halted=False,
        killed=False,
    )
    now = datetime(2026, 10, 19, 13, 40, tzinfo=UTC)
    after = risk_transition(
        prior, dict(verified_nav=str(Decimal(cap) * Decimal(".95"))), now=now, capital=cap
    )
    assert after["halted"] and not after["killed"]
    prior["high_water"] = str(Decimal(cap) / Decimal(".75"))
    after = risk_transition(prior, dict(verified_nav=str(cap)), now=now, capital=cap)
    assert after["killed"] and after["halted"]
    prior["initial_capital"] = "10000"
    with pytest.raises(ValueError):
        risk_transition(prior, dict(verified_nav=str(cap)), now=now, capital=cap)


def invented_result():
    return dict(
        task_id=LSTM,
        capital_USD=4000,
        combined_cap_USD=20000,
        paper_ready=False,
        reference_day="2026-10-16",
        symbols=component.SYMBOLS.copy(),
        weights=[0.1] * 10,
        target_cash_weight=0,
        raw_reference_marks={s: 100 for s in component.SYMBOLS},
        consume_before="2026-10-19T13:41:00Z",
        dispatch_window=["2026-10-19T13:40:00Z", "2026-10-19T13:41:00Z"],
        holding_authority_cap="2026-11-14T00:00:00Z",
    )


def test_ten_continuous_targets_reach_existing_whole_quantity_path(tmp_path):
    r = runtime.CurrentInitializationRuntime.__new__(runtime.CurrentInitializationRuntime)
    r.root = Path("/root/codex-test/open-composer")
    r.task = LSTM
    r.auth = dict(
        capital_usd=4000, authorized_at="2026-10-19T00:00:00Z", expires_at="2026-11-14T00:00:00Z"
    )
    r.clock = lambda: datetime(2026, 10, 19, 9, tzinfo=UTC)
    r.directory = tmp_path
    original = invented_result()
    r.receive_science = lambda: component.normalize_received(original)
    r.initialize = lambda package: None

    def observed(directory, **kwargs):
        directory.mkdir(parents=True)
        save(directory / "capture.json", {"invented": True})
        return dict(positions=[], orders={}, activities=[])

    r.observe = observed
    r.save_capture = lambda path, value: save(path, value)
    result = r.decide(tmp_path / "decision")
    rows = json.loads((tmp_path / "initial-decision.json").read_text())["requests"]
    assert len(rows) == 10 and [x["symbol"] for x in rows] == component.SYMBOLS
    assert sum(x["max_quantity"] * float(x["limit_price"]) for x in rows) <= 4000
    assert all(type(x["max_quantity"]) is int and x["weight"] == 0.1 for x in rows)
    assert result["broker_writes"] == 0 and original["weights"] == [0.1] * 10


@pytest.mark.parametrize(
    "field,value",
    [
        ("capital_USD", 10000),
        ("weights", [0.21] * 10),
        ("weights", [float("nan")] * 10),
        ("symbols", list(reversed(component.SYMBOLS))),
        ("paper_ready", True),
    ],
)
def test_normalized_temporal_scope_refuses_changes(field, value):
    r = invented_result()
    r[field] = value
    with pytest.raises(ValueError):
        component.normalize_received(r)


@pytest.fixture
def consumer(tmp_path, monkeypatch):
    folder = tmp_path / component.FOLDER
    folder.mkdir(parents=True)

    def write(name, value):
        return save(folder / name, value)

    (folder / "lstm_consumer.py").write_text("# invented consumer, never executed\n")
    spec = dict(
        consumer=bind(folder / "lstm_consumer.py"),
        schema=write("consumer-schema.json", {}),
        contract=write("prospective-contract.json", {}),
        policy_interface=write("policy-interface.json", {}),
    )
    spec["manifest"] = write("implementation-manifest.json", dict(files=list(spec.values())))
    forecast = write("invented-forecast.json", {"invented": True})
    spec["package"] = write("current-package.json", dict(forecast=forecast))
    spec["final"] = write("final-manifest.json", dict(files=list(spec.values())))
    review = write(
        "independent-result-review.json",
        dict(
            task_id=LSTM,
            reviewer=component.REVIEWER,
            verdict="approve_result",
            component_result_accepted=True,
            target=spec["final"],
            package=spec["package"],
            implementation=spec["manifest"],
            forecast=forecast,
        ),
    )
    result = dict(
        invented_result(),
        independent_result_review=review,
        implementation=spec["manifest"],
        forecast=forecast,
    )
    module = ModuleType("lstm_consumer")
    module.__file__ = str(folder / "lstm_consumer.py")
    module.receive_current_package = lambda *a, **kw: result
    monkeypatch.setitem(sys.modules, "lstm_consumer", module)
    return (
        tmp_path,
        folder,
        dict(task_id=LSTM, scientific_consumer=spec, scientific_acceptance=review),
        module,
    )


def test_exact_readonly_consumer_and_drift_refusal(consumer):
    root, folder, auth, module = consumer

    def clock():
        return datetime(2026, 10, 19, 9, tzinfo=UTC)

    value = component.receive(root, auth, clock=clock)
    assert value["forecast"]["weights"] == [0.1] * 10
    original = module.receive_current_package

    def changed(*a, **kw):
        value = original(*a, **kw)
        (folder / "consumer-schema.json").write_text("{}")
        return value

    module.receive_current_package = changed
    with pytest.raises(ValueError):
        component.receive(root, auth, clock=clock)


@pytest.mark.parametrize("task,cap", [(H5, 6000), (LSTM, 4000)])
def test_initial_virtual_cash_is_scoped_and_recovery_never_resets(tmp_path, monkeypatch, task, cap):
    part = make_partition(tmp_path)
    p = Partition(tmp_path, part)
    ledger, namespace = slot(tmp_path, task)
    authority = dict(
        task_id=task,
        capital_usd=cap,
        partition=part,
        ledger_root=str(ledger),
        namespace=namespace,
        account_hash=ACCOUNT,
        initial_account_scope=save(
            tmp_path / "dated-account.json",
            dict(account_hash=ACCOUNT, broker_reported_cash_equity_nonmarginable_USD=1000000),
        ),
    )
    r = runtime.CurrentInitializationRuntime.__new__(runtime.CurrentInitializationRuntime)
    r.root = tmp_path
    r.auth = authority
    r.task = task
    r.directory = ledger
    r.partition = p
    r.authority = save(tmp_path / "authority.json", authority)
    r.read_guard = lambda: None
    r.store = SourceStateCheckpoint(ledger / "checkpoints", account_hash=ACCOUNT, sleeve_id=task)
    original = runtime.source_module
    monkeypatch.setattr(
        runtime,
        "source_module",
        lambda root, name: original(Path("/root/codex-test/open-composer"), name),
    )
    with p.locked():
        r.initialize({"invented_science": True})
        before = r.store.load()
        assert before["snapshot"]["cashbook"]["cash"] == cap
        assert before["snapshot"]["evidence"]["risk"]["initial_capital"] == str(cap)
        r.initialize({"invented_science": True})
        assert r.store.load() == before
        with pytest.raises(ValueError, match="package changed"):
            r.initialize({"different_science": True})
        assert r.store.load() == before
