# Hypotheses: h20260928_20_recent_regime_opt

## H1 (E family)

- Hypothesis: At least one of the 7 preregistered E-family variants (E1-E7)
  clears the owner's literal three-part replacement rule against E0
  (batch-2's EOM_REVERSAL_SPY: select 1.34 / anchor 1.24 / stress 0.58
  Sharpe) -- (a) select-window 10bp Sharpe >= E0 + 0.10, (b) 2026
  contaminated-window Sharpe not below E0's by more than 0.10, (c) 20bp
  select-window Sharpe still >= E0 + 0.10.
- Failure mode: No E-family variant clears all three conditions -- the
  formation-window widening (E1/E2) dilutes the signal per Graziani
  (2024)'s own A.1.4 robustness finding (only the last week predicts), the
  threshold/symbol/holding-truncation variants (E3-E6) do not add enough
  select-window Sharpe, or E7's magnitude scaling does not survive the 20bp
  cost check.
- Measurement: `reports/research/screens/h20260928_20_recent_opt/leaderboard.json`,
  read per E-family candidate: `judged.select.sharpe` (10bp), `per_window.select.offsets.0.net20.sharpe`
  (20bp), `judged.holdout.sharpe` (2026 guard), plus per-family DSR
  (trial_count=8) computed separately in results.json.
- Stop/Pivot criterion: If no E-family variant clears the rule, E0 stands
  unchanged as the batch-2 result; every tested E-family variant is recorded
  with its verdict, and the direction registry entry
  (dir:end_of_month_reversal_effect) is updated to reflect that this
  specific optimization attempt did not improve on the base.

## H2 (S family)

- Hypothesis: At least one of the 9 preregistered S-family variants (S1,
  S2, S_AVG3, S_AVG5, S_SHIFT0, S_SHIFT2, S_11SECTORS, S_INVVOL,
  S_ABSFILTER) clears the owner's replacement rule against S0 (batch-2's
  FRONT_RUN_SECTOR_TOP2: select 0.75 / anchor 1.40 / stress 0.45 Sharpe).
- Failure mode: No S-family variant clears all three conditions --
  Allocate Smartly's independent extended test of the closely-related
  country-ETF front-running mechanism found it ineffective before the
  original author's sample, a caution that a select-window improvement here
  may not survive the 2026-guard or 20bp conditions either.
- Measurement: same leaderboard fields as H1, S-family rows; per-family DSR
  (trial_count=10).
- Stop/Pivot criterion: If no S-family variant clears the rule, S0 stands
  unchanged; dir:front_running_sector_seasonality registry entry updated
  accordingly.

## H3 (C family, descriptive)

- Hypothesis: C1 (EOM-gated sector top-2) or C2 (50/50 static blend) shows
  a select-window Sharpe improvement over both component bases (E0 and S0)
  individually.
- Failure mode: Neither combination beats both components; combining two
  already-marginal, recent-regime-only signals does not produce a
  Sharpe-additive effect.
- Measurement: leaderboard.json C1/C2 rows, judged.select.sharpe compared
  descriptively to E0's and S0's own judged.select.sharpe. C1/C2 are NOT
  subject to the three-part replacement rule (they do not replace E0 or S0)
  and are reported descriptively only, per the owner's brief ("<=3
  combination variants").
- Stop/Pivot criterion: Reported regardless of outcome; no registry
  base-replacement action taken from C1/C2 alone.
