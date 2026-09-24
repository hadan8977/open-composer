# Search Space: h20260924_02_momentum_crash_guard

One path, `momentum_crash_guard_t1_daily`, 5 candidates (under the card's
up-to-6 cap; total budget 5, well under the 80-candidate/24-per-path repo
ceiling). No model training, no mutation -- every guard rule is a fixed,
preregistered deterministic function of published values or
development-window-only statistics (see candidate-manifest.json for exact
formulas).

| candidate_id | family | mechanism | threshold source |
|---|---|---|---|
| cg_dm | CG-DM | SPY 24-month bear AND 126-day high-vol -> 0/1 | published windows (DM 2016); high-vol cutoff = development-window median |
| cg_bsc_daily | CG-BSC-daily | book's own 126-day realized-vol target ratio, cap 1.0 | published formula (BSC 2015), daily update per task; target = development-window median |
| cg_stop | CG-STOP | book-level drawdown stop, SMA-50 re-entry | threshold = repo kill-switch formula on development-window book drawdown |
| cg_dm_bsc | CG-DM-BSC | product of cg_dm and cg_bsc_daily multipliers | inherits both |
| cg_mkt_stop | CG-MKT-STOP | SPY single-session <= -7% -> flat N sessions | published (SEC Level-1 MWCB); N from development-window recovery, else disclosed round 5 |

Cost assumptions: 10 bp per side primary, 20 bp per side stress, applied to
the guard-scaled book's own turnover (see cost-contract.json); cash leg SHY
next-open return while de-risked.

Benchmark family: the unguarded T1 book at 10bp and 20bp (base-book
reproduction numbers reported first, Step 2); the calendar-shift placebo
(the guard's own multiplier series shifted 1-20 sessions, 20 seeds,
evaluated on anchor Sharpe) is the sole placebo family required by this
card (G3) -- no separate random-seed or menu placebo is used here since
there is only one menu (one book) and one guard series per candidate, unlike
the giants-sweep family's multi-asset menus.

Windows (frozen, unchanged from docs/plan-strategy-factory-2026-09-22.zh.md
section 1 / scripts/run_h20260918_05_recent_menu.py):

| window | start | end | use |
|---|---|---|---|
| development | 2016-01-04 | 2023-09-15 | guard threshold fitting ONLY (never select/holdout/anchor) |
| select | 2023-09-18 | 2025-12-31 | ranking window (not used to fit any threshold in this single-path round) |
| holdout | 2026-01-02 | 2026-09-17 | scored once, G2 |
| anchor | 2024-01-08 | 2026-09-16 | G1/G1'/G3/G4 |

This is not a Wave 9.2-style go/no-go band round; it reuses the frozen
giants-sweep-family G1-G5 gate set directly (see candidate-manifest.json
`contracts.validation`), which already encodes the same discipline (return
bar, drawdown bar, out-of-sample bar, placebo bar, cost-stress bar).

`trial_ledger_paths` and `evaluation_report_paths` in search-space.json
point at `trial-ledger.jsonl` and `report.md`, filled after Step 2 runs (see
decision-record.md for status).
