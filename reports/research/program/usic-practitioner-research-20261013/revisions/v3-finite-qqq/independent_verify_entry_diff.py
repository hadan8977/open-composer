import hashlib,importlib.util,json,os,resource,tempfile
from pathlib import Path
from unittest.mock import patch
resource.setrlimit(resource.RLIMIT_CPU,(10,12));assert os.sched_getaffinity(0)=={0}
P=Path(__file__).parent;ROOT=Path.cwd()
def load(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
d=load(P/'r1-entry-diff.json');assert digest(P/'r1-entry-diff.json')=='a6014b0fc435ce023cc841ed98954702af1b41e1b91565f026982e834ad1380b'
checks=[]
for b in d.values():
 if isinstance(b,dict) and 'path' in b and 'sha256' in b:
  assert digest(b['path'])==b['sha256'];checks.append(b)
e=load(P/'implementation-entry-manifest.json');assert len(e['entry_bindings'])==9
old=load(P/'entry-r1-before/implementation-entry-manifest.json')
changed=[]
for a,b in zip(old['entry_bindings'],e['entry_bindings'],strict=True):
 assert a['path']==b['path']
 if a!=b:changed.append(b['path'])
 assert digest(b['path'])==b['sha256']
assert changed==[d['code']['path']]
spec=importlib.util.spec_from_file_location('reviewed_entry_diff',ROOT/d['code']['path']);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class FakeClient:
 def __init__(self,*a,**kw):pass
 def __enter__(self):return self
 def __exit__(self,*a):pass
cases=[]
for status,complete,throws,expected in [(500,True,False,1),(302,True,False,1),(401,True,False,1),(403,True,False,1),(429,True,False,1),(404,True,False,2),(200,True,False,2),(200,False,False,1),(200,True,True,1)]:
 with tempfile.TemporaryDirectory(dir=P) as temp:
  mod.OUT=Path(temp);(mod.OUT/'input-scope.json').write_bytes((P/'input-scope.json').read_bytes());calls=[]
  def fake_get(client,url,params,cap):
   calls.append(url)
   if throws:raise RuntimeError('synthetic_transport_error')
   return b'',{'http_status':status,'entity_complete':complete,'headers':{},'stop_reason':None}
  with patch('httpx.Client',FakeClient),patch.object(mod.INTAKE,'bounded_get',fake_get):mod.source_phase()
  assert len(calls)==expected
  cases.append({'status':status,'complete':complete,'transport_exception':throws,'synthetic_calls':len(calls),'real_HTTP':0})
# Success stops after one representation; stop fixture before identity/source reads.
class StopAfterFreeze(Exception):pass
with tempfile.TemporaryDirectory(dir=P) as temp:
 mod.OUT=Path(temp);(mod.OUT/'input-scope.json').write_bytes((P/'input-scope.json').read_bytes());calls=[];original_save=mod.save
 def fake_success(client,url,params,cap):
  calls.append(url);return b'<mock/>',{'http_status':200,'entity_complete':True,'headers':{},'stop_reason':None}
 def bounded_save(path,data):
  if path.name=='frozen-historical-roster.json':raise StopAfterFreeze()
  original_save(path,data)
 with patch('httpx.Client',FakeClient),patch.object(mod.INTAKE,'bounded_get',fake_success),patch.object(mod,'parse_roster',lambda b:([{'synthetic':True}],[])),patch.object(mod,'save',bounded_save):
  try:mod.source_phase()
  except StopAfterFreeze:pass
 assert len(calls)==1;cases.append({'status':200,'parse_success':True,'synthetic_calls':1,'real_HTTP':0,'stopped_before_FTD_read':True})
# Interface consumption only; prevent guard from altering this review's resource limits.
guards=[]
with tempfile.TemporaryDirectory(dir=P) as temp:
 mod.OUT=Path(temp);prior=mod.OUT/'independent-delta-review.json';prior.write_bytes((P/'independent-delta-review.json').read_bytes())
 side={'reviewer':'independent_fixture_reviewer','verdict':'accept_same_semantics_entry_diff','prior_review':mod.bind(prior),'entry_bindings_accepted_for_execution':True,'entry_bindings':e['entry_bindings']}
 def run_guard(value):
  (mod.OUT/'independent-entry-diff-review.json').write_text(json.dumps(value))
  with patch.object(mod.resource,'setrlimit',lambda *a:None):mod.guard()
 run_guard(side);guards.append('valid prior-science plus independently-bound sidecar accepted')
 for label,edit in [('same_author',lambda x:x.update(reviewer=mod.AUTHOR)),('prior_hash_mismatch',lambda x:x['prior_review'].update(sha256='wrong')),('execution_flag_false',lambda x:x.update(entry_bindings_accepted_for_execution=False)),('changed_entry_hash',lambda x:x['entry_bindings'][0].update(sha256='wrong'))]:
  bad=json.loads(json.dumps(side));edit(bad)
  try:run_guard(bad)
  except AssertionError:guards.append(label+' rejected')
  else:raise AssertionError(label+' accepted')
u=resource.getrusage(resource.RUSAGE_SELF)
out={'status':'pass','changed_entry_binding_only':changed,'exact_current_entry_bindings':e['entry_bindings'],'source_transition_cases':cases,'receipt_guard_cases':guards,'real_network_source_market_requests':0,'credentials_initialized':False,'actual_FTD_or_market_rows_read':0,'model_or_economic_calculations':0,'CPU':u.ru_utime+u.ru_stime,'RSS_KiB':u.ru_maxrss,'affinity':[0]}
(P/'independent-entry-diff-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'status':'pass','transition_cases':len(cases),'guard_cases':len(guards),'CPU':out['CPU'],'RSS_KiB':out['RSS_KiB']}))
