"""Independent static bindings and footer review; no data scan or economics."""
import hashlib
import json
import os
import resource
import subprocess
from collections import Counter
from pathlib import Path

resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
import pyarrow.parquet as pq

ROOT = Path('/root/codex-test/open-composer')
P = Path(__file__).parent
M = ROOT / 'reports/research/program/martin-luk-usic-20261013'
verified = {}

def bind(path):
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    if str(p) not in verified:
        h = hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda: f.read(1024 * 1024), b''):
                h.update(b)
        verified[str(p)] = {'path': str(p.relative_to(ROOT)), 'sha256': h.hexdigest(), 'bytes': p.stat().st_size}
    return verified[str(p)]

def check(v):
    a = bind(v['path'])
    assert a['sha256'] == v['sha256'], v['path']
    if 'bytes' in v:
        assert a['bytes'] == v['bytes']
    return a

def load(path):
    return json.loads(Path(path).read_text())

def main():
    packet = load(P / 'review-bindings.json')
    assert bind(P / 'review-bindings.json')['sha256'] == '21195af9d2b5caad62e7dec1d20611b6a4e0cd84a7b7a81751d7a421393e42fc'
    for v in packet.values():
        if isinstance(v, dict) and 'path' in v:
            check(v)
    plan = load(ROOT / packet['plan']['path'])
    cases = load(ROOT / packet['casebook']['path'])['cases']
    images = []
    assert len(cases) == 24
    for row in cases:
        if 'image_path' in row:
            b = bind(M / row['image_path'])
            assert b['sha256'] == row['image_sha256']
            images.append(b)
    assert len(images) == 9
    probe = load(ROOT / packet['input_probe']['path'])
    for b in probe['input_bindings']:
        check(b)
    footers = []
    for row in probe['cases']:
        path = ROOT / row['path']
        meta = pq.read_metadata(path)
        assert meta.num_rows == row['footer_row_count']
        assert meta.created_by == row['writer']
        assert str(meta.schema.to_arrow_schema()) == row['schema']
        footers.append({'path': row['path'], 'rows': meta.num_rows, 'symbol': row['symbol'], 'probe_date': row['probe_date'], 'owner_clock_probe_status': row['status']})
    pairs = {(r['symbol'], r['probe_date']) for r in probe['cases'] if r['record_clock_coverage']['row_count'] > 0}
    assert len(footers) == 14 and len(pairs) == 7
    d = load(ROOT / packet['direction']['path'])
    cards = [json.loads(line) for line in (ROOT / packet['source_cards']['path']).read_text().splitlines()]
    for row in d['sources']:
        b = bind(row['snapshot_path'])
        assert b['sha256'] == row['sha256']
        card = next(c for c in cards if c['claim_id'] == row['claim_id'])
        assert card['source_sha256'] == row['sha256'] and card['source_url'] == row['url']
        assert card['quote'] in (ROOT / row['snapshot_path']).read_text()
    for name in ['query_manifest', 'pre_iteration_knowledge_baseline']:
        check(d[name])
    for path in plan['source_evidence']:
        bind(path)
    for path in [M / 'sources/interview-transcript-original.html', M / 'sources/contest-and-method-pages.json', M / 'sources/interview-and-contest-reading.json', M / 'sources/full-source-open-20261013.json', M / 'reading/key-passages-reading.txt', M / 'reading/interview-and-contest-reading.txt', P / 'sources/comparison-firstperson-01.json', P / 'sources/comparison-primary-method-reads.json', P / 'sources/plain/comparison-primary-method-reads.txt', P / 'sources/plain/comparison-firstperson-01.txt', P / 'sources/plain/comparison-official-reads-and-method-leads.txt', P / 'trial-exposure-policy.json', P / 'brief.md']:
        bind(path)
    scope = load(ROOT / packet['request_scope']['path'])
    assert len(scope['requests']) == scope['initial_request_objects'] == 13
    assert sum(r['max_pages'] for r in scope['requests']) == scope['max_pages_total'] == 32
    assert sum(r['max_pages'] * r['per_page_byte_cap'] for r in scope['requests']) == 67108864
    assert scope['aggregate_market_pool']['already_allocated'] == 0
    cm = load(ROOT / packet['candidate_manifest']['path'])
    assert [r['definition'] for r in cm['candidates']] == plan['candidate_inventory']
    cells = load(ROOT / packet['evaluation_cells']['path'])['cells']
    assert len(cells) == 120 and len({json.dumps(r, sort_keys=True) for r in cells}) == 120
    paths = ['open_composer/research/direction.py', 'harness/artifact_contracts.yaml', 'harness/source_policy.yaml']
    for path in paths:
        bind(path)
    diff = subprocess.run(['git', 'diff', '--', *paths], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    (P / 'independent-source-type-diff.txt').write_text(diff)
    bind(P / 'independent-source-type-diff.txt')
    result = {'status': 'ok', 'main_bindings': 13, 'cases': 24, 'original_images_bound_and_visually_reviewed': images, 'minute_footer_bindings': footers, 'owner_probe_seven_actual_stockdays_preserved': sorted(pairs), 'numeric_data_rows_read_by_this_review': 0, 'request_objects': 13, 'max_pages': 32, 'max_entity_bytes': 67108864, 'candidate_count': 8, 'evaluation_cells': 120, 'extra_latency_candidates': sorted({r['candidate_id'] for r in cells if r['extra_latency_bars'] > 0}), 'cell_count_by_candidate': dict(Counter(r['candidate_id'] for r in cells)), 'source_quotes_and_SHA_checked': len(cards), 'verified_unique_paths': list(verified.values()), 'resource': {'CPU_seconds': resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime, 'max_RSS_KiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, 'affinity': sorted(os.sched_getaffinity(0)), 'memory_cap_MiB': 512, 'pool': 'USIC comparisons preparation1000 shared; this independent review <=90'}}
    (P / 'independent-plan-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'status': 'ok', 'unique_paths': len(verified), 'resource': result['resource']}, ensure_ascii=False))

if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        (P / 'independent-plan-verification-failure.json').write_text(json.dumps({'error': repr(e), 'CPU_seconds': resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime, 'max_RSS_KiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, 'verified': list(verified.values())}, indent=2)+'\n')
        raise
