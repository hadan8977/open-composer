# Signal card: rev_21d

- Source: `data/features/daily_broad:ret_21`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:01:55+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2016-02-03..2026-09-17, 2274 names/day (100% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.002 | 0.7 | 50% | 0.001 | 0.002 | 0.005 | 0.000 | -0.002 |
| 5d | 0.008 | 1.3 | 50% | 0.003 | 0.008 | 0.013 | 0.004 | -0.003 |
| 20d | 0.004 | 0.7 | 50% | -0.020 | 0.006 | 0.007 | -0.000 | -0.003 |
| 60d | -0.008 | -0.5 | 44% | -0.018 | 0.006 | -0.000 | -0.015 | 0.003 |

t: non-overlapping samples. Decay (mean IC): 1d 0.002, 2d 0.005, 3d 0.007, 5d 0.008, 10d 0.008, 20d 0.004, 40d -0.003, 60d -0.008

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.03% | -0.01% | -0.00% | -0.00% | 0.00% | 0.01% | 0.01% | 0.01% | 0.02% | 0.00% |
| 5d | -0.13% | -0.05% | -0.01% | -0.00% | 0.01% | 0.03% | 0.05% | 0.05% | 0.08% | -0.02% |
| 20d | -0.30% | -0.07% | -0.01% | 0.05% | 0.10% | 0.15% | 0.18% | 0.19% | 0.17% | -0.46% |
| 60d | -0.56% | -0.03% | 0.15% | 0.27% | 0.36% | 0.38% | 0.42% | 0.30% | 0.11% | -1.39% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.000; top-K excess -3.0%..-1.4%/yr.
Overlap with controls (mean rank corr): momentum_12_1 -0.03, reversal_5d -0.43, size_dollar_adv_63 -0.03, volatility_63 0.04

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -23.1% | -0.34 | -98.0% | -28.4% | -0.89 | 49x | 100% | -77.7% |
| all | 20d | -25.8% | -0.50 | -98.4% | -33.6% | -1.22 | 23x | 100% | -81.2% |
| all | 60d | -20.7% | -0.41 | -95.9% | -28.5% | -1.24 | 8x | 100% | -57.5% |
| t1 | 5d | 4.5% | 0.31 | -70.3% | -3.4% | -0.14 | 46x | 100% | 2.7% |
| t1 | 20d | 8.5% | 0.41 | -67.9% | -0.6% | -0.03 | 21x | 100% | 4.0% |
| t1 | 60d | 11.2% | 0.48 | -62.6% | 0.7% | 0.04 | 7x | 100% | 4.0% |
| t2 | 5d | 4.4% | 0.31 | -71.1% | -0.0% | -0.00 | 49x | 100% | -3.1% |
| t2 | 20d | -0.9% | 0.17 | -78.6% | -6.5% | -0.28 | 23x | 100% | -12.7% |
| t2 | 60d | 1.3% | 0.22 | -68.0% | -5.5% | -0.29 | 8x | 100% | -5.9% |
| t3 | 5d | -28.9% | -0.58 | -98.9% | -36.0% | -1.29 | 48x | 100% | -90.2% |
| t3 | 20d | -26.1% | -0.56 | -98.2% | -33.4% | -1.38 | 23x | 100% | -83.8% |
| t3 | 60d | -19.3% | -0.40 | -95.7% | -25.9% | -1.29 | 8x | 100% | -58.6% |

