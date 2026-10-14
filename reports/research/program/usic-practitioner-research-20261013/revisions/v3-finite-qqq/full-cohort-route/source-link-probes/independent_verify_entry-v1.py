import hashlib,importlib.util,json,os,resource,tempfile
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal,localcontext,ROUND_CEILING
from unittest.mock import patch
resource.setrlimit(resource.RLIMIT_CPU,(55,60));assert os.sched_getaffinity(0)=={0}
import pyarrow.parquet as pq
P=Path(__file__).resolve().parent;R=P.parent;V=R.parent;BASE=V.parents[1];ROOT=Path.cwd();checks=[]
def load(p,dec=False):return json.loads(Path(p).read_bytes(),**({'parse_float':Decimal,'parse_int':Decimal} if dec else {}))
def verify(b):
 p=Path(b['path'])
 with p.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
 assert sha==b['sha256'],str(p);checks.append(dict(path=str(p),sha256=sha,bytes=p.stat().st_size))
verify(dict(path=P/'request-manifest.json',sha256='e8fc9fe6514e9824fd4513ffa150a007f91215b93a976cf50904918afd6c4f20'))
m=load(P/'request-manifest.json')
for b in m['entry_bindings']:verify(b)
cm=load(R/'cache-basis-probe/manifest.json')
for b in cm['files']+[cm['code'],cm['original_market_ledger']]:verify(b)
ledger=load(V/'market/request-ledger.json')
a=next(a for a in ledger['attempts'] if a['id']=='raw_RTH_2024-01-02');raw=load(a['entity']['path'],True)['bars']
daily={}
for a in ledger['attempts']:
 if a['id'] in ['diagnostic_daily_raw','diagnostic_daily_all']:
  for s,rows in load(a['entity']['path'],True)['bars'].items():
   for row in rows:
    if row['t'].startswith('2024-01-02'):daily[s,a['id']]=row
fields=dict(o='open',h='high',l='low',c='close',v='volume',n='trade_count',vw='vwap')
sample=[];cached={}
with localcontext() as ctx:
 ctx.prec=60
 for s in ['PCAR','ROST','GEHC','TSLA']:
  report=load(R/f'cache-basis-probe/{s}.json');f=next(x['file'] for x in report['source_files'] if '/2024/01/' in x['file']['path'])
  table=pq.read_table(f['path'],columns=['symbol','timestamp',*fields.values()],filters=[('symbol','==',s)],use_threads=False)
  cached[s]={r['timestamp'].isoformat().replace('+00:00','Z'):r for r in table.to_pylist() if r['timestamp'].date().isoformat()=='2024-01-02'}
  exact={k:0 for k in fields}
  for r in raw[s]:
   c=cached[s][r['t']]
   for k,ck in fields.items():exact[k]+=int(r[k]==Decimal(str(c[ck])))
  if s=='TSLA':assert all(n==len(raw[s]) for n in exact.values())
  else:
   assert exact['v']==exact['n']==len(raw[s]);assert all(exact[k]==0 for k in ['o','h','l','c','vw'])
   example=report['counterexamples'][0];r=raw[s][0];c=cached[s][r['t']]
   factor=daily[s,'diagnostic_daily_raw']['c']/daily[s,'diagnostic_daily_all']['c']
   residual=Decimal(str(c['close']))*factor-r['c']
   assert residual==Decimal(example['scaled_minus_actual_raw_close']) and residual!=0
  sample.append(dict(symbol=s,rows=len(raw[s]),exact_fields=exact))
 collisions=load(R/'cache-price-collisions.json');collision_count=0
 for group in collisions['records']:
  s=group['symbol']
  for pair in group['observed_collisions']:
   field=pair['field'];vals=[]
   for item in pair['same_cached_value_distinct_raw_values']:
    ordinal=int(item['raw_pointer'].rsplit('/',1)[1]);r=raw[s][ordinal];c=cached[s][r['t']]
    assert item['t']==r['t'] and Decimal(item['raw_value'])==r[field]
    assert Decimal(item['cache_value'])==Decimal(str(c[fields[field]]))
    pref=((r['h']+Decimal('.01'))/Decimal('.01')).to_integral_value(rounding=ROUND_CEILING)*Decimal('.01')
    assert pref==Decimal(item['P_ref_from_actual_raw_high']);vals.append((r[field],Decimal(item['cache_value']),pref))
   assert vals[0][0]!=vals[1][0] and vals[0][1]==vals[1][1]
   assert (vals[0][2]!=vals[1][2])==pair['different_P_ref_grid'];collision_count+=1

spec=importlib.util.spec_from_file_location('independent_probe_entry',BASE/'code/query_remaining_source_links.py');entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
proposed=dict(accepted_for_execution=True,author=m['author'],reviewer='ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3',allocation=m['request_limits'],economic_execution_admitted=False,request_manifest=entry.INTAKE.binding(P/'request-manifest.json'),entry_bindings=m['entry_bindings'])
original_read=Path.read_text
def fake_read(path,*args,**kwargs):
 if path==P/'independent-entry-acceptance.json':return json.dumps(proposed)
 return original_read(path,*args,**kwargs)
with patch.object(Path,'read_text',fake_read):
 _,accepted=entry.check_entry();assert accepted==m
 proposed['allocation']={'requests':4,'entity_bytes':4718592}
 try:entry.check_entry();raise RuntimeError('bad allocation accepted')
 except AssertionError:pass
 proposed['allocation']=m['request_limits']
 original_exists=Path.exists
 with patch.object(Path,'exists',lambda p:True if p==P/'market/request-ledger.json' else original_exists(p)):
  try:entry.check_entry();raise RuntimeError('consumed ledger accepted')
  except AssertionError:pass
assert not (P/'market/request-ledger.json').exists()
inert=[]
for status,complete,token,want in [(200,True,'next',3),(403,True,None,1),(200,False,None,1)]:
 with tempfile.TemporaryDirectory(prefix='inert-',dir=P) as td:
  def response(*args):return json.dumps({'bars':{},'next_page_token':token}).encode(),dict(http_status=status,entity_complete=complete,headers={},stop_reason=None)
  with patch.object(entry.INTAKE,'bounded_get',response):
   out=entry.INTAKE.collect({'requests':m['requests']},m['request_limits'],object(),Path(td)/'market')
  assert out['requests_used']==want
  if token:assert all(x['status']=='page_cap_truncated' for x in out['attempts'])
  if not complete:assert out['incomplete_response_reserved_bytes']==1572864
  inert.append(dict(http=status,complete=complete,token=token,calls=want))
assert not (P/'market/request-ledger.json').exists()
out=dict(status='pass',bindings_checked=checks,actual_cached_Jan2_field_comparisons=sample,actual_collision_pairs=collision_count,all40day_numeric_comparison_repeated=False,whole8cache_file_SHA_verified=True,guard_positive_and_badallocation_consumedledger_checks=True,inert_collector_cases=inert,credentials_initialized=False,real_network_calls=0,scope_limits=m['request_limits'],resource=dict(CPU=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,affinity=[0]))
(P/'independent-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='bindings_checked'}))
