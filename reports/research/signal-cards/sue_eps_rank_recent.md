# Signal card: sue_eps_rank_recent

- Source: `data/features/sec_fundamentals_daily:sue_eps where days_since_report <= 5`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T08:29:02+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2016-01-29..2026-09-17, 112 names/day (5% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.002 | 0.6 | 52% | -0.002 | 0.018 | 0.013 | 0.005 | 0.003 |
| 5d | 0.007 | 0.7 | 55% | 0.012 | 0.029 | 0.021 | 0.009 | 0.011 |
| 20d | 0.016 | 1.2 | 55% | 0.023 | 0.005 | 0.018 | 0.007 | 0.010 |
| 60d | 0.014 | 1.4 | 56% | 0.041 | 0.005 | 0.021 | 0.006 | 0.020 |

t: non-overlapping samples. Decay (mean IC): 1d 0.002, 2d 0.003, 3d 0.004, 5d 0.007, 10d 0.008, 20d 0.016, 40d 0.017, 60d 0.014

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | 0.02% | 0.04% | -0.02% | 0.01% | -0.00% | -0.02% | -0.02% | -0.01% | -0.00% | -0.00% |
| 5d | 0.02% | 0.07% | -0.11% | 0.02% | 0.05% | -0.08% | -0.03% | 0.03% | 0.00% | 0.03% |
| 20d | 0.19% | 0.02% | -0.26% | -0.15% | -0.04% | -0.30% | -0.20% | 0.30% | 0.11% | 0.31% |
| 60d | -0.22% | -0.36% | -0.26% | 0.13% | -0.22% | -0.58% | -0.14% | 0.93% | -0.16% | 0.77% |

Shuffle placebo (10 seeds, 20d): IC -0.004..0.005; top-K excess -2.7%..-2.2%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.23, reversal_5d 0.06, size_dollar_adv_63 0.07, volatility_63 -0.08

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -1.5% | -0.08 | -44.4% | -3.0% | -0.49 | 28x | 38% | -4.1% |
| all | 20d | 1.3% | 0.18 | -38.4% | -2.4% | -0.21 | 8x | 63% | 0.9% |
| all | 60d | 4.4% | 0.67 | -17.5% | -8.0% | -0.51 | 2x | 100% | -7.0% |
| t1 | 5d | -1.0% | -0.11 | -23.2% | -1.2% | -0.19 | 16x | 24% | -2.6% |
| t1 | 20d | 1.7% | 0.35 | -13.9% | -5.0% | -0.44 | 4x | 48% | -5.9% |
| t1 | 60d | 2.6% | 0.84 | -5.0% | -13.4% | -0.76 | 1x | 97% | -15.1% |
| t2 | 5d | -3.1% | -0.28 | -38.6% | -2.2% | -0.37 | 20x | 29% | -5.8% |
| t2 | 20d | 0.7% | 0.14 | -31.6% | -2.7% | -0.24 | 6x | 53% | 0.6% |
| t2 | 60d | 3.2% | 0.68 | -11.2% | -9.5% | -0.57 | 2x | 99% | -9.9% |
| t3 | 5d | -3.0% | -0.25 | -43.6% | -3.1% | -0.46 | 19x | 28% | -6.2% |
| t3 | 20d | 0.3% | 0.08 | -31.4% | -3.0% | -0.25 | 5x | 52% | -1.2% |
| t3 | 60d | 2.9% | 0.60 | -11.5% | -8.1% | -0.45 | 2x | 98% | -7.0% |

