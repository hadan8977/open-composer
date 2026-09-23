# Signal card: idio_vol_63

- Source: `data/features/daily_broad:idio_vol_63`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:11:17+00:00
- Flags: {"predictive": true, "stable_years": true, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": false}

Coverage 2016-04-05..2026-09-17, 2254 names/day (99% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.018 | 4.5 | 53% | 0.021 | 0.012 | 0.013 | 0.022 | 0.014 |
| 5d | 0.031 | 3.6 | 55% | 0.031 | 0.018 | 0.021 | 0.037 | 0.026 |
| 20d | 0.052 | 3.4 | 60% | 0.046 | 0.034 | 0.038 | 0.060 | 0.045 |
| 60d | 0.078 | 3.0 | 66% | 0.067 | 0.047 | 0.059 | 0.090 | 0.073 |

t: non-overlapping samples. Decay (mean IC): 1d 0.018, 2d 0.023, 3d 0.027, 5d 0.031, 10d 0.039, 20d 0.052, 40d 0.067, 60d 0.078

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.04% | 0.00% | 0.01% | 0.01% | 0.01% | 0.01% | 0.01% | 0.00% | -0.00% | -0.00% |
| 5d | -0.26% | 0.02% | 0.05% | 0.04% | 0.04% | 0.04% | 0.05% | 0.03% | -0.00% | -0.01% |
| 20d | -1.02% | 0.07% | 0.19% | 0.18% | 0.15% | 0.15% | 0.15% | 0.10% | 0.04% | -0.00% |
| 60d | -2.46% | 0.41% | 0.55% | 0.45% | 0.43% | 0.38% | 0.14% | 0.12% | -0.00% | -0.03% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess -3.1%..-1.8%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.09, reversal_5d 0.03, size_dollar_adv_63 0.23, volatility_63 -0.97

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 6.6% | 0.73 | -27.5% | -5.0% | -0.33 | 16x | 100% | -4.7% |
| all | 20d | 8.4% | 0.89 | -27.6% | -3.3% | -0.22 | 10x | 100% | -3.8% |
| all | 60d | 7.5% | 0.77 | -30.6% | -4.1% | -0.27 | 6x | 100% | -3.7% |
| t1 | 5d | 9.0% | 0.67 | -33.5% | -5.5% | -0.43 | 15x | 100% | -6.6% |
| t1 | 20d | 11.1% | 0.81 | -33.0% | -3.6% | -0.28 | 9x | 100% | -6.5% |
| t1 | 60d | 11.0% | 0.81 | -34.3% | -3.6% | -0.29 | 5x | 100% | -5.8% |
| t2 | 5d | 8.6% | 0.74 | -31.3% | -3.3% | -0.26 | 16x | 100% | -2.7% |
| t2 | 20d | 9.6% | 0.81 | -31.4% | -2.5% | -0.19 | 10x | 100% | -2.2% |
| t2 | 60d | 9.3% | 0.78 | -31.6% | -2.7% | -0.21 | 6x | 100% | -2.8% |
| t3 | 5d | 6.5% | 0.60 | -38.2% | -3.2% | -0.22 | 16x | 100% | -1.9% |
| t3 | 20d | 7.6% | 0.65 | -41.8% | -2.2% | -0.14 | 9x | 100% | -1.2% |
| t3 | 60d | 7.4% | 0.59 | -44.2% | -2.1% | -0.14 | 5x | 100% | -2.1% |

