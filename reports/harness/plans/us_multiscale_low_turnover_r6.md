# Harness Plan — us_multiscale_low_turnover_r6

Generated: 2026-07-19

## Risk Domains

- daily_open_execution
- llm_or_news_signal

## Required Skills

- data-capability-reviewer
- execution-reality-reviewer
- source-researcher

## Required Artifacts

- capability_review
- execution_policy
- execution_reality_report
- feature_packet_schema
- marginal_lift_report
- missing_modality_robustness_report
- pit_replay_evidence
- source_cards

## Blocking Rules

- **naked_market_order_must_be_justified** (blocks `research_pass`): A DAY market order without price protection requires a written justification in execution_policy explaining why the risk is acceptable.

- **compare_at_least_two_execution_methods** (blocks `research_pass`): Execution policy must compare at least two order styles (e.g. DAY market vs. MOO/OPG vs. LOO/OPG).

- **no_live_llm_call_inside_backtest** (blocks `research_pass`): LLM and news calls must be replayed from PIT packets during backtest; live API calls inside the backtest loop are prohibited.

- **llm_alpha_requires_quant_baseline** (blocks `research_pass`): An LLM or news-driven strategy must include a deterministic (non-LLM) baseline and a marginal_lift_report showing additive value.

