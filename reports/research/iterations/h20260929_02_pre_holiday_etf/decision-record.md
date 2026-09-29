# Decision Record: h20260929_02_pre_holiday_etf

## P1

- Path: `pre_holiday_etf_screen` (18 candidates: 12 primary PREHOL_*_H1/H2,
  6 RAND placebos).
- Decision: **stop (refuted)**.
- Reason: `scripts/screen_batch.py --batch h20260929_02_pre_holiday_etf
  --iteration h20260929_02_pre_holiday_etf` ran to completion (18/18
  candidates evaluated, none skipped). 0/12 primary PREHOL_* candidates
  cleared K1 (need anchor Sharpe >=1.1882 and stress >=0.6447, both, at
  10bp) or K2 (need diversifier judged_edge >=0.05 in BOTH windows) --
  every primary candidate's judged anchor and stress Sharpe was negative
  (best anchor -0.81, best stress -0.43). No candidate reached
  `watch_recent` (needs anchor Sharpe >=1.1882) or `strong_keep`. 10 of 12
  primary candidates were additionally beaten by their own ticker's
  frequency-matched RAND placebo on judged anchor Sharpe (internal
  falsification), though this changed no verdict since all 12 already
  failed K1/K2 outright. Manual 12-candidate DSR (excluding the 6
  placebos) ranged 0.001-0.065, nowhere near a publishable/promotable
  threshold. The small-cap tier's (IWM/IJR/IWC/VB) median judged Sharpe
  was less negative than the large-cap tier's (SPY/QQQ) in both windows
  (+0.32 anchor, +0.06 stress) -- the same *direction* as Ko & Yang
  (2021)'s own small-firm-only out-of-sample pattern -- but both tiers
  are deeply unprofitable, so this is a "less bad" relative difference
  between two failing groups, not evidence of a tradable small-cap edge.
  See `report.md` for full detail and
  `reports/research/screens/h20260929_02_pre_holiday_etf/leaderboard.json`/
  `results.json` for every number.
- Next iteration suggestion: `dir:pre_holiday_effect_small_cap_tier` is
  updated to `status: refuted` in the registry
  (reports/research/harvest/directions.jsonl), reopen_if a materially
  different construction is proposed with fresh evidence -- e.g. an
  individual-stock-level (not ETF-level) small-cap universe closer to Ko &
  Yang's own CRSP-decile definition, or a shorter holding window isolating
  only the single pre-holiday session with a lower cost assumption -- not
  a repeat of this exact 18-candidate ETF-level construction. No
  watch_recent or better candidate exists, so nothing is added to
  `reports/research/screens/kept.jsonl` this round.

Status separation: `workflow_pass=true`, `research_pass=false` (refuted),
`llm_contribution_pass=false`, `paper_ready_pass=false`. No paper orders,
broker writes, or simulation activity occurred.
