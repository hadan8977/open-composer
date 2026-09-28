# Decision Record: h20260928_40_equity_etf_menus

## P1

- Path: `equity_etf_menus_screen` (24 candidates: FACTOR menu -- MTUM, QUAL,
  USMV, VLUE, SIZE, 12 lookback/top_n/rebalance combinations; INDUSTRY menu --
  SMH, XBI, KRE, ITB, IGV, XOP, XRT, IHI, 12 combinations). Both menus reuse
  `run_h20260918_05_recent_menu.py:rotation_cell`'s mechanism unedited.
- Decision: **stop** (0 kept, 0 strong_keep, 5 watch_recent -- all FACTOR --
  19 refuted).
- Reason: Per `results.json`, checked against `candidate-manifest.json`'s
  keep_rule (K1 anchor >=1.1882 / stress >=0.6447 with positive 20bp CAGR
  both windows; K2 edge >=0.05 both windows): no candidate reaches full K1 or
  K2 in both windows. Five FACTOR candidates (L63_N1_MO, L252_N1_MO,
  L252_N1_WK, L252_N2_MO, L252_N2_WK) clear the anchor-only K1 bar (best
  FACTOR_L252_N1_WK, anchor Sharpe 1.437) but all fail the stress bar by a
  wide margin (best stress Sharpe only 0.405 vs the 0.6447 bar) --
  watch_recent, not a keep. Every candidate's K2 stress edge is negative
  (-0.08 to -0.31) because correlation with S3 in the anchor window is high
  for both menus (0.45-0.81), so the inverse-vol blend adds no
  diversification benefit in the stress regime. No INDUSTRY candidate even
  reaches the anchor-only watch_recent bar (best INDUSTRY_L252_N1_WK, anchor
  Sharpe 0.987); the hypothesized higher-dispersion advantage of narrow
  single-industry ETFs (H2) did not materialize -- INDUSTRY_L63_N1_MO's
  anchor Sharpe is negative (-0.09), consistent with idiosyncratic noise
  dominating a top-1 pick at the shortest lookback.
- Next iteration suggestion: do not re-tune this same 24-candidate grid on
  these two menus without a new, distinct signal (per each hypothesis's
  stop/pivot criterion in `hypotheses.md`). The five FACTOR watch_recent
  candidates are forward-tracked only (per the runbook's watch_recent rule,
  no local optimization is preregistered for them -- the owner has not named
  this menu for the 2026-09-28 optimization round); they move out on a
  3-month forward-window Sharpe <0.5 or a forward drawdown exceeding 1.5x the
  anchor-window drawdown. Both `dir:factor_style_etf_momentum_rotation` and
  `dir:narrow_industry_etf_momentum_rotation` are updated to refuted in
  `reports/research/harvest/directions.jsonl`.
