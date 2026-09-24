# External Brief: h20260924_02_momentum_crash_guard

Card H-20260924-02. Full source list, claims and quotes are in `external-brief.json`
and `direction-review.json` (verified against `reports/harness/source_cards/
h20260924_02_momentum_crash_guard.jsonl`). Summary:

1. **Daniel & Moskowitz (2016, JFE / NBER w20439), "Momentum Crashes"** -- primary
   source for CG-DM. Momentum crashes cluster in "panic" states: a 24-month
   trailing bear market (cumulative CRSP VW return < 0) combined with high
   126-day trailing market variance. Their own implementable "dynamic strategy"
   (GJR-GARCH mean/variance forecast on long-short WML) roughly doubles WML's
   Sharpe ratio historically -- an upper bound this iteration's much simpler
   binary panic gate is not expected to match. Long-only momentum is less
   exposed to the paper's crash mechanism, which is concentrated in the past-
   loser (short) leg -- directly relevant since the T1 book is long-only.

2. **Barroso & Santa-Clara (2015, JFE), "Momentum has its moments"** -- primary
   source for CG-BSC-daily. Scale exposure by the inverse of a 126-trailing-
   day realized-variance forecast (21 x mean daily squared return over 126
   sessions), targeting constant volatility (12% for their own long-short
   WML). This iteration generalizes the same formula to a DAILY update on the
   T1 book's own daily net returns (task instruction), with target = the
   book's own development-window median realized vol, not BSC's 12% (which is
   WML-specific and not transferable to a concentrated 30-stock long-only
   book).

3. **Alpha Architect / Larry Swedroe (2022-08-04), "Avoiding Momentum
   Crashes"** -- secondary synthesis of DM, BSC and Dierkes & Krupski (2022).
   Confirms "long-only momentum strategies are not subject to such deep
   crashes" (their inference from DM's own beta-asymmetry finding). Reports
   Dierkes & Krupski's published crash indicator (bear + rebound + negative
   beta) only cuts the worst monthly momentum crash from 77% to ~25-28%, not
   to zero -- sets a realistic expectation ceiling.

4. **Tommi Johnsen (2025-08-14 Substack), summarizing Butt, Kolari & Sadaqat
   (2024, J. Asset Mgmt)** -- a full regime SWITCH to reversal (long losers,
   short winners) when trailing volatility exceeds its 75th percentile over 5
   years reportedly beats vol scaling at eliminating crash losses, but
   requires shorting -- out of this task's long-only [0,1]-multiplier scope,
   named here as a stronger alternative this iteration does not attempt.

5. **Joseph Pach (2025-03-24 Substack)** -- dated, real evidence: the March
   2025 momentum crash was a fast (3-week), forced-deleveraging event, NOT
   preceded by a slow bear market (S&P 500 erased ~$5.8T peak-to-trough,
   ~40% of it from the prior 50 top performers). Motivates including fast-
   reacting candidates (CG-STOP, CG-MKT-STOP), not just the slow CG-DM
   regime gate.

6. **Paretoquant (2026-07-05 Substack)** -- dated evidence of a >=24%-from-
   peak Goldman Sachs Momentum Basket drawdown inside this iteration's own
   2026 holdout window (exact calendar date ambiguous vs. a paywalled
   2026-02-06 Bloomberg headline describing a similar-magnitude event; not
   used to fit any threshold, only as confirmation to check for in the book's
   own return series).

7. **El Ghorayeb (2021, LUISS thesis), "Momentum and the Covid-19 flash bear
   market"** -- independently re-derives BSC's exact formula (confirming it)
   and tests SHORTENED (4/6-month) bear indicators: alone, they do NOT
   significantly forecast momentum returns; only bear+variance interactions
   do, consistent with DM. Justifies keeping CG-DM at DM's published 24-month
   window rather than shortening it for speed. Explicitly did not backtest
   DM/BSC guards through the actual 2020 COVID crash ("beyond the scope of
   this dissertation") -- a real evidence gap, not filled by this source.

8. **SEC Investor.gov, "Stock Market Circuit Breakers"** -- official
   regulatory source for CG-MKT-STOP's trigger: a real, published Level-1
   market-wide circuit breaker is a 7% single-session S&P 500 decline
   (13%/20% for Levels 2/3), trigger levels recalculated daily from the prior
   close.

**Net read:** the required published mechanisms are real and well documented,
but (a) none of them were built for a long-only, daily-updated book, (b) even
the best published combined mechanism (Dierkes & Krupski's crash indicator)
only cuts crash magnitude by ~2/3, not to zero, and (c) the strongest reported
approach (full switch to reversal) is out of this task's long-only scope. This
sets the honest prior: partial or null results are plausible and must be
reported as such, not reframed as a pass.
