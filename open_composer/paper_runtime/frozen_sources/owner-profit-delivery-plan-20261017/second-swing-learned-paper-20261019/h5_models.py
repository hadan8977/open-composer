"""Exactly two current October estimators; no historical loop or account engine."""

import ast
import gzip
import hashlib
import json
from types import SimpleNamespace

from h5_common import (
    HERE, STUDY, SYMBOLS, TASK_ID, binding, checked, claim_worker, clean, finish,
    guard_write, load, now, receive_stage, save, snapshot, start, upstream,
)
from h5_input import digest, receive_current_input


def impute(train, test, state_arm):
    """Compile the exact original pure training imputer, not its study runner."""
    import numpy as np
    path = STUDY / "learning.py"
    assert binding(path) in snapshot()
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "impute_training"]
    assert len(nodes) == 1
    method = upstream("h5_feature_names", STUDY / "method.py")
    ns = dict(np=np, STOCK=method.STOCK)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"), ns)
    return ns["impute_training"](train, test, state_arm=state_arm)


def fit_current_models():
    if (HERE / "models/completed.json").exists():
        return receive_current_models()
    start("models", binding(HERE / "input/output.json"))
    s = claim_worker("models")
    current = receive_current_input()
    import numpy as np
    from open_composer.research.ml_backend.model_factory import create_model
    method = upstream("h5_model_feature_names", STUDY / "method.py")
    plan = load(HERE / "prospective-contract.json")
    with np.load(checked(current["training"]), allow_pickle=False) as fold:
        td, tj, weight = fold["train_d"], fold["train_j"], fold["weights"]
    with np.load(checked(load(HERE / "source-plan.json")["accepted_prepared"]), allow_pickle=False) as data:
        target = data["labels"][td, tj]
        assert digest(target) == current["training_audit"]["labels_sha256"]
        assert hashlib.sha256(np.column_stack([td, tj]).tobytes() + weight.tobytes()).hexdigest() == current["training_audit"]["ID_weight_sha256"]
        rows = []
        for arm, width, names in [
            ("STOCK", 9, method.STOCK),
            ("STATE", 33, method.STOCK + method.STATE + method.INTERACTIONS + ["missing_" + n for n in method.STATE + method.INTERACTIONS]),
        ]:
            raw = data[arm.lower()][td, tj]
            assert digest(raw) == current["training_audit"][arm.lower() + "_sha256"]
            # Test preprocessing uses only current eligible names. No prediction
            # is made in this fit stage; the actual new inference is separate.
            test = np.asarray(current["current_" + arm.lower()], dtype=float)[np.asarray(current["eligible"], dtype=bool)]
            train, _, medians = impute(raw, test, arm == "STATE")
            assert train.shape == (len(td), width) and np.isfinite(train).all()
            preprocessing = current["training_audit"]["preprocessing"][arm]
            assert preprocessing == dict(feature_order=names, medians=medians.tolist(),
                medians_sha256=digest(medians), train_matrix_sha256=digest(train), width=width)
            context = dict(task_id=TASK_ID, arm=arm, epoch="2026-10", cutoff="2026-09-30",
                input=binding(HERE / "input/output.json"), input_complete=binding(HERE / "input/completed.json"),
                native=s["go"]["native"], invocation=s["go"]["request"]["invocation"],
                model_attempt=s["go"]["request"]["invocation"] + ":" + arm,
                parameters=plan["models"], feature_order=names, medians=medians.tolist(),
                preprocessing=preprocessing,
                rows=len(td), train_matrix_sha256=digest(train), labels_sha256=digest(target),
                ID_weight_sha256=current["training_audit"]["ID_weight_sha256"], started_at=now())
            guard_write()
            save(HERE / "models" / (arm + "-started.json"), context)
            config = SimpleNamespace(model=SimpleNamespace(kind="lightgbm_regressor",
                hyperparameters=plan["models"], training=SimpleNamespace(seed=20261016)))
            model = create_model(config)
            model.fit(train, target, sample_weight=weight)
            dump = model.booster_.dump_model()
            state = dict(context=context, model_string=model.booster_.model_to_string(),
                         tree_dump=dump, fitted_at=now(), actual_params=model.get_params())
            path = HERE / "models" / (arm + ".json.gz")
            guard_write()
            with path.open("xb") as f:
                f.write(gzip.compress(json.dumps(clean(state), allow_nan=False, separators=(",", ":")).encode(), mtime=0))
            done = dict(arm=arm, started=binding(HERE / "models" / (arm + "-started.json")),
                        state=binding(path), input=context["input"], input_complete=context["input_complete"],
                        native=context["native"], invocation=context["invocation"],
                        model_attempt=context["model_attempt"], completed_at=now())
            save(HERE / "models" / (arm + "-completed.json"), done)
            rows.append(done)
            del model, train, raw
    return finish("models", dict(models=rows, input=binding(HERE / "input/output.json"),
                  computed_started_at=load(HERE / "models/worker-started.json")["claimed_at"],
                  computed_completed_at=now(), genuine_new_fits=2, current_predictions=0))


def receive_current_models():
    result = receive_stage("models")
    assert result["input"] == binding(HERE / "input/output.json")
    assert result["genuine_new_fits"] == 2 and result["current_predictions"] == 0
    assert [r["arm"] for r in result["models"]] == ["STOCK", "STATE"]
    current = load(HERE / "input/output.json")
    audit = current["training_audit"]
    started = load(HERE / "models/started.json")
    method = upstream("h5_received_model_feature_names", STUDY / "method.py")
    orders = {"STOCK": method.STOCK, "STATE": method.STOCK + method.STATE + method.INTERACTIONS + ["missing_" + n for n in method.STATE + method.INTERACTIONS]}
    states = {}
    for row in result["models"]:
        arm = row["arm"]
        assert row == load(HERE / "models" / (arm + "-completed.json"))
        c = load(checked(row["started"], HERE / "models" / (arm + "-started.json")))
        state = json.loads(gzip.decompress(checked(row["state"], HERE / "models" / (arm + ".json.gz")).read_bytes()))
        assert state["context"] == c and c["task_id"] == TASK_ID and c["arm"] == arm
        assert c["epoch"] == "2026-10" and c["cutoff"] == "2026-09-30"
        assert c["input"] == result["input"] and c["input_complete"] == binding(HERE / "input/completed.json")
        assert c["native"] == row["native"] == started["go"]["native"]
        assert c["invocation"] == row["invocation"] == started["go"]["request"]["invocation"]
        assert c["model_attempt"] == row["model_attempt"] == c["invocation"] + ":" + arm
        assert row["input"] == c["input"] and row["input_complete"] == c["input_complete"]
        assert c["feature_order"] == orders[arm]
        assert c["rows"] == audit["rows"]
        assert c["labels_sha256"] == audit["labels_sha256"]
        assert c["ID_weight_sha256"] == audit["ID_weight_sha256"]
        prep = audit["preprocessing"][arm]
        assert c["preprocessing"] == prep
        assert c["medians"] == prep["medians"]
        assert c["feature_order"] == prep["feature_order"]
        assert c["train_matrix_sha256"] == prep["train_matrix_sha256"]
        assert prep["width"] == (9 if arm == "STOCK" else 33)
        assert c["parameters"] == load(HERE / "prospective-contract.json")["models"]
        for k, v in c["parameters"].items():
            assert state["actual_params"][k] == v
        from h5_common import clock
        assert clock(load(HERE / "models/worker-started.json")["claimed_at"]) <= clock(c["started_at"]) <= clock(state["fitted_at"]) <= clock(row["completed_at"]) <= clock(result["computed_completed_at"])
        assert len(c["feature_order"]) == (9 if arm == "STOCK" else 33)
        assert len(c["medians"]) == (9 if arm == "STOCK" else 21)
        states[arm] = state
    assert len({s["context"]["model_attempt"] for s in states.values()}) == 2
    return states


def current_matrix(current, state, arm):
    import numpy as np
    raw = np.asarray(current["current_" + arm.lower()], dtype=float)
    medians = np.asarray(state["context"]["medians"], dtype=float)
    missing = ~np.isfinite(raw)
    out = np.where(missing, medians, raw)
    if arm == "STATE":
        out = np.c_[out, missing[:, 9:].astype(float)]
    eligible = np.asarray(current["eligible"], dtype=bool)
    assert np.isfinite(raw[eligible, :9]).all() and np.isfinite(out[eligible]).all()
    return out, eligible


def scalar_predictions(dump, x):
    """Saved tree arithmetic used by the completed receiver, no estimator API."""
    assert dump["average_output"] is False
    def leaf(node, row):
        while "leaf_value" not in node:
            assert node["decision_type"] == "<="
            node = node["left_child"] if row[node["split_feature"]] <= float(node["threshold"]) else node["right_child"]
        return float(node["leaf_value"])
    return [sum(leaf(t["tree_structure"], row) for t in dump["tree_info"]) for row in x]


def allocate(stock, state, eligible):
    import math
    assert len(stock) == len(state) == len(eligible) == 32
    valid = [j for j in range(32) if eligible[j]]
    assert all(stock[j] is not None and state[j] is not None and math.isfinite(stock[j]) and math.isfinite(state[j]) for j in valid), "Missing forecast BLOCKS, never dropped eligibility"
    assert all(stock[j] is None and state[j] is None for j in range(32) if not eligible[j])
    ranking = sorted(valid, key=lambda j: (-stock[j], j))
    k = min(5, sum(state[j] > 0 for j in valid))
    selected = ranking[:k]
    return dict(K=k, ranking=ranking, selected=selected,
                weights=[.2 if j in selected else 0.0 for j in range(32)],
                target_cash=1 - .2 * k,
                reason="valid_learned_K0" if k == 0 else "STOCK_order_STATE_positive_K")


def infer_current_decision():
    if (HERE / "inference/completed.json").exists():
        return receive_current_decision()
    start("inference", binding(HERE / "models/output.json"))
    claim_worker("inference")
    current = receive_current_input()
    states = receive_current_models()
    import numpy as np
    from lightgbm import Booster
    scores, matrices = {}, {}
    for arm in ["STOCK", "STATE"]:
        x, valid = current_matrix(current, states[arm], arm)
        value = Booster(model_str=states[arm]["model_string"]).predict(x[valid], num_threads=1)
        assert np.isfinite(value).all()
        output = [None] * 32
        for j, v in zip(np.flatnonzero(valid), value, strict=True):
            output[j] = float(v)
        scores[arm] = output
        matrices[arm] = digest(x[valid])
    allocation = allocate(scores["STOCK"], scores["STATE"], current["eligible"])
    policy = load(HERE / "policy-interface.json")
    return finish("inference", dict(input=binding(HERE / "input/output.json"),
        models=binding(HERE / "models/output.json"), symbols=SYMBOLS,
        scores=scores, matrices=matrices, allocation=allocation,
        raw_reference_marks=current["raw_reference_marks"], episode_carriers=current["episode_carriers"],
        source=current["source"], source_complete=current["source_complete"], current_actions=current["controls"]["actions"],
        child_source=current["child_source"], child_source_complete=current["child_source_complete"],
        amendment=current["amendment"], train_current_vintage_mismatch=current["train_current_vintage_mismatch"],
        reference_day="2026-10-16", policy=binding(HERE / "policy-interface.json"),
        policy_values=policy, score_units="Learned5heldsession10bpnet connected economic-return target, not calibrated RTH expected profit",
        computed_started_at=load(HERE / "inference/worker-started.json")["claimed_at"], computed_completed_at=now()))


def receive_current_decision():
    import numpy as np
    obj = receive_stage("inference")
    current = receive_current_input()
    states = receive_current_models()
    assert obj["input"] == binding(HERE / "input/output.json") and obj["models"] == binding(HERE / "models/output.json")
    assert obj["symbols"] == SYMBOLS and obj["reference_day"] == "2026-10-16"
    assert obj["policy"] == binding(HERE / "policy-interface.json") and obj["policy_values"] == load(HERE / "policy-interface.json")
    assert obj["source"] == current["source"] and obj["source_complete"] == current["source_complete"]
    for name in ["child_source", "child_source_complete", "amendment", "train_current_vintage_mismatch"]:
        assert obj[name] == current[name]
    assert obj["current_actions"] == current["controls"]["actions"]
    assert obj["raw_reference_marks"] == current["raw_reference_marks"] and obj["episode_carriers"] == current["episode_carriers"]
    for arm in ["STOCK", "STATE"]:
        x, valid = current_matrix(current, states[arm], arm)
        assert obj["matrices"][arm] == digest(x[valid])
        expected = scalar_predictions(states[arm]["tree_dump"], x[valid])
        observed = [obj["scores"][arm][j] for j in np.flatnonzero(valid)]
        assert np.allclose(expected, observed, rtol=0, atol=1e-12), "Stored scores do not match exact fitted learners"
    assert obj["allocation"] == allocate(obj["scores"]["STOCK"], obj["scores"]["STATE"], current["eligible"])
    return obj
