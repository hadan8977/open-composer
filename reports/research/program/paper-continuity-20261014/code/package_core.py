"""One exact incremental package under the accepted P0 private-build scope."""
import ast
import base64
import hashlib
import importlib.metadata
import json
import zipfile
from pathlib import Path

ROOT=Path.cwd();OUT=ROOT/'reports/research/program/paper-continuity-20261014';WT=Path('/root/codex-test/wt-paper-continuity-20261014')
PACKAGE=OUT/'hadan-core-package';PACKAGE.mkdir(exist_ok=False)
JOB=r'C:\paseo\scratch\paper-continuity-forward-20261014'
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def bind(p,rel):return {'source_path':str(p),'relative_path':rel,'bytes':p.stat().st_size,'sha256':sha(p)}
x=json.loads((OUT/'current-feature-input-manifest.json').read_text())
items={i['relative_path']:i for i in x['inputs']}
for rel in ['scripts/prepare_host_forward_version.py']:
    items[rel]=bind(WT/rel,rel)
items['scripts/worker_core.py']=bind(OUT/'code/worker_core.py','scripts/worker_core.py')
x['inputs']=list(items.values());x['dependencies']={k:importlib.metadata.version(k)for k in ['numpy','pandas','pyarrow','duckdb','polars']}
runtime=PACKAGE/'current-inputs.json';runtime.write_text(json.dumps(x,indent=2)+'\n')
old=json.loads((ROOT/'reports/research/program/day-goal-20261011-2/host-freshness-repair/recovery-preparation/hadan-package/transfer-manifest.json').read_text())
olditems={i['relative_path']:i for i in old['original_files']}
reuse=[];changed=[]
for i in items.values():
    source=Path(i['source_path']);assert source.stat().st_size==i['bytes'] and sha(source)==i['sha256']
    if source.suffix=='.py':ast.parse(source.read_text())
    prior=olditems.get(i['relative_path'])
    (reuse if prior and (prior['bytes'],prior['sha256'])==(i['bytes'],i['sha256'])else changed).append(i)
changed.append(bind(runtime,'evidence/current-inputs.json'))
archive=PACKAGE/'input.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_STORED)as z:
    for i in changed:z.write(i['source_path'],i['relative_path'])
parts=[]
with archive.open('rb')as f:
    while chunk:=f.read(768*1024):
        p=PACKAGE/f'part-{len(parts):04d}.b64';p.write_bytes(base64.b64encode(chunk))
        parts.append({'local_path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
manifest={'schema_version':1,'job_id':'paper-continuity-forward-20261014','remote_root':r'C:\paseo','remote_scratch':JOB,
          'inputs':parts,'reuse_inputs':reuse,'archive':{'local_path':archive.relative_to(ROOT).as_posix(),'bytes':archive.stat().st_size,'sha256':sha(archive)},
          'runtime_inputs_sha256':sha(runtime),'expected_added_bytes':8*(1<<30),
          'cleanup':{'required':True,'scope':JOB,'when':'After exact verified return/completion; preserve native completed artifacts during interruption'},
          'task_authority_sha256':sha(OUT/'task.json'),'working_memory_GiB_max':4,'CPU_cores':1,'broker_files_transferred':False,'paid_USD':0,
          'source_requests':0,'native_wrapper_sha256':sha(OUT/'code/run-core.ps1')}
(PACKAGE/'transfer-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
rpc=(ROOT/'reports/research/program/day-goal-20261011-2/host-freshness-repair/recovery-preparation/hadan-package/native_batch_rpc.mjs').read_text()
rpc=rpc.replace('host-freshness-azn-broad-20261012','paper-continuity-forward-20261014')
# Exact same installed native file RPC; restrict writes to this new job only.
(PACKAGE/'native_batch_rpc.mjs').write_text(rpc)
ops=[{'local':str(ROOT/i['local_path']),'remote':JOB+'\\transfer\\'+Path(i['local_path']).name,'bytes':i['bytes'],'sha256':i['sha256']}for i in parts]
for source in [PACKAGE/'transfer-manifest.json',OUT/'code/receive_core.py',OUT/'code/run-core.ps1']:
    ops.append({'local':str(source),'remote':JOB+'\\transfer\\'+source.name,'bytes':source.stat().st_size,'sha256':sha(source)})
for start in range(0,len(ops),64):(PACKAGE/f'operations-{start//64:02d}.json').write_text(json.dumps(ops[start:start+64],indent=2)+'\n')
(PACKAGE/'mkdir-operations.json').write_text(json.dumps([{'remote':JOB},{'remote':JOB+'\\transfer'}])+'\n')
print(json.dumps({'parts':len(parts),'archive_bytes':archive.stat().st_size,'reuse_files':len(reuse),'reuse_bytes':sum(i['bytes']for i in reuse),'exact_input_files':len(items),'predicted_peak_added_bytes':manifest['expected_added_bytes']}))
