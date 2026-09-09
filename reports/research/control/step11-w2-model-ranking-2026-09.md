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
| B2 ridge top50 | daily_plus_intraday | rebalance_dates | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| B3 LightGBM grid | daily_only | rebalance_dates | TBD (full 9y run in progress) | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| B3 LightGBM grid | daily_plus_intraday | rebalance_dates | TBD (queued after daily_only) | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

Market-neutral (SPY-beta-hedged) variants for every row above:

| Candidate | Feature set | `train_row_dates` | CAGR excess | Sharpe-ex-BIL | Max DD | Gates x/8 |
|---|---|---|---:|---:|---:|---:|
| B0 | daily_only | all | -12.40% | -0.7364 | -35.0% | 1/8 |
| B1 | daily_only | all | -26.23% | -0.0234 | -73.9% | 1/8 |
| B2 | daily_only | all | -22.52% | -0.7174 | -70.1% | 1/8 |
| B2 | daily_only | rebalance_dates | -21.53% | -0.4321 | -66.3% | 1/8 |
| B2 | daily_plus_intraday | rebalance_dates | TBD | TBD | TBD | TBD |
| B3 | daily_only | rebalance_dates | TBD | TBD | TBD | TBD |
| B3 | daily_plus_intraday | rebalance_dates | TBD | TBD | TBD | TBD |

**Caveat on the two already-ledgered B3 daily-only smoke numbers** (`config_hash` for `test_years=[2025,2026]` only): 45% CAGR excess / -17% drawdown / 7/8 gates was a **2-fold smoke test**, not evidence, and must not be compared against the 9-fold rows above. It exists in the ledger only to validate the pipeline before the full run; superseded by the full 2018-2026 row once it lands.

## 3. B3 vs. B1/B2: did the model beat the baseline chain?

TBD -- pending the full 9-year runs. The chain's standing champion going into
Wave B is **B1 (12-1 momentum, long-only, 4/8 gates)** -- B2 did not beat B1
(Wave A 3.5 conclusion, unchanged). This section states plainly whether B3
clears B1's bar on the same footing (same cost, same window, same gate
contract) or not. **If it does not, that is written here as a negative
result, not omitted or reframed.**

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

TBD.

## 8. Turnover and capacity

TBD -- mean two-sided weekly turnover and median position size as a percent
of 21-day ADV at an illustrative $10mm book (see `scripts/run_b3_grid.py`'s
`_turnover_and_capacity`).

## 9. Candidate artifact export

`reports/research/candidates/<experiment_id>/` -- interface defined in the
Step 11 ledger (commit `93ba159`), implemented in
`scripts/export_candidate_artifact.py` (commit `45b0bb1`). Exported
regardless of gate outcome, per plan section 5 item 4 ("无论过不过门槛都要
导出当前最好的那个"): TBD which `experiment_id` once section 3's verdict is
in -- if B3 does not beat B1, **B1 is exported anyway** (the chain's current
best), not withheld pending a positive result.

## 10. Honest conclusion

TBD.

## 11. blocked_on_user

None as of this writing.
