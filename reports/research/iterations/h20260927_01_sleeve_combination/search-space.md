# Search Space: h20260927_01_sleeve_combination

One path, `sleeve_combination_vs_delevered_control`, 7 candidates, fixed
before any combination return is computed (candidate-manifest.json,
`generated_before_backtest: true`).

- M0: S3 alone, vt40 base target + QQQ oversold dip boost to 0.60 for 10
  sessions, unchanged reference (no combination logic).
- M1: equal-thirds S1/S2/S3, month-end rebalance, intra-month drift.
- M2: 0.5 S1 / 0 S2 / 0.5 S3, same rebalance convention.
- M3: trailing-63-session inverse-volatility weight across S1/S2/S3, equal
  weight before 63 sessions of sleeve history exist.
- C1/C2/C3: each Mi's paired control, k*S3+(1-k)*SHY, k solved by bisection
  per evaluation window so std(Ci) == std(Mi) in that window (capped at
  k=1.0), rebalanced daily, no cost.

Sleeve inputs (S1/S2/S3 daily net returns) are produced unchanged by the
frozen `scripts/run_h20260922_05_salvage.py` `run_cell`: S1 target=None, S2
target=0.156 (from `strategy_specs/drafts/us_etf_growth_rotation_blend_top2_monthly.yaml`),
S3 target=0.40 with boost_target=0.60 over `salvage.boost_window(salvage.dip_signal(close), 10)`.
Costs: 10bp/side primary and 20bp/side stress for each sleeve's own turnover
(via `run_cell`) plus a combination-level rebalance cost of the same bp rate
times the sum of absolute sleeve-weight changes, charged on the session after
each month-end signal.

Windows: common start 2017-02-01 (first day all three sleeves hold a
non-cash position), stress 2017-02-01..2023-09-15, select 2023-09-18..2025-12-31,
anchor 2024-01-08..2026-09-17 (frozen gate), 2026-01-02..2026-09-17 holdout
reported but flagged contaminated (already spent by the individual sleeves).

Benchmark family per candidate: M0 reference, the paired Ci control, and
SPY/QQQ/SHY buy-and-hold. G3 (placebo) does not apply to a fixed-proportion
or inverse-volatility combination question with no discretionary pick or
gate-timing signal to randomize; the volatility-matched control Ci is the
placebo-equivalent check here (see candidate-manifest.json
`g3_not_applicable_reason`). Total candidate budget 7, well under the 80-cell
ceiling.
