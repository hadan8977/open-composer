# Signal card: gross_profitability

- Source: `data/features/sec_fundamentals_daily:gross_profitability`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T08:59:32+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2016-01-29..2026-09-17, 766 names/day (34% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.009 | 4.6 | 53% | 0.006 | 0.007 | 0.006 | 0.012 | 0.009 |
| 5d | 0.013 | 3.0 | 55% | 0.007 | 0.011 | 0.006 | 0.018 | 0.013 |
| 20d | 0.019 | 2.2 | 56% | 0.006 | 0.017 | 0.006 | 0.030 | 0.020 |
| 60d | 0.032 | 2.3 | 59% | -0.005 | 0.036 | 0.010 | 0.045 | 0.032 |

t: non-overlapping samples. Decay (mean IC): 1d 0.009, 2d 0.010, 3d 0.011, 5d 0.013, 10d 0.015, 20d 0.019, 40d 0.027, 60d 0.032

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.04% | 0.00% | 0.00% | -0.00% | 0.01% | 0.01% | 0.01% | 0.01% | 0.00% | -0.00% |
| 5d | -0.23% | 0.02% | 0.02% | -0.00% | 0.04% | 0.07% | 0.05% | 0.04% | 0.01% | -0.01% |
| 20d | -0.93% | -0.00% | 0.09% | 0.00% | 0.11% | 0.29% | 0.23% | 0.14% | 0.07% | -0.02% |
| 60d | -2.40% | 0.01% | 0.15% | -0.03% | 0.45% | 0.78% | 0.74% | 0.31% | 0.06% | -0.09% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess 0.1%..1.1%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.01, reversal_5d 0.01, size_dollar_adv_63 0.02, volatility_63 -0.02

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 10.1% | 0.49 | -55.7% | 0.7% | 0.06 | 3x | 100% | -14.1% |
| all | 20d | 10.3% | 0.50 | -55.9% | 0.8% | 0.06 | 3x | 100% | -12.6% |
| all | 60d | 10.0% | 0.50 | -54.4% | 0.5% | 0.04 | 2x | 100% | -10.7% |
| t1 | 5d | 11.3% | 0.61 | -41.0% | -2.6% | -0.26 | 3x | 100% | -14.8% |
| t1 | 20d | 11.9% | 0.63 | -40.1% | -2.0% | -0.20 | 2x | 100% | -14.1% |
| t1 | 60d | 10.7% | 0.59 | -40.8% | -3.2% | -0.32 | 2x | 100% | -14.9% |
| t2 | 5d | 11.4% | 0.56 | -45.4% | 0.7% | 0.07 | 4x | 100% | -8.1% |
| t2 | 20d | 10.9% | 0.55 | -45.5% | 0.3% | 0.03 | 3x | 100% | -7.6% |
| t2 | 60d | 10.6% | 0.54 | -46.1% | -0.1% | -0.01 | 2x | 100% | -7.5% |
| t3 | 5d | 10.4% | 0.50 | -52.8% | 2.7% | 0.22 | 4x | 100% | -7.7% |
| t3 | 20d | 11.2% | 0.53 | -55.2% | 3.3% | 0.27 | 3x | 100% | -4.9% |
| t3 | 60d | 12.0% | 0.56 | -52.7% | 4.0% | 0.33 | 2x | 100% | -2.7% |

