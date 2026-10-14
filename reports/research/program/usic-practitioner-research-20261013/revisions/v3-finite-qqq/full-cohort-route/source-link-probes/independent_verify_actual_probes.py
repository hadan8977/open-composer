import json,hashlib,resource,os
from pathlib import Path
from datetime import date,datetime
from decimal import Decimal,localcontext
from collections import Counter
from zoneinfo import ZoneInfo
resource.setrlimit(resource.RLIMIT_CPU,(40,45));assert os.sched_getaffinity(0)=={0}
import pyarrow.parquet as pq
import pandas as pd
from open_composer.market_sessions import us_equity_session_dates
from open_composer.research.features.price_hygiene import sanitize_price_matrices
P=Path(__file__).resolve().parent;R=P.parent;V=R.parent;checks=[]
def load(p,dec=False):return json.loads(Path(p).read_bytes(),**({'parse_float':Decimal,'parse_int':Decimal} if dec else {}))
def verify(b):
 p=Path(b['path']);raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==b['sha256'],str(p);checks.append(dict(path=str(p),sha256=b['sha256'],bytes=len(raw)))
verify(dict(path=P/'actual-manifest.json',sha256='adb7e462b5f02881ce7c7903b530a271e5517ece742a2e610dad207d20993dc5'))
m=load(P/'actual-manifest.json')
for b in m['files']:verify(b)
ledger=load(P/'market/request-ledger.json');request=load(P/'request-manifest.json');result=load(P/'actual-result.json')
assert ledger['requests_used']==3 and ledger['complete_entity_bytes']==170204 and ledger['incomplete_response_reserved_bytes']==0 and len(ledger['attempts'])==3
payloads={};sizes=[]
for a,spec in zip(ledger['attempts'],request['requests'],strict=True):
 assert a['id']==spec['id'] and a['params']==spec['params'] and a['page']==1 and a['http_status']==200 and a['entity_complete']
 assert a['status']=='complete_bounded_source_response' and a['next_page_token'] is None
 payloads[a['id']]=load(a['entity']['path'],True);sizes.append(Path(a['entity']['path']).stat().st_size)
assert sizes==[34,14201,155969]
assert payloads['TSLA_pre2016_raw_history']['bars']=={}
history=payloads['GEHC_GEHCV_birth_prefix']['bars']
assert len(history['GEHCV'])==12 and len(history['GEHC'])==123
assert [history[s][i]['t'][:10] for s,i in [('GEHCV',0),('GEHCV',-1),('GEHC',0),('GEHC',-1)]]==['2022-12-15','2023-01-03','2023-01-04','2023-06-30']
old=load(V/'market/request-ledger.json');a=next(a for a in old['attempts'] if a['id']=='raw_RTH_2024-01-02');raw=load(a['entity']['path'],True)['bars'];current=payloads['four_current_vintage_all_minute']['bars']
fields=dict(o='open',h='high',l='low',c='close',v='volume',n='trade_count',vw='vwap');comparisons=[]
for reported in result['current_ALL_oldcache_raw_comparisons']:
 s=reported['symbol'];basis=load(R/f'cache-basis-probe/{s}.json');src=next(x['file'] for x in basis['source_files'] if '/2024/01/' in x['file']['path'])
 table=pq.read_table(src['path'],columns=['symbol','timestamp',*fields.values()],filters=[('symbol','==',s)],use_threads=False)
 cached={r['timestamp'].isoformat().replace('+00:00','Z'):r for r in table.to_pylist()}
 allrows={r['t']:r for r in current[s]};assert len(allrows)==len(current[s])
 counts=Counter()
 for r in raw[s]:
  c=cached[r['t']];a=allrows[r['t']];counts['matched_rows']+=1
  counts['raw_equals_current_all_7']+=int(all(r[k]==a[k] for k in fields))
  counts['cache_equals_current_all_7']+=int(all(Decimal(str(c[ck]))==a[k] for k,ck in fields.items()))
  counts['raw_current_volume_and_trades_equal']+=int(r['v']==a['v'] and r['n']==a['n'])
 assert dict(counts)==reported['counts']
 for collision in reported['current_ALL_high_collisions']:
  vv=[]
  for p in collision['pairs']:
   r=raw[s][int(p['raw_pointer'].rsplit('/',1)[1])]
   assert r['t']==p['t'] and r['h']==Decimal(p['raw_h'])
   assert allrows[r['t']]['h']==Decimal(collision['same_current_ALL_high']);vv.append(r['h'])
  assert vv[0]!=vv[1]
 comparisons.append({'symbol':s,'counts':dict(counts),'collision_pairs_checked':len(reported['current_ALL_high_collisions'])})
ny=ZoneInfo('America/New_York');dayof=lambda r:datetime.fromisoformat(r['t'].replace('Z','+00:00')).astimezone(ny).date()
july={}
for a in old['attempts']:
 if a['id']=='diagnostic_daily_raw':july.update({dayof(r):r for r in load(a['entity']['path'],True)['bars'].get('GEHC',[]) if dayof(r)<=date(2023,12,29)})
extended={**{dayof(r):r for r in history['GEHC']},**july};values={}
with localcontext() as ctx:
 ctx.prec=60
 for name,prefix in [('old_July_source_window',july),('earlier_regular_symbol_window',extended)]:
  o=result['GEHC_source_window_sensitivity'][name];days=us_equity_session_dates(min(prefix),date(2023,12,29));assert len(days)==len(prefix)==o['contiguous_clean_sessions']
  cl=pd.DataFrame({'GEHC':[float(prefix[d]['c']) for d in days]},index=pd.DatetimeIndex(days));op=pd.DataFrame({'GEHC':[float(prefix[d]['o']) for d in days]},index=cl.index)
  clean,_,hyg=sanitize_price_matrices(cl,op);assert clean['GEHC'].notna().all() and hyg.manifest()==o['hygiene_asof_prefix_only']
  tail=[prefix[d] for d in days[-20:]];calc=dict(ADR20=sum(r['h']/r['l']-1 for r in tail)/20,ADV20=sum(r['c']*r['v'] for r in tail)/20,momentum21=prefix[days[-1]]['c']/prefix[days[-22]]['c']-1)
  for n in [9,21,50]:
   alpha=Decimal(2)/Decimal(n+1);v=prefix[days[0]]['c'];hist=[]
   for d in days:
    if hist:v=alpha*prefix[d]['c']+(1-alpha)*v
    hist.append(v)
   calc[f'EMA{n}']=v
   if n==21:assert (hist[-1]>hist[-6])==o['rising_EMA21_lag5']
  assert all(Decimal(o[k])==v for k,v in calc.items());assert o['first_episode_EMA_seed_certified'] is False and o['full_rank'] is None
  values[name]=calc
 delta={k:str(values['earlier_regular_symbol_window'][k]-values['old_July_source_window'][k]) for k in values['old_July_source_window']}
inventory=load(R/'cache-route-inventory.json');ids=load(R/'identity-candidates.json')['records']
assert [r['issue_key'] for r in inventory['records']]==[r['issue_key'] for r in ids]
assert len(inventory['records'])==101
assert sum(bool(r['shards']) for r in inventory['records'])==97
missing=[r['symbol_candidate'] for r in inventory['records'] if not r['shards']]
assert set(missing)=={'SGEN','ANSS','EA','WBA'}
assert sum(sum(x['exists'] for x in r['exact_file_metadata']) for r in inventory['records'])==2328
assert result['aggregate_market_requests_used']==63 and result['aggregate_complete_entity_bytes']==43895341+170204==44065545
assert result['aggregate_remaining_requests_bytes']==[33,134217728-44065545]
assert result['unused_reservation_bytes_released_after_complete3pages']==4718592-170204
out=dict(status='pass',bindings_checked=checks,source_packets=[dict(id=a['id'],size=size) for a,size in zip(ledger['attempts'],sizes,strict=True)],comparisons=comparisons,GEHC_independent_Decimal60_two_windows=[126,249],extended_minus_July=delta,GEHCV_not_spliced=True,inventory_declared_records_checked=101,inventory_missing_locators=missing,inventory_file_refs=2328,inventory_files_reopened_or_continuity_certified=False,aggregate_used_requests_bytes=[63,44065545],aggregate_remaining_requests_bytes=[33,90152183],released_entity_reservation=4548388,new_network_fits_PnL=0,resource=dict(CPU=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,affinity=[0]))
(P/'independent-actual-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='bindings_checked'}))
