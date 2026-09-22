# Giants sweep -- giants_sweep_20260922

Engine `scripts/run_giants_sweep.py`, manifest `config/giants_sweep/manifest.yaml`. 24 preregistered cells from families F1_trend_rsi_hedge, F2_two_leg_hedged_rotation, F4_fixed_weight_leverage, F5_canary_breadth_defense, F6_industry_trend_following, F7_overnight_effect. Windows, costs, fills, placebos and gate thresholds are the frozen ones from H-20260918-05 and H-20260922-02; nothing was tuned here.

## Windows and protocol

- `select` 2023-09-18 .. 2025-12-31
- `holdout` 2026-01-02 .. 2026-09-17
- `anchor` 2024-01-08 .. 2026-09-16
- costs `sum(|delta w|) * bps` charged on the execution session, 10 bp primary / 20 bp stress; signal on the close, fill at the next session's open.

## Benchmarks (buy and hold, no costs)

| benchmark | anchor CAGR | anchor max DD | anchor Sharpe | holdout Sharpe | select Sharpe |
|---|---|---|---|---|---|
| bench_SPY | 20.9% | -18.6% | 1.02 | 1.05 | 1.06 |
| bench_MTUM | 30.0% | -21.0% | 1.05 | 1.01 | 1.13 |
| bench_SPMO | 35.8% | -20.3% | 1.27 | 1.09 | 1.46 |
| bench_QQQ | 24.7% | -22.6% | 0.96 | 1.01 | 1.00 |
| bench_TQQQ | 53.5% | -57.2% | 0.93 | 0.96 | 0.98 |

## All gates pass (0 cells, top 0 shown)

None.

## Partial pass (10 cells, top 10 shown)

| cell | family | anchor CAGR | anchor DD | anchor Sh | holdout Sh | select Sh | turnover/yr | placebo beat | 20bp anchor CAGR | G1 | G1' | G2 | G3 | G4 | G5 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `f1_tqqq_rsi_no_hedge_ablation` | F1_trend_rsi_hedge | 15.9% | -5.2% | 1.37 | 1.49 | 1.13 | 23.89 | 0.0% | 13.1% | no | no | yes | yes | no | yes |
| `f1_composer_tqqq_safe` | F1_trend_rsi_hedge | 35.8% | -24.0% | 0.93 | 0.65 | 1.07 | 18.67 | 10.0% | 33.3% | no | no | no | yes | no | yes |
| `f4_nine_sig_tqqq_agg` | F4_fixed_weight_leverage | 40.7% | -40.0% | 0.97 | 1.17 | 0.97 | 1.01 | 48.3% | 40.6% | no | no | yes | no | no | yes |
| `f1_composer_tqqq_rsi` | F1_trend_rsi_hedge | 26.8% | -12.1% | 0.79 | 0.74 | 0.86 | 31.36 | 5.0% | 22.8% | no | no | no | yes | no | yes |
| `f6_sector_trend_sma200` | F6_industry_trend_following | 11.2% | -10.7% | 0.72 | 0.62 | 0.72 | 2.92 | 5.0% | 10.9% | no | no | no | yes | no | yes |
| `f6_sector_tsmom_12m` | F6_industry_trend_following | 13.3% | -13.0% | 0.81 | 1.18 | 0.68 | 1.70 | 25.0% | 13.1% | no | no | yes | no | no | yes |
| `f5_baa_balanced` | F5_canary_breadth_defense | 9.7% | -10.4% | 0.49 | 1.20 | 0.15 | 10.95 | 100.0% | 8.5% | no | no | yes | no | no | yes |
| `f2_sector_leg_only_ablation` | F2_two_leg_hedged_rotation | 6.7% | -31.2% | 0.22 | 1.58 | -0.33 | 56.00 | 95.0% | 0.9% | no | no | yes | no | no | yes |
| `f2_hedged_sector_60_40` | F2_two_leg_hedged_rotation | 4.8% | -22.2% | 0.11 | 1.54 | -0.44 | 52.42 | 100.0% | -0.6% | no | no | yes | no | no | yes |
| `f2_hedged_sector_50_50` | F2_two_leg_hedged_rotation | 4.2% | -20.2% | 0.07 | 1.48 | -0.47 | 51.52 | 100.0% | -1.1% | no | no | yes | no | no | yes |

## Fail (14 cells, top 14 shown)

| cell | family | anchor CAGR | anchor DD | anchor Sh | holdout Sh | select Sh | turnover/yr | placebo beat | 20bp anchor CAGR | G1 | G1' | G2 | G3 | G4 | G5 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `f1_sp500_2x_leverage` | F1_trend_rsi_hedge | 26.9% | -21.1% | 0.95 | 0.75 | 0.99 | 13.44 | 60.0% | 25.2% | no | no | no | no | no | yes |
| `f5_accelerating_dual_momentum` | F5_canary_breadth_defense | 17.6% | -18.2% | 0.90 | 0.70 | 0.90 | 5.23 | 100.0% | 16.9% | no | no | no | no | no | yes |
| `f1_composer_ftlt20` | F1_trend_rsi_hedge | 45.9% | -38.7% | 0.85 | 0.66 | 0.90 | 23.15 | 15.0% | 42.5% | no | no | no | no | no | yes |
| `f5_accelerating_dual_momentum_3x` | F5_canary_breadth_defense | 29.9% | -33.8% | 0.83 | 0.79 | 0.75 | 5.23 | 100.0% | 29.2% | no | no | no | no | no | yes |
| `f4_hfea_55_45_quarterly` | F4_fixed_weight_leverage | 16.0% | -35.7% | 0.50 | 0.38 | 0.64 | 0.48 | 43.3% | 16.0% | no | no | no | no | no | yes |
| `f5_canary_over_s3_levered` | F5_canary_breadth_defense | 21.0% | -56.4% | 0.57 | 0.47 | 0.62 | 11.95 | 100.0% | 19.6% | no | no | no | no | no | yes |
| `f4_tqqq_tmf_50_50_bimonthly` | F4_fixed_weight_leverage | 15.5% | -38.5% | 0.46 | 0.45 | 0.59 | 0.66 | 50.0% | 15.4% | no | no | no | no | no | yes |
| `f4_hfea_55_45_monthly` | F4_fixed_weight_leverage | 14.0% | -36.7% | 0.44 | 0.36 | 0.58 | 0.58 | 43.3% | 14.0% | no | no | no | no | no | yes |
| `f6_sector_trend_sma126` | F6_industry_trend_following | 9.5% | -10.3% | 0.60 | 0.23 | 0.56 | 4.48 | 30.0% | 9.1% | no | no | no | no | no | yes |
| `f5_baa_aggressive_3x` | F5_canary_breadth_defense | -5.0% | -43.4% | 0.02 | -0.08 | 0.13 | 10.95 | 100.0% | -6.0% | no | no | no | no | no | yes |
| `f5_baa_aggressive` | F5_canary_breadth_defense | 4.4% | -19.3% | 0.10 | 0.58 | -0.13 | 11.70 | 100.0% | 3.2% | no | no | no | no | no | yes |
| `f7_overnight_qqq_all_nights` | F7_overnight_effect | -26.2% | -55.7% | -2.49 | -2.64 | -2.65 | 504.00 | 75.0% | -55.4% | no | no | no | no | no | yes |
| `f7_overnight_qqq_skip_wed_fri` | F7_overnight_effect | -20.5% | -46.4% | -2.90 | -2.25 | -3.25 | 300.91 | 98.3% | -41.2% | no | no | no | no | no | yes |
| `f7_overnight_spy_skip_wed_fri` | F7_overnight_effect | -20.8% | -46.5% | -4.02 | -3.67 | -4.22 | 300.91 | 98.3% | -41.4% | no | no | no | no | no | yes |

## Gate definitions (unchanged from H-20260922-02)

- G1: anchor CAGR >= 50% and anchor max drawdown >= -35%
- G1': anchor Sharpe >= 2.0 and anchor CAGR >= 30%
- G2: holdout Sharpe >= 1.0 and holdout CAGR > 0
- G3: every declared placebo beats the true cell on select Sharpe <= 10% of seeds
- G4: G1 or G1' still holds at 20 bp per side
- G5: long-only spot US ETFs on the existing Alpaca daily cron

## Vol-matched excess over the benchmark family (anchor window)

| cell | vs SPY | vs MTUM | vs SPMO | vs QQQ | vs TQQQ |
|---|---|---|---|---|---|
| `f1_tqqq_rsi_no_hedge_ablation` | 12.0% | 22.3% | 14.2% | 20.7% | 116.6% |
| `f4_nine_sig_tqqq_agg` | -3.8% | -4.4% | -11.1% | -2.0% | 8.1% |
| `f1_sp500_2x_leverage` | -3.0% | -3.0% | -9.8% | -0.8% | 12.2% |
| `f1_composer_tqqq_safe` | -4.5% | -5.4% | -12.2% | -2.9% | 4.1% |
| `f5_accelerating_dual_momentum` | -1.8% | -1.0% | -7.9% | 0.9% | 19.0% |
| `f1_composer_ftlt20` | -6.9% | -9.2% | -15.7% | -6.2% | -7.3% |
| `f5_accelerating_dual_momentum_3x` | -6.2% | -8.2% | -14.8% | -5.3% | -5.0% |
| `f6_sector_tsmom_12m` | -1.7% | -0.9% | -7.9% | 0.9% | 19.4% |
| `f1_composer_tqqq_rsi` | -6.5% | -8.5% | -15.1% | -5.6% | -0.7% |
| `f6_sector_trend_sma200` | -2.3% | -1.9% | -8.8% | 0.1% | 15.9% |
| `f6_sector_trend_sma126` | -4.1% | -4.8% | -11.6% | -2.4% | 5.9% |
| `f5_canary_over_s3_levered` | -11.9% | -17.2% | -23.4% | -13.1% | -32.1% |
| `f4_hfea_55_45_quarterly` | -11.8% | -17.0% | -23.2% | -13.0% | -31.4% |
| `f5_baa_balanced` | -8.0% | -11.1% | -17.6% | -7.8% | -14.2% |
| `f4_tqqq_tmf_50_50_bimonthly` | -12.7% | -18.5% | -24.6% | -14.3% | -35.5% |
| `f4_hfea_55_45_monthly` | -12.7% | -18.5% | -24.7% | -14.3% | -35.6% |
| `f2_sector_leg_only_ablation` | -15.5% | -22.7% | -28.7% | -18.0% | -47.5% |
| `f2_hedged_sector_60_40` | -16.2% | -23.9% | -29.8% | -19.0% | -50.4% |
| `f5_baa_aggressive` | -16.9% | -24.9% | -30.8% | -19.9% | -52.8% |
| `f2_hedged_sector_50_50` | -16.7% | -24.6% | -30.5% | -19.6% | -52.1% |

## Caveats a reader must carry

- Engine regression: the three live sleeves reproduce `run_h20260918_05_recent_menu.rotation_cell` to 0.0000 Sharpe on the same panel. Against H-20260918-05 section 5 as printed the worst gap is 0.0415 (S1's holdout Sharpe, 2.18 today vs 2.22 in the card); the reference implementation reproduces 2.18 today too, so that is SIP archive drift since 2026-09-18.
- The F7 overnight cells are charged the frozen 10/20 bp per side, which is far stricter than the source paper's unstated cost assumption. Their failure is a cost verdict, not a signal verdict: two round trips per night at 10 bp is about 20 bp a night, and the protocol was not relaxed for one family.
- For monthly cells a 1-20 session calendar shift usually lands on the previous month-end feature, so the shift placebo tests 'last month's signal' rather than a fine-grained timing jitter. A beat fraction near 1.0 there means the month of the signal does not matter, which is still a real negative result, but it is a coarser control than the daily cells get.
- The 9-sig cell implements the published quarterly signal line and 10% bond floor only; the thread's later discretionary overrides are not modelled.
- Every window here is a bull market. No cell was tested in a bear regime, and the absolute-momentum and canary defences barely fired.

