# Signal card: season_2_5

- Source: `data/features/osap_price_broad:momseason_2_5`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:33:54+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2021-02-04..2026-09-17, 1825 names/day (81% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.002 | 0.8 | 50% | 0.004 | -0.001 | 0.002 | 0.003 | -0.000 |
| 5d | 0.006 | 1.4 | 51% | 0.008 | -0.001 | 0.007 | 0.007 | 0.003 |
| 20d | 0.013 | 1.6 | 53% | 0.014 | -0.000 | 0.016 | 0.014 | 0.010 |
| 60d | 0.004 | 0.3 | 51% | 0.002 | -0.008 | 0.007 | 0.004 | -0.002 |

t: non-overlapping samples. Decay (mean IC): 1d 0.002, 2d 0.002, 3d 0.004, 5d 0.006, 10d 0.011, 20d 0.013, 40d 0.006, 60d 0.004

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.02% | 0.00% | -0.00% | -0.00% | 0.01% | -0.00% | 0.01% | 0.00% | 0.00% | -0.01% |
| 5d | -0.14% | 0.01% | 0.00% | -0.01% | 0.02% | 0.02% | 0.03% | 0.04% | 0.04% | -0.01% |
| 20d | -0.61% | -0.01% | -0.01% | 0.01% | 0.08% | 0.14% | 0.14% | 0.20% | 0.22% | -0.16% |
| 60d | -1.11% | 0.05% | 0.27% | 0.24% | 0.26% | 0.35% | 0.25% | 0.26% | 0.29% | -0.87% |

Shuffle placebo (10 seeds, 20d): IC -0.000..0.001; top-K excess 0.7%..2.6%/yr.
Overlap with controls (mean rank corr): momentum_12_1 -0.02, reversal_5d 0.00, size_dollar_adv_63 0.04, volatility_63 0.02

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -17.6% | -0.38 | -74.0% | -18.8% | -1.00 | 49x | 100% | -15.2% |
| all | 20d | -10.9% | -0.17 | -62.1% | -11.5% | -0.68 | 23x | 100% | -9.0% |
| all | 60d | -7.1% | -0.07 | -59.0% | -8.0% | -0.56 | 8x | 100% | -6.2% |
| t1 | 5d | -4.7% | 0.01 | -50.2% | -10.3% | -0.68 | 44x | 100% | -9.3% |
| t1 | 20d | -0.1% | 0.15 | -43.2% | -6.0% | -0.45 | 21x | 100% | -5.3% |
| t1 | 60d | 2.8% | 0.24 | -43.7% | -3.5% | -0.31 | 7x | 100% | -0.9% |
| t2 | 5d | -2.8% | 0.05 | -52.7% | -5.8% | -0.41 | 48x | 100% | 1.2% |
| t2 | 20d | -3.1% | 0.04 | -48.8% | -6.3% | -0.50 | 22x | 100% | -2.2% |
| t2 | 60d | -0.0% | 0.14 | -44.4% | -3.6% | -0.35 | 7x | 100% | -3.0% |
| t3 | 5d | -11.6% | -0.25 | -67.3% | -10.3% | -0.74 | 49x | 100% | -5.2% |
| t3 | 20d | -7.2% | -0.10 | -59.0% | -5.7% | -0.46 | 22x | 100% | -2.5% |
| t3 | 60d | -2.9% | 0.04 | -52.9% | -1.5% | -0.15 | 8x | 100% | 0.7% |

