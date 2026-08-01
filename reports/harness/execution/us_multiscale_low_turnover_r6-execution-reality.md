# R6 Execution Reality

No execution path is authorized. R6 uses real adjusted IEX data, but an IEX daily open is not the primary official auction price and the 10:30 overlay assumes a same-boundary fill without processing or routing latency.

Future TCA must compare MOO, marketable LOO, delayed 10:30 price-protected execution, and a short participation-capped TWAP. It must retain decision, submission, acceptance, partial-fill, final-fill, cancellation, official-open, arrival-mid, and next-open timestamps and prices.

Paper fills can validate lifecycle and audit linkage only. They cannot validate market impact, queue priority, capacity, live slippage, or dividends. R6 remains blocked before any order submission.
