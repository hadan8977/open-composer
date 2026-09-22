# H-20260922-02 report: S3 volatility target and drawdown brake

Iteration `h20260922_02_s3_voltarget`. Twelve preregistered cells, selection rule: highest selection-window Sharpe at 10 bp per side. Selection-window winner: **s3_lb63_vt40_nobrake**.

Engine identity check: cell `s3_lb63_novt_nobrake` is the unmodified S3 sleeve and reproduces anchor 145.4% / -56.4% / 1.48 against the published 145.4% / -56.4% / 1.48 (match).

## Per-cell windows (10 bp per side)

| cell | select Sh | select CAGR | holdout Sh | holdout CAGR | anchor Sh | anchor CAGR | anchor maxDD | turnover/yr |
|---|---|---|---|---|---|---|---|---|
| `s3_lb63_vt40_nobrake` | 1.36 | 71.3% | 2.04 | 130.5% | 1.66 | 98.3% | -30.2% | 9.4 |
| `s3_lb63_vt40_brake25` | 1.35 | 68.3% | 2.04 | 130.5% | 1.66 | 95.3% | -29.6% | 10.1 |
| `s3_lb63_vt60_nobrake` | 1.30 | 80.7% | 2.07 | 224.8% | 1.64 | 128.4% | -36.2% | 10.4 |
| `s3_lb63_novt_nobrake` | 1.21 | 81.9% | 1.80 | 309.5% | 1.48 | 145.4% | -56.4% | 10.1 |
| `s3_lbblend_vt40_nobrake` | 1.16 | 58.8% | 1.92 | 125.3% | 1.37 | 74.9% | -35.2% | 6.2 |
| `s3_lbblend_vt60_nobrake` | 1.10 | 65.6% | 1.94 | 211.3% | 1.30 | 91.0% | -44.6% | 6.5 |
| `s3_lb63_vt60_brake25` | 1.08 | 54.6% | 1.45 | 110.7% | 1.29 | 78.9% | -40.9% | 12.9 |
| `s3_lbblend_novt_nobrake` | 1.05 | 67.6% | 1.54 | 207.6% | 1.16 | 91.2% | -56.4% | 3.7 |
| `s3_lbblend_vt40_brake25` | 1.03 | 47.5% | 1.92 | 125.3% | 1.37 | 71.7% | -32.3% | 7.6 |
| `s3_lb63_novt_brake25` | 0.90 | 45.7% | 2.02 | 306.6% | 1.36 | 103.4% | -46.2% | 15.9 |
| `s3_lbblend_novt_brake25` | 0.87 | 44.5% | 1.73 | 208.5% | 1.17 | 79.2% | -51.5% | 12.5 |
| `s3_lbblend_vt60_brake25` | 0.81 | 38.6% | 1.47 | 120.9% | 1.03 | 58.5% | -48.6% | 11.1 |

## The five required numbers, anchor window

| reference | anchor Sharpe | anchor CAGR | anchor maxDD |
|---|---|---|---|
| bench_SPY | 1.02 | 20.9% | -18.6% |
| bench_MTUM | 1.05 | 30.0% | -21.0% |
| bench_SPMO | 1.27 | 35.8% | -20.3% |
| bench_TQQQ | 0.93 | 53.5% | -57.2% |
| bench_QQQ | 0.96 | 24.7% | -22.6% |
| bench_A4_equal_weight | 1.09 | 77.1% | -64.3% |

Volatility-matched excess over SPY for the winner (anchor CAGR minus cell_vol/SPY_vol times SPY CAGR): **38.6%**.
Random-pick placebo for the winner: 10.0% of 60 seeds beat it on the selection window, 13.3% on the holdout; placebo select Sharpe median 1.06, p95 1.44.

## Gate table

| cell | G1 ret+DD | G1' Sh | G2 holdout | G3 placebo | G4 20bp | G5 exec | all |
|---|---|---|---|---|---|---|---|
| `s3_lb63_vt40_nobrake` | pass | FAIL | pass | pass (10.0%) | pass | pass | pass |
| `s3_lb63_vt40_brake25` | pass | FAIL | pass | pass (8.3%) | pass | pass | pass |
| `s3_lb63_vt60_nobrake` | FAIL | FAIL | pass | pass (5.0%) | FAIL | pass | FAIL |
| `s3_lb63_novt_nobrake` | FAIL | FAIL | pass | pass (6.7%) | FAIL | pass | FAIL |
| `s3_lbblend_vt40_nobrake` | FAIL | FAIL | pass | FAIL (35.0%) | FAIL | pass | FAIL |
| `s3_lbblend_vt60_nobrake` | FAIL | FAIL | pass | FAIL (26.7%) | FAIL | pass | FAIL |
| `s3_lb63_vt60_brake25` | FAIL | FAIL | pass | pass (10.0%) | FAIL | pass | FAIL |
| `s3_lbblend_novt_nobrake` | FAIL | FAIL | pass | FAIL (23.3%) | FAIL | pass | FAIL |
| `s3_lbblend_vt40_brake25` | pass | FAIL | pass | FAIL (36.7%) | pass | pass | FAIL |
| `s3_lb63_novt_brake25` | FAIL | FAIL | pass | FAIL (20.0%) | FAIL | pass | FAIL |
| `s3_lbblend_novt_brake25` | FAIL | FAIL | pass | FAIL (51.7%) | FAIL | pass | FAIL |
| `s3_lbblend_vt60_brake25` | FAIL | FAIL | pass | FAIL (63.3%) | FAIL | pass | FAIL |

## Stress view (20 bp per side)

| cell | anchor CAGR | anchor maxDD | anchor Sharpe | holdout Sharpe |
|---|---|---|---|---|
| `s3_lb63_vt40_nobrake` | 96.5% | -30.2% | 1.64 | 2.02 |
| `s3_lb63_vt40_brake25` | 94.1% | -29.6% | 1.65 | 2.02 |
| `s3_lb63_vt60_nobrake` | 126.1% | -36.3% | 1.62 | 2.06 |
| `s3_lb63_novt_nobrake` | 143.0% | -56.4% | 1.47 | 1.79 |
| `s3_lbblend_vt40_nobrake` | 73.8% | -35.3% | 1.36 | 1.91 |
| `s3_lbblend_vt60_nobrake` | 89.8% | -44.9% | 1.29 | 1.93 |
| `s3_lb63_vt60_brake25` | 68.4% | -45.3% | 1.17 | 1.43 |
| `s3_lbblend_novt_nobrake` | 90.5% | -56.4% | 1.15 | 1.54 |
| `s3_lbblend_vt40_brake25` | 69.0% | -32.8% | 1.33 | 1.91 |
| `s3_lb63_novt_brake25` | 114.9% | -41.1% | 1.46 | 2.00 |
| `s3_lbblend_novt_brake25` | 85.7% | -48.6% | 1.22 | 1.72 |
| `s3_lbblend_vt60_brake25` | 61.7% | -39.9% | 1.08 | 1.46 |

