# Decision Record: h20260928_42_opex_week

## P1

- Path: `opex_week_screen` (20 candidates: 8 primary option-expiration-week
  calendar candidates -- OPEX_{SPY,QQQ,DIA,IWM}_{WEEK,WEEKMON} -- plus 12
  internal placebo controls -- PLACEBO_W{1,2,4}_{SPY,QQQ,DIA,IWM}).
- Decision: **stop** (0 kept, 0 strong_keep, 0 watch_recent -- 8/8 primary
  refuted).
- Reason: Per `results.json`, checked against `candidate-manifest.json`'s
  keep_rule (K1 anchor >=1.1882 / stress >=0.6447 with positive 20bp CAGR
  both windows; K2 edge >=0.05 both windows; watch_recent anchor-only
  >=1.1882): every one of the 8 primary candidates has a NEGATIVE
  anchor-window Sharpe (best OPEX_IWM_WEEKMON at -0.176, vs. the 1.1882
  watch_recent/K1 bar), so none reaches even the weakest (watch_recent)
  tier. K2 fails identically for all 8: every diversifier edge is negative
  in both the anchor window (-0.18 to -0.77) and the stress window (-0.26
  to -0.75) -- blending this rule with S3 would make the combined
  portfolio strictly worse, not better. 20bp CAGR is negative in the
  stress window for all 8 and in the anchor window for 6/8; no candidate
  has positive 20bp CAGR in both windows. The preregistered placebo
  internal-falsification check (any primary candidate otherwise kept is
  demoted if a same-ticker placebo's anchor Sharpe is >= its own WEEK
  anchor Sharpe) did not need to fire (nothing was kept to demote), but
  independently corroborates the refutation: for all four tickers, the
  2nd-Friday-week placebo has a materially higher anchor Sharpe than the
  actual expiration week (e.g. SPY -0.632 vs. PLACEBO_W2_SPY +0.860; QQQ
  -0.643 vs. PLACEBO_W2_QQQ +1.152) -- the expiration week is not special
  in a positive direction on this universe/window/cost contract, if
  anything it underperforms an arbitrary non-expiration week. Full DSR
  (n_trials=20, conservative): max overall 0.4926 (PLACEBO_W2_QQQ, a
  placebo, never keep-eligible); max among the 8 primary candidates only
  0.0142 (OPEX_IWM_WEEKMON) -- consistent with candidates whose own Sharpe
  is negative, not a marginal near-miss.
- Next iteration suggestion: `dir:option_expiration_week_calendar_effect`
  is refuted for this scope (large-cap/index ETF proxies, 2024-2026 anchor
  + 2016-2023 stress windows, 10bp/20bp next-open-fill contract). Do not
  re-tune this same calendar rule (WEEK/WEEKMON exit timing, or the
  SPY/QQQ/DIA/IWM universe) without a new, distinct signal -- e.g. an
  actual options-flow, open-interest-rollover, or dealer-gamma-positioning
  feature this repo's data does not yet support, which would be a
  genuinely different mechanism rather than a recomputation of the same
  price-only calendar rule. The `flows_structural.rebalance_and_hedging_
  flows` coverage gap is closed for this specific candidate; other
  mechanisms in that cell (e.g. index-reconstitution flows, quarter-end
  institutional rebalancing) remain open and untested.
