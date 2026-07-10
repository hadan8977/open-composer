# Hypotheses: mom_minute_r1

## H1

- Hypothesis: QQQ time-series momentum on `30m`/`1h` bars can produce positive
  net return after Wave 9.2 base costs, with the last two walk-forward folds also
  positive. Source support: time-series momentum baseline plus cost and crash
  risk sources.
- Failure mode: the signal is only a leveraged beta proxy, flips negative after
  base or x2 costs, has too few trades, or loses money in the most recent folds.
- Measurement: bounded 16-combo P1 trial ledger, QQQ/TQQQ/SPY/BIL benchmark
  family, naive same-timeframe momentum baseline, base and x2 cost stress.
- Stop/Pivot criterion: stop if no candidate is positive after base costs or if
  recent folds are negative; pivot toward lower turnover or daily features only
  if gross alpha exists but costs erase it.

## H2

- Hypothesis: Separating overnight return context from RTH intraday confirmation
  can beat a naive overnight/intraday split baseline on QQQ `30m`/`1h` data.
  Source support: market intraday momentum and overnight/intraday decomposition
  papers.
- Failure mode: overnight thresholding merely selects gaps that mean-revert, or
  same-day flat/next-day close choices dominate the signal.
- Measurement: bounded 12-combo P3 trial ledger, QQQ/TQQQ/SPY/BIL benchmark
  family, naive split baseline, recent-fold and cost-stress checks.
- Stop/Pivot criterion: stop if base-cost net return is negative or not better
  than the naive split baseline; pivot only if one holding mode is consistently
  better but confirmation parameters are unstable.

## H3

- Hypothesis: Cross-sectional ETF intraday rotation may be a valid later path,
  but mom_minute_r1 cannot test it honestly with the current local Alpaca minute
  cache coverage. Source support: intraday cross-section paper plus Wave 9.2
  feasibility.
- Failure mode: a P2 run would mostly measure missing data and static universe
  bias rather than alpha.
- Measurement: Wave 9.2 `P2_cross_sectional_etf_rotation` path suitability and
  same-timeframe ETF symbol count.
- Stop/Pivot criterion: stop P2 for this round; only reopen after at least eight
  ETF symbols have >=18 months of same-timeframe minute history and PIT universe
  caveats are documented.
