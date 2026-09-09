# step11_momentum_placeholder_v1

Rule-based placeholder candidate artifact for `portfolio.mode=model_ranking_portfolio`
(Step 11 Wave C, `docs/plan-step-11-ml-first-loop-2026-09-06.zh.md` section 5, item 4).

## What this is

A 12-1 momentum (`momentum_252_21` = `ret_252 - ret_21`, i.e. total return over
the trailing year excluding the most recent month) top-50 equal-weight rule,
scored directly off the Wave A daily feature table
(`data/features/daily/{year}.parquet`). No `model.joblib` -- `config.json`
declares `model_kind: rule_momentum_top_k` and `score_column:
momentum_252_21`, which tells
`open_composer.adapters.execution.model_ranking_target_weights.load_candidate_artifact`
to sort on that column directly instead of loading a fitted estimator.

This is not a strawman. Per the research line's baseline chain
(`reports/research/control/step11-2026-09-06-progress.md`, Wave A / 3.5), this
exact rule (B1) is the current best-of-chain candidate at 4/8 promotion gates
-- ahead of B0 (equal-weight universe, 3/8) and B2 (ridge regression, 3/8,
did not beat B1). It is the honest current best deterministic baseline, used
here so the product target-weight -> whole-share-sizing -> paper-observation
path can be exercised end-to-end before a fitted model candidate exists. B1's
reported 4/8 gate result was computed under close-marked backtest accounting
(hence `features.json:execution=close_marked`); the *product* adapter that
consumes this artifact always targets true next-session-open OPG execution
regardless of what a candidate's own backtest accounting says -- that
product/research timing distinction is documented in
`open_composer/adapters/execution/model_ranking_target_weights.py`'s module
docstring, not something this artifact needs to reconcile.

## Contract

This directory follows the research line's authoritative candidate-artifact
export interface, defined once and frozen in
`reports/research/control/step11-2026-09-06-progress.md` ("Wave B item 5",
commit `93ba159`) specifically so this product-side consumer's loading
contract would not have to change once written:

- `model.joblib` -- a `joblib.dump()` of a `loop.RankingStrategy`-protocol
  object exposing `.score(asof_frame: pd.DataFrame) -> pd.Series` (indexed by
  symbol) directly; the caller (this adapter) does its own top-K/equal-weight
  selection, never `.predict()`. Every real export has one, including
  parameter-free candidates like B0/B1 (a near-stateless object, for
  interface uniformity). **This placeholder has none** -- see below.
- `features.json` -- always carries `feature_columns` (exact training/scoring
  order); this adapter reads only that key. The interface's other keys
  (`experiment_id`, `family`, `model_kind`, `feature_set`, `label_column`,
  `label_horizon_days`, `top_k`, `hedge`, `train_row_dates`, `execution`,
  `refit_through_date`) are metadata the adapter does not act on -- the
  StrategySpec's own `portfolio.*` fields (§ the spec YAML, not this
  artifact) are what actually drive top_k/hedge/rebalance/universe_top_n at
  runtime.
- `config.json` -- the full `ExperimentConfig` (`dataclasses.asdict`).
- `README.md` -- this file.

**This placeholder's one deliberate deviation**: it has no `model.joblib`
(there is nothing to fit -- 12-1 momentum needs no training), so
`load_candidate_artifact` falls back to a rule-based path that exists only in
this adapter, not in the interface above (the interface has no "no model,
just sort a column" case, because every *real* export always has a model).
That fallback reuses the interface's own `model_kind` field with the sentinel
value `rule_momentum_top_k`, plus one genuinely new field this artifact
introduces, `score_column`, naming which `feature_columns` entry to rank on
directly, descending.

## Swapping in the research line's real candidate

Once the research line exports `reports/research/candidates/<experiment_id>/`
(same interface, with a real `model.joblib`), change exactly one field in the
StrategySpec YAML:

```yaml
portfolio:
  candidate_artifact_dir: reports/research/candidates/<experiment_id>
```

Everything else (universe rule, top_k, rebalance cadence, whole-share sizing,
target-weight JSON schema, signal log) is unchanged by that swap.
