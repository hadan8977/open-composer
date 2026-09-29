# Hypotheses: h20260929_34_levered_single_stock

## H1

- Hypothesis: Concentrating S3's own 63-day-momentum/vt40 mechanism onto the
  top 1-3 names of a point-in-time megacap-by-liquidity menu (individual
  stocks, synthetic daily-reset 2x leverage) clears K1 (median-offset anchor
  Sharpe >= 1.1882 and stress Sharpe >= 0.6447 at 10bp, positive 20bp CAGR
  both windows) for at least one of the 12 mechanism candidates.
- Source support: brief's own design (S3 framework transplanted to
  individual stocks); cautioned by dir:equity_momentum_concentrated_pwb
  (unlevered top-37 already failed K1/K2) and the concentration-risk
  literature (quantpedia_momentum_small_portfolios_88pct_drawdown,
  piras_concentrated_momentum_ssrn_via_search_snippet).
- Failure mode: leverage/vt40 amplify volatility drag and 2022-style
  momentum-crash tail risk (daniel_moskowitz_momentum_crashes_2016,
  finra_notice_09_31_leveraged_reset_unsuitable) faster than the tighter
  concentration (k=1-3 vs 37) raises expected return; the mechanism may
  simply repeat momentum_concentrated_k37's K1/K2 failure with extra noise
  from leverage.
- Measurement: scripts/screen_batch.py leaderboard.json, per-candidate
  `judged.anchor.sharpe` / `judged.stress.sharpe` / `per_window.*.net20.cagr`.
- Stop/Pivot criterion: K1 as defined in direction-review.json's
  stop_condition. If no candidate clears K1, H1 is refuted for this design
  (not necessarily for every possible k/N/leverage combination outside the
  preregistered grid).

## H2

- Hypothesis: Even if no candidate clears K1 alone, blending the best
  candidate with S3 (63-session trailing-inverse-vol monthly weighting)
  raises Sharpe over a vol-matched S3+SHY control by >=0.05 in both anchor
  and stress windows (K2) -- i.e. the concentrated-leveraged-stock sleeve
  is a genuine diversifier even if not a standalone keep.
- Source support: S3's own diversification logic (h20260927_01_sleeve_
  combination); individual-stock momentum is mechanically a different
  return source than sector-ETF-level momentum, so low/negative correlation
  is plausible even without a standalone edge.
- Failure mode: individual megacap momentum names may load heavily on the
  same growth/momentum factor S3's underlying ETFs already capture (SMH,
  TQQQ, SOXL, UPRO, TECL, USD are already tech/semi/growth-tilted), so
  correlation with S3 could be high enough that the blend adds no edge --
  this is exactly what dir:equity_momentum_concentrated_pwb's own K2 test
  found (-0.143/-0.071 edge, both negative).
- Measurement: leaderboard.json `diversifier.anchor.judged_edge` /
  `diversifier.stress.judged_edge`, and `correlation_with_s3.anchor` /
  `.stress` for context.
- Stop/Pivot criterion: K2 as defined in direction-review.json's
  stop_condition. If no candidate clears K2 either, both H1 and H2 are
  refuted for this design and the finding is registered as a new,
  narrower negative result (not assumed identical to
  dir:equity_momentum_concentrated_pwb, since k, universe and leverage all
  differ).
