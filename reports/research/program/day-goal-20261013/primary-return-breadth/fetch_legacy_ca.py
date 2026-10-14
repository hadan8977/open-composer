"""Bounded documented issuer-announcement reads via existing native factory.

This queries historical issuer metadata only; no account, order or position API.
It does not infer a missing payable date, and stops on the first empty/failed path.
"""
from pathlib import Path
from datetime import datetime,UTC,timedelta
import json,hashlib
from open_composer.cli import _load_env
from open_composer.adapters.broker.alpaca_paper import _trading_client
from alpaca.trading.requests import GetCorporateAnnouncementsRequest

P=Path(__file__).parent;I=P/'inputs';lp=I/'market-request-ledger.json'
review=json.loads((P/'independent-plan-review.json').read_text());assert review['verdict']=='approve_deep_plan'
rows=json.loads((I/'actions-01.json').read_text())['corporate_actions']['cash_dividends']
missing=[r for r in rows if r['symbol']=='SSO' and not r.get('payable_date')]
ledger=json.loads(lp.read_text());_load_env();client=_trading_client();client._retry=0
native_request=client._session.request
def capture(method,url,**kwargs):
    assert method.upper()=='GET' and '/corporate_actions/announcements' in url
    assert len(ledger)<24 and sum(r.get('bytes',0) for r in ledger)<16777216
    row={'name':'legacy_SSO_issuer_announcements','request_path':url,'params':kwargs.get('params'), 'requested_at':datetime.now(UTC).isoformat(),'classification':'read_only_historical_issuer_metadata;no_account_order_position_access','attempt':1,'retry':False}
    ledger.append(row);lp.write_text(json.dumps(ledger,indent=2)+'\n')
    response=native_request(method,url,**kwargs);body=response.content
    f=I/f'legacy-ca-{len(ledger):02d}.json';f.write_bytes(body)
    row.update(path=str(f),status=response.status_code,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),received_at=datetime.now(UTC).isoformat())
    lp.write_text(json.dumps(ledger,indent=2)+'\n');assert sum(r.get('bytes',0) for r in ledger)<=16777216
    print('historical_reference',response.status_code,len(body),flush=True)
    return response
client._session.request=capture
try:
    for old in missing:
        day=datetime.fromisoformat(old['ex_date']).date()
        try:
            result=client.get_corporate_announcements(GetCorporateAnnouncementsRequest(ca_types=['dividend'],since=day-timedelta(days=7),until=day+timedelta(days=7),symbol='SSO',date_type='ex_date'))
        except Exception as e:
            print('documented_reference_path_stop',type(e).__name__,flush=True);break
        verified=[r for r in result if str(r.ex_date)==old['ex_date'] and r.payable_date is not None and abs(float(r.cash)-old['rate'])<1e-7]
        if not verified:
            print('documented_reference_path_no_verified_paydate',old['ex_date'],flush=True);break
        print('verified_source_field',old['ex_date'],str(verified[0].payable_date),flush=True)
finally:
    client._session.close()
    state=json.loads((P/'current-state.json').read_text());state.update(new_market_requests=len(ledger),new_market_bytes=sum(x.get('bytes',0) for x in ledger),new_source_request_units_used=40,new_orders=0,broker_account_order_position_requests=0,updated_at_utc=datetime.now(UTC).isoformat());(P/'current-state.json').write_text(json.dumps(state,indent=2)+'\n')
