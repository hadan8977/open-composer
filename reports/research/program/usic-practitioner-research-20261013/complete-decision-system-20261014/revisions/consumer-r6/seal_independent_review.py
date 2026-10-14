"""Seal r6 affected acceptance; no author ledger or economic execution."""
import hashlib
import json
from datetime import UTC,datetime
from pathlib import Path
import re
import resource
resource.setrlimit(resource.RLIMIT_CPU,(2,3))
R=Path.cwd();P=R/"reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014";D=P/"revisions/consumer-r6"
def load(p): return json.loads(p.read_text())
def bind(p):
    with p.open("rb") as f: sha=hashlib.file_digest(f,"sha256").hexdigest()
    return dict(path=str(p.relative_to(R)),sha256=sha,bytes=p.stat().st_size)
v=load(D/"independent-verification.json")
assert v["completed"] and v["synthetic_engine_count"]==24
assert bind(P/"consumer-implementation-manifest.json")["sha256"]=="219a1c12f1cb858532ed33a196f785c604836cb22805a39df241afc707e11dd6"
packet=load(D/"review-packet.json");prior=load(D/"before-consumer-independent-review.json")
assert bind(D/"before-consumer-independent-review.json")["sha256"]=="182727a953cbf4624262166a4f936048ad77013784578bf6ac2982a0872f8014"
profile=D/"independent-check-resource.txt";t=profile.read_text()
measured=round(sum(float(re.search(label+r" time \(seconds\): ([0-9.]+)",t).group(1)) for label in ("User","System")),2)
charge=round(measured+5,2);assert charge<=80
res=dict(pool="original comparison1000, r6 maximum80, old review reservations remain settled",actual_check_outer_CPU=measured,smallread_setup_seal_handoff_allowance_CPU=5,inclusive_charge_CPU=charge,comparison_before_CPU=478.59,comparison_after_CPU=round(478.59+charge,2),comparison_remaining_CPU=round(521.41-charge,2),r6_unused_of80_CPU=round(80-charge,2),fresh_cap_MiB=400,affinity=[0],maximum_RSS_KiB=int(re.search(r"Maximum resident set size \(kbytes\): (\d+)",t).group(1)),profile=bind(profile),author_ledger_mutated=False,seal_measured_inside_allowance_not_additional=True)
(D/"independent-resource.json").write_text(json.dumps(res,indent=2)+"\n")
bindings=dict(
    implementation_manifest=packet["manifest"],reviewed_request=bind(D/"review-packet.json"),affected_diff=packet["affected_diff"],
    archived_prior_review=packet["prior_review"],archived_prior_manifest=bind(D/"before-consumer-implementation-manifest.json"),
    approved_science=prior["bindings"]["approved_science"],accepted_scientific_plan=prior["bindings"]["accepted_scientific_plan"],input_manifest=prior["bindings"]["input_manifest"],
    complete_Frame_inventory=bind(P/"frame-preparation-result.json"),actual_old_January=packet["completed_actual_January"],first_probe_reconciliation=packet["first_probe_reconciliation"],
    settled_first_probe=packet["settled_first_probe"],old_first_native_failure=bind(P/"economic-results/reservations/martin-first-1800-20261014.json"),old_interrupted_account=bind(P/"economic-results/reservations/martin-first-residual-20261014.json"),
    sealed_accounting=bind(D/"accounting-at-seal.json"),independent_verification=bind(D/"independent-verification.json"),independent_check_code=bind(D/"independent_check.py"),independent_log=bind(D/"independent-check.log"),independent_resource=bind(D/"independent-resource.json"),
)
review=dict(schema_version=1,at_utc=datetime.now(UTC).isoformat(),author=prior["author"],reviewer=prior["reviewer"],verdict="approve_implementation",classification="Affected measured-throughput, independent-account shared input, and same-definition technical recovery; original complete science remains approved",bindings=bindings,corrections=[],full_scientific_approval_preserved=True,parent_question_complete=False,
accepted_differences={
    "M1":"Boundary msgspec JSON and omitted inactive Quantity preserve interpreted fields and clocks in independent synthetic reference/reuse checks. Old cProfile output is elapsed-wall profiling despite old CPU labels; only original explicit process_time counters establish CPU. New profiling timer is process_time, without rerunning January.",
    "M2":"Pruning uses consumed same-session necessary daily context only, matching fixed DecisionSystem preconditions, with P_EMA shape exemption. Actual producer updates epoch validity and daily EMA/market/shape before session; dynamic retest/hourly/volume/live risk are excluded from pruning. Native/controller held,pending,open-order,staged,cancel unions override exclusions. Additional shape-false P_SYSTEM market versus P_EMA capped single/shared witness passed.",
    "M3":"Close BookView reuse is accepted only under the current synchronous callback model: before/after controller signature unchanged, holdings/cash/closedR/marks constant within close rows, and every new buy reservation invalidates cache. Feedback recovery/re-pause actual synthetic counterexample matches reference. Immutable Frame shallow reconstruction copies all fields with exactly the original two overrides. Any later asynchronous callback or held-risk mutation would require affected revalidation.",
    "M4":"Three supplied independent-single versus two-engine shared-source cases passed, plus extra shape-false case. Separate engines/caches/books/policies/fees remain separate; active symbols are unioned and both engines match independently. Reviewer additionally captured complete book/quote/boundary representations before consumption and confirmed unchanged after both engines, beyond the author's bid-only quote assertion. This establishes tested inert equivalence, not measured economic speedup or all historical parity.",
    "P1":"Necessary March replay is accepted because old reference interpretation existed only in RAM. January is reused as its original completed old-version witness; it is not relabeled as a fresh r6 parity measurement. Reference streams days without resetting native account; each March variant seals interpreted gzip and metrics before the next. Budget-incomplete prefix or matching firstunknown is not a complete full-month throughput witness.",
    "R1":"Settled first probe is156.83=151.83 actual outer+5 launcher, with1.674631 teardown correction replacing provisional charge once. New economic cumulative1831.81333 and original residual5344.91667 verified from three settled receipts. Old first600 actual601.856538 and overrun1.856538 stay closed, and prior preparation failures remain preparation.",
},
verification_scope=dict(fresh_small_bindings=len(v["fresh_small_bindings"]),inherited_binding_references_not_rehashed=len(v["inherited_not_rehashed"]),single_shared_pairs=4,reference_reuse_pairs=4,total_synthetic_native_engines=24,full_field_decoder_checks=5,feedback_recovery_repause_equal=True,complete_book_quote_boundary_immutability_witness=True,large_Frame_price_source_scan=False,native_CLI_run=False,new_market_economic_probe=False,old33_74_25_and_source_science_reused=True),
economic_execution_admitted=True,economic_authorization_semantics="Same original-pool conditional continuation, not a refreshed180/600 or new global budget. Next at-most180 March recovery is charged on top of already consumed156.83 first probe.",
allocation=dict(economic_coreseconds=5344.91667,empirical_continuation_CPU=5344.91667,runtime_feature_generation_CPU=0,CPU=1,memory_MiB=900,entire_scope_original_remaining_CPU=5344.91667),
grant_lineage=dict(consumed_CPU=1831.81333,original_total_pool_remaining_before_task=7176.73,original_pool_CPU=7200,prior_public_replay_CPU=23.27,first_probe_used_CPU=156.83,first600_actual_CPU=601.856538,first600_overrun_CPU=1.856538,old_first1800_closed=True,no_budget_reset=True,archived_prior_grant=packet["prior_review"],settled_receipts=[bindings["old_first_native_failure"],bindings["old_interrupted_account"],packet["settled_first_probe"]]),
first_execution=dict(entry="code/run_native_consumer.py --technical-feed-probe",maximum_inclusive_CPU=180,runtime_CPU=0,scope="Necessary fixed March2024 reference/reuse recovery, maximum2 physical components; inherit actual old January without rerun",new_complete_strategy_cells=0,actual_current_native_required=True,exact_parity_required=True),
allocation_conditions=[
    "First reserve at most180 inclusive empirical CPU for bound March technical recovery only; include native admission, IO, failures, launcher/unknown and post-exit teardown. Current owner/hold/exact code/input/SHA/native/freshmemory/CPU0/unique reservation gates remain mandatory. Runtime Frame generation remains0.",
    "Persist reference and reuse interpreted witnesses with source/code/receipt identity. Both must complete the fixed intended March clock and match every interpreted audit/policy/NAV/quantity/fee/knownprefix/holding field before passing the actual data parity condition. Identical unknown-prefix behavior is valid limited evidence but does not establish full-month execution or its throughput. Budget-incomplete/kill never passes.",
    "January retains old code/input provenance and its actual completed parity. R6 extension relies on the new inert checks and actual March check; never claim January was rerun with r6 or that all25-month values were independently replayed.",
    "After actual March parity, seal measured full-clock matched-block affordability including read/parse/source construction, per-engine matching, serialization, native checks, all failed/unknown/post-exit cost and explicit margin. Do not infer two-engine speedup from inert tests; use conservative per-engine costs until actual shared workload is measured. Reconcile post-exit outer usage once in the existing serial ledger.",
    "Within the same residual and frozen inventory, author may then execute affordable complete P_SYSTEM/P_EMA contrasts across both routes and both OHLC paths, followed by informative fixed mechanism/cost contrasts. Shared block is at most2 independent engines, oneOHLC, separate cash/risk/fees/identity. Source sharing is computational reuse, not portfolio combination or pooled P&L.",
    "Choose complete blocks by mechanism information and measured workload, never winning return/path. No blind96, no replacing complete mother question with technical components or partial prefixes. If an essential full matched block is genuinely unaffordable, provide one measured major resource choice instead of silently dropping partners or adding budget.",
    "Preserve already completed Frame shards, incomplete source/account artifacts and physical replay exposure. No native checkpoint is invented. Unknown account stops only that account; the other retains its own book. Shared block CPU is nonadditive per-case and charged once inclusive.",
    "No new source/HTTP/market/fit/broker allocation. Existing conditional raw-basis, exact4-day witness, missing/rights/PIT/fill limits remain. Respect P0/HF priority, actual capped memory and Linux500MiB reserve.",
],
condition_enforcement="Machine guard enforces current binding/native/owner/hold/reservation and cumulative pool. Author must select the authorized technical flag/<=180 first reservation and seal real parity/affordability before subsequent blocks; review does not assert these scientific conditions are automatically inferred by the driver.",
reused_input_acceptance="Original25 normalized-input and bound unchanged producer acceptance reused; no new values or large SHA scans. All25 generated Frames must still pass existing fresh actual consumer validation.",
current_full_economic_cells_completed=0,native_validation_currently_passed=False,reviewer_started_economic_job=False,workflow_pass=False,research_pass=False,paper_ready_pass=False,resource=res)
text=json.dumps(review,ensure_ascii=False,indent=2)+"\n"
(D/"independent-review.json").write_text(text);(P/"consumer-independent-review.json").write_text(text)
print(json.dumps(dict(canonical=bind(P/"consumer-independent-review.json"),local=bind(D/"independent-review.json"),resource=res)))
