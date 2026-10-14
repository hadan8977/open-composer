"""Bounded independent source/feature/clock QA. No signals, orders or P&L."""
import hashlib,json,os,resource
from decimal import Decimal,localcontext
from datetime import date,datetime,timedelta
from pathlib import Path
from collections import Counter
from zoneinfo import ZoneInfo
resource.setrlimit(resource.RLIMIT_CPU,(50,50));os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import pandas as pd
import pyarrow.parquet as pq
from open_composer.market_sessions import us_equity_session_dates,previous_us_equity_session
from open_composer.research.features.price_hygiene import sanitize_price_matrices

ROOT=Path('/root/codex-test/open-composer');P=Path(__file__).parent;NY=ZoneInfo('America/New_York');B={}
def dec(x):return Decimal(str(x))
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),default=lambda v:str(v) if isinstance(v,Decimal) else None)
def read(path):return json.loads(Path(path).read_text(),parse_float=Decimal)
def day(t):return datetime.fromisoformat(t.replace('Z','+00:00')).astimezone(NY).date()
def bind(path):
 path=Path(path);path=path if path.is_absolute() else ROOT/path
 if str(path) not in B:
  raw=path.read_bytes();B[str(path)]={'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
 return B[str(path)]
def check(b):
 a=bind(b['path']);assert a['sha256']==b['sha256'];assert 'bytes' not in b or a['bytes']==b['bytes'];return ROOT/a['path']
def factor(s,d,basis,splits):
 out=Decimal(1)
 for a in splits:
  if a['symbol']==s and d<date.fromisoformat(a['ex_date'])<=basis:out*=dec(a['new_rate'])/dec(a['old_rate'])
 return out

def main():
 assert bind(P/'package-manifest.json')['sha256']=='05c0d1fcfe270d48711ab6eeaf5eb051688bb76982ceca255cf8fa8fa873548d'
 manifest=read(P/'package-manifest.json')
 for b in manifest['files']:check(b)
 assert len(manifest['files'])==42
 grant=read(P/'root-resource-decision.json');assert bind(P/'root-resource-decision.json')['sha256']=='18de64b71fd536434ce5d05bd6ccbc7a38d68a474398f4382d93da7b3f503b53'
 for b in grant['bindings'].values():check(b)
 check(grant['independent_scientific_acceptance'])
 ledger=read(P/'request-ledger.json');scope=read(P.parent/'input-and-request-scope.json');req={r['id']:r for r in scope['requests']}
 assert ledger['requests_used']==13 and ledger['complete_entity_bytes']==2347300 and ledger['incomplete_response_reserved_bytes']==0
 packets={};entities={}
 for a in ledger['attempts']:
  assert a['http_status']==200 and a['entity_complete'] and a['page']==1 and a['next_page_token'] is None
  assert a['params']==req[a['id']]['params'] and a['path']==req[a['id']]['path']
  path=check(a['entity']);assert path.stat().st_size==a['retained_bytes'];packets[a['id']]=read(path);entities[a['entity']['path']]=packets[a['id']]
  assert packets[a['id']]['next_page_token'] is None
 assert sum(a['retained_bytes'] for a in ledger['attempts'])==2347300
 count=0
 with (P/'derived/source-records.jsonl').open() as f:
  for line in f:
   r=json.loads(line);x=entities[r['entity']['path']]
   for part in r['json_pointer'].split('/')[1:]:x=x[int(part)] if isinstance(x,list) else x[part.replace('~1','/').replace('~0','~')]
   assert hashlib.sha256(canon(x).encode()).hexdigest()==r['source_object_sha256_decimal_as_text']
   assert canon(json.loads(canon(x)))==canon(r['source_object'])
   assert r['historical_first_visible'] is None;count+=1
 assert count==22410
 raw=packets['public_case_daily_raw']['bars'];adj=packets['public_case_daily_all']['bars'];actions=packets['public_case_actions']['corporate_actions'];splits=actions['forward_splits']
 assert sum(map(len,raw.values()))==sum(map(len,adj.values()))==8282
 assert sum(map(len,actions.values()))==6
 for s,rows in raw.items():
  days=[day(r['t']) for r in rows];assert days==list(us_equity_session_dates(days[0],days[-1]))
  assert len(days)==len(set(days))
  bytime={r['t']:r for r in adj[s]}
  for r in rows:
   assert dec(r['l'])<=min(dec(r['o']),dec(r['c']))<=max(dec(r['o']),dec(r['c']))<=dec(r['h']) and dec(r['l'])>0 and dec(r['v'])>0
   q=bytime[r['t']];fac=factor(s,day(r['t']),date(2026,10,13),splits)
   assert all(abs(dec(q[k])-dec(r[k])/fac)<=Decimal('.005000001') for k in ['o','h','l','c','vw'])
   assert dec(q['v'])==dec(r['v'])*fac
 features=read(P/'derived/causal-feature-candidates.json')['features'];feature_checks=[]
 for f in features:
  s=f['symbol'];d=date.fromisoformat(f['decision_day']);prev=previous_us_equity_session(d);before=[r for r in raw[s] if day(r['t'])<=prev];days=[day(r['t']) for r in before]
  assert str(prev)==f['prior_completed_day'] and len(days)==f['contiguous_clean_sessions']
  closes=[dec(r['c'])/factor(s,day(r['t']),d,splits) for r in before];opens=[dec(r['o'])/factor(s,day(r['t']),d,splits) for r in before]
  df=pd.DataFrame({s:[float(x) for x in closes]},index=pd.DatetimeIndex(days));op=pd.DataFrame({s:[float(x) for x in opens]},index=df.index)
  clean,_,hyg=sanitize_price_matrices(df,op);assert clean.equals(df) and json.loads(json.dumps(hyg.manifest()),parse_float=Decimal)==f['hygiene_asof_prefix_only']
  with localcontext() as ctx:
   ctx.prec=60
   if len(before)<20:
    assert all(f[k] is None for k in ['ADR20','ADV20','price_momentum21','EMA9','EMA21','EMA50']);feature_checks.append({'symbol':s,'day':str(d),'status':'17session_NA_correct'});continue
   assert sum(dec(r['h'])/dec(r['l'])-1 for r in before[-20:])/20==dec(f['ADR20'])
   assert sum(dec(r['c'])*dec(r['v']) for r in before[-20:])/20==dec(f['ADV20'])
   assert closes[-1]/closes[-22]-1==dec(f['price_momentum21'])
   for n in [9,21,50]:
    alpha=Decimal(2)/Decimal(n+1);value=closes[0];vals=[value]
    for c in closes[1:]:value=alpha*c+(1-alpha)*value;vals.append(value)
    assert value==dec(f['EMA'+str(n)])
    if n==21:assert (vals[-1]>vals[-6])==f['rising_EMA21_lag5']
   lows=[dec(r['l'])/factor(s,day(r['t']),d,splits) for r in before]
   anchors=[i for i in range(2,len(lows)-2) if len(lows)-1-i<=60 and all(lows[i]<lows[j] for j in [i-2,i-1,i+1,i+2])]
   if anchors:
    i=anchors[-1];assert f['missing_AVWAP_packet']['raw_RTH_VWAP_volume_start']==str(days[i])+'09:30NY';assert f['missing_AVWAP_packet']['anchor_confirmation_day']==str(days[i+2])
   else:assert f['missing_AVWAP_packet'] is None
  feature_checks.append({'symbol':s,'day':str(d),'status':'Decimal60_feature_and_anchor_match'})
 minutes={};minute_count=0
 for rid,x in packets.items():
  if req[rid].get('params',{}).get('timeframe')=='1Min':
   s=next(iter(x['bars']));rows=x['bars'][s];minute_count+=len(rows);minutes[(s,str(day(rows[0]['t'])))]=(rid,{pd.Timestamp(r['t']).value:r for r in rows})
 assert minute_count==5765 and len(minutes)==8
 grids=read(P/'derived/completed-bar-clock-components.json')['events'];stats=Counter()
 for e in grids:
  rid,bytime=minutes[(e['symbol'],e['day'])];end=pd.Timestamp(e['completed_at']);n=e['grid_minutes'];expected_n=1 if end.hour==9 and end.minute<45 else (5 if end.hour<10 or(end.hour==10 and end.minute<30) else 15)
  assert n==expected_n
  stamps=[(end-pd.Timedelta(minutes=i)).tz_convert('UTC').value for i in range(n,0,-1)];parents=[bytime.get(t) for t in stamps]
  assert e['missing_parent_minute_ns']==[t for t,r in zip(stamps,parents) if r is None]
  assert e['activation_proxy']==(end+pd.Timedelta(minutes=1)).isoformat() and e['extra_delay_activation_proxy']==(end+pd.Timedelta(minutes=2)).isoformat()
  stats[e['status']]+=1
  if all(r is not None for r in parents):
   assert e['status']=='actual_completed_bar_component'
   assert dec(e['o'])==dec(parents[0]['o']) and dec(e['c'])==dec(parents[-1]['c'])
   assert dec(e['h'])==max(dec(r['h']) for r in parents) and dec(e['l'])==min(dec(r['l']) for r in parents) and dec(e['v'])==sum(dec(r['v']) for r in parents)
  else:assert e['status']=='incomplete_or_invalid_parents_retained'
 assert stats=={'actual_completed_bar_component':175,'incomplete_or_invalid_parents_retained':33}
 clocks=read(P/'derived/minute-clock-and-vintage.json')['cases'];cache_checks=[]
 for c in clocks:
  if 'cached_all_raw_reconciliation' not in c:continue
  b=c['cached_all_raw_reconciliation']['file'];path=check(b);s=c['symbol'];d=date.fromisoformat(c['day']);start=pd.Timestamp(datetime.combine(d,datetime.min.time(),NY)).tz_convert('UTC');end=start+pd.Timedelta(days=1)
  table=pq.read_table(path,filters=[('symbol','=',s),('timestamp','>=',start),('timestamp','<',end)],use_threads=False).to_pylist()
  bytime=minutes[(s,str(d))][1];fac=factor(s,d,date(2026,10,13),splits)
  for row in table:
   r=bytime[pd.Timestamp(row['timestamp']).value]
   assert all(abs(dec(row[dst])*fac-dec(r[src]))<=Decimal('.005000001')*fac for src,dst in [('o','open'),('h','high'),('l','low'),('c','close'),('vw','vwap')])
   assert dec(row['volume'])==dec(r['v'])*fac and dec(row['trade_count'])==dec(r['n'])
  assert len(table)==len(bytime)==c['rows'];cache_checks.append({'symbol':s,'day':str(d),'actual_rows':len(table)})
 assert len(cache_checks)==7
 quote_context=read(P/'derived/quote-context.json')['contexts']
 for q in quote_context:
  rows=packets[q['request_id']]['quotes'];assert len(rows)==q['source_records']
  assert [pd.Timestamp(r['t']).value for r in rows]==sorted(pd.Timestamp(r['t']).value for r in rows)
  assert all(r['c']==['?'] for r in rows)
  assert sum(dec(r['bp'])>dec(r['ap']) for r in rows)==q['crossed_records_retained']
  valid=[r for r in rows if all(dec(r[k])>0 for k in ['bp','ap','bs','as']) and dec(r['bp'])<=dec(r['ap'])]
  assert canon(valid[0])==canon(q['first_structurally_valid_quote'])
  assert canon(next(r for r in valid if dec(r['ap'])<=501))==canon(q['first_uncrossed_ask_le501'])
 warrant=actions['spin_offs'][0];assert warrant['id']=='83d8ed5e-8d5a-4021-bf03-552c2b537dfe' and warrant['source_rate']==10 and warrant['new_rate']==1 and warrant['new_symbol']=='GME.WS'
 rights=read(P/'derived/lifecycle-and-rights.json')['GME_2025_warrant'];assert rights['market_value'] is None and rights['actual_receipt'] is None and not rights['cross_event_wealth_or_NAV_ready']
 csiq=next(f for f in features if f['symbol']=='CSIQ');assert dec(csiq['price_momentum21'])<0 and dec(csiq['EMA9'])<dec(csiq['EMA21'])
 result={'status':'ok','direct_manifest_bindings':42,'verified_paths':list(B.values()),'request_count':13,'complete_bytes':2347300,'source_records_pointer_and_canonical_SHA_replayed':count,'daily_raw_all_each':8282,'minute_rows':minute_count,'feature_checks':feature_checks,'grid_counts':dict(stats),'seven_cached_day_checks':cache_checks,'GME_quotes_nanos_and_unknown_conditions_retained':True,'GME_WS_separate_right_verified':True,'CSIQ_not_v2_eligible_on_this_date':True,'no_signals_returns_orders_fit':True,'CPU_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'memory_cap_MiB':512,'pool':'USIC comparison shared1000, max70 current review'}
 (P/'independent-component-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='verified_paths'},ensure_ascii=False))
if __name__=='__main__':
 try:main()
 except BaseException as e:
  (P/'independent-component-verification-failure.json').write_text(json.dumps({'error':repr(e),'CPU_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},indent=2)+'\n');raise
