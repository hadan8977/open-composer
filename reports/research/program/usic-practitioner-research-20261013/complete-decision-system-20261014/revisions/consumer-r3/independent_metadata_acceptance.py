"""One-field independent metadata acceptance; no native/data/economic execution."""
import hashlib
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import resource

resource.setrlimit(resource.RLIMIT_CPU, (1, 2))
R = Path.cwd()
P = R / "reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014"
D = P / "revisions/consumer-r3"
assert os.sched_getaffinity(0) == {0}
assert json.loads((R / "reports/research/control/owner-compute-hold.json").read_text())["research_paused"] is False
tasks = json.loads((R / "reports/research/control/day-goal.json").read_text())["tasks"]
task = next(t for t in tasks if t.get("id") == "MARTIN-COMPLETE-DECISION-SYSTEM-20261014")
assert task["owner"] == "7c7b1f3d-b962-4bbe-a2eb-87578888a8d5" and task["status"] == "running_complete_task"

def bind(p):
    raw = p.read_bytes()
    return dict(path=str(p.relative_to(R)), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))

def load(p):
    return json.loads(p.read_text())

assert bind(D / "review-packet.json")["sha256"] == "48c1fda948be53abc1f65d5784f402cd53dd3b6dc9c931221b3732d045b96a8c"
assert bind(P / "consumer-implementation-manifest.json")["sha256"] == "179c8aac7c37c675660b0fc74a35958ae47ab99b063f22ae15e600a2f43b4c02"
assert bind(D / "before-consumer-independent-review.json")["sha256"] == "f5d9e6ba57ba8b9deafe6916fa98679f3cf10fe274b0ed0bf9349c5c908e20e0"
old = load(D / "before-consumer-implementation-manifest.json")
new = load(P / "consumer-implementation-manifest.json")
a = {b["path"]:b for b in old["files"]}
b = {b["path"]:b for b in new["files"]}
changed = [p for p in a if a[p] != b.get(p)]
registration = P / "code/native_registration.py"
assert changed == [str(registration.relative_to(R))] and set(a) == set(b)
assert bind(registration) == b[changed[0]]
raw = registration.read_bytes()
line = b'                source_kind="authored_public_method",\n'
assert raw.count(line) == 1
assert hashlib.sha256(raw.replace(line,b"",1)).hexdigest() == a[changed[0]]["sha256"]
for k in ("approved_plan", "science_review", "scientific_contracts", "cases", "input", "input_original", "input_repair", "prepared_feature_prefix"):
    assert old[k] == new[k], k
cards_path = R / "reports/harness/source_cards/martin_complete_system_20261014.jsonl"
cards = [json.loads(x) for x in cards_path.read_text().splitlines()]
cards = [c for c in cards if c["claim_id"] in {"ML_watchlist", "ML_ADR"}]
assert len(cards) == 2 and all(c["source_type"] == "practitioner_first_person" for c in cards)
gate_path = R / "open_composer/research/iteration_dossier.py"
gate = gate_path.read_text()
assert 'source.get("source_kind") == "authored_public_method"' in gate
assert 'source.get("source_type") == "practitioner_first_person"' in gate
ledger_path = P / "economic-results/reservations/martin-first-1800-20261014.json"
assert bind(ledger_path) == new["affected_native_source_metadata"]["native_failure_charged"]
ledger = load(ledger_path)
assert ledger["status"] == "settled" and ledger["outcome"] == "failed" and ledger["runtime_actual_CPU"] == 0
assert Decimal(str(ledger["charged_CPU"])) == Decimal("17.33333") == Decimal(str(ledger["empirical_actual_CPU"]))
assert Decimal(str(load(P / "cumulative-accounting.json")["new_measured_economic_CPU"])) >= Decimal("17.33333")
prior = load(D / "before-consumer-independent-review.json")
verification = dict(
    changed_executable_bindings=changed, one_line_reverse_hash_equals_approved_r2=True,
    original_source_types=[dict(claim_id=c["claim_id"],source_type=c["source_type"]) for c in cards],
    existing_native_authored_component_exception=True, native_gate_modified=False,
    input_science_consumer_bindings_unchanged=True, native_or_test_execution=False,
    failure_receipt=bind(ledger_path), prior_grant=bind(D / "before-consumer-independent-review.json"),
    original_first_envelope_CPU=1800, consumed_empirical_CPU=17.33333,
    remaining_runtime_CPU=1200, remaining_first_empirical_CPU=582.66667,
    remaining_first_envelope_CPU=1782.66667, original_total_remaining_CPU=7159.39667,
)
(D / "independent-metadata-verification.json").write_text(json.dumps(verification,indent=2)+"\n")
review = dict(
    schema_version=1, at_utc=datetime.now(UTC).isoformat(), author=prior["author"], reviewer=prior["reviewer"],
    verdict="approve_implementation", classification="Same-semantics one-field source-kind metadata and reduced existing-grant continuation",
    bindings=dict(
        implementation_manifest=bind(P / "consumer-implementation-manifest.json"),
        reviewed_request=bind(D / "review-packet.json"),
        archived_prior_review=bind(D / "before-consumer-independent-review.json"),
        approved_science=prior["bindings"]["approved_science"],
        accepted_scientific_plan=prior["bindings"]["accepted_scientific_plan"],
        input_manifest=prior["bindings"]["input_manifest"],
        settled_prior_failure=bind(ledger_path),
        registration=bind(registration), source_cards=bind(cards_path), native_source_rule=bind(gate_path),
        metadata_verification=bind(D / "independent-metadata-verification.json"),
    ),
    full_scientific_approval_preserved=True, parent_question_complete=False, corrections=[],
    inherited_acceptance="All r2 U1/G1/G2/G3/I1/B1,33/74 and25-month input conclusions retained through archived receipt; no rescan",
    metadata_judgment="ML_watchlist/ML_ADR are already practitioner_first_person methods. Truthful authored_public_method source_kind uses the existing nonpromotable market-component exception, without relabeling them papers or relaxing any native gate.",
    economic_execution_admitted=True,
    economic_authorization_semantics="Continuation of original1800 only, after subtracting settled17.33333; changed receipt SHA never replenishes original first600/1800",
    allocation=dict(economic_coreseconds=1782.66667,runtime_feature_generation_CPU=1200,first_empirical_CPU=582.66667,CPU=1,memory_MiB=900,entire_scope_original_remaining_CPU=7159.39667),
    grant_lineage=dict(original_grant=bind(D / "before-consumer-independent-review.json"),original_total_CPU=1800,original_empirical_CPU=600,consumed_CPU=17.33333,consumed_runtime_CPU=0,no_budget_reset=True),
    allocation_conditions=[
        "Refresh registration; actual current native validation, current hold/owner/input/code, freshmemory and unique prelaunch reservation still required.",
        "Per-new-receipt remaining1200/582.66667/1782.66667 plus immutable prior17.33333 must remain within original1200/600/1800. Original7200 includes old23.27 and current17.33333; no refund of failed native.",
        "Launcher/native/failure/unknown remain inside empirical allowance; no new HTTP, source, fit, broker or parent-scope change.",
        "No Frame or account execution is certified by this metadata review; all prior conditional input/unknown/PIT/fill limits retained.",
    ],
    native_validation_currently_passed=False,reviewer_started_economic_job=False,
    resource=dict(pool="original comparison1000 / original consumer100 final1.95 reservation",inclusive_review_charge_CPU=1.95,comparison_before_CPU=452.50,comparison_after_CPU=454.45,comparison_remaining_CPU=545.55,consumer100_cumulative_CPU=100,CPU=1,memory_MiB=400,actual_profile="revisions/consumer-r3/independent-metadata-resource.txt",note="This1.95 includes measured outer job and unmeasured smallread/write/seal/handoff; reconcile actual outer profile within it, never add twice. No author ledger mutation."),
)
(P / "consumer-independent-review.json").write_text(json.dumps(review,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(bind(P / "consumer-independent-review.json")))
