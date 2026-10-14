import hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
P=Path(__file__).resolve().parent;V=P.parent
def bind(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
verification=json.loads((P/'independent-verification.json').read_text());assert verification['status']=='pass'
profile=(P/'independent-resource.txt').read_text()
actual=round(sum(float(re.search(k+r' time \(seconds\): ([\d.]+)',profile)[1]) for k in ['User','System']),2)
assert actual==6.11
unknown=5.;charge=round(actual+unknown,2);used=round(223.53+charge,2)
bindings={name:bind(path) for name,path in {
 'author_manifest':P/'manifest.json','root_pool_authority':V/'root-task-pool-continuation.json',
 'actual_result':P/'result.json','summary':P/'summary.json','config':P/'config.json',
 'full101_identity_candidates':V/'full-cohort-route/identity-candidates.json',
 'prior25_identity_candidates':V/'identity-candidates.json',
 'prior_actual_input_acceptance':V/'actual-input-acceptance.json',
 'prior_frozen_contract':V/'state-and-ledger-contract.json',
 'independent_verification':P/'independent-verification.json',
 'independent_check_code':P/'independent_verify_completed_diagnostic.py',
 'inclusive_resource':P/'independent-resource.txt','author_accounting':P/'accounting.json',
 'author_summary_resource':P/'summary-resource.txt',
}.items()}
assert bindings['author_manifest']['sha256']=='481d7c00fa145581e072a4aa2786e6ee0061c52e7c907562443294b3318a5a1d'
receipt=dict(schema_version=1,task_id='USIC-PRACTITIONER-RESEARCH',author='f9add224-744b-471c-b812-c43cc179fa38',reviewer='ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3',as_of_utc=datetime.now(timezone.utc).isoformat(),verdict='accept_completed_bounded_input_diagnostic',scope='Affected completed existing-input25x40 price/clock diagnostics and same101-issue dated identity extension; not a new plan review or economic allocation',bindings=bindings,required_corrections=[],
 actual_accepted={
 'all_manifest_bindings':1012,'checkpoint_cells':1000,'raw_minute_rows':360680,'invalid_rows':0,'missing_minutes':29320,'complete_sessions':395,'numeric_price_gate_cells':554,'complete_parents':23455,'missing_parents':2545,'EMA_PB_price_geometry':2111,'baseline_activatable_EMA_PB_before11':2043,'BREAK_price_geometry':580,
 'meaning':'Price geometry and numeric source-window features only. Event counts are correlated repeated conditional observations, not independent trades, executed orders, successful opportunities or PnL.',
 'source_identity':'101 original historical NPORT issues matched to actual dated candidate symbols using exactly two DecemberFTD files and four columns. All101 latest same-CUSIP dated points independently checked; first25 common fields exactly unchanged. No current mapping, new roster or outcome-based replacement. Dated FTD points do not certify active intervals or security type through2024–25.',
 'split_basis':'Necessary accepted action evidence checked: no known effective forward/reverse split crosses any fetched25-symbol prefix through2024-02-28; prior10 raw high is valid for this bounded diagnostic condition. This does not certify all future/raw-cache bases or completeness of the action feed.',
 'hygiene_and_clock':'Original default asof-prefix hygiene retained; observed prior-close-only Decimal60 ADR/ADV/momentum/EMA/lag5 checked. Complete1/5/15 grids and cutoff activation use actual parents, no padding; nearest support ties EMA21 thenEMA9. AVWAP unknown with legal EMA fallback stays explicit.',
 'adverse_cases':'SGEN40 empty sessions retain15600 missing minute slots and40 missing feature cells; its229 cash right and inactive evidence remain in prior receipt. ILMN→GRAL child rights, ASML action identity quarantine, and SNPS/PANW recipient/acquirer roles are inherited, not removed or reclassified.'},
 independent_coverage={
 'all1000_case_file_hash_and_count_reconciliation':True,'full1000_numeric_replay':False,
 'selected_days':verification['selected_days'],'selected_symbol_days':75,
 'Decimal60_full_feature_cases':len(verification['independent_Decimal60_numeric_cases']),
 'missing_or_insufficient_prefix_cases':75-len(verification['independent_Decimal60_numeric_cases']),
 'selected_raw_minute_rows':26931,'complete_parent_numeric_and_pointer_recomputations':1764,
 'all101_actual_four_column_mapping_checked':True,'old47_entities_rehashed':False,'old69MB_index_rebuilt_or_accepted':False,
 'preserved_receipts':'Prior47 source/entity/action/NPORT acceptance reused. New manifest has no overwrite of the original partial or failure evidence. This review does not represent sampled numeric checks as full1000 independent replay.'},
 source_fit_and_full_route_judgment={
 'verdict':'continue_bounded_same101_route_evidence; withhold_economic_allocation',
 'research_value':'The data now supports actual source-fit and execution-clock feasibility assessment, beyond three illustrative cases. Existing local evidence can determine whether the fixed eight definitions and feedback/reentry comparison have enough common, causal opportunities and a coherent held-asset path in the finite historical growth-stock adaptation.',
 'source_distance':'All960 available ADR20 observations are1.1470124%–4.7227817%, below the source usual5% preference. This is materially weaker fidelity to Martin high-ADR/small-cap/theme opportunities; it limits external validity, not the fixed v3 eligibility rule. Do not introduce an ADR5% filter, replace low-ADR names or claim replication of private performance.',
 'ordered_data_value':'395/1000 complete session cells and23455/26000 complete selected parent intervals identify useful real data and specific gaps. Among960 non-SGEN cells,13720 minutes remain absent; some otherwise incomplete days still contain valid parent events. Do not make incomplete-session==all-components-invalid, or convert an absent execution minute to a fabricated fill/zero return.',
 'not_yet_demonstrated':'Geometries are not full101-ranked opportunities, complete eight-definition workload, fills, terminal-aware NAV or evidence of net economic contribution. The diagnostic does not yet establish that spending the7200 economic ceiling has positive research value.',
 'most_informative_next_action':[
  'Same owner continue bounded local cache/basis/seed route inspection in the released original Martin2000 remainder. Freeze a same101 issue-to-episode and raw/action evidence matrix; retain unresolved and inactive slots. Keep raw basis, action effectiveness, current-version metadata and historical eligibility claims distinct.',
  'Show actual2024–25 ordered execution coverage and decision-prefix coverage per same frozen issue, including inherited rights and child assets. Quantify which missing intervals affect submitted orders, marks or held rights under unchanged rules; do not cherry-pick complete days or drop adverse terminals.',
  'Before any new market call, deliver exact same101/raw/action/benchmark request manifest only for evidenced gaps, with worst-case pagination/bytes under the consolidated remaining36 requests/90322387B. Demonstrate why each request closes a necessary route gap instead of spending unused quota. Same-scope entry acceptance can proceed directly with this reviewer.',
  'For full execution, demonstrate actual eligible/rank population, legally seeded features, causal opportunity/state/rights handling and feasible8/120/102 workload, then independent implementation/input/native/resource gates. If first-episode EMA seed or population semantics must change, declare that precise scientific delta for independent review; do not silently relabel a fetched-window seed.',
  'If the same finite adaptation cannot answer a worthwhile controller/reentry/exit question within original aggregate resources, make that specific allocation decision with evidence. Do not infer whole-market infeasibility from missingfirstvisible, Rf, ETB, AVWAP or these25 cases.'
 ],
 'scope_decision_conditions':'Changed population/seed/scientific meaning, new source family, paid feed/device or aggregate resource excess requires the applicable material decision. Ordinary local preparation and same-source same-scope repairs do not require Root per-step return.'},
 permissions={
 'root_total_pool_continuation_applied':True,'new_market_requests_admitted_here':0,'new_economic_CPU_allocated_here':0,
 'existing_total_requests':96,'actual_used_requests':60,'remaining_requests':36,'remaining_bytes':90322387,
 'market_reallocation_is_prospective':True,'original_public_source_used_cap':[37,40],
 'economic_used_allocated':[0,0],'original_conditional_economic_ceiling':7200,
 'complete_input_ready':False,'full_implementation_ready':False,'native_ready':False,
 'source_component_input_accepted':True,'not_blocked_by_historical_firstvisible_for_current_version_price_components':True},
 resource=dict(pool='Original shared comparison1000; Root delegated remainder776.47, old40 only historical',review_process_soft_hard_CPU=[75,80],actual_inclusive_CPU=actual,small_read_setup_seal_handoff_conservative_CPU=unknown,total_charge_CPU=charge,prior_comparison_CPU=223.53,comparison_cumulative_CPU=used,comparison_remaining_CPU=round(1000-used,2),max_RSS_KiB=282480,fresh_run_capped_MiB=512,CPU_affinity=[0],exit=0,author_Martin_cumulative_reported_and_profiles_checked=314.21,author_remaining_before_later_work=1685.79,old119_98_already_in_author_cumulative=True,old_failures_unknown_and_other_reviews_retained_once=True,inner5_105666_CPU_is_inside_outer6_11_not_added=True,author_ledger_not_modified=True,HF_pool_not_used=True),
 new_downloads=0,new_models=0,new_real_fits=0,new_strategy_returns_or_orders=0,research_pass=False,paper_ready_pass=False,no_Root_intermediate_message=True)
out=P/'independent-input-acceptance.json';assert not out.exists();out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'receipt':bind(out),'actual_CPU':actual,'unknown_CPU':unknown,'total_charge':charge,'comparison_cumulative':used,'comparison_remaining':round(1000-used,2)}))
