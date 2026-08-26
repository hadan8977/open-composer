# Harness Plan — nasdaq_tqqq_fixed_etf_router_daily_iter11_exposure_search_paper_auto_candidate

Generated: 2026-08-05

## Risk Domains

- daily_open_execution
- leveraged_etf
- paper_auto
- broker_specific
- router_strategy

## Required Skills

- backtest-forensics
- execution-reality-reviewer
- paper-auto-safety-reviewer
- source-researcher

## Required Artifacts

- execution_policy
- execution_reality_report
- gap_stress_report
- leveraged_etf_risk_note
- paper_safety_review
- router_cost_stress
- router_data_evidence
- router_execution_observation
- router_rebalance_intents
- router_target_weights
- router_validation
- source_cards

## Blocking Rules

- **naked_market_order_must_be_justified** (blocks `research_pass`): A DAY market order without price protection requires a written justification in execution_policy explaining why the risk is acceptable.

- **compare_at_least_two_execution_methods** (blocks `research_pass`): Execution policy must compare at least two order styles (e.g. DAY market vs. MOO/OPG vs. LOO/OPG).

- **leveraged_etf_paper_auto_requires_stress** (blocks `paper_ready_pass`): paper_auto activation for a leveraged ETF strategy requires a completed gap_stress_report and leveraged_etf_risk_note.

- **paper_auto_requires_harness_verify** (blocks `paper_ready_pass`): paper_auto activation is blocked until oc harness verify passes for this spec. The verify output must be present in reports/harness/verify/.

- **paper_order_must_link_signal** (blocks `paper_ready_pass`): Every paper order must record signal_id, spec_version, spec_hash, and execution_policy_id for audit traceability.

- **broker_order_type_must_be_sourced** (blocks `research_pass`): Any order type or time_in_force value used in execution_policy must have a corresponding source card pointing to official broker docs.

- **router_requires_target_weight_observation** (blocks `research_pass`): Router strategy promotion requires target weights, rebalance intents, cost stress, data evidence, and validation artifacts.

- **router_order_authorization_requires_readiness** (blocks `paper_ready_pass`): Router execution can remain observation_only before paper order authorization; broker orders require paper readiness and safety artifacts.

