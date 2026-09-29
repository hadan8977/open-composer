# Hypotheses: h20260928_44_etf_pair_switch

Eighteen candidates, two families, one hypothesis pair sharing the same
falsification design: compute each PAIR candidate under `rotation_cell`'s
unedited mechanism (menu size 2, top_n=1, absolute-momentum-vs-SHY filter,
monthly rebalance), check K1/K2 against S3's frozen reference numbers
(date-neutral anchor Sharpe 1.49, stress Sharpe 0.81), then check any pass
against its own paired STATIC5050 control (fixed 50/50 blend, no ranking, no
cash filter). No backtest is run under this dossier; the screening lane
consumes `candidate-manifest.json` and reports results back into this
iteration.

## H1 -- At least one PAIR candidate clears K1 or K2

- Hypothesis: at least one of the 12 pair/lookback combinations has a
  date-neutral Sharpe within 80% of S3's in both the anchor and stress
  windows (K1), or blends with S3 at 63-session inverse-vol to beat a
  vol-matched k*S3+(1-k)*SHY control by 0.05 Sharpe in both windows (K2),
  because the mechanism is the same already-live cross-sectional-momentum
  engine used on S1 (11 sectors) and S3 itself, only shrunk to the
  degenerate 2-name case a correlated pair naturally forms, and QuantConnect's
  own single-author post reports the QQQ/SPY pair specifically clearing a
  positive (if weak, ~0.8) Sharpe over 2010-2024 under a related but not
  identical rule.
- Failure mode: the QuantConnect source's own reported Sharpe (~0.8) is
  already below S3's 0.81 stress-window bar even before considering the
  source's disclosed code bugs and complete lack of independent replication;
  a 2-name switch has no diversification benefit within the pair itself (the
  two legs are, by construction, highly correlated), so the only source of
  edge is timing the relative trend, and Robot Wealth's negative-evidence
  review documents exactly the failure mode expected here: whipsaw losses in
  choppy/sideways regimes and lag after V-shaped recoveries (both are present
  in the 2016-2023 stress window, e.g. 2018 Q4, 2020 COVID crash/recovery,
  2022 bear market).
- Measurement: date-neutral Sharpe (median over monthly offsets 0-20 trading
  days) in the stress window 2016-05-02..2023-09-15 and the anchor window
  2024-01-08..2026-09-17, at 10bp cost; CAGR at 20bp cost; K2's paired
  vol-matched control per candidate; DSR with n_trials=18 (the full batch,
  conservative).
- Stop/Pivot criterion: if none of the 12 PAIR candidates clears K1 or K2 (or
  reaches the anchor-only watch_recent bar), `dir:etf_pair_relative_strength_switch`
  is refuted for this scope and the next round should not re-tune this same
  6-pair x {63,126} grid without a new, distinct signal (e.g. a
  volatility-adaptive switch threshold, or a genuinely different pair
  family) per the direction-review's stop condition.

## H2 -- Any K1/K2 pass reflects genuine switching value, not just holding both legs

- Hypothesis: if a PAIR candidate clears K1 or K2, the switching mechanism
  itself (choosing one leg over the other based on relative momentum) adds
  Sharpe over simply holding both legs statically at 50/50, because the
  economic premise of a relative-strength switch is that the stronger leg's
  near-term trend persists long enough to be worth concentrating in, which a
  static blend cannot capture.
- Failure mode: within a highly correlated pair, the return-dispersion
  "raw material" cross-sectional momentum needs is small by construction (the
  two legs share most of their variance), so the switch's turnover cost and
  whipsaw risk in choppy periods may exceed the concentration benefit,
  leaving the static 50/50 blend with an equal or higher risk-adjusted
  return -- exactly what the negative-evidence review (Robot Wealth) predicts
  for this mechanism family.
- Measurement: for every PAIR candidate that clears K1 or K2 in a given
  window, compare its judged (median-offset) net10 Sharpe in that window
  against the paired STATIC5050 candidate's judged net10 Sharpe in the same
  window.
- Stop/Pivot criterion (preregistered counter-evidence rule): a PAIR
  candidate that would otherwise be kept (K1 or K2, or watch_recent) is
  downgraded to "not kept (no switching increment)" if its judged Sharpe in
  either the anchor or the stress window does not exceed its own paired
  STATIC5050 control's judged Sharpe in that window. STATIC5050 candidates
  themselves are controls only -- never eligible for keep/strong/watch_recent
  -- and are not re-tuned or added to after seeing a result.
