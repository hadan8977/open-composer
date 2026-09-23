# Signal card: high_52w

- Source: `data/features/daily_broad:dist_from_252d_high`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:06:08+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": false}

Coverage 2016-12-30..2026-09-17, 2181 names/day (96% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.018 | 4.2 | 55% | 0.022 | 0.016 | 0.014 | 0.019 | 0.013 |
| 5d | 0.025 | 2.6 | 57% | 0.031 | 0.019 | 0.018 | 0.028 | 0.021 |
| 20d | 0.041 | 2.4 | 62% | 0.046 | 0.029 | 0.031 | 0.046 | 0.029 |
| 60d | 0.068 | 3.7 | 70% | 0.067 | 0.042 | 0.052 | 0.079 | 0.042 |

t: non-overlapping samples. Decay (mean IC): 1d 0.018, 2d 0.021, 3d 0.023, 5d 0.025, 10d 0.031, 20d 0.041, 40d 0.055, 60d 0.068

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.03% | -0.02% | 0.01% | 0.01% | 0.01% | 0.01% | 0.01% | 0.01% | 0.01% | -0.01% |
| 5d | -0.23% | -0.08% | 0.03% | 0.05% | 0.05% | 0.07% | 0.04% | 0.06% | 0.03% | -0.03% |
| 20d | -1.00% | -0.32% | 0.10% | 0.26% | 0.21% | 0.25% | 0.21% | 0.21% | 0.13% | -0.05% |
| 60d | -2.77% | -0.90% | 0.16% | 0.60% | 0.74% | 0.70% | 0.53% | 0.54% | 0.37% | 0.05% |

Shuffle placebo (10 seeds, 20d): IC -0.000..0.001; top-K excess -2.7%..-0.4%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.53, reversal_5d 0.26, size_dollar_adv_63 0.17, volatility_63 -0.54

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -9.6% | -0.53 | -64.4% | -19.6% | -1.23 | 90x | 100% | -17.7% |
| all | 20d | 5.0% | 0.37 | -33.8% | -4.6% | -0.34 | 24x | 100% | -1.9% |
| all | 60d | 9.6% | 0.60 | -35.2% | -0.1% | -0.01 | 8x | 100% | 1.3% |
| t1 | 5d | -2.5% | -0.06 | -42.3% | -16.0% | -1.03 | 62x | 100% | -16.7% |
| t1 | 20d | 7.8% | 0.52 | -30.5% | -6.0% | -0.44 | 20x | 100% | -3.1% |
| t1 | 60d | 11.0% | 0.68 | -31.7% | -2.9% | -0.26 | 7x | 100% | -2.5% |
| t2 | 5d | -6.5% | -0.33 | -49.6% | -17.0% | -1.12 | 75x | 100% | -20.6% |
| t2 | 20d | 5.7% | 0.42 | -34.8% | -4.7% | -0.35 | 22x | 100% | -3.5% |
| t2 | 60d | 8.8% | 0.58 | -37.1% | -1.7% | -0.15 | 8x | 100% | -1.4% |
| t3 | 5d | -9.2% | -0.46 | -67.4% | -16.9% | -1.11 | 77x | 100% | -9.4% |
| t3 | 20d | 2.8% | 0.24 | -41.8% | -4.5% | -0.35 | 22x | 100% | 0.4% |
| t3 | 60d | 7.5% | 0.49 | -41.4% | 0.2% | 0.01 | 8x | 100% | 3.2% |

