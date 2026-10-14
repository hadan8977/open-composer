"""Accept component semantics; require one cumulative-CPU gate placement fix."""
import hashlib
import json
from datetime import UTC,datetime
from pathlib import Path
import re
import resource
resource.setrlimit(resource.RLIMIT_CPU,(2,3))
R=Path.cwd();P=R/"reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014";E=P/"economic-results"
def load(p): return json.loads(p.read_text())
def bind(p):
    raw=p.read_bytes();return dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
packet=load(E/"source-clock-component-review-packet.json");b=packet["bindings"]
manifest=load(R/b["implementation"]["path"]);v=load(E/"source-clock-component-independent-verification.json")
assert v["completed"] and v["synthetic_native_engines"]==5
assert bind(R/b["implementation"]["path"])==b["implementation"]
assert bind(P/"consumer-independent-review.json")==b["currentcanonical"]
profiles=[E/"source-clock-component-independent-resource.txt",E/"source-clock-component-independent-resource-attempt2.txt"]
actual=0;peak=0
for p in profiles:
    s=p.read_text();actual+=sum(float(re.search(label+r" time \(seconds\): ([0-9.]+)",s).group(1)) for label in ("User","System"))
    peak=max(peak,int(re.search(r"Maximum resident set size \(kbytes\): (\d+)",s).group(1)))
actual=round(actual,2);charge=round(actual+3,2);assert charge<=75.84
res=dict(pool="original comparison1000; same source-science80 remaining75.84",actual_outer_CPU_before_seal=actual,smallread_setup_seal_handoff_allowance_CPU=3,inclusive_charge_CPU=charge,comparison_before_CPU=535.23,comparison_after_CPU=round(535.23+charge,2),comparison_remaining_CPU=round(464.77-charge,2),current_science80_used_CPU=round(4.16+charge,2),current_science80_remaining_CPU=round(75.84-charge,2),old_r6_80_historical_unused_CPU=27.52,old_consumer100_closed=True,profile_bindings=[bind(p) for p in profiles],fresh_cap_MiB=400,affinity=[0],maximum_RSS_KiB=peak,failed_snapshot_check_CPU=1.24,failure_reason="Packet frozen total3746.73333 was followed by actually settled separate offline11.000109; live ledger reconciled, not a scientific failure or refund",author_ledger_mutated=False,seal_already_inside_allowance=True)
(E/"source-clock-component-independent-review-resource.json").write_text(json.dumps(res,indent=2)+"\n")
fixtures=load(R/b["fixtures"]["path"])
raw={x["path"]:x for f in fixtures["fixtures"] for x in f["source_versions"]}
native_files=load(R/b["current_old_manifest"]["path"])["files"]
review=dict(schema_version=1,at_utc=datetime.now(UTC).isoformat(),author=packet["author"],reviewer=packet["reviewer"],verdict="revise_implementation",implementation_semantics_accepted=True,scientific_approval_preserved=True,real_market_native_probe_admitted=False,economic_execution_admitted=False,
bindings=dict(review_packet=bind(E/"source-clock-component-review-packet.json"),implementation_manifest=b["implementation"],driver=manifest["driver"],component_files=manifest["component_files"],fixtures=b["fixtures"],actual_raw_inputs=list(raw.values()),science=b["science"],canonical_old_consumer=b["currentcanonical"],old_native_manifest=b["current_old_manifest"],native_dependencies=native_files,author_verification=b["verification"],old_version_preservation=b["old_version_preservation"],source_scope=b["source_scope"],offline_component_settlements=packet["resources"]["receipts"],postpacket_noncomponent_settlement=v["post_packet_additional_closed_charge"],independent_verification=bind(E/"source-clock-component-independent-verification.json"),independent_check=bind(E/"independent_source_component_check.py"),review_resource=bind(E/"source-clock-component-independent-review-resource.json")),
accepted_components=[
"12 exact SOURCE_CLOCK_V1 fixtures verified:10 positive R0 and2 nonpositive invalid requiring zeroengine/N/A. First source/central quote ordinals, retrospective thresholds, reference, quantity,100 synthetic depth,10us submission, cost and unknown boundary frozen. No historical strategy causality is claimed for these interventions.",
"Typed observed BBO, synthetic certified necessary condition and broker election remain distinct. Bad latest BBO invalidates old knowledge; equal quote/trade timestamps, missinginitial BBO, unsupported qualification and stale observation return unknown. Nine-digit parsing and only-matured allI QA remain intact. R is an explicit observed-reference filter, not a firmNBBO certification.",
"Independent5 synthetic native engines passed:quantity1/full25/terminalpartial25to1/unknown before laterstop and an additional123456789ns-offset clock case. Actual integer fill clocks match the frozen synthetic submission, while policy datetime precision remains explicitly microseconds. Fee/cash/closedR reconciled withDecimal; postunknown quantity/closedR/feedback/snapshot quarantine matches firstknownprefix.",
"InvalidR0 independently returned0engine; real-source library invocation without admittedjob is refused before an engine. Raw/fixture binding checks and currentowner/hold/PID/currentnative phase checks are present. Exact driver fixed-spec path is the reviewed entry, not a general authorization for arbitrary standalone spec arguments.",
"NoBarBoundary is a typed interface/prohibition, not evidence that the fullcalendar/T+1/corporate-action consumer has been integrated. Stop-reference arrays are necessary-price annotations from initial controlled protection, not a complete independently evolving broker order lifecycle or a count of actual stop elections.",
],
required_corrections=[dict(id="G1",severity="cumulative_resource_gate_placement",scope="probe_source_clock.py and source_clock_native.py actual-source admission only",evidence="native_admission calls empirical_limit before its memory/native CLI children. New driver then phase_admission but does not reapply empirical_limit after their CPU usage; library phase_admission also does not rearm the CPU limit. For180 with launcher5 and a30CPU native child, pre-child ownhard173 must become143; otherwise own-process RLIMIT still excludes that actual child cost. The per-fixture remaining25 check is useful but is not the recalculated hard guard.",minimum_fix="Import existing empirical_limit; call it after native_admission and phase_admission, before source parsing/native module work. Move driver top-level source_clock_native.run_component import to after this guard. Reapply the same existing helper in real_source_admission after phase_admission so the separately callable actual library path has the same cumulative limit. Do not introduce a new controller/budget or repeat native CLI.",verification="Small inert call-order/usage fixture can verify the existing helper is rearmed after simulated child usage and before native import/engine creation; no actual CLI,source-native replay or repeat of the five semantic engines is needed. Rebind only changed driver/library/manifest and preserve prior bytes.")],
resource_judgment="Offline/protocol/input work is substantively accepted, but the proposed real-source180 remains unallocated until G1 is bound and independently accepted. This is an ordinary resource placement repair, not new science or a reason to stop the mother problem.",
allocation=dict(technical_source_window_CPU=0,CPU=1,memory_MiB=900,HTTP=0,fit=0,Frame=0,full_strategy_economic_replay=0),
proposed_after_G1_acceptance=dict(technical_source_window_CPU=180,CPU=1,memory_MiB=900,real_market_native_probe_admitted=True,scope="Only bound12 cases on two fixed source windows;10 native quote-proxy components and2 invalidR0/zeroengine cases. Actual currentnative/fresh/owner/hold/unique reservation mandatory; no oldpath healing or fullstrategy returns."),
repair_authority="Use existing offline200 allocation; no new CPU pool. Bound G1 code/syntax and tiny pure call-order check are permitted within that remaining allowance, with original unique reservation/freshCPU0 and actual outer/failure/unknown settlement. Current offline scope had49.72 in this packet and separate11.000109 subsequent source-decode work under the same science grant, leaving139.279891 of200 at this readback; no refund/reclassification of old preparation2000.05.",
resource_lineage=dict(packet_component_offline_CPU=49.72,additional_closed_source_decode_CPU=11.000109,offline200_used_at_readback_CPU=60.720109,offline200_remaining_at_readback_CPU=139.279891,current_economic_used_CPU=3757.733439,current_original_remaining_CPU=3418.996561,packet_at_seal_used_CPU=3746.73333,old_preparation_CPU=2000.05,no_budget_reset=True,unrequested_decode_code_not_reviewed=True),
continuation="After this one affected correction, accept the new binding and perform bounded real source-window interpretation. Keep complete matched economic work and measured feed/close efficiency as the mother objective; earlyunknown1470.75 is not fullmatrix cost or completion. No Root intermediate action required.",
canonical_r6_modified=False,real_source_native_engines_run_by_reviewer=0,synthetic_native_engines_run_by_reviewer=5,full_strategy_returns=0,mother_question_complete=False,research_pass=False,paper_ready_pass=False,resource=res)
(E/"source-clock-component-independent-review.json").write_text(json.dumps(review,ensure_ascii=False,indent=2)+"\n")
assert bind(P/"consumer-independent-review.json")==b["currentcanonical"]
print(json.dumps(dict(review=bind(E/"source-clock-component-independent-review.json"),resource=res)))
