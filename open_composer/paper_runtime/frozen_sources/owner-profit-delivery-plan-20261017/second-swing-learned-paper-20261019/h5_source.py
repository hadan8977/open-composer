"""Fixed historical raw/action reception. Transport is supplied by f9; no import work."""

import ast
import copy
import json
import os

from h5_common import (
    DEADLINE, FUTURE, HERE, TASK_ID, authority, binding, canonical, checked,
    clock, finish, guard_write, kernel, load, now, receive_go, receive_stage,
    save, snapshot, start,
)


def pure_function(path, name):
    path = canonical(path)
    assert binding(path) in snapshot()
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(nodes) == 1
    ns = dict(canonical=canonical, binding=binding, checked=checked, load=load,
              clock=clock, now=now, save=save, json=json, os=os)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"), ns)
    return ns[name]


def source_fetch_guard(expected_context):
    """Exact reviewed f9 hook before factory/GET and again after pacing."""
    authority()
    kernel("source")
    guard_write()
    c = load(checked(expected_context, HERE / "source/context.json"))
    assert c["task_id"] == TASK_ID
    s = load(checked(c["started"], HERE / "source/started.json"))
    receive_go(s["go"])
    assert s["go"]["request"]["stage"] == "source"
    assert c["go"] == s["go"] and c["plan"] == binding(HERE / "source-plan.json")
    assert c["requests"] == load(HERE / "source-plan.json")["requests"]
    assert clock(s["started_at"]) <= clock(c["created_at"]) <= clock(now()) < clock(DEADLINE)
    assert not (HERE / "source/completed.json").exists()
    return None


def collect_current_sources(*, fetch):
    if (HERE / "source/completed.json").exists():
        receive_sources()
        return binding(HERE / "source/output.json")
    s = start("source")  # An existing failed/orphan prefix refuses BEFORE GET.
    frozen = copy.deepcopy(load(HERE / "source-plan.json")["requests"])
    guard_write()
    save(HERE / "source/context.json", dict(task_id=TASK_ID,
         started=binding(HERE / "source/started.json"), go=s["go"],
         plan=binding(HERE / "source-plan.json"), requests=frozen, created_at=now()))
    context = binding(HERE / "source/context.json")
    writer = pure_function(FUTURE / "source_writer.py", "capture_request")

    def bounded(endpoint, params, timeout):
        source_fetch_guard(context)
        # Preserve complete returned bytes/status even if late or oversized.
        # The reviewed writer fsyncs raw+HTTP metadata BEFORE refusing late/error
        # pages. No next request or downstream use follows a failed capture.
        return fetch(endpoint, params, timeout)

    for request in frozen:
        writer(HERE / "source" / request["key"], copy.deepcopy(request), DEADLINE,
               bounded, clock("2026-10-19T00:00:00Z"), context)
        retained = sum(p.stat().st_size for p in (HERE / "source").rglob("*") if p.is_file())
        assert retained + 65536 <= 786432, "Complete capture preserved; actual source footprint exceeds declared line; no downstream use"
        source_fetch_guard(context)
    source_fetch_guard(context)
    return finish("source", dict(context=context, requests=frozen, completed_capture_at=now()))


def receive_sources():
    result = receive_stage("source")
    c = load(checked(result["context"], HERE / "source/context.json"))
    assert c["started"] == binding(HERE / "source/started.json")
    s = load(c["started"]["path"])
    assert c["go"] == s["go"] and c["plan"] == binding(HERE / "source-plan.json")
    assert result["requests"] == c["requests"] == load(HERE / "source-plan.json")["requests"]
    reader = pure_function(FUTURE / "source_contract.py", "pages")
    objects, consumed = {}, [result["context"]]
    for request in c["requests"]:
        obs, rows, latest = reader(HERE / "source" / request["key"], request, DEADLINE, clock(s["started_at"]))
        complete = load(HERE / "source" / request["key"] / "complete.json")
        assert complete["capture_context"] == result["context"]
        assert latest <= clock(complete["completed_at"]) <= clock(result["completed_capture_at"])
        assert clock(result["completed_capture_at"]) <= clock(load(HERE / "source/completed.json")["completed_at"])
        objects[request["key"]] = obs
        consumed += rows
    expected = {"started.json", "context.json", "output.json", "seal.json", "completed.json"} | {r["key"] for r in c["requests"]}
    assert {p.name for p in (HERE / "source").iterdir()} == expected
    return dict(objects=objects, consumed=consumed,
                completed_at=load(HERE / "source/completed.json")["completed_at"])


def child_source_fetch_guard(expected_context):
    """One reviewed child/date appendix only; never replay original source01."""
    from h5_common import receive_amendment
    authority()
    kernel("child-source")
    guard_write()
    receive_amendment()
    c = load(checked(expected_context, HERE / "child-source/context.json"))
    s = load(checked(c["started"], HERE / "child-source/started.json"))
    receive_go(s["go"])
    assert c["task_id"] == TASK_ID and s["go"]["request"]["stage"] == "child-source"
    assert c["go"] == s["go"]
    assert c["plan"] == binding(HERE / "child-source-plan.json")
    assert c["amendment"] == binding(HERE / "current-input-amendment.json")
    assert c["original_source_complete"] == binding(HERE / "source/completed.json")
    assert c["requests"] == load(HERE / "child-source-plan.json")["requests"]
    assert clock(s["started_at"]) <= clock(c["created_at"]) <= clock(now()) < clock(DEADLINE)
    assert not (HERE / "child-source/completed.json").exists()
    return None


def collect_child_source(*, fetch):
    if (HERE / "child-source/completed.json").exists():
        return receive_child_source()
    s = start("child-source", binding(HERE / "source/output.json"))
    requests = copy.deepcopy(load(HERE / "child-source-plan.json")["requests"])
    assert len(requests) == 1 and requests[0]["params"]["symbols"] == "VYLR"
    guard_write()
    save(HERE / "child-source/context.json", dict(task_id=TASK_ID,
        started=binding(HERE / "child-source/started.json"), go=s["go"],
        plan=binding(HERE / "child-source-plan.json"), amendment=binding(HERE / "current-input-amendment.json"),
        original_source_complete=binding(HERE / "source/completed.json"), requests=requests, created_at=now()))
    context = binding(HERE / "child-source/context.json")
    writer = pure_function(FUTURE / "source_writer.py", "capture_request")
    def bounded(endpoint, params, timeout):
        child_source_fetch_guard(context)
        return fetch(endpoint, params, timeout)
    writer(HERE / "child-source/child-mark", requests[0], DEADLINE, bounded,
           clock("2026-10-19T00:00:00Z"), context)
    child_source_fetch_guard(context)
    retained = sum(p.stat().st_size for p in (HERE / "child-source").rglob("*") if p.is_file())
    assert retained + 65536 <= load(HERE / "child-source-plan.json")["maximum_complete_capture_and_native_estimate_bytes"], "Complete child capture retained; declared footprint exceeded, refuse downstream"
    return finish("child-source", dict(context=context, requests=requests,
        original_source_complete=binding(HERE / "source/completed.json"), completed_capture_at=now()))


def receive_child_source():
    import math
    result = receive_stage("child-source")
    context = load(checked(result["context"], HERE / "child-source/context.json"))
    s = load(checked(context["started"], HERE / "child-source/started.json"))
    plan = load(HERE / "child-source-plan.json")
    assert context["go"] == s["go"] and context["plan"] == binding(HERE / "child-source-plan.json")
    assert context["amendment"] == binding(HERE / "current-input-amendment.json")
    assert result["requests"] == context["requests"] == plan["requests"]
    assert context["original_source_complete"] == result["original_source_complete"] == binding(HERE / "source/completed.json")
    reader = pure_function(FUTURE / "source_contract.py", "pages")
    objects, consumed, latest = reader(HERE / "child-source/child-mark", plan["requests"][0], DEADLINE, clock(s["started_at"]))
    complete = load(HERE / "child-source/child-mark/complete.json")
    assert complete["capture_context"] == result["context"]
    assert latest <= clock(complete["completed_at"]) <= clock(result["completed_capture_at"])
    bars = []
    for page in objects:
        assert type(page) is dict and type(page["bars"]) is dict and set(page["bars"]) == {"VYLR"}
        assert type(page["bars"]["VYLR"]) is list
        bars += page["bars"]["VYLR"]
    assert len(bars) == 1
    raw = bars[0]
    assert clock(raw["t"]) == clock("2026-10-01T04:00:00Z")
    assert all(type(raw[k]) in [int, float] and math.isfinite(raw[k]) and raw[k] > 0 for k in ["o", "c"])
    assert all(type(raw[k]) in [int, float] and math.isfinite(raw[k]) and raw[k] >= 0 for k in ["v", "n"])
    assert int(raw["n"]) == raw["n"] and not (raw["v"] == 0 and raw["n"] == 0)
    assert {p.name for p in (HERE / "child-source").iterdir()} == {"started.json", "context.json", "child-mark", "output.json", "seal.json", "completed.json"}
    return dict(symbol="VYLR", day="2026-10-01", raw=raw, consumed=[result["context"]] + consumed,
        source=binding(HERE / "child-source/output.json"), completed=binding(HERE / "child-source/completed.json"),
        completed_at=load(HERE / "child-source/completed.json")["completed_at"])
