# Hypotheses: h20260928_40_equity_etf_menus

Twenty-four candidates, two hypotheses (one per menu, 12 grid cells each), all
sharing the same engine and falsification design: compute the candidate under
`run_h20260918_05_recent_menu.py:rotation_cell`'s unedited mechanism (top-N
cross-sectional momentum by lookback, absolute-momentum-vs-SHY filter,
monthly/weekly rebalance), then check K1 and K2 against S3's frozen reference
numbers (date-neutral anchor Sharpe 1.49, stress Sharpe 0.81). No backtest is
run under this dossier; the screening lane consumes candidate-manifest.json
and reports results back into this iteration.

## H1 -- FACTOR menu (MTUM, QUAL, USMV, VLUE, SIZE) clears K1 or K2 on at least one grid cell

- Hypothesis: at least one of the 12 lookback/top_n/rebalance combinations on
  the factor-style ETF menu has a date-neutral Sharpe within 80% of S3's in
  both the anchor and stress windows (K1), or blends with S3 at 63-session
  inverse-vol to beat a vol-matched k*S3+(1-k)*SHY control by 0.05 Sharpe in
  both windows (K2), because Quantpedia's published mechanism (cross-sectional
  momentum across style ETFs) is the same family as S1-S3's already-live
  engine, only the universe (single-factor ETFs, dispersion driven by factor
  exposure rather than sector) is new.
- Failure mode: Quantpedia's own reported long-short Sharpe for this mechanism
  is only 0.33 over 1972-2005 -- weak even on its own historical sample and
  computed on a different (older, long-short, six-style) universe than the
  five modern single-factor ETFs used here; the modern factor ETFs may simply
  have too much pairwise correlation (all are large-cap US equity factor
  tilts) for cross-sectional top-N selection to add value over buying the
  market, and a top-N=1/2 long-only construction with an absolute-momentum
  cash filter may not reproduce even the modest edge the long-short version
  reported.
- Measurement: date-neutral Sharpe (median over offsets: 0-20 trading days
  monthly, 0-4 trading days weekly) in the stress window 2016-05-02..
  2023-09-15 and the anchor window 2024-01-08..2026-09-17, at 10bp cost; CAGR
  at 20bp cost; K2's paired vol-matched control per candidate; DSR with
  n_trials=24.
- Stop/Pivot criterion: if none of the 12 FACTOR candidates clears K1 or K2 (or
  reaches the anchor-only watch_recent bar), dir:factor_style_etf_momentum_rotation
  is refuted for this scope and the next round should not re-tune this same
  grid on this same menu without a new, distinct signal (e.g. a value or
  quality factor this repo's data does not yet support, per prior data-gap
  notes).

## H2 -- INDUSTRY menu (SMH, XBI, KRE, ITB, IGV, XOP, XRT, IHI) clears K1 or K2 on at least one grid cell

- Hypothesis: at least one of the 12 lookback/top_n/rebalance combinations on
  the narrow-industry ETF menu clears K1 or K2, because it reuses the exact
  mechanism already live and passing on S1's 11-broad-SPDR-sector menu
  (median-offset anchor Sharpe 1.33-1.35), and narrower single-industry ETFs
  have higher pairwise return dispersion than the 11 broad sectors, which is
  the raw material cross-sectional momentum needs.
- Failure mode: higher dispersion also means higher idiosyncratic noise (a
  single company's earnings surprise can swing KRE or XBI without reflecting a
  durable industry trend), so top-N selection could chase noise rather than
  trend, producing a lower Sharpe than the broader S1 sector menu despite the
  identical mechanism; K2 in particular could fail if the INDUSTRY menu's
  correlation with S3's own levered-semiconductor exposure is high (SMH
  overlaps directly with S3's SOXL-adjacent holdings), reducing the
  diversification benefit even if K1's standalone Sharpe is reasonable.
- Measurement: same date-neutral Sharpe/CAGR/DSR protocol as H1, plus each
  candidate's correlation with S3 in the anchor, stress and 2022 windows
  (reported by the lane automatically).
- Stop/Pivot criterion: if none of the 12 INDUSTRY candidates clears K1 or K2
  (or reaches watch_recent), dir:narrow_industry_etf_momentum_rotation is
  refuted for this scope; the negative-evidence check attempted for this
  menu (Molchanov & Stangl, blocked 403 in this session) is recorded but not
  the deciding factor either way -- the batch's own K1/K2 numbers are.
