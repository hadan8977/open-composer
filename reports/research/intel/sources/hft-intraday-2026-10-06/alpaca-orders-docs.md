# alpaca-orders-docs

- URL: https://docs.alpaca.markets/us/docs/orders-at-alpaca
- fetched_at: 2026-10-06T17:07Z (UTC, task T-20261006-12)
- kind: official-docs
- published/version: current page (undated)
- evidence grade: official

## Key excerpts (verbatim unless marked [paraphrase])

- Bracket orders: "Extended hours are not supported. extended_hours must be false or omitted."; entry market or limit; exits limit (take-profit) or stop/stop-limit; time in force "day" or "gtc".
- Time in force: day, gtc, opg ("executes only in opening auction"), cls ("executes only in closing auction"), ioc, fok. Crypto: only gtc and ioc.
- Stop orders: activate at the stop price then convert to market orders; sell stop needs "a trade on the consolidated tape at or lower than your stop price" within NBBO parameters.
