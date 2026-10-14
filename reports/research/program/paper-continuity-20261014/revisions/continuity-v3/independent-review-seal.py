import hashlib
import json
import subprocess
from datetime import UTC,datetime
from pathlib import Path

P=Path(__file__).resolve().parent;TASK=P.parents[1];WT=Path('/root/codex-test/wt-paper-continuity-20261014')
def bind(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(p),'sha256':h,'bytes':p.stat().st_size}
assert subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=WT,text=True).strip()==''
m=json.loads((P/'result-manifest.json').read_text()); verified=[]
for group in m.values():
    if isinstance(group,list):
        for item in group:
            if isinstance(item,dict) and {'path','sha256','bytes'}<=item.keys() and str(item['path']).startswith(str(P)):
                p=Path(item['path']);assert item['bytes']<2_000_000
                actual=bind(p);assert actual=={k:item[k] for k in ('path','sha256','bytes')}
                verified.append(actual)
peak=json.loads((P/'actual-peak-admission.json').read_text());terms=peak['terms']
assert sum(terms.values())==peak['required_available_bytes']==9533075101
assert sum(x['bytes'] for x in peak['live_view_inventory'] if x['mode']=='copy')==terms['live_view_physical_copies_bytes']==8662907
assert sum(x['bytes'] for x in peak['link_prior_years_inventory'])==terms['link_prior_years_physical_copies_bytes']==72052932
assert len(peak['link_prior_years_inventory'])==20
release_path=TASK/'disk-recovery/root-cold-feature-release.json';release=json.loads(release_path.read_text())
assert release['state']=='verified_archive_local_storage_released' and release['remote_MD5_matches']==24 and len(release['released'])==24
assert release['available_after']==11345170432
installation=1135210477;headroom=release['available_after']-installation-peak['required_available_bytes']
assert headroom==676884854
proof=json.loads((P/'independent-diff-verification.json').read_text())
report={'schema_version':1,'task_id':'PAPER-CONTINUITY-20261014','revision':'continuity-v3','at_utc':datetime.now(UTC).isoformat(),'author':'f9add224-744b-471c-b812-c43cc179fa38','reviewer':'ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3','verdict':'approve_implementation','code_accepted':True,'required_corrections':[],
 'scope':'V2-R1/R2/R3 affected implementation/recovery/disk difference only. M1/M2 normal paths, original147test evidence, unchanged strategy/data/plan/order protection inherited.',
 'commit':'a85d0bfcfdf4a4ea46f1ab772e7832b55b2f348b','worktree':str(WT),
 'bindings':{'result':bind(P/'result.json'),'result_manifest':bind(P/'result-manifest.json'),'revision_patch':bind(P/'revision.patch'),'activation_and_rollback':bind(P/'activation-and-rollback.md'),'peak_measurement':bind(P/'actual-peak-admission.json'),'peak_code':bind(P/'measure_peak.py'),'prior_review':bind(P.parent/'continuity-v2/independent-maintenance-review.json'),'data_installation_manifest_reused':bind(P.parent/'continuity-v2/data-installation-manifest.json'),'forward_config_reused':bind(P.parent/'continuity-v2/forward-config.json'),'Root_current_disk_release':bind(release_path),'independent_check':bind(P/'independent-diff-check.py'),'independent_verification':bind(P/'independent-diff-verification.json'),'check_resource':bind(P/'independent-diff-resource.txt')},
 'changed_code_bindings_verified':proof['changed_code_bindings_verified'],'unchanged_code_bindings_inherited':proof['unchanged_code_bindings_inherited'],'small_evidence_bindings_verified':verified,
 'correction_acceptance':[
  {'id':'V2-R1','status':'resolved','finding':'atomic_restore writes and verifies a separate temporary inode, then replaces output. In-place command/compose error paths use it, so the retained hardlinked natural candidate no longer receives backup copy writes. Author targeted failed-compose test passes; code/static exact diff checked.'},
  {'id':'V2-R2','status':'resolved','finding':'Prepared journal records exact output-before SHA and candidate inode identity. A witnessed natural-output/pre-replace state atomically restores accepted baseline, retains candidate, and marks rolled_back. Legacy v2 cutpoint requires exact existing hardlink identity. Existing independent-head/candidate/source/output guards remain. Author new/legacy cutpoint tests pass; reviewer additionally interrupted after restoration but before rolled_back journal write: ordinary retry finishes safely and preserves candidate.'},
  {'id':'V2-R3','status':'resolved','finding':'live_view_plan explicitly inventories copies versus known readonly yearly partitions, including named risk/themes histories. View admission now precedes directory creation/copy. Current writable products detach before builder use. Exact prior-year staging bytes and atomic rollback temporary maximum are separate budget terms, with per-stage rechecks. Author six tests cover old references, current theme detach and pre-copy refusal; reviewer additionally verified insufficient restore space refuses before temp/output changes.'}],
 'validation':{'author_targeted_tests_reused':6,'new_independent_small_boundary_checks':proof['additional_small_checks'],'old147_tests_rerun':False,'unchanged_M1_M2_tests_reused':True,'large_data_hashes':0,'price_target_model_or_economic_recomputation':0,'new_market_or_broker_calls':0,'production_mutations':0,'archive_reverification_or_cleanup':0},
 'capacity_decision':{'v3_old_capacity_gap_is_historical':True,'Root_release_accepted_as_authoritative':True,'Root_archive_roundtrip_not_repeated':True,'released_bytes_reported_by_Root':6954373453,'Available_at_Root_snapshot_bytes':11345170432,'installation_bytes':installation,'normal_refresh_required_Available_bytes':9533075101,'post_install_minus_refresh_budget_bytes':headroom,'resource_ready_at_supplied_Root_snapshot_for_stated_install_method':True,
   'terms_verified':terms,'interpretation':'Peak is the declared concrete current-layout write envelope with growth/download/spill/service reserves, not a guarantee on unlimited future source growth. Normal entry recomputes actual sizes/Available and stages recheck.',
   'installation_condition':'Root performs fresh pre-install capacity and process/lock checks. The positive676884854-byte headroom assumes the stated1,135,210,477-byte installation and retaining before-inodes without an additional full copy. If Root instead copies the stated960,702,868-byte before set, that extra space must be admitted separately; this receipt does not silently exempt it.'},
 'production_integration_approved_by_this_reviewer':False,'actual_installed_or_cron_run':False,'new_order_authorization':False,
 'nonblocking_limits':['Approval is for the exact reviewed maintenance implementation; Root still owns shared-tree integration, exact data/head/config installation, rollback mapping and actual current-day receipts.',
 'Original equal/unequal source occurrences, legacy failed predicates, historical targets/orders/ledgers and author/reviewer failures remain. No current-vintage-to-PIT or profitability/readiness promotion.',
 'Resource snapshot is not perpetual readiness: no-op skip, bounded initial/stage admission and fail-closed recovery remain mandatory. Unrecognized independently changed artifacts still require exact-witness resolution, not forced recovery.',
 'No retrospective catch-up orders, kill/authorization changes, ETF/intraday activation or capital-ratio change is approved. Original ordinary paper execution guards stay authoritative.'],
 'resource':{'pool_CPU':24000,'continuing_review_envelope_CPU':500,'previous_v2_review_charge_already_accounted_CPU':13.95,'this_measured_check_outer_CPU':2.61,'smallread_setup_seal_finalhandoff_allowance_CPU':4,'this_inclusive_charge_CPU':6.61,'remaining_of_same_review500_CPU':479.44,'author_v3_charged_before_Root_pending_settlement_CPU':13210.49,'Root_existing_reserve_CPU':1000,'charged_plus_reserved_after_this_review_CPU':14217.10,'unreserved_remaining_before_other_concurrent_changes_CPU':9782.90,'Root20_25_and_archive_CPU_settlement':'Already covered by the existing Root1000 reserve pending its unique settlement; not added again by this reviewer. Old17.10 and13.95 are already in author v3 total.','CPU_affinity':[0],'fresh_memory_MiB':400,'maximum_check_outer_RSS_KiB':75148,'seal_profile':'independent-review-seal-resource.txt','seal_already_inside_allowance':True,'author_ledger_modified':False},
 'next_action':'Root may integrate the exact accepted v3 patch and unchanged42-entry installation package under its existing authority and fresh capacity/lock checks. No additional science, economic or whole-data review is required by these resolved differences.'}
path=P/'independent-maintenance-review.json';assert not path.exists();path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(bind(path)))
