import hashlib,json,importlib.util,os,resource
from pathlib import Path
from unittest.mock import patch
resource.setrlimit(resource.RLIMIT_CPU,(15,20));assert os.sched_getaffinity(0)=={0}
P=Path(__file__).resolve().parent;ROOT=Path.cwd();code=P.parent/'code/acquire_case_inputs.py'
def bind(p):p=Path(p);return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
m=json.loads((P/'request-manifest.json').read_text());old=json.loads((P/'request-manifest-attempt1.json').read_text())
assert bind(P/'request-manifest.json')['sha256']=='f32512978ed96228bc240672fe2098310791890f660ed3aadc707a3cc25629aa'
assert bind(P/'request-manifest-attempt1.json')['sha256']=='3738f9aca26bdad4f497ff193615d1d6d173465cc43f11bcfd0d0902d543743f'
assert all(m[k]==v for k,v in old.items() if k!='entry_bindings')
assert len(m['entry_bindings'])==11
for b in m['entry_bindings']:assert bind(ROOT/b['path'])==b
assert m['entry_bindings'][1:]==old['entry_bindings'][1:]
before=(P.parent/'code/acquire_case_inputs-attempt1.py').read_text();after=code.read_text()
newtext='    assert (ROOT / reviewed["path"]).resolve() == (\n        ROOT / manifest["scientific_plan"]["path"]\n    ).resolve()\n    assert reviewed["sha256"] == manifest["scientific_plan"]["sha256"]'
oldtext='    assert all(reviewed.get(k) == manifest["scientific_plan"][k] for k in ("path", "sha256"))'
assert after.count(newtext)==1 and after.replace(newtext,oldtext)==before
spec=importlib.util.spec_from_file_location('case_repair',code);entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
receipt=dict(accepted_for_execution=True,author=entry.AUTHOR,reviewer=entry.REVIEWER,request_manifest=bind(P/'request-manifest.json'),entry_bindings=m['entry_bindings'],allocation=m['request_limits'],economic_execution_admitted=False)
read=Path.read_text;fault=[None]
def fake(p,*args,**kwargs):
 if p==P/'independent-entry-acceptance.json':
  r=dict(receipt)
  if fault[0]=='allocation':r['allocation']={'requests':20,'entity_bytes':39845888}
  if fault[0]=='reviewer':r['reviewer']=entry.AUTHOR
  return json.dumps(r)
 content=read(p,*args,**kwargs)
 if p==ROOT/m['independent_scientific_review']['path'] and fault[0] in ['plan_SHA','plan_path']:
  s=json.loads(content);s['bindings']['plan']['sha256' if fault[0]=='plan_SHA' else 'path']='0'*64 if fault[0]=='plan_SHA' else str(ROOT/'wrong-plan.json');return json.dumps(s)
 return content
with patch.object(Path,'read_text',fake):
 path,accepted=entry.check_entry();assert accepted==m
 rejected=[]
 for f in ['allocation','reviewer','plan_SHA','plan_path']:
  fault[0]=f
  try:entry.check_entry();raise RuntimeError('incorrect acceptance '+f)
  except AssertionError:rejected.append(f)
 fault[0]=None;exists=Path.exists
 with patch.object(Path,'exists',lambda p:True if p==P/'market/request-ledger.json' else exists(p)):
  try:entry.check_entry();raise RuntimeError('consumedledgeraccepted')
  except AssertionError:rejected.append('consumed_ledger')
assert not (P/'market/request-ledger.json').exists()
out=dict(status='pass',request_manifest=bind(P/'request-manifest.json'),entry_code=bind(code),actual11bindings_match=True,only_semantic_change='Samefile resolved path plus exact SHA; all other code text exactly restored toold by inverse patch.',same_scope_limits_requests_dates=True,positive_actual_guard_with_virtual_independent_receipt=True,negative_guards_rejected=rejected,prior_collector_checks_reused=True,real_network_credentials_fits_economics=0,resource=dict(CPU=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,affinity=[0]))
(P/'independent-entry-repair-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
