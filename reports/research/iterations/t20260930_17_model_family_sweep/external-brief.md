# External Brief: t20260930_17_model_family_sweep

## Objective

T-20260930-17 (stage 1): on the cached T-20260928-10 monthly panel (302,433 rows, 2016-05 to 2023-08, close >= $3, 21d ADV >= $1M, funds excluded, delisted included) and B0's 24 price-volume features, does swapping the model family (LightGBM, XGBoost, CatBoost, Ridge, NN3-shaped MLP, rank-mean ensemble), the training window (3y rolling vs expanding) or the horizon (21d vs 63d) raise the stress-window walk-forward RankIC by >= 0.010 (t >= 3.0) over same-cell LightGBM?

## Sources

8 source cards recorded in `external-brief.json`
(4 paper-type). Source card records: `reports/harness/source_cards/t20260930_17_model_family_sweep.jsonl`.
Topic coverage: ml_return_prediction_gu_kelly_xiu, ml_profit_limits_to_arbitrage_avramov, tree_vs_deep_tabular_grinsztajn, deep_asset_pricing_chen_pelger_zhu, lightgbm_parameters, xgboost_parameters, catboost_parameters, sklearn_mlp_parameters.

## Scope

This brief supports the single-mechanism lightweight path (search-space
`single_mechanism_no_campaign_attestation: true`). Its evidence backs the
preregistered candidate grid for path `model_family_sweep_stage1` only, not any other
mechanism family or promotion decision.
