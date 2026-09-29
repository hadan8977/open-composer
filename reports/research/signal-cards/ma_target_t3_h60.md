# Signal card: ma_target_t3_h60

- Source: `WITH ev AS (SELECT symbol, CAST(trade_date AS TIMESTAMP) AS trade_date FROM read_parquet('/root/codex-test/open-composer/data/features/sec_8k_ma_announcements/*.parquet') WHERE is_target_rule AND is_first_for_cik_365d), u AS (SELECT symbol, CAST(month_end AS TIMESTAMP) AS month_end, adv_rank FROM read_parquet('/root/codex-test/open-composer/data/features/universe_broad/*.parquet')) SELECT ev.symbol, ev.trade_date, 1.0 AS value FROM ev ASOF JOIN u ON ev.symbol = u.symbol AND ev.trade_date >= u.month_end WHERE u.adv_rank BETWEEN 1501 AND 3000`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-29T20:28:29+00:00
- Flags: {"car_t_ge_3": false, "beats_redated": true, "book_positive_20bp": false, "book_positive_20bp_recent": false}

335 events on 301 days, 330 stocks, from 2016-02-08.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | -0.07% | -0.6 | 52% | -0.37% | n/a | n/a | -0.07% |
| 5d | -0.07% | -0.3 | 51% | -0.40% | n/a | n/a | -0.07% |
| 20d | -0.62% | -1.3 | 43% | -1.31% | n/a | n/a | -0.62% |
| 60d | -0.63% | -0.5 | 41% | -2.79% | n/a | n/a | -0.63% |

Redated placebo (20 seeds, 60d): mean excess 8.98%..14.79%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | -9.6% | -0.59 | -74.1% | -9.6% | -0.56 | 54x | 45% | -23.5% |
| events | 20d | -4.6% | -0.16 | -58.0% | -9.4% | -0.42 | 37x | 89% | -11.3% |
| events | 60d | 4.1% | 0.37 | -37.2% | -8.0% | -0.46 | 16x | 99% | -18.1% |

