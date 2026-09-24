# Signal card: accruals

- Source: `data/features/sec_fundamentals_daily:accruals`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T09:13:24+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": false, "timely": false, "tradable_tiers_20bp": ["t1"], "distinct_from_controls": true}

Coverage 2016-01-29..2026-09-17, 685 names/day (30% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | -0.003 | -1.9 | 48% | -0.009 | 0.002 | -0.003 | -0.005 | -0.002 |
| 5d | -0.004 | -1.5 | 47% | -0.014 | 0.003 | -0.005 | -0.007 | -0.004 |
| 20d | -0.006 | -0.8 | 44% | -0.022 | 0.010 | -0.009 | -0.011 | -0.009 |
| 60d | -0.014 | -1.1 | 41% | -0.046 | 0.012 | -0.024 | -0.016 | -0.018 |

t: non-overlapping samples. Decay (mean IC): 1d -0.003, 2d -0.004, 3d -0.004, 5d -0.004, 10d -0.005, 20d -0.006, 40d -0.010, 60d -0.014

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.00% | -0.00% | 0.00% | -0.00% | -0.01% | -0.00% | -0.01% | -0.00% | 0.02% | -0.00% |
| 5d | -0.01% | -0.01% | 0.01% | -0.01% | -0.03% | -0.02% | -0.03% | 0.01% | 0.13% | -0.02% |
| 20d | -0.07% | -0.05% | 0.01% | 0.01% | -0.12% | -0.10% | -0.12% | 0.03% | 0.48% | -0.06% |
| 60d | -0.21% | -0.25% | -0.16% | 0.13% | -0.37% | -0.34% | -0.18% | -0.11% | 1.25% | 0.22% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess -2.5%..-0.3%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.02, reversal_5d -0.00, size_dollar_adv_63 0.00, volatility_63 0.22

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -5.6% | 0.03 | -89.2% | -11.3% | -0.50 | 8x | 100% | -42.0% |
| all | 20d | -2.4% | 0.12 | -86.1% | -8.2% | -0.38 | 7x | 100% | -37.9% |
| all | 60d | 5.5% | 0.33 | -69.6% | -0.9% | -0.05 | 5x | 100% | -14.0% |
| t1 | 5d | 20.6% | 0.80 | -43.5% | 7.3% | 0.60 | 8x | 100% | 6.3% |
| t1 | 20d | 20.0% | 0.79 | -42.5% | 6.6% | 0.57 | 6x | 100% | 6.1% |
| t1 | 60d | 19.0% | 0.77 | -42.7% | 5.6% | 0.51 | 5x | 100% | 8.8% |
| t2 | 5d | 13.7% | 0.58 | -54.6% | 4.2% | 0.29 | 9x | 100% | 4.0% |
| t2 | 20d | 12.3% | 0.54 | -56.3% | 2.7% | 0.20 | 7x | 100% | -2.2% |
| t2 | 60d | 12.4% | 0.55 | -48.8% | 2.7% | 0.21 | 5x | 100% | -2.2% |
| t3 | 5d | -4.4% | 0.04 | -86.3% | -9.5% | -0.50 | 10x | 100% | -45.2% |
| t3 | 20d | -2.2% | 0.11 | -82.9% | -7.3% | -0.40 | 8x | 100% | -40.0% |
| t3 | 60d | 4.6% | 0.30 | -71.1% | -1.1% | -0.07 | 6x | 100% | -15.7% |

