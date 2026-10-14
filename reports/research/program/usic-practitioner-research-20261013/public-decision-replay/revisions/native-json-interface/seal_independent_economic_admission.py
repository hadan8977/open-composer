import hashlib,json,re
from pathlib import Path
from datetime import datetime,timezone
V=Path(__file__).resolve().parent;P=V.parents[1];ROOT=Path.cwd();IT=ROOT/'reports/research/iterations/usic_public_decision_replay_20261014'
def bind(p):
 p=Path(p);return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
native=json.loads((V/'independent-current-native-validation.json').read_text());assert native['status']=='ok' and native['blocked']==[]
assert not (P/'replay-result').exists() and not (P/'independent-economic-resource-decision.json').exists()
refresh=json.loads((V/'independent-refresh-verification.json').read_text());assert refresh['status']=='pass'
for b in refresh['current_dossier_bindings']:assert bind(ROOT/b['path'])==b
assert bind(ROOT/'open_composer/research/iteration_dossier.py')['sha256']=='a5883ad05a437f3a08894d47852c07c6f7a0341775b041a952e07dcb81be8a97'
costs=[]
for name in ['independent-refresh-resource.txt','independent-current-native-resource.txt']:
 text=(V/name).read_text();cpu=round(sum(float(re.search(k+r' time \(seconds\): ([\d.]+)',text)[1]) for k in ['User','System']),2);costs.append(dict(receipt=bind(V/name),CPU=cpu))
actual=round(sum(x['CPU'] for x in costs),2);assert actual==7.04
charge=round(actual+5,2);used=round(316.39+charge,2)
account=dict(job_id='public-replay-native-json-resource-review-01',pool='OriginalUSICcomparison1000',prior_used_CPU=316.39,inclusive_jobs=costs,actual_CPU=actual,small_reads_setup_binding_final_seal_handoff_unknown_CPU=5,total_charge_CPU=charge,cumulative_CPU=used,remaining_CPU=round(1000-used,2),fresh_memory_MiB=400,CPU_affinity=[0],max_RSS_KiB=150840,failed_jobs=0,author550_49_and_economic0_preserved=True,HFpool_not_used=True,no_inner_doublecharge=True)
(V/'independent-resource-accounting.json').write_text(json.dumps(account,indent=2)+'\n')
files=[P/'root-scope-decision.json',P/'revisions/v2/scientific-plan.json',P/'revisions/v2/independent-plan-review.json',P/'revisions/v2/source-figure-case-timelines.json',V/'implementation-manifest.json',V/'independent-implementation-review.json',P/'acquisition/actual-input-manifest.json',P/'acquisition/independent-input-acceptance.json',P/'acquisition/case-admissions.json',P/'acquisition/components/component-result.json',P/'acquisition/components/entity-registry.json',P/'acquisition/components/actions.json',P/'acquisition/components/daily-context.json',P/'code/run_case_replay_native_json.py',P/'code/case_replay.py',P/'code/build_case_inputs.py',ROOT/'open_composer/market_sessions.py',ROOT/'open_composer/research/iteration_dossier.py',ROOT/'open_composer/research/market_component.py',P/'independent-native-entry-diff-review.json',V/'independent-current-native-validation.json',V/'independent-refresh-verification.json',V/'independent-resource-accounting.json']
summary=json.loads((P/'acquisition/components/component-result.json').read_text())
files += [ROOT/r['binding']['path'] for r in summary['cases']]
for name in ['method-definition.json','candidate-manifest.json','data-feasibility.json','search-space.json','data-contract.json','features-contract.json','labels-contract.json','validation-contract.json','costs-contract.json','benchmarks-contract.json','external-brief.json','direction-review.json','evaluation-standard-freeze.json','source-query-manifest.json','knowledge-baseline.json','search-space-preparation.json','external-brief.md','decision-record.md','hypotheses.md','search-space.md','cost-table.md']:files.append(IT/name)
files=list(dict.fromkeys(files));bindings=[bind(p) for p in files]
grant=dict(schema_version=1,task_id='USIC-PUBLIC-DECISION-REPLAY',iter_id=IT.name,author='f9add224-744b-471c-b812-c43cc179fa38',decision_owner='ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3',reviewer='ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3',as_of_utc=datetime.now(timezone.utc).isoformat(),verdict='approve_bounded_case_replay',economic_execution_admitted=True,allocation=dict(economic_coreseconds=60,CPU=1,memory_MiB=400),bindings=bindings,
 reservation_id='USIC-PUBLIC-DECISION-REPLAY-fixed16-complete-01',authority=bind(P/'root-scope-decision.json'),entrypoint=bind(P/'code/run_case_replay_native_json.py'),
 current_gates=dict(scientific_v2='approve_deep_plan',actual_input='accepted_conditional_components_with_arm_specific_NA',implementation='approve_implementation_new_JSONrunner',current_native=native,metadata_only_refresh_verified=True,actual_shared_native_matches_independently_accepted_patch=True),
 complete_scope=dict(price_trajectories=16,transaction_cost_cells=48,mandatory_borrow_stress_cells=96,candidates=['PDL','PREVH'],delays_minutes=[1,5],case_dates=['2021-02-22','2022-01-20','2025-02-20','2025-03-26'],all_invalid_missing_nofill_states_retained=True,real_fills_or_private_performance_claim=False),
 budget=dict(original_conditional_cap_CPU=7200,prior_economic_used_CPU=0,prior_economic_allocated_CPU=0,new_single_envelope_CPU=60,unallocated_original_CPU=7140,shared_author_execution_failures_nativechild_and_seal_included=True,no_second60_per_attempt=True,independent_acceptance_review_uses_originalcomparison_not_secondexecutionpool=True,new_market_requests=0,new_source_requests=0,new_cloud_paid_USD=0,new_orders=0),
 launch_conditions=[
 'Fresh run_capped400M admission withownerreserve, tasksetCPU0, OMP/OPENBLAS/MKLthreads1. Neveralterglobalcgroup oruseHFresources.',
 'Use an outer /usr/bin/time -v receipt encompassinglauncher+currentnativechild+replay. UnderCPU0, impose timeout--signal=TERM --kill-after=1s 50s aroundtheactualPythonrunner. Reserve remaining9seconds forlauncher/admission/seal/unknown; thisexternalbound isneeded becauseinternalRLIMIT isestablishedafternativechild. Do not relyonlyoninnerCPUrecord.',
 'Onecomplete60CPUenvelope includesfailedlaunches,unknownandallactualchildcosts. Chargeouterreceipt once, notagaininsideeachcase. Checkremainingenvelope beforesame-scopeordinaryrepair; nofull60automaticretry oroverwritingconsumedreplay-result.',
 'Wrappermustreadthisactualgrant/checkallcurrentbindings/revalidateactualcurrentnative--json beforedependentcasecalculation. Newnativefailure =>noPnL; preservefailedcost/receipt, ordinaryrepaironlywithinremainingauthorizedscope.',
 'Afteractualcompletion preserve16outputs plus48/96includingNAs andsource/executionlimits; sendcompleteactualresult+resourcepackage forindependentresultacceptance. No OOS,paper,broker,sourcequery ortraining authority.'
 ],
 suggested_launcher='scripts/run_capped.sh --mem 400M --wait-min 0 -- taskset -c 0 timeout --signal=TERM --kill-after=1s 50s env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python reports/research/program/usic-practitioner-research-20261013/public-decision-replay/code/run_case_replay_native_json.py',
 native_warning_interpretation='lightweight_single_mechanism_exemption_used isretained forconditionalcomponent; no source/hash/independentreview guard waived.',
 historical_packet_limit='Pre-refreshpacket immutablehistory isnot usedaslivegrantbinding. Allgrantbindings above computed afteractualfourJSONrefresh/currentnativepass. Originaldossierbytes remain before-dossier.',
 review_resource_accounting=bind(V/'independent-resource-accounting.json'),research_pass=False,paper_ready_pass=False,net_return=None,actual_replay_started_by_reviewer=False,no_Root_intermediate_message=True)
(P/'independent-economic-resource-decision.json').write_text(json.dumps(grant,indent=2)+'\n')
# Final immediate binding consistency, without invoking replay or its admission function.
for b in grant['bindings']:assert bind(ROOT/b['path'])==b
print(json.dumps(dict(implementation_review=bind(V/'independent-implementation-review.json'),resource_grant=bind(P/'independent-economic-resource-decision.json'),current_bindings=len(bindings),comparison_charge=charge,comparison_cumulative=used,comparison_remaining=round(1000-used,2))))
