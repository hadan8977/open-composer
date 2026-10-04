# External Brief: h20261004_pm_midterm_odds_leadlag

Structured entries are in `external-brief.json` (10 sources). Summary:

1. **Goldstein, Li and Wang (2026-09-03, read in full, snapshot includes the Internet Appendix)**: a one-point rise in Polymarket's Trump probability goes with 13 bp of next-day return of Trump trades (2024, in-sample, gross of costs), strategy Sharpe 1.95 (April to November 2024). Single event, no replication found. Table A.1 gives the asset directions used verbatim here.
2. **Transformation (section 3.2)**: 5-day EMA of daily probability change, 60-day rolling percentile, map to [-1, 1], one-day lag; implemented exactly, with the two unstated conventions (EMA adjust flag, rank ties) fixed in the design.
3. **Citigroup via Crypto Briefing (2026-08-17, secondary)**: a Democratic Congress means gridlock and lower yields, which supports the sign of the bond leg.
4. **Polymarket Gamma and Kalshi probes (2026-10-04)**: House (32225) and Senate (32224) control events exist since 2025-07-11 with Republican Yes tokens; Kalshi CONTROLH-2026 and CONTROLS-2026 exist since 2024-11-06.
5. **CLOB /prices-history probe**: public, windowed history, no key.

The author page (https://chenwang.one/) links the PDF, SSRN 7198379 and a summary, but no separate Internet Appendix or replication code (the appendix is inside the PDF snapshot). A web search on 2026-10-04 found no replication of the Goldstein-Li-Wang result and no other test of midterm odds against asset returns. The evidence changed the design in two ways: costs, a 1000-shift gate and a sign-flip placebo are added to what the paper reports, and the paper's single-event claim is tested on a different election rather than extended.
