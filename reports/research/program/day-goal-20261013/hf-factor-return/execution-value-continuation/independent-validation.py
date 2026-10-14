"""Independent bounded metadata checks and decisive synthetic probes; no market run."""

import ast
import hashlib
import json
import os
import pickle
import resource
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

P = Path(__file__).resolve().parent
ROOT = Path.cwd()
sys.dont_write_bytecode = True
sys.path.insert(0, str(P))
from hf_execution_policy import (  # noqa: E402
    POLICIES,
    dynamic_first_action,
    run_policy_book,
    variance_before_day,
)


def load(path):
    return json.loads(path.read_text())


def binding(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def calendar(n):
    result = []
    current = date(2017, 1, 3)
    while len(result) < n:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def flat_inputs(dates):
    days = [{"date": d, "regular15_windows": 26} for d in dates]
    bars = {
        d: {k: {"open": 100.0, "close": 100.0, "first_price_age_minutes": 0} for k in range(26)}
        for d in dates
    }
    return days, bars, {d: 100.0 for d in dates}


def main():
    assert len(os.sched_getaffinity(0)) == 1
    resource.setrlimit(resource.RLIMIT_CPU, (75, 76))
    checked_at = datetime.now(UTC).isoformat()
    handoff = load(P / "implementation-review-handoff.json")
    checked, mismatch = [], []
    for value in handoff.values():
        if isinstance(value, dict) and {"path", "sha256", "bytes"} <= value.keys():
            actual = binding(ROOT / value["path"])
            checked.append(actual)
            if actual != value:
                mismatch.append({"expected": value, "actual": actual})
    implementation = load(P / "implementation-manifest.json")
    for row in implementation["files"]:
        if row["path"].endswith((".py", ".md")):
            actual = binding(ROOT / row["path"])
            checked.append(actual)
            if actual != row:
                mismatch.append({"expected": row, "actual": actual})
    for name in (
        "scientific-plan.json",
        "scientific-plan-v1.md",
        "candidate-manifest-proposed.json",
    ):
        checked.append(binding(P / name))
    approval = load(P / "independent-plan-review-root-v1.json")
    # Mutable cumulative accounting is deliberately not compared to the earlier
    # plan review's historical ledger snapshot.
    for row in approval["bindings_verified"]:
        if Path(row["path"]).name in (
            "scientific-plan.json",
            "scientific-plan-v1.md",
            "candidate-manifest-proposed.json",
        ):
            actual = binding(ROOT / row["path"])
            if actual != row:
                mismatch.append({"expected": row, "actual": actual})

    receipt = ET.parse(P / "implementation-tests-03.xml").getroot().find("testsuite")
    test_names = [r.attrib["name"] for r in receipt.findall("testcase")]
    reused_tests = {
        "tests": int(receipt.attrib["tests"]),
        "failures": int(receipt.attrib["failures"]),
        "errors": int(receipt.attrib["errors"]),
        "skipped": int(receipt.attrib["skipped"]),
        "DP_exhaustive_cases": sum(name.startswith("test_DP_first_action") for name in test_names),
        "ZERO_cases": sum(name.startswith("test_complete_synthetic_ZERO") for name in test_names),
        "rerun": False,
    }
    assert reused_tests["tests"] == 33 and reused_tests["failures"] == reused_tests["errors"] == 0

    proposal = load(P / "candidate-manifest-proposed.json")
    full = load(P / "full-run-launch-manifest.json")
    ids = [r["candidate_id"] for r in proposal["candidates"]]
    assert len(ids) == len(set(ids)) == 60
    assert all(r["promotion_eligible"] is False for r in proposal["candidates"])
    expected20 = {(i, c, 20000) for i in ids for c in (20, 40)}
    actual20 = {
        (r["candidate_id"], r["cost_bps_each_side"], r["capital_USD"])
        for r in full["fixed20k_views"]
    }
    ids4 = [r["candidate_id"] for r in proposal["candidates"] if r["optional_independent_4k_views"]]
    expected4 = {(i, c, 4000) for i in ids4 for c in (20, 40)}
    actual4 = {
        (r["candidate_id"], r["cost_bps_each_side"], r["capital_USD"])
        for r in full["conditional4k_views"]
    }
    assert actual20 == expected20 and len(full["fixed20k_views"]) == 120
    assert actual4 == expected4 and len(full["conditional4k_views"]) == 36
    inputs = load(P / "execution-input-manifest.json")
    qa = load(P / "execution-input-QA.json")
    assert inputs["input_QA"] == binding(P / "execution-input-QA.json")
    assert inputs["new_compact_packet"] in inputs["actual_financial_read_inputs"]
    actual_bindings = {r["path"]: r for r in inputs["actual_financial_read_inputs"]}
    impl_bindings = {r["path"]: r for r in implementation["files"]}
    assert all(impl_bindings[r["path"]] == r for r in inputs["actual_financial_read_inputs"])
    assert len(actual_bindings) == 16 and len(inputs["original_source_inputs"]) == 3
    assert qa["future_label_mask_used_to_select_current_rows"] is False
    # Actual market/prediction arrays and old account ledgers are neither decoded
    # nor rehashed here. This check reuses the bound actual author input QA.
    input_check = {
        "small_manifest_consistency": True,
        "financial_read_input_bindings": len(actual_bindings),
        "actual_input_hash_QA_reused": True,
        "new_original_input_hashes": 0,
        "market_rows_decoded": 0,
        "physical_packet_rows_in_reused_QA": qa["physical_packet_rows_retained"],
        "legal_decision_rows_in_reused_QA": qa["current_legal_rows"],
        "current_vintage_PIT_certified": qa["source_current_vintage_PIT_certified"],
        "late_first_references_in_reused_QA": sum(
            r["late_first_references"] for r in qa["price_QA"]
        ),
    }

    # Decisive counterexample: the account rejects a late reference, but its risk
    # history currently accepts that same incomplete scheduled interval.
    eligible = calendar(40)
    dates = eligible[:32]
    days, bars, marks = flat_inputs(dates)
    late_day = dates[-1]
    bars[late_day][5].update(close=150.0, first_price_age_minutes=1)
    captures = []
    run_policy_book(
        days,
        bars,
        marks,
        {},
        [],
        eligible,
        POLICIES["CONT_H1_SLOW"],
        0,
        0.002,
        on_complete_day=lambda state: captures.append(pickle.dumps(state)),
    )
    late_state = pickle.loads(captures[-1])
    history = late_state["return_history"]
    actual_var = variance_before_day(history, eligible[32])
    valid_history = {d: v for d, v in history.items() if d != late_day}
    expected_var = variance_before_day(valid_history, eligible[32])
    actual_action = dynamic_first_action(0, 0, (0.005,), (actual_var,), 0.002)[0]
    expected_action = dynamic_first_action(0, 0, (0.005,), (expected_var,), 0.002)[0]
    assert late_day in history and len(valid_history) == 30
    assert actual_var > expected_var and actual_action != expected_action
    late_risk = {
        "counterexample_confirmed": True,
        "late_reference_session_admitted_to_risk": True,
        "actual_variance": actual_var,
        "complete_sessions_only_variance": expected_var,
        "actual_first_action": actual_action,
        "complete_sessions_only_first_action": expected_action,
        "fixed_mu": 0.005,
        "late_interval_session_exposure_recorded_as": late_state["exposure"][late_day],
        "incomplete_session_exposure_required": None,
    }

    # A richer checkpoint than the reused all-hold test: actual synthetic buys,
    # partial/whole reductions, unsettled sales, dividends, and an active outage.
    dates = eligible[:8]
    days, bars, marks = flat_inputs(dates)
    scores = {(dates[1], m): 0.02 for m in range(630, 945, 15)}
    scores[(dates[2], 630)] = -0.02
    actions = [
        {
            "type": "cash_dividends",
            "symbol": "SPY",
            "ex_date": dates[2],
            "payable_date": dates[5],
            "amount": 0.5,
            "id": "review-synthetic-dividend",
        }
    ]
    checkpoint = {}

    def capture(state):
        if state["next_day_index"] == 3:
            checkpoint["bytes"] = pickle.dumps(state)

    args = (days, bars, marks, scores, actions, eligible, POLICIES["DP_H16_SLOW"], 0, 0.002)
    uninterrupted = run_policy_book(*args, capital=2000, on_complete_day=capture)
    state = pickle.loads(checkpoint["bytes"])
    assert state["book"].unsettled and state["book"].dividends
    assert state["missing"].consecutive >= 4 and state["book"].orders
    missing_at_checkpoint = state["missing"].consecutive
    risk_rows_at_checkpoint = len(state["return_history"])
    resumed = run_policy_book(*args, capital=2000, resume_state=state)
    assert resumed == uninterrupted
    rich_resume = {
        "entire_result_equal": True,
        "checkpoint_keys": sorted(state),
        "unsettled_receivables_nonempty": True,
        "dividend_receivables_nonempty": True,
        "outage_count_at_checkpoint": missing_at_checkpoint,
        "historical_risk_rows": risk_rows_at_checkpoint,
        "serialized_bytes": len(checkpoint["bytes"]),
    }

    # Invoke the exact producer's nested persistence callback on synthetic state,
    # without calling one_book, loading market inputs or financial admission.
    runner_tree = ast.parse((P / "run_execution_accounts.py").read_text())
    runner = next(
        n for n in runner_tree.body if isinstance(n, ast.FunctionDef) and n.name == "one_book"
    )
    callback = next(
        n for n in runner.body if isinstance(n, ast.FunctionDef) and n.name == "save_checkpoint"
    )
    module = ast.Module(body=[callback], type_ignores=[])
    with tempfile.TemporaryDirectory(prefix="hf-review-synthetic-") as tmp:
        checkpoint_path = Path(tmp) / "synthetic.checkpoint.pkl"
        namespace = {
            "pickle": pickle,
            "checkpoint": checkpoint_path,
            "days": [None] * 1259,
            "input_id": {"synthetic": True},
        }
        exec(compile(module, str(P / "run_execution_accounts.py"), "exec"), namespace)
        namespace["save_checkpoint"]({"next_day_index": 2, "synthetic": True})
        saved_on_day2 = checkpoint_path.exists()
        namespace["save_checkpoint"]({"next_day_index": 64, "synthetic": True})
        saved_on_day64 = checkpoint_path.exists()
        assert not saved_on_day2 and saved_on_day64
    identity_assign = next(
        n
        for n in runner.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "input_id" for t in n.targets)
    )
    identity_keys = [ast.literal_eval(k) for k in identity_assign.value.keys]
    checkpoint_writer = {
        "actual_day2_written": saved_on_day2,
        "actual_day64_written": saved_on_day64,
        "daily_checkpoint_contract_met": False,
        "resume_identity_keys": identity_keys,
        "inherited_cash_action_code_bound_in_resume_identity": False,
        "neutral_exposure_input_bound_in_resume_identity": False,
    }

    from open_composer.research.iteration_dossier import (
        _campaign_requirement_blockers,
        _lightweight_single_mechanism_exempt,
    )

    search = load(
        ROOT / "reports/research/iterations/t20261014_hf_execution_value/search-space.json"
    )
    native = _campaign_requirement_blockers(
        search, registered_campaign_ids=[], campaign_bound=False
    )
    assert native == ["campaign_contract_required_for_new_iteration"]
    assert not _lightweight_single_mechanism_exempt(search, campaign_bound=False)

    usage = resource.getrusage(resource.RUSAGE_SELF)
    output = {
        "checked_at_utc": checked_at,
        "bindings_checked": checked,
        "mismatches": mismatch,
        "reused_actual_tests": reused_tests,
        "inventory": {
            "identities": 60,
            "kinds": dict(Counter(r["kind"] for r in proposal["candidates"])),
            "policies": dict(Counter(r["policy"]["policy_id"] for r in proposal["candidates"])),
            "twenty_k_views": 120,
            "conditional_four_k_views": 36,
            "all_nonpromotable": True,
            "manifest_inventory_exact": True,
        },
        "input_binding_limits": input_check,
        "late_reference_risk_counterexample": late_risk,
        "rich_state_resume": rich_resume,
        "exact_producer_checkpoint_probe": checkpoint_writer,
        "actual_native_campaign_requirement": native,
        "economic_runs": 0,
        "market_or_model_arrays_loaded": 0,
        "native_full_gate_reruns": 0,
        "new_training_or_inference": 0,
        "CPU_seconds": usage.ru_utime + usage.ru_stime,
        "max_RSS_KiB": usage.ru_maxrss,
        "affinity": sorted(os.sched_getaffinity(0)),
    }
    (P / "independent-validation.json").write_text(
        json.dumps(output, indent=2, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {k: v for k, v in output.items() if k not in ("bindings_checked",)}, allow_nan=False
        )
    )
    assert not mismatch


if __name__ == "__main__":
    main()
