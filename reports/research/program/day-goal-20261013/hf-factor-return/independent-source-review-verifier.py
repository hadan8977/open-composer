"""Bounded independent raw-source and R1-R4 binding verification; no economics."""

import gc
import hashlib
import json
import math
import os
import resource
import sys
from datetime import date, timedelta
from pathlib import Path

resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'

import pyarrow as pa
import pyarrow.parquet as pq

pa.set_cpu_count(1)
pa.set_io_thread_count(1)
ROOT = Path('/root/codex-test/open-composer')
P = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from open_composer.market_sessions import _early_closes

CACHE = {}
OUT = P / 'independent-source-and-plan-verification.json'


def read(name):
    return json.loads((P / name).read_text())


def bind(path):
    path = Path(path)
    path = path if path.is_absolute() else ROOT / path
    path = path.resolve()
    if path in CACHE:
        return CACHE[path]
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    result = {'path': str(path.relative_to(ROOT)), 'sha256': h.hexdigest(), 'bytes': path.stat().st_size}
    CACHE[path] = result
    return result


def check(expected):
    actual = bind(expected['path'])
    assert actual['sha256'] == expected['sha256'], expected['path']
    assert actual['bytes'] == expected['bytes'], expected['path']
    return actual


def nested_bindings(obj):
    if isinstance(obj, dict):
        if all(k in obj for k in ('path', 'sha256', 'bytes')):
            check(obj)
        else:
            for value in obj.values():
                nested_bindings(value)
    elif isinstance(obj, list):
        for value in obj:
            nested_bindings(value)


def main():
    a, b = read('scientific-plan.json'), read('execution-contract.json')
    revision = read('scientific-plan-revision.json')
    assert bind(P / 'scientific-plan.json')['sha256'] == '666b4048c26f98ce9ce02c9b66b2e1982e805d9ec43e8e94de9a314280a7e7fd'
    assert bind(P / 'execution-contract.json')['sha256'] == '63d57d661fe9adf7a32896ec4dae50d39941f087ce780a286a1194c7cac452f6'
    assert bind(P / 'scientific-plan-revision.json')['sha256'] == 'ecb593246c536325e6df391e7849bad6d3667522dd04264293d7d4e606717fab'
    nested_bindings(a['bindings'])
    nested_bindings(revision['binding'])
    check(b['scientific_plan'])
    old = read('scientific-plan-v1.json')
    assert a['candidates'] == old['candidates'] and len(a['candidates']) == 20
    changed = {k for k in a if a[k] != old[k]}
    assert changed == set(revision['changed_top_level'])
    assert all(revision['diff'][k] == {'old': old[k], 'new': a[k]} for k in changed)
    sections = ['feature_and_label', 'validation_and_models', 'execution_and_capital', 'inference_and_contribution', 'resources_and_gates']
    assert all(a[k] == b[k] for k in sections)
    for k in ['source', 'market', 'economic', 'planned_upper_allocation']:
        assert a['resources_and_gates'][k] == old['resources_and_gates'][k]
    clock = read('source-conditional-clock.json')
    nested_bindings(clock['primitive'])
    expected_dates = []
    d = date(1996, 1, 1)
    while d <= date(2020, 12, 31):
        if d.weekday() < 5:
            expected_dates.append(d)
        d += timedelta(days=1)
    assert len(clock['rows']) == len(expected_dates) == 6524
    for row, day in zip(clock['rows'], expected_dates, strict=True):
        assert row['date'] == str(day) and row['nominal_source_open'] == '09:30:00'
        assert row['nominal_source_close'] == ('13:00:00' if day in _early_closes(day.year) else '16:00:00')
    m, qa = read('complete-source-input-manifest.json'), read('complete-source-input-QA.json')
    prog = read('complete-input-progress.json')
    ledger = read('continuation-source-request-ledger.json')
    request = read('complete-input-request-manifest.json')
    nested_bindings(m['bindings'])
    nested_bindings(qa['bindings'])
    nested_bindings(read('continuation-preparation-resource-ledger.json')['receipts'])
    assert prog['process_exit_status'] == 0 and prog['complete_months'] == 300
    expected_months = [f'{y}{month:02}' for y in range(1996, 2021) for month in range(1, 13)]
    assert [r['month'] for r in m['files']] == expected_months
    assert m['files'] == qa['files']
    requested = {r['month']: r for r in request['files']}
    progress = {r['month']: r for r in prog['files']}
    assert set(requested) == set(progress) == set(expected_months)
    schema_names = qa['factor_columns'] + [qa['timestamp_column']]
    row_total = byte_total = 0
    for i, row in enumerate(m['files']):
        actual = check(row)
        path = ROOT / actual['path']
        meta = pq.read_metadata(path)
        assert meta.schema.names == schema_names and meta.num_columns == 273
        assert meta.num_rows == row['rows']
        assert all(meta.schema.column(k).physical_type == 'DOUBLE' for k in range(272))
        assert meta.schema.to_arrow_schema().field('datetime').type.tz is None
        assert actual['bytes'] <= requested[row['month']]['individual_body_hard_cap_bytes']
        prior = progress[row['month']]
        assert all(prior[k] == row[k] for k in ('sha256', 'bytes', 'rows'))
        assert all(prior[k] == 0 for k in ('nonfinite_values', 'NaN_values', 'infinite_values', 'values_not_in_log1p_domain', 'duplicate_timestamps'))
        assert prior['monotonic'] and prior['column_order_matches_first']
        req = requested[row['month']]
        if req['reuse_existing']:
            check(req['existing_input'])
        else:
            received = [r for r in ledger if r.get('sha256') == row['sha256'] and r.get('url') == req['url'] and r.get('status') == 200 and r.get('body_complete')]
            assert len(received) == 1 and received[0]['bytes'] == row['bytes']
        row_total += meta.num_rows
        byte_total += actual['bytes']
        if (i + 1) % 50 == 0:
            print(json.dumps({'verified_months': i + 1, 'cpu': resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime}), flush=True)
    assert row_total == m['rows'] == qa['total_actual_rows'] == 2454420
    assert byte_total == m['actual_raw_file_bytes_including_oldfirst'] == 6515013371
    assert len(ledger) == m['continuation_requests'] == 321
    assert sum(r.get('bytes', 0) for r in ledger) == m['continuation_actual_direct_bytes'] == 6494626426
    assert len(ledger) <= 400 and m['continuation_actual_direct_bytes'] <= 8 * 1024**3
    failures = [r for r in ledger if r.get('status') == 500]
    assert len(failures) == 1
    check(failures[0])
    assert [r['date'] for r in qa['days']] == sorted({r['date'] for r in qa['days']})
    assert len(qa['days']) == m['source_days'] == 6295
    assert sum(r['rows'] for r in qa['days']) == row_total
    samples = []
    for ix in (0, 149, 299):
        row = m['files'][ix]
        cols = ['datetime', 'ff__mkt', schema_names[0], a['feature_and_label']['key5'][0]]
        table = pq.read_table(ROOT / row['path'], columns=cols, use_threads=False)
        ticks = table.column('datetime').to_pylist()
        assert ticks == sorted(ticks) and len(set(ticks)) == len(ticks)
        assert all(t.strftime('%Y%m') == row['month'] and t.tzinfo is None for t in ticks)
        days = {}
        for tick in ticks:
            days.setdefault(str(tick.date()), []).append(tick)
        actual_days = [{'date': day, 'rows': len(ts), 'first': str(ts[0]), 'last': str(ts[-1]), 'non_one_minute_steps': sum((v-u).total_seconds() != 60 for u, v in zip(ts, ts[1:])), 'duplicate_times': 0} for day, ts in days.items()]
        assert actual_days == progress[row['month']]['days']
        for c in cols[1:]:
            vals = table.column(c).to_pylist()
            assert all(v is not None and math.isfinite(v) and v > -1 for v in vals)
        observed = []
        for j in (0, table.num_rows // 2, table.num_rows - 1):
            observed.append({c: str(table.column(c)[j].as_py()) if c == 'datetime' else table.column(c)[j].as_py() for c in cols})
        samples.append({'month': row['month'], 'rows': table.num_rows, 'sampled_columns': cols, 'first_middle_last_records': observed, 'all_month_timestamps_rechecked': True, 'three_value_columns_finite_domain_checked': True})
        del table, ticks, vals
        gc.collect()
    result = {'status': 'ok', 'plan_sections_equal': sections, 'plan_bindings': len(a['bindings']), 'plan_changed_top_level': sorted(changed), 'candidate_count': 20, 'caps_unchanged': True, 'conditional_clock_rows_verified': 6524, 'source_manifest': bind(P / 'complete-source-input-manifest.json'), 'source_QA': bind(P / 'complete-source-input-QA.json'), 'monthly_files_SHA_size_and_schema_verified': 300, 'raw_bytes_hashed': byte_total, 'rows_metadata_sum': row_total, 'source_days_owner_timestamp_QA_sum': 6295, 'source_value_check_scope': 'Author full-value QA bound and inspected; independent three columns and all timestamps in fixed first/middle/last months. No whole numeric matrix reread or model/economic calculation.', 'samples': samples, 'continuation_requests': len(ledger), 'continuation_bytes': m['continuation_actual_direct_bytes'], 'failed_500_response_retained': check(failures[0]), 'verified_unique_paths': list(CACHE.values()), 'resource': {'cpu_seconds': resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime, 'maxrss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, 'cpu_affinity': sorted(os.sched_getaffinity(0)), 'rlimit_cpu': 180, 'memory_cap_mib': 400, 'pool': 'HF new2000 inputQA only'}}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'ok', 'receipt': bind(OUT), 'resource': result['resource']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        (P / 'independent-source-verification-failure.json').write_text(json.dumps({'error': repr(e), 'verified_paths': list(CACHE.values()), 'cpu_seconds': resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime, 'maxrss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}, ensure_ascii=False, indent=2) + '\n')
        raise
