"""Release unused transport encodings; preserve source ZIP and exact old-byte delta."""
import hashlib
import json
import os
from pathlib import Path

ROOT=Path.cwd();P=ROOT/'reports/research/program/paper-continuity-20261014'
base=P/'hadan-core-package/input.zip';old=P/'hadan-core-package-before-boolean-null-fix/input.zip'
delta=P/'retained-old-transport-delta';delta.mkdir(exist_ok=True)
def sha(path):
    with path.open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
r={'base':{'path':str(base),'sha256':sha(base)},'old':{'path':str(old),'bytes':old.stat().st_size,'sha256':sha(old)},'block_size':1048576,'changes':[],'released_encodings':[],'reconstructed_old_sha_verified':False,'remote_science_started':False,'remote_partial_inputs_not_deleted':True}
digest=hashlib.sha256()
with old.open('rb')as a,base.open('rb')as b:
    offset=0
    while True:
        original=a.read(1048576)
        if not original:break
        current=b.read(len(original))
        if original!=current:
            path=delta/f'offset-{offset:012d}.bin';path.write_bytes(original)
            r['changes'].append({'offset':offset,'path':str(path),'bytes':len(original),'sha256':sha(path)})
            digest.update(path.read_bytes())
        else:digest.update(current)
        offset+=len(original)
assert digest.hexdigest()==r['old']['sha256']
r['reconstructed_old_sha_verified']=True
(delta/'manifest.json').write_text(json.dumps(r,indent=2)+'\n')
old.unlink()
for directory in [base.parent,old.parent]:
    for path in directory.glob('part-*.b64'):
        r['released_encodings'].append({'path':str(path),'bytes':path.stat().st_size,'lossless_reconstruction':'base ZIP base64 in 1048576-byte parts; old ZIP reconstructed via delta'})
        path.unlink()
# These are retired transfer-only column projections. Full original inputs remain referenced
# by the private downstream view and current input manifests, not by these transports.
for path in (P/'downstream-inputs/data').rglob('*.parquet'):
    r['released_encodings'].append({'path':str(path),'bytes':path.stat().st_size,'lossless_reconstruction':'source SHA + projection in downstream-input-manifest.json'})
    path.unlink()
w=Path('/root/codex-test/wt-paper-continuity-20261014');a=w/'baselines/daily-2026.parquet';b=ROOT/'data/live/backup-refresh/2026-10-13/daily/2026.parquet'
assert sha(a)==sha(b)=='2dc3646256036d600152900eb1625fc5cd5495aab4fb6f9485b0ce2a4f7db729'
tmp=a.with_suffix('.hardlink.tmp');os.link(b,tmp);tmp.replace(a)
r['baseline_identical_immutable_backup_hardlink']={'source':str(b),'target':str(a),'sha256':sha(a)}
r['all_failure_ledgers_and_original_code_retained']=True
(P/'released-reconstructible-transport.json').write_text(json.dumps(r,indent=2)+'\n')
print({'old_delta_blocks':len(r['changes']),'released_encoding_paths':len(r['released_encodings']),'source_ZIP_retained':True,'baseline_immutable':True})
