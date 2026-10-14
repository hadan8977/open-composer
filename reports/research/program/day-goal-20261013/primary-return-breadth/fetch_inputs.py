"""Reviewed bounded read-only inputs; no signals, returns, or broker operations."""
from pathlib import Path
from datetime import datetime, UTC
import hashlib, json
from open_composer.adapters.data.alpaca_snapshot import _stock_data_client
from open_composer.cli import _load_env

P = Path(__file__).parent
I = P/'inputs'
I.mkdir(exist_ok=True)
plan = P/'scientific-plan.json'
review = json.loads((P/'independent-plan-review.json').read_text())
bindings = review.get('bindings', {})
bindings = list(bindings.values()) if isinstance(bindings, dict) else bindings
assert review['verdict']=='approve_deep_plan'
assert review['author']!=review['reviewer']
assert any(Path(b['path']).resolve()==plan.resolve() and b['sha256']==hashlib.sha256(plan.read_bytes()).hexdigest() for b in bindings)
ledger_path = I/'market-request-ledger.json'
ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
_load_env()  # application's normal configuration loader; no credential text access/output
client = _stock_data_client()

def fetch(name, path, data):
    results = []
    page = 0
    while True:
        page += 1
        file = I/f'{name}-{page:02d}.json'
        prior = next((x for x in ledger if x.get('path')==str(file) and x.get('status')==200),None)
        if prior is not None:
            assert hashlib.sha256(file.read_bytes()).hexdigest()==prior['sha256']
            result = json.loads(file.read_bytes())
        else:
            assert len(ledger)<24 and sum(x.get('bytes',0) for x in ledger)<16777216
            row = {'name':name,'request_path':path,'params':dict(data),'attempt':1,'retry':False,'requested_at':datetime.now(UTC).isoformat(),'path':str(file)}
            ledger.append(row)
            ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
            try:
                response = client.get_raw(path=path,data=data,headers={'Accept':'application/json'})
                body = response.entity_bytes
                file.write_bytes(body)
                row.update(status=response.status_code,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),received_at=datetime.now(UTC).isoformat(),response_headers={k:v for k,v in response.headers.items() if k.lower() in {'date','content-type','x-request-id'}})
                ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
                assert sum(x.get('bytes',0) for x in ledger)<=16777216,'received source exceeds admitted cap; retain and stop'
                assert response.status_code==200,f'{name}:HTTP {response.status_code}; failure retained, no automatic retry'
                result=json.loads(body)
            except Exception as e:
                row['error_type']=type(e).__name__
                ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
                raise
        results.append(result)
        token=result.get('next_page_token')
        print(name,page,'status',200,'bytes',file.stat().st_size,'more',bool(token),flush=True)
        if not token:
            break
        data=dict(data,page_token=token)
    return results

try:
    # Actions first: a missing cash ledger is a specific failure, not inferred paydates.
    fetch('actions','https://data.alpaca.markets/v1/corporate-actions',{'symbols':'SPY,SSO,BIL','start':'2014-01-01','end':'2026-10-13','limit':1000,'sort':'asc'})
    for adjustment in ['raw','all']:
        fetch('bars_'+adjustment,'/stocks/bars',{'symbols':'SPY,SSO,BIL','timeframe':'1Day','start':'2015-01-01T05:00:00Z','end':'2026-10-13T04:00:00Z','adjustment':adjustment,'feed':'sip','limit':10000,'sort':'asc','asof':'-'})
    for d in ['2020-03-16','2022-06-13','2025-04-07','2026-09-30']:
        fetch('quote_'+d,'/stocks/quotes',{'symbols':'SPY,SSO,BIL','start':d+'T13:30:00Z','end':d+'T13:30:05Z','feed':'sip','limit':10000,'sort':'asc','asof':'-'})
finally:
    client.close()
    state=json.loads((P/'current-state.json').read_text())
    state.update(new_market_requests=len(ledger),new_market_bytes=sum(x.get('bytes',0) for x in ledger),actual_input_http_process='completed_or_failed_readonly_capture',updated_at_utc=datetime.now(UTC).isoformat())
    (P/'current-state.json').write_text(json.dumps(state,indent=2)+'\n')
