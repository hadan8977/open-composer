# T-20260928-01: S1/S2 rebalance-date luck (date-neutral expectations)

Descriptive only, mirroring H-20260928-01's S3 check with the same frozen engine, cost model (10 bp primary / 20 bp stress per side, next-open fills) and windows. No offset is adopted; both sleeves' live rules (O00) stay in force regardless of rank.

## S1 (5 offsets)

O00 reproduces `salvage.run_cell` (max abs diff 0.00e+00).

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

Queue highlight rule (live top 3 AND median Sharpe >20% below O00):
- stress: not triggered
- select: not triggered
- anchor: not triggered
- holdout_2026_contaminated: not triggered

## S2 (21 offsets)

O00 reproduces `salvage.run_cell` (max abs diff 6.94e-18).

| window | metric | min | median | max | O00 | O00 rank (1=best) |
|---|---|---|---|---|---|---|
| stress | cagr | 5.1% | 8.0% | 10.3% | 8.6% | 7 |
| stress | sharpe | 0.32 | 0.50 | 0.63 | 0.52 | 7 |
| stress | max_dd | -34.8% | -31.4% | -24.9% | -26.8% | 4 |
| select | cagr | 26.6% | 32.1% | 37.1% | 36.6% | 2 |
| select | sharpe | 1.17 | 1.44 | 1.72 | 1.72 | 1 |
| select | max_dd | -16.7% | -13.0% | -10.2% | -10.2% | 1 |
| anchor | cagr | 29.7% | 35.7% | 40.9% | 39.7% | 4 |
| anchor | sharpe | 1.31 | 1.55 | 1.81 | 1.80 | 2 |
| anchor | max_dd | -16.7% | -13.0% | -10.2% | -10.2% | 1 |
| holdout_2026_contaminated | cagr | 31.1% | 45.3% | 56.4% | 45.3% | 11 |
| holdout_2026_contaminated | sharpe | 1.40 | 1.88 | 2.24 | 1.88 | 12 |
| holdout_2026_contaminated | max_dd | -10.6% | -9.2% | -7.9% | -10.2% | 17 |

Queue highlight rule (live top 3 AND median Sharpe >20% below O00):
- stress: not triggered
- select: not triggered
- anchor: not triggered
- holdout_2026_contaminated: not triggered

Per-sleeve preregistration, contracts and full trial ledgers: `reports/research/iterations/h20260928_23_s1_s2_rebalance_timing/` (S2) and `reports/research/iterations/h20260928_23_s1_rebalance_timing/` (S1).

