"""Original historical reader files remain read-only; writable current files are private."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd();OUT=ROOT/'reports/research/program/paper-continuity-20261014';WT=Path('/root/codex-test/wt-paper-continuity-20261014')
manifest=json.loads((OUT/'downstream-input-manifest.json').read_text())
projections={i['output']['relative_path']:i['source']for i in manifest['projections']}
entries=[]
for item in manifest['inputs']:
    rel=item['relative_path']
    if not rel.startswith('data/'):continue
    source=Path(projections[rel]['source_path']if rel in projections else item['source_path'])
    target=WT/rel
    if target.exists():continue
    target.parent.mkdir(parents=True,exist_ok=True)
    current_writable=(rel.startswith('data/features/')and rel.endswith('/2026.parquet')and
        any('/'+g+'/'in rel for g in ['sec_fundamentals_daily','insider_broad','short_volume_broad','short_interest','news_attention']))
    if current_writable:shutil.copyfile(source,target);mode='private_writable_copy'
    else:target.symlink_to(source);mode='readonly_existing_reader_input_reference'
    entries.append({'source_path':str(source),'private_path':str(target),'mode':mode,'bytes':source.stat().st_size})
# Current insider, short interest, short volume and attributed-news source paths only.
for relative in ['data/raw/finra_short_interest/parsed.parquet','data/raw/finra_short_volume/parsed.parquet']:
    source=ROOT/relative;target=WT/relative
    if source.exists()and not target.exists():target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(source)
for relative in ['data/raw/insider/parsed','data/raw/insider/tail/parsed','data/features/news_attention/_articles']:
    source=ROOT/relative;target=WT/relative
    if source.is_dir()and not target.exists():target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(source)
source=ROOT/'data/features/news_attention/_articles_index.json';target=WT/'data/features/news_attention/_articles_index.json'
if source.exists()and not target.exists():target.symlink_to(source)
# Do not transfer or link account/credential files, and do not run source writers.
(OUT/'private-downstream-view.json').write_text(json.dumps({'entries':entries,'shared_writes':0,'archive_writers_permitted':False},indent=2)+'\n')
print(json.dumps({'new_private_references_or_copies':len(entries),'shared_writes':0}))
