# External Brief: t20261005_p1_s0_decay

## Objective

P1 mid-frequency engine Stage 0 (measurement, promotion-only): for the 53 fast signals already in the equity-book signal store, seven new daily fast signals and three fast composites, measure on U3000 by liquidity bucket the daily industry- and beta-neutral rank-IC decay (lags 1..22), persistence, half-life and net Sharpe versus trading speed at a close fill with cost model v1, and promote to the Stage 2 book-level test the objects whose recent-window implementable information is significant.

## Sources

12 source cards recorded in `external-brief.json`
(11 paper-type). Source card records: `reports/harness/source_cards/t20261005_p1_s0_decay.jsonl`.
Topic coverage: signal_half_life_and_holding_period, short_term_reversal_decomposition, residual_reversal_stat_arb, volume_shock_return_premium, overnight_intraday_return_components, optimal_partial_trading_speed, cost_mitigation_buy_hold_spread, anomaly_trading_costs_capacity, local_fast_alpha_daily_measurement.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `fast_signal_decay_p1_s0` only, not any other
mechanism family or promotion decision.
