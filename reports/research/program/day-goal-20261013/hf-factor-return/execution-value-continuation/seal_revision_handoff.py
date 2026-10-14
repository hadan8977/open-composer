"""Same-pool revised implementation and unapplied native diff handoff."""

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path.cwd()
P = Path(__file__).resolve().parent
C = P / "candidate-admission-v1"
D = ROOT / "reports/research/iterations/t20261014_hf_execution_value"


def bind(path):
    path = path.resolve()
    body = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }


def save(path, payload):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


at = datetime.now(UTC).isoformat()
ledger_path = P / "cumulative-resource-ledger.json"
ledger = json.loads(ledger_path.read_text())
assert (
    sum(
        x["job_id"] == "hf-independent-implementation-review-93af0483-v1" for x in ledger["entries"]
    )
    == 1
)
assert sum(x["job_id"] == "hf-root-plan-review-v1" for x in ledger["entries"]) == 1
before_charged = ledger["base_conservative_CPU"] + sum(
    x.get("charge_CPU", 0) for x in ledger["entries"]
)
assert before_charged >= 12644.26 - 1e-6
ids = {x["job_id"] for x in ledger["entries"]}
profiles = [x for x in sorted(P.glob("revision-*-resource-*.txt")) if "seal" not in x.name]
for path in profiles:
    body = path.read_text()
    cpu = sum(
        float(re.search(kind + r" time \(seconds\): ([\d.]+)", body)[1])
        for kind in ("User", "System")
    )
    job = "hf-exec66-revision-" + path.stem
    if job in ids:
        old = next(x for x in ledger["entries"] if x["job_id"] == job)
        assert old["receipt"] == bind(path) and abs(old["charge_CPU"] - cpu) < 1e-6
        continue
    ledger["entries"].append(
        {
            "job_id": job,
            "status": "closed",
            "charge_CPU": cpu,
            "measured_CPU": cpu,
            "exit_status": int(re.search(r"Exit status: (\d+)", body)[1]),
            "receipt": bind(path),
            "scope": (
                "Same approved package repairs, isolated scope tests and read-only "
                "inputs; failures included"
            ),
        }
    )
closing_entries = [
    {
        "job_id": "hf-exec66-revision-static-allowance-v1",
        "status": "closed",
        "charge_CPU": 20,
        "measured_CPU": None,
        "nonzero_unmetered_allowance_CPU": 20,
        "scope": (
            "All unprofiled current-turn reads/edits, before/diff rendering and "
            "exact original-test reconstruction; not Root10"
        ),
    },
    {
        "job_id": "hf-exec66-revision-final-seal-v1",
        "status": "closed",
        "charge_CPU": 8,
        "measured_CPU": None,
        "nonzero_unmetered_allowance_CPU": 8,
        "scope": (
            "Inclusive final script formatting/lint, actual capped sealing and "
            "closing metadata checks; profile retained, no extra nested charge"
        ),
    },
]
for entry in closing_entries:
    if entry["job_id"] not in ids:
        ledger["entries"].append(entry)
charged = round(
    ledger["base_conservative_CPU"] + sum(x.get("charge_CPU", 0) for x in ledger["entries"]), 2
)
allocation = json.loads((P / "root-plan-allocation-v1.json").read_text())
used = round(charged - allocation["package_start_cumulative_CPU"], 2)
future = round(allocation["package_cap_CPU"] - used, 2)
held = 30
family = round(ledger["cap_CPU"] - charged - held - future, 2)
assert family == 18525.53 and future > 0
save(ledger_path, ledger)
counts = {}
for name in ("revision-tests-01.xml", "revision-candidate-tests-01.xml"):
    suite = ElementTree.parse(P / name).getroot().find("testsuite")
    count = {k: int(suite.attrib[k]) for k in ("tests", "failures", "errors", "skipped")}
    assert not count["failures"] and not count["errors"] and not count["skipped"]
    counts[name] = count
assert counts["revision-tests-01.xml"]["tests"] == 49
assert counts["revision-candidate-tests-01.xml"]["tests"] == 47
probe = json.loads((C / "current-native-probe.json").read_text())
assert probe["current_binding_mismatches"] == [] and probe["shared_consumers_unchanged"] is True
assert probe["actual_candidate_component_applicable"] is False
before = json.loads((C / "before-bindings.json").read_text())
assert all(bind(Path(x["before_path"]))["sha256"] == x["sha256"] for x in before)
for name in (
    "open_composer/research/iteration_dossier.py",
    "open_composer/research/market_component.py",
):
    assert bind(ROOT / name)["sha256"] == next(x["sha256"] for x in before if x["path"] == name)
resources = {
    "pool_cap_CPU": 36000,
    "package_cap_CPU": 5000,
    "current_cumulative_charged_CPU": charged,
    "package_already_charged_CPU": used,
    "package_future_reserved_CPU": future,
    "old_source_held_CPU": held,
    "family_unallocated_CPU": family,
    "review25_charged_once": True,
    "Root10_charged_once": True,
    "reservation_not_charged_as_used": True,
    "new_paid_spending": 0,
    "metered_profiles_including_failed_lint": len(profiles),
    "current_turn_charge_CPU": round(charged - 12644.26, 2),
    "memory_MiB": 384,
    "core_count": 1,
    "refresh_disk_reserve_bytes": 9530000000,
}
resources["preparation_peak_RSS_KiB"] = max(
    int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", path.read_text())[1])
    for path in profiles
)
files = [
    P / name
    for name in (
        "implementation-manifest.json",
        "fixed-component-comparison.json",
        "implementation-contract-v1.md",
        "implementation-revision-handoff-v1.md",
        "seal_revision_handoff.py",
        "hf_execution_policy.py",
        "run_execution_accounts.py",
        "build_execution_dossier.py",
        "test_hf_execution_policy.py",
        "test_implementation_revisions.py",
        "check_revised_input_clocks.py",
        "revision-input-clock-QA.json",
        "execution-input-manifest.json",
        "revision-tests-01.xml",
        "revision-candidate-tests-01.xml",
        "first-book-launch-manifest.json",
        "full-run-launch-manifest.json",
    )
]
files += [
    C / name
    for name in (
        "native-applicability.diff",
        "implementation-revisions.diff",
        "before-bindings.json",
        "shared-before-dirty.diff",
        "current-native-probe.json",
        "test_candidate_admission.py",
        "run_candidate_tests.py",
        "verify_current_bindings.py",
    )
]
files += [
    C / "candidate/open_composer/research" / name
    for name in ("iteration_dossier.py", "market_component.py")
]
review = P / "independent-implementation-review.json"
assert json.loads(review.read_text())["verdict"] == "revise_implementation"
handoff = {
    "schema_version": 3,
    "task_id": "HF-EXECUTION-VALUE-CONTINUATION-20261014",
    "parent_task": "DAY3-HF-FACTOR-RETURN",
    "owner": "66ebc2b7-c533-4992-82fe-cece4f3e2b12",
    "at_utc": at,
    "status": "same_owner_R1_R3_repaired_unapplied_native_diff_ready_for93af_full_delta_review",
    "independent_review_preserved": bind(review),
    "original_review_before": bind(C / "before" / review.relative_to(ROOT)),
    "approved_scientific_plan_unchanged": bind(P / "scientific-plan.json"),
    "approved_full_definition_unchanged": bind(P / "scientific-plan-v1.md"),
    "independent_plan_approval_unchanged": bind(P / "independent-plan-review-root-v1.json"),
    "bindings": [bind(x) for x in files],
    "test_counts": counts,
    "current_implementation_input_bindings": {"checked": 31, "mismatches": []},
    "native_diff_application": (
        "unapplied; git apply --check passed against preserved current dirty shared source"
    ),
    "actual_native_and_financial_admission": (
        "blocked; isolated synthetic scope tests are not actual native pass"
    ),
    "required_review_bindings": [
        bind(P / "implementation-manifest.json"),
        bind(P / "fixed-component-comparison.json"),
    ],
    "native_consumer_before_bindings": [
        x
        for x in before
        if x["path"]
        in (
            "open_composer/research/iteration_dossier.py",
            "open_composer/research/market_component.py",
        )
    ],
    "inventory": {
        "identities": 60,
        "policies": 3,
        "information_anchor_configurations": 48,
        "causal_controls": 12,
        "fixed20k_views": 120,
        "conditional4k_views": 36,
        "all_seen": True,
        "all_nonpromotable": True,
    },
    "resources": resources,
    "cumulative_resource_ledger": bind(ledger_path),
    "disk_free_bytes_at_handoff": shutil.disk_usage(P).free,
    "new_financial_runs": 0,
    "old100plus5_or_attribution_reruns": 0,
    "new_training_or_inference": 0,
    "new_public_or_market_requests": 0,
    "shared_CLI_or_production_changes": 0,
    "new_agents_spawned": 0,
    "parent_question_complete": False,
    "economic_execution_admitted": False,
    "Root_next_action": (
        "Give original93af the complete implementation and applicability diff"
        " for one independent delta review; after real acceptance Root may "
        "apply the candidate to the preserved shared baseline. Same owner "
        "then runs actual native/input/memory/disk/CPU gates and fixed "
        "financial launch when admitted."
    ),
    "owner_continuity": (
        "Original complete experiment owner retained; this turn ends to release a slot for93af"
    ),
    "notification": "native final completion only; no duplicate message, heartbeat or LLM polling",
}
save(P / "implementation-revision-handoff-v1.json", handoff)
state = json.loads((P / "current-state.json").read_text())
state.update(
    status=handoff["status"],
    updated_at_utc=at,
    economic_execution_admitted=False,
    parent_question_complete=False,
    completion_current_CPU=charged,
    completion_reserved_CPU=held,
    package_future_reserved_CPU=future,
    family_unallocated_CPU=family,
    remaining_CPU=round(36000 - charged - held, 2),
    cumulative_resource_ledger=bind(ledger_path),
    implementation=bind(P / "implementation-manifest.json"),
    implementation_revision_handoff=bind(P / "implementation-revision-handoff-v1.json"),
    actual_exec_session=None,
    actual_job=None,
    new_economic_trials=0,
    new_policy_performance=None,
    synthetic_test_count=49,
    candidate_admission_test_count=47,
    actual_native_iteration="blocked_pending_actual_implementation_acceptance_and_Root_diff_acceptance",
    actual_native_knowledge="blocked_pending_actual_implementation_acceptance",
    next_action=handoff["Root_next_action"],
)
save(P / "current-state.json", state)
print(
    json.dumps(
        {"handoff_ready": True, "resources": resources, "test_counts": counts, "financial_runs": 0}
    )
)
