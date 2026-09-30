# t20260930_13_intraday_periodicity results (numbers copied from results.json)

Generated 2026-09-30T11:42:34Z; pre-backtest gate stamp 2026-09-30T11:01:19Z. Design frozen in hypotheses.md; tiers are mechanical, the verdict belongs to the lead round.

## Decision cells (main window 2024-01-08..2026-09-29)

| cell | mean bp | t | t_nw5 | n | placebo beat | RT1 bp | mean/RT1 | tier |
|---|---|---|---|---|---|---|---|---|
| C_L20_P1500 | 17.13 | 20.95 | 15.68 | 684 | 1.00 | 74.67 | 0.23 | closed |
| O_L20_P1500 | 14.60 | 5.50 | 4.84 | 684 | 1.00 | 77.25 | 0.19 | closed |

Net means (bp per day, annualised Sharpe) in the main window:

| cell | RT1 net | RT2 (2x) net | frozen 10 bp/side | frozen 20 bp/side |
|---|---|---|---|---|
| C_L20_P1500 | -57.54 (-38.87) | -132.21 (-67.22) | -22.87 (-16.97) | -62.87 (-46.66) |
| O_L20_P1500 | -62.65 (-14.25) | -139.91 (-30.76) | -25.40 (-5.81) | -65.40 (-14.96) |

Cost sensitivity (diagnostic, not in the tier): break-even half spread per leg h (equal on both legs) at 1x = (m - 8) / 2 bp and at 2x = (m - 16) / 4 bp; pool-wide mean h of the frozen proxy and long-leg excess over the pool mean:

| cell | break-even h 1x | break-even h 2x | mean h selected long / short | mean h whole valid pool | long minus pool mean bp |
|---|---|---|---|---|---|
| C_L20_P1500 | 4.57 | 0.28 | 34.59 / 32.08 | 24.13 | 13.21 |
| O_L20_P1500 | 3.30 | -0.35 | 35.06 / 34.20 | 24.10 | 2.32 |

## All 12 candidates, gross LS mean (bp), t_nw5, placebo beat, RT1 (main window)

| cell | mean bp | t_nw5 | beat | RT1 bp | long bp | short bp | tier |
|---|---|---|---|---|---|---|---|
| O_L1_P1500 | 10.68 | 3.93 | 1.00 | 77.59 | 0.48 | -10.19 | closed |
| O_L1_P500 | 10.82 | 3.13 | 1.00 | 73.74 | 1.03 | -9.79 | closed |
| O_L5_P1500 | 13.70 | 4.55 | 1.00 | 77.70 | 0.59 | -13.11 | closed |
| O_L5_P500 | 10.69 | 2.76 | 1.00 | 73.77 | -1.19 | -11.89 | closed |
| O_L20_P1500 | 14.60 | 4.84 | 1.00 | 77.25 | 0.92 | -13.68 | closed |
| O_L20_P500 | 11.10 | 2.79 | 1.00 | 73.50 | -1.61 | -12.72 | closed |
| C_L1_P1500 | 10.19 | 11.33 | 1.00 | 75.92 | 8.41 | -1.77 | closed |
| C_L1_P500 | 10.99 | 8.54 | 1.00 | 72.41 | 9.59 | -1.40 | closed |
| C_L5_P1500 | 15.90 | 13.26 | 1.00 | 75.62 | 12.84 | -3.06 | closed |
| C_L5_P500 | 15.50 | 9.84 | 1.00 | 72.13 | 13.49 | -2.01 | closed |
| C_L20_P1500 | 17.13 | 15.68 | 1.00 | 74.67 | 13.99 | -3.15 | closed |
| C_L20_P500 | 17.26 | 11.84 | 1.00 | 71.56 | 14.49 | -2.77 | closed |

## Other windows, decision cells (mean bp, t_nw5, n)

| cell | selection | contaminated 2026 | new holdout |
|---|---|---|---|
| C_L20_P1500 | 14.45, 17.75, 575 | 21.03, 6.20, 178 | 14.04, 2.65, 8 |
| O_L20_P1500 | 13.70, 6.30, 575 | 13.63, 1.44, 178 | 20.20, 1.90, 8 |

## Adjacent-period control (main window, L = 20)

| control | control mean bp | control t_nw5 | same-period minus control bp | diff t_nw5 |
|---|---|---|---|---|
| O_ctrl_P1500 | -2.32 | -0.90 | 16.92 | 3.99 |
| O_ctrl_P500 | 0.97 | 0.27 | 10.13 | 1.79 |
| C_ctrl_P1500 | -3.17 | -3.48 | 20.31 | 13.18 |
| C_ctrl_P500 | -4.87 | -3.67 | 22.13 | 9.50 |

## Closing-segment split (main window, signal S_C_L20)

| pool | r_C mean bp (t_nw5) | r_C1 15:30-15:50 | r_C2 15:50-close |
|---|---|---|---|
| C_L20_P1500 | 17.06 (15.58) | 3.83 (4.23) | 13.23 (24.77) |
| C_L20_P500 | 17.37 (11.89) | 3.86 (3.29) | 13.51 (17.40) |

## By year, gross LS mean bp (t_nw5), decision cells

- C_L20_P1500: 2023 5.77 (6.25, n 90); 2024 13.70 (17.97, n 252); 2025 17.72 (12.52, n 250); 2026 20.73 (6.36, n 186)
- O_L20_P1500: 2023 6.17 (1.60, n 90); 2024 9.23 (4.19, n 252); 2025 20.16 (4.91, n 250); 2026 13.92 (1.53, n 186)

## Data

| year | P1500 pool-days | with minute bars | with r_O | with r_C | DTC missing |
|---|---|---|---|---|---|
| 2023 | 155,981 | 0.924 | 0.909 | 0.911 | 0.222 |
| 2024 | 369,239 | 0.939 | 0.924 | 0.923 | 0.204 |
| 2025 | 366,046 | 0.964 | 0.952 | 0.949 | 0.179 |
| 2026 | 273,517 | 0.989 | 0.984 | 0.987 | 0.156 |

- Consistency exclusions (daily close vs last regular minute bar, |ln ratio| > 0.10): 46 P1500 pool-days (1,262 symbol-days overall).
- Split-like open/prev-close exclusions: 78 pool-days (457 overall).
- 2023 legacy whole-year shards contribute 2,192 symbols (732 only from legacy); month directories 1,574; rows present in both layouts after dedupe: 153,541.
- Hygiene (2023-07..2026-09 window): 16 symbols masked, 3,471 cells.
- Choices not fixed by hypotheses.md: daily open/close re-loaded and sanitized on the 2023-07.. window (not the T-35 full-history run); split-like sessions and consistency exclusions blank all returns of that symbol-day; a day needs >= 40 valid names and legs of >= 5; missing DTC not restricted; spread NaN filled with the day's valid-name median; placebo short leg drawn from the easy-to-borrow names not already long.
