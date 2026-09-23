# Signal card: comp_c1_mom_quality

- Source: `composite: momentum_252_21x+1, idio_vol_63x-1, max_ret_1_21x-1, dist_from_252d_highx+1`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T14:20:14+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": true, "tradable_tiers_20bp": [], "distinct_from_controls": false}

Coverage 2017-01-03..2026-09-17, 2180 names/day (96% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.021 | 4.8 | 55% | 0.026 | 0.018 | 0.018 | 0.023 | 0.010 |
| 5d | 0.033 | 3.3 | 57% | 0.038 | 0.023 | 0.025 | 0.036 | 0.016 |
| 20d | 0.050 | 2.9 | 61% | 0.050 | 0.037 | 0.039 | 0.054 | 0.024 |
| 60d | 0.076 | 3.0 | 69% | 0.073 | 0.052 | 0.061 | 0.084 | 0.040 |

t: non-overlapping samples. Decay (mean IC): 1d 0.021, 2d 0.027, 3d 0.030, 5d 0.033, 10d 0.040, 20d 0.050, 40d 0.066, 60d 0.076

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.05% | -0.01% | 0.00% | 0.02% | 0.02% | 0.01% | 0.01% | 0.00% | 0.00% | -0.00% |
| 5d | -0.30% | -0.07% | 0.02% | 0.08% | 0.09% | 0.08% | 0.06% | 0.03% | 0.01% | -0.00% |
| 20d | -1.04% | -0.37% | 0.13% | 0.27% | 0.32% | 0.26% | 0.23% | 0.17% | 0.05% | -0.02% |
| 60d | -2.34% | -1.09% | 0.36% | 0.75% | 0.75% | 0.62% | 0.51% | 0.34% | 0.16% | -0.03% |

Shuffle placebo (10 seeds, 20d): IC -0.000..0.000; top-K excess -2.0%..-0.8%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.54, reversal_5d 0.08, size_dollar_adv_63 0.22, volatility_63 -0.80

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 1.2% | 0.16 | -27.5% | -9.0% | -0.55 | 37x | 100% | -6.5% |
| all | 20d | 5.6% | 0.55 | -26.5% | -4.7% | -0.29 | 16x | 100% | -2.2% |
| all | 60d | 7.7% | 0.69 | -29.7% | -2.7% | -0.18 | 7x | 100% | -1.0% |
| t1 | 5d | 5.0% | 0.42 | -28.2% | -9.0% | -0.62 | 28x | 100% | -11.9% |
| t1 | 20d | 9.3% | 0.69 | -29.3% | -5.0% | -0.36 | 13x | 100% | -8.0% |
| t1 | 60d | 10.5% | 0.75 | -32.9% | -3.8% | -0.30 | 6x | 100% | -6.2% |
| t2 | 5d | 4.4% | 0.41 | -31.6% | -6.5% | -0.43 | 31x | 100% | -5.6% |
| t2 | 20d | 7.6% | 0.64 | -31.7% | -3.4% | -0.24 | 14x | 100% | -1.5% |
| t2 | 60d | 9.1% | 0.74 | -32.2% | -2.0% | -0.15 | 6x | 100% | 0.0% |
| t3 | 5d | 2.1% | 0.23 | -33.7% | -5.9% | -0.37 | 30x | 100% | -4.5% |
| t3 | 20d | 4.3% | 0.39 | -38.1% | -3.7% | -0.24 | 14x | 100% | -1.8% |
| t3 | 60d | 6.4% | 0.51 | -41.1% | -1.6% | -0.11 | 6x | 100% | 0.1% |

