---
card_id: H-20260928-15
status: executed, refuted for this scope (round 1, 2026-09-28) -- batch select-chosen F10 beat the zoo's select-chosen CORD60 on test rank IC but lost on 20bp book Sharpe (0.64 vs 0.88)
iteration: h20260928_15_claude_factor_batch
direction_id: dir:llm_hypothesis_code_backtest_loop
---
# H-20260928-15: Claude-authored factor batch vs the existing factor zoo

Queue task T-20260928-15 (`reports/research/control/autonomous-queue.md`).
Dossier: `reports/research/iterations/h20260928_15_claude_factor_batch/`.
Method under test: `dir:llm_hypothesis_code_backtest_loop` (Claude proposes
hypotheses, writes formulaic cross-sectional factor code, revises once from
SELECT-window IC feedback). No DeepSeek, no text labeling.

Status: DONE (refuted for this scope). TEST window computed exactly once
2026-09-28T16:49:06Z (see `reports/research/iterations/
h20260928_15_claude_factor_batch/test-results.json`); decision record
written. Sections below are filled from the raw result files directly, not
from memory.

## Prior art (see direction-review.json for the full, sourced version)

- `dir:llm_hypothesis_code_backtest_loop` already triaged/adopted 2026-09-28
  as the primary LLM-factor-mining pattern; this task is its first execution.
- `dir:llm_formulaic_alpha_mining_price_volume` (AlphaForge/AlphaGen/etc.) is
  not_executable here (GPU/RL) and is not what this task does.
- Three new primary sources opened this round: AlphaAgent (arXiv:2502.16789)
  -- S&P 500 test IC 0.0056, about a quarter of its own China CSI 500 IC
  (0.0212), same method/backend; R&D-Agent(Q) (arXiv:2505.15155) -- NASDAQ 100
  post-2023 OOS test (2024-01..2025-06-30) beats classical factor libraries
  by ~3.5-4x IC (0.0162 vs 0.0040-0.0046); Alpha-GPT (arXiv:2308.00016) --
  human-in-the-loop, no usable post-2023 US number.

## Round 1 (8 factors, preregistered before any IC computed)

See `candidate-manifest.json` and `hypotheses.md` for the full economic
hypothesis, cited source, exact formula, inputs, expected sign and
confidence for each of F01-F08.

## Round 2 (4 factors, added from Round-1 SELECT-only feedback, frozen before any TEST number existed)

F09 (dollar-weighted F01 revision), F10 (undiluted ROE+gross-profitability+
low-accruals composite), F11 (F06 revision, short_volume swapped for F03's
trading-activity surge), F12 (F08 revision, gated to negative-SUE post-report
buying). Full hypothesis/failure-mode/measurement/stop-pivot per factor:
`candidate-manifest.json` and `hypotheses.md`. F10 became the batch's overall
SELECT-chosen winner (ICIR 0.272, beating Round 1's best of -0.215/F08).

## Results

Full numbers: `select-results.json`, `test-results.json`, `k1-info.json`,
`results.json`. TEST rank IC/ICIR below are sign-adjusted (multiplied by
each candidate's own `sign_from_select`).

| | SELECT 21d ICIR (chosen) | TEST 21d rank IC | TEST ICIR | TEST 10bp book Sharpe | TEST 20bp book Sharpe |
|---|---:|---:|---:|---:|---:|
| Batch (F10_quality_composite_roe_profitability_accruals) | 0.272 | 0.0274 | 0.197 | 0.666 | 0.640 |
| Zoo (zoo_alpha158__CORD60) | -0.258 | 0.0217 | 0.223 | 0.946 | 0.879 |

Batch wins TEST rank IC (0.0274 > 0.0217); zoo wins TEST 20bp book Sharpe
(0.879 > 0.640). Both required -- only one holds.

Oracle-best per set (TEST rank IC, hindsight, not the decision rule) with DSR
deflated by set size:

| | candidate | TEST rank IC (sign-adj) | DSR probability | trial count |
|---|---|---:|---:|---:|
| Batch | F04_sue_short_confirmation | 0.0160 | 0.98% | 12 |
| Zoo | zoo_osap_price_broad__coskew_252 | 0.0378 | 17.8% | 259 |

Confidence-vs-TEST-IC Spearman (info only, n=12): **rho = 0.481**.

K1 info-only (`docs/runbook-autonomous-round.zh.md` section 5, not this
task's decision rule): F10's 20bp book Sharpe is 0.667 vs anchor
(2024-01-08..2026-09-17, bar >=1.19) -- **fails**; 0.482 vs stress
(2016-05-02..2023-09-15, bar >=0.65) -- **fails**.

## Verdict

**Refuted for this scope.** Per the queue task's own done_when, the batch's
SELECT-chosen factor must beat the zoo's SELECT-chosen factor on BOTH TEST
rank IC and TEST 20bp top-50 monthly book Sharpe. It won on TEST rank IC but
lost on TEST 20bp book Sharpe, so the method is not supported. Full narrative:
`report.md`; registry row: `dir:llm_hypothesis_code_backtest_loop` in
`reports/research/harvest/directions.jsonl`.
