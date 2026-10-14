"""Exact token continuation of a fixed existing news window, plus unused SEC date."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[5]
P = Path(__file__).resolve().parents[1]
FIRST = P / 'current-source-intake'
OUT = P / 'current-source-continuation'
sys.path.insert(0, str(ROOT / 'scripts'))
import build_sec_xbrl_fundamentals as sec
from open_composer.cli import _load_env
from open_composer.research.news import collector as news


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    target = OUT / 'ledger.json'
    assert not target.exists(), 'consumed continuation ledger'
    parent = json.loads((FIRST / 'ledger.json').read_text())
    last = [r for r in parent['requests'] if r['label'].startswith('news-')][-1]
    assert last['http_status'] == 200 and last['complete']
    bodypath = Path(last['entity_path'])
    assert sha(bodypath) == last['entity_sha256']
    token = json.loads(bodypath.read_text()).get('next_page_token')
    assert isinstance(token,str) and token
    ledger = {'parent_ledger_sha256':sha(FIRST/'ledger.json'),'last_news_entity_sha256':last['entity_sha256'],'max_requests':162,'max_entity_bytes':67108864,'entity_bytes':0,'requests':[],'broker_writes':0,'request_header_values_recorded':False,'wire_bytes':None}
    def save(): target.write_text(json.dumps(ledger,indent=2)+'\n')
    def fetch(client,label,url,params=None):
        assert len(ledger['requests']) < ledger['max_requests']
        row = {'label':label,'url':url,'params':params,'attempted_at':datetime.now(UTC).isoformat(),'status':'attempted_unknown'}
        ledger['requests'].append(row);save()
        try:
            client._throttle() if hasattr(client,'_throttle') else news._rate_limit_wait()
            raw = getattr(client,'_client',client)
            with raw.stream('GET',url,params=params,follow_redirects=False,timeout=60) as response:
                row['http_status']=response.status_code
                row['response_metadata']={k:response.headers[k] for k in ('date','content-type','last-modified') if k in response.headers}
                body = bytearray();complete=True
                for chunk in response.iter_bytes(65536):
                    body.extend(chunk)
                    if len(body)>2097152 or ledger['entity_bytes']+len(body)>ledger['max_entity_bytes']:
                        complete=False;break
            path=OUT/(label+'.body');path.write_bytes(body)
            row.update(entity_path=str(path),entity_sha256=hashlib.sha256(body).hexdigest(),entity_bytes=len(body),complete=complete,status='complete_response' if complete else 'incomplete_entity_cap')
            ledger['entity_bytes']+=len(body);save()
            return bytes(body) if complete and row['http_status']==200 else None
        except Exception as error:
            row.update(status='transport_failed_unknown_wire',error_type=type(error).__name__);save();return None
    save();_load_env()
    try:client=sec.SecClient()
    except Exception as error:
        ledger['sec_local_error_type']=type(error).__name__;save()
    else:
        try:
            # No retry of the retained Oct12 403. Oct7 is needed before the cache frontier;
            # Oct13 was in the original fixed window but not attempted after strict stop.
            for stamp in ('20261007','20261013'):
                payload=fetch(client,'sec-index-'+stamp,f'https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/form.{stamp}.idx')
                if payload is None:break
        finally:client.close()
    tokens={token}
    with httpx.Client(headers=news._headers()) as client:
        for i in range(160):
            params={**last['params'],'page_token':token}
            payload=fetch(client,f'news-{i+32:03d}',news.ALPACA_NEWS_URL,params)
            if payload is None:break
            data=json.loads(payload);token=data.get('next_page_token')
            if not token:
                ledger['news_complete_window']=True;save();break
            if not isinstance(token,str) or token in tokens:
                ledger['news_stop']='invalid_or_repeated_token';save();break
            tokens.add(token)
    ledger['finished_at']=datetime.now(UTC).isoformat();save()
    print(json.dumps({'requests':len(ledger['requests']),'bytes':ledger['entity_bytes'],'news_complete_window':ledger.get('news_complete_window',False),'SEC_statuses':[(r['label'],r.get('http_status')) for r in ledger['requests'] if r['label'].startswith('sec-')]}),flush=True)


if __name__=='__main__':main()
