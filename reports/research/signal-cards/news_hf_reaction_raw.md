# Signal card: news_hf_reaction_raw

- Source: `data/features/news_hf_reaction:news_return`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T07:05:10+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": false, "timely": false, "tradable_tiers_20bp": [], "distinct_from_controls": true}

Coverage 2024-01-02..2026-09-09, 381 names/day (17% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | -0.007 | -1.7 | 48% | -0.007 | -0.005 | -0.007 | -0.008 | 0.004 |
| 5d | -0.005 | -0.9 | 48% | -0.005 | -0.008 | -0.004 | 0.003 | -0.004 |
| 20d | -0.003 | -2.1 | 51% | -0.003 | -0.004 | -0.004 | 0.005 | -0.001 |
| 60d | 0.001 | -1.0 | 50% | 0.001 | 0.001 | -0.000 | 0.007 | -0.002 |

t: non-overlapping samples. Decay (mean IC): 1d -0.007, 2d -0.003, 3d -0.006, 5d -0.005, 10d -0.004, 20d -0.003, 40d 0.003, 60d 0.001

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.01% | 0.04% | 0.03% | 0.02% | 0.02% | 0.01% | -0.01% | -0.01% | -0.01% | -0.07% |
| 5d | -0.08% | 0.09% | 0.06% | 0.02% | 0.08% | 0.04% | 0.02% | -0.04% | 0.01% | -0.19% |
| 20d | -0.39% | 0.24% | 0.15% | -0.02% | 0.12% | 0.18% | 0.02% | 0.03% | 0.16% | -0.50% |
| 60d | -0.47% | 0.06% | 0.15% | -0.24% | -0.14% | 0.17% | 0.07% | 0.10% | 0.55% | -0.26% |

Shuffle placebo (10 seeds, 5d): IC -0.002..0.004; top-K excess -11.7%..-4.3%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.02, reversal_5d 0.25, size_dollar_adv_63 -0.01, volatility_63 0.01

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -15.5% | -0.41 | -37.7% | -26.0% | -1.61 | 96x | 100% | -26.0% |
| all | 20d | 1.8% | 0.21 | -32.0% | -7.7% | -0.56 | 24x | 100% | -7.7% |
| all | 60d | 10.7% | 0.50 | -31.0% | 0.5% | 0.04 | 8x | 100% | 0.5% |
| t1 | 5d | 1.1% | 0.18 | -33.5% | -13.9% | -1.20 | 87x | 100% | -13.9% |
| t1 | 20d | 18.2% | 0.75 | -28.9% | 1.6% | 0.16 | 22x | 100% | 1.6% |
| t1 | 60d | 21.7% | 0.87 | -27.7% | 4.3% | 0.46 | 7x | 100% | 4.3% |
| t2 | 5d | -10.4% | -0.36 | -30.0% | -22.6% | -2.74 | 93x | 99% | -22.6% |
| t2 | 20d | 6.3% | 0.38 | -25.7% | -6.0% | -0.91 | 23x | 100% | -6.0% |
| t2 | 60d | 12.9% | 0.66 | -24.9% | 0.0% | 0.00 | 8x | 100% | 0.0% |
| t3 | 5d | -16.4% | -0.65 | -38.7% | -25.4% | -2.89 | 87x | 99% | -25.4% |
| t3 | 20d | -1.5% | 0.04 | -28.1% | -10.4% | -1.77 | 22x | 100% | -10.4% |
| t3 | 60d | 6.6% | 0.41 | -28.2% | -2.5% | -0.50 | 7x | 100% | -2.5% |

