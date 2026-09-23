# Signal card: comp_c3_mom_52w

- Source: `composite: momentum_252_21x+1, dist_from_252d_highx+1`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T14:41:51+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": true, "tradable_tiers_20bp": ["t1", "t2"], "distinct_from_controls": false}

Coverage 2017-01-03..2026-09-17, 2180 names/day (96% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.019 | 4.8 | 56% | 0.025 | 0.020 | 0.017 | 0.019 | 0.007 |
| 5d | 0.025 | 2.6 | 57% | 0.034 | 0.021 | 0.019 | 0.027 | 0.009 |
| 20d | 0.033 | 2.1 | 62% | 0.043 | 0.024 | 0.025 | 0.038 | 0.008 |
| 60d | 0.053 | 2.2 | 69% | 0.062 | 0.032 | 0.039 | 0.062 | 0.006 |

t: non-overlapping samples. Decay (mean IC): 1d 0.019, 2d 0.022, 3d 0.023, 5d 0.025, 10d 0.028, 20d 0.033, 40d 0.044, 60d 0.053

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.04% | -0.02% | 0.00% | 0.00% | 0.00% | 0.00% | 0.01% | 0.02% | 0.01% | 0.01% |
| 5d | -0.22% | -0.07% | -0.00% | -0.00% | 0.01% | 0.02% | 0.06% | 0.08% | 0.07% | 0.07% |
| 20d | -0.78% | -0.29% | -0.04% | -0.04% | 0.02% | 0.12% | 0.26% | 0.30% | 0.21% | 0.23% |
| 60d | -1.89% | -0.85% | -0.27% | -0.11% | -0.16% | 0.40% | 0.80% | 0.75% | 0.63% | 0.72% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.000; top-K excess -2.8%..-0.5%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.86, reversal_5d 0.17, size_dollar_adv_63 0.15, volatility_63 -0.34

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -3.3% | 0.02 | -56.0% | -10.3% | -0.49 | 64x | 100% | -4.0% |
| all | 20d | 9.1% | 0.45 | -44.0% | 1.8% | 0.09 | 20x | 100% | 12.2% |
| all | 60d | 13.7% | 0.60 | -42.8% | 6.0% | 0.34 | 7x | 100% | 14.0% |
| t1 | 5d | 8.2% | 0.45 | -37.1% | -4.1% | -0.24 | 39x | 100% | 2.3% |
| t1 | 20d | 13.7% | 0.65 | -32.6% | 0.9% | 0.06 | 15x | 100% | 11.5% |
| t1 | 60d | 15.9% | 0.72 | -33.1% | 3.0% | 0.21 | 6x | 100% | 9.8% |
| t2 | 5d | 0.9% | 0.16 | -47.8% | -7.9% | -0.45 | 49x | 100% | -12.1% |
| t2 | 20d | 9.4% | 0.50 | -41.8% | 0.3% | 0.02 | 18x | 100% | 4.3% |
| t2 | 60d | 12.3% | 0.60 | -40.5% | 3.0% | 0.21 | 7x | 100% | 7.4% |
| t3 | 5d | -2.7% | 0.01 | -53.3% | -8.6% | -0.52 | 54x | 100% | 0.3% |
| t3 | 20d | 6.7% | 0.39 | -45.8% | 0.6% | 0.04 | 18x | 100% | 8.1% |
| t3 | 60d | 11.0% | 0.55 | -44.4% | 4.6% | 0.34 | 7x | 100% | 10.0% |

