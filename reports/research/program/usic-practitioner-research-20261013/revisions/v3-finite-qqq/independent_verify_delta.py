import hashlib,importlib.util,json,os,resource,tempfile
from pathlib import Path
from unittest.mock import patch
resource.setrlimit(resource.RLIMIT_CPU,(10,12))
assert os.sched_getaffinity(0)=={0}
P=Path(__file__).parent;ROOT=Path.cwd();out={}
def load(p):return json.loads(Path(p).read_text())
def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert h(P/'affected-review-packet.json')=='773b89bd187e85b3718ee756e8d0950627cc2de5722e5012756d3b0f45fcc3c8'
assert h(P/'implementation-entry-manifest.json')=='d59da2a9af62563808769b91ff6578d8ccbdb32b686c01ee3732d52a271ce719'
entry=load(P/'implementation-entry-manifest.json');delta=load(P/'affected-scientific-delta.json');checked={}
for b in entry['entry_bindings']+[v for v in delta.values() if isinstance(v,dict) and 'path' in v and 'sha256' in v]:
 assert h(b['path'])==b['sha256'],b['path'];checked[b['path']]=b['sha256']
old=load(delta['baseline_plan']['path']);new=load(delta['plan']['path']);oc=load(delta['baseline_contract']['path']);nc=load(delta['contract']['path'])
def diffs(a,b,path=''):
 if isinstance(a,dict) and isinstance(b,dict):
  result=[]
  for k in sorted(set(a)|set(b)):
   if k not in a or k not in b:result.append(path+'/'+k)
   else:result+=diffs(a[k],b[k],path+'/'+k)
  return result
 return [] if a==b else [path]
plan_diff=diffs(old,new);contract_diff=diffs(oc,nc);assert set(contract_diff)=={'/features_and_pool/population_scope_delta','/version'}
assert old['candidates']==new['candidates'] if 'candidates' in old else True
out.update(checked_small_bindings=checked,plan_changed_paths=plan_diff,contract_changed_paths=contract_diff)
code=ROOT/'reports/research/program/usic-practitioner-research-20261013/code/acquire_finite_cohort_bridge.py'
spec=importlib.util.spec_from_file_location('reviewed_entry',code);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
items=mod.materialize_requests(['AAPL','MSFT'])
assert len(items)==45 and sum(i['max_pages'] for i in items)==48
assert sum(i['max_pages']*i['per_page_byte_cap'] for i in items)==65011712
minute=items[5:];assert len(minute)==40 and minute[0]['id']=='raw_RTH_2024-01-02' and minute[-1]['id']=='raw_RTH_2024-02-28'
assert all(x['params']['start'].endswith('T14:30:00Z') and x['params']['end'].endswith('T20:59:59Z') for x in minute)
assert all(x['params']['adjustment']=='raw' and x['params']['asof']=='-' for x in minute)
out['offline_materialization']={'objects':45,'pages':48,'bytes_reserved':65011712,'minute_days':40,'first':minute[0]['id'],'last':minute[-1]['id'],'real_network_calls':0,'credentials_initialized':False}
# Exercise only HTTP-status branching with inert client; no external requests or actual source data.
class FakeClient:
 def __init__(self,*a,**kw):pass
 def __enter__(self):return self
 def __exit__(self,*a):pass
cases=[]
for status in [500,302,403,404,200]:
 with tempfile.TemporaryDirectory(dir=P) as t:
  mod.OUT=Path(t);(mod.OUT/'input-scope.json').write_text((P/'input-scope.json').read_text());calls=[]
  def fake_get(client,url,params,cap):
   calls.append(url);return b'',{'http_status':status,'entity_complete':True,'headers':{},'stop_reason':None}
  with patch('httpx.Client',FakeClient),patch.object(mod.INTAKE,'bounded_get',fake_get):mod.source_phase()
  cases.append({'first_status':status,'synthetic_representation_calls':len(calls),'allowed_calls_for_this_response':2 if status in [200,404] else 1,'real_HTTP_calls':0})
out['source_status_branch_cases']=cases
u=resource.getrusage(resource.RUSAGE_SELF);out['resource']={'CPU':u.ru_utime+u.ru_stime,'RSS_KiB':u.ru_maxrss,'affinity':[0]}
(P/'independent-delta-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'plan_diff':plan_diff,'contract_diff':contract_diff,'status_cases':cases,'resource':out['resource']}))
