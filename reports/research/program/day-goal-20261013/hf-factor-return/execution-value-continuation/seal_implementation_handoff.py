"""Charge measured preparation once and seal the concrete review handoff."""

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

P = Path(__file__).resolve().parent
ROOT = Path.cwd()
D = ROOT / "reports/research/iterations/t20261014_hf_execution_value"


def bind(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(name, value):
    (P / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


at = datetime.now(UTC).isoformat()
ledger_path = P / "cumulative-resource-ledger.json"
ledger = json.loads(ledger_path.read_text())
allocation = json.loads((P / "root-plan-allocation-v1.json").read_text())
previous = ledger["base_conservative_CPU"] + sum(r.get("charge_CPU", 0) for r in ledger["entries"])
assert abs(previous - 12487.17) < 1e-6
assert sum(r["job_id"] == "hf-root-plan-review-v1" for r in ledger["entries"]) == 1
save("implementation-ledger-before.json", ledger)
profiles = [
    "implementation-format-resource-01.txt",
    "implementation-format-resource-02.txt",
    "implementation-format-resource-03.txt",
    "implementation-lint-resource-01.txt",
    "implementation-lint-resource-02.txt",
    "implementation-lint-resource-03.txt",
    "implementation-lint-resource-04.txt",
    "implementation-tests-resource-01.txt",
    "implementation-tests-resource-02.txt",
    "implementation-tests-resource-03.txt",
    "input-preparation-resource-01.txt",
    "dossier-build-resource-01.txt",
    "dossier-build-resource-02.txt",
    "native-preparation-resource-01.txt",
    "native-preparation-resource-02.txt",
    "financial-admission-probe-resource.txt",
]
ids = {row["job_id"] for row in ledger["entries"]}
for name in profiles:
    job_id = "hf-exec66-I1I4-" + name.removesuffix(".txt")
    assert job_id not in ids
    body = (P / name).read_text()
    cpu = sum(
        float(re.search(kind + r" time \(seconds\): ([\d.]+)", body)[1])
        for kind in ["User", "System"]
    )
    code = int(re.search(r"Exit status: (\d+)", body)[1])
    ledger["entries"].append(
        {
            "job_id": job_id,
            "status": "closed",
            "measured_CPU": cpu,
            "charge_CPU": cpu,
            "exit_status": code,
            "receipt": bind(P / name),
            "scope": "Approved implementation, synthetic tests or read-only/native preparation",
        }
    )
ledger["entries"].extend(
    [
        {
            "job_id": "hf-exec66-I1I4-static-allowance",
            "status": "closed",
            "charge_CPU": 10,
            "measured_CPU": None,
            "nonzero_unmetered_allowance_CPU": 10,
            "scope": "Current ordinary source reads, edits and repairs; not the priorRoot10",
        },
        {
            "job_id": "hf-exec66-I1I4-final-seal",
            "status": "closed",
            "charge_CPU": 4,
            "measured_CPU": None,
            "nonzero_unmetered_allowance_CPU": 4,
            "scope": "Conservative final handoff/file verification bound; actual profile retained",
        },
    ]
)
charged = ledger["base_conservative_CPU"] + sum(r.get("charge_CPU", 0) for r in ledger["entries"])
package_used = charged - allocation["package_start_cumulative_CPU"]
package_future = allocation["package_cap_CPU"] - package_used
held = sum(r["upper_CPU"] for r in ledger["entries"] if r["status"] == "reserved")
family = ledger["cap_CPU"] - charged - held - package_future
assert held == 30 and abs(family - 18525.53) < 1e-6 and package_future > 0
assert len({r["job_id"] for r in ledger["entries"]}) == len(ledger["entries"])
save("cumulative-resource-ledger.json", ledger)
root = ElementTree.parse(P / "implementation-tests-03.xml").getroot()
suite = root.find("testsuite")
assert int(suite.attrib["tests"]) == 33 and int(suite.attrib["failures"]) == 0
assert int(suite.attrib["errors"]) == 0
manifest = json.loads((P / "implementation-manifest.json").read_text())
for row in manifest["files"]:
    assert bind(ROOT / row["path"]) == row
launch = json.loads((P / "full-run-launch-manifest.json").read_text())
assert len(launch["fixed20k_views"]) == 120 and len(launch["conditional4k_views"]) == 36
native = json.loads((P / "native-preparation-receipt.json").read_text())
assert native["native_direction_status"] == "ok"
assert native["native_iteration"]["status"] == "blocked"
assert "campaign_contract_required_for_new_iteration" in native["native_iteration"]["blocked"]
save(
    "native-blocker-attribution.json",
    {
        "actual_native_receipt": bind(P / "native-preparation-receipt.json"),
        "independent_implementation_review": "missing; author does not approve own code",
        "source8_fallback": "Derivative of unaccepted component role; no new sources requested",
        "campaign_requirement": {
            "independent_structural_blocker": True,
            "code": "open_composer/research/iteration_dossier.py",
            "functions": ["_campaign_requirement_blockers", "_lightweight_single_mechanism_exempt"],
            "actual_search_space": bind(D / "search-space.json"),
            "inventory": 60,
            "paths": 3,
            "lightweight_limit": 24,
            "inventory_not_reduced_or_exemption_faked": True,
            "native_method_applicability_or_contract_decision_needed_from_Root": True,
        },
        "parent_question_complete": False,
        "financial_launch_admitted": False,
        "not_a_scientific_null_or_original_mechanism_refutation": True,
    },
)
resources = {
    "pool_cap_CPU": 36000,
    "current_cumulative_charged_CPU": round(charged, 2),
    "already_charged_package_CPU": round(package_used, 2),
    "package_future_reserved_CPU": round(package_future, 2),
    "old_source_held_CPU": held,
    "family_unallocated_CPU": round(family, 2),
    "Root10_not_double_charged": True,
    "reservation_not_charged_as_used": True,
}
save(
    "implementation-review-handoff.json",
    {
        "schema_version": 3,
        "task_id": "HF-EXECUTION-VALUE-CONTINUATION-20261014",
        "parent_task_id": "DAY3-HF-FACTOR-RETURN",
        "at_utc": at,
        "owner": "66ebc2b7-c533-4992-82fe-cece4f3e2b12",
        "status": "concrete_implementation_ready_native_blockers_received_owner_retained",
        "implementation": bind(P / "implementation-manifest.json"),
        "I1_I4_definition": bind(P / "implementation-contract-v1.md"),
        "synthetic_tests": bind(P / "implementation-tests-03.xml"),
        "tests": 33,
        "failures": 0,
        "inputs": bind(P / "execution-input-manifest.json"),
        "input_QA": bind(P / "execution-input-QA.json"),
        "first_book_launch": bind(P / "first-book-launch-manifest.json"),
        "full_run_inventory": bind(P / "full-run-launch-manifest.json"),
        "native_receipt": bind(P / "native-preparation-receipt.json"),
        "native_blocker_attribution": bind(P / "native-blocker-attribution.json"),
        "explanation": bind(P / "implementation-handoff.md"),
        "cumulative_resources": bind(P / "cumulative-resource-ledger.json"),
        "resources": resources,
        "actual_disk_free_bytes_at_handoff": shutil.disk_usage(P).free,
        "prep_peak_RSS_KiB": 217668,
        "financial_runtime_admission": "Fresh check after review/native conditions resolve",
        "new_financial_runs": 0,
        "new_model_training_or_inference": 0,
        "old100plus5_attribution_or_real_account_reruns": 0,
        "new_public_or_market_requests": 0,
        "shared_production_writes": 0,
        "performance": None,
        "parent_question_complete": False,
        "Root_next_action": (
            "Prioritize P0 review, then independently accept I1-I4 and resolve actual60-identity "
            "campaign applicability within the approved same-parent package. Return to this owner "
            "for real native/input/runtime admissions and fixed first-book empirical continuation."
        ),
        "native_final_notification_only": True,
        "new_reviewer_or_subagent_spawned": False,
    },
)
state_path = P / "current-state.json"
state = json.loads(state_path.read_text())
save("implementation-state-before.json", state)
state.update(
    {
        "status": "implementation_input_ready_native_blocked_pending_Root_review_and_applicability",
        "updated_at_utc": at,
        "parent_question_complete": False,
        "economic_execution_admitted": False,
        "actual_exec_session": None,
        "actual_job": None,
        "implementation_review_handoff": bind(P / "implementation-review-handoff.json"),
        "implementation": bind(P / "implementation-manifest.json"),
        "new_economic_trials": 0,
        "new_policy_performance": None,
        "completion_current_CPU": round(charged, 2),
        "completion_reserved_CPU": held,
        "package_future_reserved_CPU": round(package_future, 2),
        "family_unallocated_CPU": round(family, 2),
        "remaining_CPU": round(ledger["cap_CPU"] - charged - held, 2),
        "cumulative_resource_ledger": bind(P / "cumulative-resource-ledger.json"),
        "actual_native_direction": "ok",
        "actual_native_knowledge": "blocked",
        "actual_native_iteration": "blocked",
        "synthetic_test_count": 33,
        "next_action": (
            "Root P0 review first, then concrete I1-I4 acceptance "
            "and native campaign applicability; same owner executes after real runtime gates. "
            "No new plan, sources, pool or abandonment."
        ),
    }
)
save("current-state.json", state)
print(json.dumps({"handoff_ready": True, "resources": resources, "real_financial_runs": 0}))
