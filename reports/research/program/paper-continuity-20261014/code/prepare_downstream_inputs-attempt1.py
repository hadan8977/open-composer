"""Bounded existing-reader inputs, with lossless transport-only projections."""
import hashlib
import json
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT=Path.cwd();OUT=ROOT/'reports/research/program/paper-continuity-20261014';WT=Path('/root/codex-test/wt-paper-continuity-20261014')
sys.path.insert(0,str(WT));sys.path.insert(0,str(WT/'scripts'))
from prepare_host_forward_version import _batch_bytes
from open_composer.research.equity_book.signals import THEME_SIGNALS,THEMES
STAGE=OUT/'downstream-inputs';STAGE.mkdir(exist_ok=False)
items=[];projections=[];coverage=[]
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def bind(p,rel):return {'source_path':str(p),'relative_path':rel,'bytes':p.stat().st_size,'sha256':sha(p)}
def metadata(p):
    pf=pq.ParquetFile(p);r={'path':str(p),'rows':pf.metadata.num_rows,'max_dates':{}}
    for name in ['trade_date','month_end','filed','visible_at']:
        if name not in pf.schema_arrow.names:continue
        ci=pf.schema_arrow.names.index(name);maxima=[]
        for rg in range(pf.metadata.num_row_groups):
            s=pf.metadata.row_group(rg).column(ci).statistics
            if s is not None and s.has_min_max:maxima.append(str(s.max))
        r['max_dates'][name]=max(maxima)if maxima else None
    return r
def project(source,rel,columns):
    before=bind(source,source.relative_to(ROOT).as_posix())
    pf=pq.ParquetFile(source);schema=pa.schema([pf.schema_arrow.field(c)for c in columns])
    dest=STAGE/rel;dest.parent.mkdir(parents=True,exist_ok=True);digest=hashlib.sha256();rows=0
    with pq.ParquetWriter(dest,schema)as writer:
        for batch in pf.iter_batches(batch_size=32768,columns=columns):
            clean=pa.RecordBatch.from_arrays(list(batch.columns),schema=schema)
            digest.update(_batch_bytes(clean,schema));rows+=clean.num_rows;writer.write_batch(clean)
    got=hashlib.sha256()
    for batch in pq.ParquetFile(dest).iter_batches(batch_size=32768):got.update(_batch_bytes(batch,schema))
    assert got.hexdigest()==digest.hexdigest() and sha(source)==before['sha256']
    result=bind(dest,rel);items.append(result)
    projections.append({'source':before,'output':result,'columns':columns,'rows':rows,
        'exact_typed_occurrence_sha256':digest.hexdigest(),'purpose':'temporary private compute transport only; never replace the full feature product'})
    (OUT/'downstream-projection-progress.json').write_text(json.dumps(projections,indent=2)+'\n')
def add(source,rel=None):
    assert source.is_file(), source
    items.append(bind(source,rel or source.relative_to(ROOT).as_posix()))
    if source.suffix=='.parquet':coverage.append(metadata(source))
for source in sorted((ROOT/'data/features/daily_broad').glob('20*.parquet')):
    if int(source.stem)<2026:project(source,source.relative_to(ROOT).as_posix(),['trade_date','symbol','open','close','dollar_adv_63'])
for group in ['sec_fundamentals_daily','universe_broad']:
    for source in sorted((ROOT/'data/features'/group).glob('20*.parquet')):add(source)
for relative in ['data/features/universe/_asset_metadata.parquet','data/features/sic_map/sic_map.parquet',
                 'data/features/sec_fundamentals/facts.parquet','data/features/nsi/nsi.parquet']:
    add(ROOT/relative)
for group in ['insider_broad','short_volume_broad','short_interest','news_attention','alpha101_broad','alpha191_broad']:
    add(ROOT/f'data/features/{group}/2026.parquet')
for source in sorted((ROOT/'data/live/equity_book/panel').glob('20*.parquet')):
    if int(source.stem)<2026:add(source)
columns=['trade_date','symbol']+sorted({c for cs in THEME_SIGNALS.values()for c in cs})+[f'theme_{t}'for t in THEMES]
for source in sorted((ROOT/'data/live/equity_book/signals').glob('20*.parquet')):
    if int(source.stem)<2026:project(source,source.relative_to(ROOT).as_posix(),columns)
add(ROOT/'data/live/equity_book/signals/_alpha_columns.json')
add(ROOT/'data/research/equity_book/alpha/book_v1/formation_ic.parquet')
# Only the already fixed hedge ETF roster, using the frozen existing locator.
from open_composer.research.equity_book.panel import HEDGE_ETFS
layout_path=ROOT/'data/sip/daily/_LAYOUT.json';layout=json.loads(layout_path.read_text())
add(layout_path)
selected={sid:sorted(set(names)&set(HEDGE_ETFS))for sid,names in layout['shard_symbols'].items()if set(names)&set(HEDGE_ETFS)}
assert set(s for ss in selected.values()for s in ss)==set(HEDGE_ETFS)
for year in range(2016,2025):
    for sid,names in sorted(selected.items()):
        source=ROOT/f'data/sip/daily/{year}/shard-{sid}.parquet';add(source)
        actual=set(pq.read_table(source,columns=['symbol'])['symbol'].to_pylist())
        assert set(names)<=actual or not actual, (source,names)
code=['scripts/build_equity_book_panel.py','scripts/build_equity_book_risk.py','scripts/build_equity_book_signals.py',
      'scripts/build_book_v1_alpha.py','scripts/build_sec_sic_map.py',
      'open_composer/research/equity_book/__init__.py']
code+=[p.relative_to(WT).as_posix()for p in sorted((WT/'open_composer/research/equity_book').glob('*.py'))if p.name!='__init__.py']
for rel in code:add(WT/rel,rel)
assert len({i['relative_path']for i in items})==len(items)
result={'task_id':'PAPER-CONTINUITY-20261014','inputs':items,'projections':projections,'current_schema_coverage':coverage,
        'ETF_locator':{'binding':bind(layout_path,'data/sip/daily/_LAYOUT.json'),'selected_shards':selected},
        'source_requests':0,'broker_files_transferred':False,'numerical_strategy_execution':False,
        'input_bytes':sum(i['bytes']for i in items),'CPU_seconds_parent':time.process_time()}
(OUT/'downstream-input-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'files':len(items),'input_bytes':result['input_bytes'],'projections':len(projections),'CPU_seconds':time.process_time()}))

