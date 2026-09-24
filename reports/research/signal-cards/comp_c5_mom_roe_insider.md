# Signal card: comp_c5_mom_roe_insider

- Source: `composite: momentum_252_21x+1, roex+1, insider_cluster_60dx+1`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T11:09:34+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": true, "tradable_tiers_20bp": ["t1", "t2"], "distinct_from_controls": false}

Coverage 2017-01-03..2026-09-17, 1629 names/day (71% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.016 | 5.8 | 56% | 0.020 | 0.015 | 0.014 | 0.015 | 0.007 |
| 5d | 0.022 | 3.4 | 58% | 0.027 | 0.018 | 0.019 | 0.023 | 0.009 |
| 20d | 0.029 | 2.7 | 61% | 0.031 | 0.020 | 0.022 | 0.032 | 0.012 |
| 60d | 0.043 | 2.3 | 65% | 0.043 | 0.027 | 0.033 | 0.049 | 0.015 |

t: non-overlapping samples. Decay (mean IC): 1d 0.016, 2d 0.019, 3d 0.021, 5d 0.022, 10d 0.025, 20d 0.029, 40d 0.037, 60d 0.043

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.03% | -0.01% | -0.00% | 0.00% | -0.00% | 0.01% | 0.00% | 0.01% | 0.01% | 0.02% |
| 5d | -0.16% | -0.05% | -0.01% | 0.01% | -0.00% | 0.03% | 0.02% | 0.03% | 0.03% | 0.10% |
| 20d | -0.55% | -0.15% | -0.02% | 0.04% | -0.02% | 0.06% | 0.09% | 0.09% | 0.08% | 0.38% |
| 60d | -1.34% | -0.42% | -0.16% | -0.02% | -0.06% | 0.38% | 0.12% | 0.14% | 0.37% | 0.99% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess -0.8%..0.6%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.66, reversal_5d 0.03, size_dollar_adv_63 0.18, volatility_63 -0.21

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 12.3% | 0.54 | -54.4% | 5.0% | 0.33 | 15x | 100% | 14.6% |
| all | 20d | 14.3% | 0.60 | -49.0% | 6.8% | 0.47 | 9x | 100% | 15.4% |
| all | 60d | 16.4% | 0.68 | -44.9% | 8.4% | 0.63 | 5x | 100% | 13.5% |
| t1 | 5d | 16.9% | 0.73 | -37.7% | 4.0% | 0.33 | 13x | 100% | 11.0% |
| t1 | 20d | 17.3% | 0.75 | -36.9% | 4.4% | 0.37 | 7x | 100% | 10.7% |
| t1 | 60d | 16.1% | 0.72 | -35.3% | 3.3% | 0.30 | 4x | 100% | 7.7% |
| t2 | 5d | 14.0% | 0.64 | -42.7% | 4.8% | 0.40 | 14x | 100% | 5.4% |
| t2 | 20d | 14.6% | 0.66 | -42.2% | 5.3% | 0.47 | 8x | 100% | 7.8% |
| t2 | 60d | 16.7% | 0.74 | -41.5% | 7.0% | 0.67 | 5x | 100% | 10.3% |
| t3 | 5d | 11.0% | 0.52 | -48.3% | 5.5% | 0.44 | 15x | 100% | 8.9% |
| t3 | 20d | 11.8% | 0.55 | -49.0% | 6.2% | 0.52 | 9x | 100% | 8.3% |
| t3 | 60d | 13.4% | 0.60 | -48.7% | 7.5% | 0.70 | 5x | 100% | 8.0% |

