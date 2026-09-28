# Report: h20260928_14b_uncertainty_gate

Card `H-20260928-31`, queue task `T-20260928-14`, registry row
`dir:regime_trust_uncertainty_gate_momentum_ranker`. Full numbers:
`results.json`. Training cache: `cache/ensemble_predictions.npz`,
`cache/train_meta.json`.

## Verdict

**Refuted, round 1. 0 of 3 candidates pass stage 1.** Every candidate fails
every one of its own preregistered stop conditions on the anchor window
(2024-01-08..2026-09-16); no candidate reaches stage 2 (stress window,
G1-G5, K1/K2, DSR are therefore not computed, per the preregistration:
"第二段（只有某个候选第一段全过才做）").

## Model / training

k=15 bootstrap LightGBM regressors, expanding-window annual retrain,
`kt.LGBM_COMMON` hyperparameters (unmodified), 4 cores, row-cap 100,000 rows
per bootstrap fit (disclosed pre-backtest compute cap, see the runner
script's module docstring). First out-of-sample year: **2017** (not the
~2018 the direction-review estimated -- reported exactly, per the
preregistration's instruction to state the actual data-dependent value).
Per-year training pool size: 2017 84,210 rows .. 2026 974,013 rows
(`cache/train_meta.json`). u_i (ensemble prediction std) is finite on 2,170
of 2,692 sessions, starting 2018-01-03.

Modal cost: 3 smoke launches (`t20260928-14b-smoke`, $0.0049+$0.0033+$0.0045,
the first two failed on bugs caught by the smoke test itself, the third
succeeded) + 1 full training launch (`t20260928-14b-train`, $0.0245,
5m48s wall on 4 cores/8GiB). **Total this task: $0.0372**, far under the
$1.50 cap (`python3 scripts/modal_budget.py status`).

## Bug found and fixed before scoring (disclosed, not a threshold change)

The first eval run found `z(t)` finite on only 1 of 2,692 sessions: the
original `trailing_quantile` required literally every one of the 252
trailing positions to have a finite `U(t)`, but `U(t)` has sparse single-day
gaps (held names occasionally missing a prediction around a universe
entry/exit) that appear in nearly every 252-session window in practice. Fixed
to require >=90% coverage of the trailing window (a data-coverage tolerance,
not a change to the window length of 252 sessions or either quantile
threshold, both unchanged) before any candidate was scored against it. See
`tests/test_h20260928_14b_uncertainty_gate.py::test_trailing_quantile_tolerates_sparse_nan_gaps`
for a regression test.

## Candidate results (anchor window, 10 bp unless noted)

| candidate | AUROC | anchor CAGR | anchor Sharpe | anchor max DD | vol-matched control Sharpe (k) | Sharpe gap | stage-1 stop |
|---|---|---|---|---|---|---|---|
| base (unguarded) | n/a | 63.1% | 1.088 | -41.5% | n/a | n/a | n/a |
| U1 (z>0.80, exposure 0.5) | 0.522 | 57.5% | 1.136 | -37.2% | 1.086 (k=0.824) | **+0.050** | yes (a, b1, b2, c) |
| U2 (z>0.90, exposure 0.0) | 0.522 | 40.4% | 0.868 | -35.2% | 1.087 (k=0.855) | **-0.219** | yes (a, b1, b2, c) |
| U3 (top-20% exclusion) | n/a | 24.5% | 0.755 | -27.5% | 1.079 (k=0.529) | **-0.324** | yes (b2, c) |

Stop conditions (from `results.json` `candidates.<id>.stop_conditions`):

- **U1**: `a_auroc_below_min=true` (0.522<0.60), `b1_dd_improvement_below_placebo_plus_5pp=true`
  (real anchor max-DD is 4.3pp *worse* than the unguarded book, i.e. a
  negative improvement, vs. a ~0 placebo median), `b2_sharpe_below_placebo_p90=true`
  (1.136<1.177), `c_owner_rule_fail=true` (gap +0.050<0.10). All four
  conditions independently stop it.
- **U2**: `a_auroc_below_min=true` (same 0.522 AUROC -- U1/U2 share the same
  z(t) series, only the trigger/exposure differ), `b1=true` (6.3pp worse
  drawdown than unguarded), `b2=true` (0.868<1.264), `c=true` (gap -0.219,
  badly negative -- the full de-risk actively hurts risk-adjusted return
  relative to a same-vol SHY blend).
- **U3**: AUROC not applicable (selection candidate, no book-level z(t)
  series, per the preregistration). `b2_sharpe_below_placebo_p90=true`
  (0.755<1.039, the 200-seed random-quintile-drop placebo), `c_owner_rule_fail=true`
  (gap -0.324).

Placebo detail (200 seeds each, `results.json`):

- U1/U2 real anchor max-DD "improvement" vs. the unguarded book is actually
  *negative* (-4.3pp / -6.3pp -- the gate makes the anchor-window drawdown
  worse, not better), while the block/circular-shift placebo distribution's
  median improvement is ~0 (-1.8e-7); real Sharpe sits below the placebo's
  90th percentile for both.
- U3's random-quintile-drop placebo's 90th-percentile Sharpe (1.039) is well
  above U3's own real Sharpe (0.755) -- excluding the model's own
  "most-uncertain" quintile performs *worse* than excluding a random
  quintile of the same size, the opposite of what a real signal would show.

## Interpretation

The trained ensemble-disagreement signal (`u_i`, ensemble std of 15
bootstrap LightGBM cross-sectional rank predictions) carries essentially no
information about the T1 book's own future drawdown risk in this window
(AUROC 0.522, indistinguishable from the 0.50 coin-flip baseline given the
sample size) and no information that beats a placebo that reproduces the
same on/off share or exclusion count by chance. This is a genuine negative
result for THIS specific operationalization (price-volume-only features,
k=15 bootstrap disagreement as the epistemic-uncertainty proxy, on this
book), not evidence that the source paper's own two-level DEUP framework is
wrong on its own data/model -- see `direction-review.json`'s
`remaining_evidence_gap` for what was never independently verified this
round (the paper's own universe, cost model, and exact rank-displacement
predictor architecture).

Distinct failure modes from the two prior refuted local mechanisms on the
same book: H-20260924-02's rule-based guards failed by *reducing* to
de-leveraging or an arbitrary calendar schedule; this trained signal instead
fails because it is not even directionally informative about future
drawdown risk (AUROC essentially 0.50) -- a different, and in one sense a
more basic, failure than "the mechanism works but adds nothing beyond
de-risking."

## Stage 2

Not run. `any_stage1_pass = false` in `results.json`; per the
preregistration, stage 2 (stress window, G1-G5, K1/K2, DSR) is only
performed for a candidate that clears every stage-1 stop condition.

## Files

- `results.json` -- full per-candidate metrics (10bp/20bp, anchor/holdout/
  select/stress), AUROC, placebo distributions, owner-rule k/Sharpe-gap,
  stop-condition booleans.
- `cache/ensemble_predictions.npz`, `cache/train_meta.json` -- trained
  ensemble mean/std predictions and walk-forward metadata.
- `decision-record.md` -- continue/pivot/stop call.
