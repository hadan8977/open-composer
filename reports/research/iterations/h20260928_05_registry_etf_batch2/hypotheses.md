# Hypotheses: h20260928_05_registry_etf_batch2

## H1

- Hypothesis: At least one of the seven preregistered published-rule
  replications (HFEA_UPRO_TMF, TOM_SPY, EOM_REVERSAL_SPY,
  FRONT_RUN_SECTOR_TOP2, FOMC_DRIFT_SPY, FOMC_DRIFT_TQQQ,
  XYLD_COVERED_CALL_PROXY) clears the owner's 2026-09-28 relaxed keep rule
  (K1: median-offset Sharpe >= 80% of S3's in both the anchor and stress
  windows with positive 20bp CAGR; K2: an S3+candidate 63-day inverse-vol
  blend beating a vol-matched k*S3+(1-k)*SHY control by >= 0.05 Sharpe in
  both windows) once `scripts/screen_batch.py --batch h20260928_05_batch2`
  is actually run.
- Failure mode: None of the seven candidates clears K1 or K2 in either
  window -- these well-documented calendar/fixed-weight anomalies (several of
  which report source-level Sharpe ratios of 0.5-0.6, well below S3's 1.49
  anchor / 0.81 stress) do not add value over the S3 incumbent after this
  batch's 10/20bp cost and next-open fill convention in the frozen recent
  regime.
- Measurement: `reports/research/screens/h20260928_05_batch2/leaderboard.md`
  and `.json`, read per candidate: judged (median-offset) anchor and stress
  Sharpe/CAGR, the `diversifier` edge_anchor/edge_stress columns for K2, and
  DSR on the judged anchor excess return with trial_count=7.
- Stop/Pivot criterion: If no candidate clears K1 or K2, each returns to the
  registry (`reports/research/harvest/directions.jsonl`) as
  refuted-in-this-form; no live pilot is authorized on this evidence, and
  none of the seven mechanisms is retried with new parameters inside this
  same manifest.
