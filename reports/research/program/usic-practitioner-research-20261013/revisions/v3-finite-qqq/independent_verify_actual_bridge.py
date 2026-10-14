import hashlib,json,os,resource,xml.etree.ElementTree as ET
from pathlib import Path
from decimal import Decimal,localcontext
from datetime import date,datetime
from zoneinfo import ZoneInfo
resource.setrlimit(resource.RLIMIT_CPU,(17,18));assert os.sched_getaffinity(0)=={0}
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
P=Path(__file__).parent;ROOT=Path.cwd();checks=[]
def load(p,decimal=False):return json.loads(Path(p).read_bytes(),**({'parse_float':Decimal,'parse_int':Decimal} if decimal else {}))
def check(p,sha):
 p=Path(p)
 with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 assert h==sha,str(p);checks.append({'path':str(p),'sha256':h,'bytes':p.stat().st_size})
check(P/'actual-diagnostic-package-manifest.json','a72fb8601cd70e03ada9049a3f6e3d5de646808450652c36c9669ea97e1c8216')
check(P/'actual-bridge-result.json','7d96e2158ded210c92911b1bbda9c0b518320bceea2c7ce68b2a98dea6932997')
check(P/'final-actual-accounting.json','1172df551b3b480865e9179ab70d5aeb48e4ce22cca75c08fe73577c9104ad24')
m=load(P/'actual-diagnostic-package-manifest.json')
for b in m['bindings']:check(P/b['path'],b['sha256'])
for b in m['code_bindings']:check(ROOT/b['path'],b['sha256'])
roster=load(P/'frozen-historical-roster.json');ids=load(P/'identity-candidates.json');exact=load(P/'exact-materialized-request-manifest.json');ledger=load(P/'market/request-ledger.json');repair=load(P/'source-repair-ledger.json')
assert repair['actual_calls']==1 and repair['source_units_after']==37 and repair['status']=='complete200_for_offline_parse'
src=ROOT/roster['source']['path'];assert src.stat().st_size==109147
xml=ET.fromstring(src.read_bytes());local=lambda x:x.rsplit('}',1)[-1]
def field(n,key):
 f=next((c for c in n.iter() if local(c.tag)==key),None)
 return None if f is None else (f.text or f.attrib.get('value','')).strip()
assert field(xml,'repPdDate')=='2023-09-30' and 'QQQ' in field(xml,'regName')
actual=[(field(n,'cusip'),field(n,'isin'),field(n,'assetCat')) for n in xml.iter() if local(n.tag)=='invstOrSec']
assert len(actual)==101 and all(a[2]=='EC' for a in actual)
assert actual==[(r['cusip'],r['isin'],r['assetCat']) for r in roster['rows']]
ordered=sorted((r for r in roster['rows'] if r['source_equity_common']),key=lambda r:(hashlib.sha256(('USIC-RAW-BRIDGE-20261013|'+r['cusip']+'|'+(r['isin'] or '')).encode()).hexdigest(),r['issue_key']))[:25]
assert [r['issue_key'] for r in ordered]==roster['selected_issue_keys']==[r['issue_key'] for r in ids['records']]
assert [r['source_ticker_candidate'] for r in ids['records'][:3]]==['PCAR','ROST','GEHC']
assert ledger['scope_sha256']==hashlib.sha256((P/'exact-materialized-request-manifest.json').read_bytes()).hexdigest()
assert len(ledger['attempts'])==ledger['requests_used']==47 and ledger['complete_entity_bytes']==41548041 and ledger['incomplete_response_reserved_bytes']==0
raw={};adjusted={};action_payloads={};minute_days=[];sgen_minute_count=0;totalbytes=0
for a in ledger['attempts']:
 assert a['http_status']==200 and a['entity_complete'] and a['status'] in ['response_retained','complete_bounded_source_response']
 if a['status']=='response_retained':
  assert a['next_page_token'] and any(z['id']==a['id'] and z['page']==a['page']+1 and z['params']['page_token']==a['next_page_token'] for z in ledger['attempts'])
 b=a['entity'];p=ROOT/b['path'];check(p,b['sha256']);totalbytes+=p.stat().st_size
 if a['id'].startswith('raw_RTH_'):
  payload=load(p);minute_days.append(a['id'].removeprefix('raw_RTH_'));sgen_minute_count+=len(payload.get('bars',{}).get('SGEN',[]));assert payload.get('next_page_token') is None
 elif a['id'] in ['diagnostic_daily_raw','diagnostic_daily_all']:
  dst=raw if a['id']=='diagnostic_daily_raw' else adjusted
  for symbol,records in load(p,True)['bars'].items():dst.setdefault(symbol,[]).extend(records)
 elif a['id']=='diagnostic_alltype_actions':action_payloads[b['sha256']]=load(p,True)
assert all(a['status']=='complete_bounded_source_response' for a in {z['id']:z for z in ledger['attempts']}.values())
assert totalbytes==41548041 and len(minute_days)==40 and minute_days[0]=='2024-01-02' and minute_days[-1]=='2024-02-28' and sgen_minute_count==0
assert sum(map(len,raw.values()))==sum(map(len,adjusted.values()))==15187
assert set(raw)==set(exact['resolved_diagnostic_symbols']) and len(raw)==25
ny=ZoneInfo('America/New_York');dayof=lambda r:datetime.fromisoformat(r['t'].replace('Z','+00:00')).astimezone(ny).date()
assert len(raw['SGEN'])==115 and max(map(dayof,raw['SGEN']))==date(2023,12,13)
# Actual identity points, four projected fields only; no price/quantity decoding.
import pyarrow.parquet as pq
wanted={r['issue_key'].split('|')[0] for r in ids['records']};points=[]
for b in ids['FTD_sources']:
 check(ROOT/b['path'],b['sha256'])
 table=pq.read_table(ROOT/b['path'],columns=['settlement_date','cusip','symbol','description'],use_threads=False)
 points.extend(r for r in table.to_pylist() if r['cusip'] in wanted and r['settlement_date']<date(2024,1,2))
for r in ids['records']:
 candidates=[x for x in points if x['cusip']==r['issue_key'].split('|')[0]];last=max(x['settlement_date'] for x in candidates)
 actual_points=[{**x,'settlement_date':str(x['settlement_date'])} for x in candidates if x['settlement_date']==last]
 assert sorted(actual_points,key=lambda x:json.dumps(x,sort_keys=True))==sorted(r['FTD_dated_points'],key=lambda x:json.dumps(x,sort_keys=True))
 assert r['episode_validity_interval'] is None
sgen=next(r for r in ids['records'] if r['source_ticker_candidate']=='SGEN');assert sgen['FTD_dated_points'][0]['settlement_date']=='2023-12-15'
actions=load(P/'bounded-components/all-actions-and-held-rights.json')['records'];assert len(actions)==180
for a in actions:
 _,_,kind,index=a['pointer'].split('/');source=action_payloads[a['entity']['sha256']]['corporate_actions'][kind][int(index)]
 assert json.loads(json.dumps(source,default=str))==a['record']
 assert a['actual_spendable_at'] is None and a['market_value'] is None
bad=[a for a in actions if a['quarantined_identity_mismatch']];assert len(bad)==1 and bad[0]['record']['symbol']=='ASML' and bad[0]['record']['cusip']=='G3730V147' and bad[0]['issue_links'][0]['expected_cusip']=='N07059210'
sg=next(a for a in actions if a['type']=='cash_mergers');assert sg['record']['acquiree_symbol']=='SGEN' and sg['record']['rate']=='229' and sg['record']['effective_date']=='2023-12-14'
il=next(a for a in actions if a['record'].get('new_symbol')=='GRAL');assert il['record']['source_symbol']=='ILMN' and il['record']['new_rate']=='0.166666667'
assert any(a['record'].get('acquirer_symbol')=='SNPS' for a in actions)
assert any(a['record'].get('new_symbol')=='PANW' for a in actions)
# Independent Decimal60 arithmetic for the three frozen, pre-price-selected observations.
import pandas as pd
from open_composer.market_sessions import us_equity_session_dates
from open_composer.research.features.price_hygiene import sanitize_price_matrices
observed=load(P/'bounded-components/fixed-first-three-price-features.json')['records'];numeric=[]
with localcontext() as ctx:
 ctx.prec=60
 for o in observed:
  symbol=o['symbol'];prefix={dayof(r):r for r in raw[symbol] if dayof(r)<=date(2023,12,29)};dates=us_equity_session_dates(min(prefix),date(2023,12,29))
  assert all(d in prefix for d in dates) and len(dates)==126
  # No effective split within these three July..Dec prefixes and Jan2 decision.
  assert not any(a['type']=='forward_splits' and a['record']['symbol']==symbol and min(dates)<date.fromisoformat(a['record']['ex_date'])<=date(2024,1,2) for a in actions)
  closes=pd.DataFrame({symbol:[float(prefix[d]['c']) for d in dates]},index=pd.DatetimeIndex(dates));opens=pd.DataFrame({symbol:[float(prefix[d]['o']) for d in dates]},index=closes.index)
  clean,_,hygiene=sanitize_price_matrices(closes,opens);assert clean[symbol].notna().all() and hygiene.manifest()==o['hygiene_asof_prefix_only']
  tail=[prefix[d] for d in dates[-20:]];calc={'ADR20':sum(r['h']/r['l']-1 for r in tail)/20,'ADV20':sum(r['c']*r['v'] for r in tail)/20,'momentum21':prefix[dates[-1]]['c']/prefix[dates[-22]]['c']-1}
  for n in [9,21,50]:
   alpha=Decimal(2)/Decimal(n+1);val=prefix[dates[0]]['c'];history=[]
   for day in dates:
    if history:val=alpha*prefix[day]['c']+(1-alpha)*val
    history.append(val)
   calc['EMA'+str(n)]=val
   if n==21:assert (history[-1]>history[-6])==o['rising_EMA21_lag5']
  assert all(Decimal(o[k])==value for k,value in calc.items())
  assert o['numeric_price_gate'] is True and o['full_eligibility'] is None and o['full_rank'] is None
  numeric.append({'symbol':symbol,'decision':'2024-01-02','prior':'2023-12-29','sessions':126,'independently_equal_decimal_fields':list(calc),'hygiene_no_mask':True,'ADR20':str(calc['ADR20'])})
assert not (P/'bounded-components/source-timestamp-coverage.json').exists()
account=load(P/'final-actual-accounting.json');assert account['bridge_CPU_used_cap_remaining_conservative']==[119.98,120,0.02]
u=resource.getrusage(resource.RUSAGE_SELF)
out={'status':'pass','bindings_checked':checks,'source_XML_issues':101,'first_hash_slots':25,'dated_FTD_candidates_checked':25,'source_before_price_evidence':'Market ledger scopeSHA binds exact materialized request manifest, which binds frozen roster and identity candidates; source/identity producer freezes before price intake.','market_entities_checked':47,'market_entity_bytes':41548041,'minute_entities':40,'SGEN_minute_rows_across40':0,'raw_and_all_daily_rows_each':15187,'action_source_pointers_checked':180,'critical_cases':{'SGEN':sg,'ILMN_GRAL':il,'ASML_quarantine':bad[0]},'Decimal60_price_components':numeric,'minute_parent_geometry_or_all1000_features_verified':False,'partial69MB_pointer_index_rehashed_or_accepted':False,'new_source_market_fits_strategyreturns':0,'CPU':u.ru_utime+u.ru_stime,'RSS_KiB':u.ru_maxrss,'affinity':[0]}
(P/'independent-actual-bridge-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ['status','market_entities_checked','market_entity_bytes','dated_FTD_candidates_checked','CPU','RSS_KiB']}))
