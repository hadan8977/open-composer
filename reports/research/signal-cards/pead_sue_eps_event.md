# Signal card: pead_sue_eps_event

- Source: `data/features/sec_fundamentals_daily:sue_eps where days_since_report = 0`; mode `event`; lag 0 sessions; direction +1
- Universe: top 3000 by dollar ADV, close >= $5, funds and ETFs excluded; entries at the next open; excess vs the universe equal weight
- Generated 2026-09-24T08:21:07+00:00
- Flags: {"car_t_ge_3": true, "beats_redated": false, "book_positive_20bp": false, "book_positive_20bp_recent": true}

4639 events on 1220 days, 1329 stocks, from 2016-01-29.

| horizon | mean excess | t (dates) | hit | 2024+ | T1 | T2 | T3 |
|---|---|---|---|---|---|---|---|
| 1d | 0.02% | 0.3 | 52% | -0.00% | -0.03% | 0.03% | 0.11% |
| 5d | 0.06% | 0.6 | 53% | -0.12% | 0.09% | 0.34% | 0.12% |
| 20d | 0.71% | 3.6 | 52% | 0.82% | 0.75% | 0.85% | 0.59% |
| 60d | 1.46% | 3.4 | 52% | 1.51% | 1.54% | 1.39% | 1.24% |

Redated placebo (20 seeds, 20d): mean excess 0.46%..1.06%.

Long-only book (every event stock, calendar time), 20 bp, excess vs the universe:

| book | hold | CAGR | Sharpe | max DD | excess/yr | IR | turnover/yr | invested | excess/yr 2024+ |
|---|---|---|---|---|---|---|---|---|---|
| events | 5d | -18.6% | -0.64 | -89.7% | -26.1% | -1.33 | 124x | 82% | -35.8% |
| events | 20d | 6.6% | 0.39 | -50.7% | -3.9% | -0.33 | 58x | 100% | 1.5% |
| events | 60d | 12.6% | 0.69 | -42.4% | 1.4% | 0.21 | 16x | 100% | 3.5% |

