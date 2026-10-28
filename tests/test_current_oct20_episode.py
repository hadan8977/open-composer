"""Finite Oct20 continuation fixtures; no broker/source/scientific invocation."""

import copy
from datetime import UTC, datetime

import pytest

from open_composer.intraday_runner import current_initialization_storage as storage
from open_composer.intraday_runner.current_initialization_controls import (
    ACCOUNT,
    DAY,
    identity,
    require_phase,
    session,
)
from open_composer.intraday_runner.current_initialization_episode import (
    MAIN_SHA,
    adopt_empty_funding_episode,
    normalize_received,
    receive_day,
)
from open_composer.intraday_runner.current_initialization_funding import (
    MAIN_SHA as FUNDING_SHA,
)
from open_composer.intraday_runner.current_initialization_funding import funding_snapshot
from open_composer.intraday_runner.validation_account_partition import BASE
from scripts.rebind_current_validation_code import unchanged_scope
from tests.test_current_funding_flow import context


def component(policy="BASE"):
    count = {"BASE": 27, "H5": 31, "LSTM": 10, "BASE_STATE_BUDGET": 27}[policy]
    symbols = [f"S{i}" for i in range(count)]
    return dict(
        task_id="CURRENT-PAPER-SCIENCE-20261020",
        policy=policy,
        episode_day="2026-10-20",
        application_day="2026-10-20",
        reference_day="2026-10-19",
        capital_USD=20000,
        operating_authority=False,
        targets_are_holdings_or_orders=False,
        symbols=symbols,
        weights=[0.2] * 5 + [0] * (count - 5),
        raw_reference_marks=dict.fromkeys(symbols, 100),
        consume_before="2026-10-20T13:41:00Z",
        dispatch_window=["2026-10-20T13:40:00Z", "2026-10-20T13:41:00Z"],
        holding_authority_cap="2026-11-14T00:00:00Z",
        computation_started_at="2026-10-20T11:00:00Z",
        computation_completed_at="2026-10-20T11:01:00Z",
        published_at="2026-10-20T11:01:01Z",
        completed_at="2026-10-20T11:01:02Z",
        K=5,
        cash_cause="fixture",
        package={"sha256": "new-package"},
        review={"sha256": "new-review"},
        source={"sha256": "new-source"},
        source_complete={"sha256": "new-source-complete"},
    )


def test_current_session_conversion_and_old_date_refusal():
    assert DAY.isoformat() == "2026-10-20"
    assert [x.isoformat() for x in session(DAY)] == [
        "2026-10-20T13:30:00+00:00",
        "2026-10-20T20:00:00+00:00",
    ]
    args = ("2026-10-20T00:00:00Z", "2026-11-14T00:00:00Z")
    require_phase("2026-10-20T13:40:00Z", "buy", *args)
    require_phase("2026-10-20T13:29:59Z", "decision", *args)
    for at, phase in [
        ("2026-10-19T13:40:00Z", "buy"),
        ("2026-10-20T13:41:00Z", "buy"),
        ("2026-10-21T13:40:00Z", "buy"),
        ("2026-10-20T13:30:00Z", "decision"),
    ]:
        with pytest.raises(ValueError):
            require_phase(at, phase, *args)
    identity("basecur-20261019-fa6147de-1020-buy-CRM", "CRM", "buy")
    with pytest.raises(ValueError):
        identity("basecur-20261019-fa6147de-1019-buy-CRM", "CRM", "buy")


@pytest.mark.parametrize("policy", ["BASE", "H5", "LSTM", "BASE_STATE_BUDGET"])
def test_mapping_only_preserves_order_signed_metadata_and_weights(policy):
    value = component(policy)
    value["stock_scores"] = [-1] * len(value["symbols"])
    before = copy.deepcopy(value)
    got = normalize_received(value, policy)
    assert value == before
    assert got["forecast"]["symbols"] == value["symbols"]
    assert got["forecast"]["weights"] == value["weights"]
    assert got["received_scientific_component"]["stock_scores"] == value["stock_scores"]
    assert got["runtime_K_rank_weight_recalculation"] is False


@pytest.mark.parametrize(
    "key,value",
    [
        ("reference_day", "2026-10-16"),
        ("application_day", "2026-10-19"),
        ("consume_before", "2026-10-19T13:41:00Z"),
        ("completed_at", "2026-10-20T13:30:00Z"),
        ("operating_authority", True),
        ("K", True),
    ],
)
def test_dated_or_unreceived_component_refuses(key, value):
    data = component()
    data[key] = value
    with pytest.raises(ValueError):
        normalize_received(data, "BASE")


def test_empty_funding_adoption_preserves_predecessor_and_flow():
    current, obs, _ = context()
    current["snapshot"]["evidence"].update(
        scientific_package_sha256="old-sealed-package", actions_observation_day="2026-10-19"
    )
    from open_composer.intraday_runner.source_dispatch_journal import _hash

    obs["checkpoint_hash"] = _hash(current)
    before = copy.deepcopy(current)
    now = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)  # Pure old-state fixture clock.
    proposed = funding_snapshot(
        current,
        obs,
        now=now,
        monotonic=1,
        account_hash=ACCOUNT,
        main={"sha256": FUNDING_SHA},
        capture_binding={"sha256": "fixture-capture"},
    )
    package = normalize_received(component(), "BASE")
    authority = dict(
        task_id=BASE,
        application_day="2026-10-20",
        scientific_acceptance=package["received_scientific_component"]["review"],
        current_day_selection={"sha256": MAIN_SHA},
    )
    got = adopt_empty_funding_episode(proposed, current, package, authority)
    assert current == before
    assert got["cashbook"]["cash"] == 20000
    assert got["evidence"]["allocation_flows"] == proposed["evidence"]["allocation_flows"]
    assert got["evidence"]["allocation_flows"][0]["profit_USD"] == "0"
    assert got["evidence"]["episode_continuations"][0]["prior_scientific_package_sha256"] == (
        "old-sealed-package"
    )
    replay = dict(current, generation=1, snapshot=got)
    with pytest.raises(ValueError):
        adopt_empty_funding_episode(got, replay, package, authority)
    changed = copy.deepcopy(current)
    changed["snapshot"]["consumed_ids"] = ["unknown-order"]
    with pytest.raises(ValueError):
        adopt_empty_funding_episode(proposed, changed, package, authority)


def test_scope_extension_is_narrow_and_funding_only():
    old = dict(
        code_bindings=[1],
        operating_acceptance=1,
        partition=1,
        capital_usd=10000,
        policy=1,
        spec=1,
        paper_validation=1,
        scope_note="old",
        scientific_acceptance=1,
        authorized_at="old",
        expires_at="immutable",
        namespace="immutable",
        model="immutable",
    )
    new = dict(
        old,
        code_bindings=[2],
        scientific_acceptance=2,
        authorized_at="current",
        current_day_selection={},
        application_day="2026-10-20",
        reference_day="2026-10-19",
        scientific_consumer={},
    )
    unchanged_scope(old, new, allow_funding=True, allow_current_episode=True)
    for key in ("expires_at", "namespace", "model"):
        with pytest.raises(ValueError):
            unchanged_scope(
                old,
                dict(new, **{key: "changed"}),
                allow_funding=True,
                allow_current_episode=True,
            )
    with pytest.raises(ValueError):
        unchanged_scope(old, new, allow_current_episode=True)


def test_actual_day_selection_wrong_digest_refuses(tmp_path):
    from open_composer.intraday_runner.source_activity_reception import save

    selection = save(tmp_path / "selection.json", {"owner_directive": {"sha256": "x"}})
    with pytest.raises(ValueError):
        receive_day(tmp_path, dict(current_day_selection=selection))


@pytest.mark.parametrize("mode", ["accepted", "foreign_module", "wrong_review", "post_drift"])
def test_exact_consumer_callback_boundaries(tmp_path, monkeypatch, mode):
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    from open_composer.intraday_runner.current_initialization_episode import (
        FOLDER,
        REVIEWER,
        receive,
    )
    from open_composer.intraday_runner.source_activity_reception import bind, save

    folder = tmp_path / FOLDER
    folder.mkdir(parents=True)
    consumer = folder / "current_paper_consumer.py"
    consumer.write_text("# invented callback fixture; no scientific execution\n")
    spec = dict(consumer=bind(consumer))
    for key, name, value in [
        ("schema", "consumer-schema.json", {}),
        ("contract", "prospective-contract.json", {}),
        ("manifest", "implementation-manifest.json", {"files": [bind(consumer)]}),
        ("package", "BASE/current-package.json", {"forecast": {"sha256": "fixture"}}),
        ("final", "BASE/final-manifest.json", {}),
    ]:
        spec[key] = save(folder / name, value)
    review = save(
        folder / "independent-BASE-result-review.json",
        dict(
            task_id="CURRENT-PAPER-SCIENCE-20261020",
            policy="BASE",
            reviewer=REVIEWER,
            verdict="approve_result",
            component_result_accepted=mode != "wrong_review",
            target=spec["final"],
        ),
    )
    main = Path("/root/codex-test/open-composer/reports/research/program/owner-resume-20261020")
    authority = dict(
        task_id=BASE,
        current_day_selection=bind(main / "main-resume-and-day-selection.json"),
        application_day="2026-10-20",
        reference_day="2026-10-19",
        scientific_consumer=spec,
        scientific_acceptance=review,
    )
    called = []

    def callback(path, *, for_execution):
        called.append((path, for_execution))
        if mode == "post_drift":
            consumer.write_text("# changed during callback\n")
        return dict(
            component(),
            review=review,
            package=spec["package"],
            final=spec["final"],
            consumer=spec["consumer"],
            schema=spec["schema"],
            forecast={"sha256": "fixture"},
        )

    monkeypatch.setitem(
        sys.modules,
        "current_paper_consumer",
        SimpleNamespace(
            __file__=str(consumer if mode != "foreign_module" else tmp_path / "foreign.py"),
            receive_current_package=callback,
        ),
    )
    if mode == "accepted":
        result = receive(tmp_path, authority, clock=lambda: datetime(2026, 10, 20, 12, tzinfo=UTC))
        assert result["forecast"]["weights"] == component()["weights"]
        assert called == [(spec["package"]["path"], True)]
    else:
        with pytest.raises(ValueError):
            receive(tmp_path, authority, clock=lambda: datetime(2026, 10, 20, 12, tzinfo=UTC))
        assert bool(called) == (mode == "post_drift")


def test_current_capacity_full_other_commitments_and_missing_sip(monkeypatch, tmp_path):
    import json
    from pathlib import Path
    from types import SimpleNamespace

    root = Path("/root/codex-test/open-composer")
    disk = root / "reports/ops/disk-audit-20261015"
    from open_composer.intraday_runner.source_activity_reception import bind

    receipt = bind(disk / "capacity-current-day16route-post-owner-cleanup-admission-20261020.json")
    actual = json.loads(Path(receipt["path"]).read_text())
    job = dict(
        capacity_receipt=receipt,
        whole_route_bytes=94044160,
        protected_normal_bytes=10918819017,
        terminal_bytes=65536,
        owned_roots=actual["guard_contract"]["required_roots"],
        concurrent_SIP_capacity=bind(disk / "capacity-SIP-daily1GiB-stage-admission-20261020.json"),
        concurrent_CASH_capacity=bind(
            disk / "capacity-CASH12MiB-post-owner-cleanup-admission-20261020.json"
        ),
        current_normal_forecast=actual["concurrent_protected_commitments"]["complete_normal"][
            "receipt"
        ],
    )
    monkeypatch.setattr(storage, "allocated_bytes", lambda roots: 0)
    required = sum([10918819017, 65536, 12288, 94044160, 12582912, 1073741824])
    monkeypatch.setattr(
        storage.os, "statvfs", lambda p: SimpleNamespace(f_bavail=required, f_frsize=1)
    )
    capacity = storage.capacity(root, job)
    assert capacity["remaining_current"] == 94044160 - 3 * 1024**2
    assert capacity["remaining_physical_demand"] == 94044160
    assert capacity["outside_uncredited_reserve"] == 3 * 1024**2
    monkeypatch.setattr(
        storage.os, "statvfs", lambda p: SimpleNamespace(f_bavail=required - 1, f_frsize=1)
    )
    with pytest.raises(ValueError):
        storage.capacity(root, job)
    # A newly received complete normal forecast may only increase the floor.
    # Its exact binding is part of native scope and the funding plan, not a
    # mutable guess or a reinterpretation of the old capacity receipt.
    from open_composer.intraday_runner.source_activity_reception import save

    normal = json.loads(Path(job["current_normal_forecast"]["path"]).read_text())
    normal["required_available_bytes"] += 4096
    job["current_normal_forecast"] = save(tmp_path / "larger-normal.json", normal)
    job["protected_normal_bytes"] = normal["required_available_bytes"]
    with pytest.raises(ValueError):
        storage.capacity(root, job)
    monkeypatch.setattr(
        storage.os, "statvfs", lambda p: SimpleNamespace(f_bavail=required + 4096, f_frsize=1)
    )
    assert storage.capacity(root, job)["outside_uncredited_reserve"] == 3 * 1024**2
    job["protected_normal_bytes"] = 10918819016
    with pytest.raises(ValueError):
        storage.capacity(root, job)
    job["protected_normal_bytes"] = normal["required_available_bytes"]
    del job["concurrent_SIP_capacity"]
    with pytest.raises(KeyError):
        storage.capacity(root, job)


@pytest.mark.parametrize("task_name", ["BASE", "H5", "LSTM", "STATE"])
def test_current_authority_constructor_and_old_episode_refusal(tmp_path, task_name):
    import json
    from pathlib import Path

    from open_composer.intraday_runner import validation_account_partition as partition
    from open_composer.intraday_runner.current_initialization_runtime import (
        CurrentInitializationRuntime,
        load_authority,
    )
    from open_composer.intraday_runner.source_activity_reception import bind, save
    from tests.test_current_validation_authority import authority as invented_authority

    task = getattr(partition, task_name)
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    put, value = invented_authority(tmp_path, task, six=True)
    old = put("old-authority", value)
    # The fixture helper only creates invented records; no account or native.
    with pytest.raises(KeyError):
        load_authority(tmp_path, old, now)
    value = json.loads(Path(old["path"]).read_text())
    selected = Path(
        "/root/codex-test/open-composer/reports/research/program/owner-resume-20261020/"
        "main-resume-and-day-selection.json"
    )
    extra = dict(
        application_day="2026-10-20",
        reference_day="2026-10-19",
        current_day_selection=bind(selected),
    )
    value.update(extra)
    value["scientific_consumer"] = {"invented": "no callable"}
    validation = json.loads(Path(value["paper_validation"]["path"]).read_text())
    validation.update(extra)
    value["paper_validation"] = save(tmp_path / "current-validation.json", validation)
    review = json.loads(Path(value["operating_acceptance"]["path"]).read_text())
    review.update(
        accepted_current_day_continuation=True, current_day_selection=extra["current_day_selection"]
    )
    review["accepted_trial_bindings"][task].update(
        application_day=extra["application_day"],
        reference_day=extra["reference_day"],
        scientific_consumer=value["scientific_consumer"],
        paper_validation=value["paper_validation"],
    )
    value["operating_acceptance"] = save(tmp_path / "current-review.json", review)
    current = save(tmp_path / "current-authority.json", value)
    rt = CurrentInitializationRuntime(
        tmp_path, current, entry_guard=lambda **kw: None, clock=lambda: now
    )
    assert rt.gateway is None
    assert not rt.directory.exists()
    review["accepted_current_day_continuation"] = False
    value["operating_acceptance"] = save(tmp_path / "denied-review.json", review)
    refused = save(tmp_path / "denied-authority.json", value)
    with pytest.raises(ValueError):
        load_authority(tmp_path, refused, now)
