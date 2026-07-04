# PDR Router Fold Attribution (state / asset)

- Strategy: `nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive`
- Route: `defensive_overlay:transition_TQQQ_replacement_mom_positive_lb20_min0_delay30_base[pdr:semi_light_harddd6_v0.65_breadth1_softQQQ_defGLD_rec104_mom60max20_ext35_cool5QLD_confirm5_melt6040x25_detdd8m10]`
- Source artifact: `reports/research/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive-long-window-fixed-route.json`
- Router implementation: `orphaned_bytecode_sourceless_load`
- Warmup lookback days: `252`

## Caveats

- router source exists only as orphaned bytecode; committed source cannot parse this route label (hybrid_params_from_label raises ValueError)
- adjusted daily research cache is research_cross_check evidence, not broker execution evidence
- this artifact attributes an existing fixed route; it does not discover or select parameters

## Parity check (recorded loop vs router engine vs prior artifact)

| window | recorded % | engine % | artifact % | TQQQ % |
| --- | --- | --- | --- | --- |
| full | 5643.76 | 5643.76 | 4334.28 | - |
| fold 1 | 91.36 | 91.36 | 92.04 | 274.98 |
| fold 2 | 36.13 | 36.18 | 16.3 | 92.18 |
| fold 3 | -13.5 | -13.53 | -8.51 | 95.88 |
| fold 4 | 214.92 | 214.81 | 205.72 | 373.62 |
| fold 5 | 136.93 | 136.85 | 117.76 | -25.51 |
| fold 6 | 241.63 | 241.75 | 225.85 | 162.35 |

## Fold 1: 2013-01-08 -> 2015-03-31

- Recorded compound: `91.36%` vs TQQQ `272.42%` (artifact: `92.04%` vs `274.98%`)
- State transitions: `147`

| state | days | share % | net sum % | isolated % | TQQQ sum % | gap % | assets (days) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| risk_on_ranked | 198 | 35.36 | 18.0 | 14.86 | 14.72 | 3.29 | TQQQ:134, USD:63, QLD:1 |
| confirmation_transition_overlay_TQQQ | 83 | 14.82 | 12.67 | 11.0 | 14.38 | -1.71 | TQQQ:83 |
| post_drawdown_reentry | 78 | 13.93 | 34.57 | 39.31 | 35.06 | -0.49 | TQQQ:78 |
| confirmation_transition | 75 | 13.39 | -2.97 | -4.44 | -2.32 | -0.65 | QLD:75 |
| early_deterioration_downshift | 33 | 5.89 | -1.46 | -1.71 | 0.47 | -1.94 | QQQ:33 |
| hard_stress_defensive | 31 | 5.54 | -2.02 | -2.15 | 57.56 | -59.58 | GLD:31 |
| cooldown_transition | 28 | 5.0 | 3.1 | 2.34 | 5.62 | -2.52 | QLD:28 |
| soft_stress | 24 | 4.29 | 4.63 | 4.7 | 15.21 | -10.58 | QQQ:24 |
| cooldown_transition_overlay_TQQQ | 10 | 1.79 | 9.22 | 9.39 | 9.43 | -0.21 | TQQQ:10 |

| asset | days | contribution sum % |
| --- | --- | --- |
| TQQQ | 305 | 69.07 |
| USD | 63 | 8.62 |
| QQQ | 57 | 5.2 |
| QLD | 104 | 2.88 |
| GLD | 31 | -1.25 |

## Fold 2: 2015-04-01 -> 2017-06-27

- Recorded compound: `36.13%` vs TQQQ `94.79%` (artifact: `16.3%` vs `92.18%`)
- State transitions: `141`

| state | days | share % | net sum % | isolated % | TQQQ sum % | gap % | assets (days) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| risk_on_ranked | 155 | 27.83 | 2.21 | -1.37 | 17.1 | -14.89 | TQQQ:79, USD:72, QLD:4 |
| hard_stress_defensive | 107 | 19.21 | 6.64 | 6.27 | 35.27 | -28.62 | GLD:107 |
| confirmation_transition_overlay_TQQQ | 87 | 15.62 | -11.58 | -12.84 | -9.9 | -1.68 | TQQQ:87 |
| confirmation_transition | 67 | 12.03 | 9.1 | 7.85 | 15.77 | -6.67 | QLD:67 |
| post_drawdown_reentry | 58 | 10.41 | -3.81 | -5.03 | -3.32 | -0.49 | TQQQ:58 |
| cooldown_transition_overlay_TQQQ | 29 | 5.21 | 36.01 | 41.75 | 36.71 | -0.7 | TQQQ:29 |
| early_deterioration_downshift | 27 | 4.85 | 0.9 | 0.76 | 6.27 | -5.37 | QQQ:27 |
| cooldown_transition | 17 | 3.05 | 6.53 | 6.28 | 9.84 | -3.3 | QLD:17 |
| soft_stress | 10 | 1.8 | -4.17 | -4.16 | -11.54 | 7.37 | QQQ:10 |

| asset | days | contribution sum % |
| --- | --- | --- |
| TQQQ | 253 | 28.91 |
| QLD | 88 | 12.22 |
| GLD | 107 | 7.69 |
| USD | 72 | 3.84 |
| QQQ | 37 | -1.73 |

## Fold 3: 2017-06-28 -> 2019-09-17

- Recorded compound: `-13.5%` vs TQQQ `94.78%` (artifact: `-8.51%` vs `95.88%`)
- State transitions: `139`

| state | days | share % | net sum % | isolated % | TQQQ sum % | gap % | assets (days) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hard_stress_defensive | 149 | 26.75 | 16.45 | 17.56 | 94.36 | -77.91 | GLD:149 |
| risk_on_ranked | 119 | 21.36 | -32.5 | -30.94 | -8.87 | -23.63 | TQQQ:60, USD:58, QLD:1 |
| confirmation_transition_overlay_TQQQ | 80 | 14.36 | 1.85 | -1.66 | 2.9 | -1.05 | TQQQ:80 |
| post_drawdown_reentry | 66 | 11.85 | 8.28 | 7.21 | 8.7 | -0.42 | TQQQ:66 |
| confirmation_transition | 37 | 6.64 | 7.65 | 7.26 | 13.18 | -5.53 | QLD:37 |
| soft_stress | 31 | 5.57 | -2.31 | -2.37 | -5.25 | 2.94 | QQQ:31 |
| cooldown_transition_overlay_TQQQ | 28 | 5.03 | 4.65 | 3.69 | 5.49 | -0.84 | TQQQ:28 |
| cooldown_transition | 26 | 4.67 | -3.06 | -3.71 | -3.36 | 0.3 | QLD:26 |
| early_deterioration_downshift | 19 | 3.41 | -1.36 | -1.59 | -2.47 | 1.11 | QQQ:19 |
| selected_asset_blocked | 2 | 0.36 | -1.77 | -1.78 | -2.62 | 0.84 | QLD:2 |

| asset | days | contribution sum % |
| --- | --- | --- |
| GLD | 149 | 17.71 |
| QLD | 66 | 7.82 |
| QQQ | 50 | -2.2 |
| TQQQ | 234 | -7.72 |
| USD | 58 | -9.33 |

## Fold 4: 2019-09-18 -> 2021-12-06

- Recorded compound: `214.92%` vs TQQQ `398.82%` (artifact: `205.72%` vs `373.62%`)
- State transitions: `148`

| state | days | share % | net sum % | isolated % | TQQQ sum % | gap % | assets (days) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| risk_on_ranked | 203 | 36.45 | 56.61 | 60.36 | 65.76 | -9.15 | TQQQ:100, USD:85, QLD:16, SOXL:2 |
| hard_stress_defensive | 133 | 23.88 | 5.67 | 4.47 | 93.77 | -88.1 | GLD:133 |
| post_drawdown_reentry | 49 | 8.8 | 41.04 | 48.67 | 41.88 | -0.84 | TQQQ:49 |
| confirmation_transition_overlay_TQQQ | 44 | 7.9 | 40.51 | 47.0 | 41.28 | -0.77 | TQQQ:44 |
| cooldown_transition_overlay_TQQQ | 35 | 6.28 | 21.11 | 19.18 | 21.81 | -0.7 | TQQQ:35 |
| soft_stress | 25 | 4.49 | 0.88 | 0.63 | 4.02 | -3.14 | QQQ:25 |
| cooldown_transition | 19 | 3.41 | -1.24 | -1.52 | -0.97 | -0.28 | QLD:19 |
| early_deterioration_downshift | 18 | 3.23 | -2.87 | -2.99 | -6.42 | 3.55 | QQQ:18 |
| melt_up_peak_guard | 12 | 2.15 | 1.82 | 1.08 | 3.43 | -1.61 | QLD:12 |
| confirmation_transition | 11 | 1.97 | 1.4 | 0.94 | 2.71 | -1.31 | QLD:11 |
| selected_asset_blocked | 8 | 1.44 | -29.72 | -26.42 | -44.54 | 14.82 | QLD:8 |

| asset | days | contribution sum % |
| --- | --- | --- |
| TQQQ | 228 | 131.71 |
| USD | 85 | 34.79 |
| GLD | 133 | 7.14 |
| QQQ | 43 | -0.59 |
| SOXL | 2 | -4.09 |
| QLD | 66 | -24.23 |

## Fold 5: 2021-12-07 -> 2024-02-28

- Recorded compound: `136.93%` vs TQQQ `-24.05%` (artifact: `117.76%` vs `-25.51%`)
- State transitions: `83`

| state | days | share % | net sum % | isolated % | TQQQ sum % | gap % | assets (days) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hard_stress_defensive | 306 | 55.14 | 13.48 | 13.08 | -10.59 | 24.07 | GLD:306 |
| risk_on_ranked | 111 | 20.0 | 83.77 | 109.2 | 54.63 | 29.14 | USD:94, TQQQ:16, QLD:1 |
| confirmation_transition_overlay_TQQQ | 42 | 7.57 | 8.6 | 7.61 | 9.16 | -0.56 | TQQQ:42 |
| cooldown_transition_overlay_TQQQ | 27 | 4.86 | -0.05 | -2.12 | 0.65 | -0.7 | TQQQ:27 |
| post_drawdown_reentry | 15 | 2.7 | 10.23 | 10.31 | 10.23 | 0.0 | TQQQ:15 |
| cooldown_transition | 14 | 2.52 | 0.74 | 0.1 | 2.33 | -1.59 | QLD:14 |
| early_deterioration_downshift | 14 | 2.52 | -2.0 | -2.23 | -3.79 | 1.79 | QQQ:14 |
| selected_asset_blocked | 12 | 2.16 | -6.8 | -6.9 | -9.61 | 2.81 | QLD:12 |
| confirmation_transition | 10 | 1.8 | 0.84 | 0.68 | 1.18 | -0.33 | QLD:10 |
| soft_stress | 3 | 0.54 | -4.26 | -4.23 | -12.57 | 8.31 | QQQ:3 |
| melt_up_peak_guard | 1 | 0.18 | -1.87 | -1.87 | -2.84 | 0.96 | QLD:1 |

| asset | days | contribution sum % |
| --- | --- | --- |
| USD | 94 | 89.94 |
| TQQQ | 100 | 14.58 |
| GLD | 306 | 14.53 |
| QQQ | 17 | -5.49 |
| QLD | 38 | -5.72 |

## Fold 6: 2024-02-29 -> 2026-05-21

- Recorded compound: `241.63%` vs TQQQ `156.3%` (artifact: `225.85%` vs `162.35%`)
- State transitions: `151`

| state | days | share % | net sum % | isolated % | TQQQ sum % | gap % | assets (days) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hard_stress_defensive | 137 | 24.64 | 33.71 | 38.23 | 56.38 | -22.68 | GLD:137 |
| risk_on_ranked | 120 | 21.58 | 75.9 | 98.86 | 26.43 | 49.47 | USD:99, TQQQ:15, QQQ:5, QLD:1 |
| confirmation_transition_overlay_TQQQ | 93 | 16.73 | 24.61 | 21.48 | 26.43 | -1.82 | TQQQ:93 |
| post_drawdown_reentry | 50 | 8.99 | -10.83 | -11.98 | -10.27 | -0.56 | TQQQ:50 |
| confirmation_transition | 36 | 6.47 | 10.81 | 10.76 | 17.91 | -7.1 | QLD:36 |
| early_deterioration_downshift | 27 | 4.86 | 3.89 | 3.78 | 14.11 | -10.21 | QQQ:27 |
| cooldown_transition_overlay_TQQQ | 27 | 4.86 | -10.73 | -12.17 | -10.1 | -0.63 | TQQQ:27 |
| selected_asset_blocked | 25 | 4.5 | 12.03 | 12.44 | 18.12 | -6.08 | QLD:25 |
| cooldown_transition | 24 | 4.32 | 6.06 | 5.87 | 9.67 | -3.61 | QLD:24 |
| soft_stress | 17 | 3.06 | -3.27 | -3.29 | -9.11 | 5.84 | QQQ:17 |

| asset | days | contribution sum % |
| --- | --- | --- |
| USD | 99 | 68.66 |
| GLD | 137 | 34.83 |
| QLD | 86 | 34.05 |
| TQQQ | 185 | 13.77 |
| QQQ | 49 | 0.69 |

## Full window

- Recorded compound: `5643.76%` vs TQQQ `13619.96%`
- State transitions: `811`

| state | days | share % | net sum % | isolated % | TQQQ sum % | gap % |
| --- | --- | --- | --- | --- | --- | --- |
| risk_on_ranked | 906 | 27.11 | 203.99 | 421.96 | 169.76 | 34.23 |
| hard_stress_defensive | 863 | 25.82 | 73.93 | 99.62 | 326.75 | -252.82 |
| confirmation_transition_overlay_TQQQ | 429 | 12.84 | 76.65 | 82.82 | 84.25 | -7.6 |
| post_drawdown_reentry | 316 | 9.46 | 79.48 | 104.77 | 82.28 | -2.8 |
| confirmation_transition | 236 | 7.06 | 26.84 | 24.44 | 48.43 | -21.59 |
| cooldown_transition_overlay_TQQQ | 156 | 4.67 | 60.21 | 64.73 | 63.99 | -3.78 |
| early_deterioration_downshift | 138 | 4.13 | -2.91 | -4.07 | 8.16 | -11.08 |
| cooldown_transition | 128 | 3.83 | 12.13 | 9.3 | 23.13 | -11.0 |
| soft_stress | 110 | 3.29 | -8.49 | -8.7 | -19.24 | 10.75 |
| selected_asset_blocked | 47 | 1.41 | -26.26 | -24.35 | -38.66 | 12.4 |
| melt_up_peak_guard | 13 | 0.39 | -0.05 | -0.82 | 0.6 | -0.65 |
