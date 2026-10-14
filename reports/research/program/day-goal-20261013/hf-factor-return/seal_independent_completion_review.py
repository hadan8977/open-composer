"""Seal independent M2 receipt; never settle the author's shared ledger."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

P=Path(__file__).resolve().parent
def bind(p):
    p=Path(p); b=p.read_bytes()
    return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def read(name): return json.loads((P/name).read_text())
old=P/'implementation-M2-archive/independent-implementation-review.json'
assert old.read_bytes()==(P/'independent-implementation-review.json').read_bytes()
assert bind(P/'implementation-manifest.json')['sha256']=='c4c689c827e47c7caa4145aa9fa49d5317e6a548c959a52724cf95b3f3f25d41'
assert bind(P/'completion-implementation-delta.json')['sha256']=='36b2565bc81fd2083f8821070746939d00b22a8da4458f2886ea90ac2f205389'
v=read('independent-completion-delta-verification.json')
assert v['test_exit']==0
names=['independent-completion-delta-resource-failed1.txt','independent-completion-delta-resource-failed2.txt','independent-completion-delta-resource.txt']
costs=[]
for name in names:
    t=(P/name).read_text()
    cpu=round(sum(float(re.search(k+r' time \(seconds\): ([\d.]+)',t)[1]) for k in ['User','System']),2)
    costs.append(dict(receipt=bind(P/name),inclusive_CPU=cpu,exit=int(re.search(r'Exit status: (\d+)',t)[1]),peak_RSS_KiB=int(re.search(r'Maximum resident set size \(kbytes\): (\d+)',t)[1])))
actual=round(sum(r['inclusive_CPU'] for r in costs),2)
charge=round(actual+5,2)
assert charge<180
bindings={name:bind(P/file) for name,file in {
 'implementation_manifest':'implementation-manifest.json',
 'completion_delta':'completion-implementation-delta.json',
 'root_resource_authority':'root-complete-economic-resource-amendment.json',
 'prior_M1_manifest':'implementation-M2-archive/implementation-manifest.json',
 'prior_M1_independent_review':'implementation-M2-archive/independent-implementation-review.json',
 'prior_conditional_feature_acceptance':'independent-feature-input-acceptance.json',
 'resume_contract':'calibration-resume-contract.json',
 'frozen_ledger_snapshot':'completion-resource-ledger-at-delta-review.json',
 'independent_verification':'independent-completion-delta-verification.json',
 'independent_check_code':'independent_completion_delta_check.py',
 'independent_synthetic_JUnit':'independent-completion-delta-tests.xml',
 'completion_resource_helper':'hf_completion_resources.py',
 'models_runtime':'hf_run_models.py',
 'evaluation_runtime':'hf_evaluate.py',
 'resource_admission_contract':'resource-admission.json',
}.items()}
result=dict(schema_version=1,task_id='DAY3-HF-FACTOR-RETURN',author='7b109880-ac40-447e-b2a6-f0ed1266ebac',reviewer='ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3',as_of_utc=datetime.now(timezone.utc).isoformat(),
 verdict='approve_implementation',scope='M2 affected implementation/resource/public checkpoint-resume delta only; accepted M1 science and conditional input retained.',bindings=bindings,
 findings={
  'manifest':'87 bindings:71 inherited paths after absolute-path normalization;69 unchanged and only hf_run_models.py/hf_evaluate.py changed;16 additions.29 unique small bindings freshly verified. No71 large-input or300-source rehash. New787041920-byte scaled input binding matches actual resume contract and prior accepted model-input provenance; author fresh verification reused, not represented as a new reviewer full hash.',
  'science':'All22 named original model/data/selection/economic/inference functions independently AST-equal. Evaluation main only uses common resource/native guard; model main changes calibration entry.20 pipelines/800 diagnostics/100 funded/40 host and science/cost/clock/seen definitions unchanged.',
  'actual_saved_state':'Read and SHA-check actual2377073-byte150 checkpoint and15404-byte scaler; sklearn1.9.0,150 predictors, all parameters, first150 node digest, bin thresholds, random seed, feature-subsample RNG and all scaler value digests match.350 output absent at review. No real fit, prediction or score accessed.',
  'resume':'Public same-data warm_start adds200 trees. Existing50/150 preserved; new350 output refuses overwrite. Pre/post150 prefix and bin/seed checks retained; old incomplete350 exposure and failed450-slot cost retained. Two toy50→150→pickle→350 chains match otherwise uninterrupted warm chains by every tree and prediction; these are synthetic evidence, not proof of future real350 completion.',
  'ledger':'Frozen baseline460.49 includes old5 unknown; new closed54.08 yields514.57, plus reviewer180 reservation leaves35305.43 uncommitted. Failed lint and other closed receipts retained and hashes checked. One owner settles outer launcher receipt once; inner timings are descriptive, no refund or second36000 pool.',
  'limits':'Runtime reservation and cumulative headroom checked before native I/O; affinityCPU0 and RLIMIT_CPU inclusive-slot minus5. Resume1200 therefore process1195. Actual memory still requires fresh run_capped<=1024MiB admission with owner reserve; JSON cap alone is not live RSS certification.',
  'projection':'Original350-based ratios/equivalents and1.25 plus1700/700/300/500 retained. New full projection compares used+open commitments+remaining against36000. Including current resume reservation is conservative until owner settles actual charge. Completed150 intrinsic314.817376 plus measured continuation forms full-chain timing; old failed work stays in ledger.11416 prior gate bound is not a350 measurement.',
  'native':'Resource-only method/direction diff inspected; original stream-SHA guards retained, canonical independent review and M2 must be rebound by owner before actual pre-backtest/knowledge validation. This receipt does not replace native guards.',
 },
 required_corrections=[],implementation_semantics_accepted=True,full_implementation_approval=True,implementation_ready=True,input_ready=True,
 input_ready_scope='Inherited complete conditional feature input and bounded raw-market bridge for unchanged scientific definitions; only16 selected scalar label spots were checked previously, not full136597-label parity. Current-vintage/source-conditional clock, non-PIT/non-leg replication and execution limits retained.',
 native_ready=False,economic_execution_admitted=False,real350_completed=False,
 continuation='Same author may bind this M2 receipt and complete actual native/knowledge/fresh-memory/job-reservation gates, then execute the single authorized1200-inclusive150→350 continuation. Check no old process/output before launch. This is not an automatic repeated1200 slot. Settle actual+unknown once; require full350 measured projection and fresh cumulative admission before linear/HGB/accounts. No per-fileRoot approval needed for those already-authorized conditions.',
 operational_limits=[
  'Ledger helper is a single-owner serial tool, not a concurrent transactional ledger. Its write_text is not atomic despite one comment. Preserve single writer and nonnegative finite reservations/allowances; no second reviewer ledger or duplicate outer receipt under a renamed job.',
  '350 output nonexistence is enforced in code before write, after fit; owner must retain prelaunch output/process check to avoid needless repeated training during recovery. A saved350 must be accepted/reconciled instead of rerunning150.',
  'Runtime stages are fixed resume-calibration/linear/hgb/accounts; no new stage or scientific shortcut is approved. Unknown kill cause/old peak925484KiB and all past failures remain evidence.'
 ],
 resource=dict(pool='SingleRoot36000 cumulative HF completion envelope',job_id='independent-completion-delta-review-01',reservation_CPU=180,inclusive_jobs=costs,measured_CPU=actual,small_reads_setup_repair_seal_and_handoff_conservative_CPU=5,total_charge_CPU=charge,owner_sole_settlement=True,ledger_mutated_by_reviewer=False,unknown_already_measured_inner_CPU_not_added=True,fresh_memory_MiB=400,CPU_affinity=[0],maximum_observed_RSS_KiB=max(x['peak_RSS_KiB'] for x in costs),reviewer_failures='Two static-check assertions:relative/absolute path normalization, then declared main-entry AST allowlist omission. Both reviewer code/log/profile versions preserved; no scientific failure or real fitting.',remaining_reviewer_reservation_before_owner_settle=round(180-charge,2),other_owner_concurrent_costs_not_claimed_zero=True),
 synthetic_tests_passed=5,new_real_fits=0,new_source_requests=0,new_market_requests=0,new_strategy_return_calculations=0,new_cloud_USD=0,new_orders=0,research_pass=False,paper_ready_pass=False,no_Root_intermediate_message=True)
for name in ['independent-completion-implementation-delta-review.json','independent-implementation-review.json']:
    (P/name).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(review=bind(P/'independent-implementation-review.json'),measured_CPU=actual,unknown_CPU=5,total_charge_CPU=charge)))
