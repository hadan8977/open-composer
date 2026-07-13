# Harness Plan — us_mom_minute_p1_003_frozen

Generated: 2026-07-13

## Risk Domains

- leveraged_etf
- router_strategy

## Required Skills

- backtest-forensics
- execution-reality-reviewer

## Required Artifacts

- gap_stress_report
- leveraged_etf_risk_note
- router_cost_stress
- router_data_evidence
- router_execution_observation
- router_rebalance_intents
- router_target_weights
- router_validation

## Blocking Rules

- **leveraged_etf_paper_auto_requires_stress** (blocks `paper_ready_pass`): paper_auto activation for a leveraged ETF strategy requires a completed gap_stress_report and leveraged_etf_risk_note.

- **router_requires_target_weight_observation** (blocks `research_pass`): Router strategy promotion requires target weights, rebalance intents, cost stress, data evidence, and validation artifacts.

- **router_order_authorization_requires_readiness** (blocks `paper_ready_pass`): Router execution can remain observation_only before paper order authorization; broker orders require paper readiness and safety artifacts.

