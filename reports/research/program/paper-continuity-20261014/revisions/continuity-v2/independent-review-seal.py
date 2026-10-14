import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

P=Path(__file__).resolve().parent
def binding(path):
    path=Path(path)
    with path.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(path),'sha256':h,'bytes':path.stat().st_size}
m=json.loads((P/'result-manifest.json').read_text());verified=[]
for group in m.values():
    if isinstance(group,list):
        for item in group:
            if not isinstance(item,dict) or not {'path','sha256','bytes'}<=item.keys():continue
            p=Path(item['path'])
            if item['bytes']<2_000_000 and (str(p).startswith(str(P)) or p.suffix in {'.py','.md','.patch'}):
                got=binding(p);assert got=={k:item[k] for k in ('path','sha256','bytes')},str(p)
                verified.append(got)
cap=json.loads((P/'current-capacity.json').read_text())
assert cap['projected_after_install_Available_bytes']==cap['actual_Available_bytes']-cap['installation_bytes']
assert cap['additional_space_required_for_install_plus_next_refresh_bytes']==cap['next_normal_refresh_required_Available_bytes']-cap['projected_after_install_Available_bytes']
disk=json.loads((P/'actual-disk-admission.json').read_text());assert sum(disk['terms'].values())==9444666278
proof=json.loads((P/'independent-behavior-verification.json').read_text())
review={'schema_version':1,'task_id':'PAPER-CONTINUITY-20261014','revision':'continuity-v2','author':'f9add224-744b-471c-b812-c43cc179fa38','reviewer':'ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3','reviewed_at_UTC':datetime.now(UTC).isoformat(),'verdict':'revise_implementation','code_accepted':False,'resource_ready':False,'production_integration_approved':False,
 'scope':'Only M1-M3 affected code/continuity/recovery/disk formula. Prior147 tests/current price-target evidence inherited; no new economic/science review.',
 'commit':'de3a57c3e6e781bcd33aba9f71e7a9180e156399','worktree':'/root/codex-test/wt-paper-continuity-20261014',
 'bindings':{'result':binding(P/'result.json'),'result_manifest':binding(P/'result-manifest.json'),'revision_patch':binding(P/'revision.patch'),'activation':binding(P/'activation-and-rollback.md'),'independent_verification':binding(P/'independent-behavior-verification.json'),'independent_check':binding(P/'independent-behavior-check.py'),'resource_profile':binding(P/'independent-behavior-resource.txt'),'prior_review':binding(P.parents[1]/'independent-maintenance-review.json')},
 'code_bindings_verified':proof['code_bindings_verified'],'small_evidence_bindings_verified':verified,
 'resolved_findings':[
  {'id':'M1','status':'accepted_affected_semantics','finding':'Consumer dependencies now frozen immediately before the actual consumer build, after prior monthly universe production. Frozen universe/code/facts copies retain hashes, and current-source hashes remain checked. Existing new-month transition test proves this branch; no repetition needed.'},
  {'id':'M2','status':'normal_path_accepted_subject_to_M3','finding':'Normal run_plan now dispatches isolated live stages, nine typed reader key definitions, forward prefix composition and atomic data/head publication. Current-year price/risk/theme writes retain full calculation history. Same-day heads skip and next-session synthetic transitions plus actual unequal WORX occurrence check address original normal-path gap. No old plan/order safety code changed.'},
  {'id':'M3_partial','status':'accepted_parts','finding':'Initial Available and per-stage admission, no-progress early return, corrected archive-root resolution, prior immutable snapshot reuse and output-after-replace/head interruption recovery exist. Metadata journal and preserved failed attempts improve recovery. Remaining inplace cases and peak coverage below are not resolved by the15tests.'}],
 'required_corrections':[
  {'id':'V2-R1','priority':'blocking_failed_evidence_integrity','files':['scripts/forward_feature_epoch.py:80','scripts/refresh_equity_book_live.py:1326'],
   'finding':'publish_forward_table retains natural candidate using os.link. For an in-place table such as nsi, candidate is the live output inode. If compose raises before a prepared journal (e.g. duplicate suffix), run_upstream_table restores via shutil.copy2(backup,out), overwriting that same retained candidate inode. The saved failed natural file becomes the old prefix while logging candidate/backup retained.',
   'independent_proof':'Actual synthetic in-place nsi entry with duplicate suffix exits upstream failure; live rollback succeeds, but retained natural SHA equals old published SHA and differs from produced natural SHA. Verified same inode.',
   'minimum_fix':'Restore in-place output by copying the accepted backup to a separate temporary inode then atomic replacement (or otherwise detach the retained candidate before restoration). Preserve the failed candidate bytes/hash. One focused compose-failure test is sufficient; no real panels rerun.'},
  {'id':'V2-R2','priority':'blocking_known_recovery_cutpoint','files':['scripts/forward_publication.py:28','scripts/forward_publication.py:76'],
   'finding':'For in-place producers, a durable prepared journal can exist while output still contains the natural candidate, before combined.replace(output). finish_transaction recognizes only old accepted or new composed output. The actual natural candidate is neither when it restates old rows, so automatic recovery rejects this fully witnessed expected state. Current prepared-before-replace instructions incorrectly require oldSHA for this branch.',
   'independent_proof':'Injected failure at exact combined replacement after prepared journal for in-place nsi; recover_pending raises publication recovery output matches neither accepted version. Baseline/candidate/source remain intact and recognizable.',
   'minimum_fix':'Explicitly recognize the recorded in-place candidate SHA in the prepared-before-replace state, preserve it, atomically restore the accepted baseline and mark the attempt rolled back, or finish an equivalently fully verified staged publication. Preserve independent-change rejection. Add this exact cutpoint proof and align the recovery instructions; no new recovery platform.'},
  {'id':'V2-R3','priority':'blocking_peak_admission_coverage','files':['scripts/forward_refresh_io.py:76','scripts/forward_refresh_io.py:184','scripts/forward_refresh_io.py:249'],
   'finding':'live_view physically copies old themes_YYYY and risk/*_YYYY parquet files because its symlink rule only recognizes a year at the beginning of the stem. disk_admission counts only current-year outputs, so these known historical copies do not increase the declared peak at all. run_live_stage creates/copies live_view before stage_admission, allowing those writes before the stage refusal. Prior-year staging copies for link_prior_years likewise need explicit inclusion or a demonstrated allowance. Thus9.444GB is the sum of current formula terms, not yet a verified complete peak bound.',
   'independent_proof':'Adding a4096-byte old themes_2025 synthetic input leaves required_available_bytes exactly unchanged, yet live_view produces an independent physical copy. This small counterexample proves omission, not the actual missing-byte total or a claim that4096 alone exhausts the current margin.',
   'minimum_fix':'Before creating live_view, admit all physical copies it will make using targeted file metadata, or retain accepted immutable historical products via read-only references with each writable product detached. Include prior-year staging copies explicitly or justify them quantitatively within named reserve terms. Keep per-stage checks and service reserve; recompute the concrete next-refresh requirement without a whole-disk scan or deleting unique evidence.'}],
 'disk_resource_decision':{'independent_of_code_errors':True,'provided_snapshot':cap,'formula_term_sum_verified_bytes':9444666278,'declared_gap_arithmetic_verified_bytes':6215228307,'complete_peak_certified':False,'note':'The supplied4.364GB Available is insufficient even for the existing formula after1.135GB installation. R3 may change the needed bound. Root owns fresh disk_guard recovery/installation accounting. Reviewer performed no cleanup, disk-wide scan, large data hash or production write. Resource shortfall is not a strategy/profitability rejection.'},
 'evidence_reuse':{'targeted_v2_tests':15,'old_maintenance_and_safety_tests':147,'old_tests_rerun':0,'new_small_checks':3,'actual_unequal_prefix_receipt_reused':True,'native_dry_run_reused':True,'author_capacity_error_not_native_test_failure':True,'unchanged_data_values_not_recomputed':True,'large_data_hash_responsibility':'Root'},
 'resource':{'pool':'Original PAPER-CONTINUITY24000CPU','this_review_cap_CPU':500,'author_v2_cumulative_including_prior_review17_10':13139.4,'Root_prior_big_hash_pending_inclusion_CPU':20.25,'conservative_prior_including_Root_CPU':13159.65,'this_measured_check_CPU':3.95,'smallreads_setup_seal_handoff_upper_charge_CPU':10,'this_inclusive_review_charge_CPU':13.95,'conservative_total_including_this_review_CPU':13173.60,'conditional_remaining_before_other_concurrent_costs_CPU':10826.40,'previous17_10_not_added_again':True,'actual_check_RSS_KiB':157000,'CPU_affinity':[0],'fresh_cap_MiB':400,'seal_profile':'independent-review-seal-resource.txt','seal_inside_allowance_not_extra':True,'author_ledger_modified':False,'settlement':'Original owner/Root serial-settles13.95 once; adds the previously uncounted Root20.25 once if not already settled. Other cleanup/Root costs remain additional, no quota reset.'},
 'new_source_market_broker_calls':0,'new_strategy_or_model_runs':0,'production_mutations':0,'next_action':'Root may route the three concrete ordinary fixes to the existing author on actual recovery or handle within the existing worktree ownership contract. Preserve v2 bytes and counters. Re-review only these affected branches; do not repeat15/147tests or real price/target computation. No deployment/normal refresh yet.'}
(P/'independent-maintenance-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(binding(P/'independent-maintenance-review.json')))
