# Decision Record: h20260929_01_dip_rejudge

## P1

- Path: `dip_rejudge_screen` (12 candidates: `DIP_{D1..D6}_{SPY,QQQ}`).
- Decision: **stop** (0 kept, 0 strong_keep, 0 watch_recent -- 12/12
  refuted).
- Reason: Per `results.json` (checked against `candidate-manifest.json`'s
  `keep_rule`): every candidate's anchor-window Sharpe is below the 1.1882
  K1/watch_recent bar; best is `DIP_D1_SPY` at 1.127 (95% of the bar, the
  closest miss of any candidate in either sibling iteration). `DIP_D1_SPY`
  also has the only meaningfully positive K2 anchor edge (+0.15) but fails
  the stress leg (-0.13), so K2 fails too (needs both windows). This
  re-judges H-20260924-01's 6 published rules (registry `dir:etf_dip_
  reversion_ibs_connors`, refuted 2026-09-24 under the giants-sweep G1/G1'
  bar) under a materially different, S3-relative K1/K2 bar and reaches the
  SAME qualitative verdict (0/12 pass) -- independent corroboration via a
  non-nested criterion, not a repeat of the same test. `DIP_D1_SPY` is the
  standout cell under BOTH bars (H-20260924-01's own placebo/persistence
  evidence and this iteration's K1/K2 near-miss), consistent with
  H-20260924-01's characterization of D1 as showing "a real effect... but
  its formal research-admission verdict stays pending." Full DSR: max
  local-batch (n=12) 0.53; max joint 24-family 0.411; max joint 27-family
  (main report) 0.392 -- all `DIP_D1_SPY`, all far short of any significance
  bar.
- Next iteration suggestion: `dir:etf_dip_reversion_ibs_connors` remains
  refuted, now under two independent, non-nested bars (giants-sweep G1/G1'
  and this project's K1/K2). Do not re-run this same 6-rule family on
  SPY/QQQ without a new, distinct signal. `DIP_D1_SPY` (IBS-Algotradekit
  with EMA200 trend filter) is the one cell that is close under every bar
  tried so far -- per H-20260924-01's own `reopen_if`, the next test worth
  running (if this direction is revisited) is Stage B (the 15:50 ET
  proxy + MOC timing, still unimplemented) or a genuinely new signal (e.g.
  closing-auction imbalance data), not a re-tune of the existing formula.
