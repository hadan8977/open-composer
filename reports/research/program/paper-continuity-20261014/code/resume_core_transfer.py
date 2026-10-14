"""Continue the consumed transfer using exact prior readbacks, retaining failure."""
import hashlib
import json
import subprocess
import time
from pathlib import Path
ROOT=Path.cwd();OUT=ROOT/'reports/research/program/paper-continuity-20261014';PACKAGE=OUT/'hadan-core-package'
preflight=json.loads((OUT/'hadan-control-repaired-standard-preflight.json').read_text());assert preflight['ok'] is True
s=preflight['remote']['worker_status'];assert s['status']=='ready'and s['usage_ok']and not s['paused']and not s['hard_off']
manifest=json.loads((PACKAGE/'transfer-manifest.json').read_text());assert s['usage_bytes']+manifest['expected_added_bytes']<50*(1<<30)
prior=json.loads((OUT/'transfer-core-ledger.json').read_text());assert prior['entries'][-1]['status']=='started_consumed_before_call'
all_operations=[op for p in sorted(PACKAGE.glob('operations-*.json'))for op in json.loads(p.read_text())]
by_remote={op['remote']:op for op in all_operations};completed={}
for p in sorted(OUT.glob('transfer-operations-*.log')):
    for line in p.read_text().splitlines():
        if not line.startswith('{'):continue
        row=json.loads(line)
        if row.get('status')=='native_Paseo_text_RPC_write_readback_exact':
            expected=by_remote[row['path']]
            assert (row['bytes'],row['sha256'])==(expected['bytes'],expected['sha256'])
            completed[row['path']]=row
pending=[i for i in all_operations if i['remote']not in completed]
rpc=PACKAGE/'native_batch_rpc.mjs';code=rpc.read_text()
point='    stage = "native_CAS_write";'
insert='''    if (Buffer.from(previous.bytes).equals(bytes)) {
      process.stdout.write(JSON.stringify({status: 'native_Paseo_existing_file_exact', path: resolved, bytes: bytes.length, sha256: digest(bytes)}) + '\\n');
      continue;
    }
    if (Buffer.from(previous.bytes).length !== 0) throw new Error('existing mismatched nonempty file retained');
'''
assert code.count(point)==1
repair_rpc=PACKAGE/'native_batch_rpc_partial_continuation.mjs';repair_rpc.write_text(code.replace(point,insert+point))
ledger_path=OUT/'transfer-core-continuation-ledger.json';assert not ledger_path.exists()
ledger={'prior_consumed_ledger_preserved':'transfer-core-ledger.json','old_failure':'batch01 timeout240seconds; physical file outcomes retained',
        'same_manifest_sha256':hashlib.sha256((PACKAGE/'transfer-manifest.json').read_bytes()).hexdigest(),
        'exact_prior_readbacks':len(completed),'remaining_file_operations':len(pending),'preflight':s,'entries':[]}
for start in range(0,len(pending),32):
    label=f'partial-{start//32:02d}';operations=PACKAGE/(label+'.json');operations.write_text(json.dumps(pending[start:start+32],indent=2)+'\n')
    entry={'label':label,'status':'consumed_before_call','started_unix':time.time()};ledger['entries'].append(entry);ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
    with(OUT/('transfer-'+label+'.log')).open('w')as log:
        try:
            p=subprocess.run(['node',str(repair_rpc),'write-list',str(operations)],cwd=ROOT,stdout=log,stderr=log,timeout=600)
            entry.update(status='complete'if p.returncode==0 else 'failed',exit_code=p.returncode,finished_unix=time.time())
        except subprocess.TimeoutExpired:
            entry.update(status='timeout_unknown_last_operation_retained',finished_unix=time.time());ledger_path.write_text(json.dumps(ledger,indent=2)+'\n');raise
    ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
    assert p.returncode==0,label+' failed; preserve outcomes'
    print(label,'complete',flush=True)
ledger['status']='all_declared_core_transfer_complete_pending_remote_receiver';ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
