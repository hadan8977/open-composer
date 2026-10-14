import json,resource,os,hashlib,zipfile,re,xml.etree.ElementTree as E
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
resource.setrlimit(resource.RLIMIT_CPU,(6,6));os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
import pyarrow.parquet as pq
P=Path('/root/codex-test/open-composer/reports/research/program/day-goal-20261013/hf-factor-return');ROOT=P.parents[4]
def load(p):return json.loads(p.read_text())
qa=load(P/'market-input/cache-bridge/cache-bridge-QA.json');a={}
for y in qa['annual']:
 for r in pq.read_table(y['output']['path'],use_threads=False).to_pylist():
  assert r['timestamp'] not in a;a[r['timestamp']]=r
assert len(a)==32601
NY=ZoneInfo('America/New_York');UTC=ZoneInfo('UTC');wanted=set()
for r in load(P/'funded-SPY-clock-proposed.json')['rows']:
 t=datetime.fromisoformat(r['date']+'T09:30:00').replace(tzinfo=NY)
 wanted.update((t+timedelta(minutes=15*k)).astimezone(UTC) for k in range(r['regular15_windows']))
assert len(wanted)==32602 and not(set(a)-wanted)
assert sorted(t.isoformat() for t in wanted-set(a))==['2019-08-12T19:45:00+00:00']
partial=[{'t':t.isoformat(),'n':r['minute_rows'],'first_age':r['first_price_age_minutes'],'last_age':r['last_price_age_to_window_end_minutes']} for t,r in a.items() if r['minute_rows']<15]
assert len(partial)==10
overlap=0
for receipt in load(P/'market-input/market-request-ledger.json'):
 for r in load(Path(receipt['path']))['bars']['SPY']:
  t=datetime.fromisoformat(r['t'].replace('Z','+00:00'))
  if t in a:
   assert all(r[s]==a[t][d] for s,d in [('o','open'),('h','high'),('l','low'),('c','close'),('v','volume')]);overlap+=1
assert overlap==5096
actions=load(P/'market-input/cache-bridge/SPY-BIL-bound-actions.json')
wp=Path('/root/codex-test/open-composer')/actions['issuer_source']['path']
assert hashlib.sha256(wp.read_bytes()).hexdigest()==actions['issuer_source']['sha256']
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(wp) as z:
 strings=[''.join(e.itertext()) for e in E.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)]
 rows={int(r.get('r')):r for r in E.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//m:row',ns)}
counts={'SPY':0,'BIL':0}
for r in actions['actions']:
 if r['type']!='cash_dividends':
  assert r['symbol']=='BIL' and r['ratio']==.5 and r['ex_date']=='2017-11-30' and r['fractional_cash_in_lieu_quote_and_date'] is None
  continue
 counts[r['symbol']]+=1; vals={}
 for c in rows[r['issuer_row']].findall('m:c',ns):
  v=c.find('m:v',ns);s='' if v is None else v.text
  vals[re.sub(r'\d','',c.get('r'))]=strings[int(s)] if s and c.get('t')=='s' else s
 assert vals==r['raw_cells'] and float(vals['G'])==r['issuer_income']
 for cell,field in [('D','ex_date'),('E','record_date'),('F','payable_date')]:assert datetime.strptime(vals[cell].strip(),'%m/%d/%Y').date().isoformat()==r[field]
 assert r['amount']==(r['provider_row']['rate'] if r['provider_row'] is not None else r['issuer_income'])
assert counts=={'SPY':20,'BIL':60}
daily=load(P/'market-input/cache-bridge/raw-daily-closing-reconciliation.json')
assert len(daily)==1259 and all(r['daily_raw_present'] for r in daily)
assert [r['date'] for r in daily if not r['closing15_present']]==['2019-08-12']
out={'status':'ok','scope':'Read accepted aggregate outputs/native overlap and issuer actual cells; preceding capped process checked all361 hashes and reaggregated2016/2017, did not complete raw2018-2020 independent replay. Author full100 raw/normalized QA and inspected code retained.','aggregate_windows':len(a),'expected_windows':len(wanted),'partial_windows':partial,'exact_native_overlap':overlap,'actual_issuer_rows_reparsed':counts,'daily_mark_presence_report_checked':1259,'new_economic_runs':0,'CPU_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
(P/'independent-cache-bridge-compact-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
