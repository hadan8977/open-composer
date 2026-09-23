# Signal card: resid_mom

- Source: `data/features/osap_price_broad:residualmom_252_21`; mode `rank`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:29:09+00:00
- Flags: {"predictive": false, "stable_years": false, "beats_shuffle": true, "timely": true, "tradable_tiers_20bp": ["t1", "t2"], "distinct_from_controls": false}

Coverage 2018-01-02..2026-09-17, 2100 names/day (92% of the universe).

| horizon | mean IC | t | hit | 2024+ | T1 | T2 | T3 | stale 252 |
|---|---|---|---|---|---|---|---|---|
| 1d | 0.010 | 2.7 | 54% | 0.015 | 0.016 | 0.011 | 0.007 | 0.006 |
| 5d | 0.011 | 1.2 | 54% | 0.019 | 0.015 | 0.011 | 0.008 | 0.006 |
| 20d | 0.007 | 0.5 | 55% | 0.020 | 0.010 | 0.006 | 0.005 | 0.002 |
| 60d | 0.005 | 0.2 | 54% | 0.031 | 0.004 | 0.005 | 0.005 | -0.007 |

t: non-overlapping samples. Decay (mean IC): 1d 0.010, 2d 0.012, 3d 0.012, 5d 0.011, 10d 0.010, 20d 0.007, 40d 0.007, 60d 0.005

Decile mean excess return per holding period (1 = lowest signal):

| horizon | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | -0.02% | -0.01% | -0.01% | -0.01% | 0.00% | -0.00% | 0.00% | 0.01% | 0.02% | 0.02% |
| 5d | -0.13% | -0.05% | -0.02% | -0.04% | 0.01% | 0.02% | 0.01% | 0.07% | 0.08% | 0.06% |
| 20d | -0.48% | -0.15% | -0.07% | -0.08% | 0.03% | 0.08% | 0.06% | 0.21% | 0.27% | 0.14% |
| 60d | -1.06% | -0.37% | -0.21% | -0.22% | 0.04% | 0.18% | 0.16% | 0.52% | 0.78% | 0.20% |

Shuffle placebo (10 seeds, 20d): IC -0.001..0.001; top-K excess -2.1%..-0.3%/yr.
Overlap with controls (mean rank corr): momentum_12_1 0.94, reversal_5d 0.01, size_dollar_adv_63 0.07, volatility_63 -0.01

Long-only book (top-K, overlapping cohorts), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| all | 5d | -11.0% | -0.03 | -86.0% | -11.4% | -0.35 | 12x | 100% | -33.2% |
| all | 20d | -7.4% | 0.06 | -80.8% | -7.5% | -0.23 | 8x | 100% | -21.3% |
| all | 60d | 0.9% | 0.23 | -68.7% | -0.0% | -0.00 | 5x | 100% | -5.9% |
| t1 | 5d | 24.7% | 0.72 | -54.2% | 18.0% | 0.58 | 13x | 100% | 39.8% |
| t1 | 20d | 26.8% | 0.76 | -52.0% | 19.4% | 0.64 | 7x | 100% | 40.0% |
| t1 | 60d | 23.0% | 0.70 | -57.1% | 15.7% | 0.55 | 4x | 100% | 37.0% |
| t2 | 5d | 8.2% | 0.40 | -67.0% | 6.4% | 0.21 | 15x | 100% | 11.7% |
| t2 | 20d | 6.6% | 0.36 | -66.7% | 4.8% | 0.16 | 9x | 100% | 11.7% |
| t2 | 60d | 5.8% | 0.34 | -64.1% | 3.4% | 0.12 | 5x | 100% | 5.5% |
| t3 | 5d | -6.9% | 0.04 | -81.3% | -6.1% | -0.21 | 15x | 100% | -20.7% |
| t3 | 20d | -5.1% | 0.08 | -77.1% | -4.5% | -0.16 | 10x | 100% | -20.9% |
| t3 | 60d | 1.1% | 0.22 | -67.4% | 0.6% | 0.02 | 6x | 100% | -7.8% |

