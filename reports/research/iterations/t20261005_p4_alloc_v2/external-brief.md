# External Brief: t20261005_p4_alloc_v2

## Objective

Program allocation v2 (P4): choose a walk-forward, forecast-free allocation of the paper sleeves that beats the ETF pilot P0 (0.642 S3 + 0.358 C2) at the same volatility, or else the tightest single-sleeve risk-share cap whose recent Sharpe cost is within 0.10 and that helps in stress; size it per capital tier and account type under the ~30% drawdown budget, minimum sleeve capital and Alpaca margin rules, and report DSR-deflated drawdown quantiles.

## Sources

9 source cards recorded in `external-brief.json`
(7 paper-type). Source card records: `reports/harness/source_cards/t20261005_p4_alloc_v2.jsonl`.
Topic coverage: risk_budgeting_equal_risk_contribution, estimation_error_naive_diversification, risk_parity_solvers_and_heuristics, broker_margin_leveraged_etf_rules, regulatory_leveraged_etf_margin, multiple_testing_deflated_sharpe, drawdown_distribution_and_stop_rules, factor_risk_contribution_theme, local_sleeve_combination_refutation.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `program_allocation_v2` only, not any other
mechanism family or promotion decision.
