"""Seal the narrow maintenance revision; parent artifacts remain unchanged."""
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT=Path('/root/codex-test/open-composer')
WT=Path('/root/codex-test/wt-paper-continuity-20261014')
P=ROOT/'reports/research/program/paper-continuity-20261014'
HERE=Path(__file__).resolve().parent


def sha(p):
    with p.open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()


def binding(p):
    return {'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':sha(p)}


def profile(path):
    value=path.read_text()
    def number(label):
        match=re.search(r'^\s*'+re.escape(label)+r':\s*([0-9.]+)',value,re.M)
        return float(match.group(1)) if match else None
    user, system=number('User time (seconds)'),number('System time (seconds)')
    return {'path':str(path),'CPU_seconds':round(user+system,2) if user is not None and system is not None else None,'MaxRSS_KiB':number('Maximum resident set size (kbytes)'), 'reported_exit':number('Exit status')}


def main():
    parent=json.loads((P/'result-manifest.json').read_text())
    head=subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip()
    delta=subprocess.check_output(['git','-C',str(WT),'diff','--name-only','515a233',head],text=True).splitlines()
    (HERE/'revision.patch').write_bytes(subprocess.check_output(['git','-C',str(WT),'diff','--binary','515a233',head]))
    (HERE/'complete-isolated-recovery.patch').write_bytes(subprocess.check_output(['git','-C',str(WT),'diff','--binary','4ae010a',head]))
    redirects=[]
    for item in parent['code']:
        before=HERE/'before'/Path(item['path']).relative_to(WT)
        if before.exists():
            assert sha(before)==item['sha256']
            redirects.append({'old':item,'retained':binding(before)})
    (HERE/'prior-code-bindings-retained.json').write_text(json.dumps({'prior_commits':['a8ad99c','515a233'],'old_manifest_retained_bytewise':True,'redirects':redirects},indent=2)+'\n')
    code_paths={Path(v['path']) for v in parent['code']}|{WT/v for v in delta}
    code=[binding(p) for p in sorted(code_paths)]
    installation=json.loads((HERE/'data-installation-manifest.json').read_text())
    paths=sorted(HERE.glob('*resource.txt'))+sorted((P/'disk-recovery').glob('*resource.txt'))
    jobs=[profile(p) for p in paths]
    assert all(v['CPU_seconds'] is not None for v in jobs)
    measured=round(sum(v['CPU_seconds'] for v in jobs),2)
    original=json.loads((P/'resource-ledger.json').read_text())
    prior_review=json.loads((P/'independent-maintenance-review.json').read_text())['resource']
    review_seal=profile(P/'independent-maintenance-seal-resource.txt')
    independent_charge=round(prior_review['check_measured_outer_CPU']+review_seal['CPU_seconds']+prior_review['unmetered_small_reads_setup_seal_handoff_upper_charge_CPU'],2)
    charge=round(original['charged_or_reserved_CPU_seconds']+measured+180+independent_charge,2)
    resource={'cap_CPU_seconds':24000,'parent_author_charge_retained':original['charged_or_reserved_CPU_seconds'],'parent_ledger':binding(P/'resource-ledger.json'),'prior_independent_maintenance_charge_once':independent_charge,'new_measured_outer_CPU_seconds':measured,'unknown_local_reads_hashes_format_git_setup_and_final_seal_upper_charge_CPU_seconds':180,'charged_or_reserved_CPU_seconds':charge,'remaining_CPU_seconds':round(24000-charge,2),'jobs':jobs,'all_failed_attempts_retained':True,'other_task_pools_used':False,'one_core_affinity':0,'new_actual_job_memory_cap_MiB':400}
    (HERE/'resource-ledger.json').write_text(json.dumps(resource,indent=2)+'\n')
    disk=json.loads((HERE/'actual-disk-admission.json').read_text())
    stat=os.statvfs(ROOT);available=stat.f_bavail*stat.f_frsize
    install_bytes=installation['total_installation_bytes']
    capacity={'as_of_UTC':datetime.now(UTC).isoformat(),'actual_Available_bytes':available,'installation_bytes':install_bytes,'next_normal_refresh_required_Available_bytes':disk['required_available_bytes'],'projected_after_install_Available_bytes':available-install_bytes,'additional_space_required_for_install_plus_next_refresh_bytes':max(0,disk['required_available_bytes']+install_bytes-available),'installation_space_sufficient':available>=install_bytes,'next_normal_refresh_admitted_after_install':available-install_bytes>=disk['required_available_bytes'],'actual_own_recovery':binding(P/'disk-recovery/actual-recovery.json'),'external_filesystem_changes_not_claimed_as_own_cleanup':True,'next_action':'Root resource decision/authorized disk recovery beyond the exhausted narrow duplicate candidates before normal refresh; no source/strategy relaxation'}
    (HERE/'current-capacity.json').write_text(json.dumps(capacity,indent=2)+'\n')
    result={'schema_version':1,'task_id':'PAPER-CONTINUITY-20261014','revision':'continuity-v2','author':'f9add224-744b-471c-b812-c43cc179fa38','author_self_approval':False,'state':'complete_reviewable_revision_actual_capacity_blocker','worktree':str(WT),'commits':['a8ad99c','515a233',head],'parent_result_manifest':binding(P/'result-manifest.json'),'required_corrections_addressed':{'M1':'freeze mutable monthly prerequisites after actual production and before consumer; frozen copies plus source verification','M2':'normal run_plan stages natural products in private view and publishes exact accepted prefixes/causal suffix; 9 reader heads; current-year persistence with complete risk/IC math','M3':'real initial and per-stage Available admission, no-op skipping, immutable snapshot reuse, prepared data/metadata publication journals and exact recovery'},'validation':{'focused_tests':15,'current_log':binding(HERE/'tests-revision-log.txt'),'lint':binding(HERE/'lint-accepted-candidate-log.txt'),'actual_existing_duplicate_prefix':binding(HERE/'actual-duplicate-prefix-verification.json'),'native_dry_run':binding(HERE/'native-dry-run-log.txt'),'previous_data_targets_and_100_order_safety_tests':'Root accepted prior evidence reused; no repeated price/plan or economic run'},'data_values_modified_since_parent':False,'data_installation_entries':len(installation['entries']),'feature_heads_output_path_normalized':8,'new_reader_heads':9,'actual_source_requests':0,'broker_reads':0,'broker_writes':0,'economic_calculations':0,'production_or_ETF_mutations':0,'capital_ratio_changes':0,'production_integrated':False,'resource_ready':capacity['next_normal_refresh_admitted_after_install'],'capacity':capacity,'resource':resource,'required_external_decisions':['Root limited code/safety difference acceptance after owner turn release','Root supply actual disk headroom before the next normal refresh; author narrow cleanup cannot discard unique source/results or other owners data']}
    (HERE/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (HERE/'current-state.json').write_text(json.dumps({'state':result['state'],'sourcehash':{'parent_manifest':sha(P/'result-manifest.json'),'revision_commit':head},'coverage':{'M1_M2_M3':True,'focused_tests':15,'reader_heads':9,'new_source_requests':0},'real_gap':capacity,'cumulative_CPU':charge,'next':'Root independent difference review and required disk capacity; current author turn ends to release slot'},indent=2)+'\n')
    # Small proofs only. Accepted large data are bound by their original hashes,
    # not needlessly replayed or rehashed in this same-semantics revision.
    proofs=[binding(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name not in {'result-manifest.json'}]
    proofs += [binding(p) for p in sorted((P/'disk-recovery').glob('*')) if p.is_file() and p.suffix in {'.json','.py','.txt'}]
    manifest={'schema_version':1,'task_id':'PAPER-CONTINUITY-20261014','author':result['author'],'author_self_approval':False,'parent_manifest':binding(P/'result-manifest.json'),'code':code,'data':installation['entries'],'proofs':proofs,'source_retention_encoding_changed_without_source_byte_loss':{'delta':binding(P/'disk-recovery/exact-current-zip-delta.json'),'original_SHA256':'1e00afb87e8bb7ebbc1d3c0026fa5188e74013b5224b6a4dca8781a1b9657f19','physical_container_reconstructible_offline':True},'production_integration_by_Root_only':True,'current_capacity_blocker':binding(HERE/'current-capacity.json')}
    (HERE/'result-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'commit':head,'manifest_SHA256':sha(HERE/'result-manifest.json'),'code_files':len(code),'data_entries':len(installation['entries']),'CPU_charge':charge,'capacity':capacity}))


if __name__=='__main__':main()
