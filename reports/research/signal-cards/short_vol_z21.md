# Signal card: short_vol_z21

- Source: `data/features/short_volume_broad:short_volume_ratio_zscore_21`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:45:13+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": true, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2018-08-03..2026-09-17, 2191 names/day (96% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.002 | 2.3 | 52% | 0.002 | 0.003 | 0.003 | 0.000 | 0.000 |
| 5d | 0.002 | 1.1 | 52% | 0.003 | 0.002 | 0.003 | 0.001 | 0.001 |
| 20d | 0.001 | -1.8 | 52% | 0.002 | 0.000 | 0.003 | 0.000 | -0.000 |
| 60d | 0.001 | -1.4 | 51% | 0.002 | 0.003 | -0.000 | 0.001 | 0.000 |

t: non-overlapping samples. Decay (mean IC): 1d 0.002, 2d 0.002, 3d 0.001, 5d 0.002, 10d 0.003, 20d 0.001, 40d 0.000, 60d 0.001

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | 0.00% | -0.00% | -0.01% | -0.01% | -0.00% | -0.01% | 0.00% | 0.00% | 0.01% | 0.01% |
| 5d | 0.01% | -0.01% | -0.02% | -0.00% | -0.01% | -0.00% | -0.01% | 0.00% | 0.03% | 0.01% |
| 20d | -0.03% | -0.03% | -0.04% | 0.00% | 0.00% | 0.01% | 0.00% | 0.04% | 0.04% | 0.01% |
| 60d | 0.01% | -0.04% | -0.06% | 0.02% | -0.05% | 0.01% | -0.06% | 0.11% | 0.10% | -0.04% |

Shuffle placebo (10 seeds, 5d): IC -0.001..0.001; top-K excess -13.1%..-8.0%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.00, reversal_5d -0.07, size_dollar_adv_63 0.00, volatility_63 0.00

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -11.0% | -0.36 | -67.7% | -18.7% | -3.66 | 99x | 100% | -17.8% |
| all | 20d | 3.1% | 0.25 | -43.1% | -4.0% | -1.46 | 25x | 100% | -4.3% |
| all | 60d | 6.1% | 0.37 | -42.9% | -1.2% | -0.61 | 8x | 100% | -1.5% |
| t1 | 5d | -2.0% | 0.03 | -51.0% | -14.0% | -2.94 | 91x | 100% | -13.3% |
| t1 | 20d | 8.8% | 0.49 | -37.6% | -3.8% | -1.48 | 24x | 100% | -4.4% |
| t1 | 60d | 11.6% | 0.60 | -37.7% | -1.2% | -0.57 | 8x | 100% | -1.7% |
| t2 | 5d | -8.6% | -0.26 | -60.5% | -17.1% | -3.88 | 96x | 100% | -19.8% |
| t2 | 20d | 4.3% | 0.30 | -43.2% | -4.0% | -1.61 | 25x | 100% | -3.0% |
| t2 | 60d | 6.9% | 0.40 | -43.7% | -1.5% | -0.80 | 8x | 100% | -1.8% |
| t3 | 5d | -14.0% | -0.46 | -76.4% | -19.4% | -3.57 | 97x | 100% | -14.8% |
| t3 | 20d | -1.1% | 0.08 | -52.6% | -5.5% | -1.93 | 25x | 100% | -4.1% |
| t3 | 60d | 3.6% | 0.27 | -47.2% | -0.9% | -0.42 | 8x | 100% | 0.7% |

