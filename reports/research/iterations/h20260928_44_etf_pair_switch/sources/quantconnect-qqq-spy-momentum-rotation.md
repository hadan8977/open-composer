# QQQ/SPY Momentum Rotation System -- QuantConnect forum

URL: https://www.quantconnect.com/forum/discussion/19216/qqq-spy-momentum-rotation-system/
Fetched via WebFetch: 2026-09-29T00:00:00Z (this session; the queue task's own
plan text already summarizes an earlier open of the same thread on
2026-09-28, this is an independent re-open for T-20260928-44)
Author: Robert Lemois (Pro member on QuantConnect)

## Trading rule as posted

- Lookback period: 20 trading days for momentum calculation
- Rebalance frequency: every 5 trading days
- QQQ bias: +1.0% applied to QQQ's momentum score
- Switch threshold: 0.5% momentum difference between assets required to
  switch (persistence filter against whipsaw)
- Position size: 100% allocation, fully invested in either QQQ or SPY (no
  cash position disclosed in the rule itself)

## Backtest period & reported performance (author's own numbers)

- Period: 2010-2024 (15 years)
- Initial capital $10,000 -> $123,115
- Total return: 1,131%
- CAGR: 19.02% annualized
- Maximum drawdown: ~30% (COVID-19, 2020)
- Sharpe ratio: ~0.8 (author's own estimate)

## Issues identified by QuantConnect staff in the same thread

Mia Alissi (QuantConnect staff) identified several bugs in the posted code:

1. Syntax error: unterminated string in the `rebalance` function (missing
   closing quote)
2. Logic flaw: period counters incremented before the persistence filter
   check, causing over-counting of the holding period
3. Data handling: unsafe `history()` calls with no exception handling;
   improper DataFrame indexing
4. Recommendation: counters should only increment after a confirmed position
   change

Robert acknowledged the feedback and stated he applied the recommended
corrections, but posted no updated backtest numbers after the fix. The
thread contains no independent third-party verification, no out-of-sample
test, and no live/paper trading record from any participant.

## Assessment for this iteration

Single-author, single-platform forum post; own numbers only; a platform
reviewer flagged concrete implementation bugs in the same thread and no
post-fix numbers were ever published; no independent replication found. This
is weak evidence -- used only for the *mechanism* (binary relative-strength
switch between two correlated, liquid ETFs with an absolute or relative
threshold) at the parameter values this iteration's own preregistered grid
picks (lookback 63/126 trading days, monthly rebalance, absolute-momentum-
vs-cash filter identical to the already-live rotation_cell engine), not for
the source's own 19.02% CAGR / 0.8 Sharpe numbers, which are not reused or
assumed anywhere in this iteration's candidate manifest.
