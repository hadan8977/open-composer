"""Task-local scientific receipts. Importing this module performs no work."""

import copy
import hashlib
import importlib.util
import json
import math
import os
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
BASE = HERE.parent / "candidate-contribution/current-initialization-20261019"
FUTURE = BASE.parent / "future-input-receiver"
TASK_ID = "H5-LEARNED-SWING-PAPER-VALIDATION-20261019"
REVIEWER = "93af0483-230a-4632-8b48-c63cd53a01f7"
SYMBOLS = "AES HCA IDXX HPQ OKE XYL FOX URI AXP EXC CTVA PYPL TYL FISV AFL VRSK PBCT LH TT DXC RE TJX SNA SBUX DLR WMT USB ETR WAT SO IVZ MAA".split()
DLSA = REPO / "reports/research/program/dlsa-real-market-continuation-20261014"
STUDY = REPO / "reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014/economic-results/research-reset-20261016/state-conditioned-opportunity-v1"
DEADLINE = "2026-10-19T13:30:00Z"


def canonical(path):
    p = Path(path).absolute()
    assert p == p.resolve(), "Canonical path required, including derived contexts"
    return p


def clock(value):
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    assert d.tzinfo is not None
    return d.astimezone(UTC)


def now():
    return datetime.now(UTC).isoformat()


def load(path):
    return json.loads(canonical(path).read_text())


def binding(path):
    p = canonical(path)
    b = p.read_bytes()
    return dict(path=str(p), bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def checked(row, expected=None):
    p = canonical(row["path"])
    assert expected is None or p == canonical(expected), "Wrong canonical slot"
    assert binding(p) == row, "Changed bound bytes"
    return p


def clean(x):
    if type(x).__module__.startswith("numpy"):
        return clean(x.tolist())
    if isinstance(x, float):
        if not math.isfinite(x):
            return None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (tuple, list)):
        return [clean(v) for v in x]
    return x


def save(path, obj):
    p = canonical(path)
    assert p.is_relative_to(HERE)
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(clean(obj), indent=2, allow_nan=False) + "\n").encode()
    with p.open("xb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, canonical(path))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def authority():
    assert load(REPO / "reports/research/control/owner-compute-hold.json")["research_paused"] is False
    c = load(HERE / "prospective-contract.json")
    for row in c["authority"]:
        checked(row)
    d = load(checked(c["authority"][1]))
    assert d["selected_task"] == TASK_ID
    assert d["complete_owner"] == "7b109880-ac40-447e-b2a6-f0ed1266ebac"
    assert d["independent_peer"] == REVIEWER
    assert d["operating_owner"] == "f9add224-744b-471c-b812-c43cc179fa38"
    assert d["capital"]["BASE_USD"] == d["capital"]["H5_swing_USD"] == 10000
    assert d["capital"]["LSTM_USD"] == 0 and d["capital"]["combined_max_USD"] == 20000
    assert d["deadline_exclusive_utc"] == DEADLINE
    assert clock("2026-10-19T00:00:00Z") <= clock(now()) < clock(DEADLINE)


def snapshot():
    rows = load(HERE / "implementation-manifest.json")["files"]
    assert rows and len({r["path"] for r in rows}) == len(rows)
    for row in rows:
        checked(row)
    return copy.deepcopy(rows)


def policy():
    p = load(HERE / "policy-interface.json")
    expected = dict(task_id=TASK_ID, contract=binding(HERE / "prospective-contract.json"),
        policy_version="original_stock_order_state_K_current_DAYlimit_20261019_v1",
        publish_deadline_exclusive_utc=DEADLINE, consume_before="2026-10-19T13:41:00Z",
        dispatch_window=["2026-10-19T13:40:00Z", "2026-10-19T13:41:00Z"],
        holding_authority_cap="2026-11-14T00:00:00Z", capital_USD=10000, combined_cap_USD=20000,
        reference_day="2026-10-16", next_review="2026-10-23", next_application="2026-10-26")
    assert p == expected, "Exact frozen current application interface required"
    return p


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


def receive_capacity_context():
    """Receive the exact independently checked adapter for the REAL receipt."""
    c = load(HERE / "capacity-context.json")
    external = load(checked(c["receipt"]))
    assert c["task_id"] == TASK_ID
    assert c["receipt"]["path"] == str(REPO / "reports/ops/disk-audit-20261015/capacity-BASE-H5-22MiB-admission-20261019.json")
    assert external["task_id"] == "BASE-H5-TWO-LEARNED-PAPER-VALIDATION-20261019"
    assert external["verified_nested_bindings"]["changed_scientific_whole"] == c["scientific_proposal"]
    assert external[c["admitted_field"]] is True
    assert external[c["capacity_only_field"]] is True
    assert external[c["proposal_hash_field"]] == c["aggregate_proposal"]["sha256"]
    checked(c["aggregate_proposal"])
    assert external[c["whole_cap_field"]] == c["whole_cap_bytes"] == 23068672
    assert c["scientific_proposal"] == binding(HERE / "component-storage-proposal.json")
    assert c["scientific_cap_bytes"] == 6291456
    review = load(HERE / "independent-capacity-reception.json")
    assert review["accepted"] is True and review["target"] == binding(HERE / "capacity-context.json")
    assert review["task_id"] == TASK_ID and review["reviewer"] == REVIEWER
    assert c["outside_root_shared_slot_reserved_bytes"] == 1048576
    roots = c["aggregate_owned_roots"]
    assert roots == [r["root"] for r in external["whole_route_accounting"]["current_owned_roots"]]
    assert c["paper_forecast"] == external["complete_normal_forecast"]["receipt"]
    assert str(HERE) in roots and str(HERE.parent / "second-learned-paper-20261019") in roots
    forecast = load(checked(c["paper_forecast"]))
    assert type(forecast["required_available_bytes"]) is int and forecast["required_available_bytes"] > 0
    return c, forecast["required_available_bytes"]


def guard_write():
    """Fresh actual headroom, with no borrowed reserve or pending credit."""
    c, protected = receive_capacity_context()
    own, credit = allocated([HERE, HERE.parent / "second-learned-paper-20261019"]), allocated(c["aggregate_owned_roots"])
    assert own <= 5242880 and credit <= 22020096, "Full shared1MiB remains reserved INSIDE existing envelope"
    v = os.statvfs(REPO)
    free = v.f_bavail * v.f_frsize
    remaining = 23068672 - credit
    margin = free - protected - 65536 - remaining
    assert margin >= 0, "Actual aggregate headroom lost; retain partials"
    return dict(free_bytes=free, protected_paper_bytes=protected,
                original_terminal_once_bytes=65536, route_credit_once_bytes=credit,
                scientific_allocated_bytes=own, future_growth_bytes=remaining,
                margin_bytes=margin, receipt=c["receipt"], actual_at=now(),
                context=binding(HERE / "capacity-context.json"),
                review=binding(HERE / "independent-capacity-reception.json"))


def receive_capacity_proof(proof):
    c, protected = receive_capacity_context()
    assert proof["context"] == binding(HERE / "capacity-context.json")
    assert proof["review"] == binding(HERE / "independent-capacity-reception.json")
    assert proof["receipt"] == c["receipt"]
    assert proof["protected_paper_bytes"] == protected
    assert proof["original_terminal_once_bytes"] == 65536
    for key in ["free_bytes", "route_credit_once_bytes", "scientific_allocated_bytes", "future_growth_bytes", "margin_bytes"]:
        assert type(proof[key]) is int and proof[key] >= 0
    assert proof["scientific_allocated_bytes"] <= min(5242880, proof["route_credit_once_bytes"])
    assert proof["route_credit_once_bytes"] <= 22020096
    assert proof["future_growth_bytes"] == 23068672 - proof["route_credit_once_bytes"]
    assert proof["margin_bytes"] == proof["free_bytes"] - protected - 65536 - proof["future_growth_bytes"]
    assert clock(proof["actual_at"]) <= clock(now())


def expected_kernel(stage):
    assert stage in ["source", "child-source", "input", "models", "inference"]
    cap = 629145600 if stage == "models" else 419430400
    return {"memory.max": str(cap), "memory.swap.max": "0", "cpu_affinity": [0],
            "threads": {n: "1" for n in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHONDONTWRITEBYTECODE"]}}


def process_identity():
    # The stat command name may contain spaces; fields after its final ')' are
    # stable. starttime is field22, index19 after the command/state prefix.
    tail = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    return dict(pid=os.getpid(), start_ticks=int(tail[19]))


def kernel(stage):
    group = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().split("::", 1)[1].strip().lstrip("/")
    values = {n: (group / n).read_text().strip() for n in ["memory.max", "memory.swap.max"]}
    expected = 629145600 if stage == "models" else 419430400
    assert values == {"memory.max": str(expected), "memory.swap.max": "0"}
    assert os.sched_getaffinity(0) == {0}
    assert all(os.environ.get(n) == "1" for n in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"])
    assert os.environ.get("PYTHONDONTWRITEBYTECODE") == "1"
    values.update(cpu_affinity=sorted(os.sched_getaffinity(0)),
                  threads={n: os.environ[n] for n in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHONDONTWRITEBYTECODE"]})
    assert values == expected_kernel(stage)
    return values


def predecessor(stage):
    assert stage in ["source", "child-source", "input", "models", "inference"]
    if stage == "source":
        return None, None
    prior = {"child-source": "source", "input": "child-source", "models": "input", "inference": "models"}[stage]
    receive_stage(prior)
    return binding(HERE / prior / "output.json"), binding(HERE / prior / "completed.json")


def receive_input_review(row, target):
    review = load(checked(row, HERE / "independent-current-input-review.json"))
    assert review["task_id"] == TASK_ID and review["reviewer"] == REVIEWER
    assert review["verdict"] == "accept_complete_current_input"
    assert target == binding(HERE / "input/output.json") == review["target"]
    assert review["source_linked_controls_accepted"] is True
    return review


def receive_go(go):
    r = go["request"]
    assert r["task_id"] == TASK_ID and r["stage"] in ["source", "child-source", "input", "models", "inference"]
    if r["stage"] == "source" and r["manifest"] != binding(HERE / "implementation-manifest.json"):
        return receive_retained_source_go(go)
    assert r["manifest"] == binding(HERE / "implementation-manifest.json")
    assert r["contract"] == binding(HERE / "prospective-contract.json")
    assert r["source_plan"] == binding(HERE / "source-plan.json")
    assert r["amendment"] == binding(HERE / "current-input-amendment.json")
    assert r["child_source_plan"] == binding(HERE / "child-source-plan.json")
    receive_amendment()
    assert r["codes"] == snapshot()
    stage, invocation = r["stage"], r["invocation"]
    assert type(invocation) is str and len(invocation) == 32 and all(x in "0123456789abcdef" for x in invocation)
    prior, prior_complete = predecessor(stage)
    assert r["input"] == prior and r["predecessor_complete"] == prior_complete
    assert type(r["process"]["pid"]) is int and r["process"]["pid"] > 0
    assert type(r["process"]["start_ticks"]) is int and r["process"]["start_ticks"] > 0
    native = load(checked(go["native"], HERE / "native" / (stage + "-" + invocation + ".json")))
    assert native["task_id"] == TASK_ID and native["stage"] == stage and native["invocation"] == invocation
    assert native["process"] == r["process"]
    assert native["request"] == r and native["producer"] == binding(HERE / "h5_common.py")
    assert native["registry_loaded"] is True
    assert native["component_only"] is True and native["paper_go"] is False
    assert native["kernel"] == expected_kernel(stage)
    assert native["capability_snapshot"] == binding(HERE / "capability-snapshot.json")
    assert native["actual_capability"] == load(HERE / "capability-snapshot.json")["capability"]
    receive_capacity_proof(native["capacity"])
    assert native["amendment_review"] == binding(HERE / "independent-current-amendment-review.json")
    for name, expected_verdict, target in [
        ("independent-scientific-component-review.json", "approve_prospective_application_definition", HERE / "prospective-contract.json"),
        ("independent-source-contract-review.json", "approve_source_contract", HERE / "source-plan.json"),
        ("independent-implementation-review.json", "approve_implementation", HERE / "implementation-manifest.json"),
    ]:
        review = load(HERE / name)
        assert review["task_id"] == TASK_ID and review["reviewer"] == REVIEWER
        assert review["verdict"] == expected_verdict and review["target"] == binding(target)
        assert native["reviews"][name] == binding(HERE / name)
    permission = load(HERE / "independent-current-data-permission-review.json")
    assert permission["task_id"] == TASK_ID and permission["reviewer"] == REVIEWER
    assert permission["accepted_for_current_scientific_component"] is True
    assert permission["contract"] == r["contract"]
    assert native["data_permission"] == binding(HERE / "independent-current-data-permission-review.json")
    registration = load(checked(native["processing_registration"], HERE / "processing-registration.json"))
    assert registration["task_id"] == TASK_ID and registration["stages"] == ["source", "child-source", "input", "models", "inference"]
    assert registration["contract"] == r["contract"] and registration["source_plan"] == r["source_plan"]
    assert registration["amendment"] == r["amendment"] and registration["child_source_plan"] == r["child_source_plan"]
    assert registration["new_fits"] == 2
    assert registration["new_labels"] == registration["new_historical_accounts"] == 0
    assert registration["current_decisions"] == 1 and registration["new_states"] == 2
    if stage in ["models", "inference"]:
        receive_input_review(r["input_review"], binding(HERE / "input/output.json"))
        assert native["input_review"] == r["input_review"]
    else:
        assert native["input_review"] is None and r["input_review"] is None
    if prior_complete:
        assert clock(load(checked(prior_complete))["completed_at"]) <= clock(native["at"])
    assert clock("2026-10-19T00:00:00Z") <= clock(native["capacity"]["actual_at"]) <= clock(native["at"]) <= clock(go["at"]) <= clock(now())
    assert clock(go["at"]) < clock(DEADLINE)
    return native


def admit(stage, input_binding=None):
    authority()
    codes = snapshot()
    receive_amendment()
    prior, prior_complete = predecessor(stage)
    assert input_binding == prior, "Exact actual stage predecessor required"
    input_review = None
    if stage in ["models", "inference"]:
        input_review = binding(HERE / "independent-current-input-review.json")
        receive_input_review(input_review, binding(HERE / "input/output.json"))
    r = dict(task_id=TASK_ID, stage=stage, manifest=binding(HERE / "implementation-manifest.json"),
             contract=binding(HERE / "prospective-contract.json"), source_plan=binding(HERE / "source-plan.json"),
             codes=codes, amendment=binding(HERE / "current-input-amendment.json"),
             child_source_plan=binding(HERE / "child-source-plan.json"),
             input=input_binding, predecessor_complete=prior_complete,
             input_review=input_review, process=process_identity(), invocation=uuid.uuid4().hex)
    reviews = {}
    for name in ["independent-scientific-component-review.json", "independent-source-contract-review.json", "independent-implementation-review.json"]:
        reviews[name] = binding(HERE / name)
    from open_composer.capabilities.registry import get_capability
    actual = get_capability("market.alpaca_bars", REPO).model_dump(mode="json")
    assert actual == load(HERE / "capability-snapshot.json")["capability"]
    p = HERE / "native" / (stage + "-" + r["invocation"] + ".json")
    capacity = guard_write()
    save(p, dict(task_id=TASK_ID, stage=stage, invocation=r["invocation"], process=r["process"],
                 request=r, producer=binding(HERE / "h5_common.py"), at=now(),
                 registry_loaded=True, actual_capability=actual, kernel=kernel(stage),
                 capability_snapshot=binding(HERE / "capability-snapshot.json"),
                 capacity=capacity, reviews=reviews, input_review=input_review,
                 data_permission=binding(HERE / "independent-current-data-permission-review.json"),
                 amendment_review=binding(HERE / "independent-current-amendment-review.json"),
                 processing_registration=binding(HERE / "processing-registration.json"),
                 component_only=True, paper_go=False))
    go = dict(request=r, native=binding(p), at=now())
    receive_go(go)
    assert snapshot() == codes
    return go


def start(stage, input_binding=None):
    d = HERE / stage
    assert not d.exists(), "Existing or failed invocation requires explicit recovery; no replay"
    go = admit(stage, input_binding)
    guard_write()
    save(d / "started.json", dict(task_id=TASK_ID, stage=stage, go=go, started_at=now()))
    return load(d / "started.json")


def finish(stage, obj):
    d = HERE / stage
    s = load(d / "started.json")
    receive_go(s["go"])
    assert s["go"]["request"]["stage"] == stage
    kernel(stage)
    guard_write()
    obj.setdefault("computed_started_at", now())
    obj.setdefault("computed_completed_at", now())
    if stage in ["input", "models", "inference"]:
        claim = load(d / "worker-started.json")
        assert claim["process"] == process_identity() == s["go"]["request"]["process"]
        assert claim["started"] == binding(d / "started.json") and claim["native"] == s["go"]["native"]
        assert clock(claim["claimed_at"]) <= clock(obj["computed_started_at"]) <= clock(obj["computed_completed_at"]) <= clock(now())
    obj.update(task_id=TASK_ID)
    obj.setdefault("computed_started_at", s["started_at"])
    obj.setdefault("computed_completed_at", now())
    save(d / "output.json", obj)
    worker = binding(d / "worker-started.json") if stage in ["input", "models", "inference"] else None
    save(d / "seal.json", dict(started=binding(d / "started.json"), output=binding(d / "output.json"), worker=worker, sealed_at=now()))
    save(d / "completed.json", dict(started=binding(d / "started.json"), seal=binding(d / "seal.json"), worker=worker, completed_at=now()))
    return receive_stage(stage)


def receive_stage(stage):
    d = HERE / stage
    s = load(d / "started.json")
    assert s["task_id"] == TASK_ID and s["stage"] == stage
    receive_go(s["go"])
    assert s["go"]["request"]["stage"] == stage
    if s["go"]["request"]["predecessor_complete"]:
        assert clock(load(checked(s["go"]["request"]["predecessor_complete"]))["completed_at"]) <= clock(s["started_at"])
    seal = load(d / "seal.json")
    complete = load(d / "completed.json")
    assert complete["started"] == seal["started"] == binding(d / "started.json")
    assert complete["seal"] == binding(d / "seal.json")
    if stage in ["input", "models", "inference"]:
        claim = load(d / "worker-started.json")
        assert complete["worker"] == seal["worker"] == binding(d / "worker-started.json")
        assert claim["started"] == binding(d / "started.json")
        assert claim["task_id"] == TASK_ID and claim["native"] == s["go"]["native"]
        assert claim["process"] == s["go"]["request"]["process"]
        assert claim["invocation"] == s["go"]["request"]["invocation"]
        assert clock(s["started_at"]) <= clock(claim["claimed_at"]) <= clock(seal["sealed_at"])
    else:
        assert complete["worker"] is None and seal["worker"] is None
    checked(seal["output"], d / "output.json")
    assert clock(s["go"]["at"]) <= clock(s["started_at"]) <= clock(seal["sealed_at"]) <= clock(complete["completed_at"]) <= clock(now())
    assert clock(complete["completed_at"]) < clock(DEADLINE)
    if stage not in ["source", "child-source"]:
        expected = {"started.json", "worker-started.json", "output.json", "seal.json", "completed.json"}
        if stage == "input":
            expected.add("training.npz")
        if stage == "models":
            expected |= {arm + suffix for arm in ["STOCK", "STATE"] for suffix in ["-started.json", "-completed.json", ".json.gz"]}
        assert {p.name for p in d.iterdir()} == expected, "Unlisted/partial stage artifact"
    obj = load(d / "output.json")
    assert obj["task_id"] == TASK_ID
    assert clock(s["started_at"]) <= clock(obj["computed_started_at"]) <= clock(obj["computed_completed_at"]) <= clock(seal["sealed_at"])
    return obj


def claim_worker(stage):
    s = load(HERE / stage / "started.json")
    assert s["go"]["request"]["process"] == process_identity()
    assert set(p.name for p in (HERE / stage).iterdir()) == {"started.json"}, "Refuse claimed/completed/orphan prefix before any decoder or estimator"
    receive_go(s["go"])
    guard_write()
    save(HERE / stage / "worker-started.json", dict(task_id=TASK_ID, stage=stage,
        started=binding(HERE / stage / "started.json"), native=s["go"]["native"],
        process=process_identity(), invocation=s["go"]["request"]["invocation"], claimed_at=now()))
    return s

def upstream(name, path):
    """Import only reviewed pure modules, never old study entry points."""
    assert binding(path) in snapshot()
    return module(name, path)

def received_inventory():
    m = load(HERE / "input-manifest.json")
    assert m["task_id"] == TASK_ID
    for row in m["files"]:
        checked(row)
    return m["files"]


def receive_amendment():
    a = load(HERE / "current-input-amendment.json")
    judgment = load(checked(a["independent_definition"], HERE / "independent-current-action-judgment.json"))
    assert judgment["task_id"] == TASK_ID and judgment["reviewer"] == REVIEWER
    assert judgment["verdict"] == "approve_bounded_current_input_repair_definition"
    review = load(HERE / "independent-current-amendment-review.json")
    assert review["task_id"] == TASK_ID and review["reviewer"] == REVIEWER
    assert review["verdict"] == "approve_bounded_current_input_repair_definition"
    assert review["target"] == binding(HERE / "current-input-amendment.json")
    assert review["child_source_plan"] == binding(HERE / "child-source-plan.json")
    assert review["accepted_for_current_scientific_component"] is True
    assert a["original_contract"] == binding(HERE / "prospective-contract.json")
    assert a["original_source_plan"] == binding(HERE / "source-plan.json")
    assert a["original_input_inventory"] == binding(HERE / "input-manifest.json")
    for key in ["source01_complete", "actual_fresh_actions", "diagnosis", "old_dated_rows", "recovery"]:
        checked(a[key])
    return a


def receive_retained_source_go(go):
    """Exact actual M2 source01, received without retag/re-GET/re-admission."""
    snapshot()
    current = load(HERE / "independent-implementation-review.json")
    assert current["task_id"] == TASK_ID and current["reviewer"] == REVIEWER
    assert current["verdict"] == "approve_implementation" and current["target"] == binding(HERE / "implementation-manifest.json")
    receive_amendment()
    spec = load(HERE / "source01-retained-recovery.json")
    old_mf = load(checked(spec["archived_manifest"], HERE / "M2-archive/implementation-manifest.json"))
    old_review = load(checked(spec["archived_review"], HERE / "M2-archive/independent-implementation-review.json"))
    assert spec["original_manifest"] == dict(spec["archived_manifest"], path=str(HERE / "implementation-manifest.json"))
    assert spec["original_review"] == dict(spec["archived_review"], path=str(HERE / "independent-implementation-review.json"))
    assert old_review["verdict"] == "approve_implementation" and old_review["target"] == spec["original_manifest"]
    mapping = {r["original"]["path"]: r for r in load(checked(spec["archive_map"], HERE / "M2-archive/archive-map.json"))["mapping"]}
    def old_binding(row):
        if row["path"] in mapping:
            m = mapping[row["path"]]
            assert m["original"] == row
            checked(m["archive"], HERE / "M2-archive" / Path(row["path"]).name)
            assert (m["archive"]["bytes"], m["archive"]["sha256"]) == (row["bytes"], row["sha256"])
            return load(m["archive"]["path"])
        return load(checked(row))
    for row in old_mf["files"]:
        if row["path"] in mapping:
            m = mapping[row["path"]]
            assert m["original"] == row
            checked(m["archive"])
        else:
            checked(row)
    for key, expected in [
        ("source_started", HERE / "source/started.json"), ("source_context", HERE / "source/context.json"),
        ("source_complete", HERE / "source/completed.json"), ("source_seal", HERE / "source/seal.json"),
        ("source_output", HERE / "source/output.json"), ("source_exit", HERE / "source-native-exit-event.json"),
    ]:
        checked(spec[key], expected)
    for key in ["source_log", "source_profile", "source_transport_manifest", "source_transport_review"]:
        checked(spec[key])
    assert load(spec["source_exit"]["path"])["exit_code"] == 0
    started = load(spec["source_started"]["path"])
    assert go == started["go"]
    r = go["request"]
    assert r["task_id"] == TASK_ID and r["stage"] == "source"
    assert r["manifest"] == spec["original_manifest"] and r["codes"] == old_mf["files"]
    assert r["input"] is None and r["predecessor_complete"] is None and r["input_review"] is None
    assert r["contract"] == binding(HERE / "prospective-contract.json") and r["source_plan"] == binding(HERE / "source-plan.json")
    assert go["native"] == spec["source_native"]
    native = load(checked(go["native"], HERE / "native" / ("source-" + r["invocation"] + ".json")))
    assert native["request"] == r and native["invocation"] == r["invocation"]
    assert native["task_id"] == TASK_ID and native["stage"] == "source" and native["process"] == r["process"]
    assert native["producer"] == spec["original_producer"]
    assert mapping[str(HERE / "h5_common.py")]["original"] == spec["original_producer"]
    assert native["kernel"] == expected_kernel("source") and native["registry_loaded"] is True
    assert native["component_only"] is True and native["paper_go"] is False
    assert native["capability_snapshot"] == binding(HERE / "capability-snapshot.json")
    assert native["actual_capability"] == load(HERE / "capability-snapshot.json")["capability"]
    receive_capacity_proof(native["capacity"])
    for name, verdict, target in [
        ("independent-scientific-component-review.json", "approve_prospective_application_definition", r["contract"]),
        ("independent-source-contract-review.json", "approve_source_contract", r["source_plan"]),
        ("independent-implementation-review.json", "approve_implementation", r["manifest"]),
    ]:
        row = native["reviews"][name]
        review = old_binding(row)
        assert review["task_id"] == TASK_ID and review["reviewer"] == REVIEWER
        assert review["verdict"] == verdict and review["target"] == target
    data = old_binding(native["data_permission"])
    assert data["accepted_for_current_scientific_component"] is True and data["contract"] == r["contract"]
    assert native["input_review"] is None
    assert native["processing_registration"] == spec["original_registration"]
    reg = old_binding(spec["original_registration"])
    assert reg["task_id"] == TASK_ID and reg["stages"] == ["source", "input", "models", "inference"]
    assert reg["contract"] == r["contract"] and reg["source_plan"] == r["source_plan"] and reg["new_fits"] == 2
    assert clock(native["capacity"]["actual_at"]) <= clock(native["at"]) <= clock(go["at"]) <= clock(started["started_at"]) < clock(DEADLINE)
    assert clock(load(spec["source_complete"]["path"])["completed_at"]) <= clock(now())
    return native
