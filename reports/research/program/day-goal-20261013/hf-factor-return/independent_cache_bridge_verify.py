"""Independent raw cache bridge audit, no fitting or strategy returns."""
import hashlib
import json
import math
import os
import re
import resource
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

resource.setrlimit(resource.RLIMIT_CPU, (48, 48))
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import pyarrow as pa
import pyarrow.parquet as pq
pa.set_cpu_count(1)
pa.set_io_thread_count(1)

ROOT = Path('/root/codex-test/open-composer')
P = Path(__file__).parent
OLD = ROOT / 'reports/research/program/day-goal-20261011/tail-momentum'
NY = ZoneInfo('America/New_York')
bindings = {}

def load(path):
    path = Path(path)
    return json.loads(path.read_text())

def check(b):
    path = Path(b['path'])
    path = path if path.is_absolute() else ROOT / path
    path = path.resolve()
    if path not in bindings:
        h = hashlib.sha256()
        with path.open('rb') as f:
            for data in iter(lambda: f.read(1024*1024), b''):
                h.update(data)
        bindings[path] = {'path': str(path.relative_to(ROOT)), 'sha256': h.hexdigest(), 'bytes': path.stat().st_size}
    actual = bindings[path]
    assert actual['sha256'] == b['sha256'] and actual['bytes'] == b['bytes'], str(path)
    return path

def main():
    manifest_path = P / 'market-cache-bridge-manifest.json'
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == '06657daa07a5c3ed44109df74129ee455e8c5cc6a85a7edc7585a0f9bf3df3b6'
    manifest = load(manifest_path)
    assert len(manifest['files']) == 361
    for b in manifest['files']:
        check(b)
    for b in manifest['directbindings'].values():
        check(b)
    qa = load(P / 'market-input/cache-bridge/cache-bridge-QA.json')
    clock = {r['date']:r for r in load(P/'funded-SPY-clock-proposed.json')['rows']}
    expected = set()
    for day,r in clock.items():
        start = datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=NY)
        expected.update((start+timedelta(minutes=k*15)).astimezone(ZoneInfo('UTC')) for k in range(r['regular15_windows']))
    aggregate = {}
    normalized_samples = 0
    raw_count = retained_count = 0
    for year in qa['annual']:
        progress = load(OLD / f"inputs/minute-SPY-{year['year']}/progress.json")
        assert progress['complete'] and progress['next_token'] is None
        assert progress['request']['symbols'] == 'SPY' and progress['request']['timeframe'] == '1Min'
        assert progress['request']['adjustment'] == 'raw' and progress['request']['feed'] == 'sip'
        assert progress['request']['asof'] == '2026-09-15'
        token = None
        previous_time = None
        year_retained = 0
        for i,page in enumerate(year['pages']):
            raw_path, receipt_path = check(page['raw']), check(page['receipt'])
            norm_path = check(page['normalized'])
            receipt = load(receipt_path)
            params = progress['request'].copy()
            if token is not None:
                params['page_token'] = token
            assert receipt['request'] == params and receipt['page'] == i and receipt['status_code'] == 200
            assert receipt['entity_sha256'] == page['raw']['sha256'] and receipt['entity_bytes'] == page['raw']['bytes']
            body = load(raw_path)
            assert set(body['bars']) == {'SPY'}
            token = body['next_page_token']
            assert (token is None) == (i == len(year['pages'])-1)
            source = body['bars']['SPY']
            assert len(source) == page['raw_rows']
            sample = i in (0, len(year['pages'])-1)
            norm = pq.read_table(norm_path, use_threads=False).to_pylist() if sample else None
            norm_i = 0
            for row in source:
                t = datetime.fromisoformat(row['t'].replace('Z','+00:00'))
                assert previous_time is None or t > previous_time
                previous_time = t
                local = t.astimezone(NY)
                assert local.second == local.microsecond == 0
                day = str(local.date())
                minute = local.hour*60+local.minute
                raw_count += 1
                assert 0 < row['l'] <= min(row['o'],row['c']) <= max(row['o'],row['c']) <= row['h']
                assert all(math.isfinite(row[k]) for k in ('o','h','l','c','v')) and row['v'] >= 0
                if 570 <= minute < 960 and sample:
                    nr = norm[norm_i]
                    assert nr['symbol'] == 'SPY' and nr['timestamp'] == t
                    for src,dst in [('o','open'),('h','high'),('l','low'),('c','close'),('v','volume')]:
                        assert nr[dst] == row[src]
                    norm_i += 1
                r = clock.get(day)
                if r is None or not (r['open'] <= local.strftime('%H:%M:%S') < r['close']):
                    continue
                window_minute = 570+((minute-570)//15)*15
                key = local.replace(hour=window_minute//60, minute=window_minute%60).astimezone(ZoneInfo('UTC'))
                if key not in aggregate:
                    aggregate[key] = [row['o'],row['h'],row['l'],row['c'],row['v'],1,minute,minute]
                else:
                    a = aggregate[key]
                    a[1] = max(a[1],row['h']); a[2] = min(a[2],row['l'])
                    a[3] = row['c']; a[4] += row['v']; a[5] += 1; a[7] = minute
                year_retained += 1
                retained_count += 1
            if sample:
                assert norm_i == len(norm)
                normalized_samples += norm_i
            del source, body, norm
        assert year_retained == year['retained_minutes']
        output = pq.read_table(check(year['output']), use_threads=False).to_pylist()
        for row in output:
            a = aggregate[row['timestamp']]
            assert [row[k] for k in ['open','high','low','close','volume','minute_rows','first_minute','last_minute']] == a
            assert row['first_price_age_minutes'] == a[6]-row['window_minute']
            assert row['last_price_age_to_window_end_minutes'] == row['window_minute']+14-a[7]
        assert len(output) == year['observed_windows']
        print(json.dumps({'year':year['year'],'raw_aggregation_verified_windows':len(output),'CPU':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime}),flush=True)
    assert retained_count == 488935 and len(expected) == 32602 and len(aggregate) == 32601
    missing = sorted(t.isoformat() for t in expected-set(aggregate))
    assert missing == ['2019-08-12T19:45:00+00:00'] and not(set(aggregate)-expected)
    overlaps = 0
    for rec in load(P/'market-input/market-request-ledger.json'):
        for row in load(Path(rec['path']))['bars']['SPY']:
            t = datetime.fromisoformat(row['t'].replace('Z','+00:00'))
            if t in aggregate:
                assert [row[k] for k in ['o','h','l','c','v']] == aggregate[t][:5]
                overlaps += 1
    assert overlaps == 5096
    partial = [{'timestamp':t.isoformat(),'minutes':a[5],'first_minute':a[6],'last_minute':a[7]} for t,a in aggregate.items() if a[5]<15]
    assert len(partial) == 10
    rawdaily = load(ROOT/'reports/research/program/day-goal-20261013/primary-return-breadth/inputs/bars_raw-01.json')['bars']
    for symbol in ['SPY','BIL']:
        days = {str(datetime.fromisoformat(r['t'].replace('Z','+00:00')).astimezone(NY).date()):r for r in rawdaily[symbol]}
        assert all(day in days for day in clock)
    closes = load(P/'market-input/cache-bridge/raw-daily-closing-reconciliation.json')
    assert len(closes) == 1259 and all(x['daily_raw_present'] for x in closes)
    assert [x['date'] for x in closes if not x['closing15_present']] == ['2019-08-12']
    actions = load(P/'market-input/cache-bridge/SPY-BIL-bound-actions.json')
    workbook = check(actions['issuer_source'])
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(workbook) as z:
        strings=[''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)]
        rows={int(r.get('r')):r for r in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//m:row',ns)}
    counts=Counter()
    provider = load(check(actions['provider_source']))['corporate_actions']
    divs={(r['symbol'],r['ex_date']):r for r in provider['cash_dividends']}
    for a in actions['actions']:
        if a['type']!='cash_dividends':
            assert a['symbol']=='BIL' and a['type']=='reverse_splits' and a['ex_date']=='2017-11-30' and a['ratio']==.5
            assert a['provider_row'] in provider['reverse_splits'] and a['fractional_cash_in_lieu_quote_and_date'] is None
            continue
        counts[a['symbol']]+=1
        vals={}
        for c in rows[a['issuer_row']].findall('m:c',ns):
            value=c.find('m:v',ns)
            text='' if value is None else value.text
            vals[re.sub(r'\d','',c.get('r'))]=strings[int(text)] if text and c.get('t')=='s' else text
        assert vals==a['raw_cells'] and vals['B']==a['symbol']
        for cell,field in [('D','ex_date'),('E','record_date'),('F','payable_date')]:
            assert datetime.strptime(vals[cell].strip(),'%m/%d/%Y').date().isoformat()==a[field]
        assert float(vals['G'])==a['issuer_income']
        if a['provider_row'] is not None:
            assert a['provider_row']==divs[(a['symbol'],a['ex_date'])]
            assert a['amount']==a['provider_row']['rate']
        else:
            assert a['amount']==float(vals['G'])
    assert dict(counts)=={'BIL':60,'SPY':20}
    aq=load(P/'market-input/cache-bridge/SPY-BIL-action-QA.json')
    assert [r['date'] for r in aq['qa']['SPY']['known_transition_warnings']]==['2016-03-18','2018-06-15']
    result={'status':'ok','manifest_files':361,'unique_paths':len(bindings),'bindings':list(bindings.values()),'raw_pages_receipt_cursor_checked':100,'raw_bars_read':raw_count,'retained_regular_minutes_reaggregated':retained_count,'normalized_parquet_sample_rows_checked':normalized_samples,'all100normalized_value_checks':'Author full comparison inspected and hash-bound; independent first/last page each year actual OHLCV/timestamp comparison, plus independent full raw aggregation.', 'expected_windows':32602,'actual_reaggregated_windows':32601,'native_exact_overlap':5096,'missing':missing,'partial_minute_windows':partial,'daily_dates_present_SPY_BIL':1259,'issuer_cash_rows_reparsed':dict(counts),'BIL_split_verified':True,'no_model_or_economic_calculation':True,'resource':{'CPU_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'memory_cap_MiB':400,'CPU_affinity':sorted(os.sched_getaffinity(0)),'pool':'HF new2000 source/inputQA; current review max60 coresec'}}
    (P/'independent-cache-bridge-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'ok','unique_paths':len(bindings),'resource':result['resource']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    try:
        main()
    except BaseException as e:
        (P/'independent-cache-bridge-verification-failure.json').write_text(json.dumps({'error':repr(e),'CPU_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},indent=2)+'\n')
        raise
