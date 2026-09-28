# Decision Record: h20260928_23_s1_rebalance_timing

## P1

- Path: s1_rebalance_timing (descriptive offset distribution, 5 weekly signal-day offsets)
- Decision: continue -- keep S1's live weekly rule unchanged. This iteration has no pass/fail
  condition and adopts no offset; it only measures how much of S1's headline numbers is
  rebalance-date luck, mirroring H-20260928-01's S3 check.
- Reason: O00 (live) is asserted bit-equal to `salvage.run_cell` (max abs diff 0.00e+00,
  `results.json`; panel 2016-01-04..2026-09-17). Across the 5 offsets (O00..O04): select-window
  Sharpe-ex-BIL O00 1.14, rank 1 of 5, median 0.93 (18.3% below O00, just under the queue's 20%
  highlight bar); anchor Sharpe O00 1.35, rank 2 of 5, median 1.33 (1.5% below O00 -- essentially
  no date luck). Stress window (2017-01-03..2023-08-31, full panel) Sharpe O00 0.48, rank 5 of 5
  (the WORST of the 5 offsets there, median 0.56, max DD O00 -32.1% also the deepest of the 5) --
  the live date is unlucky, not lucky, in that window. Holdout 2026 (contaminated) O00 rank 4 of
  5, ordinary. The queue's highlight rule (live top 3 AND median >20% below O00) does not fire in
  any window. S1's select and anchor headline numbers sit close to the median of its own offset
  distribution: little of S1's live evidence is a lucky rebalance date, and the stress window
  shows it is if anything unlucky.
- Bug fix (2026-09-28): the first run of this iteration did not set `base.WARMUP_START` before
  `base.load_panel`, so it silently used the recent-menu default ("2022-06-01") instead of the
  requested full history; every "stress" window actually covered only 2022-06..2023-08 with a
  truncated warmup. That first run's stress numbers (Sharpe -0.00/0.13/0.29, O00 0.19 rank 2 of 5,
  highlight rule fired) are invalid and are superseded by the corrected numbers above.
  `scripts/run_h20260928_23_s1_s2_rebalance_timing.py` now sets `base.WARMUP_START = PANEL_START`
  before `load_panel`, exactly like `scripts/run_h20260928_01_s3_rebalance_tranching.py` already
  did, plus a hard `assert_panel_covers_stress_window` check and a regression test
  (`tests/test_h20260928_23_s1_s2_offsets.py::TestPanelStartRegression`). Select, anchor and
  holdout-2026 numbers are unchanged (all lookbacks were already warm by the 2023-09 select-window
  start), confirming this was a pure data-window bug, not a selection or evaluation bug; this
  iteration is descriptive only, so no offset selection was ever affected.
- Next iteration suggestion: none. No renewal, sizing, or rule change is triggered by this
  descriptive result. The companion S2 check is `h20260928_23_s1_s2_rebalance_timing`; both feed
  registry row `dir:s1_s2_rebalance_timing_luck` alongside S3's `dir:s3_rebalance_timing_luck_tranching`.
