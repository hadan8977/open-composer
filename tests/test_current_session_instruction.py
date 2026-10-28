"""Saved current instruction mapping and prospective windows; no API/model call."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from open_composer.intraday_runner.current_initialization_controls import (
    identity,
    require_phase,
)
from open_composer.intraday_runner.current_initialization_episode import normalize_received
from open_composer.intraday_runner.current_session_instruction import FOLDER, normalize

ROOT = Path("/root/codex-test/open-composer")


@pytest.fixture(scope="module")
def saved():
    # Exact accepted readonly evidence, never call its consumer a second time.
    import hashlib

    data = (ROOT / FOLDER / "actual-readonly-consumer-views.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == (
        "061da7d088f5c422c4fedc8dc1a6664c1f00ca00e2bce60d9978d134ec37a14e"
    )
    return json.loads(data)["views"]


@pytest.mark.parametrize("policy", ["BASE", "H5", "LSTM", "BASE_STATE_BUDGET"])
def test_saved_current_instruction_exact_mapping(saved, policy):
    value = saved[policy]
    out = normalize_received(value, policy)
    assert out["forecast"]["symbols"] == value["symbols"]
    assert out["forecast"]["weights"] == value["weights"]
    assert out["forecast"]["reference_marks"] == value["raw_reference_marks"]
    assert out["received_scientific_component"] is value
    assert out["runtime_K_rank_weight_recalculation"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("new_prediction", True),
        ("consume_before", "2026-10-20T20:00:00Z"),
        ("adopted_at", "2026-10-20T10:00:00Z"),
        ("capital_USD", 10000),
    ],
)
def test_adoption_drift_refused(saved, field, value):
    changed = copy.deepcopy(saved["BASE"])
    changed[field] = value
    with pytest.raises(ValueError):
        normalize(changed, "BASE")


def test_old_and_new_windows_remain_distinct():
    now = datetime(2026, 10, 20, 15, tzinfo=UTC)
    args = ("2026-10-20T14:40:00Z", "2026-11-14T00:00:00Z")
    with pytest.raises(ValueError):
        require_phase(now, "decision", *args)
    require_phase(now, "decision", *args, prospective=True)
    require_phase(now, "opening", *args, prospective=True)
    require_phase(now, "buy", *args, prospective=True)
    for phase in ("decision", "opening", "buy"):
        with pytest.raises(ValueError):
            require_phase(
                datetime(2026, 10, 20, 19, 30, tzinfo=UTC), phase, *args, prospective=True
            )
    require_phase(datetime(2026, 10, 20, 19, 52, tzinfo=UTC), "cancel", *args, prospective=True)
    with pytest.raises(ValueError):
        require_phase(datetime(2026, 10, 20, 19, 55, tzinfo=UTC), "cancel", *args, prospective=True)


def test_actual_day_cid_no_oct19_retag():
    namespace = "basecur-20261019-fa6147de"
    identity(f"{namespace}-1020-buy-AAPL", "AAPL", "buy")
    with pytest.raises(ValueError):
        identity(f"{namespace}-1019-buy-AAPL", "AAPL", "buy")


@pytest.mark.parametrize("fail_pointer", [False, True])
def test_gen1_zero_flow_successor_and_partial_hold(tmp_path, monkeypatch, saved, fail_pointer):
    from types import SimpleNamespace

    from open_composer.intraday_runner import current_session_instruction as instruction
    from open_composer.intraday_runner.source_activity_reception import bind, save
    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint
    from open_composer.intraday_runner.validation_account_partition import ACCOUNT, BASE

    d = ROOT / (
        "reports/research/program/owner-profit-delivery-plan-20261017/"
        "paper-delivery/preopen-20261020/BASE-native-session-01"
    )
    auth_path = d / "authority.json"
    old = json.loads(auth_path.read_text())
    source = Path(old["ledger_root"]) / "checkpoints"
    clone = tmp_path / "checkpoints"
    clone.mkdir()
    for name in ("head.json", "revision-00000000.json", "revision-00000001.json"):
        (clone / name).write_bytes((source / name).read_bytes())
    store = SourceStateCheckpoint(clone, account_hash=ACCOUNT, sleeve_id=BASE)
    before = store.load()
    assert before["generation"] == 1
    before_raw = (clone / "revision-00000001.json").read_bytes()
    pointer_dir = tmp_path / "registry"
    pointer_dir.mkdir()
    original_pointer = Path(old["ledger_root"]).parent / ".account-envelope" / (BASE + ".json")
    # Real registry is beside the strategy's account root, not inside it.
    if not original_pointer.exists():
        original_pointer = (
            ROOT
            / ("reports/paper/intraday/dia-base-initialization-20261019/.account-envelope")
            / (BASE + ".json")
        )
    pointer = pointer_dir / (BASE + ".json")
    pointer.write_bytes(original_pointer.read_bytes())
    old_pointer = pointer.read_bytes()
    new = copy.deepcopy(old)
    new.update(
        session_id=instruction.SESSION,
        prospective_session={"invented": True},
        scientific_acceptance=saved["BASE"]["review"],
    )
    new_binding = {"path": "invented-new-authority", "bytes": 1, "sha256": "invented"}
    proof_binding = {"path": "invented-proof"}
    plan_binding = {"path": "invented-plan"}
    proof = dict(
        old_authority=bind(auth_path),
        registry_pointer=bind(pointer),
        canonical_head_sha256=_hash(before),
        retained_bindings=[],
        **{
            k: {"path": "invented-retained-" + k}
            for k in ("head", "revision", "consumed_marker", "actual_outcome", "outcome_review")
        },
    )
    plan = dict(
        precondition=proof_binding,
        new_authority=new_binding,
        capital_flow_USD=0,
        output=str(tmp_path / "adoption"),
        integration_receipt={"path": "invented-integration"},
    )
    review = dict(
        accepted_current_day_continuation=True,
        episode_continuation_precondition=proof_binding,
        episode_continuation_code=bind(Path(instruction.__file__).resolve()),
    )
    values = {
        plan_binding["path"]: plan,
        proof_binding["path"]: proof,
        old["operating_acceptance"]["path"]: review,
        str(auth_path): old,
        "invented-integration": dict(
            status="integrated_verified_inert",
            task_id=BASE,
            accepted_review=new["operating_acceptance"],
            installed_closure={"path": "invented-installed"},
        ),
        "invented-installed": dict(installed_code_bindings=new["code_bindings"]),
    }

    def fixture_bound(root, binding):
        if binding["path"] == str(pointer):
            return old_pointer
        if binding["path"].startswith("invented-retained-"):
            return b"{}"
        return json.dumps(values[binding["path"]]).encode()

    monkeypatch.setattr(instruction, "bound_bytes", fixture_bound)
    journal = tmp_path / "dispatch"
    journal.mkdir()

    def write(path, payload):
        if fail_pointer:
            raise OSError("invented post-checkpoint storage refusal")
        path.write_text(payload)

    runtime = SimpleNamespace(
        root=tmp_path,
        directory=tmp_path,
        task=BASE,
        auth=new,
        authority=new_binding,
        _operation_held=True,
        partition=SimpleNamespace(held=True, directory=pointer_dir),
        current_phase="decision",
        store=store,
        journal=SimpleNamespace(directory=journal),
        current_scientific_package=normalize(saved["BASE"], "BASE"),
        clock=lambda: datetime(2026, 10, 20, 15, tzinfo=UTC),
        ensure_directory=lambda p: p.mkdir(),
        save_capture=save,
        require_phase=lambda phase: None,
        write_text=write,
    )
    if fail_pointer:
        with pytest.raises(OSError):
            instruction.continue_empty_base(runtime, plan_binding)
        assert (tmp_path / "adoption/held.json").exists()
        assert pointer.read_bytes() == old_pointer
    else:
        instruction.continue_empty_base(runtime, plan_binding)
        assert json.loads(pointer.read_text())["authority"] == new_binding
    after = store.load()
    assert after["generation"] == 2
    assert after["snapshot"]["cashbook"] == before["snapshot"]["cashbook"]
    for key in ("risk", "allocation_flows", "allocated_capital"):
        assert after["snapshot"]["evidence"][key] == before["snapshot"]["evidence"][key]
    assert (clone / "revision-00000001.json").read_bytes() == before_raw
    with pytest.raises(ValueError):
        instruction.continue_empty_base(runtime, plan_binding)
    if not fail_pointer:
        # Continue the actual saved GEN1-derived snapshot through initialize and
        # decision. Only the account observation is an explicitly invented
        # successful fixture; no client/consumer/model/native is called.
        from open_composer.intraday_runner.current_initialization_runtime import (
            CurrentInitializationRuntime,
        )

        rt = CurrentInitializationRuntime.__new__(CurrentInitializationRuntime)
        rt.__dict__.update(runtime.__dict__)
        rt.root = ROOT  # Existing arithmetic implementation, no forecast forward.
        rt.read_guard = lambda **kw: None
        rt.namespace = old["namespace"]
        rt.partition.register = lambda task, binding: (
            None
            if json.loads(pointer.read_text())["authority"] == binding
            else pytest.fail("successor registry was not received")
        )
        output = tmp_path / "decision"
        (output / "account").mkdir(parents=True)
        save(
            output / "account/capture.json",
            {"synthetic": True, "authenticated": False, "checkpoint": _hash(after)},
        )
        rt.observe = lambda directory, **kw: dict(positions=[], orders={}, activities=[])
        result = rt.decide(output)
        assert result["status"] == "evaluated_current_decision"
        decision = json.loads((tmp_path / "initial-decision.json").read_text())
        assert decision["package"] == rt.current_scientific_package
        assert len(decision["requests"]) == 5
        assert store.load() == after


def test_unchanged_cash_observation_and_final_order_guards():
    import ast
    import subprocess

    from open_composer.intraday_runner import current_initialization_runtime as module

    path = "open_composer/intraday_runner/current_initialization_runtime.py"
    old = ast.parse(subprocess.check_output(["git", "show", "b79178c:" + path], text=True))
    new = ast.parse(Path(module.__file__).read_text())
    names = {
        "load_authority",
        "initialize",
        "receive_science",
        "order_guard",
        "reconcile",
        "abandon",
        "guard_write",
    }

    def selected(tree):
        return {
            n.name: ast.dump(n, include_attributes=False)
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name in names
        }

    assert selected(old) == selected(new)


def test_missing_composite_adapter_blocks_only_composite(monkeypatch):
    from open_composer.intraday_runner import current_session_instruction as instruction
    from open_composer.intraday_runner.current_initialization_runtime import (
        CurrentInitializationRuntime,
    )
    from open_composer.intraday_runner.validation_account_partition import BASE, EQUAL

    assert instruction.runtime_class(ROOT, {"task_id": BASE}) is CurrentInitializationRuntime
    monkeypatch.setattr(instruction, "bound_bytes", lambda *a: b"{}")
    with pytest.raises(ValueError, match="child runtime"):
        instruction.runtime_class(ROOT, dict(task_id=EQUAL, operating_acceptance={}))
    with pytest.raises(ValueError, match="child books"):
        instruction.normalize({}, "MULTI_EQUAL")


def test_post_buy_settle_precedes_wait_and_keeps_order_windows():
    from open_composer.intraday_runner import current_initialization_entry as entry

    authority = {"session_id": "SIX-CURRENT-SESSION-20261020"}
    assert "settle" in entry.PHASES
    initial = entry.phase_plan({"phase": "initialization"}, authority)
    assert initial == [("decision", None), ("opening", None), ("buy", None), ("settle", None)]
    assert entry.phase_plan({"phase": "session"}, authority)[:4] == initial
    ongoing = entry.phase_plan({"phase": "continuation"}, authority)
    assert [p for p, _ in ongoing] == ["risk", "cancel", "reconcile"]
    assert ongoing[1:] == [
        ("cancel", "2026-10-20T19:50:00Z"),
        ("reconcile", "2026-10-20T20:05:00Z"),
    ]
    with pytest.raises(ValueError):
        entry.phase_plan({"phase": "initialization"}, {})
    now = datetime(2026, 10, 20, 16, tzinfo=UTC)
    require_phase(now, "settle", "2026-10-20T14:40:00Z", "2026-11-14T00:00:00Z", prospective=True)
    with pytest.raises(ValueError):
        require_phase(
            datetime(2026, 10, 20, 20, tzinfo=UTC),
            "settle",
            "2026-10-20T14:40:00Z",
            "2026-11-14T00:00:00Z",
            prospective=True,
        )


def test_earlier_owned_partial_fill_applied_before_later_sleeve_decision(
    tmp_path, monkeypatch, saved
):
    """Invented actual-format FILL, real receipt application; no broker call."""
    from types import SimpleNamespace

    from open_composer.intraday_runner import current_initialization_runtime as mod
    from open_composer.intraday_runner.source_activity_reception import save
    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.source_method_bindings import source_module
    from open_composer.intraday_runner.source_reservations import SourceReservations
    from open_composer.intraday_runner.source_state_checkpoint import (
        SourceStateCheckpoint,
        snapshot,
    )
    from open_composer.intraday_runner.validation_account_partition import (
        ACCOUNT,
        BASE,
        H5,
        ValidationAccountPartition,
    )

    cash_type = source_module(ROOT, "cash").CashState
    state = SourceReservations(cash_type(cash=20000))
    cid = "basecur-20261019-fa6147de-1020-buy-AAPL"
    reservation = state.reserve_buy(cid, "AAPL", 2, 100.0, 0.2, "2026-10-20", "2026-10-20")
    request = dict(
        client_order_id=cid,
        symbol="AAPL",
        side="buy",
        qty=2,
        type="limit",
        time_in_force="day",
        limit_price=100.0,
        reservation=reservation,
    )
    order = dict(
        id="invented-owned-broker-order",
        client_order_id=cid,
        symbol="AAPL",
        side="buy",
        qty="2",
        type="limit",
        time_in_force="day",
        limit_price="100",
        status="partially_filled",
        filled_qty="1",
    )
    journal = dict(
        client_order_id=cid,
        request=request,
        request_sha256=_hash(request),
        stage="transport_returned_reconciliation_required",
        observations=[],
        dispatch_created_at="2026-10-20T15:59:59Z",
    )
    event = dict(
        id="invented-fill-1",
        activity_type="FILL",
        type="partial_fill",
        order_id=order["id"],
        symbol="AAPL",
        side="buy",
        qty="1",
        price="99",
        cum_qty="1",
        transaction_time="2026-10-20T16:00:00Z",
    )
    evidence = dict(
        allocated_capital="20000",
        account_initial_cash="1000000",
        actual_fees_reconciled=False,
        risk=dict(
            initial_capital="20000",
            net_allocation_flows="0",
            high_water="20000",
            halted=False,
            killed=False,
        ),
    )
    store = SourceStateCheckpoint(
        tmp_path / "base-checkpoints", account_hash=ACCOUNT, sleeve_id=BASE
    )
    initial = store.commit(snapshot(state, {}, {}, evidence=evidence), expected_head_sha256=None)
    later_store = SourceStateCheckpoint(
        tmp_path / "h5-checkpoints", account_hash=ACCOUNT, sleeve_id=H5
    )
    later_state = snapshot(
        SourceReservations(cash_type(cash=20000)), {}, {}, evidence=copy.deepcopy(evidence)
    )
    # Pre-existing empty later sleeve is an invented control, not real registration.
    later_store.commit(later_state, expected_head_sha256=None)
    positions = [dict(symbol="AAPL", qty="1", side="long", current_price="99", market_value="99")]
    orders = {cid: order}

    def books():
        return {
            task: dict(revision=_hash(st.load()), namespace=ns, snapshot=st.load()["snapshot"])
            for task, st, ns in [(BASE, store, "base"), (H5, later_store, "h5")]
        }

    before = ValidationAccountPartition.account_view(books(), H5, positions, orders, [event])
    assert not before["units_complete"] and not before["all_activities_known"]
    rt = mod.CurrentInitializationRuntime.__new__(mod.CurrentInitializationRuntime)
    initial_scope = save(
        tmp_path / "initial-account-scope.json",
        dict(broker_reported_cash_equity_nonmarginable_USD=1000000),
    )
    rt.root, rt.store, rt.task = ROOT, store, BASE
    rt.auth = dict(initial_account_scope=initial_scope, capital_usd=20000)
    rt.clock = lambda: datetime(2026, 10, 20, 16, 0, 3, tzinfo=UTC)
    rt.monotonic = lambda: 1
    rt.connect = lambda: None
    rt.save_capture = save
    rt.write_text = lambda p, text: p.write_text(text)
    jp = tmp_path / "journal.json"
    jp.write_text(json.dumps(journal))
    rt.journal = SimpleNamespace(
        receive=lambda ident: json.loads(jp.read_text()), _path=lambda ident: jp
    )
    rt.partition = SimpleNamespace(
        books=books, account_view=ValidationAccountPartition.account_view
    )
    output = tmp_path / "settle"
    output.mkdir()

    def capture(runtime, directory, **kwargs):
        directory.mkdir()
        page = save(directory / "activities-000.json", dict(synthetic=True, events=[event]))
        save(directory / "capture.json", dict(synthetic=True, authenticated=False))
        return dict(
            orders=orders,
            activities=[event],
            account=dict(equity="1000000"),
            response_clocks={"activities-000": "2026-10-20T16:00:02Z"},
            bodies={"activities-000": page},
            aggregate_positions=positions,
            aggregate_orders=orders,
            aggregate_activities=[event],
        )

    monkeypatch.setattr(mod, "capture", capture)
    result = rt.reconcile(output)
    applied = store.load()["snapshot"]
    assert result["fill_ids"] == [event["id"]] and result["fees_certified"] is False
    assert applied["pending"][cid]["filled"] == 1
    assert applied["cashbook"]["lots"]["AAPL"][0]["quantity"] == 1
    assert applied["pending"][cid]["remaining_funding"]  # Remainder/fee hold is retained.
    assert applied["evidence"]["risk"] == initial["snapshot"]["evidence"]["risk"]
    after = ValidationAccountPartition.account_view(books(), H5, positions, orders, [event])
    assert after["units_complete"] and after["all_activities_known"]
    assert after["own_activities"] == [] and after["holdings"] == []
    # The later receiver sees the newly committed earlier head, never an inferred fill.
    partition = ValidationAccountPartition.__new__(ValidationAccountPartition)
    partition.root = ROOT
    original_auth = json.loads(
        (
            ROOT
            / (
                "reports/research/program/owner-profit-delivery-plan-20261017/"
                "paper-delivery/preopen-20261020/BASE-native-session-01/authority.json"
            )
        ).read_text()
    )
    partition.binding, partition.books = original_auth["partition"], books
    obs = dict(
        other_checkpoint_hashes=after["other_checkpoint_hashes"],
        account_marked_value=99,
        account_unborrowed_available=999901,
    )
    assert partition.guard_new_risk(obs, H5) == books()
    stale = dict(obs, other_checkpoint_hashes={BASE: _hash(initial)})
    with pytest.raises(ValueError, match="other sleeve changed"):
        partition.guard_new_risk(stale, H5)
    # Real decision arithmetic with accepted saved instruction and a clearly
    # invented fresh successful observation; no consumer/model/API execution.
    later = mod.CurrentInitializationRuntime.__new__(mod.CurrentInitializationRuntime)
    later.root, later.directory, later.store, later.task = ROOT, tmp_path / "h5", later_store, H5
    later.directory.mkdir()
    later.auth = dict(task_id=H5, capital_usd=20000)
    later.clock = rt.clock
    later.current_scientific_package = normalize(saved["H5"], "H5")
    later.require_phase = lambda p: None
    later.read_guard = lambda **kw: None
    later.initialize = lambda package: None  # Already funded invented H5 control above.
    later.save_capture = save
    decision_dir = tmp_path / "later-decision"
    (decision_dir / "account").mkdir(parents=True)
    save(
        decision_dir / "account/capture.json",
        dict(synthetic=True, earlier_head=_hash(store.load())),
    )
    later.observe = lambda *a, **kw: dict(positions=[], orders={}, activities=[])
    decision = later.decide(decision_dir)
    assert decision["status"] == "evaluated_current_decision"
    assert len(json.loads((later.directory / "initial-decision.json").read_text())["requests"]) == 5
    assert store.load()["snapshot"] == applied


@pytest.mark.parametrize("expired", [None, "native", "authority"])
def test_final_get_rechecks_both_intervals_after_slot_io(monkeypatch, expired):
    from datetime import timedelta
    from types import SimpleNamespace

    from open_composer.intraday_runner import current_initialization_runtime as mod
    from open_composer.intraday_runner import current_initialization_storage as storage

    before = datetime(2026, 10, 20, 20, 9, 59, tzinfo=UTC)
    deadline = before + timedelta(seconds=1)
    instant, calls, checks = [before], [], []
    native_end = deadline if expired == "native" else deadline + timedelta(minutes=1)
    authority_end = deadline if expired == "authority" else deadline + timedelta(minutes=1)

    class Gateway:
        def __init__(self, client, **kw):
            self.client = client

            def physical(method, url, **kw):
                calls.append(instant[0])
                return SimpleNamespace(status_code=200, iter_content=lambda **kw: iter([b"{}"]))

            self._original_request = physical

    class Slots:
        def covers_get(self, *args):
            return True

        def guard_get(self):
            instant[0] = deadline + timedelta(seconds=1)

    def read_guard(**kw):
        checks.append(instant[0])
        if not before <= instant[0] < min(native_end, authority_end):
            raise ValueError("invented actual interval expired during slot I/O")

    rt = SimpleNamespace(
        gateway=None,
        trace_directory=Path("/invented/transport"),
        transport_count=0,
        transport_bytes=0,
        current_phase="settle",
        current_response=None,
        current_request=dict(name="account", endpoint="/account", params={}),
        capture_storage=SimpleNamespace(job={"capture_partial_slot": True}),
        capture_slots=Slots(),
        root=ROOT,
        auth=dict(
            authorized_at=before.isoformat(),
            expires_at=authority_end.isoformat(),
            reconciliation_after="2026-10-19T00:00:00Z",
        ),
        journal=object(),
        client_factory=lambda: object(),
        clock=lambda: instant[0],
        monotonic=lambda: 0,
        order_guard=lambda *a, **kw: None,
        cancel_window=lambda *a: None,
        prepare_trace_directory=lambda: None,
        check_trace_directory=lambda: None,
        read_guard=read_guard,
        save_capture=lambda *a: dict(path="invented", bytes=2, sha256="fixture"),
    )
    monkeypatch.setattr(mod, "CurrentBoundedGateway", Gateway)
    monkeypatch.setattr(mod, "secure_identity", lambda: ("invented",))
    monkeypatch.setattr(storage, "require_partial_room", lambda value: None)
    mod.CurrentInitializationRuntime.connect(rt)
    if expired:
        with pytest.raises(ValueError, match="interval expired"):
            rt.gateway._original_request(
                "GET", "https://paper-api.alpaca.markets/v2/account", params={}
            )
        assert calls == []
    else:
        rt.gateway._original_request(
            "GET", "https://paper-api.alpaca.markets/v2/account", params={}
        )
        assert calls == [instant[0]]
    assert checks[-1] == instant[0] > deadline


@pytest.mark.parametrize("age_seconds", [0, 16])
def test_saved_gen1_later_initialization_NAV_observe_without_opening_retag(
    tmp_path, monkeypatch, age_seconds
):
    from datetime import timedelta

    from open_composer.intraday_runner import current_initialization_runtime as mod
    from open_composer.intraday_runner.source_dispatch_journal import _hash
    from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint
    from open_composer.intraday_runner.validation_account_partition import ACCOUNT, BASE
    from tests.test_current_initialization import observation

    prior = ROOT / (
        "reports/research/program/owner-profit-delivery-plan-20261017/"
        "paper-delivery/preopen-20261020/BASE-native-session-01/authority.json"
    )
    authority = json.loads(prior.read_text())
    original = Path(authority["ledger_root"]) / "checkpoints"
    clone = tmp_path / "checkpoints"
    clone.mkdir()
    for name in ("head.json", "revision-00000000.json", "revision-00000001.json"):
        (clone / name).write_bytes((original / name).read_bytes())
    store = SourceStateCheckpoint(clone, account_hash=ACCOUNT, sleeve_id=BASE)
    before = store.load()
    before_bytes = (clone / "revision-00000001.json").read_bytes()
    assert before["generation"] == 1 and before["snapshot"]["evidence"]["risk"]["day"] is None
    now = datetime(2026, 10, 20, 16, tzinfo=UTC)
    rt = mod.CurrentInitializationRuntime.__new__(mod.CurrentInitializationRuntime)
    rt.root, rt.store = ROOT, store
    rt.auth = dict(
        capital_usd=20000,
        session_id="SIX-CURRENT-SESSION-20261020",
        authorized_at="2026-10-20T14:40:00Z",
        expires_at="2026-11-14T00:00:00Z",
    )
    rt.clock, rt.monotonic = lambda: now, lambda: 12 + age_seconds
    rt.connect = lambda: None

    def capture(runtime, directory, **kwargs):
        end = now - timedelta(seconds=age_seconds)
        obs = observation()
        obs.update(
            started_at=(end - timedelta(seconds=2)).isoformat(),
            oldest_response_at=(end - timedelta(seconds=2)).isoformat(),
            last_response_at=(end - timedelta(seconds=1)).isoformat(),
            completed_at=end.isoformat(),
            checkpoint_hash=_hash(store.load()),
            broker_clock=dict(is_open=True, timestamp=end.isoformat()),
            broker_clock_received_at=end.isoformat(),
        )
        return dict(observation=obs)

    monkeypatch.setattr(mod, "capture", capture)
    if age_seconds:
        with pytest.raises(ValueError):
            rt.observe(tmp_path / "invented-stale-account", opening=True)
        assert store.load() == before
    else:
        from contextlib import nullcontext

        from open_composer.intraday_runner.current_initialization_entry import run_phase
        from open_composer.intraday_runner.source_activity_reception import save

        rt.operation = lambda: nullcontext(rt)
        rt.entry_guard = lambda **kw: None
        rt.save_capture = save
        result = run_phase(rt, "opening", tmp_path / "later-opening-phase", {})
        assert json.loads(Path(result["path"]).read_text())["status"] == (
            "actual_initialization_NAV_recorded"
        )
        after = store.load()
        risk = after["snapshot"]["evidence"]["risk"]
        assert risk["day_open_nav"] is None
        assert risk["initialization_baseline"] == dict(
            day="2026-10-20",
            nav="20000",
            at=now.isoformat(),
            kind="prospective_initialization",
            actual_regular_opening_NAV=False,
        )
        assert risk["high_water"] == "20000" and risk["halted"] is False
        assert after["snapshot"]["cashbook"] == before["snapshot"]["cashbook"]
        assert (
            after["snapshot"]["evidence"]["allocation_flows"]
            == (before["snapshot"]["evidence"]["allocation_flows"])
        )
        rt.observe(tmp_path / "invented-risk", opening=False)
        risk_after = store.load()["snapshot"]["evidence"]["risk"]
        assert risk_after == risk
        with pytest.raises(ValueError, match="cannot be reset"):
            rt.observe(tmp_path / "invented-reset", opening=True)
        assert store.load()["snapshot"]["evidence"]["risk"] == risk
    assert (clone / "revision-00000001.json").read_bytes() == before_bytes
    assert (original / "revision-00000001.json").read_bytes() == before_bytes


def test_initialization_risk_preserves_halt_highwater_and_old_regular_opening():
    from open_composer.intraday_runner.current_initialization_controls import risk_transition

    prior = dict(
        initial_capital="10000",
        net_allocation_flows="10000",
        high_water="21000",
        day=None,
        day_open_nav=None,
        halted=True,
        killed=False,
    )
    now = datetime(2026, 10, 20, 16, tzinfo=UTC)
    observed = dict(
        verified_nav="20000", started_at="2026-10-20T15:59:58Z", completed_at=now.isoformat()
    )
    result = risk_transition(
        prior, observed, now=now, capital=20000, opening=True, initializing=True
    )
    assert result["halted"] is True and result["high_water"] == "21000"
    assert prior["day"] is None and result["day_open_nav"] is None
    with pytest.raises(ValueError, match="actual opening"):
        risk_transition(prior, observed, now=now, capital=20000, opening=True)
    regular = dict(observed, started_at="2026-10-20T13:30:01Z", completed_at="2026-10-20T13:30:03Z")
    normal = risk_transition(
        prior,
        regular,
        now=datetime(2026, 10, 20, 13, 30, 3, tzinfo=UTC),
        capital=20000,
        opening=True,
    )
    assert normal["day_open_nav"] == "20000" and "initialization_baseline" not in normal
    declined = risk_transition(result, dict(verified_nav="18900"), now=now, capital=20000)
    assert declined["halted"] is True and declined["high_water"] == "21000"
    killed = risk_transition(result, dict(verified_nav="15000"), now=now, capital=20000)
    assert killed["killed"] is True and killed["halted"] is True
