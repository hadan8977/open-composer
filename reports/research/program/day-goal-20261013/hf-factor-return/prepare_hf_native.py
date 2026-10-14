"""Wrap frozen source/scientific artifacts; no market inference or fitting."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
P = Path(__file__).parent
IT = 't20261013_hf_factor_conditional_method'
D = ROOT / 'reports/research/iterations' / IT
D.mkdir(exist_ok=True)
NOW = datetime.now(UTC).isoformat()


def rel(p):
    return str(Path(p).resolve().relative_to(ROOT))


def bind(p):
    p = Path(p)
    return dict(path=rel(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest(), bytes=p.stat().st_size)


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n')


plan = json.loads((P / 'scientific-plan.json').read_text())
assert hashlib.sha256((P / 'scientific-plan.json').read_bytes()).hexdigest() == '666b4048c26f98ce9ce02c9b66b2e1982e805d9ec43e8e94de9a314280a7e7fd'
cardpath = ROOT / 'reports/harness/source_cards/day20261013_hf_factor_method.jsonl'
cardpath.parent.mkdir(exist_ok=True)
original = json.loads((P.parent / 'primary-return-breadth/sources/download-ledger.json').read_text())
mainfetch = next(r for r in original if r['id'] == 'hf_zoo')['fetched_at_utc']
facts = [
    ('hf_main', P / 'hf-zoo-read.txt', 'https://public.econ.duke.edu/~boller/Papers/MS_2025.pdf', mainfetch,
     '2025-01-02', 'Intraday Market Return Predictability Culled from the Factor Zoo',
     'The authors forecast broad market returns from 272 factor portfolios. Their original economic measures use intraday gross second moments and quoted costs; published arithmetic means are not funded account CAGR.'),
    ('hf_OA', P / 'sources/hf-zoo-appendix.txt', 'https://public.econ.duke.edu/~boller/Papers/HFML_Sup_App.pdf', '2026-10-13T14:12:15.125900+00:00',
     '2024-07-18', 'OA.2',
     'OA.2 uses exante lagged bipower variation rather than same-day completed BV. OA.3 refits nonlinear models each five years. OA.5.2 supports symmetric mathematical thresholds, without proving actual author code.'),
    ('hf_construct', P / 'sources/factor-construction-paper.txt', 'https://drive.usercontent.google.com/download?id=13i37t75e0tVz1hh7FASWbw8coQnQmI4k&export=download', '2026-10-13T14:46:53.111224+00:00',
     '2023-10-01', 'The High-Frequency Factor Zoo',
     'Full-day cleaning, interpolation and additive adjustment contaminate a PIT claim. Equal-length simple-sum differences cancel a constant additive term; log compounding does not share that identity.'),
]
cards, sources, evidence = [], [], []
for ident, path, url, fetched, published, quote, claim in facts:
    assert quote in path.read_text(), (ident, path)
    b = bind(path)
    cards.append(dict(claim_id=ident, claim=claim, source_url=url, source_type='paper', fetched_at=fetched,
                      source_sha256=b['sha256'], quote=quote, verification_status='source_verified',
                      limitations='Original source read; no original 15-minute leg/PIT/execution/economic result reproduction is claimed.'))
    sources.append(dict(claim_id=ident, claim=claim, url=url, source_type='paper', published_or_updated_at=published,
                        market_and_period='US factor portfolios 1996-2020; conditional 2016-2020 SPY funding',
                        applicability='Source-supported complete same-target method comparison',
                        limitations=cards[-1]['limitations'], independent_replication='None claimed for original source implementation',
                        fetched_at=fetched, snapshot_path=b['path'], sha256=b['sha256'], source_card_path=rel(cardpath),
                        credibility='Actual author primary paper/appendix', core_claim=claim,
                        reflection='Conditional current-vintage method evidence, no unseen OOS or tradability qualification',
                        project_applicability='Reviewed 20-pipeline nonpromotable market-component method'))
    evidence.append(dict(claim_id=ident, source_card_path=rel(cardpath), snapshot_path=b['path'], snapshot_sha256=b['sha256'], source_url=url))
cardpath.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in cards))
ledger = json.loads((P / 'continuation-source-request-ledger.json').read_text())
queries = [dict(query=r['query'], searched_at=r['started_at_utc'], opened_urls=[f[2] for f in facts])
           for r in ledger if r.get('query') and r.get('operation') == 'web.search primaryofficial paths']
assert queries
save(P / 'native-query-manifest.json', dict(queries=queries, source_receipts=bind(P / 'continuation-source-request-ledger.json'),
     interpretation='Recorded actual continuation primary-source searches; source fetch times remain their own retained receipts, no new requests.'))
save(P / 'native-knowledge-baseline.json', dict(created_at=NOW, phase='Native wrapping before any economic fit; already authorized intake retained',
     no_economic_execution=True, prior_results=[bind(P.parent / 'primary-return-breadth/root-result-acceptance.json'),
     bind(P / 'root-source-continuation-decision.json'), bind(P / 'independent-plan-review.json')],
     scope='Known sealed failures and prior source-resource decision are preserved; current admitted source/implementation preparation is not pretended untouched.'))
texts = dict(objective=plan['question'], target_regime_and_horizon='1996-2020 public source; annual 2004-2020 chronological tests; actual SPY 2016-2020 funded proxy. All seen, nonpromotable.',
 existing_solution_comparison='Original broad FF forecast/quoted-cost execution vs current-vintage IDX/SUM/INV, same PLS market-only/key6/minus5/stale and full HGB algorithm controls. Direct SPY refitting is not substituted.',
 remaining_evidence_gap='Original 15-minute leg/code/TAQ quotes/PIT not recovered. Reviewed APP reconstruction and raw SPY actual actions/cache suffice only for the bound conditional question. Complete native/knowledge and fresh resource gates still required.',
 negative_experiments_checked=plan['source_and_difference']['counterevidence'],
 cost_and_execution_assumptions=json.dumps(plan['execution_and_capital'], ensure_ascii=False),
 stop_condition=plan['decision_rule'])
save(D / 'direction-review.json', dict(schema_version=3, iter_id=IT, reviewed_at=NOW, decision='proceed', **texts,
 queries=queries, sources=sources, query_manifest=bind(P / 'native-query-manifest.json'),
 pre_iteration_knowledge_baseline=bind(P / 'native-knowledge-baseline.json'), source_evidence_bindings=evidence,
 cheapest_decisive_test=dict(action='Complete fixed20 pipelines and registered diagnostics/physical funding/host, starting admitted 2019 HGB calibration only after all gates.',
 pass_condition='Measured full remaining package fits7006.69 and reveals decision-relevant net account and method contribution.',
 falsification_condition='Stop current application on complete costed evidence; full computation that cannot fit requires an explicit resource/scientific decision. No cheap-test mechanism refutation.', max_compute_minutes=7006.69/60)))
save(D / 'external-brief.json', dict(schema_version=3, iter_id=IT, research_role='market_component_method', strategy_name='conditional_hf_factor_method',
 source_spec_path=None, spec_hash=None, registered_at=NOW, objective=plan['question'], mechanism_family='broad_factor_intraday_forecasting',
 mechanism_description='Full272 current/hour/previous-packet predictors, three reviewed measurements, exante Cts labels, matched source chronological CV and nonlinear cadence.',
 current_source_card_paths=[rel(cardpath)], source_evidence_bindings=evidence, sources=sources,
 candidate_matrix_revisions=['20 fixed source-led pipelines, six same-All-target primary contrasts, full 800 rule/cost/latency diagnostics, whole20k and independent4k host. No promotion cohort.'],
 difference_from_existing=['Original factor-leg aggregation/cost/SR not silently equated to APP', 'No source-dependent preselection or test-performance hyperparameter fitting'],
 hypothesis_links=[rel(P / 'scientific-plan.json')], topic_coverage=['source_fidelity','exante_clock','measurement','algorithm','cost','capital','portfolio','power']))
(D / 'external-brief.md').write_text(plan['question'] + '\n\nComplete approved definition: ' + rel(P / 'scientific-plan.json') + '\n')
(D / 'hypotheses.md').write_text('H1: Same PLS broad information improves shared All market target versus market-only, removed and stale controls.\nH2: Full-information HGB adds algorithm value; INV diagnoses the measured contribution of source constant adjustment, without identifying PIT or nonlinear factor attribution.\nH3: Explicit four rules/costs/latency and funded SPY cash clock expose economic contribution and matched independent4k host value.\n')
save(D / 'evaluation-standard-freeze.json', dict(iter_id=IT, frozen_at=NOW, evaluation_standard_path='config/evaluation-standard-v2.json', sha256=bind('config/evaluation-standard-v2.json')['sha256']))
save(D / 'knowledge-scout-queries.json', dict(schema_version=1, iter_id=IT, queries=[], curated_candidates=[dict(title=f[5], url=f[2], summary=f[6]) for f in facts], max_results_per_query=3,
 reuse_reason='Already fetched/verified official primary sources; source300 received and no new network resolution needed.'))
print(json.dumps(dict(iter_id=IT, source_queries=len(queries), source_cards=len(cards), direction_review=bind(D / 'direction-review.json'), economic_admission=False)))
