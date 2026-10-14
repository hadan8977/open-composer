"""Bind the accepted science to one concrete initial-input allocation decision."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
REV = BASE / "revisions/v2"
OUT = BASE / "acquisition"
AUTHOR = "f9add224-744b-471c-b812-c43cc179fa38"


def load(path):
    return json.loads(path.read_text())


def dump(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def bound(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main():
    now = datetime.now(UTC).isoformat()
    review = bound(REV / "independent-plan-review.json")
    assert review["sha256"] == "6a20ccdbfd6b80908b0cda39906b1be497828c9668d522acf1e6ddd5b1445f94"
    receipt = load(REV / "independent-plan-review.json")
    assert receipt["verdict"] == "approve_deep_plan" and receipt["author"] != receipt["reviewer"]
    # Only the amended scientific bindings are checked here; do not rescan old source pools.
    for key in ("plan", "state_contract", "evaluation_cells", "paired_comparisons"):
        item = receipt["bindings"][key]
        assert bound(ROOT / item["path"])["sha256"] == item["sha256"]
    assert load(REV / "direction-preflight.json")["status"] == "ok"
    assert load(REV / "campaign-pre-discovery.json")["status"] == "ok"
    assert load(REV / "protocol-verification.json")["actual_network_requests"] == 0

    accounting = load(BASE / "cumulative-accounting.json")
    charge = receipt["resource"]["this_delta_charge_once"]
    charge_path = review["path"]
    if not any(x["receipt"] == charge_path for x in accounting["reviewer_charges"]):
        accounting["reviewer_charges"].append(
            {
                "receipt": charge_path,
                "charge_coreseconds": charge,
                "includes_measured_process_CPU": True,
            }
        )
        accounting["total_conservative_coreseconds"] = round(
            accounting["total_conservative_coreseconds"] + charge, 4
        )
        accounting["remaining_coreseconds"] = round(accounting["remaining_coreseconds"] - charge, 4)
    if not any(
        x["id"] == "initial_input_decision_sealing_setup"
        for x in accounting["unmetered_conservative_charges"]
    ):
        accounting["unmetered_conservative_charges"].append(
            {
                "id": "initial_input_decision_sealing_setup",
                "coreseconds": 10,
                "includes_final_small_metadata_job": True,
            }
        )
        accounting["total_conservative_coreseconds"] = round(
            accounting["total_conservative_coreseconds"] + 10, 4
        )
        accounting["remaining_coreseconds"] = round(accounting["remaining_coreseconds"] - 10, 4)
    accounting.update(as_of_utc=now, reserved_next_independent_review_upper_coreseconds=0)
    dump(BASE / "cumulative-accounting.json", accounting)

    implementation_files = [
        BASE / "code/acquire_components.py",
        BASE / "code/verify_acquisition.py",
        ROOT / "open_composer/adapters/data/alpaca_snapshot.py",
        ROOT / "open_composer/cli.py",
        ROOT / "open_composer/config.py",
    ]
    scope = bound(BASE / "input-and-request-scope.json")
    implementation = {
        "schema_version": 1,
        "author": AUTHOR,
        "request_scope": scope,
        "scientific_plan": bound(REV / "scientific-plan.json"),
        "independent_scientific_review": review,
        "implementation_bindings": [bound(p) for p in implementation_files],
        "factory": "open_composer.adapters.data.alpaca_snapshot._stock_data_client()",
        "transport": "Factory-created HTTP session; local bounded GET stream wrapper",
        "ordinary_interface_diff": (
            "Same13paths/params/GET/host. Accept-Encoding identity and bo"
            "unded stream add entity-prefix stop; no credential inspectio"
            "n, SDK retry, redirect, economic behavior or scope expansion"
            "."
        ),
        "httpx_version": version("httpx"),
        "capability": "market.alpaca_bars",
        "registry_status": (
            "Existing approved, unchanged; registry does not allocate this task's calls"
        ),
        "caps": {
            "objects": 13,
            "requests": 32,
            "entity_bytes": 67108864,
            "bytes_per_page": 2097152,
            "one_CPU": True,
            "memory_MiB": 900,
        },
        "byte_semantics": (
            "Exact complete response entity under existing response.conte"
            "nt convention. At byte cap or stream failure keep uncertifie"
            "d prefix and charge full page reservation. HTTP wire buffers"
            "/overhead unknown separately. No probe past reservation to c"
            "ertify EOF."
        ),
        "failure_policy": (
            "Charge before attempt; preserve status, whitelisted headers,"
            " entity or prefix hash, ordinal and unknown full-page reserv"
            "e.401/403/429 stop; no repeated token, automatic retry or im"
            "plicit rerun/reset."
        ),
        "guard": (
            "Bound Root input-only resource decision and independent appr"
            "oved plan checked before credential initialization. Actual f"
            "resh memory/admission/capped job required at invocation."
        ),
        "execute_command": (
            "python3 scripts/memory_budget.py status && scripts/run_cappe"
            "d.sh --mem 900M --wait-min 0 -- env OPENBLAS_NUM_THREADS=1 O"
            "MP_NUM_THREADS=1 .venv/bin/python reports/research/program/u"
            "sic-practitioner-research-20261013/code/acquire_components.p"
            "y --execute --admission reports/research/program/usic-practi"
            "tioner-research-20261013/acquisition/root-resource-decision."
            "json"
        ),
        "current_allocation": 0,
        "actual_HTTP_requests": 0,
        "economic_execution": False,
        "protocol_verification": bound(REV / "protocol-verification.json"),
    }
    dump(OUT / "implementation-manifest.json", implementation)
    martin = load(
        ROOT / "reports/research/program/martin-luk-usic-20261013/cumulative-accounting.json"
    )
    martin_used = (
        martin["preparation_measured_CPU_seconds"]
        + martin["setup_and_small_reads_unknown_CPU_charge"]
    )
    proposal = {
        "schema_version": 1,
        "task_id": "USIC-PRACTITIONER-RESEARCH",
        "author": AUTHOR,
        "as_of_utc": now,
        "verdict": "proposal_not_allocation",
        "decision_required": (
            "Root's one actual allocation for the independently approved first input tranche"
        ),
        "permission_origin": {
            "path": str((BASE / "brief.md").relative_to(ROOT)),
            "quote": (
                "选定完整定义、独立科学和适用原生/input/resource门后，"
                "明确原Martin条件池是否已有分配及其余量，"
                "不能两条线重复占用同一池。"
            ),
        },
        "bindings": {
            "request_scope": scope,
            "implementation_manifest": bound(OUT / "implementation-manifest.json"),
        },
        "scientific_review": review,
        "recommended_allocation": {
            "requests": 32,
            "entity_bytes": 67108864,
            "preparation_coreseconds": 120,
            "preparation_pool": "Original Martin2000, not new CPU",
            "one_CPU": True,
            "memory_MiB": 900,
        },
        "shared_conditional_pool": {
            "market_requests": 96,
            "entity_bytes": 134217728,
            "economic_coreseconds": 7200,
            "market_used": 0,
            "market_allocated": 0,
            "economic_used": 0,
            "economic_allocated": 0,
            "unallocated_after_proposed_tranche": {
                "market_requests": 64,
                "entity_bytes": 67108864,
                "economic_coreseconds": 7200,
            },
            "no_automatic_remainder_use": True,
        },
        "remaining_original_preparation": {
            "Martin_coreseconds": round(2000 - martin_used, 4),
            "Martin_after_proposed120": round(2000 - martin_used - 120, 4),
            "comparison_coreseconds": accounting["remaining_coreseconds"],
            "comparison_ledger": bound(BASE / "cumulative-accounting.json"),
        },
        "decision_value": [
            "GME2021 source501/order clocks vs observed raw quote context",
            (
                "CSIQ actual2025Dec22 planned25.51/stop25.10/fill26.28 and ex"
                "ecution-risk identifiability"
            ),
            "SMCI known split/raw-vs-all basis; LMND/SOFI sourcechart date ambiguity retained",
            (
                "One-vintage per-name price/volume/clock components and exact"
                " missing action/cash packets"
            ),
        ],
        "deliverable_after_allocation": (
            "Actual immutable entity/ordinal/hash/coverage packet and raw"
            "/all/action/clock reconciliation, accepted price/support com"
            "ponents where identified. Not private full ledger, broadTop5"
            "0 or 120 economic streams. Model reviewer independently rece"
            "ives input semantics before dependent economics."
        ),
        "stopping": [
            "Manifest/page/byte/CPU caps, no author budget expansion",
            "Transport/access/rate failure retained; no credential/provider workaround",
            "Date/basis/rights or quote unknown staysN/A; legalprice components persist",
            "No new firstseen hunt, stock expansion, ROI/P&L, fits or orders",
        ],
        "economic_execution_admitted": False,
        "new_paid_spending": 0,
        "initial_input_take_is_not_method_refutation_or_cohort_change": True,
    }
    dump(BASE / "initial-input-resource-proposal.json", proposal)

    result = {
        "task_id": "USIC-PRACTITIONER-RESEARCH",
        "owner": AUTHOR,
        "as_of_utc": now,
        "outcome": "accepted_scientific_revision_and_concrete_initial_input_resource_decision",
        "scientific_review": review,
        "required_corrections_remaining": [],
        "source_result": (
            "24public decisions/9original images preserved; four practiti"
            "oners compared by mechanism. Martin tight-stop/reentry plus "
            "Flanders feedback/month-risk remains the source-led main stu"
            "dy, not9EMA shallow sweep or private969.8% replication."
        ),
        "actual_local_input_fact": (
            "Seven predeclared stock-days have minute records inclpremark"
            "et;14fileprobes prove all-adjusted schema/clock, not rawcash"
            " or historical broadTop50 readiness. No repeat source-pool s"
            "can."
        ),
        "planned_definition_count": 8,
        "planned_cell_rows": 120,
        "predeclared_duplicate_cells": 6,
        "structural_policy_ceiling": 114,
        "exact_paired_comparisons": 102,
        "actual_economic_return_streams": 0,
        "preparation_validation": {
            "campaign_pre_discovery": "ok",
            "direction": "ok",
            "source_interface_tests_passed": 42,
            "bounded_protocol_cases_passed": 8,
        },
        "resource_proposal": bound(BASE / "initial-input-resource-proposal.json"),
        "accepted_science_is_not_market_allocation": True,
        "full7200_recommended_now": False,
        "market_calls_new": 0,
        "economic_runs": 0,
        "fits": 0,
        "orders": 0,
        "workflow_pass": False,
        "research_pass": False,
        "ml_contribution_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "end_to_end_research_complete": False,
        "next_author_action": (
            "Receive actual first-tranche allocation, continuously execut"
            "e same13objects/caps and ordinary repairs, hand real compone"
            "nt packet directly toee; broadcohort/fullmethod allocation o"
            "nly after actual usefulinput/workload evidence."
        ),
        "economic_values": {
            "return": None,
            "Sharpe": None,
            "drawdown": None,
            "reason": "No admitted/executed economic study",
        },
    }
    dump(BASE / "result.json", result)
    manifest_files = [
        BASE / "result.json",
        BASE / "initial-input-resource-proposal.json",
        OUT / "implementation-manifest.json",
        REV / "independent-plan-review.json",
        REV / "review-bindings.json",
        REV / "scientific-plan.json",
        REV / "state-and-ledger-contract.json",
        REV / "campaign-pre-discovery.json",
        REV / "direction-preflight.json",
        REV / "protocol-verification.json",
        BASE / "cumulative-accounting.json",
    ] + implementation_files[:2]
    manifest = {
        "schema_version": 1,
        "owner": AUTHOR,
        "created_at": now,
        "role": "Initial-input resource decision packet, not acquired market/economic inputs",
        "files": [bound(p) for p in manifest_files],
        "old_evidence": (
            "Dereference immutable v1/v2 review bindings; no original sna"
            "pshot or accepted artifact overwritten"
        ),
        "sealed_before_actual_resource_allocation": True,
        "new_market_entities": 0,
    }
    dump(BASE / "initial-input-decision-manifest.json", manifest)
    state = {
        "task_id": "USIC-PRACTITIONER-RESEARCH",
        "owner": AUTHOR,
        "active_owner": AUTHOR,
        "as_of_utc": now,
        "status": "independent_science_accepted_initial_input_allocation_decision_required",
        "brief": str((BASE / "brief.md").relative_to(ROOT)),
        "Martin_child": "reports/research/program/martin-luk-usic-20261013/current-state.json",
        "result": bound(BASE / "result.json"),
        "decision_manifest": bound(BASE / "initial-input-decision-manifest.json"),
        "scientific_review": review,
        "scientific_plan_approved": True,
        "input_ready": False,
        "economic_execution_admitted": False,
        "definitions": 8,
        "planned_cells": 120,
        "actual_economic_streams": 0,
        "budget_accounting": bound(BASE / "cumulative-accounting.json"),
        "Martin_source_requests_used_cap": [26, 40],
        "comparison_source_requests_used_cap": [24, 64],
        "comparison_CPU_used_remaining": [
            accounting["total_conservative_coreseconds"],
            accounting["remaining_coreseconds"],
        ],
        "market_requests_used_allocated": [0, 0],
        "economic_CPU_used_allocated": [0, 0],
        "proposed_only_input_requests_bytes_CPU": [32, 67108864, 120],
        "active_numeric_job": None,
        "prior_failures_and_budgets_preserved": True,
        "next_action": result["next_author_action"],
    }
    dump(BASE / "current-state.json", state)
    print(
        json.dumps(
            {
                "decision_manifest": bound(BASE / "initial-input-decision-manifest.json"),
                "resource_proposal": bound(BASE / "initial-input-resource-proposal.json"),
                "independent_science_accepted": True,
                "actual_market_allocation": 0,
                "comparison_CPU_used": accounting["total_conservative_coreseconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
