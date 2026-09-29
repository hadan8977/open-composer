# External Brief: h20260929_36_router_sip

Objective: T-20260929-36 (autonomous-queue.md): recheck registry direction dir:nasdaq_long_short_event_router_1m. Its best route (lookback 10, entry after 2 bars, top 1, min relative volume 1, QQQ-prior-negative gate, opening_reversal, max opening return 0) reached research_pass on Alpaca IEX cache (sweep_002: full window 2024-05-31..2026-05-29 Sharpe 1.41, annualized 35.24 percent) but was never checked on consolidated SIP data. Run the identical route, no parameter change, on SIP 1-minute bars 2023-01..data end, with 10/20 bp per side costs, placebos and the S3 combination test, and decide kept / partial / refuted.

## Sources

- https://arxiv.org/abs/1005.3535 (paper, 2010-05-19): We also show that short-term return reversal is driven by temporary liquidity imbalances lasting less than an hour and bid-ask bounce.
  - Applicability: Mechanism prior for buying an opening loser: reversal from transient liquidity imbalance that decays within about an hour; the route enters 2 minutes after the open and holds to the close, so the effect window and the holding window differ.
  - Reflection: Motivates the router's opening-reversal selection and warns the edge is a liquidity-provision premium that is large in wide-spread illiquid tapes (IEX-only prints) and small at SIP quotes.
- https://www3.nd.edu/~zda/EOD.pdf (paper, 2025-04-01): Individual stocks experience sharp intraday return reversals in the cross-section during the last 30 minutes of the trading day.
  - Applicability: Recent (2025) evidence that intraday losers get positive price pressure in the cross-section of U.S. stocks; our route holds the opening loser through that late-day window.
  - Reflection: Supports the sign of the route's exposure (long intraday losers) while showing the payoff is concentrated late in the day, not at the 09:32 entry.
- https://arxiv.org/abs/2605.04004 (paper, 2026-05-05): Eleven families fail because gross return before friction is 0.07-1.50 points, below the 2.0-point friction floor.
  - Applicability: Negative prior: opening-window OHLCV rules on Nasdaq-100 products usually fail the friction and year-stability tests, so a pass here needs to survive both explicitly.
  - Reflection: Sets the bar for the router recheck: net-of-cost, out-of-window, year-stable, placebo-beating; it is the direct counter-prior for the IEX-derived research_pass.
- https://ideas.repec.org/a/eee/dyncon/v136y2022ics0165188922000185.html (paper, 2022-03-01): Previous studies of the U.S. market regard short-term reversal as compensation for liquidity provision.
  - Applicability: Frames why a reversal premium can be earned by liquidity providers and is expected to shrink with spread and with tape coverage.
  - Reflection: Reversal returns are tied to liquidity provision, so they depend on how prints and fills are measured (IEX-only vs consolidated tape).
- https://arxiv.org/abs/1611.03110 (paper, 2016-10-29): we dissect their returns into intraday and overnight com- ponents with respect to the U.S. market hours
  - Applicability: Supports evaluating the route as a pure intraday (open-to-close) return stream separate from overnight gaps, as the router does.
  - Reflection: Same-day flatten means the router earns no overnight return; its series must be compared with S3 on a same-session close-to-close convention.
- https://docs.alpaca.markets/docs/historical-stock-data-1 (provider_official_docs, unknown): accounts for approximately ~2.5% of the market volume
  - Applicability: The router's original research_pass used the IEX feed cache, which sees about 2.5% of volume; SIP is the consolidated tape (100% of volume).
  - Reflection: Explains why an opening-window rule (first two 1-minute bars, relative volume) can differ sharply between IEX-only and SIP tapes.
- https://docs.alpaca.markets/reference/stockbars (provider_official_docs, unknown): split : adjust price and volume for forward and reverse stock splits dividend : adjust price for cash dividends spin-off : adjust price for spin-offs all : apply all above adjustments
  - Applicability: Defines split-adjusted and dividend-adjusted prices, which matter for the 10-day prior-momentum and previous-close terms across the NVDA 2024-06-10, AVGO 2024-07-15 and NFLX 2025-11-17 splits.
  - Reflection: Adjusted-for-dividends prices change lookback returns by the dividend yield at most; splits must be adjusted or lookback returns break.
- https://docs.alpaca.markets/docs/margin-and-short-selling (broker_official_docs, unknown): $0 locate and borrow fees on all ETB shares for Trading API users.
  - Applicability: Short borrow cost for easy-to-borrow mega-caps is $0 from the broker; the task still charges 0.5% a year (about 0.2 bp per short day) as a conservative modeled cost.
  - Reflection: Borrow cost is immaterial for a same-day-flatten intraday book; the binding shorting constraints are locates, Reg SHO and spreads.

## Candidate matrix revisions

- mesfin_ohlcv_intraday_falsification_2026: Added random-pick placebos (3 preregistered seeds plus 200 distribution seeds) and a year-by-window report to the candidate set, because the closest independent evidence says most OHLCV intraday rules fail friction and year stability.
- alpaca_iex_share_of_volume: Kept every parameter frozen and changed only the data tape (IEX cache to SIP consolidated), so any difference is attributable to the data; no local IEX minute cache exists to replay.
- alpaca_bars_adjustment_all: Added a split and dividend adjustment audit against data/sip/daily for NVDA (2024-06-10), AVGO (2024-07-15) and NFLX (2025-11-17) before trusting the 10-session prior momentum.
- alpaca_etb_borrow_fee_zero: Modeled borrow at 0.5 percent a year on short trade days although the broker fee for easy-to-borrow names is $0, so the short leg is not flattered.
