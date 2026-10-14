"""Existing-source, private, bounded current-window intake. No broker writes."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parents[1] / 'current-source-intake'
sys.path.insert(0, str(ROOT / 'scripts'))
import build_sec_xbrl_fundamentals as sec
import collect_finra_short_interest as si
import collect_finra_short_volume as sv
from open_composer.cli import _load_env
from open_composer.research.news import collector as news


def main():
    OUT.mkdir(exist_ok=True)
    ledger_path = OUT / 'ledger.json'
    if ledger_path.exists():
        raise RuntimeError('consumed source ledger; never restart this entry')
    ledger = {'requests': [], 'max_requests': 47, 'max_entity_bytes': 67108864, 'entity_bytes': 0, 'credential_or_identity_headers_recorded': False, 'wire_bytes': None, 'broker_writes': 0}
    def save():
        ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
    def fetch(client, label, method, url, *, params=None, body=None):
        assert len(ledger['requests']) < ledger['max_requests']
        row = {'ordinal': len(ledger['requests']), 'label': label, 'method': method, 'url': url, 'params': params, 'json': body, 'status': 'attempted_unknown', 'attempted_at': datetime.now(UTC).isoformat()}
        ledger['requests'].append(row); save()
        try:
            client._throttle() if hasattr(client, '_throttle') else news._rate_limit_wait()
            rawclient = getattr(client, '_client', client)
            with rawclient.stream(method, url, params=params, json=body, follow_redirects=False, timeout=60) as response:
                row.update(http_status=response.status_code, response_metadata={k: response.headers[k] for k in ('date','content-type','last-modified','record-total') if k in response.headers})
                payload = bytearray()
                complete = True
                for chunk in response.iter_bytes(65536):
                    payload.extend(chunk)
                    if len(payload) > 2097152 or ledger['entity_bytes'] + len(payload) > ledger['max_entity_bytes']:
                        complete = False
                        break
            path = OUT / (label + '.body')
            path.write_bytes(payload)
            row.update(entity_path=str(path), entity_bytes=len(payload), entity_sha256=hashlib.sha256(payload).hexdigest(), complete=complete, status='complete_response' if complete else 'incomplete_entity_cap')
            ledger['entity_bytes'] += len(payload); save()
            return bytes(payload) if complete and row['http_status'] == 200 else None, row
        except Exception as error:
            row.update(status='transport_failed_unknown_wire', error_type=type(error).__name__)
            save()
            return None, row
    save()
    _load_env()
    try:
        client = sec.SecClient()
    except Exception as error:
        ledger['sec_local_configuration'] = {'status': 'not_constructed', 'error_type': type(error).__name__}; save()
    else:
        try:
            for stamp in ('20261008','20261009','20261012','20261013'):
                _, row = fetch(client, 'sec-index-' + stamp, 'GET', f'https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/form.{stamp}.idx')
                if row.get('http_status') in (401,403,429) or row.get('complete') is not True:
                    break
        finally:
            client.close()
    client = sv.FinraCdnClient()
    try:
        for stamp in ('20261008','20261009','20261012','20261013'):
            _, row = fetch(client, 'finra-volume-' + stamp, 'GET', f'https://cdn.finra.org/equity/regsho/daily/CNMSshvol{stamp}.txt')
            if row.get('http_status') in (401,429) or row.get('complete') is not True:
                break
    finally:
        client.close()
    client = si.FinraClient()
    try:
        base = {'dateRangeFilters':[{'fieldName':'settlementDate','startDate':'2026-09-30','endDate':'2026-09-30'}]}
        body, row = fetch(client, 'finra-interest-probe', 'POST', si.DATA_URL, body={**base,'limit':1,'offset':0})
        if body is not None:
            total = int(row['response_metadata'].get('record-total', 0))
            ledger['finra_interest_expected_records'] = total; save()
            for i in range(min(6, (total + 4999) // 5000)):
                _, row = fetch(client, f'finra-interest-{i:02d}', 'POST', si.DATA_URL, body={**base,'limit':5000,'offset':i * 5000})
                if row.get('http_status') != 200 or row.get('complete') is not True:
                    break
    finally:
        client.close()
    try:
        headers = news._headers()
    except Exception as error:
        ledger['news_local_configuration'] = {'status':'not_constructed','error_type':type(error).__name__}; save()
    else:
        with httpx.Client(headers=headers) as client:
            token = None
            for i in range(32):
                params = {'start':'2026-10-08T00:00:00+00:00','end':'2026-10-14T00:00:00+00:00','limit':news.PAGE_LIMIT,'sort':'asc','include_content':False}
                if token: params['page_token'] = token
                body, row = fetch(client, f'news-{i:02d}', 'GET', news.ALPACA_NEWS_URL, params=params)
                if body is None:
                    break
                data = json.loads(body)
                token = data.get('next_page_token')
                row['next_page_token_present'] = bool(token); save()
                if not token:
                    ledger['news_complete_window'] = True; save(); break
    ledger['finished_at'] = datetime.now(UTC).isoformat(); save()
    print(json.dumps({'requests':len(ledger['requests']),'entity_bytes':ledger['entity_bytes'],'statuses':[(r['label'],r.get('http_status'),r['status']) for r in ledger['requests']]}), flush=True)


if __name__ == '__main__':
    main()
