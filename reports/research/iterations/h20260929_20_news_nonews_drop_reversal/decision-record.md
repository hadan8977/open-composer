# Decision Record: h20260929_20_news_nonews_drop_reversal

## P1 -- News-vs-no-news drop reversal/drift (12 candidates)

- Path: P1, the single path in `search-space.md` (DROP_NN_* and
  DRIFT_NEWS_* families).
- Decision: **stop** (refuted). All 12 preregistered candidates fail the
  decision bar in TEST (2024-01-08..2026-09-17): the best calendar Sharpe is
  0.67 (DROP_NN_D8_H5, vs the 1.19 bar) and every diversifier edge vs S3 is
  negative (best -0.57, vs the +0.05 bar). The long no-news leg's hit rate is
  below 50% (42.9%-45.1%, the opposite sign from the reversal hypothesis).
  Both preregistered placebos (shuffled news/no-news label, redated event
  date) show no candidate's real trade-level average return beats its
  placebo with the required t>=2; several are directionally worse than
  their own placebo. DSR with the full 12-candidate trial count is <=0.178
  for every long candidate and <0.0002 for every short candidate. See
  `results.json`, `trial-ledger.jsonl` and `report.md` for the full table.
- Reason: the mechanism (Chan 2003 / Savor 2012 news-vs-no-news drift and
  reversal) does not survive ADV-tiered transaction costs and the 1%/year
  short-borrow assumption in the 2024-2026 US top-1500-ADV universe at any
  of the 12 preregistered D/h combinations, and the placebo comparisons show
  the apparent small positive Sharpe cells (e.g. DROP_NN_D8_H5) are not
  attributable to the event date or the news label specifically. One short
  candidate (DRIFT_NEWS_D5_H3) also realized a catastrophic single-trade
  loss (-1757%, WOLF, 2025-09-26 entry) from a real Chapter-11
  reorganization-driven price discontinuity -- a genuine tail risk for
  unhedged single-name shorts of already-distressed names, documented in
  `report.md`, not a data or code bug (verified against the raw
  open/close series).
- Next iteration suggestion: do not re-tune this same D/h grid on this same
  daily-bar universe/window (per the preregistered stop condition in
  `direction-review.json`). A future attempt at this mechanism family would
  need a genuinely different information modality (e.g. intraday price
  action, options-flow-implied information content, or a broader all-item
  8-K feed instead of the item-2.02-only earnings feed used here) rather
  than a parameter retune of this same daily close-to-close design.

- Coordinator correction (2026-09-29, main session): the WOLF -1757% trade
  is a ticker-splice artifact, not a real short loss. Old WOLF common
  (156,479,390 shares) was cancelled on 2025-09-29 and old holders received
  1,306,896 new shares pro rata (+ up to 871,287 contingent), about
  0.0084-0.0139 new shares per old share (Wolfspeed 10-Q, SEC EDGAR). A
  short opened at 1.54 would have owed about $0.24-0.40 per old share at the
  2025-09-30 close, i.e. a +74% to +84% gain before borrow fees. The
  verdict is unchanged: trimmed-mean and ex-artifact per-trade statistics
  in report.md ("协调者更正") keep all 12 candidates far below the bar.
