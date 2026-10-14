"""Seal the scientific-plan handoff and extend the original cumulative resource ledger."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
P = Path(__file__).resolve().parent
OLD = P.parent
OWNER = "66ebc2b7-c533-4992-82fe-cece4f3e2b12"


def bind(path):
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def save(name, payload):
    (P / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


at = datetime.now(UTC).isoformat()
reconciliation = json.loads((P / "authority-and-resource-reconciliation.json").read_text())
original = OLD / "completion-resource-ledger.json"
assert bind(original) == reconciliation["inherited_ledger"], "Root ledger changed; reconcile first"
ledger = json.loads(original.read_text())
ledger["continuation_extension"] = {
    "owner": OWNER,
    "at_utc": at,
    "inherits_actual_original_ledger": bind(original),
    "old_ledger_not_overwritten": True,
    "same_pool": True,
    "old_source30_CPU_reservation_retained": True,
}
jobs = [
    ("source-preparation-resource-02.txt", 0),
    ("review-package-build-resource.txt", 0),
    ("direction-check-resource.txt", 0),
    ("preparation-format-resource.txt", 0),
    ("preparation-lint-resource.txt", 1),
    ("preparation-format-resource-02.txt", 0),
    ("preparation-lint-resource-02.txt", 1),
    ("preparation-lint-fix-resource.txt", 0),
    ("preparation-format-resource-03.txt", 0),
    ("preparation-lint-resource-03.txt", 1),
    ("preparation-format-resource-04.txt", 0),
    ("preparation-lint-resource-04.txt", 0),
]
for name, expected_exit in jobs:
    body = (P / name).read_text()
    user = float(re.search(r"User time \(seconds\): ([\d.]+)", body)[1])
    system = float(re.search(r"System time \(seconds\): ([\d.]+)", body)[1])
    actual_exit = int(re.search(r"Exit status: (\d+)", body)[1])
    assert actual_exit == expected_exit
    ledger["entries"].append(
        {
            "job_id": f"hf-exec66-prep-{name.removesuffix('.txt')}",
            "status": "closed",
            "measured_CPU": user + system,
            "charge_CPU": user + system,
            "exit_status": actual_exit,
            "receipt": bind(P / name),
            "scope": "Source/evidence/plan preparation only; no financial simulation or training",
        }
    )
ledger["entries"].extend(
    [
        {
            "job_id": "hf-exec66-plan-static-allowance-01",
            "status": "closed",
            "charge_CPU": 10,
            "measured_CPU": None,
            "nonzero_unmetered_allowance_CPU": 10,
            "scope": (
                "All ordinary reads, writing, plan reasoning support and same-AST literal repair"
            ),
        },
        {
            "job_id": "hf-exec66-plan-seal-conservative-01",
            "status": "closed",
            "charge_CPU": 2,
            "measured_CPU": None,
            "nonzero_unmetered_allowance_CPU": 2,
            "scope": (
                "Conservative cap for final short JSON/link/identity/handoff seal; profile retained"
            ),
        },
    ]
)
charged = ledger["base_conservative_CPU"] + sum(
    row.get("charge_CPU", 0) for row in ledger["entries"]
)
held = sum(row["upper_CPU"] for row in ledger["entries"] if row["status"] != "closed")
assert held == 30 and charged < ledger["cap_CPU"] - held
save("cumulative-resource-ledger.json", ledger)
manifest = json.loads((P / "candidate-manifest-proposed.json").read_text())
plan = json.loads((P / "scientific-plan.json").read_text())
assert manifest["candidate_count"] == len(manifest["candidates"]) == 60
assert len({row["candidate_id"] for row in manifest["candidates"]}) == 60
assert sum(row["planned_funded_views"] for row in manifest["candidates"]) == 120
assert sum(row["optional_independent_4k_views"] for row in manifest["candidates"]) == 36
assert bind(P / "scientific-plan-v1.md") == plan["full_definition"] == manifest["scientific_plan"]
assert bind(P / "candidate-manifest-proposed.json") == plan["candidate_manifest"]
assert bind(P / "direction-review.json") == plan["direction_evidence"]
for row in json.loads((P / "direction-review.json").read_text())["sources"]:
    assert (ROOT / row["snapshot_path"]).is_file()
    assert (ROOT / row["source_card_path"]).is_file()
runtime = json.loads((P / "owner-runtime-readback.json").read_text())
assert runtime["verified"] and runtime["readback_count"] == 1
save(
    "direction-check-receipt.json",
    {
        "at_utc": at,
        "command": (
            "uv run --offline oc research direction-check "
            "reports/research/program/day-goal-20261013/hf-factor-return/"
            "execution-value-continuation/direction-review.json"
        ),
        "actual_stdout": {"status": "ok", "blocked": []},
        "actual_exit_status": 0,
        "actual_tool_result": "exec session84192 completion returned actual stdout and exit0",
        "direction_binding": bind(P / "direction-review.json"),
        "native_resource_receipt": bind(P / "direction-check-resource.txt"),
        "independent_plan_review": "not_run",
        "iteration_gate": "not_run",
        "economic_execution_admitted": False,
    },
)
outputs = [
    "scientific-plan-v1.md",
    "scientific-plan.json",
    "candidate-manifest-proposed.json",
    "direction-review.json",
    "direction-check-receipt.json",
    "policy-source-cards.jsonl",
    "query-manifest.json",
    "pre-iteration-knowledge-baseline.json",
    "owner-runtime-readback.json",
    "local-source-and-preparation-bindings.json",
    "authority-and-resource-reconciliation.json",
    "cumulative-resource-ledger.json",
    "prepare_source_inventory.py",
    "build_review_package.py",
    "seal_plan_handoff.py",
]
save(
    "plan-review-handoff.json",
    {
        "schema_version": 3,
        "task_id": "HF-EXECUTION-VALUE-CONTINUATION-20261014",
        "parent_task_id": "DAY3-HF-FACTOR-RETURN",
        "at_utc": at,
        "owner": OWNER,
        "Root": runtime["parent_agent_id"],
        "status": "decision_ready_plan_owner_retained_turn_yields_slot",
        "summary": [
            (
                "Original full20bp failure and100+5 attribution preserved; "
                "no new training or simulation."
            ),
            "Source5minute separate-horizon DP and quadratic GP are distinguished from this APP.",
            "Existing15minute label expires at original delayed execution; lifetime is decisive.",
            (
                "Three fixed policies,48 information/anchor configurations "
                "plus12 causal risk controls."
            ),
            (
                "Maximum120 new20k books and conditional36 independent4k books, "
                "pending complete review."
            ),
            (
                "Actual source ledger has4units, not stale current-state3; "
                "unknown web andheld30 retained."
            ),
        ],
        "direction_check": "actual_native_ok_only_for_source_evidence",
        "independent_plan_review": "pending",
        "Root_economic_investment_decision": "pending",
        "new_performance": None,
        "financial_simulations": 0,
        "new_market_requests": 0,
        "new_public_source_requests": 0,
        "new_model_training_or_inference": 0,
        "new_broker_or_production_orders": 0,
        "resources": {
            "pool_cap_CPU": ledger["cap_CPU"],
            "inherited_charged_CPU": reconciliation["charged_CPU"],
            "added_conservative_CPU": round(charged - reconciliation["charged_CPU"], 2),
            "current_cumulative_charged_CPU": round(charged, 2),
            "held_CPU": held,
            "uncommitted_remaining_CPU": round(ledger["cap_CPU"] - charged - held, 2),
            "proposed_complete_package_CPU": 5000,
            "proposed_package_reserved_or_admitted": False,
            "source_request_units_used": 4,
            "source_request_units_remaining": 4,
            "direct_source_bytes_used": 586123,
            "unknown_web_bytes_retained": True,
        },
        "checks": {
            "one_actual_preferred_runtime_readback": True,
            "original_ledger_unchanged": True,
            "manifest_counts_and_hash_chain": True,
            "local_source_quotes_and_fetch_bindings": True,
            "prep_python_format_and_lint": (
                "pass_after_same_AST_literal_wrap; initial lint failure charged"
            ),
            "whole_repository_tests": "not_applicable_to_source_plan_preparation",
            "independent_review_not_self_certified": True,
        },
        "review_request": (
            "After P0 review, arrange one complete independent scientific review of plan JSON, "
            "full MD definition, actual source snapshots and inherited negative evidence. "
            "Root/Astra makes final investment admission within the same original pool. "
            "Return accepted package directly to this owner for continuous implementation, "
            "real native gates, funded tests, interpretation and parent continuation."
        ),
        "notification": {
            "route": "this turn's sole native final event to Root",
            "explicit_duplicate_message": False,
            "reviewer_spawned": False,
            "heartbeat_or_model_polling": False,
            "owner_still_holds_parent_question": True,
        },
        "outputs": [bind(P / name) for name in outputs],
    },
)
state_path = P / "current-state.json"
save("current-state-before-owner-plan.json", json.loads(state_path.read_text()))
state = json.loads(state_path.read_text())
state.update(
    {
        "status": "decision_ready_plan_pending_independent_review_owner_retained",
        "owner": OWNER,
        "active_owner": OWNER,
        "parent_question_complete": False,
        "economic_execution_admitted": False,
        "updated_at_utc": at,
        "actual_exec_session": None,
        "actual_job": None,
        "completion_current_CPU": round(charged, 2),
        "completion_reserved_CPU": held,
        "remaining_CPU": round(ledger["cap_CPU"] - charged - held, 2),
        "cumulative_resource_ledger": bind(P / "cumulative-resource-ledger.json"),
        "source_units_used": 4,
        "source_direct_bytes": 586123,
        "source_web_raw_bytes_unknown": True,
        "source_text_extraction_complete": True,
        "model_runtime": {
            **state["model_runtime"],
            "actual_runtime_readback": bind(P / "owner-runtime-readback.json"),
        },
        "scientific_plan": bind(P / "scientific-plan.json"),
        "review_handoff": bind(P / "plan-review-handoff.json"),
        "new_policy_performance": None,
        "new_economic_trials": 0,
        "source_findings": (
            "OA5.2 flow-cost rationale; OA5.3.1 separate5minute horizons, "
            "not existing single15minute. "
            "GP main results quadratic, not linear20bp SPY. Original APP execution15minutes after "
            "formation is at label-end; causal lifetime and full linear cost "
            "must discriminate value."
        ),
        "next_action": (
            "Root prioritizes P0 review, then complete independent review "
            "and final scientific/resource admission for this plan. "
            "Same owner continues implementation and empirical explanation "
            "after actual native gates; native final event yields slot without abandoning parent."
        ),
    }
)
save("current-state.json", state)
print(
    json.dumps(
        {
            "handoff_ready": True,
            "cumulative_CPU": round(charged, 2),
            "held_CPU": held,
            "remaining_CPU": round(ledger["cap_CPU"] - charged - held, 2),
            "new_economic_runs": 0,
        }
    )
)
