# Signal card: rev_5d

- Source: `data/features/daily_broad:ret_5`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T11:57:47+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": true, "tradable_tiers_20bp": [], "distinct_from_controls": false}

Coverage 2016-01-29..2026-09-17, 2281 names/day (100% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.006 | 2.0 | 50% | 0.005 | 0.010 | 0.008 | 0.003 | 0.002 |
| 5d | 0.010 | 2.6 | 51% | 0.010 | 0.015 | 0.014 | 0.007 | 0.001 |
| 20d | 0.007 | 2.0 | 51% | 0.000 | 0.009 | 0.011 | 0.004 | -0.000 |
| 60d | -0.003 | -0.3 | 47% | -0.016 | 0.005 | 0.001 | -0.008 | -0.001 |

t: non-overlapping samples. Decay (mean IC): 1d 0.006, 2d 0.010, 3d 0.011, 5d 0.010, 10d 0.008, 20d 0.007, 40d -0.001, 60d -0.003

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.05% | -0.02% | -0.00% | -0.00% | 0.00% | 0.01% | 0.01% | 0.02% | 0.03% | 0.01% |
| 5d | -0.17% | -0.06% | -0.03% | -0.01% | 0.02% | 0.02% | 0.05% | 0.07% | 0.09% | 0.01% |
| 20d | -0.39% | -0.04% | -0.02% | 0.02% | 0.08% | 0.10% | 0.13% | 0.16% | 0.17% | -0.22% |
| 60d | -0.68% | 0.07% | 0.13% | 0.21% | 0.25% | 0.29% | 0.30% | 0.30% | 0.14% | -0.99% |

Shuffle placebo (10 seeds, 5d): IC -0.001..0.000; top-K excess -11.3%..-7.8%/yr.
Overlap with controls (mean rank corr): momentum_12_1 -0.03, reversal_5d -1.00, size_dollar_adv_63 -0.02, volatility_63 0.03

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -30.3% | -0.61 | -98.3% | -39.1% | -1.34 | 93x | 100% | -80.2% |
| all | 20d | -19.1% | -0.36 | -96.3% | -26.3% | -1.16 | 24x | 100% | -63.2% |
| all | 60d | -14.9% | -0.28 | -93.5% | -22.3% | -1.17 | 8x | 100% | -47.2% |
| t1 | 5d | 2.7% | 0.26 | -65.6% | -5.9% | -0.27 | 88x | 100% | 2.3% |
| t1 | 20d | 11.9% | 0.50 | -59.5% | 1.3% | 0.08 | 22x | 100% | 5.4% |
| t1 | 60d | 11.7% | 0.51 | -57.0% | 0.5% | 0.03 | 7x | 100% | 6.0% |
| t2 | 5d | -4.4% | 0.09 | -77.0% | -9.5% | -0.38 | 91x | 100% | -11.4% |
| t2 | 20d | 4.9% | 0.31 | -71.6% | -1.9% | -0.10 | 23x | 100% | -2.9% |
| t2 | 60d | 4.1% | 0.29 | -67.5% | -3.5% | -0.22 | 8x | 100% | -1.7% |
| t3 | 5d | -32.4% | -0.77 | -98.8% | -42.0% | -1.69 | 90x | 100% | -92.3% |
| t3 | 20d | -19.8% | -0.43 | -96.6% | -26.4% | -1.36 | 23x | 100% | -68.6% |
| t3 | 60d | -14.6% | -0.30 | -93.6% | -21.0% | -1.27 | 8x | 100% | -48.5% |

