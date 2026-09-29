# Signal card: ftd_ftdsh_h60

- Source: `SELECT symbol, CAST(trade_date AS TIMESTAMP) AS trade_date, ftdsh AS value FROM read_parquet('/root/codex-test/open-composer/data/features/ftd/ftd.parquet') WHERE ftdsh IS NOT NULL`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 1500 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-29T23:24:28+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2019-02-01..2026-09-17, 1000 names/day (84% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.002 | 1.6 | 50% | 0.004 | 0.001 | 0.002 | n/a | -0.001 |
| 5d | 0.001 | 0.6 | 50% | 0.003 | -0.001 | 0.003 | n/a | -0.001 |
| 20d | -0.002 | -0.6 | 49% | 0.000 | -0.006 | 0.001 | n/a | -0.000 |
| 60d | 0.001 | -0.1 | 52% | 0.005 | -0.002 | 0.004 | n/a | -0.003 |

t: non-overlapping samples. Decay (mean IC): 1d 0.002, 2d 0.002, 3d 0.001, 5d 0.001, 10d -0.001, 20d -0.002, 40d -0.002, 60d 0.001

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | 0.01% | 0.01% | 0.00% | 0.01% | 0.02% | 0.00% | -0.00% | 0.01% | 0.01% | n/a |
| 5d | 0.07% | 0.05% | 0.01% | 0.08% | -0.01% | 0.05% | -0.02% | 0.07% | -0.09% | n/a |
| 20d | 0.30% | 0.23% | -0.01% | 0.35% | 0.43% | -0.04% | -0.10% | 0.00% | -0.50% | n/a |
| 60d | 0.64% | 0.46% | 0.19% | 0.33% | -0.07% | -0.33% | -0.13% | -0.50% | -3.16% | n/a |

Shuffle placebo (10 seeds, 60d): IC -0.002..0.001; top-K excess -2.7%..-1.4%/yr.
Overlap with controls (mean rank corr): momentum_12_1 -0.01, reversal_5d 0.00, size_dollar_adv_63 -0.05, volatility_63 -0.08

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -3.4% | -0.04 | -52.4% | -10.8% | -1.56 | 52x | 98% | -10.7% |
| all | 20d | 2.1% | 0.20 | -41.5% | -6.7% | -1.11 | 22x | 98% | -6.4% |
| all | 60d | 7.8% | 0.46 | -41.2% | -3.6% | -0.62 | 8x | 100% | -2.7% |
| t1 | 5d | -3.2% | -0.05 | -44.9% | -13.5% | -2.00 | 45x | 98% | -11.5% |
| t1 | 20d | 2.3% | 0.21 | -37.9% | -9.3% | -1.52 | 21x | 98% | -7.7% |
| t1 | 60d | 8.1% | 0.48 | -33.8% | -6.0% | -1.01 | 7x | 100% | -4.6% |
| t2 | 5d | -4.2% | -0.08 | -51.6% | -10.2% | -1.47 | 51x | 98% | -8.0% |
| t2 | 20d | 2.4% | 0.22 | -45.1% | -5.0% | -0.81 | 22x | 98% | -4.2% |
| t2 | 60d | 7.6% | 0.45 | -44.3% | -2.7% | -0.43 | 7x | 100% | 0.4% |
| t3 | 5d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 20d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 60d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |

