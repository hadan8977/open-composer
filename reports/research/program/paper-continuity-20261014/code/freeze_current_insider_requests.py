"""Exact Form4 tail inventory using the original collector population."""
import importlib.util
import json
import sys
from pathlib import Path

WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT))
spec = importlib.util.spec_from_file_location('insider_collector', WT / 'scripts/collect_sec_insider_transactions.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
allowed = m.universe_issuer_ciks(1000)
records = json.loads((P / 'dated-SEC-index-records.json').read_text())['records']
rows = [r for r in records if r['form'] in ('4', '4/A') and r['filed'] in ('20261008', '20261009', '20261013') and int(r['cik']) in allowed]
unique = {r['file_name']: r for r in rows}
requests = [{'url': 'https://www.sec.gov/Archives/' + r['file_name'], 'source_index_record': r, 'max_entity_bytes': 262144} for r in sorted(unique.values(), key=lambda r: (r['filed'], r['file_name']))]
result = {'scope': 'necessary same-source tail of the existing paper insider collector; original top1000 union issuer filter unchanged', 'requests': requests, 'max_requests': len(requests), 'max_total_entity_bytes': len(requests) * 262144, 'retry': False, 'redirect': False, 'source_only': True, 'identity_headers_recorded': False, 'broker_writes': 0}
(P / 'current-insider-request-manifest.json').write_text(json.dumps(result, indent=2) + '\n')
print({'requests': len(requests), 'max_bytes': result['max_total_entity_bytes'], 'issuer_population': len(allowed)}, flush=True)
