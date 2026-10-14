import hashlib,json,resource,os
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
resource.setrlimit(resource.RLIMIT_CPU,(40,40));os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
ROOT=Path('/root/codex-test/open-composer');P=ROOT/'reports/research/program/usic-practitioner-research-20261013/revisions/v2';OLD=P.parent.parent
bindings={}
def bind(path):
 path=Path(path);path=path if path.is_absolute() else ROOT/path;b=path.read_bytes();r={'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)};bindings[r['path']]=r;return r
def load(path):return json.loads(Path(path).read_text())
def check(b):
 r=bind(b['path']);assert r['sha256']==b['sha256'];return r
packet=load(P/'review-bindings.json');assert bind(P/'review-bindings.json')['sha256']=='7ec82e6291dbbb500a8ed75b19acc56757fd88626bd5c1f84d43522f1a492c86'
for b in packet.values():
 if isinstance(b,dict) and 'path' in b:check(b)
preserve=load(P/'v1-preservation.json');check(preserve['old_review'])
for b in preserve['old_bindings'].values():check(b)
bind(P/'v1-preservation.json')
plan=load(ROOT/packet['plan']['path']);contract=load(ROOT/packet['state_contract']['path'])
check(plan['authoritative_state_and_ledger_contract'])
for k in ['selection_and_information','portfolio_and_execution']:
 check(plan[k]['definition'])
cells=load(ROOT/packet['evaluation_cells']['path'])['cells'];pairs=load(ROOT/packet['paired_comparisons']['path'])['pairs']
assert len(cells)==120 and len(pairs)==102
byid={r['cell_id']:r for r in cells};assert len(byid)==120
assert sum(r.get('duplicate_order_tag',False) for r in cells)==6
assert {r['candidate_id'] for r in cells if r['extra_latency_bars']}=={'M_FEEDBACK','F_MONTHLY'}
assert len(contract['candidate_state_table'])==len(plan['candidate_inventory'])==8
for definition,row in zip(plan['candidate_inventory'],contract['candidate_state_table'],strict=True):
 assert all(definition[k]==v for k,v in row.items())
for r in pairs:
 a,b=byid[r['A']],byid[r['B']]
 for k in ['cost_bps','sequencing','extra_latency_bars']:assert a[k]==b[k]
 assert not a.get('duplicate_order_tag',False) and not b.get('duplicate_order_tag',False)
 if r['question']!='momentumcontrol':assert a['order_style']==b['order_style']
 if a['extra_latency_bars']:assert r['question']=='monthlybudget'
 assert r['actual_comparison_observed'] is False
count=Counter(r['question'] for r in pairs)
scope=load(ROOT/packet['request_scope']['path']);assert scope['initial_request_objects']==13 and scope['max_pages_total']==32 and scope['initial_scope_maximum']['entity_bytes']==67108864
assert plan['resource_and_stopping']['economic_allocation_proposal']['economic_allocated']==plan['resource_and_stopping']['economic_allocation_proposal']['market_allocated']==0
result={'status':'ok','verified_paths':list(bindings.values()),'v1_original_bindings_preserved':13,'plan_contract_candidate_equal':8,'cell_count':120,'known_duplicates':6,'structural_ceiling':114,'pairs':102,'pair_counts':dict(count),'input_scope_unchanged':True,'data_rows_scanned':0,'CPU_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
(P/'independent-diff-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='verified_paths'},ensure_ascii=False))
