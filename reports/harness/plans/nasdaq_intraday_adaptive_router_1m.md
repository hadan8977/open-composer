# Harness Plan — nasdaq_intraday_adaptive_router_1m

Generated: 2026-05-21

## Risk Domains

- short_sample

## Required Skills

- backtest-forensics

## Required Artifacts

- short_sample_caveat

## Blocking Rules

- **short_sample_cannot_research_pass_without_caveat** (blocks `research_pass`): A short-sample backtest requires a written short_sample_caveat documenting sample limitations before research_pass is granted.

