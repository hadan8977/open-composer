# External Brief: t20261004_book_v14_ml

## Objective

Equity book v1.4 candidate: does an out-of-sample ML composite of the same 22 slow theme inputs plus log size (M2 GBDT rank-mean of LightGBM/XGBoost/CatBoost on the 21-session book-aligned label; M3 DKKM random-Fourier-feature ridge SDF, P = 4,000, on the 5-session book-aligned return), or an equal blend of M0 with either, raise the offset-median net Sharpe of the unchanged v1.2 construction (U3000) by >= 0.10 in both the recent 2024-01-08..2026-09-15 and the stress-ML 2019-01-02..2023-08-31 windows, with annual expanding refits from 2019, a 43-session embargo and the same costs, and does it survive the paired test, account layer, placebo and family-19 DSR tier?

## Sources

8 source cards recorded in `external-brief.json`
(5 paper-type). Source card records: `reports/harness/source_cards/t20261004_book_v14_ml.jsonl`.
Topic coverage: random_fourier_feature_sdf_virtue_of_complexity, gbdt_ensemble_cross_sectional_ranking, linear_vs_ml_forecasts_after_costs, cost_aware_ml_portfolio_implementable_frontier, anomaly_net_of_cost_decay, professional_longshort_net_sharpe_benchmark, factor_replication_themes, broker_margin_short_rules.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `ml_composite_book_v14` only, not any other
mechanism family or promotion decision.
