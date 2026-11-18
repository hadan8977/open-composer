"""Oct20 task-local stage receipts. Import performs no I/O or numerical work.

Old accepted stages are historical artifacts only. Every new producer requires
the actual dated authority, exact affected reviews, input witness where needed,
current aggregate capacity, capability and real capped process identity.
"""

import hashlib
import importlib.util
import json
import math
import os
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path

from current_artifacts import HERE, PEER, REPO, TASK, binding, canonical, checked, clock, load

PARENT = HERE.parent
OPERATING = PARENT / "paper-delivery/preopen-20261020"
DEADLINE = "2026-10-20T13:30:00Z"
POLICIES = ["BASE", "H5", "LSTM", "BASE_STATE_BUDGET"]
STAGES = ["source"] + [f"{kind}/{p}" for kind in ["input", "inference"] for p in POLICIES[:3]] + ["translation/BASE_STATE_BUDGET"]
AGGREGATE_TASK = "CURRENT-PAPER-CONTINUITY-AND-INITIALIZATION-20261020"
PROPOSAL_SHA = "48a602074dcab3c8c3278fd9d8f8c19fc18af9a30c37dfebc798baedf70ed2a0"


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    if type(value).__module__.startswith("numpy"):
        return clean(value.tolist())
    if isinstance(value, float):
        assert math.isfinite(value), "Nonfinite serialized output"
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, canonical(path))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def authority():
    contract = load(HERE / "prospective-contract.json")
    owner = checked(contract["authority"]["owner"], REPO / "reports/research/program/owner-resume-20261020/owner-directive.json")
    main = load(checked(contract["authority"]["Main"], owner.with_name("main-resume-and-day-selection.json")))
    assert contract["authority"]["owner"]["sha256"] == "9334abd1126f460820dd10cffc12df9580590d251a19c90b824e970e17bc417a"
    assert contract["authority"]["Main"]["sha256"] == "2fd36f7997a7f775f11a5f879e1e25865e08bc7261d718e0bbd1a1354c003a2e"
    assert main["science_assignment"]["owner"] == contract["owner"] == "7b109880-ac40-447e-b2a6-f0ed1266ebac"
    assert main["science_assignment"]["peer"] == contract["peer"] == PEER
    hold = load(REPO / "reports/research/control/owner-compute-hold.json")
    assert hold["research_paused"] is False and hold["paper_deployment_allowed"] is True
    assert hold["owner_resume_20261020"]["directive"]["sha256"] == binding(owner)["sha256"]
    assert clock("2026-10-20T00:00:00Z") <= clock(now()) < clock(DEADLINE)


def snapshot():
    mf = load(HERE / "implementation-manifest.json")
    assert mf["task_id"] == TASK
    rows = mf["files"]
    assert rows and len({r["path"] for r in rows}) == len(rows)
    for row in rows:
        checked(row)
    return rows


def receive_reviews():
    result = {}
    for name, verdict, target in [
        ("independent-scientific-component-review.json", "approve_prospective_application_definition", "prospective-contract.json"),
        ("independent-source-contract-review.json", "approve_source_contract", "source-plan.json"),
        ("independent-historical-artifact-review.json", "approve_metadata_receiver", "current_artifacts.py"),
        ("independent-implementation-review.json", "approve_implementation", "implementation-manifest.json"),
    ]:
        r = load(HERE / name)
        assert r["task_id"] == TASK and r["reviewer"] == PEER and r["independent"] is True
        assert r["verdict"] == verdict and r["target"] == binding(HERE / target)
        result[name] = binding(HERE / name)
    data = load(HERE / "independent-current-data-permission-review.json")
    assert data["task_id"] == TASK and data["reviewer"] == PEER
    assert data["independent"] is True
    assert data["accepted_for_current_scientific_component"] is True
    assert data["contract"] == binding(HERE / "prospective-contract.json")
    result["independent-current-data-permission-review.json"] = binding(HERE / "independent-current-data-permission-review.json")
    return result


def receive_launcher():
    manifest_path = HERE / "native-launcher-manifest.json"
    manifest = load(manifest_path)
    review = load(HERE / "independent-native-launcher-review.json")
    assert manifest["task_id"] == TASK and manifest["target"] == binding(HERE / "current_supervise_stage.py")
    assert manifest["scientific_manifest"] == binding(HERE / "implementation-manifest.json")
    assert review["task_id"] == TASK and review["reviewer"] == PEER
    assert review["independent"] is True and review["verdict"] == "approve_native_launcher"
    assert review["native_launcher_accepted"] is True and review["target"] == binding(manifest_path)
    return binding(HERE / "independent-native-launcher-review.json")


def field(value, keys):
    assert type(keys) is list and keys and all(type(k) is str for k in keys)
    for key in keys:
        value = value[key]
    return value


def allocated(roots):
    seen, total = set(), 0
    for root in roots:
        root = canonical(root)
        if not root.exists():
            continue
        for folder, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [n for n in dirs if not (Path(folder) / n).is_symlink()]
            for p in [Path(folder)] + [Path(folder) / n for n in files]:
                s = p.lstat()
                key = (s.st_dev, s.st_ino)
                if key in seen or stat.S_ISLNK(s.st_mode):
                    continue
                seen.add(key)
                if stat.S_ISDIR(s.st_mode) or (stat.S_ISREG(s.st_mode) and s.st_nlink == 1):
                    total += s.st_blocks * 512
    return total


def receive_capacity_context(context_row=None, review_row=None):
    """Receive exact actual post-cleanup16-root scope, preserving CASH/Astra."""
    if context_row is None:
        pointer = load(HERE / "capacity-context.json")
        assert pointer["task_id"] == TASK
        context_row = pointer["version"]
        review_row = binding(pointer["review_path"])
    context_path = canonical(context_row["path"])
    review_path = canonical(review_row["path"])
    assert context_path.parent == review_path.parent == HERE
    assert context_path.name.startswith("capacity-context-") and context_path.suffix == ".json"
    assert review_path.name.startswith("independent-capacity-reception-") and review_path.suffix == ".json"
    c = load(checked(context_row))
    review = load(checked(review_row))
    assert review["task_id"] == TASK and review["reviewer"] == PEER
    assert review["accepted"] is True and review["target"] == context_row
    assert c["task_id"] == TASK and c["aggregate_task_id"] == AGGREGATE_TASK
    expected = REPO / "reports/ops/disk-audit-20261015/capacity-current-day16route-post-owner-cleanup-admission-20261020.json"
    receipt = load(checked(c["receipt"], expected))
    assert c["receipt"]["sha256"] == "cc8d60c8f3b39fabcfd1c6987baa025d7810a6df345222dbf9c8325243fbbede"
    assert receipt["task_id"] == AGGREGATE_TASK and receipt["admitted"] is True and receipt["capacity_only"] is True
    assert receipt["decision"] == "admitted_capacity_only"
    proposal = load(checked(c["aggregate_proposal"], OPERATING / "current-day-whole-route-storage-proposal.json"))
    assert c["aggregate_proposal"]["sha256"] == PROPOSAL_SHA
    assert receipt["request_bindings"]["actual_f9_current_day_whole_route_proposal"] == c["aggregate_proposal"]
    assert proposal["task_id"] == AGGREGATE_TASK
    assert receipt["accepted_whole_route_peak_bytes"] == c["whole_cap_bytes"] == proposal["total_whole_route_peak_bytes"] == 94044160
    assert proposal["scientific_proposal"] == c["scientific_proposal"] == binding(HERE / "component-storage-proposal.json")
    assert proposal["Main_selection"] == load(HERE / "prospective-contract.json")["authority"]["Main"]
    roots = c["aggregate_owned_roots"]
    assert roots == [r["root"] for r in proposal["current_root_allocation"]] == receipt["owned_roots"] == receipt["guard_contract"]["required_roots"]
    paths = [canonical(r) for r in roots]
    assert len(set(paths)) == 16 and HERE in paths
    assert all(not a.is_relative_to(b) for a in paths for b in paths if a != b)
    assert c["scientific_owned_roots"] == [str(HERE)] and c["scientific_cap_bytes"] == 12582912
    normal = receipt["complete_paper_forecast"]
    assert normal["receipt"] == c["paper_forecast"]
    forecast = load(checked(c["paper_forecast"]))
    protected = forecast["required_available_bytes"]
    assert protected == normal["required_available_bytes"] == 10918819017
    assert len(forecast["enabled_upstream_tables"]) == 11 and len(forecast["live_stages"]) == 7
    assert forecast["spill_and_service_already_included_once"] is True
    shared = receipt["concurrent_protected_commitments"]
    assert shared["shared_snapshot"] == c["concurrent_snapshot"]
    concurrent = load(checked(c["concurrent_snapshot"]))
    assert concurrent["complete_normal_forecast"] == c["paper_forecast"]
    assert concurrent["named_remaining_obligations"]["full_normal_spill2GiB_service512MiB_SECfetch2GiB_included_once"] is True
    assert c["terminal_once_bytes"] == shared["terminal_once_bytes"] == 65536
    assert c["synthesis_remaining_bytes"] == shared["single_synthesis"]["current_finite_remaining_future_peak_bytes"] == 12288
    other = load(checked(c["CASH_receipt"], REPO / "reports/ops/disk-audit-20261015/capacity-CASH12MiB-post-owner-cleanup-admission-20261020.json"))
    assert c["CASH_receipt"]["sha256"] == "294b41194d6f8dacac8123182fbd44637e048770f1827f8580e5aed637cbfdcf"
    assert other["admitted"] is True and other["capacity_only"] is True
    assert other["task_id"] == shared["CASH"]["task_id"] == "CASH-BACKED-EARNINGS-INFORMATION-20261019"
    assert other["accepted_whole_route_peak_bytes"] == c["CASH_whole_cap_bytes"] == 12582912
    assert canonical(c["CASH_root"]) == REPO / "reports/research/program/cash-backed-earnings-information-20261019"
    assert other["concurrent_protected_commitments"]["shared_snapshot"] == c["concurrent_snapshot"]
    # The older paper receipt excludes SIP. Receive its subsequently admitted
    # separate commitment without mutating or reinterpreting that old receipt.
    assert c["SIP_stage_admitted"] is True
    sip = load(checked(c["SIP_receipt"], REPO / "reports/ops/disk-audit-20261015/capacity-SIP-daily1GiB-stage-admission-20261020.json"))
    assert c["SIP_receipt"]["sha256"] == "190b64adcfe83f94a2cf8a42d4a5bf5efc7b438659b621a2552459572290ccb0"
    assert sip["task_id"] == "QUANT1-SIP-CURRENT-DAILY-RECOVERY-20261020" and sip["admitted"] is True and sip["capacity_only"] is True
    assert sip["accepted_incremental_stage_peak_bytes"] == c["SIP_extra_future_peak_bytes"] == 1073741824
    return c, protected


def guard_write():
    c, protected = receive_capacity_context()
    own = allocated(c["scientific_owned_roots"])
    credit = allocated(c["aggregate_owned_roots"])
    assert own + 1048576 <= c["scientific_cap_bytes"], "Science includes outside-root native/index1MiB once"
    assert credit <= c["whole_cap_bytes"]
    fs = os.statvfs(REPO)
    free = fs.f_bavail * fs.f_frsize
    remaining = c["whole_cap_bytes"] - credit
    cash_credit = allocated([c["CASH_root"]])
    other_remaining = c["synthesis_remaining_bytes"] + c["SIP_extra_future_peak_bytes"] + max(0, c["CASH_whole_cap_bytes"] - cash_credit)
    margin = free - protected - c["terminal_once_bytes"] - other_remaining - remaining
    assert margin >= 0, "Current whole-route capacity lost; preserve partials and refuse dependent use"
    pointer = load(HERE / "capacity-context.json")
    return dict(context=pointer["version"], review=binding(pointer["review_path"]),
                receipt=c["receipt"], actual_at=now(), free_bytes=free, protected_paper_bytes=protected,
                terminal_once_bytes=c["terminal_once_bytes"], other_remaining_bytes=other_remaining, CASH_allocated_bytes=cash_credit,
                route_credit_once_bytes=credit, scientific_allocated_bytes=own, future_growth_bytes=remaining, margin_bytes=margin)


def receive_capacity_proof(proof):
    c, protected = receive_capacity_context(proof["context"], proof["review"])
    assert proof["receipt"] == c["receipt"] and proof["protected_paper_bytes"] == protected
    assert proof["terminal_once_bytes"] == c["terminal_once_bytes"]
    assert type(proof["CASH_allocated_bytes"]) is int and proof["CASH_allocated_bytes"] >= 0
    assert proof["other_remaining_bytes"] == c["synthesis_remaining_bytes"] + c["SIP_extra_future_peak_bytes"] + max(0, c["CASH_whole_cap_bytes"] - proof["CASH_allocated_bytes"])
    for key in ["free_bytes", "route_credit_once_bytes", "scientific_allocated_bytes", "future_growth_bytes", "margin_bytes"]:
        assert type(proof[key]) is int and proof[key] >= 0
    assert proof["scientific_allocated_bytes"] <= proof["route_credit_once_bytes"] <= c["whole_cap_bytes"]
    assert proof["scientific_allocated_bytes"] + 1048576 <= c["scientific_cap_bytes"]
    assert proof["future_growth_bytes"] == c["whole_cap_bytes"] - proof["route_credit_once_bytes"]
    assert proof["margin_bytes"] == proof["free_bytes"] - protected - c["terminal_once_bytes"] - proof["other_remaining_bytes"] - proof["future_growth_bytes"]
    assert clock("2026-10-20T00:00:00Z") <= clock(proof["actual_at"]) <= clock(now())


def save(path, obj):
    p = canonical(path)
    assert p.is_relative_to(HERE)
    guard_write()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(clean(obj), indent=2, allow_nan=False) + "\n").encode()
    with p.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def expected_kernel(stage):
    assert stage in STAGES
    cap = 734003200 if stage == "inference/LSTM" else 419430400
    return {"memory.max": str(cap), "memory.swap.max": "0", "cpu_affinity": [0], "threads": {n: "1" for n in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHONDONTWRITEBYTECODE"]}}


def process_identity():
    tail = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    return dict(pid=os.getpid(), start_ticks=int(tail[19]))


def kernel(stage):
    group = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().split("::", 1)[1].strip().lstrip("/")
    value = {k: (group / k).read_text().strip() for k in ["memory.max", "memory.swap.max"]}
    value.update(cpu_affinity=sorted(os.sched_getaffinity(0)), threads={n: os.environ.get(n) for n in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHONDONTWRITEBYTECODE"]})
    assert value == expected_kernel(stage)
    return value


def predecessor(stage):
    assert stage in STAGES
    if stage == "source":
        return None, None
    if stage.startswith("input/"):
        prior = "source"
    elif stage.startswith("inference/"):
        prior = "input/" + stage.split("/")[1]
    else:
        # STATE's predecessor is a frozen context of BOTH actually accepted new
        # component packages; no old STATE result or missing component fallback.
        path = HERE / "STATE-components.json"
        context = load(path)
        assert context["task_id"] == TASK
        for policy in ["BASE", "H5"]:
            assert context[policy]["package"] == binding(HERE / policy / "current-package.json")
            review = load(checked(context[policy]["review"], HERE / f"independent-{policy}-result-review.json"))
            assert review["task_id"] == TASK and review["policy"] == policy and review["independent"] is True
            assert review["reviewer"] == PEER and review["verdict"] == "approve_result" and review["component_result_accepted"] is True
            assert review["target"] == binding(HERE / policy / "final-manifest.json")
            receive_stage("inference/" + policy)
        complete_path = HERE / "STATE-components-completed.json"
        complete = load(complete_path)
        assert complete["task_id"] == TASK and complete["input"] == binding(path)
        assert clock(context["created_at"]) <= clock(complete["completed_at"]) <= clock(now())
        return binding(path), binding(complete_path)
    receive_stage(prior)
    return binding(HERE / prior / "output.json"), binding(HERE / prior / "completed.json")


def receive_input_review(policy, row, target):
    assert policy in POLICIES[:3]
    r = load(checked(row, HERE / f"independent-current-input-review-{policy}.json"))
    assert r["task_id"] == TASK and r["policy"] == policy and r["reviewer"] == PEER
    assert r["independent"] is True
    assert r["verdict"] == "accept_complete_current_input"
    assert r["target"] == target == binding(HERE / "input" / policy / "output.json")
    assert r["source_linked_controls_accepted"] is True and r["derived_control_witness"] == target


def receive_go(go):
    r = go["request"]
    stage, invocation = r["stage"], r["invocation"]
    assert r["task_id"] == TASK and stage in STAGES
    assert type(invocation) is str and len(invocation) == 32 and all(c in "0123456789abcdef" for c in invocation)
    assert r["manifest"] == binding(HERE / "implementation-manifest.json") and r["codes"] == snapshot()
    assert r["contract"] == binding(HERE / "prospective-contract.json") and r["source_plan"] == binding(HERE / "source-plan.json")
    prior, prior_complete = predecessor(stage)
    assert r["input"] == prior and r["predecessor_complete"] == prior_complete
    native_path = HERE / "native" / (stage.replace("/", "-") + "-" + invocation + ".json")
    native = load(checked(go["native"], native_path))
    assert native["task_id"] == TASK and native["stage"] == stage and native["invocation"] == invocation
    assert native["request"] == r and native["producer"] == binding(HERE / "current_common.py")
    assert native["process"] == r["process"] and all(type(v) is int and v > 0 for v in r["process"].values())
    assert set(r["process"]) == {"pid", "start_ticks"}
    assert native["component_only"] is True and native["paper_go"] is False
    assert native["registry_loaded"] is True
    assert native["reviews"] == receive_reviews()
    assert native["launcher_review"] == receive_launcher()
    assert native["kernel"] == expected_kernel(stage)
    assert native["capability_snapshot"] == binding(HERE / "capability-snapshot.json")
    assert native["actual_capability"] == load(HERE / "capability-snapshot.json")["capability"]
    registration = load(checked(native["processing_registration"], HERE / "processing-registration.json"))
    assert registration["task_id"] == TASK and registration["stages"] == STAGES
    assert registration["contract"] == r["contract"] and registration["source_plan"] == r["source_plan"]
    assert registration["new_fits"] == registration["new_labels"] == registration["new_historical_accounts"] == 0
    receive_capacity_proof(native["capacity"])
    if stage.startswith("inference/"):
        receive_input_review(stage.split("/")[1], r["input_review"], prior)
    else:
        assert r["input_review"] is None
    if prior_complete:
        assert clock(load(checked(prior_complete))["completed_at"]) <= clock(native["at"])
    assert clock(native["capacity"]["actual_at"]) <= clock(native["at"]) <= clock(go["at"]) <= clock(now())
    assert clock(go["at"]) < clock(DEADLINE)
    return native


def admit(stage, input_binding):
    authority()
    codes, reviews = snapshot(), receive_reviews()
    prior, prior_complete = predecessor(stage)
    assert input_binding == prior
    input_review = binding(HERE / f"independent-current-input-review-{stage.split('/')[1]}.json") if stage.startswith("inference/") else None
    if input_review:
        receive_input_review(stage.split("/")[1], input_review, prior)
    request = dict(task_id=TASK, stage=stage, invocation=uuid.uuid4().hex, process=process_identity(),
                   manifest=binding(HERE / "implementation-manifest.json"), contract=binding(HERE / "prospective-contract.json"),
                   source_plan=binding(HERE / "source-plan.json"), codes=codes, input=input_binding,
                   predecessor_complete=prior_complete, input_review=input_review)
    from open_composer.capabilities.registry import get_capability
    actual = get_capability("market.alpaca_bars", REPO).model_dump(mode="json")
    assert actual == load(HERE / "capability-snapshot.json")["capability"]
    capacity = guard_write()
    path = HERE / "native" / (stage.replace("/", "-") + "-" + request["invocation"] + ".json")
    save(path, dict(task_id=TASK, stage=stage, invocation=request["invocation"], process=request["process"], request=request,
                   producer=binding(HERE / "current_common.py"), at=now(), kernel=kernel(stage), capacity=capacity,
                   actual_capability=actual, capability_snapshot=binding(HERE / "capability-snapshot.json"), reviews=reviews,
                   launcher_review=receive_launcher(),
                   processing_registration=binding(HERE / "processing-registration.json"), registry_loaded=True, component_only=True, paper_go=False))
    go = dict(request=request, native=binding(path), at=now())
    receive_go(go)
    assert snapshot() == codes
    return go


def start(stage, input_binding=None):
    assert stage in STAGES and not (HERE / stage).exists(), "Existing partial/claim/completion requires explicit preserved recovery, never replay"
    go = admit(stage, input_binding)
    save(HERE / stage / "started.json", dict(task_id=TASK, stage=stage, go=go, started_at=now()))
    return load(HERE / stage / "started.json")


def claim_worker(stage):
    d = HERE / stage
    assert not any((d / n).exists() for n in ["worker-started.json", "output.json", "seal.json", "completed.json"]), "A claimed/interrupted/completed worker never computes again"
    s = load(d / "started.json")
    assert s["task_id"] == TASK and s["stage"] == s["go"]["request"]["stage"] == stage
    receive_go(s["go"])
    authority()
    kernel(stage)
    assert s["go"]["request"]["process"] == process_identity(), "Worker must preserve admitted actual PID/start identity"
    claim = dict(task_id=TASK, stage=stage, started=binding(d / "started.json"), native=s["go"]["native"],
                 process=process_identity(), invocation=s["go"]["request"]["invocation"], claimed_at=now())
    save(d / "worker-started.json", claim)
    return claim


def computing(stage):
    """Require the live exclusive claim before any numerical producer import."""
    authority()
    kernel(stage)
    guard_write()
    d = HERE / stage
    assert not any((d / n).exists() for n in ["output.json", "seal.json", "completed.json"])
    s, claim = load(d / "started.json"), load(d / "worker-started.json")
    receive_go(s["go"])
    assert s["stage"] == s["go"]["request"]["stage"] == claim["stage"] == stage
    assert claim["process"] == process_identity() == s["go"]["request"]["process"]
    assert claim["started"] == binding(d / "started.json") and claim["native"] == s["go"]["native"]
    assert claim["invocation"] == s["go"]["request"]["invocation"]
    return s, claim


def finish(stage, obj):
    d = HERE / stage
    s, claim = load(d / "started.json"), load(d / "worker-started.json")
    receive_go(s["go"])
    kernel(stage)
    assert claim["process"] == process_identity() == s["go"]["request"]["process"]
    assert claim["started"] == binding(d / "started.json") and claim["native"] == s["go"]["native"]
    assert clock(claim["claimed_at"]) <= clock(obj["computed_started_at"]) <= clock(obj["computed_completed_at"]) <= clock(now())
    value = dict(clean(obj), task_id=TASK, stage=stage)
    save(d / "output.json", value)
    save(d / "seal.json", dict(started=binding(d / "started.json"), worker=binding(d / "worker-started.json"), output=binding(d / "output.json"), sealed_at=now()))
    save(d / "completed.json", dict(started=binding(d / "started.json"), worker=binding(d / "worker-started.json"), seal=binding(d / "seal.json"), completed_at=now()))
    return receive_stage(stage)


def receive_stage(stage):
    assert stage in STAGES
    d = HERE / stage
    s, claim, seal, done = [load(d / name) for name in ["started.json", "worker-started.json", "seal.json", "completed.json"]]
    assert s["task_id"] == claim["task_id"] == TASK and s["stage"] == claim["stage"] == stage
    receive_go(s["go"])
    assert claim["started"] == seal["started"] == done["started"] == binding(d / "started.json")
    assert seal["worker"] == done["worker"] == binding(d / "worker-started.json")
    assert done["seal"] == binding(d / "seal.json")
    assert claim["native"] == s["go"]["native"] and claim["process"] == s["go"]["request"]["process"]
    assert claim["invocation"] == s["go"]["request"]["invocation"]
    output = load(checked(seal["output"], d / "output.json"))
    assert output["task_id"] == TASK and output["stage"] == stage
    assert clock(s["go"]["at"]) <= clock(s["started_at"]) <= clock(claim["claimed_at"]) <= clock(output["computed_started_at"]) <= clock(output["computed_completed_at"]) <= clock(seal["sealed_at"]) <= clock(done["completed_at"]) <= clock(now())
    assert clock(done["completed_at"]) < clock(DEADLINE)
    if s["go"]["request"]["predecessor_complete"]:
        assert clock(load(checked(s["go"]["request"]["predecessor_complete"]))["completed_at"]) <= clock(s["started_at"])
    return output
