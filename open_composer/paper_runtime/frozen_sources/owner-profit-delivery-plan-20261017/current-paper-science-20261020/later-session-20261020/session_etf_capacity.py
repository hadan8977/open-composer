"""Prospective ETF-only384MiB/science20 reception; saved four-route proofs stay unchanged."""
import os
from pathlib import Path

import session_common as old

ROOT, prior = old.ROOT, old.prior
TASK = "SIX-PAPER-CURRENT-SESSION-COMPLETION-20261020"
OPS = prior.REPO / "reports/ops/disk-audit-20261015"
RECEIPT = OPS / "capacity-six-current-session-whole384MiB-M3-corrected-admission-20261020.json"
RECEIPT_SHA = "46ae769194f5131e5f299031e4077cbd9e26210c48c2d381c7aa775ec61efe01"
PROPOSAL_SHA = "f91c5438919c7fe08e62da5d9cfde345d5f2bffca2e45462087a1b0bbc15c3bc"


def receive_capacity_context(context_row=None, review_row=None):
    if context_row is None:
        pointer = old.load(ROOT / "ETF-capacity-pointer.json")
        assert pointer["task_id"] == old.TASK and pointer["session_id"] == old.SESSION
        context_row, review_row = pointer["version"], old.binding(pointer["review_path"])
    context_path, review_path = [prior.canonical(row["path"]) for row in [context_row, review_row]]
    assert context_path.parent == review_path.parent == ROOT
    assert context_path.name.startswith("ETF-capacity-context-") and context_path.suffix == ".json"
    assert review_path.name.startswith("independent-ETF-capacity-reception-") and review_path.suffix == ".json"
    c, review = [old.load(old.checked(row)) for row in [context_row, review_row]]
    assert review["task_id"] == c["task_id"] == old.TASK
    assert review["session_id"] == c["session_id"] == old.SESSION
    assert review["reviewer"] == old.PEER and review["independent"] is True
    assert review["accepted"] is True and review["target"] == context_row
    receipt = old.load(old.checked(c["receipt"], RECEIPT))
    assert c["receipt"]["sha256"] == RECEIPT_SHA
    assert receipt["task_id"] == c["aggregate_task_id"] == TASK
    assert receipt["admitted"] is receipt["capacity_only"] is True
    assert receipt["decision"] == "admitted_capacity_only" and receipt["replaces_instead_of_adding"] is True
    proposal = old.load(old.checked(c["aggregate_proposal"], prior.OPERATING / "current-session-six-route-whole-storage-proposal-M3-corrected.json"))
    assert c["aggregate_proposal"]["sha256"] == PROPOSAL_SHA
    assert receipt["request_bindings"]["actual_six_route_current_session_whole_route_proposal"] == c["aggregate_proposal"]
    assert proposal["task_id"] == TASK
    assert type(c["whole_cap_bytes"]) is int and c["whole_cap_bytes"] == receipt["accepted_whole_route_peak_bytes"] == proposal["total_whole_route_peak_bytes"] == 402653184
    guard = receipt["guard_contract"]
    assert guard["receipt_task_id"] == TASK
    assert guard["proposal_binding_field"] == "request_bindings.actual_six_route_current_session_whole_route_proposal"
    assert guard["accepted_peak_field"] == "accepted_whole_route_peak_bytes"
    roots = c["aggregate_owned_roots"]
    assert roots == receipt["owned_roots"] == guard["required_roots"] == proposal["owned_roots"]
    assert roots == [row["root"] for row in proposal["current_root_allocation"]]
    paths = [prior.canonical(p) for p in roots]
    assert len(set(paths)) == 16 and all(str(p) == r for p, r in zip(paths, roots))
    assert all(not a.is_relative_to(b) for a in paths for b in paths if a != b)
    component = receipt["accepted_scientific_component"]
    assert component["task_id"] == old.TASK and component["replaces12_not_independent20_plus12"] is True
    assert component["proposal"] == c["scientific_completion_proposal"] == old.binding(ROOT / "component-storage-completion-proposal-M2.json")
    assert c["scientific_completion_proposal"]["sha256"] == "4b7a2180ff708ef0306a967772640cacd675e94e2b7606c506b739f95dc783c8"
    assert receipt["request_bindings"]["actual_complete_scientific_completion_proposal"] == c["scientific_completion_proposal"] == proposal["scientific_completion_proposal"]
    assert c["scientific_owned_roots"] == component["scientific_owned_roots"] == [str(prior.HERE)] and prior.HERE in paths
    assert type(c["scientific_cap_bytes"]) is int and c["scientific_cap_bytes"] == component["accepted_whole_route_peak_bytes"] == guard["scientific_peak_bytes"] == 20971520
    assert c["scientific_outside_once_bytes"] == 1048576 and guard["scientific_outside1MiB_inside_component_once"] is True
    assert c["aggregate_outside_once_bytes"] == 3145728 and guard["aggregate_outside3MiB_inside_aggregate_once"] is True
    assert c["accepted_child_implementation_plan"] == receipt["request_bindings"]["actual_composite_child_implementation_PLAN_only"]
    old.checked(c["accepted_child_implementation_plan"])
    assert c["accepted_child_implementation_plan"]["sha256"] == "3fc1be845264a36ec9af1d123916cfdcaca95f47e9cc393396a22164130382c8"
    assert c["Main_source_child_resolution"] == receipt["request_bindings"]["Main_source_child_order_resolution"]
    old.checked(c["Main_source_child_resolution"], prior.OPERATING / "main-source-child-prerequisite-resolution.json")
    assert c["Main_source_child_resolution"]["sha256"] == "8af2c6faa2572fb2fa1d0c02080c3296bc4c1570b8081af9dc7029c2aadc2494"
    assert c["normal_reception_original_capacity"] == receipt["request_bindings"]["preserved_M2_capacity"]
    assert c["normal_reception_original_capacity"]["sha256"] == "49f69733d03f50408664971425219370f9c4a1e02d38c6f521d0ed04324842cb"
    old.checked(c["normal_reception_original_capacity"])
    assert guard["current_normal_context_field"] == "request_bindings.postpublication_normal_context"
    assert guard["current_normal_forecast_field"] == "request_bindings.postpublication_complete_normal"
    assert c["postpublication_reception"] == receipt["request_bindings"]["postpublication_normal_context"]
    normal = old.load(old.checked(c["normal_forecast"]))
    assert c["normal_forecast"] == receipt["request_bindings"]["postpublication_complete_normal"] == receipt["complete_paper_forecast"]["receipt"]
    receive_normal_lineage(c, normal)
    protected = normal["required_available_bytes"]
    assert type(protected) is int and protected == receipt["complete_paper_forecast"]["required_available_bytes"] == 10919282270
    assert len(normal["enabled_upstream_tables"]) == 11 and len(normal["live_stages"]) == 7
    assert normal["spill_and_service_already_included_once"] is True
    facts = receipt["current_physical_fact"]
    for key, task, cap, field in [("CASH", "CASH-BACKED-EARNINGS-INFORMATION-20261019", 12582912, "accepted_whole_route_peak_bytes"), ("SIP", "QUANT1-SIP-CURRENT-DAILY-RECOVERY-20261020", 1073741824, "accepted_incremental_stage_peak_bytes")]:
        other = old.load(old.checked(c[key + "_receipt"]))
        assert other["task_id"] == task and other["admitted"] is True and other["capacity_only"] is True
        assert other[field] == c[key + "_full_bytes"] == cap
    assert facts["CASH_FULL_future12MiB_bytes"] == c["CASH_full_bytes"]
    assert facts["SIP_FULL_future1GiB_bytes"] == c["SIP_full_bytes"]
    assert facts["paper_FULL_future384MiB_bytes"] == c["whole_cap_bytes"] and facts["complete_current_normal_bytes"] == protected
    assert c["terminal_once_bytes"] == facts["terminal_once_bytes"] == 65536
    assert c["Astra_remaining_bytes"] == facts["Astra_once_bytes"] == 12288
    old.checked(c["Astra_receipt"])
    assert facts["required_available_bytes"] == protected + c["whole_cap_bytes"] + c["CASH_full_bytes"] + c["SIP_full_bytes"] + 65536 + 12288 == 12408338014
    assert facts["physical_credits_used_bytes"] == c["physical_credit_bytes"] == 0
    assert c["logical_credit_is_not_physical_credit"] is c["fresh_normal_after_source02_required"] is True
    job = old.load(old.checked(c["source02_job"]))
    assert job["invocation_id"] == "quant1-sip-daily-20261020-02"
    assert prior.canonical(c["source02_completed_path"]) == prior.canonical(job["output"]) / "source-completed.json"
    return c, normal, context_row, review_row


def receive_normal_lineage(c, normal):
    """Receive the actual post-Source02 complete forecast without source replay."""
    path = prior.canonical(c["normal_forecast"]["path"])
    if path.parent == OPS:
        return  # Historical admitted forecasts keep their original provenance.
    post = prior.OPERATING / "quant1-SIP-guarded-stage/M4/postsource-reception-02"
    assert path == post / "complete-normal-forecast.json"
    assert c["normal_forecast"]["sha256"] == "d2898c5922a0967230d005796487fc55d8e26b239328417e6e671c5f745b0d93"
    factual = old.load(old.checked(c["postpublication_reception"], OPS / "capacity-M2-postpublication-Source02-normal-reception-20261020.json"))
    assert c["postpublication_reception"]["sha256"] == "64359741ffaf618200adbd5853b4aaadf3cb23ce44f2d78f4b93ee1a859f8ee4"
    assert factual["task_id"] == TASK and factual["capacity_only"] is True
    assert factual["existing_capacity_admission_unchanged"] is True and factual["new_admission_requested_or_created"] is False
    assert factual["existing_M2_capacity_receipt"] == c["normal_reception_original_capacity"]
    mapping = factual["runtime_reception_mapping"]
    assert mapping["capacity_receipt_remains"] == c["normal_reception_original_capacity"]
    assert mapping["current_normal_forecast_to_receive"] == c["normal_forecast"]
    assert mapping["postsource_outcome_to_receive"] == c["postsource_outcome"]
    assert mapping["source_metadata_inventory_to_reference_without_copy"] == c["source02_current_inventory"]
    outcome = old.load(old.checked(c["postsource_outcome"], post / "actual-source-outcome.json"))
    assert c["postsource_outcome"]["sha256"] == "5784d56d2c49a53e144e4d6416971c67aa51f6419ad1f9a93ba55613a196eead"
    assert outcome["task_id"] == "QUANT1-SIP-CURRENT-DAILY-RECOVERY-20261020"
    assert outcome["job"] == c["source02_job"] and outcome["complete_normal_forecast"] == c["normal_forecast"]
    assert outcome["source_completed"] == c["source02_completed"]
    done = old.load(old.checked(c["source02_completed"], c["source02_completed_path"]))
    assert done["job"] == c["source02_job"] and done["status"] == "source_stage_complete" and done["exit"] == 0
    assert outcome["all_latest_published_hashes_match"] is True
    assert outcome["current_source_inventory"] == c["source02_current_inventory"]
    old.checked(c["source02_current_inventory"])
    assert outcome["source_retried"] is False and outcome["new_provider_calls"] == 0
    assert old.clock(done["at"]) <= old.clock(normal["at_utc"]) <= old.clock(outcome["at"]) <= old.clock(old.now())
    assert normal["required_available_bytes"] == outcome["normal_required_bytes"] == 10919282270


def source02_publication(c, normal):
    """A completed writer needs a new complete normal forecast; never signal it."""
    path = prior.canonical(c["source02_completed_path"])
    if not path.exists():
        return None
    complete = old.load(path)
    assert complete["job"] == c["source02_job"] and complete["status"] == "source_stage_complete" and complete["exit"] == 0
    assert old.clock(complete["at"]) <= old.clock(normal["at_utc"]), "SIP published: receive genuinely refreshed complete normal before dependent use"
    return old.binding(path)


def guard_write():
    c, normal, context_row, review_row = receive_capacity_context()
    publication = source02_publication(c, normal)
    own = prior.allocated(c["scientific_owned_roots"])
    route = prior.allocated(c["aggregate_owned_roots"])
    assert own + c["scientific_outside_once_bytes"] <= c["scientific_cap_bytes"]
    assert route + c["aggregate_outside_once_bytes"] <= c["whole_cap_bytes"]
    fs = os.statvfs(prior.REPO)
    free = fs.f_bavail * fs.f_frsize
    required = normal["required_available_bytes"] + c["whole_cap_bytes"] + c["CASH_full_bytes"] + c["SIP_full_bytes"] + c["terminal_once_bytes"] + c["Astra_remaining_bytes"]
    assert free >= required, "Whole-session capacity lost; retain full partials and refuse dependent use"
    return dict(context=context_row, review=review_row, receipt=c["receipt"], actual_at=old.now(),
        free_bytes=free, required_available_bytes=required, protected_normal_bytes=normal["required_available_bytes"],
        route_allocated_bytes=route, scientific_allocated_bytes=own,
        route_logical_remaining_bytes=c["whole_cap_bytes"]-route-c["aggregate_outside_once_bytes"],
        physical_credit_bytes=0, margin_bytes=free-required, source02_completed=publication)


def receive_capacity_proof(proof):
    c, normal, _, _ = receive_capacity_context(proof["context"], proof["review"])
    assert proof["receipt"] == c["receipt"] and proof["protected_normal_bytes"] == normal["required_available_bytes"]
    for key in ["free_bytes", "required_available_bytes", "route_allocated_bytes", "scientific_allocated_bytes", "route_logical_remaining_bytes", "physical_credit_bytes", "margin_bytes"]:
        assert type(proof[key]) is int and proof[key] >= 0
    assert proof["physical_credit_bytes"] == 0
    assert proof["scientific_allocated_bytes"] <= proof["route_allocated_bytes"]
    assert proof["scientific_allocated_bytes"] + c["scientific_outside_once_bytes"] <= c["scientific_cap_bytes"]
    assert proof["route_logical_remaining_bytes"] == c["whole_cap_bytes"]-proof["route_allocated_bytes"]-c["aggregate_outside_once_bytes"]
    assert proof["required_available_bytes"] == normal["required_available_bytes"] + c["whole_cap_bytes"] + c["CASH_full_bytes"] + c["SIP_full_bytes"] + c["terminal_once_bytes"] + c["Astra_remaining_bytes"]
    assert proof["margin_bytes"] == proof["free_bytes"]-proof["required_available_bytes"]
    assert old.clock(c["created_at"]) <= old.clock(proof["actual_at"]) <= old.clock(old.now())
    if proof["source02_completed"] is not None:
        done = old.load(old.checked(proof["source02_completed"], c["source02_completed_path"]))
        assert done["job"] == c["source02_job"] and done["status"] == "source_stage_complete" and done["exit"] == 0
        assert old.clock(done["at"]) <= old.clock(normal["at_utc"]) <= old.clock(proof["actual_at"])
