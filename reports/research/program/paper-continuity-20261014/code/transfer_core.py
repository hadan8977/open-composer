"""Execute the exact manifest's bounded native file RPC batches once."""
import json
import subprocess
import time
import sys
from pathlib import Path
ROOT=Path.cwd();OUT=ROOT/'reports/research/program/paper-continuity-20261014';PACKAGE=OUT/'hadan-core-package'
preflight=json.loads((OUT/'hadan-transfer-preflight.json').read_text())
assert preflight['ok'] is True
s=preflight['remote']['worker_status']
assert s['status']=='ready' and s['usage_ok'] and not s['paused'] and not s['hard_off']
assert type(s['usage_bytes'])is int and s['usage_bytes']>=0
m=json.loads((PACKAGE/'transfer-manifest.json').read_text());assert s['usage_bytes']+m['expected_added_bytes']<50*(1<<30)
sys.path.insert(0,str(ROOT))
from open_composer.remote.windows_worker import validate_task_manifest
validated=validate_task_manifest(ROOT,m)
assert validated['ok'] is True
(OUT/'core-transfer-manifest-validation.json').write_text(json.dumps(validated,indent=2)+'\n')
receipt=OUT/'transfer-core-ledger.json';assert not receipt.exists()
ledger={'scope':'manifest-bound private P0 inputs','entries':[],'preflight_worker':s,'broker_files_transferred':False}
for label,action,operations in [('mkdir','mkdir-list',PACKAGE/'mkdir-operations.json'),
                              *[(p.stem,'write-list',p)for p in sorted(PACKAGE.glob('operations-*.json'))]]:
    entry={'label':label,'status':'started_consumed_before_call','started_unix':time.time()};ledger['entries'].append(entry)
    receipt.write_text(json.dumps(ledger,indent=2)+'\n')
    with(OUT/f'transfer-{label}.log').open('w')as log:
        p=subprocess.run(['node',str(PACKAGE/'native_batch_rpc.mjs'),action,str(operations)],cwd=ROOT,stdout=log,stderr=log,timeout=240)
    entry.update(status='complete' if p.returncode==0 else 'failed_preserved',exit_code=p.returncode,finished_unix=time.time())
    receipt.write_text(json.dumps(ledger,indent=2)+'\n')
    if p.returncode:raise RuntimeError(label+' failed; retain consumed transfer ledger')
    print(label,'complete',flush=True)
