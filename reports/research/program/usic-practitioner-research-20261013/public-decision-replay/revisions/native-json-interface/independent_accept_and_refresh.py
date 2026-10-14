import hashlib,json,os,resource,subprocess
from pathlib import Path
from datetime import datetime,timezone
resource.setrlimit(resource.RLIMIT_CPU,(35,40));assert os.sched_getaffinity(0)=={0}
V=Path(__file__).resolve().parent;P=V.parents[1];ROOT=Path.cwd();IT=ROOT/'reports/research/iterations/usic_public_decision_replay_20261014'
def bind(p):
 p=Path(p);raw=p.read_bytes();return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(raw).hexdigest())
packet=json.loads((V/'native-resource-review-packet.json').read_text());assert bind(V/'native-resource-review-packet.json')['sha256']=='ba2cacf3c2130240d2600513caaff120d4a929c69dfe42cce4ecf5a83de858ec'
for b in packet['bindings']:assert bind(ROOT/b['path'])==b,b['path']
old=(P/'code/run_case_replay.py').read_text();new=(P/'code/run_case_replay_native_json.py').read_text()
assert old.count('ITERATION.name],')==1 and old.replace('ITERATION.name],','ITERATION.name, "--json"],')==new
assert bind(ROOT/'open_composer/research/iteration_dossier.py')['sha256']=='a5883ad05a437f3a08894d47852c07c6f7a0341775b041a952e07dcb81be8a97'
before={n:json.loads((IT/n).read_text()) for n in ['method-definition.json','candidate-manifest.json','data-feasibility.json','search-space.json']}
review=dict(schema_version=1,author='f9add224-744b-471c-b812-c43cc179fa38',reviewer='ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3',as_of_utc=datetime.now(timezone.utc).isoformat(),verdict='approve_implementation',iter_id=IT.name,research_role='market_component_method',claim_scope='conditional_cohort',scope='Same-semantics CLI JSON-output interface only; source/input/minimalreplay approvals inherited.',bindings={'implementation_manifest':bind(V/'implementation-manifest.json'),'new_runner':bind(P/'code/run_case_replay_native_json.py'),'prior_manifest':bind(P/'implementation-manifest.json'),'prior_implementation_review':bind(P/'independent-implementation-review.json'),'prior_native_diff_review':bind(P/'independent-native-entry-diff-review.json'),'actual_applied_native':bind(ROOT/'open_composer/research/iteration_dossier.py'),'actual_input_review':bind(P/'acquisition/independent-input-acceptance.json'),'metadata_refresh_entry':bind(P/'code/refresh_native_bindings.py')},required_corrections=[],findings=['Exact fulltext equality after addingonly--jsontoocvalidateargv; algorithms/guards/candidates/costs unchanged.','AppliedsourcewholeSHA exactlymatchesprioracceptedpatcha5883ad...; author17focusedtests andactualold-dossierCLIpass retained, includingearliernoCLI/MDfailurecosts.','Newmanifest inherited shared_native_code_not_yet_modified=true fromoldmanifest; it ishistoricalmetadata, notcurrentstate. Actual appliednativeSHA above controls thisreview.','Metadatarefresh changesonlyimplementationreceipt/manifestreferences andtheirdependenthashes inthisiterationfourJSON, preservesbefore-dossier. No realcasePnL orsource/market calls.'],full_implementation_approval=True,implementation_ready=True,economic_execution_admitted=False,continuation='Followingmetadatarefresh andactualcurrentnative--jsonvalidation, separateindependenteconomic60CPUdecisionmayadmitfixed16/48/96. Thisreceiptalonegrantsnoeconomicrun.',resource={'pool':'Originalcomparison1000','job_id':'public-replay-native-json-resource-review-01','actual_final_accounting_path':str((V/'independent-resource-accounting.json').relative_to(ROOT)),'single_total_in_final_resource_decision_not_perreceipt':True},no_Root_intermediate_message=True)
receipt=V/'independent-implementation-review.json';assert not receipt.exists();receipt.write_text(json.dumps(review,indent=2)+'\n')
proc=subprocess.run([str(ROOT/'.venv/bin/python'),str(P/'code/refresh_native_bindings.py')],capture_output=True,text=True)
(V/'independent-refresh-log.txt').write_text(proc.stdout+proc.stderr);assert proc.returncode==0
after={n:json.loads((IT/n).read_text()) for n in before}
for n in before:assert json.loads((V/'before-dossier'/n).read_text())==before[n]
# Independently constrain mutation exactly to the authorized reference fields.
expected=json.loads(json.dumps(before))
expected['method-definition.json']['implementation_manifest']=review['bindings']['implementation_manifest']
expected['method-definition.json']['independent_implementation_review']=bind(receipt)
assert after['method-definition.json']==expected['method-definition.json']
for c in expected['candidate-manifest.json']['candidates']:c['method_definition_sha256']=bind(IT/'method-definition.json')['sha256']
assert after['candidate-manifest.json']==expected['candidate-manifest.json']
expected['data-feasibility.json']['required_references']['implementation']=bind(receipt)
byid={r['candidate_id']:r for r in after['candidate-manifest.json']['candidates']}
for r in expected['data-feasibility.json']['candidate_authorization']['rows']:r['candidate_binding_sha256']=hashlib.sha256(json.dumps(byid[r['candidate_id']],sort_keys=True,separators=(',',':')).encode()).hexdigest()
assert after['data-feasibility.json']==expected['data-feasibility.json']
expected['search-space.json']['candidate_manifest_sha256']=bind(IT/'candidate-manifest.json')['sha256'];expected['search-space.json']['data_feasibility_sha256']=bind(IT/'data-feasibility.json')['sha256']
assert after['search-space.json']==expected['search-space.json']
out=dict(status='pass',pre_refresh_packet_bindings_verified=len(packet['bindings']),only_runner_argv_JSON_change=True,before_dossier_bytes_preserved=True,only_four_authorized_metadata_mutations=True,current_dossier_bindings=[bind(IT/n) for n in before],receipt=bind(receipt),real_market_PnL_fits=0,CPU_affinity=[0])
(V/'independent-refresh-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
