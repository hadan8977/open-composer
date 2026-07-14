# Decision Record: mom_multiasset_r1

This record is initialized before backtests. Final continue, pivot or stop decisions will be written from the generated evaluation report and trial ledger; no path is pre-selected.

## P1
- Path: ETF absolute/relative momentum
- Decision: continue
- Reason: The 252-day, weekly, top-2 route passed three of four fold and positive OOS IR gates, although it still carries a roughly 40% historical maximum drawdown.
- Next iteration suggestion: Test regime and downside-risk overlays without changing the frozen deterministic route.

## P2
- Path: Sector risk-adjusted rotation
- Decision: stop
- Reason: The best sector candidate lost to the equal-weight sector basket in both recent folds and had negative OOS IR and rank IC.
- Next iteration suggestion: Do not spend ML budget on this path in the current data window.

## P3
- Path: Stock cross-sectional momentum
- Decision: continue
- Reason: The 12-1 top-5 route passed the internal fold gate, but its current-universe history is survivorship-biased and remains exploratory.
- Next iteration suggestion: Use it as the matched deterministic baseline for ranking ML and freeze the universe for forward virtual paper.

## P4
- Path: Stock 52-week-high and trend quality
- Decision: stop
- Reason: The best candidate had negative mean rank IC, failed two folds, and did not pass the registered three-of-four gate.
- Next iteration suggestion: Preserve the factor for future interactions, but do not create a standalone sleeve now.

## P5
- Path: Stock residual and sector-relative momentum
- Decision: continue
- Reason: The simple sector-relative top-10 route passed the portfolio fold gate and reduced concentration, although standalone rank IC was near zero.
- Next iteration suggestion: Keep it as a diversification baseline and test whether ML ranking adds stable marginal IC.
