# External brief: h20260928_23_s1_rebalance_timing

## Objective

Measure S1's rebalance timing luck across 5 weekly signal-day offsets, mirroring H-20260928-01's S3 check, so the paper renewal and any future live-pilot sizing use a date-neutral expectation. Purely descriptive: no offset is adopted.

## Reused prior art (H-20260928-01)

This round asks the identical descriptive question H-20260928-01 already validated and ran for S3
(dir:s3_rebalance_timing_luck_tranching), against S1 instead. The rebalance-timing-luck
literature review is not repeated; the same four verified source cards are cited (see
`direction-review.json` and `reports/harness/source_cards/h20260928_01_s3_rebalance_tranching.jsonl`):

- Concretum Group 2025, "The Tranching Dilemma": 348 bp best/worst trading-day CAGR gap on a
  concentrated monthly momentum book.
- Hoffstein, Faber, Braun (Panoptica/SSRN): factor indices carry >100 bp/yr rebalance timing luck,
  larger for concentrated, less-frequently-rebalanced portfolios -- both S1 (weekly, 2-of-11) and
  S2 (monthly, 2-of-6) qualify.
- CXO Advisory summary of Hoffstein/Sibears/Faber: staggering N sub-portfolios suppresses timing
  luck by roughly 1/N -- not used here (no tranching), only cited for the underlying mechanism.
- Allocate Smartly: tranched TAA portfolios keep mean return, shrink dispersion.

## What is new here

Only the local computation: run the frozen `scripts/run_h20260922_05_salvage.py` engine
(`sleeve_weights`, `run_cell`) for S1 with its signal date shifted across its own rebalance
cycle, report CAGR/Sharpe/max DD as min/median/max across offsets per window, and O00's (live)
rank. No new external research was required or performed; `oc research directions check` found no
prior local test for S1 specifically.
