# Signal card: comp_c4_mom_roe

- Source: `composite: momentum_252_21x+1, roex+1`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T11:04:11+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": true, "tradable_tiers_20bp": ["t1", "t2"], "distinct_from_controls": false}

Coverage 2017-01-03..2026-09-17, 1629 names/day (71% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.017 | 5.7 | 56% | 0.021 | 0.016 | 0.015 | 0.016 | 0.007 |
| 5d | 0.023 | 3.3 | 58% | 0.028 | 0.019 | 0.019 | 0.024 | 0.010 |
| 20d | 0.030 | 2.6 | 62% | 0.032 | 0.021 | 0.022 | 0.033 | 0.013 |
| 60d | 0.045 | 2.3 | 65% | 0.046 | 0.030 | 0.034 | 0.050 | 0.017 |

t: non-overlapping samples. Decay (mean IC): 1d 0.017, 2d 0.020, 3d 0.021, 5d 0.023, 10d 0.026, 20d 0.030, 40d 0.038, 60d 0.045

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.03% | -0.02% | -0.00% | 0.00% | -0.00% | 0.00% | 0.01% | 0.00% | 0.01% | 0.02% |
| 5d | -0.15% | -0.06% | -0.01% | 0.01% | 0.01% | 0.01% | 0.02% | 0.03% | 0.03% | 0.10% |
| 20d | -0.53% | -0.17% | -0.04% | 0.03% | 0.05% | 0.01% | 0.11% | 0.11% | 0.06% | 0.36% |
| 60d | -1.26% | -0.54% | -0.15% | -0.07% | 0.06% | 0.25% | 0.24% | 0.19% | 0.31% | 0.97% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.002; top-K excess -0.7%..0.7%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.69, reversal_5d 0.03, size_dollar_adv_63 0.20, volatility_63 -0.23

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 12.5% | 0.54 | -50.8% | 5.5% | 0.32 | 14x | 100% | 14.4% |
| all | 20d | 13.9% | 0.59 | -47.7% | 6.7% | 0.40 | 7x | 100% | 14.9% |
| all | 60d | 15.5% | 0.64 | -44.2% | 7.9% | 0.51 | 5x | 100% | 14.3% |
| t1 | 5d | 16.3% | 0.71 | -36.7% | 3.6% | 0.28 | 12x | 100% | 9.6% |
| t1 | 20d | 17.0% | 0.73 | -36.8% | 4.2% | 0.33 | 6x | 100% | 9.6% |
| t1 | 60d | 16.1% | 0.71 | -35.9% | 3.3% | 0.28 | 4x | 100% | 7.9% |
| t2 | 5d | 13.5% | 0.62 | -39.7% | 4.5% | 0.34 | 13x | 100% | 3.8% |
| t2 | 20d | 14.8% | 0.67 | -40.6% | 5.6% | 0.45 | 7x | 100% | 7.1% |
| t2 | 60d | 16.8% | 0.74 | -41.0% | 7.2% | 0.63 | 4x | 100% | 10.8% |
| t3 | 5d | 8.9% | 0.45 | -48.5% | 3.5% | 0.27 | 14x | 100% | 9.6% |
| t3 | 20d | 10.6% | 0.51 | -49.1% | 5.0% | 0.40 | 8x | 100% | 10.3% |
| t3 | 60d | 11.5% | 0.54 | -48.8% | 5.7% | 0.51 | 5x | 100% | 8.1% |

