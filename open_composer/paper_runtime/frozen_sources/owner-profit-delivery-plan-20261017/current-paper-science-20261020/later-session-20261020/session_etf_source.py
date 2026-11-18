"""Finite current ETF input source; independent source and transport reviews first."""
import ast
import copy
import json
import os
import sys

import session_etf_common as c

PLAN = c.ROOT / "ETF-source-plan.json"
SOURCE_STAGE = "ETF-source02"
RECOVERY_PLAN = c.ROOT / "ETF-source-recovery-plan-02.json"
FUTURE = c.prior.PARENT / "candidate-contribution/future-input-receiver"


def receive_source_recovery(proof=None):
    """New invocation after proven pre-HTTP failure; original prefix is retained."""
    scope = receive_source_reviews()
    if proof is None:
        proof = dict(plan=c.binding(RECOVERY_PLAN), review=scope["review"], received_at=c.now())
    plan = c.load(c.checked(proof["plan"], RECOVERY_PLAN))
    review = c.load(c.checked(proof["review"]))
    assert proof["review"] == scope["review"]
    assert review["source_recovery_accepted"] is True and review["source_recovery_plan"] == proof["plan"]
    assert plan["task_id"] == c.TASK and plan["session_id"] == c.SESSION
    assert plan["attempt"] == "02" and plan["new_source_stage"] == SOURCE_STAGE == "ETF-source02"
    assert plan["failed_source_stage"] == "ETF-source"
    assert plan["source_plan"] == c.binding(PLAN)
    assert plan["contract"] == c.binding(c.ROOT / "current-session-contract.json")
    assert plan["same_three_request_families"] is True
    assert plan["completed_physical_requests_to_replay"] == 0 and plan["retained_logical_intent_count"] == 1
    assert plan["absolute_source_cutoff"] == c.contract()["calendar"]["publish_before"]
    assert plan["HTTP_timeout_seconds_max"] == 15
    assert plan["shared_transport_immutable"] == c.binding(c.prior.REPO / "open_composer/intraday_runner/source_input_transport.py")
    for row in plan["failed_prefix"]:
        c.checked(row)
    event = c.load(c.checked(plan["failed_event"], c.ROOT / "ETF-source-exit.json"))
    diagnosis = c.load(c.checked(plan["failure_diagnosis"]))
    assert event["exit_code"] == 1 and event["completed"] is None
    assert diagnosis["physical_provider_GET_calls"] == 0 and diagnosis["capture_logical_intents"] == 1
    assert not (c.ROOT / "ETF-source/completed.json").exists()
    pid = c.prior.Path("/proc") / str(plan["actual_failed_child_PID"]) / "stat"
    if pid.exists():
        assert int(pid.read_text().rsplit(")", 1)[1].split()[19]) != plan["actual_failed_child_start_ticks"], "Original owned worker still alive"
    assert c.clock(event["actual_exit_at"]) <= c.clock(plan["created_at"]) <= c.clock(proof["received_at"]) <= c.clock(c.now())
    return proof


def receive_child_plan_identity(proof=None):
    """Receive the real source-only plan acceptance; working books stay separate."""
    root = c.prior.OPERATING
    plan_path = root / "current-session-composite-child-implementation-plan-M2.json"
    review_path = root / "independent-current-session-composite-child-plan-review-66ad.json"
    if proof is None:
        proof = dict(plan=c.binding(plan_path), review=c.binding(review_path), received_at=c.now())
    plan = c.load(c.checked(proof["plan"], plan_path))
    review = c.load(c.checked(proof["review"], review_path))
    assert proof["plan"]["sha256"] == "3fc1be845264a36ec9af1d123916cfdcaca95f47e9cc393396a22164130382c8"
    assert proof["review"]["sha256"] == "d2f80ddef0539508fd4f816f383d0a22b36d28d4f5e2e12c2e670ee2fdfd9a5b"
    assert plan["task_id"] == review["task_id"] == "SIX-PAPER-CURRENT-SESSION-COMPLETION-20261020"
    assert review["scientific_task_id"] == c.TASK
    assert plan["scientific_session_id"] == review["scientific_session_id"] == c.SESSION
    assert review["reviewer"] == "66ad4b54-ec62-400b-9a03-a29682cf58e6" and review["independent"] is True
    assert review["verdict"] == "approve_implementation" and review["target"] == proof["plan"]
    assert review["review_kind"] == "implementation_plan_identity_only"
    assert review["accepted_for_source_plan_identity"] is review["accepted_for_implementation_plan_only"] is True
    for key in ["accepted_for_current_composite_children", "actual_runtime_or_funding_accepted", "actual_child_runtime_accepted", "actual_funding_initialized", "actual_child_books_initialized", "source_go"]:
        assert review[key] is False
    assert plan["source_plan_identity_review_only"] is True
    for key in ["actual_child_runtime_accepted", "actual_child_books_initialized", "actual_parent_funding", "source_go"]:
        assert plan[key] is False
    assert plan["actual_operating_implementation"] is None
    assert plan["source_plan"] == review["source_plan"] == c.binding(PLAN)
    assert plan["scientific_contract"] == review["scientific_contract"] == c.binding(c.ROOT / "current-session-contract.json")
    assert plan["Main"] == review["Main"] == c.binding(root / "main-source-child-prerequisite-resolution.json")
    assert plan["Main"]["sha256"] == "8af2c6faa2572fb2fa1d0c02080c3296bc4c1570b8081af9dc7029c2aadc2494"
    assert review["bindings"]["plan"] == proof["plan"]
    assert plan["actual_account_hash"] == review["actual_account_hash"]
    assert len(plan["actual_account_hash"]) == 64
    assert set(plan["parents"]) == {"MULTI_EQUAL", "MULTI_HIERARCHICAL"}
    names = []
    for policy, cents in [("MULTI_EQUAL", [333334,333334,333333,333333,333333,333333]), ("MULTI_HIERARCHICAL", [166667,166667,166666,500000,500000,500000])]:
        parent = plan["parents"][policy]
        assert parent["account_hash"] == plan["actual_account_hash"]
        assert parent["parent_capital_USD"] == 20000 and parent["parent_includes_children"] is True
        children = parent["children"]
        assert [x["policy"] for x in children] == ["S1", "S2", "S3", "C2", "BASE", "H5"]
        assert [x["child_code"] for x in children] == ["S1", "S2", "S3", "C2", "B", "H"]
        assert all(type(x["initial_cents"]) is int for x in children)
        assert [x["initial_cents"] for x in children] == cents and sum(cents) == 2000000
        for child in children:
            assert child["namespace"] == parent["namespace"] + "-" + child["child_code"]
            assert child["identity_mode"] == "new_independent_composite_child"
            assert child["old_legacy_book_or_stop_reset"] is False
            assert child["actual_funding_initialized"] is False
            assert child["prospective_atomic_child_key"] == child["policy"]
            for key in ["current_NAV", "HWM", "stopped", "book_receipt", "cash_lots_AR_AP_fees_rights_receipt", "risk_stop_receipt"]:
                assert child[key] is None
            names.append(child["namespace"])
    assert len(set(names)) == 12
    assert c.clock(plan["captured_at"]) <= c.clock(review["at_utc"]) <= c.clock(proof["received_at"]) <= c.clock(c.now())
    return proof


def receive_source_reviews():
    path = c.ROOT / "ETF-source-implementation-manifest.json"
    mf = c.load(path)
    review_path = c.ROOT / "independent-ETF-source-review.json"
    review = c.load(review_path)
    assert mf["task_id"] == review["task_id"] == c.TASK and mf["session_id"] == review["session_id"] == c.SESSION
    assert review["reviewer"] == c.PEER and review["independent"] is True
    assert review["verdict"] == "approve_source_implementation" and review["source_contract_accepted"] is True
    assert review["accepted_for_current_scientific_component"] is True
    assert review["target"] == c.binding(path) and review["source_plan"] == c.binding(PLAN)
    assert mf["source_plan"] == c.binding(PLAN) and mf["contract"] == c.binding(c.ROOT / "current-session-contract.json")
    assert mf["files"] and len({r["path"] for r in mf["files"]}) == len(mf["files"])
    for row in mf["files"]:
        c.checked(row)
    return dict(manifest=c.binding(path), review=c.binding(review_path))


def receive_transport():
    root = c.prior.OPERATING
    manifest_path = root / "current-session-etf-source-transport-manifest.json"
    review_path = root / "independent-current-session-etf-source-transport-review-66ad.json"
    manifest, review = c.load(manifest_path), c.load(review_path)
    assert manifest["task_id"] == review["task_id"] == c.TASK
    assert review["reviewer"] == "66ad4b54-ec62-400b-9a03-a29682cf58e6" and review["independent"] is True
    assert review["verdict"] == "approve_implementation" and review["accepted_for_source_transport"] is True
    assert review["target"] == c.binding(manifest_path)
    assert review["verification"]["source_plan"] == c.binding(PLAN)
    assert review["bindings"]["scientific_manifest"] == receive_source_reviews()["manifest"]
    assert review["bindings"]["manifest"] == c.binding(manifest_path)
    assert manifest["scientific_manifest"] == receive_source_reviews()["manifest"]
    expected = root / "current_session_etf_source_transport.py"
    rows = manifest["files"]
    assert rows and len({r["path"] for r in rows}) == len(rows)
    for row in rows:
        c.checked(row)
    assert c.binding(expected) in rows and c.binding(__file__) in rows and c.binding(PLAN) in rows
    return dict(module=c.binding(expected), manifest=c.binding(manifest_path), review=c.binding(review_path))


def receive_context(expected_context, output=None):
    """Exact completed/active source context, shared by guard and receiver."""
    scope = receive_source_reviews()
    d = c.ROOT / SOURCE_STAGE
    context = c.load(c.checked(expected_context, d / "context.json"))
    assert context["task_id"] == c.TASK and context["session_id"] == c.SESSION
    assert context["source_plan"] == c.binding(PLAN) and context["scientific_source_code"] == scope
    assert context["requests"] == c.load(PLAN)["requests"]
    assert context["contract"] == c.binding(c.ROOT / "current-session-contract.json")
    assert context["transport"] == receive_transport()
    plan_identity = receive_child_plan_identity(context["child_plan_identity"])
    started, native = c.receive_native(SOURCE_STAGE)
    assert c.clock(plan_identity["received_at"]) <= c.clock(native["at"])
    recovery = receive_source_recovery(context["source_recovery"])
    assert native["input"] == recovery["plan"]
    assert c.clock(recovery["received_at"]) <= c.clock(native["at"])
    claim = c.load(d / "worker-started.json")
    assert context["started"] == c.binding(d / "started.json") and context["worker"] == c.binding(d / "worker-started.json")
    assert context["invocation"] == claim["invocation"] == native["invocation"]
    assert claim["process"] == native["process"] and claim["stage"] == SOURCE_STAGE
    assert claim["session_id"] == c.SESSION and claim["task_id"] == c.TASK
    assert claim["started"] == context["started"] and claim["native"] == started["native"]
    assert context["code"] == native["code"]
    assert c.clock(started["started_at"]) <= c.clock(claim["claimed_at"]) <= c.clock(context["created_at"]) <= c.clock(c.now())
    assert context["source_cutoff"] == c.contract()["calendar"]["publish_before"]
    if output is not None:
        assert output["context"] == expected_context and output["source_plan"] == context["source_plan"]
        assert output["scientific_source_code"] == scope
        assert c.clock(context["created_at"]) <= c.clock(output["computed_started_at"]) <= c.clock(output["computed_completed_at"]) <= c.clock(context["source_cutoff"])
    return context


def source_fetch_guard(expected_context):
    c.authority()
    c.kernel(SOURCE_STAGE)
    c.guard_write()
    c.reviews()
    context = receive_context(expected_context)
    c.computing(SOURCE_STAGE)
    assert c.clock(c.now()) < c.clock(context["source_cutoff"])
    return None


def upstream(path, name):
    code = c.load(c.checked(receive_source_reviews()["manifest"]))
    assert c.binding(path) in code["files"]
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(nodes) == 1
    def payload(path):
        p = c.prior.canonical(path)
        assert p.is_relative_to(c.ROOT / SOURCE_STAGE)
        return json.loads(p.read_text())
    namespace = dict(canonical=c.prior.canonical, binding=c.binding, checked=c.checked, load=payload,
        clock=c.clock, now=c.now, save=c.save, json=json, os=os)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"), namespace)
    return namespace[name]


def collect():
    c.authority()
    c.kernel(SOURCE_STAGE)
    code = receive_source_reviews()
    transport = receive_transport()  # Receive exact external closure BEFORE import/construction.
    plan_identity = receive_child_plan_identity()  # Real accepted PLAN only; no account/book call.
    recovery = receive_source_recovery()
    inventory = copy.deepcopy(c.load(PLAN)["requests"])
    started = c.start(SOURCE_STAGE, c.binding(RECOVERY_PLAN))
    claim = c.claim_worker(SOURCE_STAGE)
    d = c.ROOT / SOURCE_STAGE
    context = dict(task_id=c.TASK, session_id=c.SESSION, source_plan=c.binding(PLAN), scientific_source_code=code,
        requests=inventory, contract=c.binding(c.ROOT / "current-session-contract.json"),
        transport=transport, child_plan_identity=plan_identity, source_recovery=recovery, started=c.binding(d / "started.json"), worker=c.binding(d / "worker-started.json"),
        invocation=claim["invocation"], code=c.load(c.checked(started["native"]))["code"], created_at=c.now(),
        source_cutoff=c.contract()["calendar"]["publish_before"])
    c.save(d / "context.json", context)
    context_binding = c.binding(d / "context.json")
    source_fetch_guard(context_binding)
    module = c.prior.module("actual_new_session_etf_transport", c.checked(transport["module"]))
    adapter = module.CurrentSessionETFSourceTransport()
    begin = c.now()
    try:
        capture = upstream(FUTURE / "source_writer.py", "capture_request")
        complete = {request["key"]: capture(d / "captures" / request["key"], request, context["source_cutoff"],
            adapter.fetch, c.clock(context["created_at"]), context_binding) for request in inventory}
    finally:
        adapter.close()
    source_fetch_guard(context_binding)
    return c.finish(SOURCE_STAGE, dict(policy="ETF-source", source_plan=c.binding(PLAN), scientific_source_code=code,
        context=context_binding, captures=complete, source_only=True, new_fit_count=0, new_label_count=0,
        computed_started_at=begin, computed_completed_at=c.now()))


def receive_sources():
    output = c.receive_stage(SOURCE_STAGE)
    d = c.ROOT / SOURCE_STAGE
    context = receive_context(output["context"], output)
    assert set(output["captures"]) == {request["key"] for request in context["requests"]}
    pages = upstream(FUTURE / "source_contract.py", "pages")
    objects, consumed = {}, [output["context"], output["source_plan"], context["child_plan_identity"]["plan"], context["child_plan_identity"]["review"], context["source_recovery"]["plan"], context["source_recovery"]["review"]]
    for request in context["requests"]:
        folder = d / "captures" / request["key"]
        assert output["captures"][request["key"]] == c.binding(folder / "complete.json")
        assert c.load(folder / "complete.json")["capture_context"] == output["context"], "Request belongs to a foreign source context"
        values, bindings, latest = pages(folder, request, context["source_cutoff"], c.clock(context["created_at"]))
        assert c.clock(context["created_at"]) <= latest <= c.clock(output["computed_completed_at"])
        objects[request["key"]] = values
        consumed += bindings
    return dict(objects=objects, consumed=consumed, source=c.binding(d / "output.json"), source_complete=c.binding(d / "completed.json"),
        source_completed_at=c.load(d / "completed.json")["completed_at"], context=output["context"], source_plan=output["source_plan"])


if __name__ == "__main__":
    assert len(sys.argv) == 1
    collect()
