import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

P=Path(__file__).resolve().parent; WT=Path('/root/codex-test/wt-paper-continuity-20261014')
resource.setrlimit(resource.RLIMIT_CPU,(440,460))
sys.path[:0]=[str(WT),str(WT/'scripts')]
import pyarrow as pa
import pyarrow.parquet as pq
import forward_publication as publication
import forward_refresh_io as io
import forward_feature_epoch as epoch
from scripts import refresh_equity_book_live as rf

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
manifest=json.loads((P/'result-manifest.json').read_text())
checked=[]
for item in manifest['code']:
    path=Path(item['path']);assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256'],str(path)
    checked.append(item)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=WT,text=True).strip()=='de3a57c3e6e781bcd33aba9f71e7a9180e156399'
def frame(path,days,values):
    path.parent.mkdir(parents=True,exist_ok=True)
    pq.write_table(pa.table({'symbol':['A']*len(days),'trade_date':pa.array(days).cast(pa.timestamp('ns')),'value':values}),path)
def config(root,old):
    source=root/'source.json';source.write_text('{"corrected_bindings":[]}')
    return {'year':2026,'version_id':'test','anchor_end':'2026-10-13','version_directory':'versions','tables':{'nsi':{'anchor_sha256':sha(old)}},'runtime_context_manifest':str(source),'runtime_source_manifest':str(source)}
results=[]
with tempfile.TemporaryDirectory(prefix='review-small-',dir=P) as tmp:
    root=Path(tmp);features=root/'data/features';out=features/'nsi/nsi.parquet'
    frame(out,['2026-10-13'],[1.]);old_hash=sha(out);cfg=config(root,out)
    rf.ROOT=root;rf.FEATURES=features;rf.BACKUP_ROOT=root/'backup';rf.STAGE_ROOT=features/'_tmp'
    io.stage_admission=lambda *a:None
    produced=[]
    def runner(argv,**kw):
        frame(out,['2026-10-13','2026-10-14','2026-10-14'],[99.,2.,3.]);produced.append(sha(out))
        return subprocess.CompletedProcess(argv,0,'','')
    rc=rf.run_upstream_table(rf.table_by_name('nsi'),date(2026,10,14),[rf.Step('up:nsi','build test',['inert'])],runner,forward_config=cfg)
    assert rc==rf.EXIT_UPSTREAM and sha(out)==old_hash
    retained=next((root/'versions/natural-candidates/2026-10-14').glob('*.parquet'))
    assert sha(retained)==old_hash and sha(retained)!=produced[0]
    results.append({'id':'inplace_failed_natural_retention','finding':'confirmed_retained_natural_inode_overwritten_by_copy2_rollback','produced_natural_sha':produced[0],'retained_after_rollback_sha':sha(retained),'old_published_sha':old_hash,'same_inode':out.stat().st_ino==retained.stat().st_ino})
with tempfile.TemporaryDirectory(prefix='review-prepared-',dir=P) as tmp:
    root=Path(tmp);old=root/'old.parquet';out=root/'out.parquet'
    frame(old,['2026-10-13'],[1.]);frame(out,['2026-10-13','2026-10-14'],[99.,2.]);cfg=config(root,old)
    replace=Path.replace
    def fail_before_replace(self,target):
        if self.name.endswith('.forward.parquet') and Path(target)==out:raise OSError('injected before inplace output replacement')
        return replace(self,target)
    Path.replace=fail_before_replace
    try:
        try:epoch.publish_forward_table(root,'nsi',old,out,out,date(2026,10,14),cfg)
        except OSError:pass
        else:raise AssertionError('injection not reached')
    finally:Path.replace=replace
    journal=next((root/'versions/transactions').glob('*.json'));assert json.loads(journal.read_text())['status']=='prepared'
    try:publication.recover_pending(root/'versions')
    except ValueError as exc:
        assert 'matches neither accepted version' in str(exc)
        results.append({'id':'inplace_prepared_before_replace','finding':'confirmed_prepared_output_is_natural_not_old_and_recovery_refuses','error':str(exc)})
    else:raise AssertionError('expected unhandled inplace pre-replace state')
with tempfile.TemporaryDirectory(prefix='review-disk-',dir=P) as tmp:
    root=Path(tmp);live=root/'live';live.mkdir()
    cfg={'version_directory':'versions','disk_spill_bound_bytes':1}
    # Stat-only synthetic old artifact; no actual parquet reader or large data.
    baseline=io.disk_admission(root,cfg,source_root=root,tables=[],live=live,stages=['alpha'],year=2026,fetch=False)
    prior=live/'alpha/book_v1/themes_2025.parquet';prior.parent.mkdir(parents=True);prior.write_bytes(b'x'*4096)
    later=io.disk_admission(root,cfg,source_root=root,tables=[],live=live,stages=['alpha'],year=2026,fetch=False)
    assert baseline['required_available_bytes']==later['required_available_bytes']
    view=io.live_view(root,cfg,live);copy=view/'alpha/book_v1/themes_2025.parquet'
    assert not copy.is_symlink() and copy.stat().st_ino!=prior.stat().st_ino and copy.read_bytes()==prior.read_bytes()
    results.append({'id':'unbudgeted_historical_live_view_copy','finding':'old_theme_copied_physically_but_initial_peak_unchanged','additional_copy_bytes':copy.stat().st_size,'required_before':baseline['required_available_bytes'],'required_after':later['required_available_bytes']})
out={'code_bindings_verified':checked,'checks':results,'reused_tests':15,'old147_not_rerun':True,'market_or_broker_calls':0,'production_mutations':0,'large_data_scans':0,'affinity':sorted(os.sched_getaffinity(0)),'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
(P/'independent-behavior-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'checks':results,'max_RSS_KiB':out['max_RSS_KiB'],'code_count':len(checked)},indent=2))
