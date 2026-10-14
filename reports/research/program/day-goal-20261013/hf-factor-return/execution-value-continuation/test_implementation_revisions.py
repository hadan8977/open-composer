"""R1–R3 minimum synthetic acceptance, using the real producer persistence code."""

import json
import pickle
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

P = Path(__file__).resolve().parent
sys.path.insert(0, str(P))
from hf_execution_policy import (  # noqa: E402
    POLICIES,
    dynamic_first_action,
    future_mu,
    neutral_weight_before_day,
    run_policy_book,
    variance_before_day,
)
from run_execution_accounts import checkpoint_writer, load_checkpoint, resume_identity  # noqa: E402


def synthetic_inputs(count=40):
    dates = [str(date(2017, 1, 1) + timedelta(days=i)) for i in range(count + 10)]
    days = [{"date": d, "regular15_windows": 26} for d in dates[:count]]
    bars = {
        d: {
            k: {
                "open": 100.0,
                "close": 100.0,
                "first_price_age_minutes": 0,
                "last_price_age_to_window_end_minutes": 0,
            }
            for k in range(26)
        }
        for d in dates[:count]
    }
    marks = {d: 100.0 for d in dates[:count]}
    return days, bars, marks, dates


def run_synthetic(days, bars, marks, eligible, scores=None, actions=None, callback=None):
    return run_policy_book(
        days,
        bars,
        marks,
        scores or {},
        actions or [],
        eligible,
        POLICIES["DP_H16_SLOW"],
        0,
        0.002,
        capital=2000,
        on_complete_day=callback,
    )


@pytest.mark.parametrize(
    "damage",
    [
        "late_open",
        "missing_open",
        "open_age_unknown",
        "late_close",
        "missing_close",
        "close_age_unknown",
        "wrong_ordinal",
    ],
)
def test_incomplete_endpoints_do_not_certify_risk_and_start_unknown_is_not_zero(damage):
    days, bars, marks, eligible = synthetic_inputs(3)
    day = days[-1]["date"]
    row = bars[day][5]
    if damage == "late_open":
        row["first_price_age_minutes"] = 1
    elif damage == "missing_open":
        row.pop("open")
    elif damage == "open_age_unknown":
        row.pop("first_price_age_minutes")
    elif damage == "late_close":
        row["last_price_age_to_window_end_minutes"] = 1
    elif damage == "missing_close":
        row.pop("close")
    elif damage == "close_age_unknown":
        row.pop("last_price_age_to_window_end_minutes")
    else:
        bars[day][26] = bars[day].pop(5)  # Same count cannot replace scheduled k=5.
    snapshots = []
    run_synthetic(
        days, bars, marks, eligible, callback=lambda state: snapshots.append(pickle.dumps(state))
    )
    state = pickle.loads(snapshots[-1])
    assert day not in state["return_history"]
    assert variance_before_day(state["return_history"], eligible[3]) == 0.004**2
    bad_start = damage in {"late_open", "missing_open", "open_age_unknown", "wrong_ordinal"}
    assert state["exposure"][day] is None if bad_start else state["exposure"][day] == 0


def test_original_late_reference_counterexample_fixed_without_changing_frozen_policy():
    days, bars, marks, eligible = synthetic_inputs(32)
    late = days[-1]["date"]
    bars[late][5].update(close=150.0, first_price_age_minutes=1)
    snapshots = []
    run_synthetic(
        days, bars, marks, eligible, callback=lambda state: snapshots.append(pickle.dumps(state))
    )
    state = pickle.loads(snapshots[-1])
    assert late not in state["return_history"] and len(state["return_history"]) == 30
    assert state["exposure"][late] is None
    fixed_var = variance_before_day(state["return_history"], eligible[32])
    assert fixed_var == 0
    # Retain the old failure numerically; no rerun of an old real account or source.
    old_var = 0.5**2 / (31 * 26)
    assert old_var == pytest.approx(0.00031017369727047146)
    assert dynamic_first_action(0, 0, (0.005,), (old_var,), 0.002)[0] == 0.25
    assert dynamic_first_action(0, 0, (0.005,), (fixed_var,), 0.002)[0] == 1
    policy = POLICIES["DP_H16_SLOW"]
    mu = future_mu(0.001, policy.rho, 16)
    assert dynamic_first_action(0, 0, mu, (old_var,) * 16, 0.002)[0] == 0
    assert dynamic_first_action(0, 0, mu, (fixed_var,) * 16, 0.002)[0] == 1
    # Incomplete days stay in the exposure calendar instead of being skipped.
    exposure = {str(date(2016, 1, 1) + timedelta(days=i)): 0.4 for i in range(62)}
    exposure[late] = state["exposure"][late]
    assert neutral_weight_before_day(exposure, eligible[32], 0.97) == 0.97


def identity_fixture(tmp_path, neutral=False):
    row = {
        "candidate_id": "DP_H16_SLOW__PLS_IDX_CTS__B0",
        "policy": {"policy_id": "DP_H16_SLOW"},
        "kind": "fixed_policy_information_configuration",
    }
    inputs = tmp_path / "inputs.json"
    inputs.write_text('{"synthetic":true}')
    code = {name: tmp_path / f"{name}.py" for name in ("policy", "cash_actions", "producer")}
    for name, path in code.items():
        path.write_text(f"# synthetic {name}\n")
    matched = None
    if neutral:
        row["candidate_id"] = "DP_H16_SLOW__NEUTRAL_PLS_IDX_CTS__B0"
        row["kind"] = "causal_prior63session_exposure_control"
        matched = tmp_path / "matched.json"
        matched.write_text(
            json.dumps(
                {
                    "candidate_id": "DP_H16_SLOW__PLS_IDX_CTS__B0",
                    "initial": 2000,
                    "cost_each_side": 0.002,
                    "daily_regular_exposure": {"2017-01-02": 0.4},
                }
            )
        )
    return row, inputs, code, matched


def test_actual_daily_writer_is_readable_at_day2_and_rich_interruption_resumes(tmp_path):
    days, bars, marks, eligible = synthetic_inputs(8)
    dates = [row["date"] for row in days]
    scores = {(dates[1], m): 0.02 for m in range(630, 945, 15)}
    scores[(dates[2], 630)] = -0.02
    actions = [
        {
            "type": "cash_dividends",
            "symbol": "SPY",
            "ex_date": dates[2],
            "payable_date": dates[5],
            "amount": 0.5,
            "id": "synthetic",
        }
    ]
    row, inputs, code, _ = identity_fixture(tmp_path)
    identity, history = resume_identity(row, 20, 2000, inputs, code_paths=code)
    assert history is None and identity["matched_exposure_input"] is None
    path = tmp_path / "actual-callback.checkpoint.pkl"
    writer = checkpoint_writer(path, identity)
    indices = []

    def stop_after_day3(state):
        writer(state)  # Exactly the callback installed by one_book.
        saved = load_checkpoint(path, identity)
        indices.append(saved["next_day_index"])
        assert saved["next_day_index"] == state["next_day_index"]
        if saved["next_day_index"] == 2:
            assert saved["book"].orders and len(saved["daily"]) == 2
        if saved["next_day_index"] == 3:
            assert saved["book"].unsettled and saved["book"].dividends
            assert saved["missing"].consecutive >= 4
            raise InterruptedError("synthetic interrupt after real atomic publication")

    uninterrupted = run_synthetic(days, bars, marks, eligible, scores, actions)
    with pytest.raises(InterruptedError):
        run_synthetic(days, bars, marks, eligible, scores, actions, stop_after_day3)
    assert indices == [1, 2, 3] and path.is_file()
    resumed = run_policy_book(
        days,
        bars,
        marks,
        scores,
        actions,
        eligible,
        POLICIES["DP_H16_SLOW"],
        0,
        0.002,
        capital=2000,
        resume_state=load_checkpoint(path, identity),
        on_complete_day=writer,
    )
    assert resumed == uninterrupted
    assert load_checkpoint(path, identity)["next_day_index"] == len(days)
    assert path.exists()  # Cleanup belongs to verified producer result completion only.


@pytest.mark.parametrize(
    "mutation",
    [
        "policy",
        "cash_actions",
        "producer",
        "inputs",
        "neutral_exposure",
        "neutral_result",
        "capital",
    ],
)
def test_complete_identity_rejects_changed_execution_or_matched_inputs(tmp_path, mutation):
    row, inputs, code, matched = identity_fixture(tmp_path, neutral=True)
    identity, _ = resume_identity(row, 20, 2000, inputs, matched, code)
    checkpoint = tmp_path / "identity.pkl"
    checkpoint_writer(checkpoint, identity)({"next_day_index": 2})
    assert load_checkpoint(checkpoint, identity)["next_day_index"] == 2
    capital = 2000
    if mutation in code:
        code[mutation].write_text("# changed same path\n")
    elif mutation == "inputs":
        inputs.write_text('{"synthetic":"changed"}')
    else:
        payload = json.loads(matched.read_text())
        if mutation == "neutral_exposure":
            payload["daily_regular_exposure"]["2017-01-02"] = None
        elif mutation == "neutral_result":
            payload["other_result_field"] = "changed"
        else:
            capital = 4000
            payload["initial"] = capital
        matched.write_text(json.dumps(payload))
    changed, _ = resume_identity(row, 20, capital, inputs, matched, code)
    with pytest.raises(ValueError, match="complete identity mismatch"):
        load_checkpoint(checkpoint, changed)
