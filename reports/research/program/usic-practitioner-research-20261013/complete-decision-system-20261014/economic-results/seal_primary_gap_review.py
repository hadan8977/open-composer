"""Seal bounded result/input reviews; preserve canonical consumer and author ledgers."""
import hashlib
import json
from datetime import UTC,datetime
from pathlib import Path
import resource
import re
resource.setrlimit(resource.RLIMIT_CPU,(2,3))
R=Path.cwd();P=R/"reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014";E=P/"economic-results"
def load(p): return json.loads(p.read_text())
def bind(p):
    with p.open("rb") as f: sha=hashlib.file_digest(f,"sha256").hexdigest()
    return dict(path=str(p.relative_to(R)),sha256=sha,bytes=p.stat().st_size)
packet=load(E/"primary-result-and-gap-review-packet.json");v=load(E/"primary-independent-verification.json")
assert v["completed"] and v["used_economic_CPU"]=="3641.68333"
assert bind(P/"consumer-independent-review.json")==packet["canonical_consumer_remains"]
assert bind(P/"consumer-implementation-manifest.json")==packet["current_implementation"]
prof=E/"primary-independent-resource.txt";t=prof.read_text()
measured=round(sum(float(re.search(label+r" time \(seconds\): ([0-9.]+)",t).group(1)) for label in ("User","System")),2)
charge=round(measured+3,2);assert charge<=39.57
res=dict(pool="original comparison1000; continuation of r6 unused39.57 only",actual_check_outer_CPU=measured,smallread_setup_seal_handoff_allowance_CPU=3,inclusive_charge_CPU=charge,comparison_before_CPU=519.02,comparison_after_CPU=round(519.02+charge,2),comparison_remaining_CPU=round(480.98-charge,2),r6_80_used_including_prior40_43=round(40.43+charge,2),r6_80_unused_CPU=round(39.57-charge,2),CPU=1,fresh_cap_MiB=400,affinity=[0],maximum_RSS_KiB=int(re.search(r"Maximum resident set size \(kbytes\): (\d+)",t).group(1)),profile=bind(prof),author_ledger_mutated=False,seal_actual_inside_allowance=True)
(E/"primary-gap-independent-review-resource.json").write_text(json.dumps(res,indent=2)+"\n")
snapshot=E/"trial-ledger-at-primary-independent-review.jsonl"
assert not snapshot.exists();snapshot.write_bytes((E/"trial-ledger.jsonl").read_bytes())
bindings=dict(request=bind(E/"primary-result-and-gap-review-packet.json"),canonical_consumer=packet["canonical_consumer_remains"],implementation=packet["current_implementation"],results=packet["result_bindings"],interpretation=packet["interpretation"],addendum=packet["addendum"],interpretation_code=packet["interpretation_code"],trial_snapshot=bind(snapshot),settled_resources=packet["resource_bindings"],verification=bind(E/"primary-independent-verification.json"),review_code=bind(E/"independent_primary_gap_check.py"),review_resource=bind(E/"primary-gap-independent-review-resource.json"))
primary=dict(schema_version=1,at_utc=datetime.now(UTC).isoformat(),author=packet["author"],reviewer=packet["reviewer"],verdict="accept_primary_unknown_results_and_known_prefix",bindings=bindings,corrections=[],mother_question_complete=False,
    findings=dict(physical_full_strategy_starts=5,distinct_definitions=4,unknown_outcomes=4,complete_economic_returns=0,full_period_return=None,full_holding_conclusions=None,matched_common_sessions=176,common_end="2024-09-12T19:59:59+00:00",common_SYSTEM_equity=19911.89,common_EMA_equity=19229.05,common_SYSTEM_marked_return=-0.0044055,common_EMA_marked_return=-0.0385475,common_SYSTEM_fill_events=8,common_EMA_fill_events=42,common_SYSTEM_fees_USD=18.16,common_EMA_fees_USD=352.25,own_prefix_closed_attempt_counts=dict(SYSTEM=9,EMA=21),own_prefix_counts_are_not_matched=True,first_unknown=dict(EMA="2024-09-13T14:01:00+00:00",SYSTEM="2025-02-11T15:29:00+00:00"),underlying_event_offset_ns=2,matching_both_OHLC=True),
    interpretation="Both common marked returns are negative. SYSTEM's3.4142pp difference is not isolated mechanism contribution: substantially different exposure, trade count and fees remain. Four N/A full paths are preserved; later mechanical fills are uninterpretable and do not close the known lot. No Alpha/private performance/complete holding or mechanism refutation claim is admitted.",
    verification_coverage=dict(all_packet_small_bindings_verified=True,firstunknown_month_audit_witnesses_checked=4,common_endpoint_NAV_samples_checked=4,reported_fill_tapes_and_fee_sums_checked=True,common176_calendar_verified_from_accepted_input_inventory=True,full176_NAV_series_Sharpe_drawdown_recomputed=False,benchmark_cash_and_six_names_are_partial_unmatched=True,full_logs_or_Frame_scanned=False,old33_74_25_24_reused=True),
    resource_lineage=dict(new_economic_consumed_CPU=3641.68333,remaining_original_CPU=3535.04667,inflight_before_new_witness=0,original_task_pool_before_use=7176.73,old_public_replay_CPU=23.27,old_preparation_failures_not_reclassified=True),
    next_value_decision="Two fixed raw bar witnesses are an informative next input check before more matched account spending. They can distinguish retained-normalization/cache absence from current raw absence. Raw absence alone cannot prove no trade/quote crossing. Keep all old outcomes unchanged; any correction/replay requires ordinary bound input/version acceptance.",
    workflow_scope="Result interpretation accepted; complete mother research/workflow is not finished",research_pass=False,paper_ready_pass=False,broker_activity=0,resource=res)
(E/"primary-result-independent-review.json").write_text(json.dumps(primary,ensure_ascii=False,indent=2)+"\n")
gap=dict(schema_version=1,at_utc=datetime.now(UTC).isoformat(),author=packet["author"],reviewer=packet["reviewer"],verdict="approve_bounded_gap_witness",economic_execution_admitted=False,
    bindings=dict(code=packet["gap_code"],scope=packet["gap_scope"],transport=packet["transport"],input=packet["existing_input"],input_inventory=packet["existing_input_inventory"],provider_method=packet["existing_provider_method"],scientific_plan=packet["scientific_plan"],primaryresults=packet["result_bindings"],primary_result_review=bind(E/"primary-result-independent-review.json"),canonical_consumer=packet["canonical_consumer_remains"],implementation=packet["current_implementation"],review_resource=bind(E/"primary-gap-independent-review-resource.json")),
    allocation=dict(requests=2,entity_bytes=400000,prospective_input_CPU=80,CPU=1,memory_MiB=900),
    resource_classification="Prospective frozen-consumer source dependency within original7176.73 economic-resource ledger, with zero strategy/economic replay permission. This narrow request acceptance does not rewrite old preparation costs or canonical r6 grant.",
    lineage=dict(original_economic_task_pool_CPU=7176.73,consumed_CPU=3641.68333,remaining_before_reservation_CPU=3535.04667,maximum_remaining_after80_reservation_CPU=3455.04667,canonical_r6_grant_unchanged=True,original_market_request_cap=96,requests_already_used=80,requests_remaining_before=16,request_remaining_after_maximum=14,original_entity_cap=134217728,entity_remaining_before=78902258,entity_remaining_after400000_reservation=78502258,no_budget_reset=True),
    exact_scope="Only current raw SIP1Min LMND on2024-09-13 13:30..20:00Z and2025-02-11 14:30..21:00Z, asof symbol mapping '-'; one GET per fixed day, no pagination/retry/redirect/quote endpoint. Each entity cap200000B, response/wire distinction retained.",
    conditions=[
        "Create one unique original-pool reservation with runtime0 and empirical/prospective-input at most80, then current canonical-consumer native validation/currentowner/hold/bindings/fresh900MiB and CPU0 must pass before env/factory/GET. This sidecar is input permission, not a new600/1800/7200 allocation.",
        "Use the bound existing factory/_client/bounded_get only. Durable per-attempt count and byte reservation precede GET; partial/failed/unknown bytes stay committed. Do not log secrets or treat asof mapping as historical vintage.",
        "Only parse retained complete200 bodies; token/error/incomplete response stops without follow-up. Preserve raw body/entity hash and absence/invalidity. The fixed end timestamp may include a16:00 bar; treat it as outside the requested RTH390-minute gap grid, not an extra RTH completion.",
        "Compare only the two actually bound normalized days and their firstunknown minute/source decimal values. Original packet is authoritative; duplicate/out-of-range or otherwise anomalous raw rows must be disclosed and cannot certify complete coverage or exact uniqueness merely because a dict parser deduplicates keys.",
        "No padding, source overwrite, modified Frame, live account, fit, PnL computation, strategy replay or resurrection of old unknown paths. Raw omission proves only omission from this current source response, not zero trading or harmless stop/quote behavior.",
        "If raw contains missing minutes, retain the observed version discrepancy and submit ordinary corrected-input/version acceptance before any replay. If it also omits them, retain the unresolved quote/trade/feed-coverage question; do not infer the whole market or Martin mechanism is infeasible.",
        "No broader exception to r6 no-new-acquisition condition is granted. These exact two requests consume existing16/78902258 headroom, with failures/CPU/setup/native/unknown/postexit charged once in the old pools. Author serially settles actual usage; reviewer does not edit ledgers.",
    ],
    scope_code_review="Factory initialization follows independent receipt, exact bindings, unique launch and actualnative. Global count/byte reservation precedes bounded_GET; max2 fixed requests and no automatic retry/redirect. Source result remains diagnostic even if transport fails.",
    current_native_pass_asserted=False,GET_started_by_reviewer=False,canonical_consumer_modified=False,mother_question_complete=False,review_resource_charge_shared_with_primary=res)
(E/"gap-witness-independent-review.json").write_text(json.dumps(gap,ensure_ascii=False,indent=2)+"\n")
assert bind(P/"consumer-independent-review.json")==packet["canonical_consumer_remains"]
print(json.dumps(dict(primary=bind(E/"primary-result-independent-review.json"),gap=bind(E/"gap-witness-independent-review.json"),resource=res)))
