# Decision Record: h20260928_23_s1_s2_rebalance_timing

## P1

- Path: s2_rebalance_timing (descriptive offset distribution, 21 monthly signal-day offsets)
- Decision: continue -- keep S2's live monthly rule (2026-09-23 renewal, down-only vol target
  0.156) unchanged. This iteration has no pass/fail condition and adopts no offset; it only
  measures how much of S2's headline numbers is rebalance-date luck, mirroring H-20260928-01's S3
  check.
- Reason: O00 (live) is asserted bit-equal to `salvage.run_cell` (max abs diff 6.94e-18,
  `results.json`; panel 2016-01-04..2026-09-17). Across the 21 offsets (O00..O20): select-window
  Sharpe-ex-BIL O00 1.72, rank 1 of 21, median 1.44 (16.5% below O00, under the queue's 20%
  highlight bar); anchor Sharpe O00 1.80, rank 2 of 21, median 1.55 (14.1% below O00); neither
  triggers the highlight rule, so S2's select/anchor headline numbers are not the "best of the
  distribution" story S3 had, even though the live date ranks near the top. Stress window
  (2016-05-02..2023-08-31, full panel) O00 Sharpe 0.52, rank 7 of 21, median 0.50 (close to
  median -- ordinary, not lucky); max DD O00 -26.8%, rank 4 of 21 (shallower than most, but well
  within the distribution's -24.9% to -34.8% range, not an outlier). Holdout 2026 (contaminated)
  O00 Sharpe 1.88 ranks 12 of 21, essentially the median (every offset does well in the up-only
  2026 window, as with S3). Net: S2's live rule is not meaningfully luckier than a typical
  month-end date in the windows that carry its headline evidence.
- Bug fix (2026-09-28): the first run of this iteration did not set `base.WARMUP_START` before
  `base.load_panel`, so it silently used the recent-menu default ("2022-06-01") instead of the
  requested full history; every "stress" window actually covered only 2022-06..2023-08 with a
  truncated warmup. That first run's stress numbers (Sharpe -0.49/-0.14/0.24, O00 -0.31 rank 16 of
  21, all-negative-to-flat) are invalid and are superseded by the corrected numbers above.
  `scripts/run_h20260928_23_s1_s2_rebalance_timing.py` now sets `base.WARMUP_START = PANEL_START`
  before `load_panel`, exactly like `scripts/run_h20260928_01_s3_rebalance_tranching.py` already
  did, plus a hard `assert_panel_covers_stress_window` check and a regression test
  (`tests/test_h20260928_23_s1_s2_offsets.py::TestPanelStartRegression`). Select, anchor and
  holdout-2026 numbers are unchanged (all lookbacks were already warm by the 2023-09 select-window
  start), confirming this was a pure data-window bug, not a selection or evaluation bug; this
  iteration is descriptive only, so no offset selection was ever affected.
- Next iteration suggestion: none. No renewal, sizing, or rule change is triggered by this
  descriptive result. The companion S1 check is `h20260928_23_s1_rebalance_timing`; both feed
  registry row `dir:s1_s2_rebalance_timing_luck` alongside S3's `dir:s3_rebalance_timing_luck_tranching`.
