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

| Candidate | Feature set | `train_row_dates` | CAGR excess (vol-matched SPY) | Sharpe-ex-BIL | Max DD | DSR prob. | MAR | Capture ratio | Downside capture | Positive-fold frac. | Gates x/8 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 equal-weight universe | daily_only | all | -5.58% | 0.4596 | -41.3% | TBD | 0.26 | 0.966 | TBD | TBD | 3/8 |
| B1 12-1 momentum top50 | daily_only | all | -4.95% | 0.5777 | -58.3% | TBD | 0.33 | 1.003 | TBD | TBD | 4/8 |
| B2 ridge top50 | daily_only | all | -4.66% | 0.4768 | -37.8% | TBD | 0.28 | 0.971 | TBD | TBD | 3/8 |
| B2 ridge top50 | daily_only | rebalance_dates | -3.32% | 0.5612 | -45.5% | TBD | 0.31 | 0.992 | TBD | 3/8 |
| B2 ridge top50 | daily_plus_intraday | rebalance_dates | **not run** (see caveat below) | -- | -- | -- | -- | -- | -- | -- | -- |
| B3 LightGBM grid | daily_only | rebalance_dates | **-10.15%** | **0.4175** | **-57.9%** | fail | **0.198** | 0.972 | 0.737 | **0.778 (7/9)** | **2/8** |
| B3 LightGBM grid | daily_plus_intraday | rebalance_dates | TBD (in progress) | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

Market-neutral (SPY-beta-hedged) variants for every row above:

| Candidate | Feature set | `train_row_dates` | CAGR excess | Sharpe-ex-BIL | Max DD | Gates x/8 |
|---|---|---|---:|---:|---:|---:|
| B0 | daily_only | all | -12.40% | -0.7364 | -35.0% | 1/8 |
| B1 | daily_only | all | -26.23% | -0.0234 | -73.9% | 1/8 |
| B2 | daily_only | all | -22.52% | -0.7174 | -70.1% | 1/8 |
| B2 | daily_only | rebalance_dates | -21.53% | -0.4321 | -66.3% | 1/8 |
| B2 | daily_plus_intraday | rebalance_dates | **not run** | -- | -- | -- |
| B3 | daily_only | rebalance_dates | **-17.99%** | **-0.1946** | **-53.2%** | **0/8** |
| B3 | daily_plus_intraday | rebalance_dates | TBD | TBD | TBD | TBD |

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

**No. B3 (daily-only) does not beat B1, on any dimension that matters.**

| Metric | B1 (12-1 momentum, long-only) | B3 daily-only (long-only) | B3 wins? |
|---|---:|---:|:---:|
| CAGR excess (vol-matched SPY) | -4.95% | -10.15% | no |
| Sharpe-ex-BIL | 0.578 | 0.417 | no |
| Max drawdown | -58.3% | -57.9% | ~tie (B3 marginally less bad) |
| MAR | 0.333 | 0.198 | no |
| Capture ratio | 1.003 | 0.972 | no |
| Gates passed | 4/8 | 2/8 | no |

B3's raw CAGR (11.5%) looks superficially reasonable in isolation, but every
relative-to-benchmark measure is worse than B1's, and B1 already does not
clear the promotion bar either -- B3 is a **regression from the chain's
already-negative standing champion**, not an improvement that merely falls
short. The two-fold smoke test's much more flattering numbers (45% CAGR
excess, 7/8 gates) were an artifact of testing on only the two most
favorable, most-recent years and must not be read as "B3 nearly worked."

**Chain standing after Wave B (daily-only)**: B1 (12-1 momentum, long-only,
4/8 gates) remains the best candidate produced by this round's baseline
chain plus B3 grid. Per plan section 5 item 4, it is exported as the
current-best candidate regardless (section 9) -- this negative result for
B3 does not block that export.

**Suspiciously high validation-year rank IC in the smoke test (0.08-0.17)
prompted a leakage check** -- see section 4's placebo result before trusting
any of the numbers in this report.

## 4. Placebo (label-shuffle) check

TBD. Plan requirement: shuffle `label_rank_21` within each date's
cross-section, refit, and confirm mean validation rank IC is approximately
zero. A materially nonzero placebo IC would mean a leakage bug and blocks
this report's other conclusions until root-caused.

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
