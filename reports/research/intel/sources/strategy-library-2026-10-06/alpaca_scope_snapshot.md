# Alpaca scope snapshots (fetched 2026-10-06 ~17:00 UTC via WebFetch summaries; not raw HTML)

## https://docs.alpaca.markets/docs/options-trading-overview
- Level 0: options disabled.
- Level 1: sell covered call; sell cash-secured put.
- Level 2: Level 1 + buy call, buy put.
- Level 3: Level 1-2 + "buy a call spread", "buy a put spread".
- Naked/uncovered short options and straddles/strangles as single structures not listed at any level.
- Corroborated locally: registry `dir:naked_options_income_0dte` / `dir:put_credit_spread_income`
  (2026-09-28: "Alpaca does not support naked/uncovered short options at any approval level, including Level 3").

## https://docs.alpaca.markets/docs/crypto-trading
- Spot only: "Cryptocurrencies cannot be bought on margin", "can not be sold short".
- 20+ assets, 56 pairs (BTC/USD/USDT/USDC based); 24/7; maker/taker fees 15-25 bp at the lowest tier.
- Order cap $200k notional; order types market/limit/stop-limit; TIF GTC/IOC.

## Derived tradability rules used by the catalog
- options: yes only for covered call, cash-secured put, protective put/call on held stock, long calls/puts,
  long straddle/strangle built from two long single legs, debit spreads. Anything with an uncovered short leg
  (short straddle/strangle/guts, ratio spreads that sell more than they buy, ladders, short butterflies/condors
  built with naked wings, short combos/synthetics) = no.
  Credit spreads (bull put, bear call), butterflies, condors, iron structures: defined risk, multi-leg.
  The doc lists only "buy a call/put spread"; credit/butterfly/condor legality is INFERRED, marked
  `alpaca_basis: inferred` and left unverified until a paper probe.
- futures, FX (spot), bond cash instruments, CDS/swaps, convertibles, real estate, commodities physical,
  distressed debt, tax arbitrage, cash/REPO/lending: Alpaca does not trade them -> no.
- crypto: spot long only (no shorting, no margin).
