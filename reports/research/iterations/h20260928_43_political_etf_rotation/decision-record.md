# Decision Record: h20260928_43_political_etf_rotation

## P1

- Path: `political_etf_rotation_screen` (24 candidates: POLITICAL menu --
  NANC, GOP, MAGA, DEMZ, 12 lookback/top_n/rebalance combinations;
  PLACEBO_BIGTECH menu -- QQQ, XLK, SPY, DIA, 12 combinations, a
  preregistered placebo). Both menus reuse
  `run_h20260918_05_recent_menu.py:rotation_cell`'s mechanism unedited,
  judged on the select and anchor windows only (stress window not computed
  -- NANC/GOP launched 2023-02-07, zero coverage).
- Decision: **stop** (0 kept, 0 strong_keep, 0 watch_recent -- all 24
  refuted).
- Reason: Per `results.json`, checked against `candidate-manifest.json`'s
  keep_rule (watch_recent bar: anchor-window date-neutral Sharpe >= 1.1882,
  10bp; K2: 63-session inverse-vol blend edge with S3 >= 0.05 both windows):
  no POLITICAL candidate reaches even the anchor-only watch_recent bar. The
  closest, `POLITICAL_L252_N1_MO`, has anchor Sharpe 0.9015 (76% of the bar)
  and select Sharpe 0.886. Every candidate's K2 diversifier edge with S3 is
  negative in the anchor window (-0.18 to -0.45 for POLITICAL, -0.29 to
  -0.58 for PLACEBO_BIGTECH), so K2 fails everywhere as well. Because no
  POLITICAL candidate cleared the bar, the preregistered placebo-dominance
  disqualifier never triggers; the placebo comparison itself is mixed (7 of
  12 grid cells favor POLITICAL, 5 favor PLACEBO_BIGTECH), so the batch is
  refuted on its own Sharpe numbers, not decided by the placebo question.
  The 40bp wide-spread sensitivity check was not run because its
  preregistered trigger condition (a watch_recent-or-better POLITICAL
  candidate) was never met.
- Next iteration suggestion: do not re-tune this same 24-candidate grid on
  these two menus without a new, distinct signal, per the stop/pivot
  criterion in `hypotheses.md`'s H1. `dir:congressional_political_trade_replica_etf_rotation`
  is updated to refuted in `registry-update.json` (applied by the
  coordinator to `reports/research/harvest/directions.jsonl`, per this
  task's restriction against editing that file directly). The
  `public_records.copy_verified_live` coverage gap remains open for a
  future round; `coverage-update.json` records this attempt and its result
  for that cell. No candidate is added to `kept.jsonl` (nothing reached
  watch_recent or better).
