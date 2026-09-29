# Counter-evidence / recent-decay search (2026-09-29, this session)

Query 1: "option expiration week effect anomaly disappeared recent years
stock returns" (WebSearch).
- quantifiedstrategies.com's OPEX-week page (per the WebSearch results
  summary; the page itself returned a bot-verification wall on direct
  WebFetch and could not be independently re-read in full): "the anomaly
  appears to be fading in recent years... has deteriorated over the last
  four years" (relative to the site's own publication date, unspecified
  exact years in the summary). Historical construction cited: large-cap
  stocks with actively traded options outperformed during expiration weeks
  (0.45% vs 0.12% average weekly return, 1996-2008, 28 stocks), effect
  strongest for high option/stock-volume-ratio names.
- Separately notes the specific EXPIRATION DAY itself (close-to-close on the
  3rd Friday) is historically POOR, distinct from the week-as-a-whole
  result -- a caveat for interpreting any day-level result inside this
  iteration's week-level rule.

Query 2 (CXO Advisory, fetched directly via WebFetch):
https://www.cxoadvisory.com/calendar-effects/option-expiration-week-stock-return-drill-down/
- Sample: primarily 1996-2008, supplementary 1983-1995, pre-options control
  1948-1972.
- "During 1983-2008, average option expiration week returns are relatively
  high for the S&P 500 Index and for large-cap stocks, but not for
  small-cap stocks" -- supports restricting this iteration's universe to
  large-cap/index ETFs (SPY/QQQ/DIA/IWM), consistent with the queue task's
  own design.
- A reader critique quoted on the page argues the volume-ratio-conditioned
  version of the effect "is unusable in practice" (ex-ante unknowable
  ratios); the author's own reply suggests "the only real edge... is the
  plain option expiration week effect" but the page does not quantify
  whether that plain effect clears realistic transaction costs.
- No explicit recent-years (2010s-2020s) subperiod breakdown is given on
  this page.

## Net assessment for this iteration
Independent, non-Quantpedia evidence (quantifiedstrategies.com, via
WebSearch summary only, not independently re-verified full-text) explicitly
claims recent decay; CXO Advisory's own primary analysis is itself dated
(sample ends 2008) and does not settle the recent-window question either
way. This is consistent with the queue task's own framing ("样本老，本地
测试就是决定性否定测试") -- the local 2024-2026 anchor-window and
2016-2023 stress-window backtest run by this iteration is the decisive test
for whether the effect (if real historically) still clears the frozen
cost/keep-rule contract now, not any one blog's claim in either direction.
