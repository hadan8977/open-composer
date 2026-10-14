import json,hashlib,pathlib,zipfile,xml.etree.ElementTree as ET,datetime,sys,resource
p=pathlib.Path('reports/research/program/day-goal-20261013/primary-return-breadth'); out={};load=lambda n:json.loads((p/n).read_text())
m=load('implementation-manifest.json');assert hashlib.sha256((p/'implementation-manifest.json').read_bytes()).hexdigest()=='1f519c97ce594e90bb294aa049b68632a7b48914a67e4a60636b0d16fb372245'
for r in m['files']:
 b=pathlib.Path(r['path']).read_bytes();assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],r['path']
out['manifest_files_verified']=len(m['files'])
N={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile('reports/research/program/day-goal-20261011/root-source-support/ssga-historical-distributions.xlsx') as z:
 strings=[''.join(v.itertext())for v in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',N)]
 rows=ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//m:row',N)
wb={}
for row in rows:
 cells={}
 for c in row.findall('m:c',N):
  v=c.find('m:v',N);t=v.text if v is not None else ''; cells[''.join(k for k in c.attrib['r']if k.isalpha())]=strings[int(t)]if t and c.get('t')=='s'else t
 wb[int(row.attrib['r'])]=cells
norm=load('inputs/normalized-actions.json');cash=load('inputs/actions-01.json')['corporate_actions']['cash_dividends'];byid={x['id']:x for x in cash};count=0
for a in norm['actions']:
 if a['type']!='cash_dividends':continue
 rownum=a.get('issuer_row',a.get('source_excel_row'))
 if rownum is not None:
  r=wb[rownum];iso=lambda v:datetime.datetime.strptime(v.strip(),'%m/%d/%Y').date().isoformat()
  assert a['symbol']==r['B'] and a['ex_date']==iso(r['D']) and a['record_date']==iso(r['E']) and a['payable_date']==iso(r['F']) and abs(a['amount']-float(r['G']))<=.500001e-6
  count+=1
 elif a['symbol']=='SSO':
  raw=byid[a['id']];assert a['amount']==raw['rate']and a['payable_date']==raw.get('payable_date')
 if a['ex_date']>='2020-01-02':assert a['payable_date']>=a['ex_date']
assert len(norm['repairs'])==52 and len(norm['added_source_actions'])==2
assert [(a['symbol'],a['ex_date'])for a in norm['added_source_actions']]==[('SPY','2026-09-18'),('SPY','2018-06-15')] or set((a['symbol'],a['ex_date'])for a in norm['added_source_actions'])=={('SPY','2026-09-18'),('SPY','2018-06-15')}
out['issuer_rows_independently_matched']=count;out['payable_repairs']=52;out['added_distributions']=norm['added_source_actions'];out['unresolved_pre2020_book_actions']=len(norm['unresolved_payable'])
audit=load('inputs/action-completeness.json');segments=0;transitions=0;warnings=[]
raw=load('inputs/bars_raw-01.json')['bars'];adj=load('inputs/bars_all-01.json')['bars'];actions=norm['actions']
for sym in ['SPY','SSO','BIL']:
 chain=audit[sym]['full2020_cent_interval_actionchain'];segments+=len(chain['segments']);transitions+=len(chain['transitions'])
 rawby={r['t'][:10]:r['c']for r in raw[sym]};adjby={r['t'][:10]:r['c']for r in adj[sym]};dates=sorted(rawby)
 for seg in chain['segments']:
  ds=[d for d in dates if seg['start']<=d<=seg['end']];lo=max((adjby[d]-.005)/rawby[d]for d in ds);hi=min((adjby[d]+.005)/rawby[d]for d in ds)
  assert abs(lo-seg['lower'])<1e-12 and abs(hi-seg['upper'])<1e-12 and lo<=hi+1e-12
 for i,tr in enumerate(chain['transitions'],1):
  day=tr['date'];ev=[a for a in actions if a['symbol']==sym and a['ex_date']==day];sp=1
  for a in ev:
   if a['type']!='cash_dividends':sp*=a['ratio']
  div=sum(a['amount']for a in ev if a['type']=='cash_dividends');prior=rawby[dates[dates.index(day)-1]];formula=sorted([sp*prior/(prior-sp*div),sp*(1+div/rawby[day])]);assert all(abs(a-b)<1e-12 for a,b in zip(formula,tr['two_physical_convention_range']))
  if not tr['passes']:warnings.append({'symbol':sym,**tr})
assert segments==111 and transitions==108 and len(warnings)==1 and warnings[0]['date']=='2026-03-20'
out.update(action_free_segments_checked=segments,known_transitions_checked=transitions,known_transition_warnings=warnings)
# Quotes are checked only for entity clocks, never interpreted as fills.
quote_rows=0
for r in load('inputs/market-request-ledger.json'):
 if not r['name'].startswith('quote_'):continue
 payload=json.loads(pathlib.Path(r['path']).read_text());start=r['params']['start'];end=r['params']['end'];conv=lambda s:datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
 for qs in payload['quotes'].values():
  for q in qs:assert conv(start)<=conv(q['t'])<=conv(end);quote_rows+=1
out['quote_rows_in_requested_clock']=quote_rows
# Independent synthetic bookkeeping cases; no actual market return calculation.
sys.path.insert(0,str(p.resolve()));sys.path.insert(0,str(pathlib.Path.cwd()))
import pandas as pd
from evaluator import simulate
ix=pd.bdate_range('2026-09-28',periods=6);price=pd.Series([100,100,99,99,99,99],index=ix,dtype=float)
a=[{'id':'div','type':'cash_dividends','ex_date':'2026-09-30','payable_date':'2026-10-01','amount':1}]
f,o,e,d=simulate(price,price,pd.Series([1,0,0,0,0,0],index=ix),a,capital=1000,cost=0)
assert f.iloc[2].shares==0 and f.iloc[2].dividend_receivable==9 and f.iloc[2].unavailable_sales_credit==891 and all(abs(f.nav-1000)<1e-9)
assert f.iloc[4].proxy_available_cash==1000 and f.iloc[4].dividend_receivable==0
# Missing open retains prior holdings; retry sale later, never drops a session.
op=price.copy();op.iloc[2]=float('nan');g,orders,ev,det=simulate(price,op,pd.Series([1,0,0,0,0,0],index=ix),a,capital=1000,cost=0)
assert len(g)==6 and g.iloc[2].shares==9 and orders[1]['accepted']is False and orders[2]['accepted']is True
# A4k book uses its own integer lots; it is not 0.2 times a20k position.
flat=pd.Series([333.0]*6,index=ix);target=pd.Series(True,index=ix)
b4=simulate(flat,flat,target,[],capital=4000,cost=.002)[0];b20=simulate(flat,flat,target,[],capital=20000,cost=.002)[0];assert b4.iloc[1].shares!=.2*b20.iloc[1].shares
out['independent_synthetic_checks']=['ex_date_sale_retains_entitlement_and_NAV','actual_payable_proxy_cash_transfer','missing_open_keeps_held_position_and_calendar','independent4k_integer_rounding']
out['economic_evaluations']=0;out['review_process_coreseconds']=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime
pathlib.Path('/tmp/breadth_impl_check_result.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
