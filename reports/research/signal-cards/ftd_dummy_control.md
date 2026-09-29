# Signal card: ftd_dummy_control

- Source: `SELECT symbol, CAST(trade_date AS TIMESTAMP) AS trade_date, ftd_dummy AS value FROM read_parquet('/root/codex-test/open-composer/data/features/ftd/ftd.parquet') WHERE ftd_dummy IS NOT NULL`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 1500 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-29T23:31:42+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": true, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2019-02-01..2026-09-17, 1100 names/day (93% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.003 | 2.4 | 51% | 0.003 | 0.003 | 0.003 | n/a | 0.000 |
| 5d | 0.004 | 1.7 | 52% | 0.003 | 0.002 | 0.005 | n/a | -0.000 |
| 20d | 0.003 | -0.3 | 53% | -0.000 | 0.003 | 0.004 | n/a | 0.000 |
| 60d | 0.010 | 0.6 | 58% | 0.007 | 0.008 | 0.013 | n/a | 0.002 |

t: non-overlapping samples. Decay (mean IC): 1d 0.003, 2d 0.003, 3d 0.003, 5d 0.004, 10d 0.003, 20d 0.003, 40d 0.006, 60d 0.010

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | n/a | 0.01% | 0.00% | -0.02% | n/a | n/a | -0.00% | -0.00% | 0.04% | n/a |
| 5d | n/a | 0.03% | 0.02% | -0.06% | n/a | n/a | -0.02% | -0.01% | 0.07% | n/a |
| 20d | n/a | 0.15% | 0.09% | 0.17% | n/a | n/a | -0.07% | -0.08% | -0.41% | n/a |
| 60d | n/a | 0.35% | -0.05% | 0.52% | n/a | n/a | -0.16% | -0.02% | -1.27% | n/a |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess -4.5%..-2.6%/yr.
Overlap with controls (mean rank corr): momentum_12_1 -0.00, reversal_5d 0.01, size_dollar_adv_63 -0.06, volatility_63 -0.11

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -3.7% | -0.06 | -54.3% | -11.2% | -1.64 | 55x | 98% | -6.2% |
| all | 20d | 3.2% | 0.25 | -39.1% | -5.7% | -0.92 | 22x | 98% | -1.5% |
| all | 60d | 7.3% | 0.44 | -41.8% | -4.2% | -0.68 | 7x | 100% | -2.1% |
| t1 | 5d | -3.2% | -0.04 | -50.8% | -13.4% | -2.18 | 45x | 98% | -11.9% |
| t1 | 20d | 2.8% | 0.23 | -37.4% | -8.8% | -1.50 | 21x | 98% | -7.3% |
| t1 | 60d | 7.8% | 0.47 | -35.6% | -6.2% | -1.05 | 7x | 100% | -2.3% |
| t2 | 5d | -5.8% | -0.15 | -53.1% | -12.0% | -1.79 | 53x | 98% | -12.9% |
| t2 | 20d | 1.8% | 0.19 | -44.6% | -5.5% | -0.90 | 22x | 98% | -5.5% |
| t2 | 60d | 7.6% | 0.45 | -44.0% | -2.7% | -0.42 | 7x | 100% | -0.7% |
| t3 | 5d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 20d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 60d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |

