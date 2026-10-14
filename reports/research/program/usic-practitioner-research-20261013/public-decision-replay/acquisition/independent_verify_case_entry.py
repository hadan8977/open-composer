import json,hashlib,importlib.util,os,resource,tempfile
from pathlib import Path
from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch
resource.setrlimit(resource.RLIMIT_CPU,(35,40));assert os.sched_getaffinity(0)=={0}
from open_composer.market_sessions import us_equity_session_dates,us_equity_session_close,previous_us_equity_session
P=Path(__file__).resolve().parent;BASE=P.parent;ROOT=Path.cwd();checked=[]
def bind(p):p=Path(p);raw=p.read_bytes();return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(raw).hexdigest())
def verify(b):
 assert bind(ROOT/b['path'])==b,b['path'];checked.append(b)
m=json.loads((P/'request-manifest.json').read_text())
for b in m['entry_bindings']:verify(b)
for b in m['prior_request_ledgers']:verify(b)
assert len(m['entry_bindings'])==11 and len(m['requests'])==7
assert sum(r['max_pages'] for r in m['requests'])==19
assert sum(r['max_pages']*r['per_page_byte_cap'] for r in m['requests'])==39845888
ny=ZoneInfo('America/New_York');clocks=[]
for c in m['case_clocks']:
 day=date.fromisoformat(c['date_candidate']);start=date.fromisoformat(c['prefix_start_session']);prior=previous_us_equity_session(day)
 sessions=us_equity_session_dates(start,prior);assert len(sessions)==37 and str(prior)==c['prior_session']
 begin=datetime.combine(start,time(9,30),ny).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
 end=(datetime.combine(day,us_equity_session_close(day),ny)-timedelta(seconds=1)).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
 assert begin==c['start_UTC'] and end==c['end_inclusive_UTC']
 r=next(r for r in m['requests'] if r['id']==c['case_id'].split('_')[1]+'_minute_raw')
 assert r['params']['start']==begin and r['params']['end']==end and r['params']['adjustment']=='raw'
 clocks.append(dict(case=c['case_id'],prior=str(prior),prefix_sessions=37,start=begin,end=end,early_close_prefix=[str(d) for d in sessions if us_equity_session_close(d)==time(13)]))
ledgers=[json.loads((ROOT/b['path']).read_text()) for b in m['prior_request_ledgers']]
assert sum(l['requests_used'] for l in ledgers)==63 and sum(l['complete_entity_bytes']+l['incomplete_response_reserved_bytes'] for l in ledgers)==44065545
reuse=[]
for r in m['reuse_existing_entities']:
 l=next(l for l,b in zip(ledgers,m['prior_request_ledgers']) if b==r['ledger'])
 a=next(a for a in l['attempts'] if a.get('entity')==r['entity']);assert a['params']==r['params'] and a['entity_complete']
 # Reuse inherited entity hash acceptance; inspect symbol presence only, no returns.
 data=json.loads((ROOT/r['entity']['path']).read_bytes())
 if 'bars' in data:present={s:len(rows) for s,rows in data['bars'].items() if s in ['TSLA','SMCI']}
 else:present={'action_types':sorted(data.get('corporate_actions',{}))}
 reuse.append(dict(entity=r['entity'],selected_presence=present))
assert any(x['selected_presence'].get('TSLA',0)>0 for x in reuse) and any(x['selected_presence'].get('SMCI',0)>0 for x in reuse)
spec=importlib.util.spec_from_file_location('case_entry',BASE/'code/acquire_case_inputs.py');entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
proposed=dict(accepted_for_execution=True,author=m['author'],reviewer=entry.REVIEWER,allocation=m['request_limits'],economic_execution_admitted=False,request_manifest=bind(P/'request-manifest.json'),entry_bindings=m['entry_bindings'])
read=Path.read_text
def fake(p,*args,**kwargs):
 if p==P/'independent-entry-acceptance.json':return json.dumps(proposed)
 return read(p,*args,**kwargs)
failure=None
with patch.object(Path,'read_text',fake):
 try:entry.check_entry()
 except AssertionError:
  science=json.loads((ROOT/m['independent_scientific_review']['path']).read_text());reviewed=science['bindings']['plan']
  assert Path(reviewed['path']).resolve()==(ROOT/m['scientific_plan']['path']).resolve()
  assert reviewed['sha256']==m['scientific_plan']['sha256'] and reviewed['path']!=m['scientific_plan']['path']
  failure=dict(reason='literal_absolute_relative_scientific_plan_path_mismatch',reviewed=reviewed,manifest=m['scientific_plan'])
# Continue all non-dependent collector checks using synthetic responses, not a permission grant.
inert=[]
for typ,want in [('normal',7),('pagination',19),('403',1),('incomplete',1)]:
 with tempfile.TemporaryDirectory(prefix='inert-',dir=P) as temp:
  counter=[0]
  def response(client,path,params,cap):
   counter[0]+=1
   return json.dumps({'bars':{},'next_page_token':str(counter[0]) if typ=='pagination' else None}).encode(),dict(http_status=403 if typ=='403' else 200,entity_complete=typ!='incomplete',headers={},stop_reason=None)
  with patch.object(entry.INTAKE,'bounded_get',response):out=entry.INTAKE.collect({'requests':m['requests']},m['request_limits'],object(),Path(temp)/'market')
  assert out['requests_used']==want
  if typ=='pagination':assert all(a['status']=='page_cap_truncated' for a in out['attempts'] if a['page']==next(s['max_pages'] for s in m['requests'] if s['id']==a['id']))
  if typ=='incomplete':assert out['incomplete_response_reserved_bytes']==2097152
  inert.append(dict(mode=typ,calls=want))
assert not (P/'market/request-ledger.json').exists()
out=dict(status='revise_entry' if failure else 'pass',request_manifest=bind(P/'request-manifest.json'),bindings_checked=checked,case_clocks_verified=clocks,reuse_selected_presence=reuse,entry_blocker=failure,inert_collector_results=inert,real_HTTP=0,credentials_initialized=False,economic_computation=False,resource=dict(CPU=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,affinity=[0]))
(P/'independent-entry-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['bindings_checked','reuse_selected_presence']}))
