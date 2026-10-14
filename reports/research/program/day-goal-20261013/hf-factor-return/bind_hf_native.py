"""Bind accepted method/input review into native contracts; no fitting or economic go."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
P = Path(__file__).parent
IT = 't20261013_hf_factor_conditional_method'
D = ROOT / 'reports/research/iterations' / IT
NOW = datetime.now(UTC).isoformat()


def bind(p):
    p = Path(p)
    return dict(path=str(p.resolve().relative_to(ROOT)), sha256=hashlib.sha256(p.read_bytes()).hexdigest(), bytes=p.stat().st_size)


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n')


plan = json.loads((P / 'scientific-plan.json').read_text())
impl = json.loads((P / 'implementation-manifest.json').read_text())
review = json.loads((P / 'independent-implementation-review.json').read_text())
assert review['verdict'] == 'approve_implementation' and review['author'] != review['reviewer']
refs = list(review['bindings'].values()) if isinstance(review['bindings'], dict) else review['bindings']
assert any(all(r.get(k) == bind(P / 'implementation-manifest.json')[k] for k in ['path', 'sha256']) for r in refs)
ids = [r['candidate_id'] for r in plan['candidates']]
path = 'conditional_hf_factor_method'
contracts = {
    kind: {key: dict(row, path=str(Path(row['path']).resolve().relative_to(ROOT)))
           for key, row in group.items()}
    for kind, group in impl['contracts'].items()
}
definition = dict(schema_version=1, research_role='market_component_method', iter_id=IT,
                  candidate_manifest_path=str((D / 'candidate-manifest.json').relative_to(ROOT)),
                  data_feasibility_path=str((D / 'data-feasibility.json').relative_to(ROOT)),
                  time_axis_kind='market_timestamp', claim_scope='conditional_cohort', real_market_claim=True,
                  candidate_ids=ids, **{name: bind(P / (name.replace('_', '-') + '.json')) for name in
                  ['scientific_plan', 'independent_plan_review', 'implementation_manifest', 'independent_implementation_review', 'execution_contract']},
                  promotion_eligible=False, paper_trading_allowed=False, broker_activity_allowed=False,
                  pit_universe_certified=False, deployment_readiness_claim=False)
save(D / 'method-definition.json', definition)
candidates = [dict(candidate_id=r['candidate_id'], path=path, role='conditional_current_vintage_method',
                   method=json.dumps(r, ensure_ascii=False), ablation='Bound20 source-led pipelines and six common-All-target contrasts',
                   fallback='Missing packet intraday zero-risk; funded single-attempt no-fill and affordable whole-lot skip',
                   mechanism_family='broad_factor_intraday_forecasting', mechanism='272 causal conditional source-factor predictors',
                   promotion_eligible=False, research_role='market_component_method',
                   method_definition_path=bind(D / 'method-definition.json')['path'], method_definition_sha256=bind(D / 'method-definition.json')['sha256'],
                   scale_curve_point=False, data_contract=path, feature_contract=path, label_contract=path,
                   validation_contract=path, cost_contract=path, benchmark_contract=path) for r in plan['candidates']]
save(D / 'candidate-manifest.json', dict(schema_version=3, iter_id=IT, research_role='market_component_method',
                                       manifest_type='generic_candidate_family_v1', generated_before_backtest=True, generated_at=NOW,
                                       candidate_count=20, spec_hashes={}, contracts=contracts, candidates=candidates))
required = {n: bind(f) for n, f in dict(input_acceptance=P/'independent-implementation-review.json', source_acceptance=P/'independent-complete-source-input-acceptance.json',
                                      raw_market_acceptance=P/'independent-market-cache-bridge-acceptance.json', independent_plan=P/'independent-plan-review.json',
                                      execution_clock=P/'execution-contract.json', input_warnings=P/'data-capability-review.json').items()}
save(D / 'data-feasibility.json', dict(schema_version=1, report_type='actual_market_component_conditional_input_acceptance', iter_id=IT,
 workflow_pass=True, research_pass=False, llm_contribution_pass=False, paper_ready_pass=False, historical_evaluation_authorized=True,
 authority='Independent complete scientific/source/market/feature/implementation acceptance for this conditional method; native/resource gates still required.',
 path_gates={path:dict(action='evaluate', historical_evaluation_go=True, candidate_ids=ids)},
 candidate_accounting=dict(frozen_candidate_count=20, evaluation_authorized_count=20, dependency_skipped_count=0, unresolved_count=0, balanced=True),
 candidate_authorization=dict(candidate_count=20, rows=[dict(candidate_id=c['candidate_id'], path=path, action='evaluate',
 reason_code='reviewed_conditional_current_vintage_inputs', candidate_binding_sha256=hashlib.sha256(json.dumps(c,sort_keys=True,separators=(',',':')).encode()).hexdigest()) for c in candidates]),
 required_reference_names=list(required), required_references=required, scope='Not source-original 15-minute legs/PIT/quote fills/actual settlement/OOS/paper readiness.'))
save(D / 'search-space.json', dict(schema_version=3, created_at=NOW, iter_id=IT, research_role='market_component_method',
 strategy_name='conditional_hf_factor_method', source_spec_path=None, spec_hash=None, total_candidate_budget=20,
 single_mechanism_no_campaign_attestation=True, candidate_manifest_path=bind(D/'candidate-manifest.json')['path'],
 candidate_manifest_sha256=bind(D/'candidate-manifest.json')['sha256'], candidate_manifest_contract='generic_candidate_family_v1',
 paths=[dict(name=path,candidate_count=20,hypothesis_refs=['H1','H2','H3'], parameters=dict(definitions=ids,no_posttest_selection=True),
 benchmark_family=['SPY','BIL_physical_CIL_NA_if_odd','CASH','SPY_overnight_only','PLS_MKT','KEY6','MINUS5','STALE','AR1_AR4_AR26','OLS','HOST_F1_net10','HOST_EW_net10'])],
 trial_ledger_paths=[str((D/'trial-ledger.jsonl').relative_to(ROOT))], evaluation_report_paths=[str((D/'evaluation-report.json').relative_to(ROOT))],
 cost_table_path=str((D/'costs-contract.json').relative_to(ROOT)),data_feasibility_path=bind(D/'data-feasibility.json')['path'],
 data_feasibility_sha256=bind(D/'data-feasibility.json')['sha256'],contracts=contracts))
(D/'search-space.md').write_text('One fixed mechanism,20 fullsource pipelines; common target contrasts, three measurement views, 800 four-rule diagnostics and complete physical100 fee/40 host books. No posttest policy changes or promotion.\n')
(D/'decision-record.md').write_text('Independent source/scientific/implementation input accepted for conditional method. Native knowledge/iteration and fresh resource gate pending; economic execution remains false. No paper/order/promotion claim.\n')
print(json.dumps(dict(iter_id=IT,candidate_manifest=bind(D/'candidate-manifest.json'),economic_admission=False)))
