# Step 13 progress (Track L executor; one line per completed item: time, commit, result)

Plan: `docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md`.
Gates: `config/promotion/recent-regime-high-return-gates-v2.json`.
Full narrative for the Step 11 Wave B closeout items below (placebo leakage
investigation) lives in `reports/research/control/step11-2026-09-06-progress.md`;
this file is the lighter, append-only log the plan's section 6 asks for.

- 2026-09-09 08:58 UTC -- `608309f` -- `--placebo-only` generalized with `--placebo-feature-set`, so both daily_only and daily_plus_intraday can be placebo-checked.
- 2026-09-09 08:58 UTC -- `cbba147` -- fixed `_run_label_shuffle_placebo` missing `extra_train_columns` + only shuffling one of three label columns (crashed on first real invocation this round).
- 2026-09-09 09:00 UTC -- daily_only placebo (post-cbba147, pre-bb21f27): selected cell IC 0.171 (all 6 cells 0.05-0.17) -- still far above the 0.02 clean threshold. Not yet root-caused at this point.
- 2026-09-09 09:07 UTC -- `000b59c` -- Track L L0 collector (`open_composer/research/news/collector.py` + `scripts/collect_alpaca_news_packets.py`), 9/9 tests, one-day smoke test (2024-06-03, 897 articles) passed against the real API.
- 2026-09-09 14:19 UTC -- `bb21f27` -- **root cause found and fixed**: `GridSelectedLightGBMStrategy.fit()` never held out the validation year from the fit pool (fit on the entire training window including the validation year, then scored that same year -- in-sample, not a real holdout). Confirmed by the placebo's own pattern (deeper trees showing 2-3x the shallow trees' spurious IC at the same horizon -- memorization capacity, not signal). Fix: fit_rows now excludes the validation year plus a `2 * label_horizon_days`-calendar-day embargo before it. New regression test reproduces the mechanism at synthetic scale. 43/43 kernel tests pass.
- 2026-09-09 14:19 UTC -- daily_only placebo rerun launched with the fix (`/tmp/placebo_daily_only_v3.log`) -- numbers pending, will update this line once landed.
- 2026-09-09 14:30 UTC -- (L-track executor handoff; recorded by pathspec commit, see next entry) -- `/tmp/placebo_daily_only_v3.log` landed: post-fix daily_only placebo mean rank IC **0.0013** (clean, threshold 0.02), selected cell `h21_d6`. Full three-number record now in `step11-w2-model-ranking-2026-09.md` sections 3-4: pre-fix daily_only 0.171, pre-fix daily_plus_intraday 0.206, post-fix daily_only 0.0013. daily_plus_intraday feature set stays **closed** (already worse than daily_only even under the shared pre-fix bias); only daily_only is queued for a clean re-run, test years 2024-2026 only, later when the box is free -- not run this session. Collector (`collect_alpaca_news_packets.py --start 2024-01-01`, PID 1939055/1939060) confirmed still running throughout, not restarted.

## blocked_on_user / cross-agent coordination notes

- Per the 2026-09-09 14:10 UTC coordinator message: a third agent now owns `panel.py`'s `extra_feature_roots` parameter (needed first for the open factor-library tables). L-track does **not** edit `panel.py`; will use `extra_feature_roots` once that agent lands it and the coordinator signals it's ready.
- The pre-fix daily_only/daily_plus_intraday B3 grid ledger entries (`step11_b3_lightgbm_grid_daily_only`, `step11_b3_lightgbm_grid_daily_plus_intraday`) were selected via the in-sample mechanism above and must be treated as unreliable until re-run with `bb21f27`'s fix -- this affects the Wave B report's section 2-3 verdicts and, per plan section 3.4/7, gates whether Track M may reuse the grid-selection path at all.
