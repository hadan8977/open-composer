# Step 11 Wave B: model-ranking candidate report (B0 -> B3)

Status: **DRAFT / IN PROGRESS** -- skeleton written 2026-09-09 while the full
9-year B3 walk-forward runs in the background; numbers below are filled in
as each run lands (see `reports/research/control/step11-2026-09-06-progress.md`
for the live status of which runs are done vs. still in flight). Do not cite
any number in this file marked `TBD` -- it is a placeholder, not a zero or an
estimate.

Plan reference: `docs/plan-step-11-ml-first-loop-2026-09-06.zh.md` sections
3.5 and 4. Ledger: `reports/research/ledger/experiments.jsonl`.

## 1. Methodology (fixed across every row in this report)

- **Universe**: point-in-time liquid-name universe, monthly cohorts (`open_composer/research/features/universe.py`), full 2016-2026 union backing the panel.
- **Rebalance**: weekly (Friday signal date -> next trading session), top **K=50** equal-weight, long-only and SPY-beta-hedged market-neutral variants both reported for every row.
- **Costs**: 10bps/side base, 25bps/side stress (both reported by the gate evaluation; this report's headline numbers are base-cost unless noted).
- **Walk-forward**: anchored expanding window, retrained/rescored once per test year 2018-2026 (9 folds), embargo = label horizon. No test year's weights ever come from a fit that saw that year's data (`open_composer/research/kernel/loop.py::build_weight_schedule`).
- **Execution**: `close_marked` (close-to-close, one-session-lagged approximation) unless a row is explicitly marked `next_open` (open-to-open, one-bar-later fill -- see section 6). **Promotion decisions use `next_open` only; the grid search itself (which cell/model wins) was run under `close_marked` for methodological consistency across all candidates, per the Step 11 ledger's Wave B item 4 section.**
- **Gate contract**: `config/promotion/unlevered-family-paper-tier-gates.json` (8 gates, all against a volatility-matched SPY benchmark unless noted): `cagr_excess_vol_matched_benchmark >= 5pp`, `sharpe_excess_bil > 1.0`, `dsr_probability >= 0.5`, `max_drawdown >= -35%`, `mar >= 0.6`, `positive_fold_fraction >= 0.6`, `benchmark_vm_capture_ratio >= 1.0`, `benchmark_vm_downside_capture <= 1.0`.
- **Training-row convention** (`train_row_dates`, recorded per-config, not a silent constant): `"all"` uses every trading day in the anchored window; `"rebalance_dates"` uses only the weekly cross-sections the model is ever scored on (~1/5 the rows). Reported separately, not blended, so the comparison is never confounded with the feature-set comparison.
- **B3 grid**: label horizon {5, 10, 21} x tree depth {3, 6} = 6 cells per feature set (daily-only, daily+intraday), selected per test year by validation-year (the training window's own last year) mean rank IC -- test-year metrics never influence cell selection.

## 2. Headline comparison (same basis: 2018-2026 OOS, base cost, long-only unless noted)

**Caveat added 2026-09-10 (Step 13 Track M bisection, commit `30879b4`)**:
every return series in this report was computed before that commit, under
`open_composer/research/kernel/loop.py::returns_from_weight_schedule`'s
pre-fix formula, which recomputed each day's portfolio return with the
*same*, never-updated target weight for the whole holding window --
mathematically equivalent to rebalancing the book back to those exact
weights every trading day, not buying once at signal time and holding.
That formula **overstates** compounded returns for any book with real
day-to-day return dispersion (proved in
`tests/test_kernel_loop.py`'s new regression tests); it never understates
them. Every row below already fails its gates on a negative CAGR
excess/Sharpe basis, so a clean re-run under the fixed formula cannot flip
any verdict from fail to pass -- it can only make an already-negative
number more negative. A clean re-run of this report's rows is deferred
(not scheduled this round); the numbers below should be read as an
upper bound on how these candidates actually performed, not the corrected
figure. `scripts/evaluate_cross_sectional_momentum_liquid500.py` (Step 10)
independently implements the same pre-fix, constant-weight-per-day
formula and has the same known issue -- not changed as part of this fix.

| Candidate | Feature set | `train_row_dates` | CAGR excess (vol-matched SPY) | Sharpe-ex-BIL | Max DD | DSR prob. | MAR | Capture ratio | Downside capture | Positive-fold frac. | Gates x/8 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 equal-weight universe | daily_only | all | -5.58% | 0.4596 | -41.3% | TBD | 0.26 | 0.966 | TBD | TBD | 3/8 |
| B1 12-1 momentum top50 | daily_only | all | -4.95% | 0.5777 | -58.3% | TBD | 0.33 | 1.003 | TBD | TBD | 4/8 |
| B2 ridge top50 | daily_only | all | -4.66% | 0.4768 | -37.8% | TBD | 0.28 | 0.971 | TBD | TBD | 3/8 |
| B2 ridge top50 | daily_only | rebalance_dates | -3.32% | 0.5612 | -45.5% | TBD | 0.31 | 0.992 | TBD | 3/8 |
| B2 ridge top50 | daily_plus_intraday | rebalance_dates | **not run** (see caveat below) | -- | -- | -- | -- | -- | -- | -- | -- |
| B3 LightGBM grid | daily_only | rebalance_dates | **-10.15%** | **0.4175** | **-57.9%** | fail | **0.198** | 0.972 | 0.737 | **0.778 (7/9)** | **2/8** |
| B3 LightGBM grid | daily_plus_intraday | rebalance_dates | **-13.13%** | **0.3425** | **-57.2%** | fail | **0.152** | 0.953 | 0.745 | **0.556 (5/9)** | **1/8** |

Market-neutral (SPY-beta-hedged) variants for every row above:

| Candidate | Feature set | `train_row_dates` | CAGR excess | Sharpe-ex-BIL | Max DD | Gates x/8 |
|---|---|---|---:|---:|---:|---:|
| B0 | daily_only | all | -12.40% | -0.7364 | -35.0% | 1/8 |
| B1 | daily_only | all | -26.23% | -0.0234 | -73.9% | 1/8 |
| B2 | daily_only | all | -22.52% | -0.7174 | -70.1% | 1/8 |
| B2 | daily_only | rebalance_dates | -21.53% | -0.4321 | -66.3% | 1/8 |
| B2 | daily_plus_intraday | rebalance_dates | **not run** | -- | -- | -- |
| B3 | daily_only | rebalance_dates | **-17.99%** | **-0.1946** | **-53.2%** | **0/8** |
| B3 | daily_plus_intraday | rebalance_dates | **-23.49%** | **-0.2921** | **-71.3%** | **1/8** |

**B2 daily_plus_intraday rebalance_dates was not completed.** Two attempts
were made (2026-09-08 and 09-09); both died without producing a ledger
record (one under an out-of-policy `--mem 2.0G` cap whose real death cause
was never captured, one that was superseded by prioritizing the B3 grid
under the Thursday deadline). This is deprioritized behind the B3 grid per
explicit instruction and is recorded here as **not done**, not silently
dropped -- if time remains after the B3 daily_plus_intraday grid, placebo,
next_open comparison, and candidate export are all in, this is the next
item, not before.

**Caveat on the B3 daily-only smoke-test ledger entry**
(`step11_b3_lightgbm_grid_daily_only_SMOKE_2fold`, `config_hash
d8a778eb7457d52e`, `test_years=[2025,2026]`, marked `"smoke_test": true` in
the ledger): 45% CAGR excess / -17% drawdown / 7/8 gates was a **2-fold
smoke test** run only to validate the pipeline before paying for the full
9-year walk-forward. It is **not comparable** to the full 2018-2026 result
above (`step11_b3_lightgbm_grid_daily_only`, `config_hash
6a61c089670ff4aa`) and must never be cited alongside it or the B0-B2 rows.

## 3. B3 vs. B1/B2: did the model beat the baseline chain?

**No. Neither B3 feature set beats B1, on any dimension that matters, and
daily_plus_intraday is worse than daily_only, not better.**

| Metric | B1 (12-1 momentum, long-only) | B3 daily-only (long-only) | B3 daily+intraday (long-only) | Either B3 wins? |
|---|---:|---:|---:|:---:|
| CAGR excess (vol-matched SPY) | -4.95% | -10.15% | -13.13% | no |
| Sharpe-ex-BIL | 0.578 | 0.417 | 0.342 | no |
| Max drawdown | -58.3% | -57.9% | -57.2% | ~tie (both B3 marginally less bad) |
| MAR | 0.333 | 0.198 | 0.152 | no |
| Capture ratio | 1.003 | 0.972 | 0.953 | no |
| Positive-fold fraction | -- | 0.778 (7/9) | 0.556 (5/9) | no |
| Gates passed | 4/8 | 2/8 | 1/8 | no |

B3's raw CAGR (daily-only 11.5%, daily+intraday ~8.7%) looks superficially
reasonable in isolation, but every relative-to-benchmark measure is worse
than B1's, and B1 already does not clear the promotion bar either -- B3 is a
**regression from the chain's already-negative standing champion**, not an
improvement that merely falls short. Adding intraday features made every
single one of these numbers worse, not better, and roughly halved the
positive-fold fraction (7/9 -> 5/9) -- more features did not help here, they
actively hurt out-of-sample. The two-fold smoke test's much more flattering
daily-only numbers (45% CAGR excess, 7/8 gates) were an artifact of testing
on only the two most favorable, most-recent years and must not be read as
"B3 nearly worked."

**Chain standing after Wave B**: B1 (12-1 momentum, long-only, 4/8 gates)
remains the best candidate produced by this round's baseline chain plus the
B3 grid, in both feature sets tested. Per plan section 5 item 4, it is
exported as the current-best candidate regardless (section 9) -- this
negative result for B3 does not block that export.

**Suspiciously high validation-year rank IC prompted a leakage check, and
the full daily_plus_intraday grid made this more urgent, not less**: the
daily-only smoke test's validation IC (0.08-0.17, 2 years only) already
looked high for a rank-IC prediction target. The full 9-year
daily_plus_intraday grid is worse: **every single validation year from
2017 through 2025 selected the same cell (`h21_d6`, horizon 21/depth 6) at a
mean rank IC between 0.15 and 0.40** -- IC that high, that consistently, for
this many independent years, is not a pattern genuine cross-sectional equity
return prediction produces. See section 4's placebo result (both feature
sets) before trusting any of the numbers in this report.

**Update 2026-09-09 14:1x UTC -- the leak flagged above is root-caused,
fixed, and reverified (commit `bb21f27`; full mechanism and numbers in
section 4).** The daily_only and daily_plus_intraday CAGR/Sharpe/MAR/gate
numbers in the table above were both produced by the grid's pre-fix, leaky
cell-selection path, so neither verdict should be read as "the best cell for
that feature set, honestly measured" -- only as "B3, run through a
since-fixed selection process, did not beat B1." **daily_plus_intraday
stays closed** as a feature set regardless: it was already the worse of the
two on every metric in the table above even under the shared pre-fix bias,
consistent with the Step 13 plan's (section 3.1) decision to not use
intraday features. Only the **daily_only** grid is queued for a clean
re-run under the fix, and only for test years **2024-2026** (the Step 13
recent-regime window this round actually targets, not the original
2018-2026 range) -- **later, when the box is free**; it is not run in this
session.

## 4. Placebo (label-shuffle) check

Plan requirement: shuffle **every** label horizon column (`label_rank_5`,
`label_rank_10`, `label_rank_21` -- not just the outer `label_column`; see
the bug note below) within each date's cross-section (destroys any true
feature-label relationship, preserves the marginal distribution the model
sees), refit the same `GridSelectedLightGBMStrategy` machinery on one
anchored window (test year 2026), score the following validation year, and
confirm the mean validation rank IC is approximately zero. Threshold, per
`config/promotion/recent-regime-high-return-gates-v2.json`'s
`ml_placebo_rank_ic_abs_maximum`: **clean means \|IC\| < 0.02.**

`uv run python scripts/run_b3_grid.py --placebo-only --placebo-feature-set {daily_only,daily_plus_intraday}`

**Verdict: FAILED pre-fix for both feature sets. Leakage confirmed** (both
were run through the same leaky `GridSelectedLightGBMStrategy.fit()`
path) **-- root-caused and fixed the same day, commit `bb21f27`; see the
"Root cause" paragraph below for the corrected, post-fix daily_only
numbers.**

| Feature set | Selected cell (2026 validation) | Placebo mean rank IC (shuffled labels) | Clean (\|IC\| < 0.02)? |
|---|---|---:|:---:|
| daily_only (pre-fix) | h5_d6 | **0.1709** | **no -- 8.5x the threshold** |
| daily_plus_intraday (pre-fix) | h21_d6 | **0.2057** | **no -- 10.3x the threshold** |
| daily_only (post-fix, `bb21f27`) | h21_d6 | **0.0013** | **yes -- ~15x inside the threshold** |
| daily_plus_intraday (post-fix) | -- | not yet rerun (see "what happens next" below) | -- |

Full per-cell breakdown, daily_only pre-fix (every cell is well above
threshold, not just the selected one -- this is not an artifact of which
cell happened to be picked):

| Cell | Placebo validation rank IC (pre-fix) |
|---|---:|
| h5_d3 | 0.0539 |
| h5_d6 | **0.1709** (selected) |
| h10_d3 | 0.0462 |
| h10_d6 | 0.1590 |
| h21_d3 | 0.0494 |
| h21_d6 | 0.1690 |

Full per-cell breakdown, daily_plus_intraday pre-fix (same pattern -- every
cell elevated, deeper trees worse):

| Cell | Placebo validation rank IC (pre-fix) |
|---|---:|
| h5_d3 | 0.0639 |
| h5_d6 | 0.2016 |
| h10_d3 | 0.0590 |
| h10_d6 | 0.2050 |
| h21_d3 | 0.0618 |
| h21_d6 | **0.2057** (selected) |

With labels shuffled within each date's cross-section -- destroying any real
feature-label relationship by construction -- a correctly-isolated pipeline
should produce IC statistically indistinguishable from zero. Every one of
the six cells instead lands between 0.05 and 0.17, and the deeper-tree cells
(`_d6`) are consistently ~3x the shallower (`_d3`) ones at the same horizon,
which is itself informative: **this looks like a systematic property of the
pipeline, not sampling noise around zero.** This means the B3 grid's own
rank-IC-based cell selection (picking the (horizon, depth) cell by trailing
validation-year rank IC) is itself contaminated -- it may be selecting
cells by however strongly a leak expresses itself in a given cell's
hyperparameters, not by genuine predictive skill. **Every B3 number in
sections 2-3 of this report must now be read as coming from a pipeline with
a confirmed leak, not merely as "a model that tried and honestly lost."**
The two are different findings: the original section 3 conclusion ("B3 does
not beat B1") remains true as a statement about what was measured, but the
measurement itself is compromised, so it should not be read as a clean
verdict on whether LightGBM ranking *could* work on this feature set --
that question is now open pending root cause, not answered "no."

**Root cause found and fixed the same day (commit `bb21f27`, 2026-09-09
14:18 UTC).** `GridSelectedLightGBMStrategy.fit()`
(`open_composer/research/kernel/b3_grid_strategy.py`) computed
`validation_year` as the training window's last calendar year and scored
each grid cell on that year's rows -- but built every cell's `fit_rows` from
the *entire* `train_frame`, validation year included, so `model.fit(fit_rows)`
trained directly on the same rows it was then scored on. In plain terms:
**the cells were scored on rows they were trained on** -- in-sample recall,
not a real train/validation split. This explains every feature of the
placebo evidence above: shuffled labels should give ~0 IC, but every cell
(both feature sets) showed 0.05-0.21, and the deeper-tree cells (`_d6`)
consistently ran ~2-3x their shallow (`_d3`) counterparts at the same
horizon -- the signature of extra tree capacity memorizing rows it was
later "scored" on, not sampling noise (which would not scale with depth)
and not a genuine relationship (which the label shuffle would have
destroyed). Fix: `fit_rows` now excludes the validation year plus a
`2 x label_horizon_days`-calendar-day embargo before it, so no training row
whose forward label could have peeked into the validation year survives
into the fit pool. A new regression test
(`test_validation_year_is_held_out_of_the_fit_pool_not_scored_in_sample`,
`tests/test_b3_grid_strategy.py`) reproduces the mechanism at synthetic
scale; 43/43 kernel tests pass post-fix.

**Corrected daily_only placebo, same protocol, post-fix**
(`/tmp/placebo_daily_only_v3.log`): selected cell `h21_d6`, placebo mean
rank IC **0.0013** -- clean (about 15x inside the `< 0.02` threshold), a
roughly 130x reduction from the pre-fix 0.1709. Full post-fix per-cell
breakdown (every cell now near zero, not just the selected one -- this is a
genuine fix, not one that happens to help only the winning cell):

| Cell | Placebo validation rank IC (post-fix) |
|---|---:|
| h5_d3 | -0.0007 |
| h5_d6 | 0.0009 |
| h10_d3 | -0.0009 |
| h10_d6 | 0.0012 |
| h21_d3 | -0.0008 |
| h21_d6 | **0.0013** (selected) |

**Three numbers for the record**: pre-fix daily_only **0.171**
(`/tmp/placebo_daily_only_v2.log`), pre-fix daily_plus_intraday **0.206**
(`/tmp/placebo_daily_plus_intraday.log`), post-fix daily_only **0.0013**
(`/tmp/placebo_daily_only_v3.log`). daily_plus_intraday has not been rerun
post-fix (see "what happens next" below), so there is no post-fix number
for it yet.

**What happens next.** The recorded daily_only and daily_plus_intraday B3
grid verdicts in sections 2-3 both used the pre-fix, biased cell-selection
path -- neither the -10.15% nor the -13.13% CAGR-excess number comes from a
cleanly-selected cell. **daily_plus_intraday stays closed** as a feature
set: it was already the worse of the two even under the shared pre-fix bias
(every metric in section 3's table), so a clean re-run is not expected to
change that decision and is not planned. Only the **daily_only** grid is
queued for a clean re-run under `bb21f27`'s fix -- and only for test years
**2024-2026** (the Step 13 recent-regime window this round is actually
targeting, not the original Step 11 2018-2026 range) -- **later, when the
box is free**; it is explicitly not run in this session (one heavy job at a
time on a shared 3.9GB box, with Track M and Track L work both queued
ahead of it).

**Consequence for Track M (Step 13)**: per
`docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md`
section 3.4, Track M's ML grid could not reuse this grid-selection path
until this placebo's conclusion landed. It has now landed twice: **failed
pre-fix** (leak confirmed) and **passed post-fix** (`bb21f27`, \|IC\| =
0.0013, well under 0.02) -- the shared code path (`b3_grid_strategy.py`)
itself is clean as of this commit. Track M should build on the post-fix
code for any new grid work, still run its own per-unit placebo (plan
section 3.4 is unchanged by this fix), and treat this report's own
daily_only/daily_plus_intraday historical verdicts as provisional until the
queued clean re-run above lands -- not as a green light to skip its own
placebo discipline.

## 5. Rank IC by validation year (per grid cell selected)

TBD -- one row per test year, the winning `(horizon, depth)` cell, and that
cell's mean validation-year rank IC, for both feature sets.

## 6. `next_open` vs. `close_marked` (winning candidate only)

Per the Step 11 ledger's Wave B item 4: the grid search itself runs under
`close_marked` for every cell (methodology held fixed while comparing
cells); only the single winning candidate (whichever of B1/B3 clears
section 3's bar) is re-run under `next_open` and reported here side by
side. **Promotion, if any, is gated on the `next_open` numbers only.**

| Execution | CAGR excess | Sharpe-ex-BIL | Max DD | Gates x/8 |
|---|---:|---:|---:|---:|
| close_marked (grid-search basis) | TBD | TBD | TBD | TBD |
| next_open (promotion basis) | TBD | TBD | TBD | TBD |

## 7. Feature importance (top 15, winning B3 cell, last fitted year)

**Not yet captured from the real run -- being regenerated, not silently
dropped.** The daily_only full-grid process was killed by a whole-scope
memcg OOM (see the Step 11 ledger's 2026-09-09 entries) immediately after
writing the ledger record, tearsheet, and MLflow run but before the parent
process could print/collect `top_feature_importances()` and
`_turnover_and_capacity()` (both computed *after* the ledger write, per
`scripts/run_b3_grid.py::_run_b3_and_queue_result`'s ordering) -- so the
ledger record itself is complete and correct, but this report-only,
diagnostic side data from that specific process never reached disk. Each
walk-forward year's fit is independent (no state carries over -- see
`baseline_strategies.py`/`b3_grid_strategy.py` module docstrings), so the
last test year's (2026) winning cell can be reproduced exactly by refitting
*only* that one year's anchored window (cheap -- one year, not nine) rather
than rerunning the full grid. Queued right after the daily_plus_intraday
grid + placebo + B1 export finish (not run concurrently with them, per the
Wave B memory discipline).

## 8. Turnover and capacity

**Same status as section 7** -- lost to the same process death, queued for
the same cheap single-year regeneration pass (turnover/capacity need the
full 9-year schedule, not just the last year's model, so this one does
require a full, but scoring-only -- not refitting-only -- pass; sized
appropriately once queued).

## 9. Candidate artifact export

`reports/research/candidates/<experiment_id>/` -- interface defined in the
Step 11 ledger (commit `93ba159`), implemented in
`scripts/export_candidate_artifact.py` (commit `45b0bb1`). Exported
regardless of gate outcome, per plan section 5 item 4 ("无论过不过门槛都要
导出当前最好的那个").

**Current best per section 3: `step11_b1_momentum_top50`** (B3 did not beat
it in either feature set tested so far). Exported to
`reports/research/candidates/step11_b1_momentum_top50/`. This is a
parameter-free rule (12-1 momentum, no fitted coefficients) -- `model.joblib`
is still written (a `MomentumFactorStrategy` instance, satisfying the same
`.score()` protocol every other candidate's artifact does) so the
product-side consumer never has to branch on "does this candidate have a
real model," but `features.json`'s `feature_columns: ["momentum_252_21"]`
makes the ranking rule explicit. **If the `daily_plus_intraday` B3 grid
beats B1 once it lands, this export is superseded and re-pointed to that
experiment_id** -- not left stale.

## 10. Honest conclusion

**Preliminary (daily_plus_intraday grid still running as of this writing --
finalized once it lands, not before):**

Wave B's model-first hypothesis has not paid off so far. Every ML candidate
tried this round (B2 ridge, B3 LightGBM, in both `train_row_dates`
conventions tested for daily-only) has come in behind the simplest rule in
the chain (B1, 12-1 momentum) on the metrics that matter for promotion
(excess CAGR, Sharpe-ex-BIL, gate count). B3's headline raw CAGR (11.5%)
would look fine in isolation; it only reads as a regression once compared
to its own benchmark on a volatility-matched basis, which is exactly why
that comparison exists. Nothing in this round's evidence supports
promoting a model-ranking candidate over the existing rule-based champion.
The chain's answer to "should Wave B's ML models replace B1" is, as of the
daily-only result, **no** -- this is being written down plainly rather than
reframed around B3's more flattering absolute numbers.

Whether `daily_plus_intraday` features change this conclusion is the one
open question this report is still waiting on.

## 11. blocked_on_user

None as of this writing.
