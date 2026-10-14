import hashlib,json,os,resource
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU,(15,20));assert os.sched_getaffinity(0)=={0}
P=Path(__file__).resolve().parent;OLD=P.parents[1];checked={}
def verify(b):
 p=Path(b['path']);raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==b['sha256'],str(p)
 if 'bytes' in b:assert len(raw)==b['bytes']
 checked[str(p)]=dict(sha256=b['sha256'],bytes=len(raw))
verify(dict(path=P/'scientific-review-packet.json',sha256='cab1d46943e44a54fa78f8dc4dd9b4389bd5b891430a4de9e70a6bb5e4576ff7'))
packet=json.loads((P/'scientific-review-packet.json').read_text())
for b in packet['bindings']+[packet['retained_original_direct_bindings_packet']]:verify(b)
delta=json.loads((P/'science-delta.json').read_text())
for b in delta.values():
 if isinstance(b,dict) and 'path' in b and 'sha256' in b:verify(b)
old=json.loads((OLD/'scientific-plan.json').read_text());new=json.loads((P/'scientific-plan.json').read_text())
allowed={'source_records','signal_clock','risk_and_execution','costs','workload','resource_balances','prepared_UTC','revision','prior_plan','prior_independent_review'}
changed=[k for k in old.keys()|new.keys() if old.get(k)!=new.get(k)]
assert set(changed)<=allowed,changed
for k in ['candidate_ids','population','initialization','input_route','native_route','root_authority','inherited_seen','reported_metrics','stop_conditions']:
 assert old[k]==new[k],k
cases=json.loads((P/'source-figure-case-timelines.json').read_text());oc=json.loads((OLD/'source-figure-case-timelines.json').read_text())
assert cases['cases'][:3]==oc['cases'][:3]
smci=cases['cases'][3];assert smci['date_candidate']=='2025-03-26' and smci['setup_and_previous_bar_date']=='2025-03-25' and smci['prior_candidate_date']=='2025-03-25'
w=new['workload'];assert w['effective_price_trajectories']==w['price_paths']==4*2*2==16
assert w['transactioncost_outputs']==16*3==48 and w['borrowstress_outputs']==48*2==96 and w['borrow_stress_required']
assert new['costs']['borrow_stress_APR']==[0,.2] and new['costs']['borrow_stress_daycount']==1 and new['costs']['borrow_day_basis']==365
assert 'same_bar_paths' not in new['risk_and_execution']
assert new['research_role']=='market_component_method' and new['claim_scope']=='conditional_cohort' and not new['promotion_eligible']
out=dict(status='pass',bindings=checked,changed_top_level_keys=sorted(changed),unchanged_science_sections=['candidate_ids','population','initialization','input_route','native_route','root_authority','inherited_seen','reported_metrics','stop_conditions'],old_source_images_reopened=False,old_plan_cases_review_bytes_preserved=True,only_case_date_changed='SMCI setup25/break26',workload=[16,48,96],new_network_market_fit_PnL=0,resource=dict(CPU=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,affinity=[0]))
(P/'independent-delta-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
