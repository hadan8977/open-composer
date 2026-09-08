# step11_momentum_placeholder_v1

Rule-based placeholder candidate artifact for `portfolio.mode=model_ranking_portfolio`
(Step 11 Wave C, `docs/plan-step-11-ml-first-loop-2026-09-06.zh.md` section 5, item 4).

## What this is

A 12-1 momentum (`momentum_252_21` = `ret_252 - ret_21`, i.e. total return over
the trailing year excluding the most recent month) top-50 equal-weight rule,
scored directly off the Wave A daily feature table
(`data/features/daily/{year}.parquet`). No `model.joblib` -- `config.json`
declares `strategy_kind: rule_momentum_top_k` and `score_column:
momentum_252_21`, which tells
`open_composer.adapters.execution.model_ranking_target_weights.load_candidate_artifact`
to sort on that column directly instead of loading a fitted estimator.

This is not a strawman. Per the research line's baseline chain
(`reports/research/control/step11-2026-09-06-progress.md`, Wave A / 3.5), this
exact rule (B1) is the current best-of-chain candidate at 4/8 promotion gates
-- ahead of B0 (equal-weight universe, 3/8) and B2 (ridge regression, 3/8,
did not beat B1). It is the honest current best deterministic baseline, used
here so the product target-weight -> whole-share-sizing -> paper-observation
path can be exercised end-to-end before a fitted model candidate exists.

## Contract

`open_composer.adapters.execution.model_ranking_target_weights` reads exactly
two files from a candidate artifact directory:

- `config.json` -- `score_column` (used when there is no `model.joblib`) and
  `strategy_kind`.
- `features.json` -- `feature_columns` (order matters for a fitted model's
  `.predict(X)` call; for this placeholder it is just `["momentum_252_21"]`),
  `beta_column` (default `beta_252_spy`, used only when `hedge:
  spy_beta_hedge`).

A `model.joblib` (fitted LightGBM or ridge object with `.predict(X)`) is
optional; when present it takes priority over `score_column`.

## Swapping in the research line's real candidate

Once the research line exports `reports/research/candidates/<experiment_id>/`
(same `config.json`/`features.json` contract, plus `model.joblib`), change
exactly one field in the StrategySpec YAML:

```yaml
portfolio:
  candidate_artifact_dir: reports/research/candidates/<experiment_id>
```

Everything else (universe rule, top_k, rebalance cadence, whole-share sizing,
target-weight JSON schema, signal log) is unchanged by that swap.
