import ast
import hashlib
import json
import os
import resource
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path

E=Path(__file__).resolve().parent;ROOT=Path('/root/codex-test/open-composer')
resource.setrlimit(resource.RLIMIT_CPU,(15,18))
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def check(b):
    p=ROOT/b['path'];assert bind(p)==b or ('bytes' not in b and bind(p)['sha256']==b['sha256']);return p
add=json.loads((E/'source-stage-result-prefix-affected-addendum.json').read_text())
for key in ('driver','result','receipt','inclusive_resource'):check(add[key])
obj=json.loads((ROOT/add['result']['path']).read_text());counts=Counter();checked=0
fn=next(n for n in ast.parse((ROOT/add['driver']['path']).read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='interpretation')
ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual-interpretation-AST','exec'),ns)
for row in obj['rows']:
    original=json.loads(check(row['original_result']).read_text());native=original['native_quote_research_proxy']
    reason=native.get('firstunknown',{}).get('reason','') if native.get('firstunknown') else ''
    kind='invalid_R0' if native['native_engines']==0 else ('gap_unknown' if 'missing scheduled active minute' in reason else ('protective_rejection_unknown' if 'native order rejection' in reason else 'flat_stop'))
    counts[kind]+=1
    assert row['firstunknown']==native.get('firstunknown') and row['original_known_closed_R']==native.get('closed_R')
    refs=original['necessary_observed_price_reference'];before=json.dumps((native,refs),sort_keys=True)
    assert len(refs)==len(row['known_account_price_reference'])
    for original_ref,masked in zip(refs,row['known_account_price_reference'],strict=True):
        assert ns['interpretation'](native,original_ref)==masked
        assert masked['raw_source_counterfactual_annotation']==original_ref
        cutoff=native.get('firstunknown',{}).get('at_ns') if native.get('firstunknown') else None
        if native['native_engines']==0 or (cutoff is not None and original_ref['event_ns']>=cutoff):
            assert masked['observed_price_reference'] is None and not masked['known_component_prefix']
        assert masked['native_protective_acceptance_explicitly_reported'] is False
        checked+=1
    assert before==json.dumps((native,refs),sort_keys=True)
    if kind=='protective_rejection_unknown':
        rejections=[a for a in native['audit'] if a['action']=='unresolved_native_rejection']
        assert len(rejections)==1 and rejections[0]['intent_id']==row['fixture']+'-entry-protect'
        assert rejections[0]['native_at_ns']==native['firstunknown']['at_ns']
assert dict(counts)=={'gap_unknown':4,'flat_stop':4,'protective_rejection_unknown':2,'invalid_R0':2}
old_review=E/'source-stage-actual-independent-review.json'
result={'schema_version':1,'at_utc':datetime.now(UTC).isoformat(),'author':'7c7b1f3d-b962-4bbe-a2eb-87578888a8d5','reviewer':'ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3','verdict':'accept_same_scope_result_interpretation','required_corrections':[],
 'bindings':{'addendum':bind(E/'source-stage-result-prefix-affected-addendum.json'),'mask_code':add['driver'],'mask_result':add['result'],'offline_receipt':add['receipt'],'offline_profile':add['inclusive_resource'],'protective_rejection_clarification':bind(E/'source-v2-protective-rejection-clarification.json'),'prior_actual_acceptance':bind(old_review),'stage_profile_review_unchanged':bind(E/'source-stage-profile-independent-review.json'),'independent_check':bind(Path(__file__))},
 'accepted_counts':dict(counts),'saved_annotation_rows_verified':checked,'all_original_native_and_source_values_unchanged':True,
 'decisive_qualification':'This addendum narrows the original source-result interpretation: February bid-threshold fixtures have immediate protective rejection and firstunknown at the initial-fill clock, not a later central gap. Later true price-condition annotations are counterfactual source observations, not known actual-account/protective/stop eligibility. Submission timestamp alone is never acceptance.',
 'mask_acceptance':'Every at-or-after-firstunknown annotation and every invalidR0 annotation is None in known-component interpretation; all raw counterfactual annotations retained. Original known closedR/feedback/marks and unknowns unchanged. No native rerun.',
 'limits':['The prefix mask does not certify native acceptance, broker election or active order lifecycle. known_component_prefix=True denotes only absence of recorded pathunknown; after a flat stop it does not imply an outstanding protective order. Any use as an actual working-stop predicate still requires explicit accepted/active/terminated lifecycle evidence.',
 'Native mark35.33 is not interchangeable with raw observed bid35.30/ask35.36. Installed native sell-stop check uses bid<=stop; the recorded rejection is decisive here. No broker behavior is inferred.',
 'September four flat quote-proxy stops preceding the raw necessary-price reference remain conditional component facts only. March equality and slower-candidate decision unchanged.'],
 'resource_lineage':{'original_pool_CPU':7176.73,'latest_author_used_CPU':4036.52333,'latest_author_remaining_CPU':3140.20667,'offline200_used_CPU':153.69,'offline200_remaining_CPU':46.31,'annotation_charge_already_settled_CPU':5.60,'March220_remaining_CPU':94.27,'stage_profile_allocation_reset':False,'snapshot4030_92333_retained_as_history':True},
 'review_resource':{'pool':'Original comparison1000 / same source-science80','this_addendum_inclusive_charge_CPU':3.50,'includes_actual_check_and_smallread_seal_handoff':True,'measured_profile':'prefix-mask-independent-resource.txt','prior_result_stage_review_charge_CPU':15.19,'prior_review_charge_not_repeated':True,'comparison_after_prior_review_CPU':579.47,'comparison_after_this_addendum_CPU':582.97,'comparison_remaining_CPU':417.03,'source_science80_remaining_CPU':28.10,'CPU_affinity':sorted(os.sched_getaffinity(0)),'fresh_memory_MiB':400,'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'author_serial_settle_once':True},
 'new_allocation':0,'review_engines':0,'review_native_CLI':0,'HTTP':0,'large_Frame_reads':0,'author_ledger_modified':False,'canonical_r6_modified':False,'source_and_stage_execution_grants_unchanged':True,'Root_message_sent':False,'mother_question_complete':False}
(E/'source-stage-result-prefix-independent-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'receipt':bind(E/'source-stage-result-prefix-independent-review.json'),'counts':dict(counts),'rows':checked}))
