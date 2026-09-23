# Signal card: rt_reclaim

- Source: `data/features/reversal_trend_broad:rt_recl_signal`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T13:04:10+00:00
- Flags: {"car_t_ge_3": false, "beats_redated": false, "book_positive_20bp": false, "book_positive_20bp_recent": false}

13289 events on 1932 days, 3805 stocks, from 2016-02-01.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | -0.04% | -0.6 | 48% | -0.32% | -0.06% | -0.02% | -0.09% |
| 5d | -0.14% | -1.0 | 48% | -0.71% | -0.12% | -0.00% | -0.23% |
| 20d | -0.81% | -3.3 | 48% | -1.66% | 0.04% | -0.72% | -0.94% |
| 60d | -2.29% | -5.5 | 46% | -4.25% | -0.16% | -1.11% | -3.21% |

Redated placebo (20 seeds, 5d): mean excess -0.73%..-0.37%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | -34.1% | -1.05 | -99.1% | -45.7% | -1.67 | 149x | 97% | -63.8% |
| events | 20d | -6.2% | -0.11 | -72.2% | -15.4% | -1.11 | 47x | 100% | -25.2% |
| events | 60d | 0.4% | 0.14 | -59.6% | -8.9% | -0.94 | 16x | 100% | -12.1% |

