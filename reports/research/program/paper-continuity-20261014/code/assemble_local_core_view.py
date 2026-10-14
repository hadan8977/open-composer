"""Read-only archive references; materialized corrections; private producer outputs."""
import hashlib
import json
import shutil
from pathlib import Path
ROOT=Path.cwd();OUT=ROOT/'reports/research/program/paper-continuity-20261014';WT=Path('/root/codex-test/wt-paper-continuity-20261014')
manifest=json.loads((OUT/'current-feature-input-manifest.json').read_text())
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
entries=[]
for item in manifest['inputs']:
    rel=item['relative_path']
    if not rel.startswith(('data/','baselines/')):continue
    source=Path(item['source_path']);assert source.stat().st_size==item['bytes']and sha(source)==item['sha256']
    dest=WT/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        assert sha(dest)==item['sha256'];continue
    # These directories are passed only to read-only feature APIs, never a fetcher.
    if rel.startswith('baselines/') or source.is_relative_to(OUT):
        shutil.copyfile(source,dest);mode='private_copy'
    else:dest.symlink_to(source);mode='readonly_input_reference_not_an_archive_writer_target'
    entries.append({**item,'private_path':str(dest),'mode':mode})
result={'entries':entries,'outputs_private':True,'source_requests':0,'archive_writers_permitted':False,'shared_production_changes':0}
(OUT/'local-core-view.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'assembled_paths':len(entries),'private_root':str(WT),'source_requests':0}))
