import hashlib,importlib.util,json,os,resource,tempfile,types
from pathlib import Path
from unittest.mock import patch
resource.setrlimit(resource.RLIMIT_CPU,(10,12));assert os.sched_getaffinity(0)=={0}
P=Path(__file__).parent;ROOT=Path.cwd()
load=lambda p:json.loads(Path(p).read_text())
digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert digest(P/'transport-repair-entry.json')=='33b06f484842dc74f5e72ee2bbe279ec95b8d51952b1006e5f1af4262c6c7643'
e=load(P/'transport-repair-entry.json');assert len(e['repair_entry_bindings'])==7
for b in e['repair_entry_bindings']:assert digest(b['path'])==b['sha256']
code=ROOT/e['repair_entry_bindings'][0]['path'];spec=importlib.util.spec_from_file_location('repair_entry_review',code);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original_parent=digest(P/'source-request-ledger.json');cases=[]
for label,status,complete,missing,throws in [('missing_config',None,None,True,False),('denied',403,True,False,False),('redirect',302,True,False,False),('error',500,True,False,False),('incomplete',200,False,False,False),('transport',None,None,False,True),('retained200',200,True,False,False)]:
 with tempfile.TemporaryDirectory(dir=P) as td:
  m.OUT=Path(td)
  for name in ['source-request-ledger.json','independent-source-access-and-method-review.json','input-scope.json']:(m.OUT/name).write_bytes((P/name).read_bytes())
  calls=[];closed=[];configuration_calls=[]
  class StubClient:
   def __init__(self):
    if missing:raise RuntimeError('synthetic_missing_configuration')
    self._client=object()
   def get(self,*a,**kw):raise AssertionError('forbidden_retry_helper')
   def close(self):closed.append(True)
  def no_configuration_read(**kwargs):configuration_calls.append(str(kwargs['dotenv_path']))
  sec=types.SimpleNamespace(load_dotenv=no_configuration_read,SecClient=StubClient)
  def inert_get(client,url,params,cap):
   ledger=load(m.OUT/'source-repair-ledger.json');assert ledger['actual_calls']==1 and ledger['unknown_reserved_bytes']==2097152
   calls.append((url,cap));assert url==e['source_url'] and cap==2097152 and params=={}
   if throws:raise RuntimeError('synthetic_transport')
   return b'<synthetic/>',{'http_status':status,'entity_complete':complete,'headers':{},'stop_reason':None}
  with patch.object(m,'load_module',lambda *a:sec),patch.object(m.ACQ.INTAKE,'bounded_get',inert_get):m.collect_one()
  l=load(m.OUT/'source-repair-ledger.json');assert l['actual_calls']==len(calls)==(0 if missing else 1)
  assert len(closed)==(0 if missing else 1)
  assert l['source_units_after']==(36 if missing else 37)
  # Never decode actual retained source or FTD; exercise offline failure with inert parser.
  def parse_failure(body):raise m.ACQ.ET.ParseError('synthetic_schema_difference')
  with patch.object(m.ACQ,'parse_roster',parse_failure),patch.object(m.ACQ.INTAKE,'bounded_get',lambda *a:(_ for _ in ()).throw(AssertionError('offline_download'))):m.parse_retained()
  assert (m.OUT/'source-repair-result.json').exists()
  try:
   with patch.object(m,'load_module',lambda *a:sec):m.collect_one()
  except AssertionError:pass
  else:raise AssertionError('consumed_slot_reused')
  cases.append({'case':label,'synthetic_calls':len(calls),'source_units_after':l['source_units_after'],'status':l['status'],'client_closed':bool(closed),'configuration_loader_mocked':True,'implicit_rerun_rejected':True})
guards=[]
with tempfile.TemporaryDirectory(dir=P) as td:
 m.OUT=Path(td)
 for name in ['source-request-ledger.json','independent-source-access-and-method-review.json']:(m.OUT/name).write_bytes((P/name).read_bytes())
 good={'verdict':'accept_same_source_transport_entry_diff','reviewer':'independent_fixture','prior_method_review':m.bind(m.OUT/'independent-source-access-and-method-review.json'),'repair_entry_bindings':e['repair_entry_bindings']}
 def call_guard(payload):
  (m.OUT/'independent-transport-entry-diff-review.json').write_text(json.dumps(payload))
  with patch.object(m.resource,'setrlimit',lambda *a:None):m.guard()
 call_guard(good);guards.append('valid sidecar and original R1 guards accepted')
 for label,edit in [('self_review',lambda x:x.update(reviewer=m.ACQ.AUTHOR)),('method_hash_mismatch',lambda x:x['prior_method_review'].update(sha256='wrong')),('entry_hash_mismatch',lambda x:x['repair_entry_bindings'][0].update(sha256='wrong'))]:
  bad=json.loads(json.dumps(good));edit(bad)
  try:call_guard(bad)
  except AssertionError:guards.append(label+' rejected')
  else:raise AssertionError(label+' accepted')
assert digest(P/'source-request-ledger.json')==original_parent
u=resource.getrusage(resource.RUSAGE_SELF)
out={'status':'pass','repair_entry_bindings':e['repair_entry_bindings'],'cases':cases,'guards':guards,'parent403_unchanged':True,'real_HTTP':0,'real_configuration_reads':0,'FTD_or_market_rows':0,'fits_PnL':0,'CPU':u.ru_utime+u.ru_stime,'RSS_KiB':u.ru_maxrss,'affinity':[0]}
(P/'independent-transport-entry-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ['status','CPU','RSS_KiB','real_HTTP','real_configuration_reads']}))
