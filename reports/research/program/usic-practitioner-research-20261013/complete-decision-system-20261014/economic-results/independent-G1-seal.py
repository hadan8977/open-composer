import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

E=Path(__file__).resolve().parent
ROOT=Path('/root/codex-test/open-composer')
def bind(p):
    return {'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
packet=json.loads((E/'source-clock-G1-review-packet.json').read_text())
prior_path=ROOT/packet['bindings']['prior_component_review']['path']
prior=json.loads(prior_path.read_text())
assert hashlib.sha256(prior_path.read_bytes()).hexdigest()=='f287172f0d8245e83829b19257a8e4a1629ff319b15bf6fda00aacdc4b5af284'
current=E/'source-clock-component-independent-review.json'
assert current.read_bytes()==prior_path.read_bytes(), 'Unexpected concurrent canonical change'
bindings=json.loads((E/'source-clock-G1-independent-current-bindings.json').read_text())
bindings['G1_independent_verification']=bind(E/'source-clock-G1-independent-verification.json')
bindings['G1_independent_check']=bind(E/'independent-G1-check.py')
review={
 'schema_version':1,'at_utc':datetime.now(UTC).isoformat(),
 'author':packet['author'],'reviewer':packet['reviewer'],
 'verdict':'approve_implementation','implementation_semantics_accepted':True,
 'scientific_approval_preserved':True,'real_market_native_probe_admitted':True,
 'economic_execution_admitted':False,
 'scope':'G1 cumulative-CPU rearm placement and delayed native import only; prior accepted component semantics inherited. Conditional180CPU real-source component probe only, not a complete strategy economic run.',
 'bindings':bindings,'required_corrections':[],
 'G1_resolution':{'accepted':True,'actual_diff':'Only empirical_limit import/calls and delayed source_clock_native import; non-admission library functions and driver main remaining AST identical to prior accepted code.',
   'driver_order':['current native_admission','phase_admission','empirical_limit','lazy source_clock_native import'],
   'library_order':['phase_admission','empirical_limit','fixture/raw validation'],
   'independent_actual_helper_fake_child_CPU_check':{'child0_soft_hard':[165,173],'child30_soft_hard':[135,143]},
   'old_native_semantics':'Five independently accepted synthetic engines and all prior boundary checks reused, no new engine or CLI executed.'},
 'accepted_components':prior['accepted_components'],
 'allocation':{'technical_source_window_CPU':180,'CPU':1,'memory_MiB':900,
   'source_requests':0,'scope':'Only12 frozen SOURCE_CLOCK_V1 fixtures in the two bound2-minute LMND source windows:10positiveR0 components,2invalidR0 zero-engine/N/A. Inclusive native children/imports/probe/failed/teardown/unknown within180.',
   'origin':'Original7176.73 cumulative pool; not new money or a reset. Unique prelaunch reservation and actual current native/fresh/owner/hold/PID/bindings guards remain mandatory.'},
 'resource_lineage':{'original_economic_pool_CPU':7176.73,'author_report_used_CPU':3827.90333,'author_report_remaining_CPU':3348.82667,'author_report_inflight_CPU':0,'offline200_used_CPU':130.89,'offline200_remaining_CPU':69.11,'old_preparation_CPU':2000.05,
   'decoder_postexit_reconciliation':'11.000109 internal rusage replaced by11.48 inclusive outer+launcher, delta0.479891 once; new binding verified from G1 packet. Old review snapshot retained in archive and not used as current balance.',
   'other_isolated_close_candidate':'Costs retained as reported; candidate implementation and16new synthetic comparisons NOT reviewed or admitted here.',
   'execution_rule':'Driver must reconcile live commitments and reserve before launch; snapshot is not a mutable-ledger hash gate or spendable-balance promise. No author ledger modified.'},
 'limits':['Observed BBO remains distinct from then-certified NBBO and complete broker stop election. I condition does not itself establish stop eligibility.',
   'No new Frame or quote/trade injection into old strategy paths; four unknown outcomes remain unknown. No claims about full strategy returns or complete feed/calendar/cash consumer integration.',
   'Native/fresh checks are conditions for owner execution, not already-passed assertions in this receipt. No actual source engine ran during this review.',
   'Mother question continues after the component interpretation; earlyunknown1470.75 is not affordability of the full96 matrix.'],
 'canonical_r6_modified':False,'actual_native_CLI_by_reviewer':0,'synthetic_native_engines_run_this_review':0,'real_source_native_engines_run_by_reviewer':0,'HTTP':0,'full_strategy_returns':0,'mother_question_complete':False,'research_pass':False,'paper_ready_pass':False,
 'resource':{'pool':'Original comparison1000, same source-science80','attempt1_measured_outer_CPU':1.15,'attempt2_measured_outer_CPU':1.09,'measured_before_seal_CPU':2.24,'inclusive_setup_seal_smallread_handoff_allowance_CPU':4.0,'inclusive_charge_CPU':6.24,
   'seal_profile':'source-clock-G1-independent-seal-resource.txt','seal_actual_included_in_allowance_not_added_again':True,
   'comparison_before_CPU':552.78,'comparison_after_CPU':559.02,'comparison_remaining_CPU':440.98,'source_science80_before_remaining_CPU':58.29,'source_science80_after_remaining_CPU':52.05,
   'max_RSS_before_seal_KiB':20960,'fresh_memory_cap_MiB':400,'CPU_affinity':[0],'failure_preserved':'First independent binding check correctly detected the old decoder receipt had settled to newer inclusive bytes. Reused execution bindings now omit that historical mutable cost snapshot; new accounting evidence checked in the G1 packet. No science/input or guard weakened.',
   'author_serial_settle_once':True,'author_ledger_modified':False,
   'profiles':[bind(E/'source-clock-G1-independent-resource.txt'),bind(E/'source-clock-G1-independent-resource-attempt2.txt')]}
}
current.write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(bind(current)))
