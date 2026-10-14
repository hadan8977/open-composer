"""Unused exact tail requests; independently closed XML components are explicit."""
import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT))
from open_composer.cli import _load_env
spec = importlib.util.spec_from_file_location('insider_collector', WT / 'scripts/collect_sec_insider_transactions.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def main():
    manifest = json.loads((P / 'current-insider-request-manifest.json').read_text())
    parent = P / 'current-insider-tail-recovery'
    prior = json.loads((parent / 'ledger.json').read_text())
    consumed = len(prior['requests'])
    assert consumed == 45 and prior['requests'][-1]['http_status'] == 200
    out = P / 'current-insider-tail-continuation'
    out.mkdir(exist_ok=True)
    target = out / 'ledger.json'
    assert not target.exists(), 'consumed continuation'
    scope = {'parent_sha256': hashlib.sha256((parent / 'ledger.json').read_bytes()).hexdigest(), 'requests': manifest['requests'][consumed:], 'max_requests': manifest['max_requests'] - consumed, 'partial_entity_rule': 'retain capped prefix; use only independently closed valid ownershipDocument with offsets/SHA; never label entire HTTP entity complete; no retries or redirects', 'all_original_request_cap': manifest['max_requests']}
    (P / 'current-insider-continuation-request-manifest.json').write_text(json.dumps(scope, indent=2) + '\n')
    ledger = {'parent_sha256': scope['parent_sha256'], 'requests': [], 'entity_bytes': 0, 'wire_bytes': None, 'identity_headers_recorded': False, 'broker_writes': 0}
    def save():
        target.write_text(json.dumps(ledger, indent=2) + '\n')
    frames = {}
    def parse(row, payload):
        document = m.extract_ownership_document(payload)
        row['ownership_document_found'] = document is not None
        if document is None:
            return
        offset = payload.find(document)
        row['component'] = {'start_offset': offset, 'end_offset': offset + len(document), 'bytes': len(document), 'sha256': hashlib.sha256(document).hexdigest(), 'entity_complete': row['complete']}
        index = row['source_index_record']
        frame = m.parse_form4_xml(document, accession=Path(index['file_name']).stem, source_dataset='tail:' + index['filed'])
        row['transaction_rows'] = len(frame)
        if not frame.empty:
            frame['filing_date'] = pd.to_datetime(index['filed'], format='%Y%m%d')
            frames.setdefault(index['filed'], []).append(frame)
    # The original incomplete response contains a complete 3059-byte ownership XML.
    last = prior['requests'][-1]
    body = Path(last['entity_path']).read_bytes()
    assert hashlib.sha256(body).hexdigest() == last['entity_sha256']
    component = {k: last[k] for k in ('source_index_record', 'complete', 'entity_path', 'entity_sha256')}
    parse(component, body)
    assert component['ownership_document_found']
    ledger['retained_parent_component'] = component
    save()
    old_root = os.environ.get('OPEN_COMPOSER_ROOT')
    os.environ['OPEN_COMPOSER_ROOT'] = str(ROOT)
    try:
        _load_env()
    finally:
        if old_root is None:
            os.environ.pop('OPEN_COMPOSER_ROOT', None)
        else:
            os.environ['OPEN_COMPOSER_ROOT'] = old_root
    client = m.SecClient()
    try:
        for i, request in enumerate(scope['requests']):
            row = {'original_ordinal': consumed + i, 'url': request['url'], 'source_index_record': request['source_index_record'], 'status': 'attempted_unknown', 'started_at': datetime.now(UTC).isoformat()}
            ledger['requests'].append(row)
            save()
            payload = bytearray()
            try:
                wait = client._min_interval - (time.monotonic() - client._last_request)
                if wait > 0:
                    time.sleep(wait)
                client._last_request = time.monotonic()
                complete = True
                with client._client.stream('GET', request['url'], follow_redirects=False, timeout=45) as response:
                    row['http_status'] = response.status_code
                    row['response_metadata'] = {k: response.headers[k] for k in ('date', 'content-type', 'last-modified') if k in response.headers}
                    for chunk in response.iter_bytes(16384):
                        allowed = request['max_entity_bytes'] - len(payload)
                        payload.extend(chunk[:allowed])
                        if len(chunk) > allowed:
                            complete = False
                            break
                path = out / f'{consumed + i:04d}.body'
                path.write_bytes(payload)
                ledger['entity_bytes'] += len(payload)
                row.update(status='complete_response' if complete else 'retained_partial_entity', complete=complete, entity_path=str(path), entity_bytes=len(payload), entity_sha256=hashlib.sha256(payload).hexdigest())
                if row['http_status'] == 200:
                    parse(row, bytes(payload))
                save()
                if row['http_status'] in (401, 403, 429) or row['http_status'] >= 500 or 300 <= row['http_status'] < 400:
                    ledger['stop'] = {'original_ordinal': consumed + i, 'http_status': row['http_status']}
                    save()
                    break
            except Exception as error:
                row.update(status='failed_unknown_wire', error_type=type(error).__name__)
                save()
                break
            if (i + 1) % 100 == 0:
                print(f'new tail components {i + 1}/{len(scope["requests"])}', flush=True)
    finally:
        client.close()
    parsed = out / 'parsed'
    parsed.mkdir(exist_ok=True)
    for old in (parent / 'parsed').glob('*.parquet'):
        frames.setdefault(old.stem, []).insert(0, pd.read_parquet(old))
    for stamp, parts in frames.items():
        pd.concat(parts, ignore_index=True).to_parquet(parsed / f'{stamp}.parquet', index=False, compression='zstd')
    ledger['all_original_requests_attempted'] = consumed + len(ledger['requests']) == manifest['max_requests']
    ledger['ownership_component_missing_ordinals'] = [r['original_ordinal'] for r in ledger['requests'] if not r.get('ownership_document_found')]
    ledger['completed_at'] = datetime.now(UTC).isoformat()
    save()
    print({'requests': len(ledger['requests']), 'entity_bytes': ledger['entity_bytes'], 'all_attempted': ledger['all_original_requests_attempted'], 'missing_components': len(ledger['ownership_component_missing_ordinals'])}, flush=True)


if __name__ == '__main__':
    main()
