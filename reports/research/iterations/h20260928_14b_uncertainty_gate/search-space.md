# Search Space: h20260928_14b_uncertainty_gate

One path, `uncertainty_gate_t1_book`, 3 preregistered candidates (well under
the 24-per-path / 80-per-round caps): U1 (book-level exposure cut to 0.5 at
uncertainty quantile z(s-1)>0.80), U2 (book-level exposure cut to 0.0 at
z(s-1)>0.90), U3 (individual-name DEUP-style cap: exclude the top 20% most
uncertain names at cohort formation, backfill by momentum rank).

Shared model: k=15 bootstrap LightGBM regressors (row-level bootstrap, seeds
0-14), target = 20-session-forward cross-sectional rank of return, features =
`kt.BASE_FEATURE_COLUMNS` rank-normalized daily, universe = top-500 by dollar
ADV (same PIT universe as the T1 book). Walk-forward: expanding window,
annual retrain each January, labels purged to end >=21 sessions before the
retrain date. LightGBM hyperparameters fixed to
`scripts/run_t20260928_10_ml_killtest.py`'s `LGBM_COMMON` (num_leaves=31,
learning_rate=0.05, n_estimators=400, colsample_bytree=0.8, subsample=0.8,
subsample_freq=1, min_child_samples=200), `num_threads` = requested Modal
cores, no tuning.

Cost: 10 bp per side primary, 20 bp stress (`cost-contract.json`). Benchmark
family: unguarded T1 book (10bp/20bp), a same-realized-vol-matched control
(k*book + (1-k)*SHY, k solved on the same window), and two placebo families
(block/circular-shift of the gate series for U1/U2, random-quintile-drop of
cohort membership for U3, >=200 seeds each). Wave/band: this is a
single-mechanism, lightweight iteration (3 candidates, one path, no campaign
contract) per the existing lightweight-single-mechanism exemption used by
`h20260924_02_momentum_crash_guard`.

Stage 1 evaluates all 3 candidates on the anchor window (2024-01-08..latest)
against AUROC / placebo / owner-rule stop conditions. Stage 2 (only for a
candidate clearing all of stage 1) adds the stress window
(2016-05..2023-08, truncated to the actual walk-forward out-of-sample start),
G1-G5, K1/K2 tiering and DSR at 3 trials. Total candidate budget: 3.
