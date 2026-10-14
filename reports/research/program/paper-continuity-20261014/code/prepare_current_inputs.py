"""Freeze only known feature-builder inputs and accepted source-view corrections."""
import collections
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path.cwd()
OUT = ROOT / 'reports/research/program/paper-continuity-20261014'
STAGE = OUT / 'local-inputs'
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
OLD = ROOT / 'reports/research/program/day-goal-20261011-2'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def binding(source, relative):
    before=source.stat()
    digest=sha(source)
    after=source.stat()
    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns), source
    return {'source_path':str(source),'relative_path':relative,'bytes':after.st_size,'sha256':digest}

def main():
    started=time.process_time()
    STAGE.mkdir(exist_ok=False)
    items={}
    for group in ('data/sip/daily','data/sip-delisted/by_year'):
        for year in (2025,2026):
            for source in sorted((ROOT/group/str(year)).glob('*.parquet')):
                rel=source.relative_to(ROOT).as_posix(); items[rel]=binding(source,rel)
    for group in ('universe','universe_broad'):
        for source in sorted((ROOT/'data/features'/group).glob('20*.parquet')):
            rel=source.relative_to(ROOT).as_posix(); items[rel]=binding(source,rel)
    source=ROOT/'data/features/intraday_daily/2026.parquet'
    items[source.relative_to(ROOT).as_posix()]=binding(source,source.relative_to(ROOT).as_posix())
    original_items=list(items.values())
    corrections=[]
    # Re-materialize the same twenty quarantined keys against actual current bytes.
    qm=OLD/'host-freshness-repair/recovery-preparation/quarantine-manifest.json'
    q=json.loads(qm.read_text()); rel='data/sip/daily/'+q['target_shard']; source=ROOT/rel
    table=pq.read_table(source); wanted={tuple(k) for k in q['quarantine_keys']}
    keys=list(zip(table['symbol'].to_pylist(),[str(d)[:10] for d in table['timestamp'].to_pylist()],strict=True))
    mask=pa.array([k in wanted for k in keys]); removed=table.filter(mask)
    assert removed.num_rows==len(wanted) and {k for k in keys if k in wanted}==wanted
    dest=STAGE/'azn-filtered.parquet'; pq.write_table(table.filter(pc.invert(mask)),dest)
    quarantine=STAGE/'azn-quarantined.parquet';pq.write_table(removed,quarantine)
    corrections.append({'kind':'same20AZNcompatibilitykeys_current_source','original':items[rel],
                        'historical_source_sha256':q['expected_source_sha256'],'keys':q['quarantine_keys'],
                        'quarantine':binding(quarantine,'evidence/azn-quarantined.parquet')})
    items[rel]=binding(dest,rel)
    # Only exact old canonical observations may collapse raw multiplicity.
    canonical_source=OLD/'host-exact-observation-materialization/canonical-observations.parquet'
    canonical=pq.read_table(canonical_source)
    ckeys=list(zip(canonical['symbol'].to_pylist(),canonical['timestamp'].to_pylist(),strict=True))
    assert len(ckeys)==len(set(ckeys))==69
    for label,rel in [('primary','data/sip/daily/2026/shard-0397.parquet'),
                      ('delisted','data/sip-delisted/by_year/2026/delisted-broad-batch-0226.parquet')]:
        table=pq.read_table(ROOT/rel)
        keys=list(zip(table['symbol'].to_pylist(),table['timestamp'].to_pylist(),strict=True))
        positions=collections.defaultdict(list)
        for ordinal,key in enumerate(keys):positions[key].append(ordinal)
        assert all(len(positions[key])==1 for key in ckeys), label
        selected=table.take(pa.array([positions[key][0] for key in ckeys]))
        assert selected.equals(canonical,check_metadata=False), 'canonical fields changed: '+label
        keep=pa.array([key not in set(ckeys) for key in keys])
        remainder=table.filter(keep);dest=STAGE/(label+'-remainder.parquet');pq.write_table(remainder,dest)
        corrections.append({'kind':'canonical69exact_current_observations','original':items[rel],
                            'source_rows':table.num_rows,'canonical_references':69,'remaining_rows':remainder.num_rows,
                            'all_canonical_typed_fields_equal':True})
        items[rel]=binding(dest,rel)
    rel='data/sip/daily/2026/shard-forward-worx-canonical.parquet'
    items[rel]=binding(canonical_source,rel)
    for group in ('daily','daily_broad'):
        source=OLD/'host-freshness-repair/recovery-preparation/actual-pilot/baselines'/f'{group}-2026.parquet'
        rel=f'baselines/{group}-2026.parquet';items[rel]=binding(source,rel)
    for rel in ['scripts/build_daily_features.py','scripts/prepare_host_forward_version.py',
                'open_composer/__init__.py','open_composer/research/__init__.py',
                'open_composer/research/features/__init__.py','open_composer/research/features/daily_features.py',
                'open_composer/research/features/price_hygiene.py','open_composer/research/features/universe.py',
                'open_composer/research/features/intraday_daily.py']:
        items[rel]=binding(WT/rel,rel)
    oldmanifest=json.loads((OLD/'host-freshness-repair/recovery-preparation/hadan-package/transfer-manifest.json').read_text())
    oldbindings={i['relative_path']:i for i in oldmanifest['original_files']}
    reusable=[];changed=[]
    for item in items.values():
        old=oldbindings.get(item['relative_path'])
        if old and (old['bytes'],old['sha256'])==(item['bytes'],item['sha256']):reusable.append(item['relative_path'])
        else:changed.append(item['relative_path'])
    result={'task_id':'PAPER-CONTINUITY-20261014','scope':'private natural 2026 daily/daily_broad; source 2025+2026',
            'prefix_end':'2026-10-07','suffix_end':'2026-10-13','version_id':'host-forward-v1-20261014',
            'inputs':list(items.values()),'original_source_bindings':original_items,'source_corrections':corrections,
            'reuse_candidate_paths_only_pending_remote_hash':reusable,'new_or_changed_paths':changed,
            'input_bytes':sum(i['bytes'] for i in items.values()),'process_CPU_seconds':time.process_time()-started,
            'broker_files_transferred':False,'source_requests':0,'historical_invariance_pass':None}
    (OUT/'current-feature-input-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['inputs','original_source_bindings','source_corrections','reuse_candidate_paths_only_pending_remote_hash','new_or_changed_paths']}))
    print('reuse candidates',len(reusable),'changed',len(changed))

if __name__=='__main__':main()
