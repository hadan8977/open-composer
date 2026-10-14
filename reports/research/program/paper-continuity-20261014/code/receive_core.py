"""Verify declared incremental transfer and copy verified old inputs into a private root."""
import base64
import hashlib
import json
import shutil
from pathlib import Path

JOB=Path(r'C:\paseo\scratch\paper-continuity-forward-20261014')
OLD=Path(r'C:\paseo\scratch\host-freshness-azn-broad-20261012\root')
ROOT=JOB/'root'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

manifest=json.loads((JOB/'transfer/transfer-manifest.json').read_text(encoding='utf-8'))
assert str(JOB).casefold()==manifest['remote_scratch'].casefold()
assert not (JOB/'core-receive-receipt.json').exists()
archive=JOB/'transfer/input.zip'
with archive.open('xb') as output:
    for item in manifest['inputs']:
        path=JOB/'transfer'/Path(item['local_path']).name
        assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256']
        output.write(base64.b64decode(path.read_bytes(),validate=True))
assert archive.stat().st_size==manifest['archive']['bytes'] and sha(archive)==manifest['archive']['sha256']
ROOT.mkdir(exist_ok=False)
import zipfile
with zipfile.ZipFile(archive) as z:
    for member in z.infolist():
        p=Path(member.filename)
        assert not p.is_absolute() and '..' not in p.parts and ':' not in member.filename
    z.extractall(ROOT)
copied=[]
for item in manifest['reuse_inputs']:
    source=OLD/item['relative_path']; target=ROOT/item['relative_path']
    assert source.resolve().is_relative_to(OLD.resolve())
    assert source.is_file() and source.stat().st_size==item['bytes'] and sha(source)==item['sha256'], item['relative_path']
    target.parent.mkdir(parents=True,exist_ok=True)
    assert not target.exists()
    shutil.copyfile(source,target)
    copied.append(item['relative_path'])
runtime=json.loads((ROOT/'evidence/current-inputs.json').read_text(encoding='utf-8'))
for item in runtime['inputs']:
    p=ROOT/item['relative_path'];assert p.is_file() and p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],item['relative_path']
receipt={'all_current_inputs_exact':True,'files':len(runtime['inputs']),'bytes':sum(i['bytes']for i in runtime['inputs']),
         'copied_old_verified_paths':copied,'old_inputs_changed':False,'broker_files_transferred':False}
(JOB/'core-receive-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'all_current_inputs_exact':True,'files':len(runtime['inputs']),'old_reuse_count':len(copied)}))
