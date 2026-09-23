# Signal card: max_ret_21

- Source: `data/features/daily_broad:max_ret_1_21`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:15:28+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": false}

Coverage 2016-02-03..2026-09-17, 2274 names/day (100% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.016 | 4.3 | 53% | 0.018 | 0.007 | 0.012 | 0.019 | 0.010 |
| 5d | 0.026 | 3.1 | 55% | 0.025 | 0.010 | 0.019 | 0.032 | 0.017 |
| 20d | 0.041 | 2.7 | 60% | 0.031 | 0.020 | 0.031 | 0.048 | 0.030 |
| 60d | 0.062 | 2.5 | 65% | 0.043 | 0.033 | 0.048 | 0.072 | 0.053 |

t: non-overlapping samples. Decay (mean IC): 1d 0.016, 2d 0.020, 3d 0.023, 5d 0.026, 10d 0.032, 20d 0.041, 40d 0.053, 60d 0.062

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.04% | 0.00% | 0.01% | 0.01% | 0.01% | 0.01% | 0.00% | 0.00% | 0.00% | -0.01% |
| 5d | -0.23% | -0.00% | 0.02% | 0.05% | 0.03% | 0.07% | 0.02% | 0.03% | 0.03% | -0.02% |
| 20d | -0.93% | -0.01% | 0.18% | 0.18% | 0.19% | 0.16% | 0.08% | 0.13% | 0.07% | -0.05% |
| 60d | -2.10% | 0.06% | 0.38% | 0.43% | 0.40% | 0.33% | 0.25% | 0.23% | 0.12% | -0.12% |

Shuffle placebo (10 seeds, 20d): IC -0.000..0.001; top-K excess -3.1%..-1.5%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.08, reversal_5d -0.09, size_dollar_adv_63 0.16, volatility_63 -0.74

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 0.7% | 0.12 | -39.8% | -11.5% | -0.67 | 34x | 100% | -14.7% |
| all | 20d | 4.5% | 0.60 | -26.4% | -7.9% | -0.47 | 16x | 100% | -11.2% |
| all | 60d | 5.3% | 0.74 | -24.0% | -7.2% | -0.43 | 7x | 100% | -9.8% |
| t1 | 5d | 3.1% | 0.29 | -35.2% | -11.7% | -0.83 | 39x | 100% | -15.4% |
| t1 | 20d | 6.8% | 0.57 | -29.3% | -8.3% | -0.60 | 19x | 100% | -13.0% |
| t1 | 60d | 9.5% | 0.78 | -30.1% | -5.8% | -0.43 | 7x | 100% | -9.6% |
| t2 | 5d | 2.1% | 0.23 | -42.9% | -10.4% | -0.74 | 40x | 100% | -11.1% |
| t2 | 20d | 6.0% | 0.57 | -35.0% | -6.8% | -0.48 | 19x | 100% | -7.9% |
| t2 | 60d | 8.1% | 0.77 | -31.4% | -4.9% | -0.36 | 7x | 100% | -4.5% |
| t3 | 5d | 0.5% | 0.10 | -41.8% | -9.9% | -0.63 | 39x | 100% | -13.3% |
| t3 | 20d | 4.8% | 0.49 | -35.2% | -5.8% | -0.38 | 18x | 100% | -8.9% |
| t3 | 60d | 5.6% | 0.54 | -37.5% | -5.0% | -0.33 | 7x | 100% | -7.9% |

