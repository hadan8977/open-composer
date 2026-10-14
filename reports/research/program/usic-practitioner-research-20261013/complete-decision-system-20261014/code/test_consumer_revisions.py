"""Only the affected unknown/admission/phase/hygiene differences, no P&L."""

import json
from dataclasses import replace
from datetime import date

import consumer_admission as gate
import pytest
from decision_system import read_parameters
from frame_producer import FrameProducer
from test_decision_system import SPEC, book, frame, system


@pytest.fixture
def admitted_fixture(tmp_path, monkeypatch):
    root = tmp_path
    package = root / "package"
    package.mkdir()
    controls = root / "reports/research/control"
    controls.mkdir(parents=True)
    monkeypatch.setattr(gate, "ROOT", root)
    monkeypatch.setattr(gate, "P", package)
    monkeypatch.setattr(gate.os, "sched_getaffinity", lambda _: {0})
    for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS"):
        monkeypatch.setenv(k, "1")
    (controls / "owner-compute-hold.json").write_text(json.dumps(dict(research_paused=False)))
    (controls / "day-goal.json").write_text(
        json.dumps(
            dict(
                tasks=[
                    dict(
                        id=gate.TASK,
                        owner=gate.AUTHOR,
                        status="running_complete_task",
                    ),
                    dict(id="legacy", active_owner="f9"),
                ]
            )
        )
    )
    cases = dict(cells=[dict(cell_id=str(i)) for i in range(96)])
    (package / "consumer-cases.json").write_text(json.dumps(cases))
    impl = {
        k: []
        for k in (
            "files",
            "approved_plan",
            "science_review",
            "scientific_contracts",
            "cases",
            "input",
            "prepared_feature_prefix",
        )
    }
    (package / "consumer-implementation-manifest.json").write_text(json.dumps(impl))
    review = dict(
        verdict="approve_implementation",
        author=gate.AUTHOR,
        reviewer=gate.REVIEWER,
        economic_execution_admitted=True,
        allocation=dict(
            CPU=1,
            memory_MiB=900,
            economic_coreseconds=gate.POOL,
            runtime_feature_generation_CPU=1200,
            first_empirical_CPU=600,
        ),
        bindings=dict(implementation=gate.bind(package / "consumer-implementation-manifest.json")),
    )
    (package / "consumer-independent-review.json").write_text(json.dumps(review))
    (package / "cumulative-accounting.json").write_text(
        json.dumps(dict(new_measured_economic_CPU=0))
    )
    return root, package


def test_exact_task_owner_and_real_conflict(admitted_fixture):
    root, _ = admitted_fixture
    gate.authority()  # Canonical owner; unrelated legacy active_owner does not block.
    path = root / "reports/research/control/day-goal.json"
    day = json.loads(path.read_text())
    day["tasks"][0]["active_owner"] = "other"
    path.write_text(json.dumps(day))
    with pytest.raises(AssertionError):
        gate.authority()


def test_unique_combined_reservation_includes_inflight_and_settles_once(
    admitted_fixture, monkeypatch
):
    _, package = admitted_fixture
    gate.reserve("first", ["0"], 1200, 600)
    with pytest.raises(FileExistsError):
        gate.reserve("first", ["0"], 1200, 600)
    with pytest.raises(AssertionError):
        gate.reserve("same_grant_duplicate", ["1"], 1200, 600)
    review_path = package / "consumer-independent-review.json"
    review = json.loads(review_path.read_text())
    for i in range(1, 3):
        review["distinct_fixture_grant"] = i
        review_path.write_text(json.dumps(review))
        gate.reserve("job" + str(i), [str(i)], 1200, 600)
    review["distinct_fixture_grant"] = 3
    review_path.write_text(json.dumps(review))
    with pytest.raises(AssertionError):
        gate.reserve("job3", ["3"], 1200, 600)  # 7200 > original7176.73, even though closed usage0.
    gate.update("first", runtime_actual_CPU=1200)
    monkeypatch.setattr(gate, "usage", lambda: (100, 1250))
    gate.settle("first", "known_failed_example")
    row = gate.receipt("first")
    assert row["runtime_actual_CPU"] == 1200
    assert row["empirical_actual_CPU"] == 155 and row["charged_CPU"] == 1355
    assert (
        json.loads((package / "cumulative-accounting.json").read_text())[
            "new_measured_economic_CPU"
        ]
        == 1355
    )
    with pytest.raises(AssertionError):
        gate.settle("first", "second_charge")


def test_standalone_cannot_use_review_claim_without_current_native(admitted_fixture):
    gate.reserve("blocked", [], 1200, 600)
    gate.claim_launch("blocked", "consumer")
    with pytest.raises(AssertionError):
        gate.phase_admission("blocked", "runtime")
    # Even a superficially admitted receipt with failed native cannot start.
    gate.update("blocked", status="admitted", native=dict(status="blocked"))
    with pytest.raises(AssertionError):
        gate.phase_admission("blocked", "runtime")


def test_empirical600_counts_native_launcher_and_excludes_runtime_once(
    admitted_fixture, monkeypatch
):
    gate.reserve("phases", ["0"], 1200, 600)
    gate.update("phases", runtime_actual_CPU=1200)
    monkeypatch.setattr(gate, "usage", lambda: (100, 1210))
    observed = []
    monkeypatch.setattr(gate.resource, "setrlimit", lambda _, bounds: observed.append(bounds))
    gate.empirical_limit("phases")
    assert observed == [(584, 585)]  # 600 - launcher5 - native10, with1-second guard.


def test_hygiene_is_prefix_only_future_bad_print_cannot_delete_past():
    params = read_parameters(SPEC)
    raw = {
        "SOFI": {
            "2024-01-02": dict(o=10, h=11, l=9, c=10, v=100, vw=10),
            "2024-01-03": dict(o=10, h=11, l=9, c=10, v=100, vw=10),
            "2024-01-04": dict(o=1000, h=1100, l=900, c=1000, v=100, vw=1000),
        }
    }
    producer = FrameProducer(params, dict(raw=raw), [], [])
    before = producer._daily_history("SOFI", date(2024, 1, 4))
    assert len(before) == 2 and all(d.close == 10 for d in before)
    after = producer._daily_history("SOFI", date(2024, 1, 5))
    assert len(after) == 1 and after[0].close == 1000
    assert len(before) == 2  # Later default last-break never rewrites the old decision prefix.


def test_split_trigger_blocks_entry_but_preserves_actual_holding_exit():
    assert system().step(replace(frame(), trigger_price_eligible=False), book()) == []
    policy = system()
    entry = policy.step(frame(), book())[0]
    policy.entry_report(
        "SOFI",
        entry.eligible_after,
        filled=True,
        price=10,
        quantity=entry.quantity,
        order_id=entry.id,
        report_id="inert-hygiene-fill",
        terminal=True,
        cancelled_quantity=0,
    )
    later = replace(
        frame(),
        start=entry.eligible_after,
        end=entry.eligible_after + __import__("datetime").timedelta(minutes=1),
        trigger_price_eligible=False,
        trail_daily_close=9,
        trail_daily_ema9=10,
    )
    exits = policy.step(later, book())
    assert len(exits) == 1 and exits[0].reason == "completed_daily_trend_failure"
