# Search Space: h20260928_02_cross_asset_sleeve

One path, `cross_asset_sleeve_vs_delevered_s3_control`, 2 candidates, fixed
before any return is computed (candidate-manifest.json,
`generated_before_backtest: true`).

- D1: Carlson's Defense First TAA rotation over TLT/GLD/DBC/UUP -- rank by the
  mean of 1/3/6/12 calendar-month returns as of the signal date, weight
  40/30/20/10 by rank, redirect any tier scoring below BIL (T-bills) to SPY.
  Published, unedited rules (reused from `run_h20260923_12_s3_defense_first.defense_weights`,
  generalized to an arbitrary signal date so offsets != 0 evaluate without
  look-ahead).
- D2: TLT/GLD/DBC/UUP each held only when trailing-12-month return beats
  SHY's, sized by inverse 63-session trailing daily-return volatility across
  eligible names, otherwise 100% SHY. Round-number thresholds from the queue
  task, not tuned.

Both candidates are monthly (`freq: "M"`), swept across all 21 monthly
rebalance-day offsets via `scripts/screen_lane.py`'s harness and judged by the
median (no cherry-picked rebalance date, per the owner's 2026-09-28 rule).
Each is combined with the live S3 sleeve by trailing-63-session inverse
volatility (`screen_lane.combine_two_sleeves`, ported unedited from
`run_h20260927_01_sleeve_combination.combine_portfolio`) and judged against a
vol-matched delevered-S3 control (`screen_lane.diversifier_edge_for_offset`,
k solved by bisection per window, capped at 1.0, zero cost -- conservative in
the control's favor).

Costs: 10bp/side primary and 20bp/side stress on each candidate's own
turnover, plus the same rate on the combination's rebalance turnover,
charged on the session after each month-end signal.

Windows: select 2023-09-18..2025-12-31, anchor 2024-01-08..2026-09-17
(frozen gate), stress 2016-05-02..2023-09-15, 2026-01-02..2026-09-17 holdout
reported but flagged contaminated (already spent by S3 and, for D1's
SPY-fallback sibling, by H-20260923-12).

Benchmark family per candidate: S3 incumbent reference, the paired
vol-matched control, and SPY/SHY buy-and-hold. G3 (placebo) does not apply to
this trend-rotation/combination question -- there is no discretionary asset
pick or gate-timing signal to randomize (D1's ranking and D2's eligibility
are both fully deterministic); the vol-matched control is the
placebo-equivalent check (see candidate-manifest.json `g3_not_applicable_reason`).
Total candidate budget 2, well under the 24-candidate lightweight-exemption
ceiling and the 80-cell campaign ceiling.
