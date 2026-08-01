# Research Memory: us_spy_dual_trend_core_r8

- Iteration: `mom_spy_dual_trend_core_r8`; fixed candidate R8D01 stopped with no retry or parameter change.
- Data: immutable Alpaca SIP daily SPY/QQQ/XLK/BIL and raw SPY 30m/5m/1m through `2026-07-17`; seven requests, complete sessions, no fallback, forward fill, or zero-return substitution.
- Result at 10 bps one-way: return `40.456674%`, annualized return `3.452869%`, Sharpe `0.736668`, maximum drawdown `-11.479512%`, 54 entries and four positive independent folds.
- Cost stress: 20 bps return `34.501439%`, Sharpe `0.642641`, maximum drawdown `-13.170420%`.
- Benchmark failure: matched entry-only 40% SPY / 60% cash buy-and-hold Sharpe was `0.887071`; R8 delta was `-0.150404`.
- Statistical failure: DSR probability was `0.075204` at global lower-bound `N=8002` and `0.095829` at sensitivity `N=4664`.
- Cross-feed: 1,375 hash-bound SIP/IEX sessions, 99.8545% target-state agreement, but four transition mismatches exceeded the frozen maximum of two.
- Interpretation: daily re-evaluation creates too much whipsaw for a single SPY trend sleeve. Do not retune the 126-session lookback or 40% weight.
- Next path: a new diversified family with slower state updates, fixed-ETF sector-relative momentum, GLD/IEF trend diversification, risk caps, turnover buffers, and selection-prohibited intraday execution shadows.
- `workflow_pass=true`; `research_pass=false`; `llm_contribution_pass=false`; `paper_ready_pass=false`; broker authority remains false.
