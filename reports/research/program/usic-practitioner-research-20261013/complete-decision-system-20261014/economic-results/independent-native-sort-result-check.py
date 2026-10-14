import gzip
import hashlib
import json
import os
import resource
from decimal import Decimal
from pathlib import Path

E=Path(__file__).resolve().parent;ROOT=Path('/root/codex-test/open-composer')
resource.setrlimit(resource.RLIMIT_CPU,(15,18))
packet=json.loads((E/'native-sort-actual-result-review-packet.json').read_text());b=packet['bindings'];checked={}
def check(x):
    if isinstance(x,dict):
        if 'path' in x and 'sha256' in x:
            p=ROOT/x['path'];assert p.stat().st_size<2_000_000
            with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
            assert h==x['sha256'] and ('bytes' not in x or p.stat().st_size==x['bytes']),str(p)
            checked[str(p)]=h
        else:
            for v in x.values():check(v)
    elif isinstance(x,list):
        for v in x:check(v)
def read(x):return json.loads((ROOT/x['path']).read_text())
check(packet)
actual=read(b['actual']);original=read(b['original_March_acceptance']);receipt=read(b['receipt']);cost=read(b['cost']);proposal=read(b['resource_choice'])
assert receipt['status']=='settled' and receipt['outer_exit']==0 and receipt['charged_CPU']==76.0
variant=actual['variants'][0]
assert len(actual['variants'])==1 and variant['complete'] and variant['known'] and variant['minutes']==7800
assert variant['events']==original['variants'][0]['events']
assert actual['input']==original['input'] and actual['full_strategy_returns']==0
pairs=[]
for policy in ('P_SYSTEM','P_EMA'):
    cand=next(x for x in b['accounts'] if Path(x['path']).name=='bulk__'+policy+'.json.gz')
    ref=next(x for x in b['original_reference_accounts'] if Path(x['path']).name=='reference__'+policy+'.json.gz')
    with gzip.open(ROOT/cand['path'],'rt') as f:a=json.load(f)
    with gzip.open(ROOT/ref['path'],'rt') as f:c=json.load(f)
    assert a==c and a['full_month_clock_executed'] and a['known_complete_month'] and a['unknown'] is None
    pairs.append({'policy':policy,'all_saved_fields_exact_equal':True,'fields':sorted(a),'native_orders':len(a['native_orders'])})
    del a,c
ratio=variant['CPU']/original['variants'][0]['CPU']
assert abs(ratio-cost['bulk_vs_original_ratio'])<1e-12 and ratio>1
base=(Decimal(str(variant['CPU']))+Decimal(str(actual['source_read_CPU'])))*Decimal(25)*Decimal(2)*Decimal('1.25')+90+180
est8=base*2;est32=base*8;remaining=Decimal('2947.07667')
for name,expected in [('full_primary4_market_bothOHLC_CPU_estimate',base),('full_primary8_two_routes_bothOHLC_CPU_estimate',est8),('full_primary32_all8policies_routes_paths_CPU_estimate',est32),('minimum_primary8_shortfall_excluding_newsource_work',est8-remaining)]:
    assert abs(Decimal(str(cost[name]))-expected)<Decimal('1e-8'),name
assert sum(Decimal(str(proposal['recommended_scope'][k])) for k in ['stage1_CPU_upper','stage2_CPU_upper','interpretation_and_uncertainty_CPU_upper'])==36000
assert Decimal(str(proposal['recommended_scope']['requested_extra_CPU_upper']))+remaining==36000
assert Decimal('4153.65333')+Decimal(str(receipt['charged_CPU']))==Decimal(str(packet['economic_used_CPU']))
assert Decimal(str(packet['economic_used_CPU']))+remaining==Decimal('7176.73')
result={'checked_small_bindings':checked,'paired_saved_accounts':pairs,'complete_clock_per_account_minutes':7800,'candidate_engines':2,'events_exact_equal':True,'actual_pair_CPU':variant['CPU'],'actual_source_read_CPU':actual['source_read_CPU'],'reference_pair_CPU':original['variants'][0]['CPU'],'measured_ratio':ratio,'actual_inclusive_charge_CPU':receipt['charged_CPU'],'estimates_verified':{'primary4':str(base),'primary8':str(est8),'primary32':str(est32),'primary8_shortfall':str(est8-remaining)},'proposal_budget_arithmetic':{'prospective_remaining_scope_CPU':36000,'existing_remaining_included_CPU':2947.07667,'requested_extra_CPU':33052.92333,'implied_cumulative_total_if_granted_CPU':40229.65333,'not_same_as_cumulative36000':True},'estimates_are_not_empirical_fullscope_lower_bounds':True,'new_source_work_not_costed':True,'resource_allocation_granted':0,'current_review_native_engines':0,'native_CLI':0,'HTTP':0,'large_Frame_reads_or_hashes':0,'affinity':sorted(os.sched_getaffinity(0)),'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
(E/'native-sort-actual-independent-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='checked_small_bindings'}))
