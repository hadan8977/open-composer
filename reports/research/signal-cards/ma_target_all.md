# Signal card: ma_target_all

- Source: `SELECT symbol, trade_date, 1.0 AS value FROM (SELECT symbol, CAST(trade_date AS TIMESTAMP) AS trade_date FROM read_parquet('/root/codex-test/open-composer/data/features/sec_8k_ma_announcements/*.parquet') WHERE is_target_rule AND is_first_for_cik_365d)`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-29T20:21:39+00:00
- Flags: {"car_t_ge_3": false, "beats_redated": true, "book_positive_20bp": false, "book_positive_20bp_recent": false}

596 events on 506 days, 584 stocks, from 2016-02-02.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | -0.02% | -0.2 | 51% | -0.25% | 0.03% | 0.08% | -0.07% |
| 5d | 0.01% | 0.1 | 48% | -0.37% | 0.10% | 0.15% | -0.07% |
| 20d | -0.75% | -2.4 | 42% | -1.36% | -1.97% | -0.48% | -0.62% |
| 60d | -1.33% | -1.6 | 40% | -2.21% | -3.11% | -1.51% | -0.63% |

Redated placebo (20 seeds, 20d): mean excess 2.07%..5.14%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | -15.1% | -0.86 | -84.1% | -12.6% | -0.66 | 85x | 65% | -29.8% |
| events | 20d | -8.3% | -0.52 | -64.7% | -16.2% | -0.89 | 43x | 96% | -21.9% |
| events | 60d | 1.4% | 0.17 | -37.0% | -10.1% | -0.64 | 15x | 99% | -15.0% |

