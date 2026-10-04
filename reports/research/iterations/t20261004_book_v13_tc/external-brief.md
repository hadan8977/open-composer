# External Brief: t20261004_book_v13_tc

## Objective

Equity book v1.3 candidate: can a preregistered cost-aware trading rule (Garleanu-Pedersen partial adjustment at rate 1/2 or 1/3, the same on the unit book with the VIX scale applied at once, or a Novy-Marx-Velikov style no-trade band of 0.25 / 0.50 weight SD) raise the net Sharpe of the unchanged v1.2 primary book M0_U3000 by at least 0.10 in both the recent (2024-01-08..2026-09-15) and the stress (2017-10-02..2023-08-31) window, against full rebalancing (B0, R6 identity), with a paired Newey-West t >= 2, and keep the gain in the account layer (whole shares, $100 minimum order) so the paper book trades cheaper without changing its signal.

## Sources

8 source cards recorded in `external-brief.json`
(6 paper-type). Source card records: `reports/harness/source_cards/t20261004_book_v13_tc.jsonl`.
Topic coverage: dynamic_trading_partial_adjustment_aim_portfolio, buy_hold_spread_no_trade_band_cost_mitigation, cost_aware_ml_portfolio_implementable_frontier, trading_cost_square_root_impact, anomaly_net_of_cost_decay, professional_longshort_net_sharpe_benchmarks, factor_theme_replication_slow_signals, broker_margin_rules_reg_t.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `cost_aware_trading_rules_book_v13` only, not any other
mechanism family or promotion decision.
