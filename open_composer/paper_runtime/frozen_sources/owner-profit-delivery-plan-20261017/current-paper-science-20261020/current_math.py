"""Saved-model/result arithmetic, standard library only; no producer calls."""

import ast
import gzip
import json
import math

from current_common import HERE, PARENT, binding, checked, load, snapshot

H5 = PARENT / "second-swing-learned-paper-20261019"


def old_math(name):
    path = H5 / "h5_models.py"
    assert binding(path) in snapshot()
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(nodes) == 1
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"), namespace)
    return namespace[name]


def base_allocation(scores, eligible, symbols):
    assert len(scores) == len(eligible) == len(symbols) == 28
    assert all(type(x) in [int, float] and math.isfinite(x) for x in scores)
    assert all(type(v) is bool for v in eligible)
    ranking = sorted([j for j in range(28) if eligible[j] and scores[j] > 0], key=lambda j: (-scores[j], symbols[j]))
    chosen = ranking[:5]
    return dict(K=len(chosen), ranking=ranking, selected=chosen,
                weights=[.2 if j in chosen else 0.0 for j in range(28)], target_cash=1 - .2 * len(chosen),
                reason="supported_positive_scores" if chosen else "supported_no_positive_current_eligible_scores")


def h5_states(current):
    adopted = current["historical_model_provenance"]["adopted"]
    assert len(adopted["states"]) == 2
    states = {}
    for arm, row in zip(["STOCK", "STATE"], adopted["states"], strict=True):
        state = json.loads(gzip.decompress(checked(row, H5 / "models" / (arm + ".json.gz")).read_bytes()))
        assert state["context"] == adopted["exact_inner_contexts"][arm]
        assert all(state["actual_params"][k] == v for k, v in state["context"]["parameters"].items())
        states[arm] = state
    return states


def h5_matrix(current, state, arm):
    rows = current["current_" + arm.lower()]
    medians = state["context"]["medians"]
    assert len(medians) == (9 if arm == "STOCK" else 21)
    assert len(rows) == len(current["eligible"]) == 32
    result = []
    for values, eligible in zip(rows, current["eligible"], strict=True):
        assert len(values) == len(medians)
        missing = [v is None or not math.isfinite(v) for v in values]
        if eligible:
            assert not any(missing[:9]), "Required stock support missing"
        row = [m if bad else v for v, m, bad in zip(values, medians, missing, strict=True)]
        if arm == "STATE":
            row += [float(v) for v in missing[9:]]
        assert len(row) == (9 if arm == "STOCK" else 33) and all(math.isfinite(v) for v in row)
        result.append(row)
    return result


def h5_scores(current, states):
    result = {}
    for arm in ["STOCK", "STATE"]:
        matrix = h5_matrix(current, states[arm], arm)
        values = old_math("scalar_predictions")(states[arm]["tree_dump"], [row for row, yes in zip(matrix, current["eligible"], strict=True) if yes])
        it = iter(values)
        result[arm] = [next(it) if yes else None for yes in current["eligible"]]
        assert all(v is None or math.isfinite(v) for v in result[arm])
    return result


def verify_decision(policy, current, forecast):
    assert forecast["policy"] == policy and forecast["reference_day"] == "2026-10-19"
    assert forecast["raw_reference_marks"] == current["raw_reference_marks"]
    assert forecast["current_actions"] == current["current_actions"]
    assert forecast["input"] == binding(HERE / "input" / policy / "output.json")
    assert forecast["source"] == current["source"] and forecast["source_completed_at"] == current["source_completed_at"]
    assert forecast["historical_model_provenance"] == current["historical_model_provenance"]
    if policy == "BASE":
        state = load(checked(current["historical_model_provenance"]["adopted"]["model"]))
        m = state["model"]
        assert len(current["model_design"]) == 28 and all(len(r) == 14 for r in current["model_design"])
        scalar = [sum((v - mean) / scale * coef for v, mean, scale, coef in zip(row, m["mean"], m["scale"], m["coef"], strict=True)) + m["intercept"] for row in current["model_design"]]
        assert len(scalar) == len(forecast["scores"]) == 28
        assert max(abs(a - b) for a, b in zip(scalar, forecast["scores"], strict=True)) <= 2e-12
        allocation = base_allocation(forecast["scores"], current["eligible"], current["symbols"])
        assert forecast["allocation"] == allocation
    elif policy == "H5":
        scores = h5_scores(current, h5_states(current))
        assert scores == forecast["scores"], "Saved scores differ from exact two retained learners"
        allocation = old_math("allocate")(scores["STOCK"], scores["STATE"], current["eligible"])
        assert allocation == forecast["allocation"]
    else:
        assert policy == "LSTM" and len(forecast["per_seed"]) == 2
        assert [r["seed"] for r in forecast["per_seed"]] == [20261016, 20261017]
        expected_checkpoints = [r["checkpoint"] for r in current["model_context"]]
        assert [r["checkpoint"] for r in forecast["per_seed"]] == expected_checkpoints
        for row in forecast["per_seed"]:
            assert all(len(row[name]) == 10 for name in ["raw_position_logits", "sigmoid_position_fractions", "uncapped_vol_weights", "capped_weights", "feasible_weights", "neutral_raw0_weights"])
            assert all(type(v) in [int, float] and math.isfinite(v) for name in ["raw_position_logits", "sigmoid_position_fractions", "uncapped_vol_weights", "capped_weights", "feasible_weights", "neutral_raw0_weights"] for v in row[name])
            for raw, sigmoid in zip(row["raw_position_logits"], row["sigmoid_position_fractions"], strict=True):
                expected = 1 / (1 + math.exp(-raw)) if raw >= 0 else math.exp(raw) / (1 + math.exp(raw))
                assert abs(expected - sigmoid) <= 1e-7, "Float32 sigmoid witness differs"
            uncapped = [s * .15 / (math.sqrt(252) * v) / 10 for s, v in zip(row["sigmoid_position_fractions"], current["current_vol"], strict=True)]
            assert max(abs(a - b) for a, b in zip(uncapped, row["uncapped_vol_weights"], strict=True)) <= 2e-15
            capped = [min(v, .2) for v in uncapped]
            divisor = max(1, sum(capped))
            assert abs(divisor - row["budget_divisor"]) <= 2e-15
            assert max(abs(a - b) for a, b in zip(capped, row["capped_weights"], strict=True)) <= 2e-15
            assert max(abs(a / divisor - b) for a, b in zip(capped, row["feasible_weights"], strict=True)) <= 2e-15
            neutral = [min(.5 * .15 / (math.sqrt(252) * v) / 10, .2) for v in current["current_vol"]]
            neutral_divisor = max(1, sum(neutral))
            assert max(abs(a / neutral_divisor - b) for a, b in zip(neutral, row["neutral_raw0_weights"], strict=True)) <= 2e-15
        weights = [(a + b) / 2 for a, b in zip(forecast["per_seed"][0]["feasible_weights"], forecast["per_seed"][1]["feasible_weights"], strict=True)]
        assert max(abs(a - b) for a, b in zip(weights, forecast["weights"], strict=True)) <= 2e-15
        assert abs(forecast["target_cash"] - (1 - sum(weights))) <= 2e-15
        allocation = dict(weights=forecast["weights"], target_cash=forecast["target_cash"])
    weights = allocation["weights"]
    assert all(type(v) in [int, float] and math.isfinite(v) and 0 <= v <= .2 + 1e-12 for v in weights)
    assert sum(weights) <= 1 + 1e-12 and abs(allocation["target_cash"] - (1 - sum(weights))) <= 1e-12
    return allocation
