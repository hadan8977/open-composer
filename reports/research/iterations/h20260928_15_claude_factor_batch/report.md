# h20260928_15_claude_factor_batch

T-20260928-15: does "an LLM (Claude) proposes hypotheses, writes formulaic
cross-sectional factor code, gets IC feedback" beat the existing Alpha101/
Alpha158/Alpha191/OSAP-price/rank-card factor zoo on the project's own broad
U.S. equity data. Method under test: `dir:llm_hypothesis_code_backtest_loop`.
Full numbers: `select-results.json`, `test-results.json`, `k1-info.json`,
`results.json` (all raw, this file only narrates them).

SELECT window 2016-06-01..2023-12-29 (screening only). TEST window
2024-01-02..2026-09-08 (end date aligned to Alpha158's coverage ceiling, the
same for batch and zoo alike). Universe: top-1000-by-ADV, `load_market`.
Sign fixed from each candidate's own SELECT-window mean rank IC.

## Head-to-head: SELECT-chosen batch factor vs SELECT-chosen zoo factor

keep_rule (candidate-manifest.json): the batch's SELECT-chosen factor must
beat the zoo's SELECT-chosen factor on BOTH TEST rank IC and TEST 20bp
top-50 monthly book Sharpe. `test_21d rank IC`/`ICIR` below are sign-adjusted
(multiplied by `sign_from_select`) so both rows are read "in the direction
each side's own SELECT window said to trade it."

| | SELECT 21d ICIR (chosen) | TEST 21d rank IC | TEST 21d ICIR | TEST 10bp book Sharpe | TEST 20bp book Sharpe |
|---|---:|---:|---:|---:|---:|
| Batch: F10_quality_composite_roe_profitability_accruals | 0.272 | 0.0274 | 0.197 | 0.666 | **0.640** |
| Zoo: zoo_alpha158__CORD60 | -0.258 | 0.0217 | 0.223 | 0.946 | **0.879** |

- TEST rank IC: batch (0.0274) > zoo (0.0217) -- **batch wins**.
- TEST 20bp book Sharpe: batch (0.640) < zoo (0.879) -- **zoo wins**.
- Both required for "supported" -- only one holds.

zoo_alpha158__CORD60 (Alpha158's 60-day correlation-of-price-and-volume
factor) covers 86.7% of universe name-days in the TEST window; its
max |rank corr| against any of the 12 batch factors is 0.075 (vs F10) --
genuinely different signal, not a near-duplicate of the batch's winner.

## Oracle-best per set (TEST rank IC, hindsight -- not the decision rule; info only), DSR deflated by set size

| set | candidate | TEST 21d rank IC (sign-adj) | TEST 21d ICIR (sign-adj) | TEST 20bp book Sharpe | trial count | DSR probability |
|---|---|---:|---:|---:|---:|---:|
| Batch | F04_sue_short_confirmation | 0.0160 | 0.259 | 0.931 | 12 | 0.98% |
| Zoo | zoo_osap_price_broad__coskew_252 | 0.0378 | 0.308 | 1.215 | 259 | 17.8% |

Both oracle-best DSR probabilities are well under any usable significance
bar (batch's own hindsight pick is *less* credible than the zoo's, despite
scoring a higher raw book Sharpe, because it is one pick out of only 12 vs
one pick out of 259 -- the deflation direction that matters here cuts
*against* trusting either hindsight pick, batch included).

## Confidence-vs-TEST-IC Spearman (info only, not the decision rule)

Across the 12 preregistered batch factors, Spearman rank correlation between
each factor's preregistered confidence score (candidate-manifest.json,
written before any IC was computed) and its realized TEST 21d rank IC
(sign-adjusted): **rho = 0.481** (n=12). Directionally consistent with
confidence tracking realized strength, but not to be read as validated --
n=12, not independently significant, and this project's own hypotheses.md
never set a pass/fail bar on it. Per-factor rows: `results.json`'s
`confidence_vs_test_ic_spearman_info_only.rows`.

## K1 info-only (`docs/runbook-autonomous-round.zh.md` section 5; not this task's decision rule -- a different, already-frozen promotion bar reused for context only)

Batch-chosen factor (F10, sign +1) 20bp top-50 book Sharpe vs the K1 bar:

| window | dates | 20bp Sharpe | bar | pass? |
|---|---|---:|---:|---|
| anchor | 2024-01-08..2026-09-17 | 0.667 | >=1.19 | **no** |
| stress | 2016-05-02..2023-09-15 | 0.482 | >=0.65 | **no** |

F10 fails K1 on both windows -- consistent with, not contradicting, the
main verdict below (the TEST-window book Sharpe of 0.64 is well short of a
promotable bar regardless of how it compares to the zoo).

## Verdict

**Refuted for this scope.** Per the queue task's own `done_when`: the
batch's SELECT-chosen factor must beat the zoo's SELECT-chosen factor on
BOTH TEST rank IC and TEST 20bp top-50 monthly book Sharpe. It beat the zoo
on TEST rank IC (0.0274 vs 0.0217) but lost on TEST 20bp book Sharpe (0.640
vs 0.879). "An LLM (Claude) that proposes hypotheses, writes formulaic
factor code, and revises once from SELECT-window IC feedback" did not beat
the existing factor zoo on this universe/period/cost basis. The batch's own
best factor (F10, an undiluted ROE+gross-profitability+low-accruals
composite) is itself a reasonable quality signal (TEST ICIR 0.197, positive
in both SELECT and TEST) -- the negative result is about the *batch beating
the zoo*, not about F10 having zero value on its own. Round 2's revision
step (replacing a diluting second ingredient with a plain three-way quality
composite) did improve on Round 1's own SELECT ICIR (0.272 vs the best
Round-1 factor's 0.215), consistent with the SELECT-feedback loop doing
something, just not enough to clear an already-strong zoo (led by Alpha158,
a large, mature, professionally-curated factor library).
