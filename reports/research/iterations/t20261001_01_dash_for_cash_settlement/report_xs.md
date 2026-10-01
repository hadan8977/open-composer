# T-20261001-02 cross-section mechanism measurement (report_xs)

Generated 2026-10-01T04:32:58.140632+00:00 from `results_xs.json`. No verdict.
Months 115 (2017-02-28 .. 2026-08-31), pool median 500, D1 median 50, delisted symbols ever in P500: 219.

## M1 / M2 / M3

| item | series | coef/mean (bp) | t (NW) | n days |
|---|---|---|---|---|
| M1 pre-window minus rest (all) | d1_dv | -7.66 | -0.86 | 2408 |
| M1 pre-window minus rest (pre) | d1_dv | -9.57 | -0.88 | 1823 |
| M1 pre-window minus rest (post) | d1_dv | -1.75 | -0.12 | 585 |
| M1 pre-window minus rest (all) | d1_ew | -4.74 | -0.58 | 2408 |
| M1 pre-window minus rest (pre) | d1_ew | -6.65 | -0.64 | 1823 |
| M1 pre-window minus rest (post) | d1_ew | 1.08 | 0.10 | 585 |
| M1 pre-window minus rest (all) | d10_dv | -2.00 | -0.20 | 2408 |
| M1 pre-window minus rest (pre) | d10_dv | -1.44 | -0.15 | 1823 |
| M1 pre-window minus rest (post) | d10_dv | -2.65 | -0.10 | 585 |
| M1 pre-window minus rest (all) | d1_minus_d10_dv | -5.66 | -0.42 | 2408 |
| M1 pre-window minus rest (pre) | d1_minus_d10_dv | -8.13 | -0.58 | 1823 |
| M1 pre-window minus rest (post) | d1_minus_d10_dv | 0.90 | 0.03 | 585 |
| M1 pass (d1_dv coef<0, t<=-2.0) | d1_dv | False | | |
| M2 post-window mean (all) | d1_dv | 10.86 | 2.02 | 777 |
| M2 post-window mean (pre) | d1_dv | 10.22 | 1.70 | 609 |
| M2 post-window mean (post) | d1_dv | 13.20 | 1.12 | 168 |
| M2 post-window mean (all) | d1_ew | 6.09 | 1.34 | 777 |
| M2 post-window mean (pre) | d1_ew | 6.83 | 1.27 | 609 |
| M2 post-window mean (post) | d1_ew | 3.43 | 0.43 | 168 |
| M2 post-window mean (all) | d10_dv | 8.27 | 1.32 | 777 |
| M2 post-window mean (pre) | d10_dv | 6.48 | 1.05 | 609 |
| M2 post-window mean (post) | d10_dv | 14.75 | 0.81 | 168 |
| M2 post-window mean (all) | d1_minus_d10_dv | 2.59 | 0.32 | 777 |
| M2 post-window mean (pre) | d1_minus_d10_dv | 3.73 | 0.44 | 609 |
| M2 post-window mean (post) | d1_minus_d10_dv | -1.55 | -0.07 | 168 |

| M3 version | theta4 (bp) | theta3 (bp) | theta4-theta3 (bp) | t | pre/post months |
|---|---|---|---|---|---|
| overlap_2024_2025 | 82.99 | -44.79 | 127.78 | 3.00 | 87/19 |
| out_of_paper_2026 | 78.50 | -42.20 | 120.70 | 1.58 | 87/8 |
| combined | 81.66 | -44.03 | 125.68 | 3.05 | 87/27 |

M3 cell means (combined version, bp / months):

- tm4_pre: -37.62 bp, 87 months
- tm4_post: 39.00 bp, 27 months
- tm3_pre: -1.30 bp, 87 months
- tm3_post: -50.36 bp, 27 months

## Long-only trade economics (era b, b+1 open -> tau+4 open, once per month)

| portfolio | window | gross bp | gross t | net10 bp | net20 bp | Sharpe net10 | months |
|---|---|---|---|---|---|---|---|
| d1_dv | stress_2016_2023 | 133.58 | 2.12 | 113.58 | 93.58 | 0.70 | 79 |
| d1_dv | selection | 67.27 | 0.63 | 47.27 | 27.27 | 0.30 | 27 |
| d1_dv | benchmark | 119.17 | 1.18 | 99.17 | 79.17 | 0.60 | 32 |
| d1_dv | contaminated_2026 | 271.24 | 1.19 | 251.24 | 231.24 | 1.35 | 8 |
| d1_dv | all | 129.08 | 2.48 | 109.08 | 89.08 | 0.68 | 115 |
| d1_ew | stress_2016_2023 | 104.82 | 1.86 | 84.82 | 64.82 | 0.59 | 79 |
| d1_ew | selection | 6.66 | 0.08 | -13.34 | -33.34 | -0.11 | 27 |
| d1_ew | benchmark | 54.93 | 0.72 | 34.93 | 14.93 | 0.28 | 32 |
| d1_ew | contaminated_2026 | 216.05 | 1.17 | 196.05 | 176.05 | 1.30 | 8 |
| d1_ew | all | 91.28 | 2.03 | 71.28 | 51.28 | 0.51 | 115 |
| d1_dv_minus_spy | stress_2016_2023 | 72.17 | 1.58 | 32.17 | -7.83 | 0.27 | 79 |
| d1_dv_minus_spy | selection | 54.82 | 0.72 | 14.82 | -25.18 | 0.13 | 27 |
| d1_dv_minus_spy | benchmark | 88.91 | 1.15 | 48.91 | 8.91 | 0.39 | 32 |
| d1_dv_minus_spy | contaminated_2026 | 163.26 | 0.83 | 123.26 | 83.26 | 0.77 | 8 |
| d1_dv_minus_spy | all | 75.87 | 1.99 | 35.87 | -4.13 | 0.30 | 115 |
| d10_dv | stress_2016_2023 | 53.89 | 0.90 | 33.89 | 13.89 | 0.22 | 79 |
| d10_dv | selection | 85.89 | 0.74 | 65.89 | 45.89 | 0.38 | 27 |
| d10_dv | benchmark | 104.03 | 0.75 | 84.03 | 64.03 | 0.37 | 32 |
| d10_dv | contaminated_2026 | 97.36 | 0.24 | 77.36 | 57.36 | 0.23 | 8 |
| d10_dv | all | 71.99 | 1.27 | 51.99 | 31.99 | 0.30 | 115 |
| p500_ew | stress_2016_2023 | 53.15 | 1.56 | 33.15 | 13.15 | 0.38 | 79 |
| p500_ew | selection | 21.22 | 0.36 | 1.22 | -18.78 | 0.01 | 27 |
| p500_ew | benchmark | 29.76 | 0.58 | 9.76 | -10.24 | 0.12 | 32 |
| p500_ew | contaminated_2026 | 59.00 | 0.62 | 39.00 | 19.00 | 0.50 | 8 |
| p500_ew | all | 48.73 | 1.75 | 28.73 | 8.73 | 0.33 | 115 |

Fixed tau-4 b-rule results are in `results_xs.json` under `trade.fix4`.
Caveats: survivor handling drops missing delisted returns (favourable to long losers); formation history starts 2017-01 (calendar starts 2016-01-04).
