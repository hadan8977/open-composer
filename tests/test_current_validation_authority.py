"""Invented native/admission documents only; never real paper authorization."""

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest

from open_composer.intraday_runner.current_initialization_controls import ACCOUNT, ENV_PATH
from open_composer.intraday_runner.current_initialization_runtime import load_authority
from open_composer.intraday_runner.source_activity_reception import bind
from open_composer.intraday_runner.validation_account_partition import (
    BASE,
    H5,
    LSTM,
    SLOTS,
    STATE,
    slot,
)


def authority(root, task, *, three=False, six=False):
    def put(name, value):
        path = root / (name + ".json")
        path.write_text(json.dumps(value))
        return bind(path)

    directory, namespace = slot(root, task)
    main = put(
        "main-account",
        dict(owner_account_scope_bound=True, account_hash=ACCOUNT, explicit_env_path=ENV_PATH),
    )
    directive = put("pivot-owner", dict(invented=True))
    partition = put(
        "partition",
        dict(
            selected_task=LSTM if three else H5,
            selected_tasks=[BASE, H5, LSTM],
            allocation_by_task_USD={BASE: 10000, H5: 6000, LSTM: 4000}
            if three
            else {BASE: 10000, H5: 10000, LSTM: 0},
            BASE_partition_continuation={"explicitly_authorized_affected_extension": True},
            account_binding=main,
            prior_partition=put("prior-partition", {"invented": True}),
            owner_instruction=directive,
            capital=dict(
                combined_max_USD=20000,
                BASE_USD=10000,
                H5_swing_USD=6000 if three else 10000,
                LSTM_USD=4000 if three else 0,
                gross_max=1,
                no_inter_sleeve_transfer_or_borrowed_idleallocation=True,
                same_verified_isolated_account=True,
                long_cash_only=True,
            ),
        ),
    )
    if six:
        partition = put(
            "six-partition",
            dict(
                event_id="main-existing-paper-six-candidate-allocation-20261019",
                candidate_inventory=[dict(task_id=t, initial_allocation_USD=20000) for t in SLOTS],
                funding=dict(
                    selected_six_initial_allocations_total_USD=120000,
                    account_hash=ACCOUNT,
                    paper_only=True,
                    long_cash=True,
                    per_portfolio_gross_max_own_NAV_multiple=1,
                    no_cross_trial_idle_cash_lending=True,
                    no_double_reserved_account_cash_or_sale_AR=True,
                ),
                owner_directive=directive,
                supersedes_allocation_only=partition,
            ),
        )
    owner = put("owner-fixture", dict(invented=True))
    purpose = put(
        "purpose-fixture", dict(scope_authorized=True, selected_route=BASE, owner_instruction=owner)
    )
    fields = dict(
        task_id=task,
        account_hash=ACCOUNT,
        capital_usd=20000 if six else {BASE: 10000, H5: 6000, LSTM: 4000}[task] if three else 10000,
        ledger_root=str(directory),
        partition=partition,
        spec=put("spec-fixture", {}),
        policy=put("policy-fixture", {}),
        model=put("model-fixture", {}),
        scientific_acceptance=put("science-fixture", {}),
    )
    validation = put(
        "validation-fixture",
        dict(
            **fields,
            economic_only_exception=True,
            generic_promotion_or_harness_pass_claimed=False,
            owner_instruction=owner,
            Main_validation=purpose,
        ),
    )
    consumer = (
        dict(invented="not an executable actual consumer") if task in {H5, LSTM, STATE} else None
    )
    accepted = dict(
        policy=fields["policy"],
        spec=fields["spec"],
        scientific_acceptance=fields["scientific_acceptance"],
        paper_validation=validation,
        scientific_consumer=consumer,
    )
    review = put(
        "review-fixture",
        dict(
            accepted_current_runtime=True,
            reviewer="66ad4b54-ec62-400b-9a03-a29682cf58e6",
            account_hash=ACCOUNT,
            accepted_trial_bindings={task: accepted},
            code_bindings=[],
            partition=partition,
        ),
    )
    initial = put("initial-fixture", dict(captured_at_utc="2026-10-19T02:54:00+00:00"))
    value = dict(
        **fields,
        active=True,
        namespace=namespace,
        env_path=ENV_PATH,
        gross_multiple=1,
        long_cash_only=True,
        authorized_at="2026-10-19T04:00:00+00:00",
        expires_at="2026-11-14T00:00:00+00:00",
        main_scope=main,
        code_bindings=[],
        operating_acceptance=review,
        initial_account_scope=initial,
        reconciliation_after="2026-10-19T02:54:00+00:00",
        paper_validation=validation,
        scientific_consumer=consumer,
    )
    return put, value


@pytest.mark.parametrize("task", [BASE, H5])
def test_scoped_economic_exception_does_not_require_profit(task, tmp_path):
    put, value = authority(tmp_path, task)
    actual = load_authority(tmp_path, put("auth", value), datetime(2026, 10, 19, 5, tzinfo=UTC))
    assert actual == value and actual["capital_usd"] == 10000


@pytest.mark.parametrize(
    "key,value",
    [
        ("capital_usd", 20000),
        ("env_path", "/tmp/default.env"),
        ("account_hash", "0" * 64),
        ("namespace", "oldquant2"),
        ("active", "unknown"),
        ("gross_multiple", 4),
        ("long_cash_only", False),
        ("ledger_root", "/tmp/other-book"),
    ],
)
def test_account_capital_identity_isolation_refuses(tmp_path, key, value):
    put, auth = authority(tmp_path, BASE)
    original = copy.deepcopy(auth)
    auth[key] = value
    with pytest.raises(ValueError):
        load_authority(tmp_path, put("auth", auth), datetime(2026, 10, 19, 5, tzinfo=UTC))
    assert original[key] != value


def test_validation_byte_drift_and_expiry_refuse(tmp_path):
    put, auth = authority(tmp_path, BASE)
    a = put("auth", auth)
    with pytest.raises(ValueError, match="expired"):
        load_authority(tmp_path, a, datetime(2026, 11, 14, tzinfo=UTC))
    (tmp_path / "validation-fixture.json").write_text("{}")
    with pytest.raises(ValueError, match="hash changed"):
        load_authority(tmp_path, a, datetime(2026, 10, 19, 5, tzinfo=UTC))


def test_first_capacity_receipt_cannot_admit_second(tmp_path):
    from open_composer.intraday_runner.current_initialization_entry import capacity

    path = tmp_path / "receipt.json"
    path.write_text(
        json.dumps(
            dict(
                admitted=True,
                capacity_only=True,
                task_id=BASE,
                accepted_whole_route_peak_bytes=14680064,
            )
        )
    )
    job = dict(
        task_id=H5,
        whole_route_bytes=14680064,
        protected_normal_bytes=10918819017,
        terminal_bytes=65536,
        capacity_receipt=bind(path),
    )
    with pytest.raises(ValueError, match="storage scope"):
        capacity(tmp_path, job)


@pytest.mark.parametrize(
    "open_flag,age,ok",
    [
        (True, 0, True),
        (True, 15, True),
        (True, 15.000001, False),
        (True, -0.000001, False),
        (False, 0, False),
        ("unknown", 0, False),
        (1, 0, False),
    ],
)
def test_actual_market_clock_not_calendar_only(open_flag, age, ok):
    from open_composer.intraday_runner.current_initialization_controls import require_broker_open

    now = datetime(2026, 10, 19, 13, 40, tzinfo=UTC)
    o = dict(
        broker_clock=dict(timestamp=(now - timedelta(seconds=age)).isoformat(), is_open=open_flag),
        broker_clock_received_at=now.isoformat(),
    )
    if ok:
        require_broker_open(o, now)
    else:
        with pytest.raises(ValueError):
            require_broker_open(o, now)


@pytest.mark.parametrize("task,cap", [(BASE, 10000), (H5, 6000), (LSTM, 4000)])
def test_three_scopes_exact_caps_no_economic_pass(tmp_path, task, cap):
    put, value = authority(tmp_path, task, three=True)
    assert (
        load_authority(tmp_path, put("auth-three", value), datetime(2026, 10, 19, 9, tzinfo=UTC))[
            "capital_usd"
        ]
        == cap
    )
    value["capital_usd"] = 10000 if cap != 10000 else 6000
    with pytest.raises(ValueError):
        load_authority(tmp_path, put("wrong-cap", value), datetime(2026, 10, 19, 9, tzinfo=UTC))


def test_BASE_prior_validation_partition_is_preserved_only_for_bound_successor(tmp_path):
    put, old = authority(tmp_path, BASE)
    old_validation = old["paper_validation"]
    prior_partition = put(
        "old-partition-retained", json.loads((tmp_path / "partition.json").read_text())
    )
    # Retain old validation bytes under a different immutable fixture path.
    saved = json.loads((tmp_path / "validation-fixture.json").read_text())
    saved["partition"] = prior_partition
    old_validation = put("old-validation-retained", saved)
    put, new = authority(tmp_path, BASE, three=True)
    part = json.loads((tmp_path / "partition.json").read_text())
    part["prior_partition"] = prior_partition
    new["partition"] = put("new-partition", part)
    new["paper_validation"] = old_validation
    op = json.loads((tmp_path / "review-fixture.json").read_text())
    op["partition"] = new["partition"]
    op["accepted_trial_bindings"][BASE]["paper_validation"] = old_validation
    new["operating_acceptance"] = put("new-op", op)
    assert (
        load_authority(tmp_path, put("successor", new), datetime(2026, 10, 19, 9, tzinfo=UTC))
        == new
    )
    part["prior_partition"] = put("unrelated-prior", {"invented": True})
    new["partition"] = put("bad-partition", part)
    op["partition"] = new["partition"]
    new["operating_acceptance"] = put("bad-op", op)
    with pytest.raises(ValueError):
        load_authority(tmp_path, put("bad-successor", new), datetime(2026, 10, 19, 9, tzinfo=UTC))


@pytest.mark.parametrize("task", [BASE, H5, LSTM])
def test_twenty_thousand_actual_scope_each_requires_bound_admission(tmp_path, task):
    put, value = authority(tmp_path, task, six=True)
    actual = load_authority(tmp_path, put("auth", value), datetime(2026, 10, 19, 10, tzinfo=UTC))
    assert actual["capital_usd"] == 20000
    value["capital_usd"] = 20001
    with pytest.raises(ValueError):
        load_authority(tmp_path, put("bad-auth", value), datetime(2026, 10, 19, 10, tzinfo=UTC))
