"""Single-request exact Form4 submissions via the normal SEC client; no retry."""
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
    manifest_path = P / 'current-insider-request-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    out = P / 'current-insider-tail-recovery'
    out.mkdir(exist_ok=True)
    ledger_path = out / 'ledger.json'
    assert not ledger_path.exists(), 'consumed ledger; do not restart or erase'
    ledger = {'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(), 'requests': [], 'entity_bytes': 0, 'wire_bytes': None, 'identity_headers_recorded': False, 'broker_writes': 0, 'authorization': 'task.json necessary exact existing scheduled-provider intake; no paid access/new provider'}
    def save():
        ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
    save()
    previous_root = os.environ.get('OPEN_COMPOSER_ROOT')
    os.environ['OPEN_COMPOSER_ROOT'] = str(ROOT)
    try:
        _load_env()
    finally:
        if previous_root is None:
            os.environ.pop('OPEN_COMPOSER_ROOT', None)
        else:
            os.environ['OPEN_COMPOSER_ROOT'] = previous_root
    try:
        client = m.SecClient()
    except Exception as error:
        ledger['configuration_stop'] = type(error).__name__
        save()
        return
    frames = {}
    try:
        for i, request in enumerate(manifest['requests']):
            assert len(ledger['requests']) < manifest['max_requests']
            row = {'ordinal': i, 'url': request['url'], 'source_index_record': request['source_index_record'], 'status': 'attempted_unknown', 'started_at': datetime.now(UTC).isoformat()}
            ledger['requests'].append(row)
            save()
            payload = bytearray()
            try:
                elapsed = time.monotonic() - client._last_request
                if elapsed < client._min_interval:
                    time.sleep(client._min_interval - elapsed)
                client._last_request = time.monotonic()
                complete = True
                with client._client.stream('GET', request['url'], follow_redirects=False, timeout=45) as response:
                    row['http_status'] = response.status_code
                    row['response_metadata'] = {k: response.headers[k] for k in ('date', 'content-type', 'last-modified') if k in response.headers}
                    for chunk in response.iter_bytes(16384):
                        payload.extend(chunk)
                        if len(payload) > request['max_entity_bytes'] or ledger['entity_bytes'] + len(payload) > manifest['max_total_entity_bytes']:
                            complete = False
                            break
                path = out / f'{i:04d}.body'
                path.write_bytes(payload)
                ledger['entity_bytes'] += len(payload)
                row.update(status='complete_response' if complete else 'incomplete_entity_cap', complete=complete, entity_path=str(path), entity_bytes=len(payload), entity_sha256=hashlib.sha256(payload).hexdigest())
                if complete and row['http_status'] == 200:
                    document = m.extract_ownership_document(bytes(payload))
                    row['ownership_document_found'] = document is not None
                    if document is not None:
                        index = request['source_index_record']
                        stamp = index['filed']
                        frame = m.parse_form4_xml(document, accession=Path(index['file_name']).stem, source_dataset='tail:' + stamp)
                        if not frame.empty:
                            frame['filing_date'] = pd.to_datetime(index['filed'], format='%Y%m%d')
                            frames.setdefault(stamp, []).append(frame)
                        row['transaction_rows'] = len(frame)
                save()
                if not complete or row['http_status'] in (401, 403, 429) or row['http_status'] >= 500 or 300 <= row['http_status'] < 400:
                    ledger['stop'] = {'ordinal': i, 'reason': row['status'], 'http_status': row['http_status']}
                    save()
                    break
            except Exception as error:
                row.update(status='failed_unknown_wire', error_type=type(error).__name__)
                save()
                break
            if (i + 1) % 50 == 0:
                print(f'filing entities {i + 1}/{len(manifest["requests"])}', flush=True)
    finally:
        client.close()
    parsed = out / 'parsed'
    parsed.mkdir(exist_ok=True)
    for stamp, items in frames.items():
        pd.concat(items, ignore_index=True).to_parquet(parsed / f'{stamp}.parquet', index=False, compression='zstd')
    ledger['all_requests_attempted'] = len(ledger['requests']) == len(manifest['requests'])
    ledger['completed_at'] = datetime.now(UTC).isoformat()
    save()
    print({'requests': len(ledger['requests']), 'bytes': ledger['entity_bytes'], 'all_attempted': ledger['all_requests_attempted']}, flush=True)


if __name__ == '__main__':
    main()
