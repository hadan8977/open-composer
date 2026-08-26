# Harness Plan — us_breadth_calendar_flow_r1_cal02

Generated: 2026-08-17

## Risk Domains

- daily_open_execution
- router_strategy

## Required Skills

- backtest-forensics
- execution-reality-reviewer
- source-researcher

## Required Artifacts

- execution_policy
- execution_reality_report
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

- **router_requires_target_weight_observation** (blocks `research_pass`): Router strategy promotion requires target weights, rebalance intents, cost stress, data evidence, and validation artifacts.

- **router_order_authorization_requires_readiness** (blocks `paper_ready_pass`): Router execution can remain observation_only before paper order authorization; broker orders require paper readiness and safety artifacts.

