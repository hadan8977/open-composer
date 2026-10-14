"""Accept the complete retained parquet only after full prefix and suffix checks."""
import json
import sys
from datetime import UTC,datetime
from pathlib import Path
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
ROOT=Path.cwd();WT=Path('/root/codex-test/wt-paper-continuity-20261014');OUT=ROOT/'reports/research/program/paper-continuity-20261014'
sys.path.insert(0,str(WT/'scripts'))
from prepare_host_forward_version import _batch_bytes,sha256,verify_prefix
old=WT/'baselines/daily_broad-2026.parquet';temporary=WT/'data/features/daily_broad/2026.parquet.tmp';target=temporary.with_suffix('')
candidate=WT/'data/features/_bounded_actual02/daily_broad/2026.parquet'
assert not target.exists() and not (OUT/'compose-broad-recovery.json').exists()
assert sha256(old)=='5f7a8ae15a908af08843b3337ae436baa6c6f2fb80c32dd2b5c12243e9cd28b1'
schema=pq.ParquetFile(old).schema_arrow;prefix=verify_prefix(old,temporary)
cut=pa.scalar('2026-10-07').cast(schema.field('trade_date').type)
end=pa.scalar('2026-10-13').cast(schema.field('trade_date').type)
def suffix(path):
    batches=[]
    for batch in pq.ParquetFile(path).iter_batches(batch_size=32768,use_threads=False):
        dates=batch.column(schema.get_field_index('trade_date'))
        if pc.any(pc.greater(dates,end)).as_py():raise ValueError('unexpected future row')
        got=batch.filter(pc.greater(dates,cut))
        if got.num_rows:batches.append(pa.RecordBatch.from_arrays(list(got.columns),schema=schema))
    return pa.Table.from_batches(batches,schema=schema).combine_chunks()
actual=suffix(temporary);expected=suffix(candidate)
assert actual.num_rows==expected.num_rows>0
a=actual.to_batches(max_chunksize=32768);b=expected.to_batches(max_chunksize=32768)
assert len(a)==len(b) and all(_batch_bytes(x,schema)==_batch_bytes(y,schema)for x,y in zip(a,b,strict=True))
keys=list(zip(actual['symbol'].to_pylist(),actual['trade_date'].to_pylist(),strict=True))
assert len(keys)==len(set(keys)) and max(k[1]for k in keys)==end.as_py()
assert pq.ParquetFile(temporary).metadata.num_rows==prefix['rows']+actual.num_rows
digest=sha256(temporary)
temporary.replace(target)
result={'status':'complete_retained_candidate_verified_and_published_privately','version_id':'host-forward-v1-20261014',
    'failed_attempt_retained':'compose-broad-actual01-resource.txt','source_first_visible_certified':False,
    'baseline_sha256':sha256(old),'prefix_end':'2026-10-07','suffix_end':'2026-10-13',
    'prefix_verification':prefix,'suffix_rows':actual.num_rows,'suffix_exact_all48_typed_values_null_floatbits':True,
    'suffix_duplicate_keys':0,'prefix_suffix_overlap':0,'legacy_duplicate_occurrences_preserved':69,
    'legacy_duplicate_inventory':'reports/research/program/day-goal-20261011-2/host-freshness-repair/recovery-preparation/hadan-package/key-attribution/duplicate-keys-old.csv',
    'output':{'path':str(target),'bytes':target.stat().st_size,'sha256':digest},
    'natural_candidate':{'path':str(candidate),'sha256':sha256(candidate)},
    'available_at_UTC':datetime.now(UTC).isoformat(),'original_whole_panel_invariance_pass':None,'production_changes':0}
(OUT/'compose-broad-recovery.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
