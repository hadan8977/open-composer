# Search Space: h20260929_03_ma_target_drift

One path, `ma_target_drift_signal_card`, 4 candidate cards (limit 24).

- Event: 8-K with Item 1.01 (not a completion 8-K: 2.01 together with 5.01), whose filer is the acquired party by a code rule on the main text (merger sub merges into the company/filer), not a SPAC-named shell, not an amendment or holding-company reorganization; first such filing per CIK in 365 days.
- Timing: `trade_date` = last session on or before the Eastern acceptance date; signal_card enters at the next session open.
- Variants: `all` targets; `t3` = ADV rank 1501-3000 at the latest month-end on or before trade_date (small/illiquid, per owner 2026-09-28 preference).
- Horizons: 20 sessions primary, 60 sessions comparison; both count as trials (4 total).
- Costs: 10 and 20 bp per side (signal_card), long only.
- Placebo: signal_card redated (+-126 sessions, 20 seeds). Extra diagnostics: CAR [-5,-1] before and 1-20 after.
- Not tested: hold-to-close (needs completion status, which would select survivors and is not available free at announcement time).
