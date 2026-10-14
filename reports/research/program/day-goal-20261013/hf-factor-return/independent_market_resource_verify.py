"""Independent partial market pagination/clock audit; no new requests or P&L."""
import hashlib
import json
import math
import os
import re
import resource
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

resource.setrlimit(resource.RLIMIT_CPU, (40, 40))
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
ROOT = Path('/root/codex-test/open-composer')
P = Path(__file__).parent
seen = {}

def load(name):
    return json.loads((P / name).read_text())

def bind(path):
    path = Path(path)
    path = path if path.is_absolute() else ROOT / path
    path = path.resolve()
    if path not in seen:
        b = path.read_bytes()
        seen[path] = {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)}
    return seen[path]

def check(x):
    b = bind(x['path'])
    assert b['sha256'] == x['sha256'] and b['bytes'] == x['bytes'], x['path']
    return b

def main():
    assert bind(P / 'market-input-resource-decision.json')['sha256'] == 'ac05ac8e8b43900b78f0a4f00da558985696268dc7b3a6f6efcb0b9b293ceb4b'
    assert bind(P / 'market-resource-decision-manifest.json')['sha256'] == '36dfb4d212038e27bfddf4e68ebc1b6142e7f65fdfd715254b7f0b1bcaa97280'
    assert bind(P / 'remaining-market-request-proposal.json')['sha256'] == '454b3c369882b6697646495c20b1e485a88815cac6243d12f60e29231110a66a'
    manifest = load('market-resource-decision-manifest.json')
    decision = load('market-input-resource-decision.json')
    proposal = load('remaining-market-request-proposal.json')
    check(manifest['decision'])
    assert manifest['bindings'] == decision['bindings']
    for b in manifest['bindings'].values():
        check(b)
    ledger = load('market-input/market-request-ledger.json')
    oldpath = ROOT / 'reports/research/program/day-goal-20261013/primary-return-breadth/inputs/market-request-ledger.json'
    old = json.loads(oldpath.read_text())
    bind(oldpath)
    assert len(old) == 9 and sum(x['bytes'] for x in old) == 4120032
    assert len(ledger) == len(manifest['actual_market_pages']) == 15
    allbars, token, row_counts, page_bytes = [], None, [], []
    for entry, page in zip(ledger, manifest['actual_market_pages'], strict=True):
        actual = check(page)
        assert actual['sha256'] == entry['sha256']
        assert actual['bytes'] == entry['retained_bytes'] == entry['bytes']
        assert entry['status'] == 200 and entry['body_complete'] and entry['automatic_retries'] == 0
        params = proposal['params_except_cursor'].copy()
        if token is not None:
            params['page_token'] = token
        assert entry['params'] == params and entry['request_path'] == '/stocks/bars'
        body = json.loads((ROOT / actual['path']).read_text())
        assert set(body['bars']) == {'SPY'}
        bars = body['bars']['SPY']
        assert len(bars) == page['rows']
        assert bars[0]['t'] == page['first'] and bars[-1]['t'] == page['last']
        token = body['next_page_token']
        assert token
        allbars.extend(bars)
        row_counts.append(len(bars))
        page_bytes.append(actual['bytes'])
    assert proposal['cursor']['value'] == token
    ticks = [datetime.fromisoformat(b['t'].replace('Z', '+00:00')) for b in allbars]
    assert ticks == sorted(ticks) and len(set(ticks)) == len(ticks)
    for b in allbars:
        assert all(math.isfinite(b[k]) for k in ['o', 'h', 'l', 'c', 'v', 'n', 'vw'])
        assert 0 < b['l'] <= min(b['o'], b['c']) <= max(b['o'], b['c']) <= b['h']
        assert b['v'] > 0 and b['n'] > 0
    clock = load('funded-SPY-clock-proposed.json')
    bind(P / 'funded-SPY-clock-proposed.json')
    expected = {r['date']: r for r in clock['rows']}
    tz = ZoneInfo('America/New_York')
    actual = {}
    for t in ticks:
        local = t.astimezone(tz)
        day = str(local.date())
        r = expected.get(day)
        if r and r['open'] <= str(local.time()) < r['close']:
            actual.setdefault(day, []).append(local)
    last_day = str(ticks[-1].astimezone(tz).date())
    covered = {d for d in expected if d <= last_day}
    future = {d for d in expected if d > last_day}
    assert set(actual) == covered
    for d, ts in actual.items():
        r = expected[d]
        start = datetime.fromisoformat(d+'T'+r['open']).replace(tzinfo=tz)
        want = [start+timedelta(minutes=15*k) for k in range(r['regular15_windows'])]
        assert ts == want, d
    assert len(allbars) == 12187 and sum(len(v) for v in actual.values()) == 5096
    assert len(covered) == 196 and len(expected) == 1259 and len(future) == 1063
    assert sum(page_bytes) == 1314927
    assert min(row_counts) == 719 and max(row_counts) == 925
    assert last_day == '2016-10-11'
    rate = len(ledger)/len(covered)
    additional = math.ceil(rate*len(future))
    mean_bytes = sum(page_bytes)/len(ledger)
    estimate = additional*mean_bytes
    assert additional == 82
    assert math.isclose(estimate, proposal['projection']['linear_additional_response_bytes'])
    prior_bytes = sum(x['bytes'] for x in old) + sum(page_bytes)
    remaining = 16*1024**2 - prior_bytes
    assert proposal['prior_global_market_requests'] == len(old)+len(ledger) == 24
    assert proposal['prior_global_market_bytes'] == prior_bytes == 5434959
    assert proposal['same_remaining_byte_cap'] == remaining == 11342257
    assert proposal['proposed_new_additional_request_units'] == 120
    assert proposal['new_direct_byte_allowance'] == proposal['new_USD_allowance'] == 0
    current_code = (P/'fetch_spy_intraday.py').read_text()
    prior_code = (P/'fetch_spy_intraday-v1-loaded.py').read_bytes()
    assert re.sub(r'\bMARKET_INPUT\b', 'I', current_code).encode() == prior_code
    qa = load('market-input-coverage-and-resource-QA.json')
    assert qa['pages'] == manifest['actual_market_pages']
    assert all(not r['missing_times'] for r in qa['actual_partial_day_grid_checks'])
    resources = load('preparation-resource-continuation-02.json')
    check(resources['prior_resource_continuation'])
    check(resources['immutable_base_source_ledger'])
    for r in resources['new_receipts']:
        check(r['receipt'])
    total = resources['prior_measured_plus_allowance'] + sum(r['actual_user_plus_system_CPU'] for r in resources['new_receipts']) + resources['new_resource_decision_write_and_review_setup_allowance']
    assert math.isclose(total, resources['cumulative_conservative_CPU'])
    result = {'status': 'ok', 'hash_or_size_mismatches': 0, 'verified_unique_paths': list(seen.values()), 'actual_pages': 15, 'HTTP200_complete': 15, 'ordered_cursor_chain_verified': True, 'last_cursor_matches_proposal': True, 'OHLCV_n_vwap_finite_and_geometry_checked': True, 'rows': 12187, 'regular_rows': 5096, 'complete_regular_day_grids_under_bound_clock': 196, 'expected_days_under_bound_clock': 1259, 'future_missing_days': 1063, 'last_local_date': last_day, 'rows_per_page_range': [min(row_counts), max(row_counts)], 'actual_new_bytes': sum(page_bytes), 'global_prior_requests': 24, 'global_prior_bytes': prior_bytes, 'remaining_same16MiB': remaining, 'projection': {'additional_requests_density_estimate': additional, 'bytes_density_estimate': estimate, 'proposed_additional_hardcap': 120, 'hypothetical_total_global_count_after_amendment': 144, 'hypothetical_HF_count_after_amendment': 135, '120_at_current_mean_bytes': 120*mean_bytes, '120_at_observed_largest_page_bytes': 120*max(page_bytes), 'estimates_not_completion_guarantee': True}, 'only_identifier_rename_capture_code_verified': True, 'source300_raw_rehashed': False, 'prior_resource_conservative_CPU': total, 'resource': {'CPU_seconds': resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime, 'max_RSS_KiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, 'memory_cap_MiB': 400, 'affinity': sorted(os.sched_getaffinity(0)), 'review_cap_coresec': 60, 'pool': 'HF new2000 source/inputQA'}}
    (P/'independent-market-resource-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','rows','regular_rows','future_missing_days','projection','resource']},ensure_ascii=False))

if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        (P/'independent-market-resource-verification-failure.json').write_text(json.dumps({'error':repr(exc),'CPU_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},indent=2)+'\n')
        raise
