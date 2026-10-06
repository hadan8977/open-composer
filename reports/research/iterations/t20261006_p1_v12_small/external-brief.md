# External Brief: t20261006_p1_v12_small

## Objective

v1.2 small-capital construction: can the unchanged v1.2 M0_U3000 book run in a $50,000 Alpaca account (fractional DAY-order longs, whole-share ETB shorts) and keep >= 0.80 of the full $1M account's recent Sharpe (F1 excess over BIL, F2 information ratio over SPY), with V2 feasibility, by concentrating to the top-K names per side (R1, R1B) or by dropping the short stock leg (R3)?

## Sources

12 source cards recorded in `external-brief.json`
(4 paper-type). Source card records: `reports/harness/source_cards/t20261006_p1_v12_small.jsonl`.
Topic coverage: small_account_whole_share_rounding_feasibility, cardinality_constrained_portfolio_concentration, long_leg_versus_short_leg_factor_value, constraint_cost_transfer_coefficient, broker_fractional_and_short_sale_rules, paper_simulator_fill_realism, sharpe_difference_inference_low_power, index_relative_underweight_extension.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `v12_small_capital_construction` only, not any other
mechanism family or promotion decision.
