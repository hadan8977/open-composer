# Decision Record: h20260928_15_claude_factor_batch

TEST window computed exactly once, 2026-09-28T16:49:06Z, after Round 2 (F09-
F12) was frozen from Round-1 SELECT-only feedback. See `report.md` and
`results.json` for the full numbers this record summarizes.

## P1 -- claude_factor_batch_screen

- Path: claude_factor_batch_screen (12 Claude-authored factors -- 8 Round 1 +
  4 Round 2 -- vs the symmetric Alpha101/Alpha158/Alpha191/OSAP-price/27-card
  zoo, 259 zoo candidates total)
- Decision: **stop** (refuted for this scope; per queue task T-20260928-15's
  own `done_when`, the batch's SELECT-chosen factor
  (F10_quality_composite_roe_profitability_accruals) must beat the zoo's
  SELECT-chosen factor (zoo_alpha158__CORD60) on BOTH TEST rank IC and TEST
  20bp top-50 monthly book Sharpe. Batch won TEST rank IC (0.0274 vs 0.0217)
  but lost TEST 20bp book Sharpe (0.640 vs 0.879) -- only one of two required
  conditions held.)
- Reason: The "LLM proposes hypotheses, writes factor code, gets IC feedback"
  loop did not beat an already-strong, professionally-curated factor library
  (Alpha158) on our own broad-universe US data after costs. F10 itself is not
  worthless in isolation (TEST ICIR 0.197, positive sign in both SELECT and
  TEST, and Round 2's revision genuinely improved on Round 1's best SELECT
  ICIR: 0.272 vs 0.215) -- the negative result is specifically that the batch
  did not clear the zoo's own best pick, and F10 also fails the project's
  separate, already-frozen K1 info-only promotion bar on both windows (anchor
  0.667 < 1.19, stress 0.482 < 0.65), so no path to paper-readiness exists
  for F10 as constructed. Confidence-vs-TEST-IC Spearman (0.481, n=12, info
  only) is directionally consistent with the preregistered confidence scores
  tracking something real, but that alone does not change the keep_rule
  outcome.
- Next iteration suggestion: `dir:llm_hypothesis_code_backtest_loop` is
  refuted specifically for "one-shot formulaic factor vs a symmetric zoo
  baseline that already includes Alpha158" on this universe/cost basis; it is
  not a blanket refutation of using an LLM to write factor code at all. A
  future reopening would need a genuinely new element -- e.g. a larger
  hypothesis/code iteration budget with intermediate IC feedback per factor
  (not just two frozen rounds), or applying the same loop to a data source
  the existing zoo does not already cover (this batch's insider/short-
  interest-based factors, F01/F08/F09/F12, were the batch's own most novel
  ingredients relative to the zoo and are worth revisiting with a sharper
  hypothesis before reusing this exact construction). Not queued
  automatically; left for the next direction-ranking pass per the mission's
  own "先确定方向，再投入计算" rule.
