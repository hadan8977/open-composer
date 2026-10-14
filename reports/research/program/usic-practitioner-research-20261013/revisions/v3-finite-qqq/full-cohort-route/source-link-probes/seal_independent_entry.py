import json,hashlib,re
from pathlib import Path
from datetime import datetime,timezone
P=Path(__file__).resolve().parent;R=P.parent;V=R.parent;ROOT=Path.cwd()
def bind(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(b).hexdigest())
v=json.loads((P/'independent-verification.json').read_text());m=json.loads((P/'request-manifest.json').read_text())
assert len(v['binding_mismatches'])==1 and v['binding_mismatches'][0]['path']=='data/sip/minute/_LAYOUT.json'
assert v['whole8cache_file_SHA_verified'] and v['guard_positive_and_badallocation_consumedledger_checks']
for b in m['entry_bindings']:assert bind(ROOT/b['path'])==b
layout_path=ROOT/'data/sip/minute/_LAYOUT.json';body=layout_path.read_bytes();layout=json.loads(body)
snapshot=P/'independent-current-layout-snapshot.json';assert not snapshot.exists();snapshot.write_bytes(body)
mapping={s:sorted(k for k,ss in layout['shard_symbols'].items() if s in ss) for s in ['PCAR','ROST','GEHC','TSLA']}
for s,shards in mapping.items():assert shards==json.loads((R/f'cache-basis-probe/{s}.json').read_text())['locator_shards']
resource_files=['independent-resource-failed1.txt','independent-resource.txt'];charges=[]
for name in resource_files:
 t=(P/name).read_text();cpu=round(sum(float(re.search(k+r' time \(seconds\): ([\d.]+)',t)[1]) for k in ['User','System']),2)
 charges.append(dict(receipt=bind(P/name),inclusive_CPU=cpu))
actual=round(sum(x['inclusive_CPU'] for x in charges),2);total=round(actual+5,2);used=round(234.64+total,2)
assert actual==8.92
receipt=dict(schema_version=1,as_of_utc=datetime.now(timezone.utc).isoformat(),author='f9add224-744b-471c-b812-c43cc179fa38',reviewer='ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3',verdict='accept_bounded_source_route_entry',accepted_for_execution=True,request_manifest=bind(P/'request-manifest.json'),entry_bindings=m['entry_bindings'],allocation=dict(requests=3,entity_bytes=4718592),economic_execution_admitted=False,
 authority=bind(V/'root-task-pool-continuation.json'),
 scope='Exact three same-source route probes only; same frozen101 historical issues, GEHCV solely lineage of existing GEHC issue. No investment-population/seed/threshold/candidate change.',
 actual_cache_acceptance={
  'verdict':'accept_observed_cache_basis_counterexamples_with_locator_provenance_limit',
  'accepted':'All8 actual cache parquet SHA pass. Four fixed Jan2 source/cache comparisons independently recomputed:PCAR388/ROST383/GEHC385 priceOHLC/VWAP differ while volume/tradecount agree;TSLA390 all7 fields agree. All12 recorded collision pairs and their raw pointers/cache timestamp keys/P_ref round-up independently match. Current daily-factor inverse residuals recomputed, including ROST+0.2627232709USD.',
  'author_full40day_counts':'15438/15380/15536/15600 recorded counts and producer logic reviewed; not independently rerun over all40 days. No whole101 or2024–25 cash-execution certification.',
  'interpretation':'The observed stored-price field is non-injective at these examples; ROST samehigh135.43 corresponds to raw138.855 versus138.85 and different frozenP_ref138.87/138.86. Sameclose collisions prove close ambiguity only; differenthigh/P_ref is not attributed to close. This does not prove every reconstruction with additional independent source data impossible. TSLA is a real positive control, not proof other dates/symbols raw.',
  'historical_locator_binding_not_verified':v['binding_mismatches'][0],
  'current_locator_snapshot':bind(snapshot),'current_four_symbol_shards':mapping,
  'nonblocking_reason':'Only mutable_LAYOUT locator differs; its old exact bytes are not available to this check and are not certified. Independent current snapshot maps the same four symbols to the same shards; all8 fixed data-file hashes and decisive numeric observations are verified directly. Historical cohort selection came from the frozen NPORT/hash roster, not_LAYOUT, and the approved3-request executor never reads_LAYOUT. Thus this limits old locator provenance, not request identity, quota guard or data counterexamples.',
  'preservation':'Original manifest and oldexpectedSHA retained untouched; current snapshot is separately labeled, not a retrospective replacement. Future packets should bind a frozen locator copy or omit mutable locator as authoritative numeric input.'},
 rationale_by_request={
  'TSLA_pre2016_raw_history':'One bounded packet can distinguish a local2016 acquisition boundary from provider response coverage. Empty/error/truncated history is evidence only for that request; first row does not prove first security episode or certify EMA seed.',
  'GEHC_GEHCV_birth_prefix':'Tests existing36266G107 predecessor-symbol coverage using known name-change lineage. GEHCV response cannot alone certify when-issued eligibility or justify a raw-share splice; remains the same issue investigation.',
  'four_current_vintage_all_minute':'Paired currentALL against already held rawJan2 and oldcache helps distinguish version differences and representation loss without fitting an inverse or changing rules. No extra raw sample or cohort acquisition.'},
 execution_limits=[
  'Exact nine entry bindings, request manifest and independent receipt required; owner/hold/CPU0/old13+47 ledgers and absent consumed probe ledger checked before credentials orHTTP.',
  'Existing licensed factory only after actual acceptance. No credential values initialized/read by reviewer, no retry/redirect/fallbackURL ornewprovider.',
  'Exactly max1 page per object, max1572864 entity bytes each; request and fullunknown-byte reservation charged before call. Token retains incomplete object and does not authorize pagination.',
  '401/403/429, transport or incomplete entity stops remaining batch under accepted collector. Other failed/empty slots remain recorded. Wire overhead unknown is not represented as exact entity bytes.',
  'Fresh singleCPU memory admission and original remainingMartin preparation pool required. No use of HF resource pool; no added source/public search units or economic CPU.',
  'Results return directly for actual input acceptance and continued full route judgment; no per-stepRoot request. Threeprobe allocation is not full101 readiness or7200 allocation.'
 ],
 admission_evidence=dict(bindings=bind(P/'independent-verification.json'),check_code=bind(P/'independent_verify_entry.py'),positive_guard_pass=True,bad_allocation_rejected=True,consumed_ledger_rejected=True,inert_cases=v['inert_collector_cases'],real_HTTP=0,credentials_loaded=False),
 aggregate=dict(prior_used_requests=60,prior_entity_bytes=43895341,prior_remaining_requests=36,prior_remaining_bytes=90322387,new_reserved_requests=3,new_reserved_entity_bytes=4718592,worstcase_cumulative_requests=63,worstcase_cumulative_entity_bytes=48613933,remaining_unreserved_requests=33,remaining_unreserved_entity_bytes=85603795,unused_bytes_reconcile_only_after_actual_receipt=True,original_aggregate_requests=96,original_aggregate_entity_bytes=134217728,public_source_used_cap=[37,40],economic_allocated_CPU=0,conditional_economic_ceiling_CPU=7200),
 required_execution_corrections=[],full101_route_ready=False,research_pass=False,paper_ready_pass=False,
 resource=dict(pool='Original comparison1000',prior_used_CPU=234.64,inclusive_jobs=charges,actual_CPU=actual,small_reads_setup_repair_snapshot_seal_handoff_unknown_CPU=5,total_charge_CPU=total,cumulative_CPU=used,remaining_CPU=round(1000-used,2),fresh_memory_MiB=512,affinity=[0],max_RSS_KiB=165132,failed1='Actual mutable locator mismatch, retained; second job completed affected numerical and entry checks without treating mismatch as pass.',inner_CPU_not_added_twice=True,author_Martin_reported_used=344.29,author_Martin_remaining_before_subsequent_work=1655.71,old119_98_and_all_failures_preserved=True),no_Root_intermediate_message=True)
out=P/'independent-entry-acceptance.json';assert not out.exists();out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(receipt=bind(out),actual_CPU=actual,total_charge_CPU=total,cumulative_CPU=used,remaining_CPU=round(1000-used,2))))
