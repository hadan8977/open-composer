import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

E=Path(__file__).resolve().parent; P=E.parent
ROOT=Path('/root/codex-test/open-composer')
def bind(path):
    return {'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
def check(obj):
    if isinstance(obj,dict):
        if 'path' in obj and 'sha256' in obj:
            p=ROOT/obj['path']; assert p.stat().st_size<2_000_000
            assert bind(p)==obj or (bind(p)['sha256']==obj['sha256'] and 'bytes' not in obj),str(p)
        else:
            for v in obj.values(): check(v)
    elif isinstance(obj,list):
        for v in obj: check(v)
packet=json.loads((E/'source-v2-close-affected-review-packet.json').read_text()); b=packet['bindings']
canonical=E/'source-clock-component-independent-review.json'
assert bind(canonical)==b['G1_acceptance']
prior=json.loads(canonical.read_text())
check(prior['bindings']['native_dependencies'])
archive=E/'source-clock-v2/prior-G1-independent-review.json'
assert not archive.exists()
archive.write_bytes(canonical.read_bytes())
resource_note={'pool':'original comparison1000 / existing source-science80','actual_check_outer_CPU':1.26,'seal_setup_read_handoff_allowance_CPU':4,'inclusive_charge_CPU':5.26,'comparison_before_CPU':559.02,'comparison_after_CPU':564.28,'comparison_remaining_CPU':435.72,'source_science80_before_remaining_CPU':52.05,'source_science80_remaining_CPU':46.79,'seal_measured_profile':'source-v2-close-independent-seal-resource.txt','seal_is_inside_allowance_not_extra':True,'actual_check_RSS_KiB':24372,'fresh_memory_cap_MiB':400,'CPU_affinity':[0],'author_serial_settle_once':True,'author_ledger_modified':False}
lineage={'original_pool_CPU':7176.73,'reported_used_CPU':3864.63333,'reported_remaining_CPU':3312.09667,'inflight_at_packet':0,'offline200_used_CPU':142.56,'offline200_remaining_CPU':57.44,'old_preparation_CPU':2000.05,'source180_already_consumed_CPU':25.06,'source180_remaining_CPU':154.94,'two_sequential_probes_max_CPU':374.94,'new_global_allocation':False,'execution_rule':'Live cumulative committed/unknown/inflight accounting remains decisive; reserve each sequential job once before launch, current native/fresh/owner/hold/PID/exact binding and empirical_limit after native child CPU required. No resetting original180 or7176.73.'}
common={'schema_version':1,'at_utc':datetime.now(UTC).isoformat(),'author':packet['author'],'reviewer':packet['reviewer'],'verdict':'approve_implementation','required_corrections':[],'scientific_approval_preserved':True,'economic_execution_admitted':False,'canonical_r6_modified':False,'mother_question_complete':False,'research_pass':False,'paper_ready_pass':False,'resource_lineage':lineage,'review_resource_shared_once':resource_note,'review_actions':{'native_CLI':0,'engines':0,'HTTP':0,'large_Frame_reads':0,'large_Frame_hashes':0,'new_model_or_full_strategy_runs':0}}
base_bindings={'affected_packet':bind(E/'source-v2-close-affected-review-packet.json'),'implementation_manifest':b['implementation'],'science':prior['bindings']['science'],'canonical_old_consumer':prior['bindings']['canonical_old_consumer'],'old_native_manifest':prior['bindings']['old_native_manifest'],'native_dependencies':prior['bindings']['native_dependencies'],'independent_verification':bind(E/'source-v2-close-independent-verification.json'),'independent_check':bind(E/'independent-source-v2-close-check.py')}
source=dict(common)
source.update(scope='V2 observed initial quote expectation and before-assert persistence only; accepted G1 rearm/library retained. Two fixed2-minute source windows,12controlled fixtures; not a strategy return or broker execution claim.',real_market_native_probe_admitted=True,
 allocation={'technical_source_window_CPU':154.94,'CPU':1,'memory_MiB':900,'HTTP':0,'original_component_envelope_CPU':180,'already_consumed_CPU':25.06,'reset_allowed':False},
 bindings={**base_bindings,'driver':b['source_V2_driver'],'fixtures':b['source_V2_fixtures'],'source_library':b['source_library_unchanged'],'source_module':b['sourceclock_module_unchanged'],'actual_raw_inputs':prior['bindings']['actual_raw_inputs'],'prior_G1_review':bind(archive),'V2_author_proof':b['V2_repair'],'prior_actual_failed_run':b['prior_actual_source_failure'],'prior_actual_failed_profile':b['prior_actual_source_profile']},
 findings=['Independently parsed the existing two quote entities, checked all12 latest actual messages strictly before frozen submit. September latest is source ordinal1,16ns before submit, ask18.2; February latest is ordinal0,10000ns before submit, ask35.36. Latest messages themselves are valid; no fallback over a bad latest quote.',
 'All fields other than V2 identity and expected initial quote/price equal V1. Original reference/stops/quantity/R0/submission/protection clocks are unchanged. This is a source-input expectation correction, no profitability-based timing selection.',
 'Driver persists each native return and pending validation progress before price/clock/quantity assertions. V1 physical engine exposure1/accepted results0 remains; lost fill is N/A and is not inferred from current source.',
 'Prior independent five synthetic native checks reused. V2 real source results remain unobserved pending actual execution and later result acceptance.'],
 boundaries=['10positiveR0 plus2invalidR0/zeroengine fixtures only; old four full-path unknown results remain unknown.','Synthetic100-share depth, current-vintage event clocks, observed BBO and broker election limits remain unchanged.','No new Frame, source fetching, full strategy trial, source-clock integration into canonical r6, or global budget.'],
 historical_binding_resolution={'old_G1_original_path':b['G1_acceptance'],'immutable_exact_archive':bind(archive),'note':'Author sealed packet/manifests retain historical G1 reference; this archive supplies those exact original bytes after canonical update. Executable bindings use new driver/fixtures and the immutable archive, never the obsolete current-path SHA.'})
check(source['bindings'])
source_bytes=json.dumps(source,ensure_ascii=False,indent=2)+'\n'
canonical.write_text(source_bytes)
source_immutable=E/'source-clock-v2/independent-component-review.json'
assert not source_immutable.exists();source_immutable.write_text(source_bytes)
close=dict(common)
close.update(scope='Isolated immutable source JSON/frozen Frame decoding reuse; bounded fixed full March2024 reference-versus-candidate measurement. Candidate core not applied.',
 actual_March_source_probe_admitted=True,
 allocation={'fixed_March_CPU':220,'CPU':1,'memory_MiB':900,'HTTP':0,'source_intervals':'fixed previously-seen March2024,7800 minute packets','native_engines':4,'variants':2,'accounts_per_variant':2,'policies':['P_SYSTEM','P_EMA'],'route':'market','cost_bps_per_side':20,'OHLC':'O-H-L-C','other_variants_admitted':False,'scope':'Inclusive actual native/import/input IO/hash/encoding/engine/serialization/failed/teardown/unknown costs; partial or unknown month never a throughput gate.'},
 bindings={**base_bindings,'driver':b['source_close_driver'],'candidate_manifest':b['source_close_candidate'],'candidate_files':b['isolated_candidate_files'],'original_reference_files':b['old_core_files'],'inert_import_harness':b['inert_import_harness'],'inert16_evidence':b['source_close_inert16'],'March_source':b['March_source_inventory'],'frame_result':b['frame_result_unchanged'],'immutable_source_component_review':bind(source_immutable),'candidate_diff':b['diff']},
 findings=['Only source JSON and frozen Frame/support/anchor values are shared; each strategy keeps separate cash, book, native cache, policy/controller, staged/pending orders and feedback. Per-account overrides construct a fresh Frame.',
 'Independently executed actual class/decoder AST plus candidate cache without Nautilus: allFrame fields equal, source frames reused by identity, account override values isolated, bad_clock/missing_low/extra_field errors match and occur only when that row is requested. Interval cache clear verified.',
 'All four author synthetic scenarios were deep-compared reference/reuse across two independent accounts (16already-run engines); no engine repeated here. New market/market full March pairing remains to be measured, not credited by those synthetic scenarios.',
 'Actual driver binds specific March file to inherited frame preparation inventory; no large Frame read/hash done in review. Execution must freshly verify it. Native children precede empirical_limit rearm/heavy imports. Exact reference/candidate interpreted state/order/controller/fees/clocks equality and equal event counts are required; partial/unknown throws after saving available evidence.',
 '220CPU is a bounded technical measurement envelope based on prior month cost plus IO/admission/failure/output/teardown margin. No speedup or complete2-year matched affordability is inferred before measured full-clock acceptance.'],
 limits=['Native order comparison uses the explicit driver fields (id/status/quantity/filled/leaves/ts_init/ts_last), alongside audit, policy states, snapshots, lots, controller and source events; it is not a bytewise comparison of all Nautilus internals or random UUIDs.',
 'Each variant is persisted before comparison; all failures and incomplete exposure retain cumulative cost. Results cannot select a profitable path or silently change candidate/route/cost/clock.',
 'No production/core replacement is approved by this probe receipt. Applying a demonstrated same-semantics improvement and deriving a complete matched block cost remains a subsequent affected acceptance.'],
 linked_source_review=bind(source_immutable))
check({k:v for k,v in close['bindings'].items() if k!='March_source'})
target=E/'source-close-independent-review.json'
assert not target.exists();target.write_text(json.dumps(close,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'source_review':bind(canonical),'source_close_review':bind(target),'charge_once_CPU':5.26},indent=2))
