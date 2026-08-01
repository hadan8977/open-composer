# Harness Plan — us_multiasset_forward_mm_r5_l01

Generated: 2026-07-31

## Risk Domains

- daily_open_execution

## Required Skills

- execution-reality-reviewer
- source-researcher

## Required Artifacts

- execution_policy
- execution_reality_report
- source_cards

## Blocking Rules

- **naked_market_order_must_be_justified** (blocks `research_pass`): A DAY market order without price protection requires a written justification in execution_policy explaining why the risk is acceptable.

- **compare_at_least_two_execution_methods** (blocks `research_pass`): Execution policy must compare at least two order styles (e.g. DAY market vs. MOO/OPG vs. LOO/OPG).

