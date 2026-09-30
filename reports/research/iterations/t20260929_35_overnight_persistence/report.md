# t20260929_35_overnight_persistence report

Generated 2026-09-30T10:55:37Z from `results.json` (pre-backtest gate stamp 2026-09-30T10:12:19Z). Design frozen in `hypotheses.md`. No conclusion is drawn here; tiers are computed mechanically.

## Decision and pre-specified second cell (main window 2024-01-08 to 2026-09-29)

| cell | mean bp/night | t | t_nw5 | n | placebo beat | t_min | tier | stress mean bp | stress t_nw5 | stress class | auction 2x net bp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ON21_P1500_LS | 2.56 | 0.62 | 0.66 | 683 | 1.00 | 2.0 | closed | 4.81 | 2.98 | recent_only | -13.89 |
| ON5_P1500_LS | -4.62 | -1.11 | -1.02 | 683 | 0.00 | 2.5 | closed | 4.14 | 2.35 | recent_only | -21.07 |

Second cell enabled by rule (decision tier != pass): True.

## All 20 candidates, main window, gross (LS: long minus short decile; LO: top-20 absolute)

| cell | mean bp | t | t_nw5 | Sharpe | n | placebo beat | auction 1x net | auction 2x net | cont 1x net | cont 2x net | frozen 10 net | frozen 20 net | LO excess bp |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ON5_P1500_LS | -4.62 | -1.11 | -1.02 | -0.67 | 683 | 0.00 | -13.07 | -21.07 | -151.02 | -296.97 | -45.07 | -85.07 |  |
| ON5_P1500_LO | 5.21 | 0.75 | 0.75 | 0.45 | 683 | n/a | 1.21 | -2.79 | -111.68 | -228.58 | -14.79 | -34.79 | -1.54 |
| ON5_P500_LS | -7.60 | -1.45 | -1.31 | -0.88 | 683 | 0.00 | -15.80 | -23.80 | -145.24 | -282.67 | -47.80 | -87.80 |  |
| ON5_P500_LO | 8.61 | 1.44 | 1.52 | 0.88 | 683 | n/a | 4.61 | 0.61 | -73.27 | -155.16 | -11.39 | -31.39 | 1.36 |
| ON21_P1500_LS | 2.56 | 0.62 | 0.66 | 0.38 | 683 | 1.00 | -5.89 | -13.89 | -150.36 | -302.82 | -37.89 | -77.89 |  |
| ON21_P1500_LO | -0.84 | -0.11 | -0.12 | -0.07 | 683 | n/a | -4.84 | -8.84 | -161.86 | -322.89 | -20.84 | -40.84 | -7.59 |
| ON21_P500_LS | 2.78 | 0.54 | 0.57 | 0.33 | 683 | 0.97 | -5.43 | -13.43 | -139.57 | -281.71 | -37.43 | -77.43 |  |
| ON21_P500_LO | 6.08 | 0.91 | 1.03 | 0.55 | 683 | n/a | 2.08 | -1.92 | -91.09 | -188.27 | -13.92 | -33.92 | -1.17 |
| ON63_P1500_LS | 3.35 | 0.80 | 0.93 | 0.49 | 683 | 1.00 | -5.11 | -13.11 | -146.98 | -296.86 | -37.11 | -77.11 |  |
| ON63_P1500_LO | 7.38 | 0.94 | 1.08 | 0.57 | 683 | n/a | 3.38 | -0.62 | -155.28 | -317.94 | -12.62 | -32.62 | 0.63 |
| ON63_P500_LS | 4.97 | 0.89 | 1.07 | 0.54 | 683 | 1.00 | -3.23 | -11.23 | -136.95 | -278.67 | -35.23 | -75.23 |  |
| ON63_P500_LO | 13.13 | 1.72 | 2.03 | 1.05 | 683 | n/a | 9.13 | 5.13 | -92.99 | -199.12 | -6.87 | -26.87 | 5.88 |
| ON252_P1500_LS | 11.99 | 2.57 | 3.08 | 1.56 | 683 | 1.00 | 3.53 | -4.47 | -140.70 | -292.92 | -28.47 | -68.47 |  |
| ON252_P1500_LO | 20.20 | 2.30 | 2.49 | 1.40 | 683 | n/a | 16.20 | 12.20 | -141.32 | -302.84 | 0.20 | -19.80 | 13.50 |
| ON252_P500_LS | 17.01 | 2.64 | 3.24 | 1.60 | 683 | 1.00 | 8.81 | 0.81 | -128.16 | -273.13 | -23.19 | -63.19 |  |
| ON252_P500_LO | 25.25 | 2.88 | 3.32 | 1.75 | 683 | n/a | 21.25 | 17.25 | -91.42 | -208.09 | 5.25 | -14.75 | 18.12 |
| TOW21_P1500_LS | 5.40 | 1.62 | 1.93 | 0.98 | 683 | 1.00 | -3.07 | -11.07 | -147.93 | -300.78 | -35.07 | -75.07 |  |
| TOW21_P1500_LO | 8.85 | 1.26 | 1.38 | 0.77 | 683 | n/a | 4.85 | 0.85 | -136.67 | -282.19 | -11.15 | -31.15 | 2.10 |
| TOW21_P500_LS | 3.29 | 0.75 | 0.86 | 0.45 | 683 | 0.98 | -4.92 | -12.92 | -139.74 | -282.57 | -36.92 | -76.92 |  |
| TOW21_P500_LO | 10.80 | 1.72 | 1.94 | 1.04 | 683 | n/a | 6.80 | 2.80 | -81.20 | -173.19 | -9.20 | -29.20 | 3.54 |

## Windows for the decision and second cells (gross mean bp / t_nw5 / n)

| cell | main | selection | stress | contaminated | new_holdout |
|---|---|---|---|---|---|
| ON21_P1500_LS | 2.56 / 0.66 / 683 | 3.30 / 0.91 / 575 | 4.81 / 2.98 / 1847 | 1.18 / 0.12 / 178 | -22.39 / -2.22 / 7 |
| ON5_P1500_LS | -4.62 / -1.02 / 683 | 0.49 / 0.12 / 575 | 4.14 / 2.35 / 1847 | -15.53 / -1.36 / 178 | -59.35 / -2.84 / 7 |

## Diagnostics (not in the decision), main window

- ON21_P1500_LS (a) next-day intraday of same LS: -13.70 bp, t_nw5 -3.17, n 683
- ON21_P1500_LS (c) Friday nights 8.29 bp (n 136), other nights 1.13 bp (n 547)
- ON21_P1500_LS (d) long minus pool 3.34 bp, short minus pool 0.78 bp
- ON21_P1500_LS (e) ETB-proxy short leg LS gross 2.68 bp, t_nw5 0.68, n 683
- ON5_P1500_LS (a) next-day intraday of same LS: -4.91 bp, t_nw5 -1.08, n 683
- ON5_P1500_LS (c) Friday nights 9.79 bp (n 136), other nights -8.20 bp (n 547)
- ON5_P1500_LS (d) long minus pool 0.25 bp, short minus pool 4.87 bp
- ON5_P1500_LS (e) ETB-proxy short leg LS gross -6.05 bp, t_nw5 -1.33, n 683
- (b) P1500 LS on past-21d intraday, next overnight: -3.84 bp, t_nw5 -1.18, n 683
- (b) P500 LS on past-21d intraday, next overnight: 0.06 bp, t_nw5 0.01, n 683
- (f) SPY close to next open: 5.91 bp, t_nw5 2.50, n 683
- survivorship ON21_P1500_LS_survivors_only: main 2.66 bp, t_nw5 0.68
- survivorship ON5_P1500_LS_survivors_only: main -4.58 bp, t_nw5 -1.01

## Data

- symbols_total: 4443; symbols_in_p1500_survivors_only: 3429; delisted_symbols_in_p1500: 1296; delisted_share_in_pool: 0.1414; fund_excluded: 6408; otc_excluded: 306; missing_metadata: 917; split_filtered_rows: 2061

Conventions and known biases: see the module docstring of `scripts/run_t20260929_35_overnight_persistence.py` and `hypotheses.md` (opening-price basis, earnings nights, survivorship).

## Gross mean bp/night by calendar year (t_nw5 in brackets)

| cell | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ON5_P1500_LS | -3.5 (-0.8) | 6.4 (3.3) | 1.3 (0.6) | 4.3 (1.8) | 5.9 (0.7) | 9.4 (1.8) | 5.1 (1.0) | 1.7 (0.6) | -2.9 (-0.7) | 3.5 (0.4) | -17.2 (-1.5) |
| ON5_P1500_LO | 10.9 (1.5) | 13.2 (3.5) | 6.5 (1.6) | 4.1 (0.8) | 33.2 (2.2) | 24.2 (1.6) | -12.2 (-1.5) | 5.9 (0.9) | 8.0 (0.9) | 8.5 (0.6) | -4.9 (-0.4) |
| ON5_P500_LS | -11.1 (-2.5) | 2.6 (1.0) | -4.0 (-1.4) | 0.5 (0.2) | 5.1 (0.5) | 7.2 (1.1) | 3.3 (0.5) | 0.5 (0.1) | -3.2 (-0.5) | 0.1 (0.0) | -23.3 (-1.7) |
| ON5_P500_LO | -0.3 (-0.0) | 7.3 (2.3) | 1.0 (0.3) | 4.1 (0.8) | 26.9 (1.8) | 21.6 (1.7) | -6.5 (-0.8) | 5.3 (0.9) | 11.5 (1.5) | 14.9 (1.5) | -5.8 (-0.5) |
| ON21_P1500_LS | -2.6 (-1.1) | 4.6 (2.8) | 1.3 (0.9) | 1.0 (0.5) | 14.0 (1.8) | 13.4 (2.3) | 2.6 (0.5) | 0.8 (0.2) | 0.3 (0.1) | 6.1 (0.9) | 0.3 (0.0) |
| ON21_P1500_LO | 14.9 (3.0) | 18.7 (3.1) | 6.2 (1.4) | 6.0 (1.2) | 46.8 (3.4) | 24.2 (1.7) | -14.4 (-1.8) | 3.0 (0.4) | 10.4 (1.1) | -1.9 (-0.1) | -16.8 (-1.4) |
| ON21_P500_LS | -6.4 (-2.3) | 2.3 (1.1) | -3.2 (-1.4) | -1.4 (-0.6) | 18.5 (1.9) | 15.2 (2.0) | -0.3 (-0.1) | 0.6 (0.1) | 0.4 (0.1) | 2.8 (0.3) | 4.8 (0.4) |
| ON21_P500_LO | 3.4 (0.9) | 11.9 (3.3) | -1.1 (-0.3) | 4.5 (1.0) | 34.4 (2.6) | 29.3 (1.8) | -7.3 (-1.0) | 4.8 (0.8) | 6.8 (0.7) | 3.3 (0.3) | 6.6 (0.6) |
| ON63_P1500_LS | 6.3 (2.6) | 8.1 (6.0) | 1.3 (0.8) | 2.1 (1.2) | 11.1 (1.9) | 17.0 (2.4) | 7.3 (1.4) | -1.4 (-0.5) | 4.8 (1.4) | 4.5 (0.7) | -0.4 (-0.0) |
| ON63_P1500_LO | 20.4 (3.9) | 22.8 (5.0) | 5.7 (1.1) | 11.9 (2.4) | 44.7 (3.6) | 32.1 (2.1) | -15.6 (-2.2) | -4.0 (-0.6) | 19.9 (2.0) | 4.9 (0.4) | -8.4 (-0.7) |
| ON63_P500_LS | -0.2 (-0.1) | 8.4 (4.0) | -1.5 (-0.7) | 0.7 (0.3) | 15.9 (2.0) | 19.8 (2.0) | 3.3 (0.5) | -2.5 (-0.6) | 6.6 (1.4) | 3.6 (0.4) | 3.9 (0.3) |
| ON63_P500_LO | 5.8 (1.6) | 15.2 (4.9) | -1.3 (-0.3) | 5.9 (1.2) | 37.0 (2.9) | 35.8 (2.1) | -8.6 (-1.5) | 1.7 (0.3) | 13.7 (1.7) | 12.0 (1.0) | 11.5 (0.9) |
| ON252_P1500_LS | 12.0 (2.9) | 8.8 (4.9) | 5.9 (3.7) | 2.0 (1.2) | 11.5 (2.9) | 15.8 (2.1) | 11.9 (2.2) | 1.7 (0.7) | 10.2 (3.2) | 9.0 (1.3) | 18.5 (1.8) |
| ON252_P1500_LO | 37.7 (2.8) | 19.1 (3.8) | 11.0 (2.0) | 7.7 (1.5) | 34.9 (3.3) | 31.1 (2.0) | -14.2 (-2.0) | -5.7 (-0.8) | 29.6 (2.8) | 18.0 (1.1) | 8.3 (0.6) |
| ON252_P500_LS | 0.9 (0.2) | 9.5 (3.7) | 2.0 (0.7) | 2.0 (0.8) | 15.0 (2.5) | 18.4 (1.7) | 9.0 (1.3) | -0.3 (-0.1) | 12.6 (2.8) | 11.9 (1.4) | 29.7 (2.2) |
| ON252_P500_LO | 14.9 (2.4) | 13.7 (4.6) | 6.0 (1.1) | 8.0 (1.6) | 36.1 (3.0) | 22.4 (1.4) | -6.5 (-1.0) | 4.5 (0.7) | 27.6 (2.9) | 18.8 (1.2) | 28.0 (1.9) |
| TOW21_P1500_LS | 4.5 (2.0) | 3.9 (2.7) | 2.4 (1.2) | 5.3 (3.0) | 14.1 (1.6) | 9.7 (2.1) | 10.4 (2.4) | 6.1 (2.3) | 3.7 (1.5) | 0.8 (0.2) | 14.4 (2.0) |
| TOW21_P1500_LO | 18.9 (3.7) | 23.5 (4.3) | 1.7 (0.3) | 12.5 (2.3) | 55.1 (3.1) | 28.9 (2.4) | -8.6 (-0.9) | 9.5 (1.1) | 23.2 (2.5) | 1.5 (0.1) | -2.1 (-0.2) |
| TOW21_P500_LS | -0.9 (-0.4) | 3.5 (1.7) | 2.0 (0.7) | 4.9 (1.9) | 14.0 (1.3) | 7.2 (1.1) | 5.6 (1.0) | 7.8 (2.2) | -0.9 (-0.2) | 0.3 (0.1) | 14.1 (1.4) |
| TOW21_P500_LO | 5.6 (1.6) | 13.3 (3.5) | 2.2 (0.5) | 9.1 (1.8) | 34.5 (1.9) | 17.5 (1.4) | -7.2 (-0.9) | 10.3 (1.7) | 9.1 (1.3) | 5.0 (0.5) | 19.4 (1.7) |

## Long-only counterpart of the decision cell (ON21_P1500_LO, main window)

- absolute nightly mean -0.84 bp (t_nw5 -0.12), excess over pool equal weight -7.59 bp (t_nw5 -1.26), pool equal-weight night 6.75 bp.

## Conventions, caveats and what this file does not say

- Tier and stress class are the mechanical output of `tier_from_stats` and `stress_class_from_stats` (thresholds from hypotheses.md); the verdict is for the lead round. The second cell `enabled_by_rule` flag only records that the decision tier is not `pass`.
- Placebo beat = fraction of 100 same-pool random long/short books (seeds 0..99, same k per night) whose window mean is below the real mean. The random books are market neutral by construction and have a much smaller nightly variance than the real decile book, so the beat fraction can be 1.00 for a small mean.
- Costs: LS auction cost is 4 sides x 2 bp per night (1x) and 4 x 4 bp (2x); the borrow term (T-32 tiers, calendar days / 360, Friday nights 3 days) is deducted in every net column. The AR spread in the continuous columns is the repo estimator (median 38 bp over the P1500 main window, 61 bp in the top ON21 decile), which is known to overstate liquid-stock spreads; those columns are for the paper-account approximation only.
- Not measured: official opening/closing auction prices (daily-bar open vs official open tail in high-overnight-volatility names), earnings nights (kept, diagnostic only), fill reliability of `cls` and `opg` on the paper account. Nights whose next-session open is missing (delisting or halt) have no return and are dropped, which is a residual survivorship bias.
- Pool rank is taken on dv21 first and the $5 / 63-session filters are applied afterwards, so a night's pool can hold fewer than 1500 names (mean 1467). Decile leg size is floor(0.10 x valid names). Diagnostic (b) sorts on mean(ID_{t-21..t-1}).

