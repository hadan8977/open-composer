# Decision Record: h20260929_01_letf_flow_reversal

## P1

- Path: `letf_flow_reversal_screen` (15 candidates: 12 primary
  `LETF_{SPY,QQQ,SMH}_D{2,3}_H{1,3}` + 3 internal `LETF_{SPY,QQQ,SMH}_RAND`
  placebos).
- Decision: **stop** (0 kept, 0 strong_keep, 0 watch_recent -- 12/12 primary
  refuted).
- Reason: Per `results.json` (checked against `candidate-manifest.json`'s
  `keep_rule`: K1 anchor >=1.1882 / stress >=0.6447 with positive 20bp CAGR
  both windows; K2 edge >=0.05 both windows): every one of the 12 primary
  candidates has an anchor-window Sharpe below the K1 bar (best
  `LETF_SMH_D2_H1` at 0.796, 33% short of 1.1882) and every stress-window
  Sharpe is also below its bar (5 of 12 are outright negative). K2 fails
  identically -- every diversifier edge is negative in both windows for all
  12 candidates. The preregistered RAND-placebo internal-falsification rule
  did not need to fire (nothing was kept to demote), but the real
  drop-conditioned entries do beat their own frequency-matched random-day
  placebo on all three tickers (e.g. SMH: 0.796 vs. RAND's -0.237) --
  independent evidence the mechanism is directionally real, just too small
  to clear K1/K2 under this cost/fill contract, consistent with Lenkey
  (2024)'s own "statistically significant, economically insignificant"
  reading. Full DSR: max local-batch (n=15) 0.31; max joint 24-family 0.232;
  max joint 27-family (main report) 0.216 -- all `LETF_SMH_D2_H1`, all far
  short of any significance bar.
- Next iteration suggestion: `dir:letf_close_rebalancing_flow_reversal` is
  refuted for this scope (SPY/QQQ/SMH, fixed 2%/3% price-drop threshold,
  1/3-day hold, 2024-2026 anchor + 2016-2023 stress windows, 10bp/20bp
  next-open-fill contract). Do not re-tune this same fixed-threshold grid on
  this same universe without a new, distinct signal -- e.g. an actual
  AUM/flow-magnitude proxy (options open interest, fund-flow data, or the
  leveraged product's own end-of-day volume) instead of a fixed price-return
  threshold, which this repo's data does not yet support. If revisited,
  `LETF_SMH_D2_H1` (SMH, -2% threshold, 1-day hold) is the specific cell to
  start from -- it leads on anchor Sharpe, DSR, and K2 shortfall margin
  among all 12 primary candidates.
