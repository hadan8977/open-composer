# Signal card: news_attention

- Source: `data/features/news_attention:attention_surge_5d`; mode `rank`; lag 0 sessions; direction -1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:49:03+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": false, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2024-01-02..2026-09-09, 783 names/day (36% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.001 | 0.3 | 51% | 0.001 | 0.001 | 0.002 | n/a | 0.003 |
| 5d | -0.003 | -0.8 | 47% | -0.003 | -0.003 | -0.002 | n/a | 0.000 |
| 20d | -0.003 | -0.2 | 47% | -0.003 | -0.004 | 0.000 | n/a | -0.004 |
| 60d | -0.002 | -1.5 | 46% | -0.002 | 0.001 | -0.005 | n/a | -0.005 |

t: non-overlapping samples. Decay (mean IC): 1d 0.001, 2d -0.000, 3d -0.001, 5d -0.003, 10d -0.007, 20d -0.003, 40d -0.002, 60d -0.002

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.02% | -0.01% | 0.01% | 0.02% | 0.01% | 0.00% | 0.01% | -0.01% | 0.01% | -0.18% |
| 5d | -0.04% | 0.00% | 0.11% | 0.03% | 0.04% | 0.01% | 0.00% | -0.01% | -0.01% | 0.00% |
| 20d | -0.16% | -0.01% | 0.22% | 0.22% | 0.05% | 0.14% | -0.13% | -0.03% | -0.16% | 0.45% |
| 60d | -0.10% | -0.23% | 0.22% | 0.27% | 0.43% | 0.25% | 0.13% | 0.43% | -0.35% | 1.27% |

Shuffle placebo (10 seeds, 20d): IC -0.002..0.002; top-K excess 1.0%..3.5%/yr.
Overlap with controls (mean rank corr): momentum_12_1 -0.04, reversal_5d -0.02, size_dollar_adv_63 -0.17, volatility_63 -0.04

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -3.6% | -0.11 | -27.9% | -15.7% | -2.45 | 90x | 100% | -15.7% |
| all | 20d | 11.2% | 0.71 | -22.4% | -1.6% | -0.30 | 23x | 100% | -1.6% |
| all | 60d | 12.5% | 0.79 | -21.0% | -0.6% | -0.10 | 7x | 100% | -0.6% |
| t1 | 5d | -3.7% | -0.13 | -22.1% | -21.1% | -3.19 | 82x | 100% | -21.1% |
| t1 | 20d | 11.3% | 0.72 | -19.9% | -6.7% | -1.19 | 21x | 100% | -6.7% |
| t1 | 60d | 13.7% | 0.88 | -18.8% | -4.7% | -0.77 | 7x | 100% | -4.7% |
| t2 | 5d | -0.3% | 0.07 | -26.8% | -13.4% | -2.31 | 85x | 100% | -13.4% |
| t2 | 20d | 10.8% | 0.69 | -22.3% | -3.0% | -0.67 | 23x | 100% | -3.0% |
| t2 | 60d | 12.8% | 0.80 | -21.2% | -1.2% | -0.28 | 7x | 100% | -1.2% |
| t3 | 5d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 20d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |
| t3 | 60d | 0.0% | n/a | 0.0% | 0.0% | n/a | 0x | 0% | 0.0% |

