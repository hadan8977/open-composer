# H-20260927-01 sleeve combination vs delevered control

Common start: 2017-02-01. Cost 10/20 bp primary/stress.

## Anchor and stress window metrics (net10)

| candidate | window | CAGR | Sharpe | max DD | turnover/yr |
|---|---|---|---|---|---|
| M0 | stress | 24.5% | 0.70 | -48.0% | 11.32 |
| M0 | anchor | 118.2% | 1.84 | -32.3% | 11.68 |
| M1 | stress | 15.7% | 0.69 | -23.9% | 0.43 |
| M1 | anchor | 59.8% | 1.91 | -17.3% | 0.39 |
| M2 | stress | 18.7% | 0.72 | -28.6% | 0.50 |
| M2 | anchor | 69.8% | 1.85 | -20.7% | 0.44 |
| M3 | stress | 13.0% | 0.64 | -23.3% | 1.84 |
| M3 | anchor | 54.4% | 2.10 | -13.0% | 1.81 |
| C1 | stress | 15.7% | 0.69 | -26.5% | 0.00 |
| C1 | anchor | 56.5% | 1.82 | -17.1% | 0.00 |
| C2 | stress | 18.0% | 0.69 | -30.9% | 0.00 |
| C2 | anchor | 68.9% | 1.83 | -20.6% | 0.00 |
| C3 | stress | 14.0% | 0.68 | -23.3% | 0.00 |
| C3 | anchor | 45.8% | 1.81 | -13.9% | 0.00 |

## Adoption rule

| Mi | a | b | c | d | pass |
|---|---|---|---|---|---|
| M1 | True | True | False | True | False |
| M2 | True | True | False | True | False |
| M3 | True | True | False | True | False |

## Sleeve pairwise daily-return correlation

- stress: s1/s2 0.56, s1/s3 0.48, s2/s3 0.83
- select: s1/s2 0.64, s1/s3 0.56, s2/s3 0.76
- anchor: s1/s2 0.59, s1/s3 0.60, s2/s3 0.79
- holdout_2026_contaminated: s1/s2 0.57, s1/s3 0.67, s2/s3 0.82

## k by window

- C1: stress=0.548, select=0.516, anchor=0.519, holdout_2026_contaminated=0.546
- C2: stress=0.649, select=0.621, anchor=0.623, holdout_2026_contaminated=0.638
- C3: stress=0.479, select=0.439, anchor=0.425, holdout_2026_contaminated=0.428

Overall pass: False

