# Step 7 Hardening Plan - 2026-07-02

## Objective

Fix the harness issues that can make Open Composer draw the wrong conclusion
from ML-assisted strategy research before continuing strategy optimization or
model training.

## Product Boundary

- StrategySpec remains the source of truth.
- Open Composer owns harness engineering: data provenance, validation gates,
  artifact writing, and deterministic local checks.
- Codex/Claude remain the orchestration and research layer.

## Non-Negotiables

- Do not enable live or real-money broker writes.
- Do not weaken strict data, benchmark, cost, or paper-readiness gates.
- Do not promote sample, fixture, cache fallback, or replay-cache evidence as
  paper-ready.
- Do not implement Step 7.B decay monitoring or Step 7.C LLM proposal flows in
  this patch set.
- Do not introduce a new ML dependency.

## Review Lanes

1. Code path and tests
   - `oc strategy promotion-report`
   - `open_composer/research/promotion.py`
   - `open_composer/research/auto_research.py`
   - Promotion and data-tier tests

2. Quant method
   - ML out-of-sample evidence must use stitched purged predictions.
   - Walk-forward evidence must come from ML training folds and window metadata,
     not tiny sliced re-training backtests.

3. Data capability
   - A live Alpaca fetch can earn `research_strict`.
   - Later cache replay must not erase the previously earned strict provenance
     when that tier is explicitly persisted in the generated spec.

4. Product UX
   - CLI should expose `--refresh-data/--use-cache` for promotion reports.
   - Promotion reports should state the ML evidence kind clearly.

## Waves

1. ML promotion semantics
   - Branch ML specs away from generic OOS and sequential walk-forward checks.
   - Use full-window ML backtest as `ml_purged_stitched_oos` evidence.
   - Use `MLTrainingRun.folds` and `window_metadata` for the ML walk-forward
     gate.
   - Add regression tests.

2. Strict data provenance workflow
   - Add `--refresh-data/--use-cache` to `oc strategy promotion-report`.
   - Persist only earned `research_strict` in auto-generated specs.
   - Pass full data profile into the strict-data check.
   - Add regression tests.

3. Verification
   - Run format, lint, focused tests, full tests, and `oc repo check --strict`.
   - Run a targeted promotion smoke on the current QQQ candidate if local data
     and runtime permit.

## Acceptance

- ML promotion OOS details include `evidence_kind=ml_purged_stitched_oos`.
- ML promotion walk-forward details include
  `validation_policy=ml_purged_embargo_walk_forward`.
- ML promotion blocks if fold count or OOS prediction count is zero.
- Non-ML promotion keeps the existing generic OOS and walk-forward behavior.
- `oc strategy promotion-report --refresh-data` is accepted and passes through.
- Auto research persists `data_assumptions.acquisition_tier: research_strict`
  only when the observed data profile earned that tier.
- Cache/sample/fixture evidence remains not paper-ready.
