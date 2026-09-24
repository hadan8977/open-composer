# Signal card: news_hf_reaction_event_p90

- Source: `data/features/news_hf_reaction:news_return`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T07:22:01+00:00
- Flags: {"car_t_ge_3": false, "beats_redated": true, "book_positive_20bp": false, "book_positive_20bp_recent": false}

20448 events on 674 days, 2560 stocks, from 2024-01-02.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | -0.11% | -1.6 | 48% | -0.11% | 0.23% | -0.08% | -0.35% |
| 5d | -0.29% | -1.9 | 47% | -0.29% | -0.05% | -0.18% | -0.47% |
| 20d | -0.76% | -2.9 | 46% | -0.76% | 0.70% | -0.61% | -1.92% |
| 60d | -0.40% | -0.9 | 44% | -0.40% | 3.39% | 0.18% | -3.85% |

Redated placebo (20 seeds, 5d): mean excess 0.17%..0.40%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | -23.1% | -0.66 | -53.0% | -34.8% | -1.89 | 120x | 100% | -34.8% |
| events | 20d | -0.2% | 0.14 | -33.1% | -9.5% | -0.65 | 35x | 100% | -9.5% |
| events | 60d | 11.8% | 0.53 | -31.3% | 1.6% | 0.13 | 13x | 100% | 1.6% |

