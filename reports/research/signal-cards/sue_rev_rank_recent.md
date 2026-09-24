# Signal card: sue_rev_rank_recent

- Source: `data/features/sec_fundamentals_daily:sue_rev where days_since_report <= 5`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T08:45:43+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2016-01-29..2026-09-17, 104 names/day (5% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.007 | 1.6 | 53% | 0.000 | -0.006 | 0.015 | 0.016 | 0.004 |
| 5d | 0.016 | 1.9 | 56% | 0.007 | -0.009 | 0.029 | 0.019 | 0.013 |
| 20d | 0.010 | 0.7 | 54% | 0.001 | -0.021 | 0.028 | 0.033 | 0.018 |
| 60d | 0.011 | 0.2 | 56% | 0.005 | 0.001 | 0.022 | 0.029 | 0.016 |

t: non-overlapping samples. Decay (mean IC): 1d 0.007, 2d 0.011, 3d 0.011, 5d 0.016, 10d 0.015, 20d 0.010, 40d 0.013, 60d 0.011

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.05% | -0.01% | 0.00% | -0.02% | 0.00% | 0.02% | 0.05% | -0.02% | 0.01% | 0.03% |
| 5d | -0.10% | -0.09% | -0.09% | -0.05% | 0.06% | 0.16% | 0.07% | -0.07% | 0.00% | 0.11% |
| 20d | -0.26% | -0.01% | -0.05% | 0.00% | 0.24% | 0.01% | 0.22% | -0.03% | -0.06% | -0.07% |
| 60d | -0.63% | -0.22% | -0.21% | 0.38% | 0.68% | 0.14% | 0.24% | -0.28% | 0.07% | -0.10% |

Shuffle placebo (10 seeds, 20d): IC -0.004..0.003; top-K excess -2.7%..-2.0%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.15, reversal_5d 0.03, size_dollar_adv_63 0.13, volatility_63 -0.07

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -1.5% | -0.07 | -44.6% | -4.2% | -0.69 | 27x | 38% | -6.4% |
| all | 20d | 1.3% | 0.18 | -36.0% | -2.4% | -0.21 | 8x | 63% | -0.4% |
| all | 60d | 4.4% | 0.66 | -15.5% | -8.7% | -0.56 | 2x | 100% | -8.1% |
| t1 | 5d | -1.7% | -0.20 | -25.5% | -2.9% | -0.53 | 15x | 23% | -4.1% |
| t1 | 20d | 1.4% | 0.30 | -14.2% | -5.4% | -0.50 | 4x | 47% | -7.6% |
| t1 | 60d | 2.4% | 0.74 | -5.0% | -13.2% | -0.76 | 1x | 97% | -16.7% |
| t2 | 5d | -2.5% | -0.23 | -35.8% | -2.1% | -0.35 | 19x | 28% | -4.7% |
| t2 | 20d | 1.6% | 0.26 | -22.5% | -1.5% | -0.14 | 5x | 52% | -0.9% |
| t2 | 60d | 3.2% | 0.72 | -7.9% | -10.1% | -0.59 | 2x | 98% | -11.0% |
| t3 | 5d | -1.9% | -0.15 | -40.7% | -1.8% | -0.28 | 19x | 27% | -3.9% |
| t3 | 20d | 1.4% | 0.22 | -30.1% | -1.4% | -0.11 | 5x | 51% | 0.3% |
| t3 | 60d | 2.9% | 0.61 | -10.2% | -8.4% | -0.46 | 2x | 98% | -7.1% |

