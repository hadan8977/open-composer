# Signal card: overnight_mom_21

- Source: `data/features/daily_broad:overnight_return_21d_mean`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:20:11+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": false, "timely": true, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2016-01-29..2026-09-04, 1719 names/day (75% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | -0.002 | -1.0 | 50% | -0.003 | 0.000 | -0.003 | -0.003 | -0.005 |
| 5d | -0.009 | -1.9 | 48% | -0.011 | -0.008 | -0.012 | -0.006 | -0.006 |
| 20d | -0.017 | -1.4 | 46% | -0.011 | -0.023 | -0.019 | -0.011 | -0.008 |
| 60d | -0.017 | -1.4 | 46% | -0.021 | -0.027 | -0.019 | -0.009 | -0.011 |

t: non-overlapping samples. Decay (mean IC): 1d -0.002, 2d -0.005, 3d -0.006, 5d -0.009, 10d -0.013, 20d -0.017, 40d -0.016, 60d -0.017

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | 0.02% | -0.01% | 0.00% | -0.01% | -0.00% | 0.00% | 0.00% | -0.00% | -0.00% | -0.00% |
| 5d | 0.06% | 0.01% | 0.01% | -0.00% | -0.00% | 0.01% | -0.00% | -0.01% | -0.03% | -0.03% |
| 20d | 0.08% | 0.05% | 0.12% | 0.08% | 0.08% | 0.05% | 0.02% | -0.03% | -0.13% | -0.32% |
| 60d | 0.07% | 0.06% | 0.07% | 0.08% | 0.07% | 0.01% | 0.02% | -0.01% | -0.20% | -0.17% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess -0.1%..1.4%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.07, reversal_5d 0.18, size_dollar_adv_63 -0.01, volatility_63 0.07

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -5.2% | 0.08 | -88.8% | -9.2% | -0.30 | 42x | 100% | -37.5% |
| all | 20d | 0.8% | 0.22 | -85.1% | -4.0% | -0.15 | 22x | 100% | -23.7% |
| all | 60d | 7.1% | 0.37 | -79.7% | 1.1% | 0.05 | 8x | 100% | -6.2% |
| t1 | 5d | 7.2% | 0.37 | -49.1% | -3.0% | -0.15 | 41x | 100% | -7.9% |
| t1 | 20d | 9.3% | 0.44 | -54.9% | -1.3% | -0.07 | 21x | 100% | -2.7% |
| t1 | 60d | 10.1% | 0.46 | -56.4% | -1.0% | -0.06 | 7x | 100% | 1.0% |
| t2 | 5d | -6.1% | -0.00 | -77.4% | -13.2% | -0.58 | 43x | 100% | -25.5% |
| t2 | 20d | -3.0% | 0.08 | -79.7% | -10.3% | -0.50 | 22x | 100% | -14.5% |
| t2 | 60d | 6.5% | 0.36 | -69.6% | -1.5% | -0.09 | 7x | 100% | -1.4% |
| t3 | 5d | -1.1% | 0.15 | -81.3% | -5.4% | -0.23 | 41x | 100% | -18.4% |
| t3 | 20d | 2.4% | 0.24 | -80.4% | -2.6% | -0.13 | 22x | 100% | -14.6% |
| t3 | 60d | 9.5% | 0.44 | -73.6% | 3.5% | 0.21 | 8x | 100% | 0.1% |

