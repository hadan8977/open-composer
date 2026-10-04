# t20261004_book_v13_tc: cost-aware trading rules on the v1.2 primary book (M0_U3000)

Mechanical output of `scripts/book_v13_trading_rules.py`; contract `hypotheses.md` unchanged (sha256 in results.json). No verdict is stated here; the main review decides.

- identity: pass=True, max abs diff 0.0
- mechanical_status: **no_rule_eligible_keep_v12**, selected_rule: None
- Stage 2 not run (no rule met E1-E4).


## Window recent (2024-01-08..2026-09-15)

| rule | net SR (offset med) | gross SR | net SR blend | cost bp/yr | one-sided turnover/yr | mean gross exp | OLS beta | Dimson beta | 2x-cost net SR | delta vs B0 | offsets improved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | 1.485 | 1.721 | 1.506 | 221.4 | 15.89 | 1.838 | 0.026 | 0.052 | 1.269 | n/a | - |
| P2 | 1.597 | 1.752 | 1.618 | 136.6 | 9.82 | 1.752 | 0.031 | 0.063 | 1.462 | 0.112 | 5 |
| P3 | 1.638 | 1.768 | 1.643 | 106.0 | 7.57 | 1.695 | 0.030 | 0.065 | 1.530 | 0.154 | 5 |
| P2V | 1.522 | 1.705 | 1.564 | 160.2 | 11.57 | 1.757 | 0.020 | 0.046 | 1.360 | 0.038 | 5 |
| N25 | 1.557 | 1.700 | 1.613 | 126.8 | 8.33 | 1.709 | 0.029 | 0.056 | 1.435 | 0.073 | 5 |
| N50 | 1.642 | 1.744 | 1.659 | 80.1 | 4.84 | 1.563 | 0.031 | 0.060 | 1.561 | 0.158 | 5 |

## Window stress (2017-10-02..2023-08-31)

| rule | net SR (offset med) | gross SR | net SR blend | cost bp/yr | one-sided turnover/yr | mean gross exp | OLS beta | Dimson beta | 2x-cost net SR | delta vs B0 | offsets improved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | 0.598 | 0.775 | 0.597 | 151.8 | 12.90 | 1.592 | 0.029 | 0.024 | 0.441 | n/a | - |
| P2 | 0.634 | 0.755 | 0.647 | 92.1 | 7.86 | 1.521 | 0.032 | 0.026 | 0.533 | 0.036 | 5 |
| P3 | 0.654 | 0.755 | 0.656 | 71.4 | 6.04 | 1.470 | 0.033 | 0.028 | 0.573 | 0.056 | 5 |
| P2V | 0.668 | 0.805 | 0.656 | 110.3 | 9.40 | 1.524 | 0.027 | 0.024 | 0.545 | 0.071 | 5 |
| N25 | 0.681 | 0.790 | 0.677 | 83.6 | 6.47 | 1.490 | 0.029 | 0.024 | 0.592 | 0.083 | 5 |
| N50 | 0.722 | 0.798 | 0.714 | 51.7 | 3.67 | 1.352 | 0.030 | 0.024 | 0.665 | 0.124 | 5 |

## Window full (2017-10-02..2026-09-15)

| rule | net SR (offset med) | gross SR | net SR blend | cost bp/yr | one-sided turnover/yr | mean gross exp | OLS beta | Dimson beta | 2x-cost net SR | delta vs B0 | offsets improved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | 0.911 | 1.107 | 0.921 | 173.6 | 13.89 | 1.680 | 0.026 | 0.023 | 0.736 | n/a | - |
| P2 | 0.979 | 1.111 | 0.991 | 106.3 | 8.52 | 1.604 | 0.029 | 0.028 | 0.868 | 0.068 | 5 |
| P3 | 0.999 | 1.109 | 1.005 | 82.5 | 6.56 | 1.551 | 0.030 | 0.030 | 0.910 | 0.088 | 5 |
| P2V | 0.970 | 1.119 | 0.978 | 125.6 | 10.09 | 1.607 | 0.024 | 0.022 | 0.841 | 0.059 | 5 |
| N25 | 1.002 | 1.122 | 1.010 | 97.2 | 7.08 | 1.569 | 0.027 | 0.024 | 0.902 | 0.090 | 5 |
| N50 | 1.044 | 1.129 | 1.046 | 60.7 | 4.06 | 1.429 | 0.027 | 0.025 | 0.978 | 0.133 | 5 |

## Window A (2024-01-08..2026-06-30)

| rule | net SR (offset med) | gross SR | net SR blend | cost bp/yr | one-sided turnover/yr | mean gross exp | OLS beta | Dimson beta | 2x-cost net SR | delta vs B0 | offsets improved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | 1.408 | 1.655 | 1.445 | 219.8 | 15.95 | 1.826 | 0.037 | 0.048 | 1.183 | n/a | - |
| P2 | 1.532 | 1.695 | 1.571 | 134.7 | 9.80 | 1.741 | 0.042 | 0.061 | 1.390 | 0.124 | 5 |
| P3 | 1.566 | 1.698 | 1.599 | 104.4 | 7.55 | 1.683 | 0.041 | 0.063 | 1.455 | 0.158 | 5 |
| P2V | 1.468 | 1.660 | 1.514 | 159.7 | 11.66 | 1.745 | 0.031 | 0.043 | 1.298 | 0.060 | 5 |
| N25 | 1.479 | 1.632 | 1.549 | 126.1 | 8.36 | 1.696 | 0.040 | 0.053 | 1.347 | 0.071 | 5 |
| N50 | 1.562 | 1.666 | 1.600 | 79.7 | 4.85 | 1.552 | 0.041 | 0.058 | 1.478 | 0.154 | 5 |

## Window B (2026-07-01..2026-09-15)

| rule | net SR (offset med) | gross SR | net SR blend | cost bp/yr | one-sided turnover/yr | mean gross exp | OLS beta | Dimson beta | 2x-cost net SR | delta vs B0 | offsets improved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | 2.064 | 2.244 | 2.080 | 239.6 | 15.17 | 1.981 | -0.238 | 0.159 | 1.900 | n/a | - |
| P2 | 2.019 | 2.151 | 2.087 | 158.8 | 10.01 | 1.890 | -0.234 | 0.140 | 1.905 | -0.045 | 2 |
| P3 | 2.022 | 2.134 | 2.080 | 125.1 | 7.81 | 1.829 | -0.219 | 0.130 | 1.929 | -0.042 | 2 |
| P2V | 2.047 | 2.175 | 2.051 | 165.8 | 10.45 | 1.893 | -0.234 | 0.138 | 1.933 | -0.018 | 1 |
| N25 | 2.141 | 2.254 | 2.213 | 134.7 | 7.95 | 1.865 | -0.224 | 0.150 | 2.044 | 0.076 | 4 |
| N50 | 2.158 | 2.239 | 2.226 | 84.3 | 4.67 | 1.701 | -0.196 | 0.131 | 2.094 | 0.094 | 4 |

## Newey-West t (lag 5) of the blended daily net difference vs B0

| rule | full | recent | stress | A | B |
|---|---|---|---|---|---|
| P2 | 1.02 | 0.82 | 0.60 | 1.01 | -0.58 |
| P3 | 0.48 | 0.40 | 0.28 | 0.66 | -0.78 |
| P2V | 1.07 | 0.18 | 1.17 | 0.44 | -0.77 |
| N25 | 2.94 | 1.57 | 2.28 | 1.59 | 0.20 |
| N50 | 1.76 | 0.82 | 1.49 | 1.04 | -0.41 |

## Eligibility (hypotheses.md section 5)

| rule | E1 +0.10 both windows | E2 >=4/5 offsets both windows | E3 NW t full >= 2 | E4 |beta| <= 0.15 | all |
|---|---|---|---|---|---|
| P2 | False | True | False | True | False |
| P3 | False | True | False | True | False |
| P2V | False | True | False | True | False |
| N25 | False | True | True | True | False |
| N50 | True | True | False | True | False |

## D1 turnover sources of B0 (return-free)

| window | flips/tranche-yr | turnover share on flip refreshes | cost share on flip refreshes | mean turnover flip / other refresh | drift /yr | target change /yr | turnover /yr |
|---|---|---|---|---|---|---|---|
| recent | 7.48 | 0.259 | 0.257 | 1.10 / 0.55 | 4.23 | 31.02 | 31.78 |
| stress | 6.44 | 0.257 | 0.261 | 1.04 / 0.44 | 3.45 | 25.18 | 26.04 |

## D2 median weekly rank autocorrelation (offset-0 decision dates, in_u3000)

| series | recent | weeks | stress | weeks |
|---|---|---|---|---|
| value | 0.991 | 134 | 0.985 | 297 |
| quality | 0.994 | 134 | 0.993 | 297 |
| investment | 0.996 | 134 | 0.995 | 297 |
| momentum | 0.971 | 134 | 0.974 | 297 |
| low_risk | 0.994 | 134 | 0.994 | 297 |
| earnings | 0.991 | 134 | 0.989 | 297 |
| insider | 0.933 | 134 | 0.950 | 297 |
| short_info | 0.964 | 134 | 0.955 | 283 |
| seasonality | 1.000 | 134 | 1.000 | 230 |
| M0_composite | 0.983 | 134 | 0.983 | 297 |

## D3 2x-cost frontier (offset-median net Sharpe at 1x / 2x cost)

| rule | recent 1x | recent 2x | stress 1x | stress 2x |
|---|---|---|---|---|
| B0 | 1.485 | 1.269 | 0.598 | 0.441 |
| P2 | 1.597 | 1.462 | 0.634 | 0.533 |
| P3 | 1.638 | 1.530 | 0.654 | 0.573 |
| P2V | 1.522 | 1.360 | 0.668 | 0.545 |
| N25 | 1.557 | 1.435 | 0.681 | 0.592 |
| N50 | 1.642 | 1.561 | 0.722 | 0.665 |

## Implementation choices

- Contract windows (recent 2024-01-08..2026-09-15, stress 2017-10-02..2023-08-31, full 2017-10-02..2026-09-15, A, B) are used, not T25.WINDOWS (whose recent ends 2026-12-31); series_metrics slices label dates.
- Several rules share one decision loop per (variant, offset): decision inputs, targets and returns are computed once, each rule keeps its own (w_state, h_state, x_prev); B0 is one of them and was checked against the saved R6 parquets (identity.json: o0 and o3, four columns, max abs diff 0.0; all five offsets also 0.0).
- delta_offset_median = median over the 5 offsets of the rule's net Sharpe minus median over the 5 offsets of B0's net Sharpe (E1); the median of the per-offset differences is reported but not used for E1.
- E2 counts offsets with a strictly higher net Sharpe than B0 of the same offset in each window; E3 uses the full-window Newey-West t (Bartlett, lag 5, intercept only, no small-sample correction) of the blended daily net difference; E4 uses the OLS and Dimson beta of the blended net series vs SPY in recent and stress.
- The Newey-West t is computed by hac_mean_t in the script; cross-check on N50 full: hac_mean_t 1.758 vs book_v12_score.nw_ols intercept t 1.760 with a random regressor (same estimator up to the regressor).
- 2x cost net = gross - 2 * trade cost - borrow on the same rows (borrow not doubled).
- Selection tie rule (within 0.01 of the top recent offset-median net Sharpe, take the lower recent turnover) is implemented but was not needed: no rule met E1-E4.
- gross_exposure_mean is the mean over window rows of sum|x_new| held in each block, averaged over the 5 offsets.
- D1 drift = sum|x_old - x_prev_new| and target change = sum|w_tgt - w_tgt_prev| at refresh rows (first refresh excluded), summed per window, divided by window years (rows/252), averaged over the 5 offsets; one offset pass is one full book, so values are in units of book equity.
- D2 rank autocorrelation: Spearman between consecutive offset-0 decision dates over in_u3000 members with finite values at both dates; weeks with an undefined correlation (constant cross-section) are dropped and the week count is reported per series and window; windows by the later decision date.
- Stage 2 (variants, account, placebo, score) was not run because no rule met E1-E4 (stage gate of hypotheses.md section 5).
