import hashlib,json,math,os,pickletools,re,resource
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU,(15,16));assert os.sched_getaffinity(0)=={0}
os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
P=Path(__file__).parent;E=P/'economic';F=P/'features'
def load(p):return json.loads(Path(p).read_text())
def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(b):
 p=Path(b['path']);assert p.stat().st_size==b['bytes'] and digest(p)==b['sha256'];return b
assert digest(P/'economic-capacity-decision.json')=='9f3c131521be4ea38f6e806a521dd92b51b1b36a9f46f7d934dfe08a17acbd99'
d=load(P/'economic-capacity-decision.json');checked=[check(b) for b in d['bindings'].values()]
receipts=[]
for b in d['economic_receipts']:
 check(b);text=Path(b['path']).read_text();cpu=sum(float(re.search(k+r' time \(seconds\): ([\d.]+)',text).group(1)) for k in ['User','System']);assert math.isclose(cpu,b['inclusive_CPU'],abs_tol=1e-9);receipts.append({'path':b['path'],'CPU':cpu})
assert math.isclose(sum(x['CPU'] for x in receipts),453.67,abs_tol=1e-9)
checkpoints=[]
for s in d['checkpoints']:
 b=s['checkpoint'];check(b);fields={};pending=None
 for op,arg,pos in pickletools.genops(Path(b['path']).read_bytes()):
  if op.name in ['SHORT_BINUNICODE','BINUNICODE'] and isinstance(arg,str) and arg in ['max_iter','max_depth','learning_rate','warm_start','_sklearn_version']:
   pending=arg
  elif pending and op.name not in ['MEMOIZE']:
   if op.name.startswith('BININT') or op.name in ['BINFLOAT','SHORT_BINUNICODE','BINUNICODE']:fields[pending]=arg
   elif op.name in ['NEWTRUE','NEWFALSE']:fields[pending]=(op.name=='NEWTRUE')
   pending=None
 assert fields['max_iter']==s['trees'] and fields['max_depth']==6 and fields['learning_rate']==.1 and fields['warm_start'] is True
 checkpoints.append({'binding':b,'safe_pickle_opcode_metadata':fields,'model_deserialized_or_predicted':False})
trials=[json.loads(x) for x in (E/'model-trial-ledger.jsonl').read_text().splitlines()]
assert len(trials)==5 and sum(t['state']=='started' for t in trials)==3 and sum(t['state']=='completed' for t in trials)==2
assert {t['candidate_id'] for t in trials}=={'HGB_IDX_CTS'}
assert not any('validation_MSE' in t or 'test_score' in t for t in trials)
assert not (E/'models/HGB-IDX-2019-depth6-lr0.1-trees350.pkl').exists()
assert not (E/'full-resource-projection.json').exists()
import numpy as np
rows=load(F/'packet-row-clock.json');labels=np.load(F/'labels.npy',mmap_mode='r')[:len(rows)];years=np.fromiter((int(r['date'][:4]) for r in rows),dtype=np.int16)
eligible=np.flatnonzero((years>=1997)&np.isfinite(labels).all(1))
ns={};details={}
for year in [2004,2009,2014,2019]:
 prior=eligible[years[eligible]<year];n=math.floor(.8*len(prior));ns[year]=n
 details[year]={'n_train':n,'n_validation':len(prior)-n,'last_train_row':int(prior[n-1]),'last_train_date':rows[int(prior[n-1])]['date'],'last_validation_row':int(prior[-1]),'last_validation_date':rows[int(prior[-1])]['date']}
assert ns[2019]==96451 and details[2019]['n_validation']==24113
assert details[2019]['last_train_date']=='2014-08-11' and details[2019]['last_validation_date']=='2018-12-31'
ratios={str(y):n/ns[2019] for y,n in ns.items()};assert ratios==d['full_refit_train_n_ratios']
eq=8*sum(ratios.values())-1;measured=d['completed150_intrinsic_calibration_CPU'];fixed=1700+700+300+500;bound=measured+measured*eq*1.25+fixed
assert math.isclose(eq,d['remaining_largestfit_equivalents'],abs_tol=1e-12) and math.isclose(bound,d['resource_projection_lower_bound_from_completed150'],abs_tol=1e-9) and bound>7006.69
ng=load(P/'extension-native-gate.json');assert ng['status']=='ok' and ng['blocked']==[] and not ng['guard_cache_or_skip'];assert len(ng['hash_calls'])==ng['actual_hash_calls']==153;assert sum(c['bytes'] for c in ng['hash_calls'])==ng['actual_hash_bytes']==10668285053
knowledge=load(P/'extension-knowledge-native-receipt.json');assert knowledge['result']['status']=='ok' and knowledge['result']['blocked']==[]
for row in knowledge['policy_batch_log']:assert row['policy_bytes_before_after_equal'] and row['all_native_card_validations_executed'] and not row['freshness_or_guard_checks_skipped']
u=resource.getrusage(resource.RUSAGE_SELF)
out={'status':'pass','checked_small_decision_bindings':checked,'economic_receipts':receipts,'economic_used_before_review':sum(x['CPU'] for x in receipts),'checkpoint_checks':checkpoints,'logical_configs_started':3,'logical_configs_completed':2,'warm_start_chains':1,'full350_absent':True,'full_projection_absent':True,'year_counts_and_cutoffs':details,'ratios':ratios,'equivalents':eq,'completed150_intrinsic_CPU':measured,'frozen_gate_bound':bound,'frozen_gate_cap':7006.69,'required_measured350_to_fit_old_formula_ignoring_other_closed_costs':(7006.69-fixed)/(1+1.25*eq),'bound_is_not_actual_full_runtime_lower_bound':True,'native_recorded_hash_calls':153,'native_recorded_hash_bytes':10668285053,'native_large_payloads_rehashed_now':False,'actual_rows_read_from_clock':len(rows),'clock_file_bytes':(F/'packet-row-clock.json').stat().st_size,'scaled787MB_file_not_rehashed_or_read':True,'source300_and71HAR_not_rehashed':True,'pickle_execution_fit_inference_strategyreturns':0,'CPU':u.ru_utime+u.ru_stime,'RSS_KiB':u.ru_maxrss,'affinity':[0]}
(P/'independent-economic-capacity-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ['status','frozen_gate_bound','required_measured350_to_fit_old_formula_ignoring_other_closed_costs','economic_used_before_review','CPU','RSS_KiB']}))
