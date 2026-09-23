# Signal card: intraday_rev_21

- Source: `data/features/daily_broad:intraday_return_21d_mean`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:23:56+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": false, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2016-01-29..2026-09-04, 1719 names/day (75% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.002 | 0.6 | 49% | 0.001 | 0.002 | 0.004 | -0.001 | -0.002 |
| 5d | 0.004 | 0.8 | 48% | -0.004 | 0.002 | 0.007 | 0.002 | -0.004 |
| 20d | -0.003 | 0.1 | 47% | -0.029 | -0.007 | -0.000 | -0.004 | -0.004 |
| 60d | -0.011 | -1.1 | 42% | -0.025 | -0.012 | -0.006 | -0.015 | 0.004 |

t: non-overlapping samples. Decay (mean IC): 1d 0.002, 2d 0.003, 3d 0.004, 5d 0.004, 10d 0.003, 20d -0.003, 40d -0.008, 60d -0.011

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.02% | -0.00% | -0.01% | -0.00% | -0.00% | 0.00% | 0.00% | 0.01% | 0.00% | 0.02% |
| 5d | -0.07% | -0.01% | -0.01% | -0.01% | -0.02% | 0.01% | 0.02% | 0.02% | 0.03% | 0.05% |
| 20d | 0.04% | 0.03% | -0.03% | -0.00% | -0.00% | 0.00% | 0.02% | 0.04% | 0.01% | -0.12% |
| 60d | 0.11% | 0.08% | 0.09% | 0.06% | 0.09% | 0.03% | 0.03% | 0.03% | -0.03% | -0.49% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.000; top-K excess -0.5%..1.0%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.00, reversal_5d -0.39, size_dollar_adv_63 -0.02, volatility_63 0.02

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 0.1% | 0.23 | -85.1% | -2.1% | -0.07 | 51x | 100% | -21.1% |
| all | 20d | 3.1% | 0.28 | -80.9% | -0.6% | -0.02 | 22x | 100% | -14.1% |
| all | 60d | 4.8% | 0.31 | -78.6% | -0.3% | -0.01 | 8x | 100% | -10.3% |
| t1 | 5d | 2.5% | 0.26 | -62.5% | -5.8% | -0.25 | 46x | 100% | -9.4% |
| t1 | 20d | 6.8% | 0.36 | -64.7% | -2.5% | -0.13 | 21x | 100% | -3.8% |
| t1 | 60d | 9.7% | 0.44 | -60.7% | -0.9% | -0.05 | 7x | 100% | -0.1% |
| t2 | 5d | 0.4% | 0.21 | -72.9% | -4.6% | -0.18 | 49x | 100% | -12.5% |
| t2 | 20d | 3.5% | 0.28 | -74.7% | -2.7% | -0.13 | 22x | 100% | -13.7% |
| t2 | 60d | 6.7% | 0.36 | -67.7% | -0.6% | -0.03 | 8x | 100% | -7.7% |
| t3 | 5d | -0.3% | 0.19 | -82.6% | -3.2% | -0.13 | 48x | 100% | -23.6% |
| t3 | 20d | 5.1% | 0.32 | -75.3% | 1.0% | 0.05 | 22x | 100% | -11.8% |
| t3 | 60d | 5.8% | 0.34 | -74.7% | 0.8% | 0.05 | 8x | 100% | -5.9% |

