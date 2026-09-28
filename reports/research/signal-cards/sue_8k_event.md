# Signal card: sue_8k_event

- Source: `data/features/sue_8k_visible:value`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-28T06:32:15+00:00
- Flags: {"car_t_ge_3": false, "beats_redated": false, "book_positive_20bp": false, "book_positive_20bp_recent": false}

1032 events on 303 days, 570 stocks, from 2024-01-12.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | -0.16% | -1.4 | 49% | -0.16% | -0.03% | -0.23% | 0.13% |
| 5d | -0.43% | -1.9 | 50% | -0.43% | -0.14% | -0.28% | 0.00% |
| 20d | 0.48% | 1.1 | 50% | 0.48% | 0.48% | 0.48% | 1.41% |
| 60d | 2.01% | 1.8 | 48% | 2.01% | 2.53% | 0.84% | 4.82% |

Redated placebo (20 seeds, 20d): mean excess 0.44%..1.95%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | -29.1% | -0.87 | -63.9% | -41.9% | -1.68 | 125x | 86% | -41.9% |
| events | 20d | 12.4% | 0.61 | -25.4% | -0.1% | -0.01 | 57x | 100% | -0.1% |
| events | 60d | 16.4% | 0.93 | -19.9% | 2.3% | 0.34 | 16x | 100% | 2.3% |

