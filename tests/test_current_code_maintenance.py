"""Invented local registry continuation fixtures; never use the real ledger."""

import importlib.util
import json
import socket
from pathlib import Path

import pytest

from open_composer.intraday_runner.source_activity_reception import bind, save
from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint
from open_composer.intraday_runner.validation_account_partition import (
    ACCOUNT,
    BASE,
    H5,
    LSTM,
    SLOTS,
    slot,
)

SCRIPT = Path(__file__).parents[1] / "scripts/rebind_current_validation_code.py"
spec = importlib.util.spec_from_file_location("maintenance_fixture", SCRIPT)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("no network")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path
    ledger, namespace = slot(root, BASE)
    registry = ledger.parent / ".account-envelope" / (BASE + ".json")
    registry.parent.mkdir(parents=True)
    ledger.mkdir()
    for p in (
        root / "reports/paper/.submission.lock",
        root / "reports/paper/.control.lock",
        registry.parent / "account.lock",
        ledger / ".operation.lock",
    ):
        p.touch()
    data = root / "packet"
    data.mkdir()

    def write(name, value):
        return save(data / name, value)

    old = dict(
        task_id=BASE,
        account_hash=ACCOUNT,
        partition=write("legacy-partition.json", {"invented": True}),
        main_scope=write("account-scope.json", {"invented": True}),
        namespace=namespace,
        capital_usd=10000,
        ledger_root=str(ledger),
        expires_at="2026-11-14T00:00:00Z",
        authorized_at="2026-10-19T00:00:00Z",
        code_bindings=[{"old": True}],
        operating_acceptance={"old": True},
    )
    old_auth = write("old-authority.json", old)
    old_pointer = save(
        registry,
        dict(
            task=BASE,
            authority=old_auth,
            partition=old["partition"],
            ledger_root=str(ledger),
            namespace=namespace,
            allocation=10000,
        ),
    )
    snapshot = dict(
        cashbook=dict(cash=10000, sales=[], purchases=[], dividends=[], lots={}, next_id=0),
        pending={},
        consumed_ids=[],
        applied_fill_ids=[],
        fills={},
        fees={},
        evidence={"unresolved_actual_liabilities": False},
    )
    store = SourceStateCheckpoint(ledger / "checkpoints", account_hash=ACCOUNT, sleeve_id=BASE)
    store.commit(snapshot, expected_head_sha256=None)
    output = ledger / "invocations/base-current-session-20261019-02"
    output.mkdir(parents=True)
    Path(str(output) + ".launcher").mkdir()
    job = write(
        "job.json",
        dict(
            authority=old_auth,
            task_id=BASE,
            output=str(output),
            invocation_id=output.name,
            whole_route_bytes=23068672,
        ),
    )
    (ledger / "consumed").mkdir()
    consumed = save(ledger / "consumed" / (output.name + ".json"), {"job": job})
    completion = save(output / "completion.json", {"results": [], "failures": ["invented"]})
    launcher = save(
        Path(str(output) + ".launcher") / "completion.json", {"exit_code": 2, "native_exit": 2}
    )
    main = write(
        "main.json",
        {
            "continued_authority": {
                "new_invocation_successor_under_existing_scope_after_accepted_affected_repair_"
                "Main_exact_integration_and_fresh_native_gates": True
            }
        },
    )
    first_auth = write(
        "first-authority.json",
        dict(old, code_bindings=[{"oldest": True}], operating_acceptance={"oldest": True}),
    )
    first_output = ledger / "invocations/base-current-session-20261019-01"
    first_output.mkdir()
    Path(str(first_output) + ".launcher").mkdir()
    first_job = write(
        "first-job.json",
        dict(
            authority=first_auth,
            task_id=BASE,
            output=str(first_output),
            invocation_id=first_output.name,
        ),
    )
    history = dict(
        authority=first_auth,
        job=first_job,
        native_consumed=save(
            ledger / "consumed" / (first_output.name + ".json"), {"job": first_job}
        ),
        completion=save(
            first_output / "completion.json", {"results": [], "failures": ["invented"]}
        ),
        launcher_completion=save(
            Path(str(first_output) + ".launcher/completion.json"),
            {"exit_code": 2, "native_exit": 2},
        ),
        maintenance_completed=write(
            "previous-maintenance.json", {"pointer": old_pointer, "financial_state_changed": False}
        ),
    )
    dispatch = ledger / "dispatch"
    dispatch.mkdir()
    lock = dispatch / ".dispatch.lock"
    lock.touch()
    ds, ls = dispatch.stat(), lock.stat()
    dispatch_identity = dict(
        path=str(dispatch),
        device=ds.st_dev,
        inode=ds.st_ino,
        lock_device=ls.st_dev,
        lock_inode=ls.st_ino,
    )
    proof = write(
        "proof.json",
        dict(
            session01=history,
            dispatch_identity=dispatch_identity,
            dispatch_lock=bind(lock),
            old_pointer=old_pointer,
            old_authority=old_auth,
            head=bind(store.directory / "head.json"),
            revision=bind(store.directory / "revision-00000000.json"),
            old_job=job,
            native_consumed=consumed,
            completion=completion,
            launcher_completion=launcher,
            main_continuation=main,
        ),
    )
    review = write(
        "review.json",
        dict(
            accepted_code_maintenance=True,
            maintenance_code=bind(SCRIPT),
            maintenance_precondition=proof,
            maintenance_capacity_receipt=write(
                "capacity-receipt.json", {"accepted_whole_route_peak_bytes": 34603008}
            ),
        ),
    )
    new = dict(old, code_bindings=[{"new": True}], operating_acceptance=review)
    new_auth = write("new-authority.json", new)
    plan = write(
        "plan.json",
        dict(
            precondition=proof,
            new_authority=new_auth,
            integration_receipt=write(
                "integration.json",
                {
                    "status": "integrated_verified_inert",
                    "task_id": BASE,
                    "accepted_review": review,
                    "installed_closure": write(
                        "closure.json", {"installed_code_bindings": new["code_bindings"]}
                    ),
                },
            ),
            audit_directory=str(data / "audit"),
        ),
    )
    calls = []

    class Storage:
        def __init__(self, root, job):
            assert job["whole_route_bytes"] == 34603008
            assert job["capacity_receipt"] == bind(data / "capacity-receipt.json")

        def check(self, extra=0, *, path=None):
            calls.append((extra, path))
            return {}

        def save(self, path, value):
            self.check(len(json.dumps(value)) * 2 + 8192, path=path)
            return save(path, value)

    monkeypatch.setattr(maintenance, "NativeStorage", Storage)
    monkeypatch.setattr(maintenance, "kernel_evidence", lambda: None)
    monkeypatch.setattr(maintenance, "service_finished", lambda name: {"MainPID": "0"})
    monkeypatch.setattr(
        maintenance, "load_authority", lambda root, b, now: maintenance.receive(root, b)
    )
    return dict(
        root=root,
        ledger=ledger,
        registry=registry,
        data=data,
        plan=plan,
        old=old,
        new=new,
        proof=proof,
        store=store,
        calls=calls,
        Storage=Storage,
    )


def test_exact_pointer_only_with_all_financial_and_native_bytes_retained(fixture):
    f = fixture
    before = {p: p.read_bytes() for p in f["ledger"].rglob("*") if p.is_file()}
    old_pointer = f["registry"].read_bytes()
    result = maintenance.execute(f["root"], f["plan"])
    assert json.loads(Path(result["path"]).read_text())["financial_state_changed"] is False
    for p, raw in before.items():
        assert p.read_bytes() == raw
    assert (f["data"] / "audit/old-pointer.json").read_bytes() == old_pointer
    pointer = json.loads(f["registry"].read_text())
    assert pointer["allocation"] == 10000
    assert pointer["authority"] == json.loads(Path(f["plan"]["path"]).read_text())["new_authority"]
    assert {p.name for p in (f["ledger"] / "dispatch").iterdir()} == {".dispatch.lock"}
    with pytest.raises(ValueError):
        maintenance.execute(f["root"], f["plan"])


@pytest.mark.parametrize(
    "field,value",
    [("capital_usd", 20000), ("namespace", "changed"), ("expires_at", "2026-12-01T00:00:00Z")],
)
def test_scope_cannot_expand(fixture, field, value):
    f = fixture
    new = dict(f["new"], **{field: value})
    with pytest.raises(ValueError, match="financial or lifecycle"):
        maintenance.unchanged_scope(f["old"], new)


@pytest.mark.parametrize("change", ["checkpoint", "native-marker", "dispatch", "decision"])
def test_changed_or_unknown_saved_state_refuses(fixture, change):
    f = fixture
    pointer = f["registry"].read_bytes()
    if change == "checkpoint":
        state = f["store"].load()
        state["snapshot"]["cashbook"]["cash"] = 9999
        from open_composer.intraday_runner.source_dispatch_journal import _hash

        original = f["store"].load()
        f["store"].commit(state["snapshot"], expected_head_sha256=_hash(original))
    elif change == "native-marker":
        next((f["ledger"] / "consumed").iterdir()).unlink()
    elif change == "dispatch":
        (f["ledger"] / "dispatch" / "unknown-marker.json").write_text("{}")
    else:
        (f["ledger"] / "initial-decision.json").write_text("{}")
    with pytest.raises((ValueError, FileNotFoundError)):
        maintenance.execute(f["root"], f["plan"])
    assert f["registry"].read_bytes() == pointer


def test_storage_refusal_before_mutation(fixture, monkeypatch):
    f = fixture
    pointer = f["registry"].read_bytes()

    def refuse(*args, **kwargs):
        raise ValueError("no allocation")

    monkeypatch.setattr(f["Storage"], "check", refuse)
    with pytest.raises(ValueError, match="no allocation"):
        maintenance.execute(f["root"], f["plan"])
    assert f["registry"].read_bytes() == pointer
    assert not (f["data"] / "audit").exists()
    assert {p.name for p in (f["ledger"] / "dispatch").iterdir()} == {".dispatch.lock"}


def test_post_pointer_failure_retains_consumed_audit_no_reset(fixture, monkeypatch):
    f = fixture
    original = f["Storage"].save

    def fail_final(self, path, value):
        if path.name == "completed.json":
            raise ValueError("final receipt unavailable")
        return original(self, path, value)

    monkeypatch.setattr(f["Storage"], "save", fail_final)
    with pytest.raises(ValueError, match="final receipt"):
        maintenance.execute(f["root"], f["plan"])
    assert (f["data"] / "audit/prepared.json").exists()
    assert not (f["data"] / "audit/completed.json").exists()
    assert f["store"].load()["generation"] == 0
    with pytest.raises(ValueError):
        maintenance.execute(f["root"], f["plan"])


@pytest.mark.parametrize("which", ["first-native", "previous-maintenance", "dispatch-inode"])
def test_session02_continuation_retains_both_predecessors(fixture, which):
    f = fixture
    pointer = f["registry"].read_bytes()
    proof = json.loads(Path(f["proof"]["path"]).read_text())
    if which == "first-native":
        Path(proof["session01"]["native_consumed"]["path"]).write_text("{}")
    elif which == "previous-maintenance":
        Path(proof["session01"]["maintenance_completed"]["path"]).write_text("{}")
    else:
        dispatch = f["ledger"] / "dispatch"
        dispatch.rename(f["ledger"] / "retained-dispatch")
        dispatch.mkdir()
        (dispatch / ".dispatch.lock").touch()
    with pytest.raises(ValueError):
        maintenance.execute(f["root"], f["plan"])
    assert f["registry"].read_bytes() == pointer


def test_maintenance_capacity_binding_refuses_drift_without_mutation(fixture):
    f = fixture
    old_pointer = f["registry"].read_bytes()
    (f["data"] / "capacity-receipt.json").write_text("{}")
    with pytest.raises(ValueError):
        maintenance.execute(f["root"], f["plan"])
    assert f["registry"].read_bytes() == old_pointer
    assert not (f["data"] / "audit").exists()


def partition_successor(f):
    def write(name, value):
        return save(f["data"] / name, value)

    owner = write("partition-owner.json", {"invented": True})
    part = write(
        "three-partition.json",
        dict(
            selected_task=LSTM,
            selected_tasks=list(SLOTS),
            owner_instruction=owner,
            account_binding=f["old"]["main_scope"],
            prior_partition=f["old"]["partition"],
            allocation_by_task_USD={BASE: 10000, H5: 6000, LSTM: 4000},
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
            BASE_partition_continuation=dict(
                explicitly_authorized_affected_extension=True,
                allowed_BASE_authority_fields_to_change_only=[
                    "code_bindings",
                    "operating_acceptance",
                    "partition",
                ],
                allowed_BASE_registry_fields_to_change_only=["authority", "partition"],
            ),
        ),
    )
    review = json.loads((f["data"] / "review.json").read_text())
    review["maintenance_partition"] = part
    reviewed = write("partition-review.json", review)
    authority = write(
        "partition-authority.json", dict(f["new"], partition=part, operating_acceptance=reviewed)
    )
    plan = json.loads(Path(f["plan"]["path"]).read_text())
    integration = json.loads(Path(plan["integration_receipt"]["path"]).read_text())
    integration["accepted_review"] = reviewed
    plan.update(
        new_authority=authority,
        integration_receipt=write("partition-integration.json", integration),
    )
    return write("partition-plan.json", plan), part


def test_partition_only_successor_preserves_BASE_and_both_failed_invocations(fixture):
    f = fixture
    plan, part = partition_successor(f)
    old = json.loads(f["registry"].read_text())
    before = {p: p.read_bytes() for p in f["ledger"].rglob("*") if p.is_file()}
    maintenance.execute(f["root"], plan)
    after = json.loads(f["registry"].read_text())
    assert after["partition"] == part and after["allocation"] == 10000
    assert {k: v for k, v in old.items() if k not in {"authority", "partition"}} == {
        k: v for k, v in after.items() if k not in {"authority", "partition"}
    }
    assert all(p.read_bytes() == raw for p, raw in before.items())
    assert not slot(f["root"], H5)[0].exists() and not slot(f["root"], LSTM)[0].exists()


@pytest.mark.parametrize("task", [H5, LSTM])
def test_partition_migration_refuses_any_existing_other_ledger(fixture, task):
    f = fixture
    plan, _ = partition_successor(f)
    old = f["registry"].read_bytes()
    slot(f["root"], task)[0].mkdir(parents=True)
    with pytest.raises(ValueError, match="prospective sleeve"):
        maintenance.execute(f["root"], plan)
    assert f["registry"].read_bytes() == old


def test_partition_migration_rechecks_other_ledgers_before_CAS(fixture, monkeypatch):
    f = fixture
    plan, _ = partition_successor(f)
    old = f["registry"].read_bytes()
    original = f["Storage"].save

    def mutate(self, path, value):
        result = original(self, path, value)
        if path.name == "prepared.json":
            slot(f["root"], LSTM)[0].mkdir(parents=True)
        return result

    monkeypatch.setattr(f["Storage"], "save", mutate)
    with pytest.raises(ValueError, match="prospective sleeve"):
        maintenance.execute(f["root"], plan)
    assert f["registry"].read_bytes() == old
    assert (f["data"] / "audit/prepared.json").exists()


def funding_successor(f, monkeypatch):
    """Invented current native scope with the real locked helper/publication code."""
    from types import SimpleNamespace

    from open_composer.intraday_runner import current_initialization_account as account
    from open_composer.intraday_runner import current_initialization_funding as funding
    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from tests.test_current_funding_flow import context

    data = f["data"]
    oldproof = json.loads(Path(f["proof"]["path"]).read_text())
    # A new fixture's generation0 is created with real funding/risk evidence.
    original = f["store"].load()
    state = original["snapshot"]
    state["evidence"].update(
        allocated_capital="10000",
        risk=dict(
            initial_capital="10000",
            high_water="10000",
            day=None,
            day_open_nav=None,
            halted=False,
            killed=False,
        ),
    )
    original["snapshot"] = state
    from open_composer.intraday_runner.source_dispatch_journal import _canonical

    (f["store"].directory / "revision-00000000.json").write_text(_canonical(original) + "\n")
    f["store"]._publish(original)
    oldproof.update(
        head=bind(f["store"].directory / "head.json"),
        revision=bind(f["store"].directory / "revision-00000000.json"),
    )
    proof = save(data / "funding-proof.json", oldproof)
    decision = dict(
        actual_predecessor_readonly={k: oldproof[k] for k in ("old_pointer", "head", "revision")}
    )
    main = save(data / "funding-main.json", decision)
    monkeypatch.setattr(funding, "MAIN_SHA", main["sha256"])
    monkeypatch.setattr(maintenance, "receive_partition", lambda root, b: decision)
    review = json.loads((data / "review.json").read_text())
    review.update(
        accepted_funding_continuation=True,
        maintenance_partition=main,
        maintenance_precondition=proof,
    )
    rb = save(data / "funding-review.json", review)
    new = dict(f["new"], capital_usd=20000, partition=main, operating_acceptance=rb)
    nb = save(data / "funding-new.json", new)
    integration = json.loads((data / "integration.json").read_text())
    integration["accepted_review"] = rb
    plan = save(
        data / "funding-plan.json",
        dict(
            precondition=proof,
            new_authority=nb,
            integration_receipt=save(data / "funding-integration.json", integration),
            audit_directory=str(data / "funding-audit"),
        ),
    )
    c, o, kw = context()
    o["checkpoint_hash"] = _hash(original)
    partition = SimpleNamespace(held=True)
    runtime = SimpleNamespace(
        authority=nb,
        _operation_held=True,
        partition=partition,
        current_phase="decision",
        maintenance_plan=plan,
        guard_write=lambda *a, **k: None,
        read_guard=lambda **kw: None,
        connect=lambda: None,
        clock=lambda: kw["now"],
        monotonic=lambda: 1,
    )
    monkeypatch.setattr(
        maintenance, "ValidationAccountPartition", lambda *a, **k: SimpleNamespace(held=False)
    )

    def capture(rt, directory, **kw):
        directory.mkdir()
        save(directory / "capture.json", dict(observation=o))
        return dict(
            aggregate_positions=[], aggregate_orders={}, aggregate_activities=[], observation=o
        )

    monkeypatch.setattr(account, "capture", capture)
    return plan, runtime, original


def test_actual_funding_helper_creates_successor_not_reset(fixture, monkeypatch):
    f = fixture
    plan, rt, old = funding_successor(f, monkeypatch)
    before = (f["store"].directory / "revision-00000000.json").read_bytes()
    result = maintenance.execute(f["root"], plan, runtime=rt)
    assert json.loads(Path(result["path"]).read_text())["capital_flow_USD"] == 10000
    current = f["store"].load()
    assert current["generation"] == 1 and current["snapshot"]["cashbook"]["cash"] == 20000
    assert (f["store"].directory / "revision-00000000.json").read_bytes() == before
    assert json.loads(f["registry"].read_text())["allocation"] == 20000
    assert current["snapshot"]["evidence"]["allocation_flows"][0]["profit_USD"] == "0"
    with pytest.raises(ValueError):
        maintenance.execute(f["root"], plan, runtime=rt)


def test_funding_publication_failure_preserves_hold_no_reapply(fixture, monkeypatch):
    f = fixture
    plan, rt, old = funding_successor(f, monkeypatch)
    before = f["registry"].read_bytes()
    write = maintenance._atomic_write_text

    def refuse(path, text):
        if path == f["registry"]:
            raise OSError("invented publication failure")
        return write(path, text)

    monkeypatch.setattr(maintenance, "_atomic_write_text", refuse)
    with pytest.raises(OSError):
        maintenance.execute(f["root"], plan, runtime=rt)
    assert f["registry"].read_bytes() == before
    assert f["store"].load()["generation"] == 1
    with pytest.raises(ValueError):
        maintenance.execute(f["root"], plan, runtime=rt)
    assert f["store"].load()["snapshot"]["cashbook"]["cash"] == 20000


def test_six_capacity_storage_context_replaces_old_roots_without_job_rewrite(fixture, monkeypatch):
    f = fixture
    data = f["data"]
    review = json.loads((data / "review.json").read_text())
    roots = [str(data / str(i)) for i in range(13)]
    proposal = save(
        data / "six-proposal.json", dict(current_root_allocation=[{"root": r} for r in roots])
    )
    receipt = save(
        data / "six-capacity.json",
        dict(
            task_id="SIX-CANDIDATE-PAPER-VALIDATION-20261019",
            accepted_whole_route_peak_bytes=90177536,
            request_bindings={"actual_six_candidate_whole_route_proposal": proposal},
        ),
    )
    review["maintenance_capacity_receipt"] = receipt
    rb = save(data / "six-capacity-review.json", review)
    new = dict(f["new"], operating_acceptance=rb)
    nb = save(data / "six-capacity-auth.json", new)
    integration = json.loads((data / "integration.json").read_text())
    integration["accepted_review"] = rb
    plan = json.loads(Path(f["plan"]["path"]).read_text())
    plan.update(
        new_authority=nb,
        integration_receipt=save(data / "six-capacity-integration.json", integration),
    )
    pb = save(data / "six-capacity-plan.json", plan)
    before = (data / "job.json").read_bytes()

    class Reached(Exception):
        pass

    def storage(root, job):
        assert job["owned_roots"] == roots and job["whole_route_bytes"] == 90177536
        assert job["capacity_receipt"] == receipt
        raise Reached()

    monkeypatch.setattr(maintenance, "NativeStorage", storage)
    with pytest.raises(Reached):
        maintenance.execute(f["root"], pb)
    assert (data / "job.json").read_bytes() == before
    assert not (data / "audit").exists()


@pytest.mark.parametrize(
    "boundary",
    [
        "revision_storage",
        "head_storage",
        "receipt_return",
        "registry_io",
        "head_io",
        "code_recheck",
        "secure_change",
    ],
)
def test_funding_staleness_at_actual_publication_boundaries_holds(fixture, monkeypatch, boundary):
    from datetime import timedelta

    f = fixture
    plan, rt, old = funding_successor(f, monkeypatch)
    now = rt.clock()
    elapsed = [0]
    rt.clock = lambda: now + timedelta(seconds=elapsed[0])
    rt.monotonic = lambda: 1 + elapsed[0]
    before = f["registry"].read_bytes()
    Storage = f["Storage"]
    seen = []

    class DelayedStorage(Storage):
        def check(self, extra=0, *, path=None):
            result = super().check(extra, path=path)
            name = Path(path).name if path else ""
            if not seen and (
                (boundary == "revision_storage" and name == "revision-00000001.json")
                or (boundary == "head_storage" and name == "head.json")
            ):
                elapsed[0] += 16
                seen.append(boundary)
            return result

        def save(self, path, value):
            result = super().save(path, value)
            if (
                boundary == "receipt_return"
                and Path(path).name == "funding-checkpoint.json"
                and not seen
            ):
                elapsed[0] += 16
                seen.append(boundary)
            return result

    monkeypatch.setattr(maintenance, "NativeStorage", DelayedStorage)
    if boundary == "registry_io":
        original = maintenance._atomic_write_text

        def write(path, text):
            result = original(path, text)
            if path == f["registry"] and not seen:
                elapsed[0] += 16
                seen.append(boundary)
            return result

        monkeypatch.setattr(maintenance, "_atomic_write_text", write)
    if boundary == "head_io":
        original = SourceStateCheckpoint._publish

        def publish(self, revision):
            result = original(self, revision)
            if revision["generation"] == 1 and not seen:
                elapsed[0] += 16
                seen.append(boundary)
            return result

        monkeypatch.setattr(SourceStateCheckpoint, "_publish", publish)
    if boundary in {"code_recheck", "secure_change"}:

        def recheck(**kw):
            if boundary == "secure_change":
                raise ValueError("invented changed secure identity")
            if not seen:
                elapsed[0] += 16
                seen.append(boundary)

        rt.read_guard = recheck
    with pytest.raises((ValueError, FileExistsError)):
        maintenance.execute(f["root"], plan, runtime=rt)
    audit = f["data"] / "funding-audit"
    assert (audit / "funding-hold.json").is_file()
    assert not (audit / "completed.json").exists()
    if boundary != "registry_io":
        assert f["registry"].read_bytes() == before
    else:
        assert json.loads(f["registry"].read_text())["allocation"] == 20000
    assert json.loads((f["store"].directory / "revision-00000000.json").read_text()) == old
    with pytest.raises((ValueError, FileExistsError)):
        maintenance.execute(f["root"], plan, runtime=rt)
