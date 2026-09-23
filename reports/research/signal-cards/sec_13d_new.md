# Signal card: sec_13d_new

- Source: `SELECT issuer_symbol AS symbol, visible_session AS trade_date, 1.0 AS value FROM read_parquet('data/features/sec_13d/*.parquet') WHERE is_new_13d`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-23T12:56:55+00:00
- Flags: {"car_t_ge_3": false, "beats_redated": false, "book_positive_20bp": false, "book_positive_20bp_recent": false}

711 events on 607 days, 499 stocks, from 2016-02-08.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | -0.13% | -0.4 | 46% | -1.24% | -0.71% | -0.32% | 0.25% |
| 5d | -0.28% | -0.6 | 45% | -1.77% | -1.75% | -1.10% | 1.32% |
| 20d | -0.56% | -0.8 | 47% | -3.46% | -3.07% | -0.85% | 1.03% |
| 60d | -1.59% | -1.4 | 44% | -6.47% | -1.04% | -1.49% | -1.20% |

Redated placebo (20 seeds, 20d): mean excess -2.26%..1.21%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | -42.3% | -0.41 | -99.8% | -31.5% | -0.49 | 94x | 71% | -87.3% |
| events | 20d | -8.0% | 0.04 | -89.9% | -11.7% | -0.31 | 44x | 100% | -31.9% |
| events | 60d | 3.8% | 0.28 | -62.1% | -4.1% | -0.21 | 15x | 100% | -20.6% |

