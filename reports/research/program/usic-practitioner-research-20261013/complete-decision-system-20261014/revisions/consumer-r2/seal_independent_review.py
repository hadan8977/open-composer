"""Seal this independent affected review; never launch or mutate author accounting."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path.cwd()
P = ROOT / "reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014"
D = P / "revisions/consumer-r2"

def bind(path):
    with path.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    return dict(path=str(path.relative_to(ROOT)), sha256=sha, bytes=path.stat().st_size)

assert bind(P / "consumer-implementation-manifest.json")["sha256"] == "10705c4e0253f324d7dc6a92294c904c66e8327a0ac5696f1b43492ea612ef1b"
assert bind(D / "before/consumer-independent-review.json")["sha256"] == "9cd1a43c33ef1b65d9de7acec1d6a7bad11ee70b85b607a86347d9e27eab00e8"
v = json.loads((D / "independent-diff-verification.json").read_text())
assert v["focused_pytest_exit"] == 0
suite = ET.parse(D / "independent-affected-tests.xml").getroot().find("testsuite")
assert suite.attrib["tests"] == "4" and suite.attrib["failures"] == suite.attrib["errors"] == "0"
probe = json.loads((D / "independent-limit-probe-result.json").read_text())
assert probe["child"]["raised"] and probe["standalone_runtime_limits"] == [1198,1199]
profiles = [D / n for n in ("independent-diff-resource.txt", "independent-diff-resource-attempt2.txt", "independent-limit-probe-resource.txt")]
known = 0.0
peak = 0
for p in profiles:
    t = p.read_text()
    known += sum(float(re.search(label+r" time \(seconds\): ([0-9.]+)", t).group(1)) for label in ("User", "System"))
    peak = max(peak, int(re.search(r"Maximum resident set size \(kbytes\): (\d+)",t).group(1)))
known = round(known,2)
charge = round(known+3.0,2)
assert charge <= 21.97
resource = dict(
    pool="original comparison1000; continuation of consumer100 reservation",
    previous_comparison_charged_CPU=432.48,
    measured_outer_CPU_before_seal=known,
    measured_profiles=[bind(p) for p in profiles],
    small_reads_writes_setup_seal_and_handoff_allowance_CPU=3.0,
    allowance_includes_final_seal_outer_CPU_not_an_extra_charge=True,
    charged_CPU=charge,
    comparison_cumulative_CPU=round(432.48+charge,2),
    comparison_remaining_CPU=round(1000-432.48-charge,2),
    original_consumer100_cumulative_CPU=round(78.03+charge,2),
    original_consumer100_remaining_CPU=round(21.97-charge,2),
    maximum_observed_RSS_KiB=peak,
    fresh_capped_memory_MiB=400, actual_affinity=[0],
    failures_retained=["Reviewer fixture first lacked launcher_unknown_CPU (1.32 outer CPU)", "Nested child probe quoting SyntaxError retained in successful check record; separate actual kernel probe corrected only this instrumentation"],
    author_preparation_or_economic_charge=0,
    settlement="Author serially records this single comparison charge; reviewer does not mutate cumulative author accounting",
)
mapping = {
    "reviewed_request": P / "consumer-review-packet.json",
    "implementation_manifest": P / "consumer-implementation-manifest.json",
    "affected_diff": D / "affected-diff.json",
    "archived_prior_review": D / "before/consumer-independent-review.json",
    "approved_science": P / "revisions/r1/independent-review.json",
    "accepted_scientific_plan": P / "revisions/r1/scientific-plan-v2.json",
    "input_manifest": P / "complete-input-v2-result.json",
    "prior_independent_input_verification": P / "independent-consumer-input-verification.json",
    "prior_independent_consumer_verification": P / "independent-consumer-verification.json",
    "sealed_accounting_baseline": D / "accounting-at-seal.json",
    "hygiene_evidence": P / "causal-hygiene-verification.json",
    "affected_verification": D / "independent-diff-verification.json",
    "affected_JUnit": D / "independent-affected-tests.xml",
    "actual_kernel_limit_probe": D / "independent-limit-probe-result.json",
    "actual_kernel_limit_probe_code": D / "independent_limit_probe.py",
}
review = dict(
    schema_version=1, at_utc=datetime.now(UTC).isoformat(),
    author="7c7b1f3d-b962-4bbe-a2eb-87578888a8d5",
    reviewer="ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3",
    verdict="approve_implementation",
    classification="Affected consumer-r2 implementation, conditional input and prospective resource acceptance; existing complete scientific approval preserved",
    bindings={k:bind(p) for k,p in mapping.items()},
    full_scientific_approval_preserved=True,
    parent_question_complete=False,
    corrections=[],
    affected_acceptance={
        "U1":"Accepted. Actual Nautilus missing-active-minute/adverse9.5 stop witness independently passed. Later mechanical native fill is quarantined; original lot/state quantity, marks, closedR and feedback stay at known prefix. Full path closedR, holding, cash and NAV remain N/A; diagnostics are explicitly uninterpretable.",
        "G1":"Accepted. Both entrypoints consume the same current receipt/manifest, exact task, hold, affinity, unique prelaunch reservation and actual native dossier snapshot. Retained Frame existence alone cannot admit reuse. Author must refresh registration then obtain actual current native pass; no present native pass is asserted.",
        "G2":"Accepted. Per-grant cumulative runtime1200/empirical600/combined1800 and original7176.73 commitments retained. Empirical600 includes native child, launcher unknown5, failure and seal; runtime child counted once. Actual kernel probe in current environment verifies child and standalone can move inherited594/595 limits to1198/1199. This is environment-specific, not a portable privilege assumption. Unknown interrupted slots stay committed.",
        "G3":"Accepted. Exact task owner/status checked against actual authority; conflicting active_owner rejected by independent fixture, unrelated stale parent owner ignored.",
        "I1":"Accepted for bound inputs. Default stock price hygiene runs on past causal daily prefix in known split units; actual7027 zero-break/ghost and24 prefix equivalence evidence reviewed, not rescanned. Current09:30 split-like trigger exclusion is entry-only; retained10 completed prefixes remain immutable. Holding outcomes never select eligibility.",
        "B1":"Accepted. Exact e05fd verifier bytes restored; changed native metadata/registration bindings reviewed. Prior review archived bytes remain exact. Fresh native validation still required after this receipt is consumed.",
    },
    verification_scope={
        "fresh_small_bindings_checked":len(v["fresh_checked"]),
        "unchanged_manifest_bindings_inherited":len(v["inherited_not_rehashed"]),
        "independent_focused_checks_passed":4,
        "earlier_33_tests_and_74_bindings_reused":True,
        "prior_25_month_input_QA_reused":True,
        "no_price_or_Frame_rescan":True,
        "kernel_probe_not_training_or_strategy_run":True,
    },
    input_acceptance={
        "status":"accepted_conditional_research_input_and_frozen_runtime_producer",
        "full25_month_normalized_input":True,
        "complete25_month_Frame_output_already_exists":False,
        "completed_prefix":"Dec2023 through Sep2024; reuse only under actual bound source/code/parity checks",
        "exact_raw":"Only4 November symbol-days/1547 witnessed records; minute adjustment rounding remains conditional",
        "missing_minutes_and_GME_warrant_rights":"Retain missing/unknown and sticky unknown wealth; no padding, zero right value, or complete cash-path claim",
        "PIT_certified":False, "source_private_strategy_replication":False,
        "OOS_or_paper_ready":False,
    },
    economic_execution_admitted=True,
    economic_authorization_semantics="Prospective bounded allocation conditional on all current executable guards; this review does not claim that native validation or economic execution has already occurred",
    allocation=dict(economic_coreseconds=1800,runtime_feature_generation_CPU=1200,first_empirical_CPU=600,CPU=1,memory_MiB=900,entire_scope_original_remaining_CPU=7176.73),
    allocation_conditions=[
        "Refresh current registration then actual iteration martin_complete_system_20261014_dev validation must be ok; bind the current dossier before child use.",
        "Prelaunch unique reservation and current hold/exact owner/current implementation hashes must pass; reuse no consumed reservation.",
        "Fresh memory admission and actual capped one-core runtime, retain Linux500MiB and P0/HF priority; no new HTTP/model fit/broker action.",
        "Runtime generation1200 and first empirical600 are cumulative portions of one1800 envelope; launcher/native/failure/unknown count inside600, not a third pool.",
        "Original450.62+480.63 failures remain preparation; no retrospective reclassification or quota reset. Shared economic7176.73 is a cap, remaining5376.73 is not newly allocated by this receipt.",
        "Incomplete future Frame output or failed native/resource gate prevents dependent account cells; preserve partial output and inflight commitments for ordinary same-scope recovery.",
        "Continue complete approved mother question after first empirical evidence; this initial envelope does not replace full scope with a four-case/preparation-only study.",
    ],
    native_validation_currently_passed=False,
    reviewer_started_economic_job=False,
    workflow_pass=False,research_pass=False,paper_ready_pass=False,
    resource=resource,
)
(D / "independent-review-resource.json").write_text(json.dumps(resource,indent=2)+"\n")
review["bindings"]["review_resource"] = bind(D / "independent-review-resource.json")
(P / "consumer-independent-review.json").write_text(json.dumps(review,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(dict(receipt=bind(P / "consumer-independent-review.json"),resource=resource),ensure_ascii=False))
