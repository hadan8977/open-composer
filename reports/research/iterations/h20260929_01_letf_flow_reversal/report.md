# Report: h20260929_01_letf_flow_reversal

Batch-screening pass for T-20260929-01 part A: 15 candidates (12 primary
`LETF_{SPY,QQQ,SMH}_D{2,3}_H{1,3}` leveraged-ETF close-rebalancing-flow-
reversal candidates + 3 internal `LETF_{SPY,QQQ,SMH}_RAND` placebo
controls). Run via `scripts/screen_batch.py --batch
h20260929_01_letf_flow_reversal --iteration h20260929_01_letf_flow_reversal`;
raw output at `reports/research/screens/h20260929_01_letf_flow_reversal/
leaderboard.json`. Every number below is read directly from that file and
this iteration's own `results.json`/`combined-dsr.json`, checked
candidate-by-candidate against `candidate-manifest.json`'s preregistered
K1/K2/watch_recent/strong_keep thresholds -- no candidate, grid point, or
threshold was changed after seeing a result.

## S3 reference

Anchor median Sharpe (net10) 1.4853, K1 anchor bar (80%) 1.1882. Stress
median Sharpe (net10) 0.8059, K1 stress bar (80%) 0.6447 (both from
`h20260928_01_s3_rebalance_tranching/results.json`).

## Result: 0/12 primary kept, 0 watch_recent, 12/12 primary refuted

| id | anchor Sharpe | stress Sharpe | K1 anchor bar | K1 stress bar | K2 edge anchor/stress | DSR (own n=15) | DSR (n=24) | DSR (n=27) |
|---|---|---|---|---|---|---|---|---|
| LETF_SPY_D2_H1 | 0.267 | -0.398 | fail | fail | -0.03 / -0.66 | 0.09 | 0.060 | 0.054 |
| LETF_SPY_D2_H3 | -0.445 | -0.223 | fail | fail | -0.52 / -0.59 | 0.01 | 0.003 | 0.002 |
| LETF_SPY_D3_H1 | 0.160 | -0.479 | fail | fail | -0.05 / -0.75 | 0.07 | 0.042 | 0.038 |
| LETF_SPY_D3_H3 | -0.783 | -0.018 | fail | fail | -0.40 / -0.51 | 0.00 | 0.0001 | 0.0001 |
| LETF_QQQ_D2_H1 | 0.172 | -0.065 | fail | fail | -0.10 / -0.31 | 0.07 | 0.045 | 0.040 |
| LETF_QQQ_D2_H3 | -0.044 | 0.286 | fail | fail | -0.36 / -0.14 | 0.03 | 0.020 | 0.018 |
| LETF_QQQ_D3_H1 | -0.219 | 0.036 | fail | fail | -0.35 / -0.36 | 0.02 | 0.010 | 0.009 |
| LETF_QQQ_D3_H3 | -0.623 | -0.074 | fail | fail | -0.70 / -0.42 | 0.00 | 0.0009 | 0.0008 |
| LETF_SMH_D2_H1 | **0.796** | -0.257 | fail | fail | -0.00 / -0.48 | 0.31 | **0.232** | **0.216** |
| LETF_SMH_D2_H3 | -0.183 | 0.122 | fail | fail | -0.88 / -0.33 | 0.02 | 0.012 | 0.011 |
| LETF_SMH_D3_H1 | 0.503 | 0.215 | fail | fail | -0.19 / -0.15 | 0.17 | 0.121 | 0.111 |
| LETF_SMH_D3_H3 | -0.229 | 0.057 | fail | fail | -0.92 / -0.36 | 0.02 | 0.009 | 0.008 |

Every primary candidate fails K1 on both legs (all 12 anchor-window Sharpes
are below the 1.1882 bar -- best is `LETF_SMH_D2_H1` at 0.796, still 46%
short; all 12 stress-window Sharpes are also below 0.6447, and 5 of 12 are
outright negative). No candidate reaches even the weaker anchor-only
`watch_recent` bar. K2 fails identically: every diversifier edge is negative
in the anchor window and every one is negative in the stress window (adding
any of these 12 rules to S3 would make the combined portfolio worse, not
better, in every case, in both windows).

## RAND placebo comparison (internal falsification)

| ticker | D2_H1 anchor Sharpe | RAND anchor Sharpe | real beats RAND? |
|---|---|---|---|
| SPY | 0.267 | -1.455 | yes |
| QQQ | 0.172 | -1.639 | yes |
| SMH | 0.796 | -0.237 | yes |

The real drop-conditioned entry beats its own frequency-matched random-day
placebo on all three tickers (anchor window) -- so the mechanism is NOT
demoted by the preregistered placebo rule (which would only fire if a
primary candidate were otherwise kept; none was). This is worth reporting on
its own terms: the drop-day conditioning IS doing something distinguishable
from a random entry of the same frequency, it is simply not enough to clear
K1/K2 against S3 under this cost/fill contract.

## DSR

Three reportings, per the queue task's instruction to report both 24 (non-
placebo) and 27 (full family, matching the queue's literal instruction) --
main report is 27:
- This iteration's own local batch (n=15, 12 primary + 3 placebo, as
  `scripts/screen_batch.py` computes automatically): max overall 0.31
  (`LETF_SMH_D2_H1`).
- Joint 24-candidate family (12 LETF primary + 12 DIP, excludes the 3 RAND
  placebos; computed manually via `scripts/compute_h20260929_01_combined_
  dsr.py`, saved to `combined-dsr.json`): max among LETF candidates 0.232
  (`LETF_SMH_D2_H1`); max overall (including the DIP_* candidates) 0.411
  (`DIP_D1_SPY`, see the sibling report).
- **Full 27-candidate family (main report, matches the queue task's literal
  instruction): max among LETF candidates 0.216 (`LETF_SMH_D2_H1`); max
  overall 0.392 (`DIP_D1_SPY`).**

All three DSR figures are far short of any standard significance bar (e.g.
0.95), consistent with 0/12 primary candidates clearing K1 or K2.

## Interpretation

Lenkey (2024)'s own synthesis reads the leveraged-ETF rebalancing-flow
literature as producing statistically significant but economically
insignificant associations. This batch's result is consistent with that
reading: the mechanism is directionally real (drop-day entries beat
frequency-matched random entries on every ticker), but the magnitude is too
small to clear either K1 (Sharpe vs. S3) or K2 (diversifier value added to
S3) under this project's 10bp/20bp next-open-fill contract. `LETF_SMH_D2_H1`
(SMH, -2% threshold, 1-day hold) is the standout cell by every metric here
(highest anchor Sharpe, highest DSR, smallest K2 shortfall) -- if this
direction is ever revisited (e.g. with an actual AUM/flow-magnitude proxy
instead of a fixed price threshold), SMH -2%/1-day is the specific cell to
start from.
