# Decision Record: h20260929_71_wikipedia_pageviews

## Path

wikipedia_pageview_weekly_attention (4 candidates behind an IC gate)

## Decision

**Stop.** Refuted at the preregistered weekly RankIC gate (lag 0, median across 5 weekday offsets), source `results.json`:

- (a) 2024-01-08 onward: IC -0.0030, Newey-West t -0.53 (need IC > 0 and t >= 2.5) -> fail.
- (b) 2016-07 to 2023-12: IC +0.0050, t 1.40 -> sign condition met (positive), but t is below 2 and current-constituent survivorship applies.
- (c) real 2024+ IC -0.0030 vs placebo p95 +0.0058 (81% of 500 title shuffles are at or above the real value) -> fail.

Lag 1 agrees (2024+ IC -0.0032, t -0.60; 2016-2023 IC +0.0037, t 1.04). The slow control VC28_90 is also null (2024+ IC -0.0017, t -0.28). Coverage: 501 list tickers, 501 series fetched, 467 used after dropping 27 rename-break series (>90% fall of the 28-day mean within 90 days), 4 duplicate-title tickers and 3 tickers absent from SIP (BF.B, BRK.B, IVZ). No candidate was built; `trial-ledger.jsonl` records the 4 candidates as `not_evaluated_ic_gate_failed`.

## Reason

The frozen gate failed on two of three conditions in the recent window that matters for near-term use. The published record (DJIA 2004-2012, 2011-2014 classifiers, 2016-2023 secondary summary of Pyun 2025) is not reproduced for S&P 500 names after a close-signal, next-open fill: 2016-2023 shows a small positive IC that is not significant, and 2024 onward shows none. Consistent with the local null result for news-count attention (`dir:news_attention_features`). The gate, candidates and placebo count were not changed after seeing results.

## Next iteration suggestion

Stop; do not add variants (other windows, mirror, sector-neutral versions) on the same page-view series. Reopen only with point-in-time constituent history including delisted names, or a vendor page-view history with bot filtering, and state the difference. Status: `workflow_pass` true, `research_pass` false, `llm_contribution_pass` false, `paper_ready_pass` false.
