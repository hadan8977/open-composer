# Signal card: insider_cluster_buy_top500_weekly

- Source: `WITH src AS (SELECT symbol, trade_date, buyers_60d FROM read_parquet('data/features/insider_broad/*.parquet', union_by_name=true)), wk AS (SELECT max(trade_date) AS td FROM (SELECT DISTINCT trade_date FROM src) GROUP BY date_trunc('week', trade_date)) SELECT s.symbol, s.trade_date, 1.0 AS value FROM src s JOIN wk ON s.trade_date = wk.td WHERE s.buyers_60d >= 2`; mode `event`; lag 0 sessions; direction +1
- Universe: top 500 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-29T16:30:56+00:00
- Flags: {"car_t_ge_3": false, "beats_redated": true, "book_positive_20bp": true, "book_positive_20bp_recent": false}

9352 events on 556 days, 381 stocks, from 2016-01-29.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | 0.02% | 0.6 | 49% | 0.00% | 0.02% | n/a | n/a |
| 5d | 0.02% | 0.2 | 48% | -0.07% | 0.02% | n/a | n/a |
| 20d | 0.15% | 0.8 | 48% | -0.73% | 0.15% | n/a | n/a |
| 60d | -1.11% | -4.5 | 46% | -3.75% | -1.11% | n/a | n/a |

Redated placebo (20 seeds, 20d): mean excess -1.26%..-0.71%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | 11.9% | 0.52 | -47.7% | -0.1% | -0.01 | 14x | 100% | -7.0% |
| events | 20d | 12.3% | 0.54 | -46.0% | 0.0% | 0.00 | 11x | 100% | -11.9% |
| events | 60d | 7.5% | 0.41 | -44.8% | -5.2% | -0.45 | 8x | 100% | -16.5% |

