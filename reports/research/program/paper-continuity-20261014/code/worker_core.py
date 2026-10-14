"""Original natural builders plus the separately versioned prefix composition."""
import ctypes
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; JOB=ROOT.parent;OUT=ROOT/'results/core'
assert str(JOB).casefold()==r'C:\paseo\scratch\paper-continuity-forward-20261014'.casefold()
OUT.mkdir(parents=True,exist_ok=False)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
inputs=json.loads((ROOT/'evidence/current-inputs.json').read_text(encoding='utf-8'))
def verify():
    for i in inputs['inputs']:
        p=ROOT/i['relative_path']; assert p.stat().st_size==i['bytes'] and sha(p)==i['sha256'],i['relative_path']
verify()
versions={k:importlib.metadata.version(k)for k in ['numpy','pandas','pyarrow','duckdb','polars']}
(OUT/'versions.json').write_text(json.dumps(versions,indent=2)+'\n')
executions=[]
def cpu(proc):
    a,b,c,d=(wintypes.FILETIME()for _ in range(4))
    if not ctypes.windll.kernel32.GetProcessTimes(wintypes.HANDLE(int(proc._handle)),ctypes.byref(a),ctypes.byref(b),ctypes.byref(c),ctypes.byref(d)):
        raise OSError('inclusive child CPU observation unavailable')
    return ((c.dwHighDateTime<<32)+c.dwLowDateTime+(d.dwHighDateTime<<32)+d.dwLowDateTime)/1e7
def run(label,args):
    started=time.monotonic()
    with (OUT/(label+'.stdout')).open('w',encoding='utf-8')as out,(OUT/(label+'.stderr')).open('w',encoding='utf-8')as err:
        p=subprocess.Popen([sys.executable,'-B',*args],cwd=ROOT,stdout=out,stderr=err)
        (JOB/'active-child.json').write_text(json.dumps({'PID':p.pid,'label':label,'started_UTC':time.time()}))
        try:code=p.wait(timeout=1600)
        except subprocess.TimeoutExpired:p.kill();p.wait();code=124
        row={'label':label,'argv':args,'exit_code':code,'wall_seconds':time.monotonic()-started,'child_CPU_seconds':cpu(p)}
    executions.append(row)
    (OUT/(label+'-execution.json')).write_text(json.dumps(row,indent=2)+'\n')
    assert code==0, label+' failed; preserve original attempt'
for group in ['daily','daily_broad']:
    args=['scripts/build_daily_features.py','--years','2026','--memory-limit','1.0GB','--out-dir',f'data/features/_forward_candidates/{group}']
    if group=='daily_broad':args+=['--universe-root','data/features/universe_broad','--extra-daily-root','data/sip-delisted/by_year']
    run('build-'+group,args)
    old=next(i for i in inputs['inputs']if i['relative_path']==f'baselines/{group}-2026.parquet')
    run('compose-'+group,['scripts/prepare_host_forward_version.py','--baseline',old['relative_path'],
        '--baseline-sha256',old['sha256'],'--candidate',f'data/features/_forward_candidates/{group}/2026.parquet',
        '--output',f'data/features/{group}/2026.parquet','--source-manifest','evidence/current-inputs.json',
        '--prefix-end','2026-10-07','--suffix-end','2026-10-13','--version-id','host-forward-v1-20261014',
        '--receipt',f'results/core/compose-{group}.json'])
verify()
result={'status':'actual_private_core_completed','executions':executions,'parent_CPU_seconds':time.process_time(),
        'inclusive_python_CPU_seconds':time.process_time()+sum(x['child_CPU_seconds']for x in executions),
        'source_requests':0,'broker_calls':0,'original_whole_panel_pass':None,'production_changes':0}
(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
