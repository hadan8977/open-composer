"""Independent bounded component acceptance; no strategy returns or network."""
import hashlib,json,os,resource
from collections import Counter
from pathlib import Path
from decimal import Decimal,localcontext,ROUND_CEILING
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
resource.setrlimit(resource.RLIMIT_CPU,(75,80))
assert os.sched_getaffinity(0)=={0}
import pandas as pd
import pyarrow.parquet as pq
from open_composer.market_sessions import us_equity_session_dates,previous_us_equity_session
from open_composer.research.features.price_hygiene import sanitize_price_matrices
P=Path(__file__).resolve().parent;V=P.parent;ROOT=Path.cwd();NY=ZoneInfo('America/New_York');checks=[]
def load(p,dec=False):return json.loads(Path(p).read_bytes(),**({'parse_float':Decimal,'parse_int':Decimal} if dec else {}))
def verify(b):
 p=Path(b['path']);blob=p.read_bytes();assert hashlib.sha256(blob).hexdigest()==b['sha256'],str(p)
 checks.append(dict(path=str(p),sha256=b['sha256'],bytes=len(blob)));return blob
verify(dict(path=P/'manifest.json',sha256='481d7c00fa145581e072a4aa2786e6ee0061c52e7c907562443294b3318a5a1d'))
manifest=load(P/'manifest.json')
for b in manifest['files']:verify(b)
verify(manifest['root_pool_authority']);verify(manifest['original_accepted_manifest'])
config=load(P/'config.json');result=load(P/'result.json');summary=load(P/'summary.json')
for b in config.values():
 if isinstance(b,dict) and 'path' in b and 'sha256' in b:verify(b)
days=[date.fromisoformat(d) for d in config['days']];symbols=config['symbols']
assert days==list(us_equity_session_dates(date(2024,1,1),date(2024,12,31)))[:40]
assert len(symbols)==len(set(symbols))==25
cases={};counts=Counter();geometry=Counter();adrs=[]
config_sha=hashlib.sha256((P/'config.json').read_bytes()).hexdigest()
for symbol in symbols:
 for day in days:
  c=load(P/'cases'/f'{symbol}--{day}.json');cases[symbol,day]=c
  assert c['symbol']==symbol and c['day']==str(day) and c['config_sha256']==config_sha
  assert not c['orders_fits_strategy_returns_PnL'];assert len(c['events'])==26
  f=c['feature'];assert f['full_eligibility'] is None and f['full_rank'] is None
  assert not f['episode_interval_certified'] and not f['first_episode_EMA_seed_certified']
  counts.update(c['counts']);geometry.update(c['geometry_counts'])
  assert len(c['missing_minutes'])==c['counts']['missing_real_minutes']
  assert all(e['full_eligibility'] is None and not e['actual_order_or_fill'] for e in c['events'])
  if 'ADR20' in f:adrs.append(Decimal(f['ADR20']))
assert dict(counts)==result['counts'];assert dict(geometry)==result['geometry_counts']
assert counts['raw_minute_rows']+counts['missing_real_minutes']==1000*390
assert len(adrs)==960 and max(adrs)<Decimal('.05')
assert str(min(adrs))==summary['source_fit_only']['ADR_min'] and str(max(adrs))==summary['source_fit_only']['ADR_max']
assert all(cases['SGEN',d]['counts']['raw_minute_rows']==0 and cases['SGEN',d]['counts']['missing_real_minutes']==390 for d in days)

ids=load(V/'full-cohort-route/identity-candidates.json');oldids=load(V/'identity-candidates.json')
roster=load(V/'frozen-historical-roster.json')['rows'];ordered=sorted(roster,key=lambda x:x['diagnostic_hash'])
assert len(ids['records'])==101 and ids['FTD_sources']==oldids['FTD_sources']
for old,new in zip(oldids['records'],ids['records'][:25],strict=True):
 for key,value in old.items():assert new[key]==value,(key,old['issue_key'])
points=[]
for b in ids['FTD_sources']:
 # Same two already accepted files; read only identity fields, do not repeat raw SHA.
 table=pq.read_table(b['path'],columns=['settlement_date','cusip','symbol','description'],use_threads=False)
 points.extend(r for r in table.to_pylist() if r['settlement_date']<date(2024,1,2))
bycusip={}
for r in points:bycusip.setdefault(r['cusip'],[]).append(r)
for issue,r in zip(ordered,ids['records'],strict=True):
 assert r['issue_key']==issue['issue_key'] and r['diagnostic_hash']==issue['diagnostic_hash']
 p=bycusip.get(issue['cusip'],[]);last=max((x['settlement_date'] for x in p),default=None)
 recent=sorted(({**x,'settlement_date':str(x['settlement_date'])} for x in p if x['settlement_date']==last),key=lambda x:json.dumps(x,sort_keys=True))
 assert recent==sorted(r['FTD_dated_points'],key=lambda x:json.dumps(x,sort_keys=True))
 s=sorted({x['symbol'] for x in recent if x['symbol']});expected=issue['ticker'] or (s[0] if len(s)==1 else None)
 assert r['source_ticker_candidate']==expected and r['episode_validity_interval'] is None and r['first_real_episode_EMA_seed'] is None

ledger=load(V/'market/request-ledger.json');raw={};pointers={};minute_attempts={}
def stamp(r):return datetime.fromisoformat(r['t'].replace('Z','+00:00')).astimezone(NY)
def valid(r):return all(r[k].is_finite() and r[k]>0 for k in ['o','h','l','c','vw']) and r['l']<=min(r['o'],r['c'])<=max(r['o'],r['c'])<=r['h'] and r['v']>=0 and not(r['v']==0 and r['n']==0)
for a in ledger['attempts']:
 if a['id']=='diagnostic_daily_raw':
  for s,rr in load(a['entity']['path'],True)['bars'].items():
   for i,r in enumerate(rr):
    d=stamp(r).date();assert d not in raw.setdefault(s,{})
    raw[s][d]=r;pointers[s,d]={'entity_sha256':a['entity']['sha256'],'pointer':f'/bars/{s}/{i}'}
 if a['id'].startswith('raw_RTH_'):minute_attempts[date.fromisoformat(a['id'][8:])]=a
actions=load(V/'bounded-components/all-actions-and-held-rights.json')['records']
splits=[a['record'] for a in actions if 'split' in a['type']]
for s in symbols:
 assert not any(a.get('symbol')==s and min(raw[s])<date.fromisoformat(a['ex_date'])<=days[-1] for a in splits)
selected=[days[0],days[19],days[-1]];numeric=[];events_checked=0;raw_rows=0
with localcontext() as ctx:
 ctx.prec=60
 for day in selected:
  a=minute_attempts[day];payload=load(a['entity']['path'],True)
  for s in symbols:
   c=cases[s,day];f=c['feature'];assert c['source_minute_entity']==a['entity']
   prior=previous_us_equity_session(day);prefix={d:r for d,r in raw[s].items() if d<=prior}
   cal=list(us_equity_session_dates(min(prefix),prior))
   close=pd.DataFrame({s:[float(prefix[d]['c']) if d in prefix and valid(prefix[d]) else float('nan') for d in cal]},index=pd.DatetimeIndex(cal))
   op=pd.DataFrame({s:[float(prefix[d]['o']) if d in prefix and valid(prefix[d]) else float('nan') for d in cal]},index=close.index)
   clean,_,hyg=sanitize_price_matrices(close,op);assert hyg.manifest()==f['hygiene_asof_prefix_only']
   suffix=[]
   for d,x in zip(cal,clean[s],strict=True):suffix=[] if pd.isna(x) else suffix+[d]
   assert len(suffix)==f['contiguous_clean_sessions']
   pdates=sorted(prefix)
   assert f['raw_daily_last20_pointers']==[pointers[s,d] for d in pdates[-20:]]
   if len(suffix)>=63:
    tail=[prefix[d] for d in suffix[-20:]]
    calc={'ADR20':sum(r['h']/r['l']-1 for r in tail)/20,'ADV20':sum(r['c']*r['v'] for r in tail)/20,'momentum21':prefix[suffix[-1]]['c']/prefix[suffix[-22]]['c']-1}
    for n in [9,21,50]:
     alpha=Decimal(2)/Decimal(n+1);history=[];val=prefix[suffix[0]]['c']
     for d in suffix:
      if history:val=alpha*prefix[d]['c']+(1-alpha)*val
      history.append(val)
     calc[f'EMA{n}']=val
     if n==21:assert f['rising_EMA21_lag5']==(history[-1]>history[-6])
    assert all(Decimal(f[k])==v for k,v in calc.items())
    gate=calc['ADV20']>=50000000 and calc['momentum21']>0 and calc['EMA9']>calc['EMA21']>calc['EMA50'] and f['rising_EMA21_lag5']
    assert bool(gate)==f['numeric_price_gate']
    numeric.append([s,str(day)])
   else:assert f['numeric_price_gate'] is False and 'ADR20' not in f
   records=payload.get('bars',{}).get(s,[]);raw_rows+=len(records);mapped={};seen=set();duplicates=set();invalid=[]
   for ordinal,r in enumerate(records):
    t=stamp(r)
    if t in seen:duplicates.add(t)
    seen.add(t)
    if valid(r):mapped[t]=(ordinal,r)
    else:invalid.append(ordinal)
   start=datetime.combine(day,datetime.min.time(),NY)+timedelta(hours=9,minutes=30)
   expected=[start+timedelta(minutes=i) for i in range(390)]
   missing=[str(t) for t in expected if t not in mapped or t in duplicates]
   assert missing==c['missing_minutes'] and invalid==c['invalid_source_ordinals']
   geom=Counter();grid=list(range(1,15))+list(range(15,60,5))+[60,75,90]
   gridup=lambda x:(x/Decimal('.01')).to_integral_value(rounding=ROUND_CEILING)*Decimal('.01')
   prev10=max(prefix[d]['h'] for d in sorted(d for d in prefix if valid(prefix[d]))[-10:])
   for offset,e in zip(grid,c['events'],strict=True):
    width=1 if offset<15 else 5 if offset<60 else 15
    assert e['close_time']==str(start+timedelta(minutes=offset)) and e['width_minutes']==width
    times=[start+timedelta(minutes=i) for i in range(offset-width,offset)]
    if any(t not in mapped or t in duplicates for t in times):
     assert e['status']=='missing_real_parent';geom['missing_parent_events']+=1;continue
    geom['complete_parent_events']+=1;rr=[mapped[t][1] for t in times]
    low=min(r['l'] for r in rr);high=max(r['h'] for r in rr);last=rr[-1]['c']
    assert e['source_pointers']==[f'/bars/{s}/{mapped[t][0]}' for t in times]
    assert (Decimal(e['low']),Decimal(e['high']),Decimal(e['close']))==(low,high,last)
    if f['numeric_price_gate']:
     pref=gridup(high+Decimal('.01'));adr=Decimal(f['ADR20'])
     supports=[(abs(low-Decimal(f[k]))/Decimal(f[k]),i,k) for i,k in enumerate(['EMA21','EMA9']) if abs(low-Decimal(f[k]))/Decimal(f[k])<=Decimal('.25')*adr and last>=Decimal(f[k])]
     pb=bool(supports) and pref>=5 and 0<(pref-low)/pref<=min(Decimal('.05'),Decimal('.5')*adr)
     assert e['EMA_PB_price_geometry']==pb and Decimal(e['P_ref'])==pref
     assert e['chosen_support']==(min(supports)[2] if supports else None)
     active=offset+1<90;assert e['baseline_activation_before_cutoff']==active
     if pb:geom['EMA_PB_price_geometry_candidates']+=1;geom['baseline_activatable_EMA_PB_candidates']+=int(active)
     if width==5:
      bp=gridup(max(high+Decimal('.01'),prev10+Decimal('.01')))
      br=last>prev10+Decimal('.01') and bp>=5 and 0<(bp-low)/bp<=min(Decimal('.05'),Decimal('.5')*adr)
      assert e['BREAK_price_geometry']==br and Decimal(e['BREAK_P_ref'])==bp and Decimal(e['previous10high'])==prev10
      geom['BREAK_price_geometry_candidates']+=int(br)
    events_checked+=1
   assert dict(geom)==c['geometry_counts'],(s,str(day),geom,c['geometry_counts'])
out=dict(status='pass',manifest_bindings=len(manifest['files']),hashed=checks,all1000_checkpoint_counts_reconciled=dict(counts),geometry_summary=dict(geometry),source_fit={'count':len(adrs),'min':str(min(adrs)),'max':str(max(adrs)),'above5percent':0},full101_four_identity_columns_checked=True,first25_exact_common_fields_unchanged=True,selected_days=list(map(str,selected)),selected_symbol_days=75,independent_Decimal60_numeric_cases=numeric,complete_parent_events_recomputed=events_checked,selected_raw_minute_rows=raw_rows,missing_parent_and_session_clocks_verified=True,whole1000_feature_numeric_replay=False,old47_source_rehash=False,old69MB_index_rebuilt=False,no_economic_or_network=True,resource={'CPU':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,'RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'affinity':[0]})
(P/'independent-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ['hashed','independent_Decimal60_numeric_cases']}))
