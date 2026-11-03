from pathlib import Path
import json
from decimal import Decimal as D
from collections import defaultdict
from datetime import datetime, UTC
b=Path(__file__).resolve().parents[2]/'reports/owner/paper-recovery-20261103'
marks={}
for p in (b/'evidence/market').glob('raw-*.json'):
 if '.receipt.' in p.name: continue
 for s,rows in json.loads(p.read_text())['bars'].items():
  for r in rows:
   key=(s,r['t'][:10]); value=D(str(r['c']))
   assert key not in marks or marks[key]==value
   marks[key]=value
result={}
for name in ['legacy','six']:
 activities=json.loads((b/'evidence'/name/'activities-all-v2.json').read_text())
 assert len({r['id'] for r in activities})==len(activities)
 cash=D(0); quantities=defaultdict(D); fees=D(0); dividends=D(0)
 for r in activities:
  day=(r.get('transaction_time') or r['date'])[:10]
  assert day<='2026-11-02'
  if r['activity_type']=='FILL':
   sign=1 if r['side']=='buy' else -1
   assert r['side'] in ['buy','sell']
   qty=D(r['qty'])*sign;quantities[r['symbol']]+=qty;cash-=qty*D(r['price'])
  else:
   cash+=D(r['net_amount'])
   if day>='2026-10-01' and r['activity_type']=='FEE':fees-=D(r['net_amount'])
   if day>='2026-10-01' and r['activity_type']=='DIV':dividends+=D(r['net_amount'])
 quantities={s:q for s,q in quantities.items() if q}
 broker_positions={r['symbol']:D(r['qty']) for r in json.loads((b/'evidence'/name/'positions.json').read_text())}
 assert quantities==broker_positions
 position_value=sum(q*marks[s,'2026-11-02'] for s,q in quantities.items())
 equity=cash+position_value
 expected=D('103318.64' if name=='legacy' else '998167.48')
 assert equity==expected,(name,equity,expected)
 account=json.loads((b/'evidence'/name/'account.json').read_text())
 assert cash==D(account['cash'])
 result[name]={'all_activity_count':len(activities),'positions_match_broker':True,'cash_rebuilt_from_all_activities':str(cash),'position_value_at_Nov02_close':str(position_value),'account_close_equity':str(equity),'residual_usd':str(equity-expected),'October_onward_fees':str(fees),'October_onward_dividends':str(dividends)}
report=json.loads((b/'performance.json').read_text())
assert sum(D(r['profit_before_unattributed_costs_usd']) for r in report['actual_strategies'] if r['id'].startswith('six/'))==D('-1831.50')
assert D('-1831.50')-D(result['six']['October_onward_fees'])==D('-1832.52')
result['checked_at']=datetime.now(UTC).isoformat();result['method']='Independent root reconstruction from raw broker activities and raw price bodies; no reuse of worker account calculation functions; no HTTP or broker writes'
(b/'independent-raw-reconciliation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
