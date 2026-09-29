# External Brief: h20260928_43_political_etf_rotation

Four sourced findings (queue task's two required URLs + one primary source +
one negative-evidence check; full detail in `direction-review.json.sources`
and `reports/harness/source_cards/h20260928_43_political_etf_rotation.jsonl`):

1. **bit.com knowledge hub** (post, 2026-09-28) -- STOCK Act 30-45 day
   disclosure rule; NANC described as a regulated ETF replicating Democratic
   members' disclosed trades; explicit caveat that disclosure lag may already
   partly price in the lawmaker's information edge.
2. **24/7 Wall St** (post, 2026-04-20) -- NANC +88.49% / GOP +64.31% total
   return since the 2023-02-07 launch (vs S&P 500 +74.70%); explicit
   skeptical claim that NANC's outperformance is an "accidental" byproduct of
   its mega-cap-tech concentration (NVDA/MSFT/AMZN/CRM/GOOGL), not a genuine
   informational edge -- the direct motivation for this batch's
   PLACEBO_BIGTECH menu.
3. **NANC fund methodology** (official docs, via subversiveetfs.com,
   corroborated by etf.com/TipRanks/Trackinsight) -- actively managed,
   disclosure-trading-intensity-weighted, 100-200 holdings, TER 0.72%; NOT a
   price-momentum construction. Confirms this batch's rotation_cell mechanism
   layers a second-order price-trend overlay on top of the funds' own
   first-order disclosure-replica construction.
4. **Eggers & Hainmueller 2013, "Capitol Losses"** (paper, Journal of
   Politics) -- academic negative evidence: no informed-trading or
   above-market-return effect found in actual congressional member
   portfolios 2004-2008 (2-3%/yr underperformance vs. a passive index).
   Grounds the placebo-dominance disqualifier: any POLITICAL-menu edge found
   here must beat the same-grid-cell PLACEBO_BIGTECH candidate, or it is not
   attributed to the political-copy-trade framing.

No candidate rule parameter is derived from any of these four sources beyond
the menu itself (NANC/GOP/MAGA/DEMZ vs. QQQ/XLK/SPY/DIA) -- the mechanism
(cross-sectional top-N momentum rotation with an absolute-momentum-vs-SHY
filter) is `run_h20260918_05_recent_menu.py:rotation_cell`, reused unedited,
exactly as in every prior batch-screening round.
