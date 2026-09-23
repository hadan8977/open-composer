# Signal card: insider_new_buy

- Source: `SELECT symbol, trade_date, 1.0 AS value FROM read_parquet('data/features/insider_broad/*.parquet', union_by_name=true) WHERE days_since_last_visible_buy = 0`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:51:54+00:00
- Flags: {"car_t_ge_3": true, "beats_redated": true, "book_positive_20bp": false, "book_positive_20bp_recent": false}

27607 events on 2639 days, 3137 stocks, from 2016-01-29.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | 0.05% | 2.1 | 49% | 0.07% | 0.01% | 0.06% | 0.06% |
| 5d | 0.13% | 2.4 | 49% | 0.14% | -0.07% | 0.07% | 0.20% |
| 20d | 0.37% | 3.3 | 49% | 0.23% | 0.38% | 0.06% | 0.35% |
| 60d | 1.02% | 5.0 | 48% | 0.77% | 0.64% | 0.19% | 1.05% |

Redated placebo (20 seeds, 20d): mean excess -0.75%..-0.45%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | -6.1% | -0.10 | -64.9% | -15.3% | -1.32 | 103x | 100% | -12.4% |
| events | 20d | 7.3% | 0.40 | -56.7% | -2.1% | -0.23 | 34x | 100% | -3.4% |
| events | 60d | 11.3% | 0.55 | -52.1% | 1.4% | 0.18 | 11x | 100% | 1.5% |

