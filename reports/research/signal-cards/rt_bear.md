# Signal card: rt_bear

- Source: `data/features/reversal_trend_broad:rt_bear_signal`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T13:07:02+00:00
- Flags: {"car_t_ge_3": false, "beats_redated": true, "book_positive_20bp": false, "book_positive_20bp_recent": false}

16820 events on 2349 days, 3895 stocks, from 2016-02-11.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | -0.13% | -2.7 | 49% | -0.14% | -0.04% | -0.03% | -0.16% |
| 5d | -0.25% | -2.5 | 49% | -0.29% | -0.06% | 0.07% | -0.43% |
| 20d | -0.48% | -2.5 | 48% | -0.55% | -0.38% | 0.01% | -0.54% |
| 60d | -1.33% | -4.3 | 47% | -1.51% | -0.37% | -0.53% | -1.55% |

Redated placebo (20 seeds, 5d): mean excess 0.02%..0.25%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | -28.4% | -1.09 | -97.2% | -42.1% | -2.03 | 151x | 100% | -41.8% |
| events | 20d | -1.6% | 0.04 | -52.5% | -12.3% | -1.16 | 41x | 100% | -8.1% |
| events | 60d | 4.6% | 0.32 | -45.2% | -6.2% | -0.85 | 14x | 100% | -4.0% |

