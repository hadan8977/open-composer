# R7 Execution Reality Review

- Status: `blocked`
- Historical data: real Alpaca Basic IEX through `2026-07-17`
- Order authority: none
- Formal-forward observations: `0`

The daily candidates assume complete-close signals and fills at the next IEX daily open. D06 is a selection-prohibited shadow on a 29-date intraday-complete subset and a 10:30 IEX bar boundary. It drops D04's `2024-07-22` execution and starts from cash, so it is not the exact persistent D04 parent path. Neither price is an official primary-exchange opening-auction benchmark, and the 10:30 path omits processing and routing latency.

Future TCA must compare MOO, marketable LOO, a delayed protected limit, and a short limit-constrained TWAP. It must retain official-open, SIP, IEX, arrival-mid, first-fill, volume-weighted-fill, and next-mark references. Alpaca paper execution is useful for lifecycle and logging tests only; it does not establish live slippage, queue priority, market impact, fees, dividends, or capacity.

Paper simulation remains blocked by the failed complete historical family gate, zero formal-forward observations, missing official-open parity, missing matched fills, and missing notional capacity evidence.
