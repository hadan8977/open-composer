# Signal card: insider_cluster_buy

- Source: `SELECT symbol, trade_date, 1.0 AS value FROM read_parquet('data/features/insider_broad/*.parquet', union_by_name=true) WHERE days_since_last_visible_buy = 0 AND buyers_60d >= 2`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:54:28+00:00
- Flags: {"car_t_ge_3": true, "beats_redated": true, "book_positive_20bp": true, "book_positive_20bp_recent": true}

15493 events on 2605 days, 2184 stocks, from 2016-01-29.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | 0.07% | 2.0 | 49% | 0.07% | -0.05% | 0.08% | 0.06% |
| 5d | 0.24% | 3.3 | 50% | 0.10% | -0.18% | 0.21% | 0.24% |
| 20d | 0.78% | 5.0 | 50% | 0.45% | 0.53% | 0.19% | 1.00% |
| 60d | 1.53% | 5.5 | 49% | 0.56% | 0.18% | -0.39% | 2.43% |

Redated placebo (20 seeds, 20d): mean excess -0.75%..-0.41%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | 0.3% | 0.16 | -63.5% | -7.9% | -0.48 | 99x | 100% | -9.2% |
| events | 20d | 11.7% | 0.54 | -56.1% | 2.4% | 0.19 | 32x | 100% | 0.6% |
| events | 60d | 12.0% | 0.56 | -53.2% | 2.4% | 0.23 | 11x | 100% | 0.5% |

