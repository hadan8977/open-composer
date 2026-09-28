# h20260928_06_registry_stock_batch3

K1: Sharpe(10bp) >= 1.19 anchor / >= 0.65 stress AND CAGR(20bp) > 0 both windows.
K2: diversifier edge (S3+candidate vs vol-matched k*S3+(1-k)*SHY) >= 0.05 Sharpe both windows.

| candidate | anchor Sharpe(10bp) | stress Sharpe(10bp) | edge anchor | edge stress | corr anchor | corr stress | DSR anchor | tier |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| momentum_concentrated_k37 | 1.03 | 0.51 | -0.143 | -0.071 | 0.29 | 0.32 | 0.545 | none |
| skew_52wk_high_k95 | 0.82 | 0.54 | -0.008 | -0.014 | 0.31 | 0.37 | 0.409 | none |
| vam_momentum_k50 | 0.95 | 0.57 | -0.105 | -0.025 | 0.30 | 0.33 | 0.492 | none |
| a13d_item4_h6 | 0.15 | 0.21 | -0.195 | -0.235 | 0.07 | 0.19 | 0.092 | none |
| a13d_item4_h12 | 0.33 | 0.10 | -0.099 | -0.279 | 0.13 | 0.23 | 0.148 | none |
| a13d_item4_h24 | 0.49 | 0.04 | -0.270 | -0.255 | 0.17 | 0.26 | 0.218 | none |
| monday_afternoon_spy | 0.51 | -0.07 | -0.150 | -0.331 | 0.34 | 0.37 | 0.225 | none |
| monday_afternoon_qqq | 0.63 | -0.03 | -0.234 | -0.351 | 0.45 | 0.44 | 0.292 | none |
| overnight_only_spy | -3.99 | -3.59 | -2.500 | -2.296 | 0.39 | 0.29 | 0.000 | none |
| overnight_only_qqq | -2.45 | -2.97 | -1.855 | -1.874 | 0.47 | 0.34 | 0.000 | none |

Kept (K1 or K2): none

## needs_modal (Modal cloud lane, task T-20260928-12)

Three rows need a broad-universe, multi-year minute-bar panel this 4GB box
cannot hold or build cheaply (`data/features/minute_panel` covers only SPY;
the raw `data/sip/minute` archive is 29G). Not shrunk into a same-day-close
proxy, per the owner's addendum -- see `results.json`'s `needs_modal` list for
full detail.

| id | universe | date range | granularity | why local can't do it |
|---|---|---|---|---|
| dir:signed_jump_variation | top-500 PIT broad | 2016-2025 | 5-min or finer realized variance | no broad minute panel; 29G raw archive |
| dir:end_of_day_reversal | top-500 PIT broad | 2016-2025 | 1-min bars at 15:30 ET | no broad minute panel |
| dir:intraday_reversal_reit_pwb | top-500 PIT broad + REITs | 2016-2025 | first-half-hour (09:30-10:00 ET) | real mechanism (overnight predicts first half hour) needs intraday bars, discovered by opening the primary source this pass |

## Not-testable-now rows (blocker recorded in the registry append, not run here)

classic_anomalies_beta_size_europe_pwb, dual_class_share_arbitrage_pwb,
option_implied_variance_premium_pwb, nominal_price_anomaly_pwb,
market_inefficiency_scoring_pwb, frontier_market_factor_pricing_pwb,
esg_smart_beta_pwb, long_short_ratio_extension_pwb, classic_anomalies_factor_reviews_pwb,
risk_based_portfolio_construction_pwb, deep_learning_stat_arb_residual,
ml_implied_risk_premia_pwb, collective2_adaptive_investments_knn_tqqq_sqqq,
buy_side_analyst_recommendations_pwb, patent_grant_event_kpss,
index_rebalance_flow_prediction, event_8k_item402_restatement_drift,
tactical_mean_reversion_multi_asset_pwb, moving_average_volume_heuristic_pwb,
trend_filtered_mean_variance_pwb, ema_crossover_atr_paper_track -- each has an
exact blocker and `reopen_if` in the `reports/research/harvest/directions.jsonl`
append for that id.

## Note on the AEGIS candidate (vam_momentum_k50)

dir:volatility_gated_momentum_aegis was forwarded mid-round, before this
dossier's manifest was frozen or any result computed; its testable partial
(step-1-only volatility-adjusted-momentum) was added to the same preregistered
manifest as `vam_momentum_k50` and ran in the same pass. The other four
forwarded rows (tactical_mean_reversion_multi_asset_pwb,
moving_average_volume_heuristic_pwb, trend_filtered_mean_variance_pwb,
ema_crossover_atr_paper_track) were all classified not-testable-now (undisclosed
formula, portfolio-optimization mechanism mismatch, or a new per-symbol
trigger/stop engine this batch's brief restricts against building), so no
separate follow-up run was needed for them.

