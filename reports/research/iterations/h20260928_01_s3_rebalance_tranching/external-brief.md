# External brief: h20260928_01_s3_rebalance_tranching

Question: S3 trades once a month at the month-end close. Does splitting it into four
tranches that trade on different days lower the drawdown without costing return?

What the literature says:
- Concretum (Zarattini and Pagani, 2025): 20-stock monthly momentum, 1991-2024. Best vs worst
  trading day differ by 348 bp CAGR. Tranching leaves mean CAGR and Sharpe unchanged and
  shrinks the dispersion. It reports no drawdowns for tranched books.
- Hoffstein, Faber, Braun (SSRN 3673910) and Hoffstein, Sibears, Faber (JBIS 2019): timing luck
  often above 100 bp a year; N staggered tranches cut it by about 1/N.
- Allocate Smartly: tranched TAA averaged 14.2% vs 13.9% single-day; dispersion down ~2/3.
- Newfound 2020: a tranched book behaves like a slow trend follower. For S3 that is a risk:
  in a fast crash only a quarter of the book moves at each date.

Prior: T4 should land near the median of the 21 offsets. Whether it beats O00 depends on
whether month-end happens to be a lucky or unlucky day for S3; the drawdown effect is the
open local question.
