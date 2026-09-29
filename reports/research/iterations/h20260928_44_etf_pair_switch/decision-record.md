# Decision Record: h20260928_44_etf_pair_switch

## P1

- Path: `etf_pair_switch_screen` (18 candidates: 12 `PAIR_*` relative-strength
  switch candidates across six highly correlated ETF pairs -- QQQ/SPY,
  SMH/QQQ, XLE/XOP, KRE/XLF, IWM/SPY, ARKK/QQQ -- at lookback {63,126}
  trading days, monthly rebalance, plus 6 `STATIC5050_*` placebo controls,
  one per pair). Both families reuse `run_h20260918_05_recent_menu.py:
  rotation_cell`'s already-live mechanism unedited at menu size 2.
- Decision: **stop** (0 kept, 0 strong_keep, 0 watch_recent, 1 downgraded to
  "not kept -- no switching increment", 11 refuted outright).
- Reason: Per `results.json`, checked against `candidate-manifest.json`'s
  `keep_rule` (K1 anchor >=1.1882 / stress >=0.6447 with positive 20bp CAGR
  both windows; K2 edge >=0.05 both windows; counter-evidence downgrade
  against the paired STATIC5050 control): exactly one candidate,
  `PAIR_SMHQQQ_L63_MO`, clears full K1 on its own numbers (anchor Sharpe
  1.2848, stress Sharpe 0.7679, both above bar; 20bp CAGR positive both
  windows). It is then downgraded by the preregistered counter-evidence rule
  because its own paired control, `STATIC5050_SMHQQQ_MO`, beats it in the
  stress window (0.8882 vs 0.7679) even though the PAIR candidate wins the
  anchor window (1.2848 vs 1.2041) -- the rule requires beating the control
  in every window the candidate passed K1 on, so this counts as no genuine
  switching increment. No other `PAIR_*` candidate reaches K1 in both
  windows or K2 in both windows (every `diversifier_edge_anchor` is
  negative for the PAIR family); `PAIR_SMHQQQ_L126_MO` misses the K1 anchor
  bar by a hair (1.1722 vs 1.1882) and does not qualify for watch_recent
  either. Across most of the six pairs, the STATIC5050 control's
  stress-window Sharpe exceeds its PAIR counterpart's, consistent with the
  preregistered negative-evidence check (Robot Wealth's dual-momentum
  review: whipsaw cost in choppy periods erodes the concentration benefit
  of switching between two highly correlated names).
- Next iteration suggestion: `dir:etf_pair_relative_strength_switch` is
  refuted for this scope; do not re-tune this same 6-pair x {63,126} grid
  without a new, distinct signal (e.g. a volatility- or correlation-adaptive
  switch threshold that only switches when the pair's relative-momentum
  signal is unusually strong, rather than every month regardless of
  conviction) per `hypotheses.md`'s stop/pivot criterion. The coverage-map
  gap `relative_value.pairs_stat_arb`'s long-only leg is resolved with a
  negative result; the still-untested short leg and cointegration/residual
  modeling remain gated on owner permission for shorting, unchanged by this
  round. `dir:etf_pair_relative_strength_switch` is updated to `refuted` in
  `registry-update.json` for the coordinator to merge into
  `reports/research/harvest/directions.jsonl`.
