# T-20260928-01 S1 rebalance timing luck (descriptive, no adoption)

Panel 2016-01-04..2026-09-17. O00 = live rule; Onn = signal moved nn sessions after the S1's own rebalance date. No offset is adopted from this run; O00 stays live regardless of rank.

## Offset distribution (net 10 bp)

| window | metric | min | median | max | O00 | O00 rank (1=best) |
|---|---|---|---|---|---|---|
| stress | cagr | 9.5% | 11.3% | 14.7% | 9.5% | 5 |
| stress | sharpe | 0.48 | 0.56 | 0.69 | 0.48 | 5 |
| stress | max_dd | -32.1% | -28.9% | -26.1% | -32.1% | 5 |
| select | cagr | 17.9% | 20.0% | 23.6% | 23.6% | 1 |
| select | sharpe | 0.82 | 0.93 | 1.14 | 1.14 | 1 |
| select | max_dd | -16.9% | -15.2% | -13.6% | -16.9% | 5 |
| anchor | cagr | 21.9% | 27.4% | 29.2% | 27.7% | 2 |
| anchor | sharpe | 1.04 | 1.33 | 1.41 | 1.35 | 2 |
| anchor | max_dd | -16.9% | -15.2% | -13.6% | -16.9% | 5 |
| holdout_2026_contaminated | cagr | 34.3% | 46.4% | 49.2% | 45.7% | 4 |
| holdout_2026_contaminated | sharpe | 1.67 | 2.23 | 2.40 | 2.18 | 4 |
| holdout_2026_contaminated | max_dd | -9.6% | -8.2% | -8.0% | -8.5% | 4 |

## Queue highlight rule (live top 3 AND median Sharpe >20% below O00)

- stress: not triggered
- select: not triggered
- anchor: not triggered
- holdout_2026_contaminated: not triggered

