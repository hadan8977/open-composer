# Signal card: roe

- Source: `data/features/sec_fundamentals_daily:roe`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T09:17:57+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": ["t2"], "distinct_from_controls": true}

Coverage 2016-01-29..2026-09-17, 1622 names/day (71% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.009 | 4.8 | 54% | 0.010 | 0.005 | 0.007 | 0.011 | 0.009 |
| 5d | 0.016 | 3.7 | 55% | 0.015 | 0.008 | 0.013 | 0.019 | 0.016 |
| 20d | 0.026 | 3.0 | 59% | 0.021 | 0.012 | 0.022 | 0.031 | 0.029 |
| 60d | 0.041 | 3.3 | 67% | 0.026 | 0.020 | 0.033 | 0.049 | 0.047 |

t: non-overlapping samples. Decay (mean IC): 1d 0.009, 2d 0.012, 3d 0.014, 5d 0.016, 10d 0.020, 20d 0.026, 40d 0.034, 60d 0.041

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.01% | 0.01% | -0.01% | -0.01% | -0.01% | 0.00% | 0.00% | 0.00% | 0.01% | 0.00% |
| 5d | -0.04% | 0.03% | -0.04% | -0.02% | -0.03% | 0.01% | 0.02% | 0.02% | 0.04% | 0.00% |
| 20d | -0.09% | 0.12% | -0.16% | -0.13% | -0.12% | 0.04% | 0.06% | 0.08% | 0.17% | 0.03% |
| 60d | 0.02% | 0.24% | -0.50% | -0.46% | -0.28% | 0.03% | 0.07% | 0.15% | 0.46% | 0.25% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess -1.1%..0.4%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.02, reversal_5d 0.02, size_dollar_adv_63 0.19, volatility_63 -0.28

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 7.2% | 0.40 | -55.8% | -2.4% | -0.18 | 5x | 100% | -13.1% |
| all | 20d | 7.0% | 0.40 | -59.1% | -2.6% | -0.21 | 4x | 100% | -15.6% |
| all | 60d | 8.7% | 0.46 | -48.5% | -1.2% | -0.10 | 3x | 100% | -10.5% |
| t1 | 5d | 19.4% | 1.03 | -34.7% | 3.9% | 0.53 | 3x | 100% | -1.7% |
| t1 | 20d | 19.1% | 1.03 | -34.7% | 3.6% | 0.48 | 3x | 100% | -2.3% |
| t1 | 60d | 18.0% | 0.99 | -34.4% | 2.7% | 0.35 | 2x | 100% | -1.6% |
| t2 | 5d | 16.1% | 0.75 | -46.8% | 4.6% | 0.53 | 5x | 100% | 4.2% |
| t2 | 20d | 16.0% | 0.75 | -47.6% | 4.5% | 0.54 | 4x | 100% | 4.7% |
| t2 | 60d | 17.2% | 0.80 | -47.0% | 5.5% | 0.69 | 3x | 100% | 7.1% |
| t3 | 5d | -2.3% | 0.06 | -76.5% | -9.2% | -0.67 | 6x | 100% | -27.7% |
| t3 | 20d | -1.6% | 0.09 | -75.8% | -8.5% | -0.65 | 5x | 100% | -28.0% |
| t3 | 60d | 0.8% | 0.17 | -71.8% | -6.3% | -0.52 | 4x | 100% | -19.6% |

