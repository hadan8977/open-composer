"""STATE adapter witnesses use invented data; never invoke scientific producers."""

import sys
from datetime import UTC, datetime
from types import ModuleType

import pytest

from open_composer.intraday_runner import current_initialization_runtime as runtime
from open_composer.intraday_runner import current_state_component as component
from open_composer.intraday_runner.source_activity_reception import bind, save


def result():
    symbols = ["S" + str(i) for i in range(27)]
    return dict(
        task_id=component.STATE,
        policy="BASE_STATE_BUDGET",
        capital_USD=20000,
        reference_day="2026-10-16",
        paper_ready=False,
        targets_are_holdings_or_orders=False,
        symbols=symbols,
        weights=[0.2] * 5 + [0] * 22,
        raw_reference_marks={s: 100 for s in symbols},
        K=5,
        historical_strict_prior_BASE_reference_parity=False,
        consume_before="2026-10-19T13:41:00Z",
        dispatch_window=["2026-10-19T13:40:00Z", "2026-10-19T13:41:00Z"],
        holding_authority_cap="2026-11-14T00:00:00Z",
    )


@pytest.fixture
def received(tmp_path, monkeypatch):
    root = tmp_path / component.FOLDER
    child = root / "BASE_STATE_BUDGET"
    child.mkdir(parents=True)
    (root / "synthesis_consumer.py").write_text("# invented stub never executed\n")
    spec = dict(
        consumer=bind(root / "synthesis_consumer.py"),
        schema=save(root / "consumer-schema.json", {}),
        contract=save(root / "prospective-contract.json", {}),
    )
    spec["manifest"] = save(root / "implementation-manifest.json", dict(files=list(spec.values())))
    forecast = save(child / "output.json", {})
    spec["package"] = save(child / "current-package.json", dict(forecast=forecast))
    spec["final"] = save(child / "final-manifest.json", dict(files=list(spec.values())))
    review = save(
        root / "independent-BASE_STATE_BUDGET-result-review.json",
        dict(
            task_id=component.STATE,
            reviewer=component.REVIEWER,
            verdict="approve_result",
            component_result_accepted=True,
            target=spec["final"],
            package=spec["package"],
            implementation=spec["manifest"],
            forecast=forecast,
        ),
    )
    value = dict(
        result(), review=review, package=spec["package"], final=spec["final"], forecast=forecast
    )
    module = ModuleType("synthesis_consumer")
    module.__file__ = str(root / "synthesis_consumer.py")
    module.receive_current_package = lambda *a, **k: value
    monkeypatch.setitem(sys.modules, "synthesis_consumer", module)
    return (
        tmp_path,
        root,
        dict(task_id=component.STATE, scientific_consumer=spec, scientific_acceptance=review),
        module,
    )


def test_canonical_received_view_is_copied_and_expiry_refuses(received):
    root, folder, auth, module = received
    received = component.receive(root, auth, clock=lambda: datetime(2026, 10, 19, 11, tzinfo=UTC))
    assert received["forecast"]["symbols"] == result()["symbols"]
    assert received["forecast"]["weights"] == result()["weights"]
    with pytest.raises(ValueError):
        component.receive(root, auth, clock=lambda: datetime(2026, 10, 19, 13, 41, tzinfo=UTC))


def test_changed_binding_after_callback_refuses(received):
    root, folder, auth, module = received
    original = module.receive_current_package

    def changed(*a, **k):
        value = original(*a, **k)
        (folder / "consumer-schema.json").write_text("{}")
        return value

    module.receive_current_package = changed
    with pytest.raises(ValueError):
        component.receive(root, auth, clock=lambda: datetime(2026, 10, 19, 11, tzinfo=UTC))


def test_runtime_selects_state_and_never_hides_missing_input(monkeypatch, tmp_path):
    r = runtime.CurrentInitializationRuntime.__new__(runtime.CurrentInitializationRuntime)
    r.task = component.STATE
    r.root = tmp_path
    r.auth = {"task_id": component.STATE}
    r.read_guard = lambda: None
    r.clock = lambda: datetime(2026, 10, 19, 11, tzinfo=UTC)
    marker = {"exact_new_policy": True}
    from open_composer.intraday_runner import current_initialization_episode as episode

    def receive(root, auth, *, clock):
        assert root == tmp_path and auth == r.auth and clock is r.clock
        return marker

    monkeypatch.setattr(episode, "receive", receive)
    assert r.receive_science() is marker

    def missing(*a, **k):
        raise ValueError("missing actual input")

    monkeypatch.setattr(episode, "receive", missing)
    with pytest.raises(ValueError):
        r.receive_science()


@pytest.mark.parametrize("task", ["CROSS-ASSET-LSTM-PAPER-VALIDATION-20261019", component.STATE])
def test_actual_runtime_constructor_receives_selected_namespace(tmp_path, task, monkeypatch):
    from open_composer.intraday_runner.current_initialization_dispatch import CurrentDispatchJournal
    from open_composer.intraday_runner.validation_account_partition import slot
    from tests.test_current_validation_authority import authority

    put, auth = authority(tmp_path, task, six=True, current_day=True, monkeypatch=monkeypatch)
    r = runtime.CurrentInitializationRuntime(
        tmp_path,
        put("auth", auth),
        entry_guard=lambda **kw: None,
        clock=lambda: datetime(2026, 10, 19, 11, tzinfo=UTC),
    )
    ledger, namespace = slot(tmp_path, task)
    assert r.journal.namespace == namespace and r.cap == 20000
    assert not ledger.exists() and r.gateway is None
    own = namespace + "-1019-buy-SPY"
    assert r.journal._path(own).parent == ledger / "dispatch"
    with pytest.raises(ValueError):
        r.journal._path("basecur-20261019-fa6147de-1019-buy-SPY")
    with pytest.raises(ValueError):
        CurrentDispatchJournal(ledger / "dispatch", namespace="unknown")
