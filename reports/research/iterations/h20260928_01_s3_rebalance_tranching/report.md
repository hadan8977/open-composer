# H-20260928-01 S3 rebalance timing luck and four-tranche execution

Panel 2016-01-04..2026-09-17. O00 = live month-end rule; Onn = signal moved nn sessions later; T4 = four tranches at offsets [0, 5, 10, 15].

## Per-candidate metrics (net 10 bp)

| candidate | window | CAGR | Sharpe | max DD | turnover/yr |
|---|---|---|---|---|---|
| O00 | stress | 33.4% | 0.87 | -48.0% | 10.94 |
| O00 | anchor | 116.3% | 1.82 | -32.3% | 11.69 |
| O01 | stress | 26.9% | 0.74 | -44.7% | 11.44 |
| O01 | anchor | 94.7% | 1.56 | -37.4% | 11.24 |
| O02 | stress | 27.2% | 0.74 | -48.2% | 11.91 |
| O02 | anchor | 84.0% | 1.45 | -37.2% | 10.87 |
| O03 | stress | 20.6% | 0.62 | -51.4% | 11.92 |
| O03 | anchor | 94.9% | 1.59 | -33.5% | 10.77 |
| O04 | stress | 37.3% | 0.92 | -44.3% | 11.12 |
| O04 | anchor | 76.3% | 1.36 | -38.8% | 10.79 |
| O05 | stress | 35.4% | 0.88 | -48.2% | 11.44 |
| O05 | anchor | 68.7% | 1.26 | -49.7% | 11.13 |
| O06 | stress | 30.1% | 0.79 | -51.3% | 11.38 |
| O06 | anchor | 67.3% | 1.26 | -42.7% | 10.39 |
| O07 | stress | 34.2% | 0.86 | -52.7% | 10.55 |
| O07 | anchor | 59.9% | 1.12 | -41.8% | 11.62 |
| O08 | stress | 23.3% | 0.67 | -71.0% | 11.02 |
| O08 | anchor | 69.2% | 1.27 | -35.4% | 10.25 |
| O09 | stress | 33.9% | 0.85 | -67.7% | 10.15 |
| O09 | anchor | 71.5% | 1.31 | -34.6% | 9.34 |
| O10 | stress | 33.5% | 0.84 | -67.0% | 9.98 |
| O10 | anchor | 77.0% | 1.39 | -34.7% | 8.91 |
| O11 | stress | 31.6% | 0.80 | -61.8% | 10.51 |
| O11 | anchor | 88.8% | 1.52 | -34.4% | 9.08 |
| O12 | stress | 37.0% | 0.89 | -64.0% | 10.02 |
| O12 | anchor | 83.9% | 1.49 | -34.6% | 8.76 |
| O13 | stress | 36.2% | 0.88 | -63.1% | 9.62 |
| O13 | anchor | 85.8% | 1.47 | -32.5% | 9.00 |
| O14 | stress | 31.4% | 0.81 | -64.1% | 10.19 |
| O14 | anchor | 91.8% | 1.55 | -37.2% | 9.36 |
| O15 | stress | 34.9% | 0.86 | -58.9% | 9.78 |
| O15 | anchor | 84.1% | 1.44 | -38.9% | 9.84 |
| O16 | stress | 23.2% | 0.66 | -59.4% | 10.75 |
| O16 | anchor | 88.1% | 1.52 | -37.3% | 9.12 |
| O17 | stress | 28.1% | 0.75 | -56.1% | 10.27 |
| O17 | anchor | 98.2% | 1.65 | -37.9% | 9.47 |
| O18 | stress | 32.8% | 0.85 | -57.2% | 10.42 |
| O18 | anchor | 89.1% | 1.57 | -33.2% | 9.15 |
| O19 | stress | 29.7% | 0.79 | -56.8% | 11.65 |
| O19 | anchor | 94.7% | 1.64 | -32.1% | 10.64 |
| O20 | stress | 27.0% | 0.73 | -46.9% | 11.69 |
| O20 | anchor | 101.2% | 1.69 | -28.9% | 11.22 |
| T4 | stress | 35.6% | 0.90 | -52.0% | 10.44 |
| T4 | anchor | 87.0% | 1.52 | -35.2% | 10.27 |

## Offset distribution (21 single-date versions, net 10 bp)

| window | metric | min | median | max | O00 | O00 rank (1=best) | T4 |
|---|---|---|---|---|---|---|---|
| stress | cagr | 20.6% | 31.6% | 37.3% | 33.4% | 9 | 35.6% |
| stress | sharpe | 0.62 | 0.81 | 0.92 | 0.87 | 5 | 0.90 |
| stress | max_dd | -71.0% | -56.8% | -44.3% | -48.0% | 4 | -52.0% |
| select | cagr | 43.3% | 57.3% | 85.0% | 85.0% | 1 | 60.6% |
| select | sharpe | 0.90 | 1.15 | 1.51 | 1.51 | 1 | 1.21 |
| select | max_dd | -49.7% | -35.4% | -28.9% | -32.3% | 3 | -35.2% |
| anchor | cagr | 59.9% | 85.8% | 116.3% | 116.3% | 1 | 87.0% |
| anchor | sharpe | 1.12 | 1.49 | 1.82 | 1.82 | 1 | 1.52 |
| anchor | max_dd | -49.7% | -35.4% | -28.9% | -32.3% | 3 | -35.2% |
| holdout_2026_contaminated | cagr | 124.3% | 142.8% | 161.2% | 152.9% | 5 | 141.1% |
| holdout_2026_contaminated | sharpe | 1.92 | 2.09 | 2.25 | 2.21 | 3 | 2.09 |
| holdout_2026_contaminated | max_dd | -23.1% | -19.0% | -16.6% | -16.6% | 1 | -18.3% |

## Adoption rule (T4 vs O00)

- (a) anchor max DD shallower: False (delta -2.9 pp)
- (b) stress max DD shallower: False (delta -4.0 pp)
- (c) Sharpe give-up <= 0.05 in anchor and stress: False (anchor -0.298, stress +0.034)
- (d) anchor G1/G1' at 10 and 20 bp: False

Overall pass: False

