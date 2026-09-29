# Signal card: net_share_issuance_252

- Source: `SELECT symbol, CAST(trade_date AS TIMESTAMP) AS trade_date, nsi252 AS value FROM read_parquet('/root/codex-test/open-composer/data/features/nsi/nsi.parquet') WHERE nsi252 IS NOT NULL`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 1500 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-29T22:18:56+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": ["t2"], "distinct_from_controls": true}

Coverage 2017-01-03..2026-09-17, 850 names/day (71% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.004 | 1.5 | 51% | 0.005 | 0.003 | 0.004 | n/a | 0.005 |
| 5d | 0.008 | 1.3 | 51% | 0.009 | 0.005 | 0.009 | n/a | 0.009 |
| 20d | 0.019 | 1.7 | 55% | 0.011 | 0.013 | 0.020 | n/a | 0.022 |
| 60d | 0.033 | 1.8 | 59% | 0.005 | 0.026 | 0.032 | n/a | 0.039 |

t: non-overlapping samples. Decay (mean IC): 1d 0.004, 2d 0.005, 3d 0.006, 5d 0.008, 10d 0.013, 20d 0.019, 40d 0.027, 60d 0.033

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | 0.00% | 0.01% | -0.01% | -0.01% | -0.00% | -0.01% | -0.00% | -0.00% | 0.01% | 0.01% |
| 5d | -0.00% | 0.04% | -0.02% | -0.05% | -0.02% | -0.03% | -0.01% | 0.00% | 0.04% | 0.04% |
| 20d | -0.01% | 0.11% | -0.06% | -0.18% | -0.05% | -0.11% | 0.00% | 0.03% | 0.13% | 0.15% |
| 60d | 0.13% | 0.17% | -0.11% | -0.55% | -0.17% | -0.07% | 0.03% | 0.06% | 0.10% | 0.43% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.002; top-K excess -1.4%..-0.4%/yr.
Overlap with controls (mean rank corr): momentum_12_1 -0.10, reversal_5d 0.01, size_dollar_adv_63 0.11, volatility_63 -0.20

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 14.1% | 0.66 | -53.9% | 3.4% | 0.34 | 5x | 100% | 6.4% |
| all | 20d | 13.1% | 0.63 | -52.4% | 2.6% | 0.26 | 4x | 100% | 5.7% |
| all | 60d | 12.5% | 0.61 | -52.1% | 1.9% | 0.20 | 3x | 100% | 3.8% |
| t1 | 5d | 13.7% | 0.73 | -42.6% | 0.0% | 0.00 | 5x | 100% | -0.9% |
| t1 | 20d | 14.3% | 0.76 | -42.6% | 0.5% | 0.05 | 3x | 100% | -0.1% |
| t1 | 60d | 15.1% | 0.79 | -43.0% | 1.3% | 0.12 | 2x | 100% | 0.3% |
| t2 | 5d | 11.6% | 0.56 | -58.8% | 2.5% | 0.24 | 6x | 100% | 2.5% |
| t2 | 20d | 10.5% | 0.52 | -58.9% | 1.6% | 0.15 | 4x | 100% | 1.6% |
| t2 | 60d | 10.8% | 0.54 | -57.2% | 1.8% | 0.18 | 3x | 100% | 0.1% |
| t3 | 5d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 20d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 60d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |

