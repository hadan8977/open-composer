"""New prospective session receipts; old science and expired jobs stay immutable."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parent
sys.path.insert(0, str(PREVIOUS))
import current_common as prior

TASK = prior.TASK
SESSION = "SIX-CURRENT-SESSION-20261020"
OWNER = "7b109880-ac40-447e-b2a6-f0ed1266ebac"
PEER = prior.PEER
binding, checked, load, now, clock = prior.binding, prior.checked, prior.load, prior.now, prior.clock


def contract():
    p = ROOT / "current-session-contract.json"
    value = load(p)
    assert value["task_id"] == TASK and value["session_id"] == SESSION
    assert value["owner"] == OWNER and value["peer"] == PEER
    owner = checked(value["owner_directive"], prior.PARENT / "six-paper-operation-continuation-20261020/owner-directive.json")
    main = checked(value["Main"], prior.OPERATING / "main-six-current-session-completion-decision.json")
    assert binding(owner)["sha256"] == "880ffa56f0338452466eacb7b37f1c9c75d78c8496112b4699ebffc706a9f464"
    assert binding(main)["sha256"] == "bef005c833c469800f50f12527f6681f9a3e8e791e4af2888d062a6944af02c5"
    envelope = load(checked(value["Main_clock_envelope"], prior.OPERATING / "main-prospective-current-session-envelope.json"))
    assert value["Main_clock_envelope"]["sha256"] == "dceb83e917180f41cbfe88692b4096c9956f6ecd603b54d6a6a9af768097a4c5"
    assert value["new_fits"] == value["new_labels"] == value["new_backtests"] == 0
    assert value["reference_day"] == "2026-10-19" and value["application_day"] == "2026-10-20"
    assert clock(value["created_at"]) <= clock(now())
    cal = value["calendar"]
    assert clock(envelope["created_at_utc"]) <= clock(value["created_at"]) < clock(cal["dispatch_window"][0])
    assert clock(cal["dispatch_window"][0]) < clock(cal["publish_before"]) < clock(cal["dispatch_window"][1])
    assert cal["dispatch_window"][1] == cal["consume_before"] == envelope["latest_new_risk_dispatch_utc"]
    assert cal["cancel_pending_by"] == envelope["pending_initial_order_cancel_by_utc"]
    assert cal["post_close_reconcile"] == envelope["post_close_reconciliation_window_utc"]
    assert cal["decision_mode"] == "per_policy_as_soon_as_actual_accepted_instruction_and_operating_readiness"
    assert value["holding_authority_cap"] == "2026-11-14T00:00:00Z"
    return value


def authority(*, execution=False):
    value = contract()
    hold = load(prior.REPO / "reports/research/control/owner-compute-hold.json")
    assert hold["paper_deployment_allowed"] is True and hold["new_paper_strategy_activation_allowed"] is True
    limit = value["calendar"]["consume_before" if execution else "publish_before"]
    assert clock(value["created_at"]) <= clock(now()) < clock(limit), "New session scope expired; no backdating/catch-up"
    return value


def reviews():
    index = load(ROOT / "implementation-pointer.json")
    manifest_path, review_path = checked(index["manifest"]), checked(index["review"])
    assert manifest_path.parent == review_path.parent == ROOT
    mf, review = load(manifest_path), load(review_path)
    assert mf["task_id"] == review["task_id"] == TASK and mf["session_id"] == review["session_id"] == SESSION
    assert review["reviewer"] == PEER and review["independent"] is True
    assert review["verdict"] == "approve_implementation" and review["session_scope_accepted"] is True
    assert review["target"] == binding(manifest_path)
    assert mf["contract"] == binding(ROOT / "current-session-contract.json")
    assert mf["files"] and len({r["path"] for r in mf["files"]}) == len(mf["files"])
    for row in mf["files"]:
        checked(row)
    return dict(manifest=binding(manifest_path), review=binding(review_path))


def receive_code(proof):
    mf = load(checked(proof["manifest"]))
    review = load(checked(proof["review"]))
    assert mf["task_id"] == review["task_id"] == TASK and mf["session_id"] == review["session_id"] == SESSION
    assert review["reviewer"] == PEER and review["independent"] is True
    assert review["verdict"] == "approve_implementation" and review["session_scope_accepted"] is True
    assert review["target"] == proof["manifest"]
    assert mf["contract"] == binding(ROOT / "current-session-contract.json")
    assert mf["files"] and len({r["path"] for r in mf["files"]}) == len(mf["files"])
    for row in mf["files"]:
        checked(row)
    return mf


def kernel(stage):
    cap = 734003200 if stage == "inference/LSTM" else 419430400
    group = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().split("::", 1)[1].strip().lstrip("/")
    result = {k: (group / k).read_text().strip() for k in ["memory.max", "memory.swap.max"]}
    result["cpu_affinity"] = sorted(os.sched_getaffinity(0))
    result["threads"] = {k: os.environ.get(k) for k in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHONDONTWRITEBYTECODE"]}
    assert result == {"memory.max": str(cap), "memory.swap.max": "0", "cpu_affinity": [0],
                      "threads": {k: "1" for k in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHONDONTWRITEBYTECODE"]}}
    return result


def save(path, value):
    path = prior.canonical(path)
    assert path.is_relative_to(ROOT)
    prior.guard_write()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write((json.dumps(prior.clean(value), indent=2, allow_nan=False) + "\n").encode())
        f.flush()
        os.fsync(f.fileno())


def actual_registry():
    registry = prior.REPO / "capabilities/registry.yaml"
    before = binding(registry)
    argv = [str(prior.REPO / ".venv/bin/python"), "-c",
            'import json; from pathlib import Path; from open_composer.capabilities.registry import get_capability; print(json.dumps(get_capability("market.alpaca_bars",Path.cwd()).model_dump(mode="json")))']
    p = subprocess.run(argv, cwd=prior.REPO, capture_output=True, text=True, timeout=30, check=True)
    result = json.loads(p.stdout)
    assert before == binding(registry)
    assert result == load(PREVIOUS / "capability-snapshot.json")["capability"]
    return dict(argv=argv, actual_capability=result, registry=before, received_at=now(),
                actual_unmodified_registered_receiver=True, provider_calls=0)


def start(stage, input_binding):
    assert stage in ["adopt/BASE", "adopt/H5", "adopt/BASE_STATE_BUDGET", "inference/LSTM", "ETF-source", "ETF-input", "translation/MULTI_EQUAL", "translation/MULTI_HIERARCHICAL"]
    authority()
    k, code = kernel(stage), reviews()
    assert not (ROOT / stage).exists(), "Existing new-session prefix requires explicit recovery; never replay"
    checked(input_binding)
    input_review, predecessor_complete = None, None
    if stage == "inference/LSTM":
        assert input_binding == binding(PREVIOUS / "input/LSTM/output.json")
        review = load(PREVIOUS / "independent-current-input-review-LSTM.json")
        assert review["task_id"] == TASK and review["policy"] == "LSTM" and review["reviewer"] == PEER and review["independent"] is True
        assert review["verdict"] == "accept_complete_current_input" and review["source_linked_controls_accepted"] is True
        assert review["target"] == review["derived_control_witness"] == input_binding
        assert not (PREVIOUS / "inference/LSTM/worker-started.json").exists()
        assert not (PREVIOUS / "inference/LSTM/completed.json").exists()
        input_review = binding(PREVIOUS / "independent-current-input-review-LSTM.json")
        predecessor_complete = binding(PREVIOUS / "input/LSTM/completed.json")
    meta = actual_registry()
    capacity = prior.guard_write()
    native = dict(task_id=TASK, session_id=SESSION, stage=stage, invocation=uuid.uuid4().hex,
        process=prior.process_identity(), at=now(), kernel=k, code=code, registry=meta,
        capacity=capacity, input=input_binding, input_review=input_review, predecessor_complete=predecessor_complete,
        contract=binding(ROOT / "current-session-contract.json"),
        prior_expired_LSTM_failure=binding(PREVIOUS / "LSTM02-native-exit-event.json"),
        component_only=True, operating_or_order_go=False)
    save(ROOT / stage / "native-go.json", native)
    started = dict(task_id=TASK, session_id=SESSION, stage=stage, started_at=now(), native=binding(ROOT / stage / "native-go.json"))
    save(ROOT / stage / "started.json", started)
    return started


def receive_native(stage):
    path = ROOT / stage
    started = load(path / "started.json")
    native = load(checked(started["native"], path / "native-go.json"))
    assert started["task_id"] == native["task_id"] == TASK
    assert started["session_id"] == native["session_id"] == SESSION
    assert started["stage"] == native["stage"] == stage
    expected_cap = 734003200 if stage == "inference/LSTM" else 419430400
    assert native["kernel"] == {"memory.max": str(expected_cap), "memory.swap.max": "0", "cpu_affinity": [0],
        "threads": {k: "1" for k in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHONDONTWRITEBYTECODE"]}}
    assert isinstance(native["invocation"], str) and len(native["invocation"]) == 32 and all(c in "0123456789abcdef" for c in native["invocation"])
    assert set(native["process"]) == {"pid", "start_ticks"} and all(type(v) is int and v > 0 for v in native["process"].values())
    receive_code(native["code"])
    assert native["contract"] == binding(ROOT / "current-session-contract.json")
    checked(native["input"])
    if stage == "inference/LSTM":
        assert native["input"] == binding(PREVIOUS / "input/LSTM/output.json")
        witness = load(checked(native["input_review"], PREVIOUS / "independent-current-input-review-LSTM.json"))
        assert witness["task_id"] == TASK and witness["policy"] == "LSTM" and witness["reviewer"] == PEER and witness["independent"] is True
        assert witness["verdict"] == "accept_complete_current_input" and witness["source_linked_controls_accepted"] is True
        assert witness["target"] == witness["derived_control_witness"] == native["input"]
        complete = load(checked(native["predecessor_complete"], PREVIOUS / "input/LSTM/completed.json"))
        assert clock(complete["completed_at"]) <= clock(native["at"])
    else:
        assert native["input_review"] is None and native["predecessor_complete"] is None
    prior.receive_capacity_proof(native["capacity"])
    assert native["registry"]["actual_capability"] == load(PREVIOUS / "capability-snapshot.json")["capability"]
    checked(native["registry"]["registry"])
    assert native["registry"]["actual_unmodified_registered_receiver"] is True and native["registry"]["provider_calls"] == 0
    assert native["registry"]["argv"] == [str(prior.REPO / ".venv/bin/python"), "-c",
        'import json; from pathlib import Path; from open_composer.capabilities.registry import get_capability; print(json.dumps(get_capability("market.alpaca_bars",Path.cwd()).model_dump(mode="json")))']
    assert clock(contract()["created_at"]) <= clock(native["registry"]["received_at"]) <= clock(native["at"])
    assert clock(contract()["created_at"]) <= clock(native["at"]) <= clock(started["started_at"]) <= clock(now())
    return started, native


def claim_worker(stage):
    authority()
    kernel(stage)
    d = ROOT / stage
    assert not any((d / name).exists() for name in ["worker-started.json", "output.json", "seal.json", "completed.json"])
    started, native = receive_native(stage)
    assert native["process"] == prior.process_identity()
    claim = dict(task_id=TASK, session_id=SESSION, stage=stage, started=binding(d / "started.json"),
                 native=started["native"], invocation=native["invocation"], process=native["process"], claimed_at=now())
    save(d / "worker-started.json", claim)
    return claim


def computing(stage):
    authority()
    kernel(stage)
    prior.guard_write()
    started, native = receive_native(stage)
    d = ROOT / stage
    claim = load(d / "worker-started.json")
    assert claim["process"] == native["process"] == prior.process_identity()
    assert claim["started"] == binding(d / "started.json") and claim["native"] == started["native"]
    assert claim["invocation"] == native["invocation"] and claim["stage"] == stage and claim["session_id"] == SESSION
    assert not any((d / n).exists() for n in ["output.json", "seal.json", "completed.json"])
    return started, claim


def finish(stage, output):
    computing(stage)
    d = ROOT / stage
    claim = load(d / "worker-started.json")
    assert clock(claim["claimed_at"]) <= clock(output["computed_started_at"]) <= clock(output["computed_completed_at"]) <= clock(now())
    save(d / "output.json", dict(prior.clean(output), task_id=TASK, session_id=SESSION, stage=stage))
    save(d / "seal.json", dict(started=binding(d / "started.json"), worker=binding(d / "worker-started.json"),
                              output=binding(d / "output.json"), sealed_at=now()))
    save(d / "completed.json", dict(started=binding(d / "started.json"), worker=binding(d / "worker-started.json"),
                                   seal=binding(d / "seal.json"), completed_at=now()))
    return receive_stage(stage)


def receive_stage(stage):
    d = ROOT / stage
    started, native = receive_native(stage)
    claim, seal, done = [load(d / n) for n in ["worker-started.json", "seal.json", "completed.json"]]
    assert claim["started"] == seal["started"] == done["started"] == binding(d / "started.json")
    assert seal["worker"] == done["worker"] == binding(d / "worker-started.json")
    assert claim["native"] == started["native"] and claim["process"] == native["process"]
    assert claim["invocation"] == native["invocation"] and claim["stage"] == stage and claim["session_id"] == SESSION
    assert done["seal"] == binding(d / "seal.json")
    output = load(checked(seal["output"], d / "output.json"))
    assert output["task_id"] == TASK and output["session_id"] == SESSION and output["stage"] == stage
    assert clock(started["started_at"]) <= clock(claim["claimed_at"]) <= clock(output["computed_started_at"]) <= clock(output["computed_completed_at"]) <= clock(seal["sealed_at"]) <= clock(done["completed_at"]) <= clock(now())
    assert clock(done["completed_at"]) < clock(contract()["calendar"]["publish_before"])
    return output
