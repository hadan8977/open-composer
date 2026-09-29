# External Brief: h20260928_42_opex_week

Six sourced findings (two paper-level: Stivers & Sun 2013 and Garcia-Ares &
Muravyev 2025) grounding the option-expiration-week calendar-effect
candidate family for T-20260928-42.

1. **Quantpedia -- Option-Expiration Week Effect**
   (https://quantpedia.com/strategies/option-expiration-week-effect,
   fetched via WebFetch 2026-09-29). Long-only S&P 100 stocks during the
   week containing the month's 3rd Friday, cash otherwise. Backtest
   1988-2010 (source paper Stivers & Sun 2013): 9.3%/yr, Sharpe 0.61, vol
   ~8.7%, max drawdown -15.14%. Mechanism: option market-maker delta-hedge
   rebalancing reduces short-stock hedge positions over the expiration week.
   No recent-period figure disclosed. Source type: post (practitioner
   summary). Credibility: medium. Grounds `OPEX_*_WEEK`.

2. **Stivers & Sun (2013), Journal of Banking & Finance 37(11):4226-4240**
   (https://www.sciencedirect.com/science/article/abs/pii/S0378426613003051,
   located via WebSearch 2026-09-29 as the primary academic source behind
   Quantpedia's summary; abstract-level record). "Returns and option
   activity over the option-expiration week for S&P 100 stocks" -- OE-week
   returns are high relative to less-option-active stocks, the same stock's
   other weeks, and risk-adjusted alphas; mechanism is reduced market-maker
   net long-call/short-stock hedge positions plus declining implied-vol
   risk perceptions. Source type: paper. Credibility: high. Full text
   paywalled, not fetched; abstract-level confirmation only.

3. **Garcia-Ares & Muravyev (2025), "Option returns: a tale of the
   expiration rollover day"** (FMA working paper,
   https://www.fma.org/assets/docs/Derivatives2025/GarciaAres.pdf; WebFetch
   could not parse the raw PDF bytes, so the file was downloaded via curl
   and full text extracted with `pdftotext -layout` -- read directly, not a
   search-engine summary). Option-return-anomaly predictability
   concentrates on the 3rd-Friday expiration and especially the FOLLOWING
   MONDAY, driven by covered-call-writer rollover order imbalance
   overwhelming market-maker inventory capacity. Sample May 2005-Dec 2021;
   patterns "remain largely robust over the entire sample period." Studies
   delta-hedged option returns, not stock/ETF direction. Source type:
   paper. Credibility: high. Grounds `OPEX_*_WEEKMON`'s deferred exit.

4. **Internal placebo design** (not an external source). 12 candidates
   (`PLACEBO_W{1,2,4}_{SPY,QQQ,DIA,IWM}`) apply the identical WEEK
   construction anchored to the 1st, 2nd or 4th Friday's week instead of
   the 3rd, to test whether the expiration week specifically -- rather than
   "some calendar week, long-only" generically -- carries any edge under
   this project's cost/fill contract. Never eligible for a keep tier.

5. **quantifiedstrategies.com -- The Options Expiration Week Effect**
   (https://www.quantifiedstrategies.com/the-option-expiration-week-effect/;
   direct WebFetch returned a bot-verification wall in this session and
   could not be independently re-read in full -- carried only via a
   WebSearch summary, disclosed as blocked rather than dropped). Per that
   summary: the effect "appears to be fading in recent years... has
   deteriorated over the last four years." Historical construction cited:
   large-cap stocks with actively traded options outperformed during
   expiration weeks (0.45% vs 0.12% average weekly return, 1996-2008, 28
   stocks). Source type: post. Credibility: low (fetch-blocked,
   summary-only). Counter-evidence motivating why this round treats the
   local 2024-2026 backtest as decisive.

6. **CXO Advisory -- Option Expiration Week Stock Return Drill-down**
   (https://www.cxoadvisory.com/calendar-effects/option-expiration-week-stock-return-drill-down/,
   fetched via WebFetch 2026-09-29). "During 1983-2008, average option
   expiration week returns are relatively high for the S&P 500 Index and
   for large-cap stocks, but not for small-cap stocks." A reader critique
   argues a volume-ratio-conditioned version of the effect is "unusable in
   practice." Sample ends 2008; no recent-years subperiod breakdown given.
   Source type: post. Credibility: medium. Supports restricting this
   iteration's universe to large-cap/index ETFs.

## Net read

Two independent academic-grade sources (Stivers & Sun 2013 original paper,
confirmed via WebSearch; Garcia-Ares & Muravyev 2025, full text read)
support a real, mechanism-grounded option-expiration-week / rollover-Monday
effect, with the more recent paper's own sample (through Dec 2021) finding
the pattern still robust. Independent counter-evidence (found on request,
per the task brief) claims recent decay, though that specific source could
not be independently re-verified full-text in this session. Both the
original Quantpedia/Stivers-Sun sample (ends 2010) and the CXO Advisory
sample (ends 2008) are old relative to this project's 2024-2026 anchor
window, and this project's own cost/fill contract (10bp/20bp, next-open
fill) differs from the sources' own Friday-close-to-Friday-close holding
period. None of this is grounds to skip the local test -- it is the reason
the local backtest, not any one source's historical number, is the decisive
evidence for this iteration.
