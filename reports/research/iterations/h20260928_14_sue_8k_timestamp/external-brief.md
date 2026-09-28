# External brief: h20260928_14_sue_8k_timestamp

Direction `dir:pead_xbrl_sue_filing_date` (refuted) /
`dir:pead_xbrl_8k_llm` (triaged, accounting half), from
`reports/research/harvest/directions.jsonl` and
`reports/research/control/registry-backfill-2026-09-28.md` Job B. Full
source list with quotes: `external-brief.json`; the subset bound to a
verified snapshot and quote-matched source card: `direction-review.json`.

## What was reused, unchanged

The SUE construction (Foster-Olsen-Shevlin 1984 seasonal random walk) and
the PEAD mechanism (Bernard-Thomas 1989) are the same foundational
literature the refuted card already cited; this iteration does not
re-derive them, only re-confirms them (WebSearch summaries of the Stanford
GSB working-paper listing and the RePEc/IDEAS listing respectively, since
the original 1984/1989 journal PDFs are paywalled). `scripts/
build_sec_xbrl_fundamentals.py::sue_series` (unchanged) still computes
`sue_eps`; only its `visible_at` join changes in this iteration.

## What was newly confirmed this pass

- **Battalio & Mendenhall (2006), "Post-Earnings Announcement Drift: Timing
  and Liquidity Costs"** (already source-carded in this repo,
  `reports/harness/source_cards/profit_route_challenge_20260921.jsonl`,
  claim_id `pead_cost_counterpoint`): reconfirmed live today via a fresh
  Crossref fetch of the same DOI. Actual quote data 1993-2002: trading
  immediately on the announcement rather than waiting until market close
  recovers hedged-portfolio returns >=14%/yr after costs -- direct,
  independent, published evidence that the single variable this iteration
  changes (visible_at timing) is the economically load-bearing one, not a
  cosmetic change.
- **Subrahmanyam's PEAD replication, Feb 2001-Dec 2024** (UCLA Anderson
  Review's own published brief, fetched live today): all-stocks
  t-statistic 2.18 (barely significant), 1.43 (not significant) once
  microcaps are excluded. This matches, and does not add to, the caveat the
  refuted card's own rationale already carried -- kept as a reminder that
  any admission here should be read as a microcap-tilted effect, not a
  large-cap rediscovery.
- **SEC Form 8-K Item 2.02 and the EDGAR submissions API**: confirmed via
  live fetches today (sec.gov's own Form 8-K instructions PDF, reachable but
  not machine-text-extractable this pass; sec.gov's own EDGAR API overview
  page; corroborated by a third-party dataset description, sec-api.io) that
  Item 2.02 filings are specifically earnings-release announcements
  (furnished, not filed, Exhibit 99 text) and that `data.sec.gov`'s
  submissions API is the correct, official, no-auth JSON source -- the same
  API this repo's own `scripts/build_earnings_events.py` already reads,
  including its already-verified Eastern-time handling of
  `acceptanceDateTime`.

## What was NOT re-derived

This iteration does not re-run the literature search that originally
motivated `dir:pead_xbrl_8k_llm` (`H-20260916-06`) or the SEC-XBRL data
source review (`I-20260923-08`); both are cited by path rather than
re-fetched, per the mission's "reuse fresh verified knowledge" rule -- the
only genuinely new question this iteration answers is empirical (does the
timing fix clear the admission rule), not literature-level.

## Local data facts (see `data-feasibility.json` for full detail)

Left table (`data/features/sec_fundamentals_daily`): unchanged, 2016-01-29+,
sue_eps event rows identical to the refuted card's own 4,639 events. Right
table (`data/features/earnings_events`): 16,015 rows with an Item-2.02 tag,
1,448 distinct tickers, `acceptance_utc` 2024-01-02 to 2026-09-17,
14,923 with fetched exhibit text (acceptance_utc itself is populated for all
16,015 regardless of exhibit-fetch status). The join is therefore bounded to
2024-2026, disclosed as the main evidence gap in `direction-review.json`.
