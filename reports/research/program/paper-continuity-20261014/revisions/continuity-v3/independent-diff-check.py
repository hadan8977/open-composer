import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

P=Path(__file__).resolve().parent;WT=Path('/root/codex-test/wt-paper-continuity-20261014')
ROOT=Path('/root/codex-test/open-composer')
resource.setrlimit(resource.RLIMIT_CPU,(100,120))
assert json.loads((ROOT/'reports/research/control/owner-compute-hold.json').read_text())['research_paused'] is False
def bind(path):
    p=Path(path)
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':h}
manifest=json.loads((P/'result-manifest.json').read_text())
parent=json.loads((P.parent/'continuity-v2/result-manifest.json').read_text())
old={x['path']:x for x in parent['code']};changed=[];inherited=[]
for item in manifest['code']:
    if item['path'] in old and item==old[item['path']]:inherited.append(item)
    else:
        assert bind(item['path'])==item;changed.append(item)
assert {Path(x['path']).name for x in changed}=={'forward_publication.py','forward_refresh_io.py','refresh_equity_book_live.py','test_forward_v3_recovery.py'}
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=WT,text=True).strip()=='a85d0bfcfdf4a4ea46f1ab772e7832b55b2f348b'
assert subprocess.check_output(['git','diff','--name-only'],cwd=WT,text=True).strip()==''
sys.path[:0]=[str(WT),str(WT/'scripts')]
import forward_publication as pub
from prepare_host_forward_version import sha256

checks=[]
with tempfile.TemporaryDirectory(prefix='review-post-restore-',dir=P) as tmp:
    root=Path(tmp);old=root/'old.parquet';out=root/'output.parquet';candidate=root/'candidate.parquet';source=root/'source.json'
    old.write_bytes(b'accepted-old');out.write_bytes(b'failed-natural');os.link(out,candidate);source.write_text('{}')
    head=root/'latest.json';receipt=root/'receipt.json';journal=root/'transactions/attempt.json'
    value={'status':'prepared','output':str(out),'baseline':str(old),'old_sha256':sha256(old),'candidate':str(candidate),'candidate_sha256':sha256(candidate),'output_before_sha256':sha256(out),'output_was_candidate_inode':True,'head':str(head),'previous_head_sha256':None,'receipt':str(receipt),'source_manifest':str(source),'source_manifest_sha256':sha256(source),'result':{'output':{'sha256':'nonmatching-new-composed'}}}
    pub.atomic_json(journal,value)
    original=pub.atomic_json
    def fail_status(path,obj):
        if path==journal and obj['status']=='rolled_back':raise OSError('injected after restored output, before rolled_back status')
        original(path,obj)
    pub.atomic_json=fail_status
    try:
        try:pub.finish_transaction(journal)
        except OSError:pass
        else:raise AssertionError('injected cutpoint not reached')
    finally:pub.atomic_json=original
    assert sha256(out)==sha256(old) and candidate.read_bytes()==b'failed-natural'
    assert json.loads(journal.read_text())['status']=='prepared'
    pub.recover_pending(root)
    assert json.loads(journal.read_text())['status']=='rolled_back'
    assert out.stat().st_ino!=candidate.stat().st_ino and not head.exists()
    checks.append({'id':'post_restore_pre_status_crash','pass':True,'retry':'existing prepared-old branch finishes rollback without overwriting retained candidate'})
    original_stat=pub.os.statvfs
    class NoRoom:
        f_bavail=0
        f_frsize=1
    pub.os.statvfs=lambda _:NoRoom()
    before=set(root.iterdir());out_before=out.read_bytes()
    try:
        try:pub.atomic_restore(old,out)
        except OSError as exc:assert 'insufficient disk' in str(exc)
        else:raise AssertionError('missing space refusal')
    finally:pub.os.statvfs=original_stat
    assert set(root.iterdir())==before and out.read_bytes()==out_before
    checks.append({'id':'restore_no_room_before_temp','pass':True,'output_and_candidate_preserved':True})
peak=json.loads((P/'actual-peak-admission.json').read_text())
print('peak keys',list(peak))
out={'changed_code_bindings_verified':changed,'unchanged_code_bindings_inherited':inherited,'additional_small_checks':checks,'author_six_tests_reused':True,'old147_tests_rerun':False,'large_data_or_archive_reads':0,'production_changes':0,'affinity':sorted(os.sched_getaffinity(0)),'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
(P/'independent-diff-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'changed_files':len(changed),'inherited_files':len(inherited),'checks':checks,'max_RSS_KiB':out['max_RSS_KiB']}))
