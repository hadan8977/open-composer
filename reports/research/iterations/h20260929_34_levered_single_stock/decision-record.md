# Decision Record: h20260929_34_levered_single_stock

## P1

- Path: levered_single_stock_screen (14 candidates: 12 mechanism cells,
  N in {20,50} x k in {1,2,3} x leverage in {1x,2x}, plus
  LSS_N20_EW_2X equal-weight-no-picking control and LSS_RAND_K2_2X
  random-pick placebo).
- Decision: stop. No candidate clears K1 (anchor AND stress Sharpe both
  above the 80%-of-S3 bar) or K2 (>=0.05 diversifier edge vs S3 both
  windows). See `report.md` for the full per-candidate table, sourced from
  `reports/research/screens/h20260929_34_levered_single_stock/leaderboard.json`.
  5 of the 12 mechanism candidates (all top-50-menu: LSS_N50_K1_1X,
  LSS_N50_K2_1X, LSS_N50_K2_2X, LSS_N50_K3_1X, LSS_N50_K3_2X) clear K1's
  anchor-only bar (median-offset net-10bp anchor Sharpe 1.18-1.44 vs the
  1.1882 bar) but none clears the stress bar (best 0.6425-0.6653 vs the
  0.6447 bar, several narrowly short); all 5 beat both falsification
  controls (LSS_N20_EW_2X 0.975, LSS_RAND_K2_2X 0.7181) on judged anchor
  Sharpe, so none is demoted -- these 5 are recorded as `watch_recent`, not
  a keep, per the 2026-09-28 owner rule.
- Reason: the underlying mechanism (63-day momentum, absolute-momentum
  filter, vt40) is the same one that already failed both K1 and K2 at k=37
  on the unlevered broad-top-500 universe (dir:equity_momentum_concentrated_pwb).
  Narrowing k to 1-3 and restricting to a megacap-liquidity top-20/50 menu,
  plus adding 2x synthetic leverage, raises the anchor-window Sharpe (up to
  1.44) and does add a genuine stock-picking increment over an equal-weight
  no-picking control (+0.47 Sharpe) and a random-pick placebo (+0.72
  Sharpe) -- so this is not simply leverage-or-noise. But the increment does
  not survive into the stress window (2016-05..2023-09) at the required
  magnitude in any of the 12 cells, and K2 (diversification value added to
  S3) fails everywhere (best anchor-window edge is essentially 0.00,
  usually negative) -- individual megacap-stock momentum is not a
  meaningfully different return source from S3's already-momentum-driven
  leveraged-sector-ETF book in this sample. Consistent with the concentration/
  leverage risk literature logged in the source cards (FINRA 09-31,
  Daniel & Moskowitz 2016, Piras SSRN, MDPI LETF paper): concentration and
  leverage compound tail risk (stress-window max drawdown -38% to -79% across
  the 5 watch_recent candidates) faster than the narrower stock-picking edge
  compensates for it.
- Next iteration suggestion: no further optimization of this specific
  design (top-1/2/3 megacap momentum + 2x + vt40) is preregistered; the
  5 watch_recent candidates are forward-tracked only (not optimized) per
  the runbook's watch_recent convention, using the frozen rule as of this
  commit. A genuinely different next step, if pursued, would need a
  different return source (not another momentum variant on the same
  megacap-liquidity universe) to plausibly clear K2's diversification bar
  against S3.
