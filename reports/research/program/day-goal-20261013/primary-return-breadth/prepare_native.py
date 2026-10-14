"""Source/native dossier preparation only; does not allocate economic runs."""
from pathlib import Path
from datetime import datetime, UTC
import json, hashlib

P=Path(__file__).parent
ROOT=Path.cwd()
IT='t20261013_conditional_fedput_application'
D=ROOT/'reports/research/iterations'/IT
D.mkdir(exist_ok=True)
NOW=datetime.now(UTC).isoformat()
def rel(p): return str(Path(p).resolve().relative_to(ROOT))
def bind(p):
 p=Path(p);return {'path':rel(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def write(p,x): Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
plan=json.loads((P/'scientific-plan.json').read_text())
ledger=json.loads((P/'sources/download-ledger.json').read_text())
cardpath=ROOT/'reports/harness/source_cards/day20261013_conditional_fedput.jsonl'
facts=[
 ('original_cycle','fedput_original','The author Table7 lateweek2/4/6 lossQ1 coefficient is34.8bp/day versusoddweeks; nestedweek/month/quarter states increasecontrasts. Regression/sourcefullsamplequintiles are not executable netCAGR.','Even-week mean-reversal'),
 ('fed_2026','fed_cycle_counterevidence','The2026 author review reports statistically significant oppositecycle2017-2021. Calendar riskpremium cannot be presumedstable.','statistically significant opposite cycle'),
 ('dtc','dtc_original','OriginalDTC long-short monthlygrossmean1.2% requiresactualhistoricalstocks andshortlegborrow/funding; oldmomentumavoidanceisadifferentfailedbranch.','a 1.2% monthly return'),
 ('hf_zoo','hf_zoo_original','Published factorzooTable4 has19.89%costadjustedannualarithmeticmean/SR1.37 intraday and26.73%overnightinclusive arithmeticmean, notCAGR;272factors/fullsourcecost differs.','Intraday Market Return Predictability Culled from the Factor Zoo')]
cards,sources,ev=[],[],[]
for ident,claimid,claim,quote in facts:
 row=next(x for x in ledger if x['id']==ident);f=P/'sources'/f'{ident}.txt';b=bind(f)
 assert quote in f.read_text(),quote
 card={'claim_id':claimid,'claim':claim,'source_url':row['url'],'source_type':'paper','fetched_at':row.get('fetched_at_utc',row.get('fetched_at')),'source_sha256':b['sha256'],'quote':quote,'verification_status':'source_verified','limitations':'Actual fetched originaltext, not rawreturn reproduction or capitalprofit forecast.'}
 cards.append(card)
 sources.append({'claim_id':claimid,'claim':claim,'url':row['url'],'source_type':'paper','published_or_updated_at':{'original_cycle':'2018-02-12','fed_2026':'2026-05-01','dtc':'2015-05-01','hf_zoo':'2025-01-02'}[ident], 'publication_precision':'month' if ident in {'fed_2026','dtc'} else 'day','market_and_period':'US equities; exactsample/source limits in complete scientificplan','applicability':'Crossdependency primary-return mechanism choice','limitations':card['limitations'],'independent_replication':'None claimed fororiginallicensed input','fetched_at':card['fetched_at'],'snapshot_path':b['path'],'sha256':b['sha256'],'source_card_path':rel(cardpath),'credibility':'Primary author paper','core_claim':claim,'reflection':'Source statistic is not net fundedCAGR; retain counterevidence.','project_applicability':'Nonpromotable conditional Fed-put application'})
 ev.append({'claim_id':claimid,'source_card_path':rel(cardpath),'snapshot_path':b['path'],'snapshot_sha256':b['sha256'],'source_url':row['url']})
cardpath.write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in cards))
queries=[{'query':'Fed FOMC cycle current author update and original loss-state evidence','searched_at':next(x for x in ledger if x['id']=='fed_2026')['fetched_at_utc'],'opened_urls':[x['url'] for x in ledger if x['id'] in {'fed_2026','original_cycle'}]}, {'query':'Days-to-cover and highfrequency factorzoo original results and input archives','searched_at':next(x for x in ledger if x['id']=='dtc')['fetched_at_utc'],'opened_urls':[x['url'] for x in ledger if x['id'] in {'dtc','hf_zoo'}]}]
write(P/'query-manifest.json',{'queries':queries,'timestamp_scope':'Source fetchreceipt time, not exact search start; actual originaltoolqueries retained in sessiontrace.','source_units':40,'direct_ledger':bind(P/'sources/download-ledger.json')})
write(P/'knowledge-baseline.json',{'created_at':NOW,'no_economic_execution':True,'bindings':[bind(x) for x in ['reports/research/program/day-goal-20261013/research-frontier/new-sources.json','reports/research/program/day-goal-20261013/research-frontier/old-results.json','reports/research/harvest/directions.jsonl']], 'prior_scope':'Old specific pre-FOMC andmomentumavoidance failures preserved, not globalfamilyblacklist; original optionpackage paused.'})
direction={'schema_version':3,'iter_id':IT,'reviewed_at':NOW,'decision':'proceed','objective':plan['question'],'target_regime_and_horizon':plan['inference']['partitions'],'existing_solution_comparison':'Original lateweek×marketloss versus genericloss andshiftedcalendar, source nestedstates/1x2xrisk; no sealedpreFOMC week0 rerun.','remaining_evidence_gap':'Frenchaggregate primitives available in boundexistingcurrent202608vintage; calendar1994-2014/originalvintage/sourceinputnotaccepted; source34.8bp isregressioncontrast. Actual3ETF cashactions/quotes/bars notyetaccepted; planapproval andimplementationnativegates stillrequired.','negative_experiments_checked':'2026authors2017-2021 oppositecycle, oldsinglepreFOMC failure, oldDTC momentumavoidance wrongsign, retired crossassetDefenseFirst andsourceHF friction/inputgap.','cost_and_execution_assumptions':json.dumps(plan['funded_execution']),'stop_condition':plan['decision_rule'],'queries':queries,'sources':sources,'query_manifest':bind(P/'query-manifest.json'),'pre_iteration_knowledge_baseline':bind(P/'knowledge-baseline.json'),'source_evidence_bindings':ev,'cheapest_decisive_test':{'action':'Complete6fixed nonpromotable conditionalstreams andmatched14controls, cost/capital/risk/hostdiagnostics, nochooser/OOS.','pass_condition':'Complete boundactualinput/cashcostdecision; positiveproxyneverpromoted automatically.','falsification_condition':'Weaknetcalendarincrement justifiesdeferapplication; nofullmechanismrefutation.','max_compute_minutes':120}}
write(D/'direction-review.json',direction)
external={'schema_version':3,'iter_id':IT,'research_role':'market_component_method','strategy_name':'conditional_late_intermeeting_fedput','source_spec_path':None,'spec_hash':None,'registered_at':NOW,'objective':plan['question'],'mechanism_family':'conditional_post_fomc_reversal','mechanism_description':plan['information_clock'],'current_source_card_paths':[rel(cardpath)],'source_evidence_bindings':ev,'sources':sources,'candidate_matrix_revisions':['6 source nestedstate/riskdepth streams ofone fixedmechanism;14controls andhostviews diagnostic; no selection/campaign breadth.'],'difference_from_existing':['Late postmeeting conditionalreaction contrasts genericreversal; sealed singlepremeetingdriftexcluded.'],'hypothesis_links':[rel(P/'scientific-plan.json')],'topic_coverage':['source_fidelity','causal_clock','net_cost','cash','risk_match','portfolio','power','recent_counterevidence']}
write(D/'external-brief.json',external)
(D/'external-brief.md').write_text(plan['question']+'\n\nComplete definition: '+rel(P/'scientific-plan.json')+'\n')
(D/'hypotheses.md').write_text('H1: latephase improves drawdown-state net accountvalue overgenericreversal.\nH2: source deeperloss states preserveeventeffect withoutcapitalcosterasure.\nH3: actualSSO improves meaningfulreturn only ifrisk/cost/hostevidence supports.\n')
write(D/'evaluation-standard-freeze.json',{'iter_id':IT,'frozen_at':NOW,'evaluation_standard_path':'config/evaluation-standard-v2.json','sha256':bind('config/evaluation-standard-v2.json')['sha256']})
print('sourcefoundation',IT,bind(D/'direction-review.json'))
