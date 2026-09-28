# External Brief: h20260928_04_s3_alt_div_batch1

19 published, long-only, US-listed-ETF rules researched from primary sources
(SSRN papers, issuer/SEC filings, author blogs) before any preregistration or
backtest. Full field-level bindings are in external-brief.json and
reports/harness/source_cards/h20260928_04_s3_alt_div_batch1.jsonl; this file
is the readable summary.

## F1 -- managed futures ETFs held outright

- **DBMF** (iMGP DBi Managed Futures Strategy ETF, inception 2019-05-08): CTA
  hedge-fund replication via liquid futures across equities, fixed income,
  currencies, commodities. Live record since 2019.
- **KMLM** (KFA Mount Lucas Managed Futures Index Strategy ETF, inception
  2020-12-01): tracks the KFA MLM Index, 22 futures across 11 commodities, 6
  currencies, 5 global bond markets, vol-weighted baskets. Live record since
  2020.
- **CTA** (Simplify Managed Futures Strategy ETF, inception 2022-03-07):
  systematic long/short trend on commodity and rate futures, benchmarked to
  the SG CTA Index. Live record since 2022 -- short stress sample, flagged.
- **WTMF** (WisdomTree Managed Futures Strategy Fund, inception 2011-01-05):
  tracks the Diversified Trends Indicator (DTI), the first managed-futures
  ETF. Live record since 2011, the longest of this family.
- **FMF** (First Trust Managed Futures Strategy Fund, inception 2013-08-01):
  actively managed absolute-return managed-futures fund. Live record since
  2013.

## F2 -- Keller/Antonacci/Faber published tactical-allocation rules

- **VAA-G4** (Keller & Keuning 2017, SSRN 3002624): 13612W momentum,
  offensive SPY/EFA/EEM/AGG vs defensive LQD/IEF/SHY, all-or-nothing single
  asset. AllocateSmartly independent replication.
- **DAA-G12** (Keller & Keuning 2018, SSRN 3212862): 12-asset risky universe,
  VWO/BND canary, breadth-scaled cash fraction. Exact T=6/B=2 parameters
  confirmed in TuringTrader's open-source code.
- **PAA-CPR** (Keller & Keuning 2016, SSRN 2759734): 12-asset universe, SMA
  breadth momentum, crash-protection asset rotates IEF/SHY by momentum -- the
  paper's own original CP-rotation variant.
- **HAA** (Keller & Keuning 2023, SSRN 4346906): single TIP canary, 8-asset
  offensive universe with per-asset absolute+relative dual momentum. Primary
  source is co-author JW Keuning's own TrendXplorer announcement post.
- **GPM** (Keller, Butler & Kipnis, SSRN 2606884): correlation-hedged
  momentum score on the same 12-asset universe as PAA, top-3 held.
- **GEM** (Antonacci, 'Risk Premia Harvesting Through Dual Momentum', first
  place 2012 NAAIM Wagner Award): absolute momentum on SPY vs BIL gates
  relative momentum between SPY and EFA, else AGG. Primary paper PDF opened
  directly.
- **GTAA-5** (Faber 2007, SSRN 962461, the most-downloaded SSRN paper ever):
  5 equal 20% sleeves (SPY/EFA/TIP/GSG/VNQ), 10-month SMA timing per sleeve.
- **ADM** (Engineered Portfolio 2018-05-02, the strategy's own originating
  post): 1/3/6-month momentum sum picks SPY vs SCZ, defensive TLT vs TIP.
- **BAA-Balanced** (Keller & Keuning, SSRN 3592671): re-included from
  reports/research/iterations/giants_sweep_20260922/ (candidate
  f5_baa_balanced, anchor Sharpe 0.49, failed the old frozen-gate criterion)
  because the acceptance criterion changed to K1/K2; direction-review.json
  states this justification explicitly.

## F3 -- other alt-diversifier ETFs held outright

- **RPAR** (RPAR Risk Parity ETF, inception 2019-12-13): 4-asset-class
  risk-parity index, ~25% target risk contribution each, quarterly rebalance.
- **UPAR** (UPAR Ultra Risk Parity ETF, inception 2022-01-03): 1.4x-levered
  RPAR via implied financing. Short live record, flagged.
- **NTSX** (WisdomTree U.S. Efficient Core Fund, inception 2018-08-02): 90%
  S&P 500 plus Treasury-futures overlay for ~60% notional bonds.
- **QAI** (NYLI Hedge Multi-Strategy Tracker ETF, inception 2009-03-25):
  rules-based hedge-fund beta replication, fund-of-funds. Longest live
  record in F3.
- **TRTY** (Cambria Trinity ETF, inception 2018-09-10): actively managed
  trend + carry + global risk-parity fund-of-funds.

## What was excluded and why

S1/S2/S3, standalone Defense First, and TLT/GLD/DBC/UUP-vs-SHY trend (queue
task T-20260928-02) are excluded per the brief. Step 10's cross-asset TSMOM
(reports/research/control/step10-w1-cross-asset-trend-2026-09.md, 0/12 pass)
is not duplicated -- none of the 19 candidates here is a pure cross-sectional
TSMOM rotation over the same asset menu; the closest (GTAA, PAA, DAA, GPM,
BAA) all add a canary/breadth crash-protection mechanism Step 10 did not test.

## Data feasibility

All 33 tickers used across the 19 candidates are present in the local SIP
daily archive (data/sip/daily/*/*.parquet) confirmed via duckdb on
2026-09-28, each from either the 2016-01-04 archive floor or the ticker's
own later inception date, through 2026-09-25. No data fetch was required.
