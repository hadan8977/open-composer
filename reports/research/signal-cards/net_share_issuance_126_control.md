# Signal card: net_share_issuance_126_control

- Source: `SELECT symbol, CAST(trade_date AS TIMESTAMP) AS trade_date, nsi126 AS value FROM read_parquet('/root/codex-test/open-composer/data/features/nsi/nsi.parquet') WHERE nsi126 IS NOT NULL`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 1500 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-29T22:22:56+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": ["t2"], "distinct_from_controls": true}

Coverage 2016-07-05..2026-09-17, 871 names/day (73% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.004 | 1.6 | 51% | 0.005 | 0.003 | 0.004 | n/a | 0.004 |
| 5d | 0.009 | 1.3 | 52% | 0.008 | 0.004 | 0.010 | n/a | 0.009 |
| 20d | 0.020 | 1.5 | 55% | 0.008 | 0.013 | 0.022 | n/a | 0.022 |
| 60d | 0.035 | 2.1 | 59% | 0.002 | 0.024 | 0.037 | n/a | 0.041 |

t: non-overlapping samples. Decay (mean IC): 1d 0.004, 2d 0.006, 3d 0.006, 5d 0.009, 10d 0.013, 20d 0.020, 40d 0.028, 60d 0.035

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | 0.01% | 0.01% | -0.00% | -0.01% | -0.01% | -0.01% | -0.00% | 0.00% | 0.00% | 0.01% |
| 5d | 0.04% | 0.03% | -0.02% | -0.05% | -0.03% | -0.03% | -0.02% | 0.01% | 0.02% | 0.05% |
| 20d | 0.11% | 0.10% | -0.11% | -0.14% | -0.03% | -0.11% | -0.08% | -0.00% | 0.11% | 0.17% |
| 60d | 0.18% | 0.27% | -0.25% | -0.38% | 0.11% | -0.17% | -0.11% | -0.15% | 0.19% | 0.31% |

Shuffle placebo (10 seeds, 20d): IC -0.002..0.001; top-K excess -2.1%..-0.9%/yr.
Overlap with controls (mean rank corr): momentum_12_1 -0.12, reversal_5d 0.01, size_dollar_adv_63 0.11, volatility_63 -0.20

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | 13.1% | 0.64 | -52.8% | 1.7% | 0.17 | 9x | 100% | 3.5% |
| all | 20d | 13.3% | 0.65 | -51.5% | 1.9% | 0.19 | 6x | 100% | 3.3% |
| all | 60d | 12.9% | 0.64 | -53.9% | 1.6% | 0.16 | 4x | 100% | 2.5% |
| t1 | 5d | 13.4% | 0.72 | -42.9% | -0.6% | -0.05 | 9x | 100% | -0.4% |
| t1 | 20d | 13.3% | 0.71 | -42.2% | -0.7% | -0.06 | 6x | 100% | -0.3% |
| t1 | 60d | 14.1% | 0.75 | -43.5% | 0.0% | 0.00 | 4x | 100% | 1.4% |
| t2 | 5d | 13.5% | 0.65 | -53.6% | 3.2% | 0.32 | 9x | 100% | 4.7% |
| t2 | 20d | 13.5% | 0.65 | -53.0% | 3.1% | 0.32 | 6x | 100% | 3.4% |
| t2 | 60d | 12.9% | 0.63 | -56.7% | 2.6% | 0.27 | 4x | 100% | 2.2% |
| t3 | 5d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 20d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 60d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |

