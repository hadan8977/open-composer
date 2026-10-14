import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

P=Path(__file__).resolve().parent
WT=Path('/root/codex-test/wt-paper-continuity-20261014')
def binding(path):
    path=Path(path)
    with path.open('rb') as f:
        digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(path),'sha256':digest,'bytes':path.stat().st_size}

manifest=json.loads((P/'result-manifest.json').read_text())
small_names=['result.json','result-manifest.json','task.json','isolated-recovery.patch',
 'activation-and-rollback.md','forward-config-candidate.json','actual-target-parity-and-held-coverage.json',
 'actual-current-native-readonly-plan-result.json','hygiene-exact-fields-and-holdings.json',
 'final-focused-tests-log.txt','plan-refresh-safety-tests-log.txt','final-ruff-log.txt',
 'readonly-control-exact-copy.json','compose-current-reader-panel.json','compose-current-reader-prices.json',
 'compose-current-reader-etf.json','compose-current-reader-signals.json','compose-current-reader-themes.json',
 'compose-current-risk-cov.json','compose-current-risk-exposures.json','compose-current-risk-factor_returns.json',
 'compose-current-risk-residuals.json','current-feature-input-manifest.json',
 'independent-maintenance-verification.json','independent-maintenance-check.py','independent-maintenance-check-resource.txt']
bindings=[binding(P/n) for n in small_names]
expected={x['path']:x for group in manifest.values() if isinstance(group,list) for x in group if isinstance(x,dict) and 'path' in x and 'sha256' in x}
for b in bindings:
    if b['path'] in expected:
        assert b['sha256']==expected[b['path']]['sha256'], b['path']
plan_path=WT/'reports/paper/book/quant1/plans/2026-10-14.json'
plan=json.loads(plan_path.read_text())
bindings.append(binding(plan_path))
assert bindings[-1]['sha256']==expected[str(plan_path)]['sha256']
verification=json.loads((P/'independent-maintenance-verification.json').read_text())
result={
 'schema_version':1,'task_id':'PAPER-CONTINUITY-20261014',
 'author':'f9add224-744b-471c-b812-c43cc179fa38','reviewer':'ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3',
 'reviewed_at_UTC':datetime.now(UTC).isoformat(),'verdict':'revise_implementation',
 'scope':'Complete isolated maintenance code and continuity review; Root separately owns data installation hashes, activation and rollback acceptance.',
 'worktree':str(WT),'commits':['a8ad99c','515a233f187fa97147d998f70b279e9d24c0da31'],
 'runtime_readback':{'actual_tool':'paseo.get_agent_status','agent_id':'ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3','model':'gpt-6-astra','thinkingOptionId':'high','effectiveThinkingOptionId':'high','currentModeId':'full-access','runtimeInfo_modeId':'full-access','status':'running','model_switches':0},
 'bindings':bindings,'verified_code_bindings':verification['code_bindings_verified'],
 'required_corrections':[
  {'id':'M1','priority':'blocking_continuity','files':['scripts/refresh_equity_book_live.py:1538','scripts/forward_feature_epoch.py:53'],
   'finding':'Producer dependencies are hashed before run_plan executes the universe/universe_broad monthly update. A legitimate appended month changes the bound universe bytes, so subsequent daily publication rejects the inputs it actually consumed. New-month additions not present in the pre-update list are also not bound.',
   'evidence':'Actual publisher synthetic dependency mutation rejected with producer input/code changed during feature build. run_plan order places monthly universe producers before daily; snapshot is before all of run_plan.',
   'minimum_fix':'Freeze each relevant dependency after its prerequisite producer completes and before its consumer starts; retain the before snapshot if needed. Do not simply stop verifying dependency hashes. Add one small new-month transition plus unchanged-day proof.'},
  {'id':'M2','priority':'blocking_history_and_continuity','files':['scripts/refresh_equity_book_live.py:590','scripts/refresh_equity_book_live.py:1360','code/publish_current_readers.py'],
   'finding':'The accepted private reader/risk/signal/theme outputs were manually composed with historical prefixes, but the cron live stages still directly overwrite panel/prices/ETF/signals/risk/alpha using natural builders, without the composition/history guard. prices still runs without --years, risk without --write-from-year. Therefore current Oct7 parity does not demonstrate the next cron preserves those accepted reader histories; the existing hygiene evidence already records 17 changed historical cutoffs.',
   'evidence':'Small fake-runner execution of the actual build_plan/run_plan dispatches all five examined live builders directly with no forward publication hook. Existing compose-current-reader-* and risk/theme receipts establish the private output path differs from the natural producer path.',
   'minimum_fix':'Wire the reviewed private natural-build plus prefix-composition behavior into the normal live refresh, with coherent staged dependencies and final freshness publication. Keep unequal duplicate occurrences in the source; explicitly retain the accepted reader key-selection/cardinality semantics. Prove a synthetic same-day and next-session refresh preserves previous reader rows and does not rewrite pre-2026 partitions, plus a targeted existing duplicate-key example. No full historical/model rebuild is requested.'},
  {'id':'M3','priority':'blocking_operability_and_recovery','files':['scripts/prepare_forward_source_context.py:23','scripts/forward_feature_epoch.py:60','scripts/refresh_equity_book_live.py:1535','activation-and-rollback.md'],
   'finding':'Every non-no-upstream invocation copies a new two-year context before per-table already-published skips, then retains full natural candidates and additional composed/staging outputs. There is no concrete peak-space admission before those writes. Root observed only285757440 available bytes; existing input manifest alone accounts for157660807 context bytes and the bound daily_broad output is329713766 bytes, already exceeding remaining space before additional candidates/backups/spill. Cleanup is in progress but has not been independently accepted here. A disk failure after output replacement but before latest receipt publication leaves the new output with no matching head; a normal retry is rejected by the consumed receipt guard.',
   'evidence':'No new disk scan: sums use existing manifest metadata and Root supplied df. Actual small injected OSError at latest JSON temp write reproduced output_published/head_absent/retry_refused. This is fail-closed, not silent acceptance, but the current generic rollback instructions do not specify this cut-point recovery.',
   'minimum_fix':'Use f9/Root actual reclaimed-space receipt and a concrete next-refresh peak bound covering context, staged/natural/composed candidates, backups and spill; check it before copying or publishing. Avoid copying a new context on a no-op repeated day. State a narrow recoverable publication procedure (matching output/head/backup hashes, preserving failed receipt and candidate, new attempt identity) for each publication cut point; a tiny injected-failure test suffices. No new storage platform, unbounded retention policy or deletion of unique evidence is required.'}
 ],
 'accepted_affected_semantics':[
  'plan.py preserves existing submitted-plan bytes when orders match and still rejects changed orders after a receipt; only unsubmitted metadata may refresh. Existing 100 safety tests include this exact branch and are reused.',
  'Default target date is latest completed exchange session; run_plans requires previous-session decision and exact target execution date before subprocess. Future preview is readonly, backdated submission refused.',
  'Existing submission env opt-in, file lock, verified paper-origin client, kill switch, current plan risk checks, order window and client-order-id lookup remain in place. No order or authorization change is approved by this review.',
  'Bounded daily query applies output-year filtering after full trailing/cross-sectional query; intraday join remains symbol-local. Issuer joins and insider cohort partition preserve original formulas. Existing focused parity tests reused.',
  'Account valuation is readonly and explicitly unattributed; missing-plan reconciliation remains nonzero. No missed strategy P&L or fill history is invented.',
  'Prefix composer preserves typed/null/float bits and unequal occurrence history; suffix duplicate keys reject. Source AZN/canonical69 corrections validate exact witnesses and fail if current source differs.'
 ],
 'actual_evidence_reused':{'maintenance_tests':47,'safety_tests':100,'lint':'pass','historical_target_names':1698,'historical_weight_max_abs_difference':0.0,'held_names_unique_covered':1472,'readonly_decision':'2026-10-13','readonly_execution':'2026-10-14','readonly_plan_status':plan.get('status'),'readonly_plan_summary':plan.get('summary'),'all_large_data_hashes':'Root responsibility; not repeated','full_pipeline_reexecuted':False},
 'nonblocking_limits':[
  'Current-source versioned forward evidence is not PIT/security-lifetime/total-return certification; original failed whole-panel predicates remain failed.',
  'Current 373 proposed orders and eight not-shortable rejections are readonly observations, not fills or authority to trade; re-evaluate current state through existing normal guards.',
  'Actual lifecycle/authorization expiry and safe activation remain Root existing-book operational responsibilities; reviewer did not change/read credentials, toggle kill or fabricate new harness/readiness/promotion.',
  'Two-year correction contract is explicitly2026 and safely refuses another year; a subsequent-year anchor remains a separately reviewed maintenance need.',
  'Inherited unchanged broker submit audit behavior and broader strategy performance were not redesigned. Existing ETF/intraday operation and submitted history remain outside this repair.'
 ],
 'skills_used':[{'path':'.agents/skills/paper-auto-safety-reviewer/SKILL.md','application':'Affected existing-book safety maintenance only; no new paper_auto activation or strategy promotion.'}],
 'new_source_requests':0,'broker_reads':0,'broker_writes':0,'production_mutations':0,'model_runs':0,
 'resource':{'pool':'PAPER-CONTINUITY-20261014 original24000CPU','review_cap_CPU':1000,'prior_author_report_charged_or_reserved_CPU':12463.16,'check_measured_outer_CPU':5.74,'check_peak_RSS_KiB':158924,'check_exit':0,'CPU_affinity':[0],'memory_cap_MiB':400,'fresh_admission':'run_capped research admission passed','unmetered_small_reads_setup_seal_handoff_upper_charge_CPU':10,'seal_outer_profile':'independent-maintenance-seal-resource.txt','settlement':'Owner adds 5.74 + actual seal outer CPU +10 once; this review does not edit the author ledger or refund prior costs.'},
 'production_integration_approved':False,'new_order_authorization':False,
 'next_action':'Original f9 owner repairs M1-M3 within the same task; preserve original package and provide one affected code/operability receipt. Root can keep preparing installation but should not treat the current package as continuous-refresh approved.'
}
(P/'independent-maintenance-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(binding(P/'independent-maintenance-review.json')))
