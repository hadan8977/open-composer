# Harness Plan — nasdaq_long_short_event_router_15m_sweep_001

Generated: 2026-05-23

## Risk Domains

- llm_or_news_signal
- router_strategy
- short_selling

## Required Skills

- backtest-forensics
- data-capability-reviewer
- execution-reality-reviewer
- source-researcher

## Required Artifacts

- borrow_cost_estimate
- ex_dividend_risk_note
- feature_packet_schema
- marginal_lift_report
- missing_modality_robustness_report
- pit_replay_evidence
- router_cost_stress
- router_data_evidence
- router_execution_observation
- router_rebalance_intents
- router_target_weights
- router_validation
- short_exposure_policy
- short_sale_source_cards
- short_squeeze_stress

## Blocking Rules

- **no_live_llm_call_inside_backtest** (blocks `research_pass`): LLM and news calls must be replayed from PIT packets during backtest; live API calls inside the backtest loop are prohibited.

- **llm_alpha_requires_quant_baseline** (blocks `research_pass`): An LLM or news-driven strategy must include a deterministic (non-LLM) baseline and a marginal_lift_report showing additive value.

- **router_requires_target_weight_observation** (blocks `research_pass`): Router strategy promotion requires target weights, rebalance intents, cost stress, data evidence, and validation artifacts.

- **router_order_authorization_requires_readiness** (blocks `paper_ready_pass`): Router execution can remain observation_only before paper order authorization; broker orders require paper readiness and safety artifacts.

- **short_requires_borrow_and_rule_evidence** (blocks `research_pass`): Short-selling research pass requires broker/rule source cards and borrow/shortable evidence.

- **short_paper_ready_requires_squeeze_and_dividend_stress** (blocks `paper_ready_pass`): Paper readiness for short exposure requires squeeze stress and ex-dividend risk review.

