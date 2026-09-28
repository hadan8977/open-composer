# Decision Record: h20260928_05_registry_etf_batch2

## P1

- Path: `registry_etf_batch2_screen` (7 candidates: HFEA_UPRO_TMF, TOM_SPY,
  EOM_REVERSAL_SPY, FRONT_RUN_SECTOR_TOP2, FOMC_DRIFT_SPY, FOMC_DRIFT_TQQQ,
  XYLD_COVERED_CALL_PROXY).
- Decision: **pivot** (2/7 watch_recent -- forward-tracked only, not kept,
  not promoted; 5/7 stop).
- Reason: Per `results.json`'s `adoption` block, checked against
  candidate-manifest.json's adoption_rule (K1 anchor >=1.1882 / stress
  >=0.6447 with positive 20bp CAGR both windows; K2 combination edge >=0.05
  both windows; runbook section 5's forward-only `watch_recent` tier for
  anchor-only K1 passes): EOM_REVERSAL_SPY (anchor Sharpe 1.2406, stress
  0.5845) and FRONT_RUN_SECTOR_TOP2 (anchor 1.4022, stress 0.4517) both clear
  the K1 anchor bar (1.1882) but miss the stress bar (0.6447) -> tier
  `watch_recent` per the runbook's forward-only rule, not kept and not
  promoted to any live pilot. Both also fail K2 in the stress window (-0.173,
  -0.168). Both candidates were corrected from a monthly ("M") declaration to
  a single-version ("D") declaration on their calendar-anchored dates before
  any valid result was computed -- see `candidate-manifest.json`'s
  `parameters.freq_correction`: declaring them "M" made offsets 1-20 never
  fire (the signal is only defined at the calendar-anchored date), so the
  offset-median silently degenerated to pure SHY; this was caught and fixed
  in the same session, before either candidate had a first result. The other
  5 candidates (HFEA_UPRO_TMF, TOM_SPY, FOMC_DRIFT_SPY, FOMC_DRIFT_TQQQ,
  XYLD_COVERED_CALL_PROXY) fail K1 on anchor Sharpe alone (all below 1.1882)
  and fail K2 in at least one window -- **stop**.
- Next iteration suggestion: log EOM_REVERSAL_SPY and FRONT_RUN_SECTOR_TOP2
  to `reports/research/screens/kept.jsonl` with `tier: "watch_recent"` for
  forward-only tracking (no optimization, no promotion); drop either if 3
  forward months show Sharpe <0.5 or a max drawdown exceeding 1.5x its
  anchor-window drawdown. Mark the other 5 refuted-in-this-form in the
  registry per each direction's own stop_condition; do not retry any of the 7
  with new parameters inside this same manifest without a new mechanism or
  new disclosed data.
