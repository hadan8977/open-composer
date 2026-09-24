# Signal card: news_hf_reaction_5d_sum

- Source: `WITH r AS (SELECT symbol, trade_date, news_return FROM read_parquet('data/features/news_hf_reaction/*.parquet')), cal AS (SELECT DISTINCT symbol, trade_date FROM read_parquet('data/features/daily_broad/*.parquet')), dense AS (SELECT cal.symbol, cal.trade_date, COALESCE(r.news_return, 0) AS news_return FROM cal LEFT JOIN r USING (symbol, trade_date)) SELECT symbol, trade_date, SUM(news_return) OVER (PARTITION BY symbol ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS value FROM dense`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T07:17:39+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": false, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2016-01-29..2026-09-17, 2282 names/day (100% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | -0.001 | -0.9 | 51% | -0.001 | -0.004 | -0.000 | -0.001 | 0.000 |
| 5d | -0.003 | -2.5 | 49% | -0.003 | -0.009 | -0.003 | 0.002 | -0.002 |
| 20d | 0.000 | 0.1 | 50% | 0.000 | -0.003 | -0.000 | 0.001 | 0.001 |
| 60d | 0.003 | -0.5 | 57% | 0.003 | 0.002 | 0.002 | 0.004 | -0.001 |

t: non-overlapping samples. Decay (mean IC): 1d -0.001, 2d -0.003, 3d -0.003, 5d -0.003, 10d -0.001, 20d 0.000, 40d 0.005, 60d 0.003

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | 0.01% | 0.00% | 0.02% | 0.42% | 0.01% | -0.00% | -0.04% | -0.00% | -0.00% | -0.02% |
| 5d | 0.02% | 0.03% | 0.02% | -0.08% | 0.00% | -0.00% | -0.03% | 0.01% | 0.04% | -0.05% |
| 20d | 0.04% | 0.05% | 0.08% | -1.03% | -0.04% | 0.00% | -0.40% | 0.13% | 0.03% | -0.06% |
| 60d | 0.08% | -0.06% | -0.37% | -2.78% | -0.07% | -0.01% | -0.35% | 0.20% | 0.13% | 0.46% |

Shuffle placebo (10 seeds, 5d): IC -0.001..0.002; top-K excess -7.7%..-6.2%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.02, reversal_5d 0.24, size_dollar_adv_63 0.02, volatility_63 0.01

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -6.9% | -0.12 | -70.2% | -15.9% | -1.10 | 48x | 100% | -35.9% |
| all | 20d | 0.1% | 0.14 | -48.3% | -8.8% | -0.73 | 17x | 100% | -15.8% |
| all | 60d | 5.0% | 0.32 | -44.1% | -4.3% | -0.40 | 6x | 100% | -3.3% |
| t1 | 5d | 6.2% | 0.36 | -41.9% | -6.3% | -0.57 | 37x | 100% | -18.0% |
| t1 | 20d | 14.5% | 0.66 | -34.6% | 1.1% | 0.11 | 16x | 100% | 2.8% |
| t1 | 60d | 16.3% | 0.74 | -36.8% | 2.6% | 0.29 | 6x | 100% | 9.1% |
| t2 | 5d | -3.1% | 0.00 | -55.9% | -13.0% | -1.30 | 50x | 100% | -24.2% |
| t2 | 20d | 5.2% | 0.33 | -47.6% | -5.0% | -0.58 | 20x | 100% | -8.9% |
| t2 | 60d | 10.6% | 0.54 | -47.7% | -0.2% | -0.02 | 7x | 100% | 1.1% |
| t3 | 5d | -8.6% | -0.20 | -77.9% | -16.3% | -1.34 | 47x | 100% | -32.5% |
| t3 | 20d | -2.9% | 0.02 | -63.7% | -10.4% | -1.11 | 19x | 100% | -20.1% |
| t3 | 60d | 3.3% | 0.25 | -53.7% | -4.4% | -0.56 | 7x | 100% | -8.1% |

