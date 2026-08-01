# Harness Plan — us_multiscale_event_momentum_r5

Generated: 2026-07-18

## Risk Domains

- llm_or_news_signal

## Required Skills

- data-capability-reviewer
- source-researcher

## Required Artifacts

- capability_review
- feature_packet_schema
- marginal_lift_report
- missing_modality_robustness_report
- pit_replay_evidence

## Blocking Rules

- **no_live_llm_call_inside_backtest** (blocks `research_pass`): LLM and news calls must be replayed from PIT packets during backtest; live API calls inside the backtest loop are prohibited.

- **llm_alpha_requires_quant_baseline** (blocks `research_pass`): An LLM or news-driven strategy must include a deterministic (non-LLM) baseline and a marginal_lift_report showing additive value.

