# Harness Plan — stock_liquidity_causal_inventory_20261023

Generated: 2026-10-23

## Risk Domains

- daily_open_execution
- router_strategy
- short_selling

## Required Skills

- backtest-forensics
- execution-reality-reviewer
- source-researcher

## Required Artifacts

- borrow_cost_estimate
- ex_dividend_risk_note
- execution_policy
- execution_reality_report
- router_cost_stress
- router_data_evidence
- router_execution_observation
- router_rebalance_intents
- router_target_weights
- router_validation
- short_exposure_policy
- short_sale_source_cards
- short_squeeze_stress
- source_cards

## Blocking Rules

- **naked_market_order_must_be_justified** (blocks `research_pass`): A DAY market order without price protection requires a written justification in execution_policy explaining why the risk is acceptable.

- **compare_at_least_two_execution_methods** (blocks `research_pass`): Execution policy must compare at least two order styles (e.g. DAY market vs. MOO/OPG vs. LOO/OPG).

- **router_requires_target_weight_observation** (blocks `research_pass`): Router strategy promotion requires target weights, rebalance intents, cost stress, data evidence, and validation artifacts.

- **router_order_authorization_requires_readiness** (blocks `paper_ready_pass`): Router execution can remain observation_only before paper order authorization; broker orders require paper readiness and safety artifacts.

- **short_requires_borrow_and_rule_evidence** (blocks `research_pass`): Short-selling research pass requires broker/rule source cards and borrow/shortable evidence.

- **short_paper_ready_requires_squeeze_and_dividend_stress** (blocks `paper_ready_pass`): Paper readiness for short exposure requires squeeze stress and ex-dividend risk review.

