# Signal card: comp_c2_mom_quality_insider

- Source: `composite: momentum_252_21x+1, idio_vol_63x-1, max_ret_1_21x-1, dist_from_252d_highx+1, insider_cluster_60dx+1`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T14:32:26+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": true, "tradable_tiers_20bp": [], "distinct_from_controls": false}

Coverage 2017-01-03..2026-09-17, 2180 names/day (96% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.021 | 4.8 | 55% | 0.026 | 0.018 | 0.018 | 0.022 | 0.009 |
| 5d | 0.032 | 3.2 | 57% | 0.038 | 0.023 | 0.025 | 0.036 | 0.016 |
| 20d | 0.049 | 2.9 | 61% | 0.049 | 0.036 | 0.039 | 0.054 | 0.024 |
| 60d | 0.076 | 2.9 | 69% | 0.072 | 0.050 | 0.060 | 0.083 | 0.039 |

t: non-overlapping samples. Decay (mean IC): 1d 0.021, 2d 0.026, 3d 0.029, 5d 0.032, 10d 0.039, 20d 0.049, 40d 0.065, 60d 0.076

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.05% | -0.02% | 0.00% | 0.02% | 0.02% | 0.01% | 0.01% | 0.00% | 0.00% | -0.00% |
| 5d | -0.30% | -0.08% | 0.03% | 0.09% | 0.08% | 0.08% | 0.06% | 0.03% | 0.01% | -0.00% |
| 20d | -1.03% | -0.40% | 0.19% | 0.27% | 0.32% | 0.25% | 0.23% | 0.16% | 0.05% | -0.02% |
| 60d | -2.31% | -1.15% | 0.42% | 0.77% | 0.71% | 0.65% | 0.51% | 0.33% | 0.13% | -0.03% |

Shuffle placebo (10 seeds, 20d): IC -0.000..0.001; top-K excess -2.1%..-0.3%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.54, reversal_5d 0.08, size_dollar_adv_63 0.21, volatility_63 -0.80

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 1.8% | 0.21 | -28.1% | -8.4% | -0.54 | 35x | 100% | -5.1% |
| all | 20d | 6.1% | 0.57 | -26.9% | -4.3% | -0.28 | 15x | 100% | -1.1% |
| all | 60d | 7.6% | 0.67 | -30.9% | -2.7% | -0.19 | 7x | 100% | -0.3% |
| t1 | 5d | 4.6% | 0.38 | -29.1% | -9.5% | -0.66 | 29x | 100% | -11.7% |
| t1 | 20d | 9.4% | 0.70 | -29.4% | -4.9% | -0.36 | 13x | 100% | -7.9% |
| t1 | 60d | 10.7% | 0.77 | -32.7% | -3.7% | -0.29 | 6x | 100% | -5.9% |
| t2 | 5d | 3.8% | 0.35 | -32.8% | -7.1% | -0.48 | 31x | 100% | -4.9% |
| t2 | 20d | 7.0% | 0.59 | -32.0% | -4.0% | -0.29 | 14x | 100% | -1.2% |
| t2 | 60d | 8.8% | 0.71 | -32.8% | -2.3% | -0.18 | 6x | 100% | 0.3% |
| t3 | 5d | 1.8% | 0.21 | -34.0% | -6.2% | -0.40 | 30x | 100% | -4.7% |
| t3 | 20d | 4.1% | 0.37 | -39.2% | -3.9% | -0.26 | 14x | 100% | -2.2% |
| t3 | 60d | 6.4% | 0.50 | -42.1% | -1.6% | -0.11 | 6x | 100% | -0.3% |

