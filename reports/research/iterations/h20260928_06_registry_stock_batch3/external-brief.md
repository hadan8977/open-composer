# External brief: h20260928_06_registry_stock_batch3

Nine sources were opened this pass to back the ten testable-now candidates and to
justify three reclassifications (needs_modal / near-duplicate skip). See
`external-brief.json` for the full structured list and `direction-review.json`
plus `reports/harness/source_cards/h20260928_06_registry_stock_batch3.jsonl` for
the four quote-verified snapshot bindings (paperswithbacktest concentrated
momentum, paperswithbacktest skewness/52-week-high, paperswithbacktest intraday
time-series reversal, alphactor overnight-edge) plus the arXiv AEGIS abstract.

Key findings that changed the candidate matrix from the harvest's own claims:

1. Opening the actual paperswithbacktest "Intraday time series reversal" page
   showed the real mechanism is "overnight return predicts the first half-hour
   return", not a same-day open/close reversal as the harvest claim's summary
   implied. That needs intraday minute bars across the broad universe, which
   this box does not have (only SPY in `data/features/minute_panel`), so this
   row moved to needs_modal alongside signed_jump_variation and
   end_of_day_reversal, per the owner's Modal-lane addendum.
2. The AEGIS paper cited by a secondary, unverified blog (trendsandbreakouts.com)
   was independently located on arXiv (2604.09060, Chakraborty & Singh, April
   2026) and its abstract matches the blog's mechanism description. Rather than
   discard the row for weak sourcing, this round tests only its disclosed step 1
   (volatility-adjusted momentum ranking) as `vam_momentum_k50`, explicitly
   dropping the minimax-correlation diversification and SLSQP Sortino allocation
   steps as portfolio-construction work outside this batch's score-and-top-k
   engine.
3. Two sources (the Brav/Jiang/Partnoy/Thomas 2008 PDF and the Pigorsch/Schafer
   2024 ScienceDirect page) were opened and read but could not be quote-bound
   into `direction-review.json`'s verified-source schema: the PDF's compressed
   text stream defeats the naive HTML-tag-stripping snapshot verifier, and the
   ScienceDirect page returned a cookie/paywall shell with no extractable
   abstract text. Both are disclosed here rather than silently dropped, and
   their content is used only in prose (existing_solution_comparison /
   cost_and_execution_assumptions), not as a quote-verified numeric claim.

Fourteen of the batch's rows (see `report.md`) are classified not-testable-now
with a specific blocker each (non-US market, needs a short leg, proprietary or
undisclosed data, or a near-duplicate of an already-refuted local mechanism);
three are needs_modal pending the Modal cloud lane.
