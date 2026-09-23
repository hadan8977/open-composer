# Signal card: days_to_cover

- Source: `data/features/short_interest:days_to_cover`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:41:28+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": ["t1"], "distinct_from_controls": true}

Coverage 2018-01-11..2026-09-16, 768 names/day (34% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.000 | 0.2 | 51% | 0.004 | 0.001 | -0.001 | n/a | 0.003 |
| 5d | 0.004 | 1.2 | 54% | 0.010 | 0.006 | 0.001 | n/a | 0.007 |
| 20d | 0.008 | 1.4 | 55% | 0.020 | 0.008 | 0.004 | n/a | 0.015 |
| 60d | 0.015 | 1.5 | 59% | 0.034 | 0.014 | 0.009 | n/a | 0.023 |

t: non-overlapping samples. Decay (mean IC): 1d 0.000, 2d 0.002, 3d 0.003, 5d 0.004, 10d 0.005, 20d 0.008, 40d 0.012, 60d 0.015

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.02% | -0.00% | -0.01% | 0.01% | -0.00% | -0.00% | 0.01% | 0.01% | 0.01% | 0.01% |
| 5d | -0.09% | -0.02% | -0.04% | 0.02% | -0.02% | 0.01% | 0.07% | 0.04% | 0.03% | -0.01% |
| 20d | -0.31% | -0.08% | -0.07% | 0.01% | 0.03% | -0.05% | 0.18% | 0.03% | 0.28% | -0.03% |
| 60d | -0.90% | -0.06% | -0.27% | 0.05% | 0.05% | -0.22% | 0.13% | 0.04% | 0.61% | 0.55% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess 0.6%..2.1%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.03, reversal_5d 0.01, size_dollar_adv_63 0.33, volatility_63 0.01

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -0.2% | 0.17 | -71.0% | -3.7% | -0.17 | 27x | 100% | 8.2% |
| all | 20d | 3.1% | 0.26 | -65.6% | -0.7% | -0.03 | 15x | 100% | 9.0% |
| all | 60d | 9.9% | 0.45 | -60.1% | 5.2% | 0.29 | 6x | 100% | 17.3% |
| t1 | 5d | 9.2% | 0.42 | -62.5% | 1.4% | 0.07 | 24x | 100% | 6.7% |
| t1 | 20d | 11.8% | 0.49 | -59.7% | 3.4% | 0.18 | 14x | 100% | 12.5% |
| t1 | 60d | 16.0% | 0.61 | -54.3% | 6.5% | 0.40 | 5x | 100% | 19.7% |
| t2 | 5d | -3.6% | 0.02 | -62.5% | -10.1% | -0.68 | 26x | 100% | -1.7% |
| t2 | 20d | -0.2% | 0.14 | -58.8% | -6.7% | -0.50 | 16x | 100% | -0.6% |
| t2 | 60d | 7.9% | 0.42 | -47.3% | 0.7% | 0.06 | 6x | 100% | 8.1% |
| t3 | 5d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 20d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 60d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |

