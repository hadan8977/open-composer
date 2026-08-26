# Harness Plan — us_pit_semantic_theme_r20_m02

Generated: 2026-08-05

## Risk Domains

- daily_open_execution
- leveraged_etf

## Required Skills

- backtest-forensics
- execution-reality-reviewer
- source-researcher

## Required Artifacts

- execution_policy
- execution_reality_report
- gap_stress_report
- leveraged_etf_risk_note
- source_cards

## Blocking Rules

- **naked_market_order_must_be_justified** (blocks `research_pass`): A DAY market order without price protection requires a written justification in execution_policy explaining why the risk is acceptable.

- **compare_at_least_two_execution_methods** (blocks `research_pass`): Execution policy must compare at least two order styles (e.g. DAY market vs. MOO/OPG vs. LOO/OPG).

- **leveraged_etf_paper_auto_requires_stress** (blocks `paper_ready_pass`): paper_auto activation for a leveraged ETF strategy requires a completed gap_stress_report and leveraged_etf_risk_note.

