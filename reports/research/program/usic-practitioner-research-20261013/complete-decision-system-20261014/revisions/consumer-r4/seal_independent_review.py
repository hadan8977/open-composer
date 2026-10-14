"""Seal affected independent r4 acceptance and original-pool continuation."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
import re
import resource

resource.setrlimit(resource.RLIMIT_CPU,(2,3))
R=Path.cwd()
P=R/"reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014"
D=P/"revisions/consumer-r4"
def bind(p):
    with p.open("rb") as f: sha=hashlib.file_digest(f,"sha256").hexdigest()
    return dict(path=str(p.relative_to(R)),sha256=sha,bytes=p.stat().st_size)
def load(p): return json.loads(p.read_text())
v=load(D/"independent-verification.json")
assert v["completed"] and len(v["synthetic_checks"])==8
assert bind(P/"consumer-implementation-manifest.json")["sha256"]=="d51957a4b32803fdd32a5092cbef2ead8ee08ec51277e5c8a49529c5e2edf2d0"
prior=load(D/"before-consumer-independent-review.json")
assert bind(D/"before-consumer-independent-review.json")["sha256"]=="ecd406d4eb5cbff4ff6ecc0e85a2f43df7ece45d1babe8efb6b0a1419c9ab238"
profile=D/"independent-check-resource.txt"
t=profile.read_text()
measured=round(sum(float(re.search(label+r" time \(seconds\): ([0-9.]+)",t).group(1)) for label in ("User","System")),2)
charge=round(measured+5,2)
assert charge<=80
resource_receipt=dict(pool="original comparison1000; separate r4 maximum80, old consumer100 remains fully consumed",actual_check_outer_CPU=measured,small_read_write_setup_seal_handoff_allowance_CPU=5,inclusive_charge_CPU=charge,comparison_before_CPU=454.45,comparison_after_CPU=round(454.45+charge,2),comparison_remaining_CPU=round(545.55-charge,2),r4_unused_of80_CPU=round(80-charge,2),fresh_cap_MiB=400,affinity=[0],maximum_RSS_KiB=int(re.search(r"Maximum resident set size \(kbytes\): (\d+)",t).group(1)),check_profile=bind(profile),author_ledger_mutation=False,seal_actual_is_inside_allowance_not_extra=True)
(D/"independent-resource.json").write_text(json.dumps(resource_receipt,indent=2)+"\n")
bindings=dict(
    implementation_manifest=bind(P/"consumer-implementation-manifest.json"),
    reviewed_request=bind(D/"review-packet.json"),
    affected_diff=bind(D/"affected-diff.json"),
    archived_prior_review=bind(D/"before-consumer-independent-review.json"),
    archived_prior_manifest=bind(D/"before-consumer-implementation-manifest.json"),
    approved_science=prior["bindings"]["approved_science"],
    accepted_scientific_plan=prior["bindings"]["accepted_scientific_plan"],
    input_manifest=prior["bindings"]["input_manifest"],
    complete_Frame_manifest=bind(P/"frame-preparation-result.json"),
    immutable_Frame_job_manifest=bind(P/"frame-preparation-resume3-manifest.json"),
    archived_admission_only_code=bind(D/"before/consumer_admission.py"),
    old_first_native_failure=bind(P/"economic-results/reservations/martin-first-1800-20261014.json"),
    old_interrupted_account_settlement=bind(P/"economic-results/reservations/martin-first-residual-20261014.json"),
    actual_old_outer_profile=bind(P/"economic-results/first-residual-inclusive-resource.txt"),
    sealed_accounting=bind(D/"accounting-at-seal.json"),
    independent_verification=bind(D/"independent-verification.json"),
    independent_check_code=bind(D/"independent_check.py"),
    independent_check_log=bind(D/"independent-check.log"),
    independent_resource=bind(D/"independent-resource.json"),
)
review=dict(
    schema_version=1,at_utc=datetime.now(UTC).isoformat(),author=prior["author"],reviewer=prior["reviewer"],
    verdict="approve_implementation",classification="Same-scope affected event-feed/decoder/resource/recovery acceptance; no new scientific review",
    bindings=bindings,full_scientific_approval_preserved=True,parent_question_complete=False,corrections=[],
    accepted_differences={
        "F1":"Causal morning pruning uses only already-consumed same-session daily leadership. All native positions/open orders, controller quantities/pending/protection and staged/cancel-then-sell intents survive. Opening prefix and missing leadership keep full feed. Afternoon exclusion follows original entry cutoff. Unexpected excluded submission asserts before matching; no silent substitution.",
        "F2":"Updated grouped inactive marks branch accepted before session/month and partial checks, after stickyunknown isolation. Actual synthetic callback with outstandingpartial and differing session updates only mark. Four paired reference/reuse engine witnesses matched audits, snapshots, closedR, unknown, cash, marks, quantities,lots and split coordinates. Active L2, quote order and timing retained. No real-market parity claimed yet.",
        "F3":"Five full-field decoder comparisons passed including dynamic fields and changed anchor touches. Exact immutable key contains context time and all supports/anchors. Close-group cash reuse occurs only before next-open submissions, while risk/reservation view updates each row. JSON serialization change does not create a new strategy.",
        "R1":"Soft-limit unwind margin and source-interval checks improve graceful stopping; SIGKILL remains possible and does not prove settlement. budget_incomplete suppresses full-path terminal cash/equity/closedR/holding claims. Actual overrun is retained and charged, never discarded; independent temporary ledger witness rejects duplicate settlement.",
        "R2":"Only evidenced original P_SYSTEM market20 O-H-L-C interrupted account is presently replayable by explicit same-definition recovery, with old logs archived. No native checkpoint is claimed. Later budget_incomplete result.json remains incomplete evidence; current driver refuses its automatic replay. Such a later recovery requires ordinary same-scope handling, not fabricated completion or deleting history.",
        "G1":"Original used1674.98333 is preserved; first empirical601.856538 and overrun1.856538 are historical closed exposure. New continuation consumes only original remaining5501.74667; per-grant and total settled/inflight checks persist. No restart of first600 or1800.",
        "B1":"Only admission-code historical byte substitution is allowed, with exact original hash and archived bytes. Frame-producing code/spec/input/context/geometry remain bound; 25-month output inventory checked from manifest, no new large-file hash/value scan by reviewer. Runtime guard still freshly verifies actual outputs before use.",
    },
    verification_scope=dict(fresh_small_bindings=len(v["fresh_small_bindings"]),inherited_bindings_not_rehashed=len(v["inherited_not_rehashed"]),paired_native_inert_cases=4,native_engines_for_pairs=8,extra_grouped_mark_engine=1,decoder_full_field_checks=5,extra_exposure_and_settlement_witnesses=True,old33_74_and25_normalized_input_reused=True,large_Frame_or_input_scan=False,actual_market_probe_run=False,full16_pair_suite_run=False),
    input_acceptance=dict(status="Existing conditional inputs and completed25-output producer inventory accepted for guarded reuse",raw_exact_scope="Only prior4 November symbol-days; no wider exact-raw/PIT/fill certification",Frame_values_independently_replayed_this_review=False,large_output_hashes_delegated_to_existing_actual_runtime_guard=True,actual_full_continuous_account_cells_completed=0,old_Jan_Jul_partial_not_full_result=True),
    economic_execution_admitted=True,
    economic_authorization_semantics="Conditional continuation within original residual, not additional global CPU. First physical job is restricted to technical feed parity; subsequent frozen complete contrasts become authorized only after the stated empirical conditions are actually satisfied.",
    allocation=dict(economic_coreseconds=5501.74667,runtime_feature_generation_CPU=0,empirical_continuation_CPU=5501.74667,CPU=1,memory_MiB=900,entire_scope_original_remaining_CPU=5501.74667),
    grant_lineage=dict(consumed_CPU=1674.98333,original_total_pool_remaining_before_task=7176.73,original_pool_CPU=7200,prior_public_replay_CPU=23.27,old_first1800_closed=True,old_first600_actual_CPU=601.856538,old_first600_overrun_CPU=1.856538,no_budget_reset=True,original_approval=bind(D/"before-consumer-independent-review.json"),settled_receipts=[bindings["old_first_native_failure"],bindings["old_interrupted_account_settlement"]]),
    first_execution=dict(entry="code/run_native_consumer.py --technical-feed-probe",maximum_inclusive_CPU=180,runtime_CPU=0,policy="P_SYSTEM market20bps O-H-L-C",fixed_inputs="first January2024 session profile and full March2024 reference/reuse from already-seen immutable Frames",maximum_physical_components=4,selectable_strategy_results=False,new_market_or_fit=0),
    allocation_conditions=[
        "Owner first reserves at most180 empirical CPU, runtime0, for the bound technical-feed-probe only. Its actual current native/fresh memory/CPU0/unique job/currentowner/hold/hash guards must pass. This180 is part of5501.74667, includes native/launcher/failure/unknown, never extra.",
        "Before any optimized complete account cell, actual fixed January and March reference/reuse results must report exact interpreted equality across audit,policy,snapshots,closedR,knownprefix unknown/quantities/lots/marks/cash. Failed,partial or killed diagnostic does not satisfy this condition. Preserve both sides and cost; ordinary same-semantics repairs retain cumulative accounting.",
        "After successful bound parity, owner seals actual diagnostic output and a measured full-contrast affordability calculation before reserving complete matched blocks. Include parsing/IO/native/serialization, actual failed/unknown costs, matched partners and both OHLC paths, plus explicit safety margin; short component throughput is an estimate, not measured full runtime.",
        "Within this same residual grant and without per-step Root approval, prioritize complete P_SYSTEM versus P_EMA contrasts across both frozen routes and both OHLC scenarios at primary cost, then informative preregistered mechanism/cost contrasts. Select order by mechanism information and measured workload, never favorable return/path. No blind obligation to run96; no replacing mother question with technical or partial prefix outputs.",
        "If a required complete matched block is not affordable under actual remaining global and grant commitments, stop before a knowingly partial economic launch and give one measured material resource choice. No automatic additional global allocation, new hypothesis, altered candidate or data window.",
        "Old25 Frame outputs are reused with historical admission-byte substitution only; generation allocation0. No large-input recreation, new HTTP/source/market/fit/broker action. P0/HF priority and Linux500MiB reserve retained.",
        "No current native pass is asserted by this receipt. Refresh actual dossier and pass its validation after the new binding; keep all falsepromotion/PIT/fill/right/unknown limitations.",
    ],
    first_probe_condition_enforcement="Unique reservation caps are machine checked; owner must select the authorized technical flag and at-most180 reservation, then seal actual parity/affordability evidence before later block reservation. This review does not claim the driver independently infers those scientific conditions.",
    native_validation_currently_passed=False,reviewer_started_economic_job=False,workflow_pass=False,research_pass=False,paper_ready_pass=False,
    resource=resource_receipt,
)
text=json.dumps(review,ensure_ascii=False,indent=2)+"\n"
(D/"independent-review.json").write_text(text)
(P/"consumer-independent-review.json").write_text(text)
print(json.dumps(dict(canonical=bind(P/"consumer-independent-review.json"),local=bind(D/"independent-review.json"),resource=resource_receipt)))
