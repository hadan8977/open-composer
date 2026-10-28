"""Affected H5 adapter fixtures, no scientific producer or network operation."""

import ast
import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner import current_h5_component as h5
from open_composer.intraday_runner import current_initialization_entry as entry
from open_composer.intraday_runner import current_initialization_runtime as runtime
from open_composer.intraday_runner.source_activity_reception import bind, save


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("no provider or account in adapter fixtures")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def invented():
    symbols = ["EG", "CTVA", "AFL", "DXC", "SNA", "IVZ"] + [f"X{i}" for i in range(25)]
    return dict(
        task_id=h5.TASK,
        capital_USD=10000,
        combined_cap_USD=20000,
        reference_day="2026-10-16",
        operating_authority=False,
        targets_are_holdings_or_orders=False,
        symbols=symbols,
        weights=[0, 0.2, 0.2, 0.2, 0.2, 0.2] + [0] * 25,
        K=5,
        raw_reference_marks={s: 20 for s in symbols},
        reason="invented signed STOCK",
        stock_scores=[-0.5] * 32,
        ranking=[3, 6, 1, 9, 2],
        selected=[3, 6, 1, 9, 2],
        consume_before="2026-10-19T13:41:00Z",
    )


def test_normalization_preserves_order_signed_scores_and_exact_weights():
    received = invented()
    result = h5.normalize_received(received)
    assert result["forecast"]["symbols"] == received["symbols"]
    assert result["forecast"]["weights"] == received["weights"]
    assert result["received_scientific_component"] == received
    assert result["received_scientific_component"]["stock_scores"][0] < 0
    assert result["positive_STOCK_filter_or_K_recalculation"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("capital_USD", 20000),
        ("K", 4),
        ("operating_authority", True),
        ("reference_day", "2026-10-15"),
        ("weights", [0.21] * 31),
    ],
)
def test_unmatched_scientific_scope_refuses(field, value):
    received = invented()
    received[field] = value
    with pytest.raises(ValueError):
        h5.normalize_received(received)


@pytest.fixture
def reception(tmp_path, monkeypatch):
    folder = tmp_path / h5.FOLDER
    folder.mkdir(parents=True)
    bindings = {}
    for key, name in dict(
        package="current-package.json",
        schema="consumer-schema.json",
        consumer="h5_consumer_stdlib.py",
    ).items():
        bindings[key] = save(folder / name, {"invented": key})
    bindings["manifest"] = save(folder / "implementation-manifest.json", {"files": []})
    bindings["final"] = save(
        folder / "final-manifest.json",
        {"files": [bindings[k] for k in ("package", "manifest", "schema")]},
    )
    bindings["repair"] = save(
        folder / "consumer-repair-manifest.json",
        {
            "sealed_final": bindings["final"],
            "sealed_package": bindings["package"],
            "schema": bindings["schema"],
            "files": [bindings["consumer"]],
        },
    )
    receipt = save(
        folder / "independent-result-review.json",
        {
            "task_id": h5.TASK,
            "reviewer": h5.REVIEWER,
            "verdict": "approve_result",
            "component_result_accepted": True,
            "target": bindings["final"],
            "consumer_repair_accepted": True,
            "consumer_repair": bindings["repair"],
        },
    )
    result = dict(invented(), review=receipt, final=bindings["final"])
    calls = []

    def receive(path, *, for_execution):
        calls.append((path, for_execution))
        return result

    module = SimpleNamespace(
        __file__=str(folder / "h5_consumer_stdlib.py"), receive_current_package=receive
    )

    def importer(name):
        assert name == "h5_consumer_stdlib"
        return module

    monkeypatch.setattr(h5.importlib, "import_module", importer)
    authority = dict(task_id=h5.TASK, scientific_consumer=bindings, scientific_acceptance=receipt)
    return tmp_path, authority, calls, module, folder


def test_exact_repaired_entry_only(reception):
    root, authority, calls, _, _ = reception
    result = h5.receive(root, authority, clock=lambda: datetime(2026, 10, 19, 6, tzinfo=UTC))
    assert result["forecast"]["weights"] == invented()["weights"]
    assert calls == [(authority["scientific_consumer"]["package"]["path"], True)]


def test_repair_approval_required_before_import(reception):
    root, authority, calls, _, _ = reception
    path = Path(authority["scientific_acceptance"]["path"])
    review = json.loads(path.read_text())
    review["consumer_repair_accepted"] = False
    path.write_text(json.dumps(review))
    authority["scientific_acceptance"] = bind(path)
    with pytest.raises(ValueError, match="independently"):
        h5.receive(root, authority, clock=lambda: datetime(2026, 10, 19, 6, tzinfo=UTC))
    assert calls == []


def test_callback_drift_and_expiry_refuse(reception):
    root, authority, calls, module, folder = reception
    with pytest.raises(ValueError, match="expired"):
        h5.receive(root, authority, clock=lambda: datetime(2026, 10, 19, 13, 41, tzinfo=UTC))
    original = module.receive_current_package

    def changed(*a, **k):
        result = original(*a, **k)
        (folder / "consumer-schema.json").write_text("{}")
        return result

    module.receive_current_package = changed
    with pytest.raises(ValueError, match="hash changed"):
        h5.receive(root, authority, clock=lambda: datetime(2026, 10, 19, 6, tzinfo=UTC))


@pytest.mark.parametrize("task", ["BASE-CURRENT-INITIALIZATION-20261019", h5.TASK])
def test_same_native_gate_requires_exact_selected_task_and_scope(tmp_path, monkeypatch, task):
    from open_composer.intraday_runner.validation_account_partition import slot

    # Use real gate logic with invented receipt/authority, no actual invocation.
    namespace = dict(vars(entry))
    namespace["__file__"] = str(
        tmp_path / "open_composer/intraday_runner/current_initialization_entry.py"
    )
    source = ast.parse(Path(entry.__file__).read_text())
    node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "gate")
    # Literal closure entries are the complete required set in this empty fixture root.
    required = next(
        n
        for n in ast.walk(node)
        if isinstance(n, ast.Tuple)
        and any(
            isinstance(x, ast.Constant)
            and x.value == "open_composer/intraday_runner/current_h5_component.py"
            for x in n.elts
        )
    )
    code = [{"path": str(tmp_path / x.value)} for x in required.elts]
    job = dict(
        task_id=task,
        active=True,
        phase="decision",
        invocation_id="invented-one",
        whole_route_bytes=23068672,
        protected_normal_bytes=10918819017,
        terminal_bytes=65536,
        authority={"invented": "authority"},
        output=str(slot(tmp_path, task)[0] / "invocations/invented-one"),
        code_bindings=code,
        not_before="2026-10-19T00:00:00Z",
        expires_at="2026-10-19T20:10:00Z",
        capacity_receipt={},
        owned_roots=[],
        native_acceptance={"invented": "native"},
    )
    excluded = {"active", "native_acceptance"}
    native = dict(
        accepted=True,
        scope="CURRENT_VALIDATION_NATIVE_V1",
        job_scope={k: v for k, v in job.items() if k not in excluded},
    )
    auth = dict(task_id=task, code_bindings=code, ledger_root=str(slot(tmp_path, task)[0]))
    namespace.update(
        bound_bytes=lambda root, b: json.dumps(
            native if b == job["native_acceptance"] else job
        ).encode(),
        load_authority=lambda *a: auth,
        capacity=lambda *a: {"invented": True},
        kernel_evidence=lambda: {"invented": True},
    )
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), "<exact-native-gate>", "exec"), namespace
    )
    assert namespace["gate"](tmp_path, {}, now=datetime(2026, 10, 19, 6, tzinfo=UTC))[0] == job
    native["job_scope"] = dict(native["job_scope"], task_id="UNSELECTED")
    with pytest.raises(ValueError, match="native reception"):
        namespace["gate"](tmp_path, {}, now=datetime(2026, 10, 19, 6, tzinfo=UTC))


def test_h5_existing_decision_quantity_path_is_no_write_rehearsal(tmp_path):
    # Invented account observation explicitly does not establish actual funds.
    r = runtime.CurrentInitializationRuntime.__new__(runtime.CurrentInitializationRuntime)
    r.root = Path("/root/codex-test/open-composer")
    r.task = h5.TASK
    r.auth = dict(
        capital_usd=10000, authorized_at="2026-10-19T00:00:00Z", expires_at="2026-11-14T00:00:00Z"
    )
    r.clock = lambda: datetime(2026, 10, 19, 6, tzinfo=UTC)
    r.directory = tmp_path
    r.receive_science = lambda: h5.normalize_received(invented())
    r.initialize = lambda package: None
    captured = []

    def observation(directory, *, risk):
        assert risk is False
        directory.mkdir(parents=True)
        save(directory / "capture.json", {"invented_no_actual_account": True})
        return dict(positions=[], orders={}, activities=[])

    def keep(path, value):
        captured.append(value)
        return save(path, value)

    r.observe = observation
    r.save_capture = keep
    result = r.decide(tmp_path / "decision")
    assert result["broker_writes"] == 0
    rows = captured[0]["requests"]
    assert [row["symbol"] for row in rows] == ["CTVA", "AFL", "DXC", "SNA", "IVZ"]
    assert len(rows) == 5 and all(row["weight"] == 0.2 for row in rows)
    assert all(type(row["max_quantity"]) is int and row["max_quantity"] > 0 for row in rows)
    assert sum(row["max_quantity"] * float(row["limit_price"]) for row in rows) <= 10000
    assert captured[0]["planning_buffer_not_actual_fee"] is True
