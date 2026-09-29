# Signal card: ftd_ftdadv

- Source: `SELECT symbol, CAST(trade_date AS TIMESTAMP) AS trade_date, ftdadv AS value FROM read_parquet('/root/codex-test/open-composer/data/features/ftd/ftd.parquet') WHERE ftdadv IS NOT NULL`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 1500 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-29T23:26:52+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2019-02-01..2026-09-17, 1098 names/day (93% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.004 | 3.0 | 51% | 0.004 | 0.004 | 0.004 | n/a | 0.001 |
| 5d | 0.005 | 2.1 | 52% | 0.004 | 0.004 | 0.006 | n/a | 0.001 |
| 20d | 0.005 | 0.4 | 55% | 0.001 | 0.006 | 0.006 | n/a | 0.004 |
| 60d | 0.013 | 0.6 | 59% | 0.006 | 0.011 | 0.015 | n/a | 0.006 |

t: non-overlapping samples. Decay (mean IC): 1d 0.004, 2d 0.004, 3d 0.005, 5d 0.005, 10d 0.005, 20d 0.005, 40d 0.008, 60d 0.013

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | 0.00% | 0.01% | -0.00% | 0.02% | 0.02% | 0.04% | -0.00% | -0.01% | 0.03% | n/a |
| 5d | -0.01% | 0.06% | -0.00% | 0.13% | 0.18% | 0.26% | -0.01% | -0.02% | 0.05% | n/a |
| 20d | -0.02% | 0.18% | 0.19% | 0.40% | 0.57% | 0.78% | -0.06% | -0.05% | -0.44% | n/a |
| 60d | 0.08% | 0.27% | 0.15% | 0.84% | 0.24% | -0.35% | -0.19% | 0.10% | -1.36% | n/a |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess -3.6%..-2.1%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.00, reversal_5d 0.01, size_dollar_adv_63 -0.03, volatility_63 -0.13

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -3.1% | -0.04 | -49.5% | -10.7% | -1.61 | 58x | 98% | -11.8% |
| all | 20d | 3.5% | 0.27 | -39.0% | -5.4% | -0.87 | 23x | 98% | -6.0% |
| all | 60d | 8.3% | 0.49 | -41.7% | -3.3% | -0.54 | 8x | 100% | -1.3% |
| t1 | 5d | -2.3% | -0.00 | -44.0% | -12.5% | -1.97 | 46x | 98% | -13.8% |
| t1 | 20d | 2.7% | 0.23 | -35.9% | -8.9% | -1.47 | 22x | 98% | -9.5% |
| t1 | 60d | 7.3% | 0.44 | -35.9% | -6.6% | -1.14 | 7x | 100% | -3.4% |
| t2 | 5d | -4.5% | -0.09 | -52.1% | -10.5% | -1.61 | 54x | 98% | -8.9% |
| t2 | 20d | 1.1% | 0.16 | -44.6% | -6.2% | -1.04 | 22x | 98% | -2.0% |
| t2 | 60d | 7.5% | 0.44 | -44.7% | -2.8% | -0.45 | 7x | 100% | -0.4% |
| t3 | 5d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 20d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 60d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |

