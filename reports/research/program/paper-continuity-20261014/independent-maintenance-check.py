"""Independent small binding/continuity checks; no broker, source fetch or real panel scan."""
import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

P = Path(__file__).resolve().parent
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
resource.setrlimit(resource.RLIMIT_CPU, (850, 900))
sys.path[:0] = [str(WT), str(WT / 'scripts')]
import pyarrow as pa
import pyarrow.parquet as pq
import forward_feature_epoch as ep
import refresh_equity_book_live as rf

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

manifest = json.loads((P / 'result-manifest.json').read_text())
checked = []
for item in manifest['code']:
    p = Path(item['path'])
    assert p.stat().st_size == item['bytes'] and sha(p) == item['sha256'], str(p)
    checked.append(item)
inputs = json.loads((P / 'current-feature-input-manifest.json').read_text())['inputs']
context_bytes = sum(i['bytes'] for i in inputs if any(x in i.get('relative_path','') for x in ['data/sip/daily/2025/', 'data/sip/daily/2026/', 'data/sip-delisted/by_year/2025/', 'data/sip-delisted/by_year/2026/']))
results = {'code_bindings_verified': checked, 'code_binding_count': len(checked),
           'context_bytes_from_existing_manifest_not_new_disk_scan': context_bytes,
           'affinity': sorted(os.sched_getaffinity(0)), 'checks': []}
with tempfile.TemporaryDirectory(prefix='paper-review-', dir=P) as d:
    root = Path(d)
    old = root/'old.parquet'; new = root/'candidate.parquet'; out = root/'out.parquet'
    def table(days, values):
        return pa.table({'symbol':['A']*len(days), 'trade_date':pa.array(days).cast(pa.timestamp('ns')), 'close':values})
    pq.write_table(table(['2026-10-30'],[10.]), old)
    pq.write_table(table(['2026-10-30','2026-11-02'],[10.,11.]), new)
    dependency=root/'universe.parquet'; dependency.write_bytes(b'old-month')
    source=root/'source.json'
    source.write_text(json.dumps({'producer_dependencies':[{'path':str(dependency),'bytes':dependency.stat().st_size,'sha256':sha(dependency)}]}))
    cfg={'tables':{'daily':{'anchor_sha256':sha(old)}}, 'year':2026,'version_directory':'version',
         'version_id':'test','anchor_end':'2026-10-30','runtime_source_manifest':str(source)}
    dependency.write_bytes(b'new-month')
    try:
        ep.publish_forward_table(root,'daily',old,new,out,date(2026,11,2),cfg)
    except ValueError as e:
        assert 'producer input/code changed' in str(e)
        results['checks'].append({'id':'monthly_dependency_before_update','result':'confirmed_normal_update_rejected','error':str(e)})
    else:
        raise AssertionError('expected frozen pre-month dependency rejection')
    source.write_text('{}')
    # Fail the final head write after output.replace, using the actual publisher.
    original=Path.write_text
    def fail_head(self,*args,**kwargs):
        if self.name=='daily.json.tmp':
            raise OSError('injected disk-full during latest receipt publication')
        return original(self,*args,**kwargs)
    Path.write_text=fail_head
    try:
        try:
            ep.publish_forward_table(root,'daily',old,new,out,date(2026,11,2),cfg)
        except OSError:
            assert out.exists() and not (root/'version/latest/daily.json').exists()
        else:
            raise AssertionError('expected interruption')
    finally:
        Path.write_text=original
    try:
        ep.publish_forward_table(root,'daily',old,new,out,date(2026,11,2),cfg)
    except ValueError as e:
        assert 'consumed forward receipt exists' in str(e)
        results['checks'].append({'id':'publication_disk_failure_recovery','result':'output_published_head_absent_retry_refused','error':str(e)})
    else:
        raise AssertionError('expected explicit recovery required')
    calls=[]
    def runner(argv,**kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv,0,'','')
    plan=rf.build_plan(date(2026,10,14),tables=[],stages=['panel','prices','etf','signals','risk'],fetch=False,upstream=False,forward_config=cfg)
    assert rf.run_plan(date(2026,10,14),plan,runner=runner,forward_config=cfg)==0
    assert len(calls)==5
    results['checks'].append({'id':'downstream_forward_epoch','result':'all_five_live_builders_direct_without_prefix_publication_hook','commands':calls})
results['peak_RSS_KiB']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
(P/'independent-maintenance-verification.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({k:v for k,v in results.items() if k not in ['code_bindings_verified','checks']}))
print(json.dumps(results['checks'],indent=2))
