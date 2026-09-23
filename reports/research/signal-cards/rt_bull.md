# Signal card: rt_bull

- Source: `data/features/reversal_trend_broad:rt_bull_signal`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:59:35+00:00
- Flags: {"car_t_ge_3": true, "beats_redated": true, "book_positive_20bp": false, "book_positive_20bp_recent": false}

9386 events on 1897 days, 3124 stocks, from 2016-02-11.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | -0.11% | -1.8 | 49% | -0.23% | -0.04% | -0.10% | -0.11% |
| 5d | -0.40% | -3.7 | 50% | -0.88% | -0.31% | -0.21% | -0.40% |
| 20d | -0.64% | -3.0 | 49% | -1.41% | -0.22% | -0.40% | -0.55% |
| 60d | -0.88% | -2.3 | 47% | -2.15% | 0.14% | -0.47% | -1.13% |

Redated placebo (20 seeds, 5d): mean excess -0.18%..0.11%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | -38.4% | -1.36 | -99.5% | -54.4% | -2.02 | 155x | 98% | -68.0% |
| events | 20d | -2.6% | -0.00 | -52.4% | -13.2% | -1.16 | 46x | 100% | -21.3% |
| events | 60d | 5.7% | 0.37 | -44.5% | -5.5% | -0.86 | 16x | 100% | -8.5% |

