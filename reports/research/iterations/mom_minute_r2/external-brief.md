# External Brief: mom_minute_r2

This brief reuses the sourced market claims from `mom_minute_r1`; Step 9.R
changes the execution and validation methodology, not those external claims.
The former performance evidence is withdrawn by the 2026-07-11 methodology
audit. This brief gates only the fixed nine-combination P1 lockbox round.

Objective: design a methodology-corrected, non-ML US minute momentum round without
repeating the defensive PDR/GLD path. The brief was researched on 2026-07-10 and
is paired with `reports/harness/source_cards/us_minute_momentum.jsonl`.

## Sources

1. Moskowitz, Ooi, and Pedersen, "Time Series Momentum", 2012,
   `paper`, high credibility,
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463.
   Core claim: time-series momentum is a documented cross-asset pattern.
   Applicability: P1 can start from a plain trend baseline. Reflection: the
   evidence is lower-frequency than minute ETF trading, so minute results need
   local cost and walk-forward proof.

2. Gao, Han, Li, and Zhou, "Market Intraday Momentum", 2018, `paper`, high
   credibility, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866.
   Core claim: early-day market movement can predict later-day market movement.
   Applicability: P3 should test opening/overnight information separately from
   all-day trend. Reflection: opening effects are cost-sensitive and can decay.

3. Lou, Polk, and Skouras, "A Tug of War: Overnight Versus Intraday Expected
   Returns", 2019, `paper`, high credibility,
   https://www.sciencedirect.com/science/article/abs/pii/S0304405X19300650.
   Core claim: overnight and intraday return components differ. Applicability:
   P3 is not redundant with P1. Reflection: ETF execution costs can erase the
   decomposition edge.

4. Barroso and Santa-Clara, "Momentum Has Its Moments", 2015, `paper`, high
   credibility, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2041429.
   Core claim: volatility-managed momentum can improve risk-adjusted behavior.
   Applicability: useful follow-up if a base path survives. Reflection: adding
   it now would enlarge the search before base evidence exists.

5. Daniel and Moskowitz, "Momentum Crashes", 2014/2016, `paper`, high
   credibility, https://www.nber.org/papers/w20439. Core claim: momentum can
   suffer crash regimes and sharp reversals. Applicability: 9.4 must inspect
   recent-fold results and drawdown, not just headline CAGR. Reflection:
   crash evidence is not minute-specific, so it is a risk lens.

6. Heston, Korajczyk, and Sadka, "Intraday Patterns in the Cross-Section of
   Stock Returns", 2010, `paper`, high credibility,
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1107590. Core claim:
   intraday cross-sectional patterns exist. Applicability: P2 is conceptually
   valid. Reflection: Wave 9.2 local data coverage is too sparse for this round.

7. Frazzini, Israel, and Moskowitz, "Trading Costs of Asset Pricing
   Anomalies", 2018, `paper`, high credibility,
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2294498. Core claim:
   costs materially change anomaly profitability. Applicability: every 9.4
   trial must use the Wave 9.2 cost table. Reflection: actual broker fills are
   still a later paper-stage evidence requirement.

8. Alpaca Market Data FAQ, provider official docs, accessed 2026-07-10,
   https://docs.alpaca.markets/docs/market-data-faq. Core claim: Alpaca market
   data feed entitlements affect completeness. Applicability: current Alpaca
   IEX cache is research-only evidence. Reflection: provider docs are living
   documentation and must be rechecked before paper/live decisions.

## Topic Coverage

- Intraday and minute-level time-series momentum and reversal.
- Cross-sectional intraday momentum and same-timeframe data coverage limits.
- Overnight versus intraday return decomposition.
- Volatility-managed momentum and momentum crash risk.
- Opening/early-day market intraday momentum effects.
- Transaction costs, spreads, and high-turnover anomaly implementation.
- Alpaca IEX feed caveat and research-only data status.

## Candidate Matrix Revisions

- Keep P1 time-series ETF momentum, bounded to QQQ `30m` and `1h` in the first
  live matrix. `15m` remains available but costs and churn make it secondary.
- Stop/defer P2 cross-sectional ETF rotation. The idea is research-valid, but
  Wave 9.2 found too few ETF symbols with >=18 months of local minute data in a
  common timeframe.
- Keep P3 overnight/intraday decomposition as a distinct path with QQQ `30m` and
  `1h`, an overnight threshold, and a naive split baseline.
- Defer P4 volatility-adjusted momentum as a separate path. Volatility controls
  are a follow-up if P1/P3 survive; adding them now increases overfit risk.

## Conclusion

Proceed to Wave 9.4 only with P1 and P3, total budget `28`, non-ML, QQQ-focused,
cost-gated, and research-only. Do not promote, paper trade, or claim full-market
data quality from this Alpaca/IEX evidence.
