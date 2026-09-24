# Signal card: asset_growth

- Source: `data/features/sec_fundamentals_daily:asset_growth`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T09:07:11+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": false, "timely": false, "tradable_tiers_20bp": ["t1", "t2"], "distinct_from_controls": true}

Coverage 2016-01-29..2026-09-17, 1576 names/day (69% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | -0.004 | -2.3 | 45% | -0.005 | -0.001 | -0.003 | -0.005 | -0.003 |
| 5d | -0.004 | -1.1 | 45% | -0.005 | 0.001 | -0.003 | -0.005 | -0.005 |
| 20d | -0.003 | -0.4 | 42% | -0.006 | 0.006 | -0.004 | -0.006 | -0.005 |
| 60d | -0.003 | -0.1 | 38% | -0.013 | 0.017 | -0.008 | -0.006 | -0.005 |

t: non-overlapping samples. Decay (mean IC): 1d -0.004, 2d -0.004, 3d -0.004, 5d -0.004, 10d -0.004, 20d -0.003, 40d -0.004, 60d -0.003

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.01% | 0.01% | 0.01% | 0.00% | 0.00% | 0.00% | -0.00% | -0.01% | 0.01% | -0.00% |
| 5d | -0.06% | 0.04% | 0.04% | 0.01% | 0.01% | 0.02% | -0.01% | -0.05% | 0.03% | -0.02% |
| 20d | -0.23% | 0.13% | 0.14% | 0.03% | 0.11% | 0.05% | -0.03% | -0.21% | 0.12% | -0.09% |
| 60d | -0.54% | 0.34% | 0.44% | 0.12% | 0.09% | 0.09% | -0.09% | -0.65% | 0.34% | -0.12% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess -0.6%..1.6%/yr.
Overlap with controls (mean rank corr): momentum_12_1 -0.04, reversal_5d -0.00, size_dollar_adv_63 -0.03, volatility_63 -0.07

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -3.8% | 0.06 | -83.2% | -10.4% | -0.47 | 5x | 100% | -44.3% |
| all | 20d | -2.0% | 0.11 | -79.7% | -9.0% | -0.43 | 5x | 100% | -41.7% |
| all | 60d | 0.2% | 0.16 | -71.5% | -7.3% | -0.40 | 4x | 100% | -33.8% |
| t1 | 5d | 22.9% | 0.99 | -37.9% | 7.9% | 0.74 | 4x | 100% | 11.7% |
| t1 | 20d | 24.3% | 1.05 | -35.7% | 8.9% | 0.88 | 3x | 100% | 13.2% |
| t1 | 60d | 23.2% | 1.03 | -34.6% | 7.9% | 0.84 | 3x | 100% | 13.3% |
| t2 | 5d | 13.6% | 0.61 | -45.5% | 3.3% | 0.26 | 5x | 100% | -1.8% |
| t2 | 20d | 14.6% | 0.64 | -47.0% | 4.1% | 0.34 | 5x | 100% | 0.7% |
| t2 | 60d | 14.8% | 0.66 | -46.9% | 4.2% | 0.36 | 3x | 100% | 1.0% |
| t3 | 5d | -9.0% | -0.10 | -87.9% | -14.4% | -0.66 | 7x | 100% | -47.5% |
| t3 | 20d | -7.9% | -0.07 | -85.2% | -13.3% | -0.65 | 6x | 100% | -43.7% |
| t3 | 60d | -4.4% | 0.02 | -81.3% | -10.3% | -0.58 | 4x | 100% | -38.4% |

