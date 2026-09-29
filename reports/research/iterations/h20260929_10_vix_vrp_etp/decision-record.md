# Decision Record: h20260929_10_vix_vrp_etp

## P1

- Path: `vix_vrp_etp_screen` (12 candidates: 10 primary VVRP_*, 1 RAND
  placebo, 1 static 50/50 SMH/QQQ control).
- Decision: **stop (refuted)**.
- Reason: `scripts/screen_batch.py --batch h20260929_10_vix_vrp_etp
  --iteration h20260929_10_vix_vrp_etp` ran to completion (12/12
  candidates evaluated, none skipped). 0/10 primary VVRP_* candidates
  cleared K1 (need anchor Sharpe >=1.1882 and stress >=0.6447, both, at
  10bp; best anchor was 0.42, best stress-only was 0.90 but with a -0.05
  anchor) or K2 (need diversifier judged_edge >=0.05 in BOTH windows; all
  10 were negative in the anchor window, -0.41 to -0.06). No candidate
  reached watch_recent (needs anchor Sharpe >=1.19) or strong_keep. A
  static 50/50 SMH/QQQ external control (no VIX signal) scored anchor
  Sharpe 1.20 / stress 0.89 -- clearing K1 on its own and beating every
  VVRP_* primary by 0.8-1.3 Sharpe points in the anchor window, which is
  decisive evidence the dual-VIX-signal mechanism adds nothing over a
  trivial diversified-ETF hold. Manual 10-candidate DSR (n=10, excluding
  the placebo/control) ranged 0.25-0.51, nowhere near a publishable
  threshold. Reconciliation against the QuantConnect independent
  replication's own reported Sharpe 0.729 (2016-01..2026-07): the closest
  faithful-parameter analog here (VVRP_COMBO_RV10_SPY) gave a naive ~0.59
  over the same span -- in the same ballpark (methodology differences:
  SVXY vs VIXY, no 2%-no-trade-band, idle-capital handling) but the source
  window and instrument are different enough that this reconciliation is
  context, not itself a pass/fail criterion. See `report.md` for full
  detail and `results.json`/`reports/research/screens/h20260929_10_vix_vrp_etp/leaderboard.json`
  for every number.
- Next iteration suggestion: `dir:vix_term_structure_short_vol` is updated
  to `status: refuted` in the registry (reports/research/harvest/directions.jsonl),
  reopen_if a materially different mechanism (e.g. a genuine VX-futures-
  curve signal, if that data ever becomes available) is proposed with
  fresh evidence -- not the same ETP-only VIX/VIX3M construction tested
  here. No watch_recent or better candidate exists, so nothing is added to
  `reports/research/screens/kept.jsonl` this round.

Status separation: `workflow_pass=true`, `research_pass=false` (refuted),
`llm_contribution_pass=false`, `paper_ready_pass=false`. No paper orders,
broker writes, or simulation activity occurred.
