"""Small binding/resource seal for the three accepted-scope repairs."""
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
HERE = Path(__file__).resolve().parent
V2 = HERE.parent / 'continuity-v2'


def binding(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': digest}


def profile(path):
    text = path.read_text()
    def number(label):
        match = re.search(r'^\s*'+re.escape(label)+r':\s*([0-9.]+)', text, re.M)
        return float(match.group(1)) if match else None
    user, system = number('User time (seconds)'), number('System time (seconds)')
    assert user is not None and system is not None
    return {'path': str(path), 'CPU_seconds': round(user+system, 2),
            'MaxRSS_KiB': number('Maximum resident set size (kbytes)'),
            'exit_status': number('Exit status')}


parent = json.loads((V2 / 'result-manifest.json').read_text())
commit = subprocess.check_output(['git', '-C', str(WT), 'rev-parse', 'HEAD'], text=True).strip()
changed = subprocess.check_output(['git', '-C', str(WT), 'diff', '--name-only', 'de3a57c', commit], text=True).splitlines()
(HERE / 'revision.patch').write_bytes(subprocess.check_output(['git', '-C', str(WT), 'diff', '--binary', 'de3a57c', commit]))
(HERE / 'complete-isolated-recovery.patch').write_bytes(subprocess.check_output(['git', '-C', str(WT), 'diff', '--binary', '4ae010a', commit]))
old = {Path(v['path']).relative_to(WT).as_posix(): v for v in parent['code']}
redirects = []
for relative in changed:
    if relative in old:
        before = HERE / 'before' / Path(relative).name
        proof = binding(before)
        assert proof['sha256'] == old[relative]['sha256']
        redirects.append({'prior_binding': old[relative], 'retained_before': proof})
(HERE / 'retained-v2-code.json').write_text(json.dumps({'prior_commit':'de3a57c','bindings':redirects}, indent=2)+'\n')
jobs = [profile(p) for p in sorted(HERE.glob('*resource.txt'))]
new_cpu = round(sum(v['CPU_seconds'] for v in jobs), 2)
# The measured child profiles exclude admission launcher and this small seal;
# 30 CPU conservatively charge all such reads/setup/lint/git/sealing once.
author_charge = round(13139.4 + 13.95 + new_cpu + 30, 2)
resource = {'cap_CPU_seconds':24000, 'prior_v2_charge_including_ee17_10':13139.4,
            'new_ee_review_charge_once':13.95, 'new_author_measured_CPU_seconds':new_cpu,
            'new_setup_reads_lint_git_seal_unknown_upper_charge_CPU_seconds':30,
            'charged_CPU_seconds_before_Root_pending_settlement':author_charge,
            'Root_reserved_CPU_seconds':1000,
            'Root_known20_25_and_archive_installation_costs':'pending Root settlement against this 1000 reserve; not also charged here',
            'charged_plus_reserved_CPU_seconds':round(author_charge+1000,2),
            'remaining_unreserved_CPU_seconds':round(24000-author_charge-1000,2),
            'old_failures_and_unknown_preserved':True,'other_task_pools_used':False,'jobs':jobs,
            'actual_job_memory_cap_MiB':400,'CPU_affinity':[0]}
(HERE / 'resource-ledger.json').write_text(json.dumps(resource,indent=2)+'\n')
peak=json.loads((HERE/'actual-peak-admission.json').read_text())
st=os.statvfs(ROOT); available=st.f_bavail*st.f_frsize
capacity={'as_of_UTC':datetime.now(UTC).isoformat(),'actual_Available_bytes':available,
          'installation_bytes':peak['installation_bytes'],
          'normal_refresh_required_Available_bytes':peak['required_available_bytes'],
          'install_plus_refresh_gap_bytes':max(0,peak['installation_bytes']+peak['required_available_bytes']-available),
          'ready_after_install':available-peak['installation_bytes']>=peak['required_available_bytes'],
          'Root_archive6768_release_assumed':False,'Root_archive_paths_touched':False}
(HERE/'current-capacity.json').write_text(json.dumps(capacity,indent=2)+'\n')
code_paths={Path(v['path']) for v in parent['code']}|{WT/v for v in changed}
result={'schema_version':1,'task_id':'PAPER-CONTINUITY-20261014','revision':'continuity-v3',
        'author':'f9add224-744b-471c-b812-c43cc179fa38','author_self_approval':False,
        'state':'complete_reviewable_three_fix_package_pending_Root_and_independent_acceptance',
        'commit':commit,'worktree':str(WT),'base_commit':'de3a57c',
        'parent_manifest':binding(V2/'result-manifest.json'),
        'independent_required_corrections':binding(V2/'independent-maintenance-review.json'),
        'corrections':{'V2-R1':'separate temporary inode plus atomic accepted-backup restore retains failed natural SHA',
                       'V2-R2':'recorded natural output/pre-replace state rolls back with retained candidate; v2 same-inode compatibility; independent changes reject',
                       'V2-R3':'stat inventory and admission before view copy; old named theme/risk/year partitions reference-only, current writers detached; prior-year copy and rollback temp explicitly counted'},
        'focused_tests':6,'old147_or_large_panel_rerun':False,
        'test_log':binding(HERE/'tests-final-log.txt'),'runtime':binding(HERE/'runtime-readback.json'),
        'data_manifest_reused':binding(V2/'data-installation-manifest.json'),
        'forward_config_reused':binding(V2/'forward-config.json'),
        'new_source_requests':0,'broker_calls_or_orders':0,'business_data_changes':0,
        'production_changes':0,'ETF_or_capital_ratio_changes':0,'archive_cleanup_actions':0,
        'capacity':capacity,'resource':resource,
        'handoff':'Root triggers ee limited difference review after this author turn ends; no fifth active reviewer created'}
(HERE/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(HERE/'current-state.json').write_text(json.dumps({'state':result['state'],'sourcehash':{'parent':parent['parent_manifest']['sha256'],'v2':result['parent_manifest']['sha256'],'commit':commit},'coverage':{'V2_R1_R2_R3':True,'focused_tests':6,'new_source_requests':0},'real_gap':capacity,'cumulative':resource,'next':result['handoff']},indent=2)+'\n')
proofs=[binding(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='result-manifest.json']
manifest={'schema_version':1,'task_id':result['task_id'],'revision':'continuity-v3','author':result['author'],
          'author_self_approval':False,'parent_manifest':result['parent_manifest'],
          'code':[binding(p) for p in sorted(code_paths)],'data':parent['data'],
          'data_value_hashes_reused_without_large_rehash':True,'proofs':proofs,
          'production_integration_by_Root_only':True}
(HERE/'result-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'manifest':binding(HERE/'result-manifest.json'),'commit':commit,
                  'code_files':len(manifest['code']),'data_entries':len(manifest['data']),
                  'resource':{k:v for k,v in resource.items() if k!='jobs'},'capacity':capacity}))
