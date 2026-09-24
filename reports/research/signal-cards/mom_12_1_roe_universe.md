# Signal card: mom_12_1_roe_universe

- Source: `SELECT d.symbol, d.trade_date, d.momentum_252_21 AS value FROM read_parquet('data/features/daily_broad/*.parquet') d JOIN read_parquet('data/features/sec_fundamentals_daily/*.parquet', union_by_name=true) f USING (symbol, trade_date) WHERE f.roe IS NOT NULL`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T10:56:19+00:00
- Flags: {"predictive": false, "stable_years": true, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": ["t1", "t2"], "distinct_from_controls": false}

Coverage 2017-01-03..2026-09-17, 1629 names/day (71% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.015 | 3.8 | 56% | 0.021 | 0.018 | 0.014 | 0.014 | 0.008 |
| 5d | 0.017 | 1.9 | 55% | 0.028 | 0.018 | 0.014 | 0.019 | 0.010 |
| 20d | 0.016 | 1.1 | 57% | 0.030 | 0.014 | 0.009 | 0.021 | 0.010 |
| 60d | 0.022 | 0.7 | 59% | 0.044 | 0.016 | 0.012 | 0.029 | 0.008 |

t: non-overlapping samples. Decay (mean IC): 1d 0.015, 2d 0.016, 3d 0.017, 5d 0.017, 10d 0.017, 20d 0.016, 40d 0.019, 60d 0.022

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.03% | -0.01% | -0.01% | 0.00% | -0.00% | -0.00% | 0.01% | 0.01% | 0.01% | 0.03% |
| 5d | -0.16% | -0.05% | -0.04% | -0.00% | 0.00% | 0.01% | 0.02% | 0.04% | 0.05% | 0.14% |
| 20d | -0.53% | -0.12% | -0.12% | -0.01% | 0.01% | 0.02% | -0.02% | 0.08% | 0.17% | 0.51% |
| 60d | -1.08% | -0.48% | -0.39% | -0.20% | 0.01% | -0.02% | -0.09% | 0.04% | 0.52% | 1.70% |

Shuffle placebo (10 seeds, 20d): IC -0.000..0.001; top-K excess -1.3%..0.5%/yr.
Overlap with controls (mean rank corr): momentum_12_1 1.00, reversal_5d 0.03, size_dollar_adv_63 0.09, volatility_63 -0.07

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 15.5% | 0.55 | -58.0% | 14.2% | 0.42 | 14x | 100% | 17.6% |
| all | 20d | 17.5% | 0.58 | -56.8% | 15.8% | 0.48 | 8x | 100% | 18.3% |
| all | 60d | 18.7% | 0.61 | -59.3% | 16.3% | 0.52 | 5x | 100% | 20.2% |
| t1 | 5d | 25.7% | 0.75 | -51.8% | 17.0% | 0.58 | 12x | 100% | 40.4% |
| t1 | 20d | 29.0% | 0.82 | -49.8% | 19.4% | 0.68 | 6x | 100% | 43.1% |
| t1 | 60d | 25.7% | 0.77 | -52.8% | 16.3% | 0.61 | 4x | 100% | 39.7% |
| t2 | 5d | 17.2% | 0.60 | -52.7% | 11.8% | 0.44 | 15x | 100% | 17.9% |
| t2 | 20d | 16.2% | 0.58 | -52.5% | 11.0% | 0.42 | 8x | 100% | 17.1% |
| t2 | 60d | 16.2% | 0.58 | -51.1% | 10.7% | 0.43 | 5x | 100% | 10.4% |
| t3 | 5d | 4.0% | 0.29 | -67.8% | 1.9% | 0.08 | 17x | 100% | 4.1% |
| t3 | 20d | 6.5% | 0.36 | -65.0% | 4.2% | 0.18 | 9x | 100% | 5.4% |
| t3 | 60d | 10.2% | 0.45 | -61.7% | 7.4% | 0.35 | 5x | 100% | 10.7% |

