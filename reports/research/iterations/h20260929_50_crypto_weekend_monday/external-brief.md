# External Brief: h20260929_50_crypto_weekend_monday

Structured entries are in `external-brief.json`. Summary:

1. **Mourey, Shahrour, Soiman (Finance Research Letters 86, 2025)** - the paper
   behind the direction. Negative weekend returns of 20 large cryptos predict
   Monday equity declines; positive ones do nothing; stronger after May 2022.
   Only the RePEc abstract was read (publisher page 403); no return window, rule,
   Sharpe or cost is given.
2. **Binance Research via Yahoo (2026-09-22)** - weekend tokenized-equity prices
   priced a median 92% of the Monday opening gap (one summer of data). This is
   the prior that the effect sits in the gap and is priced before a Monday-open fill.
3. **CME ES hours and Alpaca 24/5 docs** - index futures reopen Sunday 18:00 ET;
   Alpaca lists a Sunday 8:00 PM ET overnight session. A Sunday-night fill exists at
   the broker but is a different fill rule; out of scope for this step.
4. **ACR Journal (2025) and arXiv 2506.08718** - weekend crypto behaviour is a
   distinct object; the venues used (Binance, Coinbase) are the price-discovery venues.
5. Local registry: `dir:prediction_market_crypto_as_equity_signal` only ran a
   one-day lead-lag probe; `dir:crypto_weekend_to_monday_equity_transmission`
   is the row this step tests.

The evidence changed the design in three ways (see `candidate_matrix_revisions`):
the gap is the control and only oc/o2o gate, the gate uses the asymmetric
W<0 grouping in the two recent samples, and an equal-weight 10-coin signal was
added next to BTC and ETH.
