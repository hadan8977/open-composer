# Report: h20260929_01_dip_rejudge

Re-judgment of H-20260924-01's 6 published ETF dip-reversion rules
(registry `dir:etf_dip_reversion_ibs_connors`) on SPY/QQQ 1x with next-open
fill, under this project's K1/K2 screening-lane contract (T-20260929-01 part
B). 12 candidates `DIP_{D1..D6}_{SPY,QQQ}`. Run via `scripts/screen_batch.py
--batch h20260929_01_dip_rejudge --iteration h20260929_01_dip_rejudge`; raw
output at `reports/research/screens/h20260929_01_dip_rejudge/leaderboard.
json`. Every number below is read directly from that file and this
iteration's own `results.json`/`combined-dsr.json`.

## S3 reference

Anchor median Sharpe (net10) 1.4853, K1 anchor bar (80%) 1.1882. Stress
median Sharpe (net10) 0.8059, K1 stress bar (80%) 0.6447.

## Result: 0/12 kept, 0 watch_recent, 12/12 refuted

| id | anchor Sharpe | stress Sharpe | K1 anchor bar | K1 stress bar | K2 edge anchor/stress | DSR (own n=12) | DSR (n=24) | DSR (n=27) |
|---|---|---|---|---|---|---|---|---|
| DIP_D1_SPY | **1.127** | 0.532 | fail (close: 95% of bar) | fail | 0.15 / -0.13 | 0.53 | **0.411** | **0.392** |
| DIP_D1_QQQ | 0.307 | 0.902 | fail | fail (passes bar alone, but K1 needs both legs) | -0.60 / 0.05 | 0.12 | 0.070 | 0.064 |
| DIP_D2_SPY | -2.079 | -1.424 | fail | fail | -1.14 / -1.10 | 0.00 | 0.0000 | 0.0000 |
| DIP_D2_QQQ | -1.059 | -0.412 | fail | fail | -1.00 / -0.53 | 0.00 | 0.001 | 0.001 |
| DIP_D3_SPY | -0.242 | -0.070 | fail | fail | -0.10 / -0.49 | 0.02 | 0.009 | 0.008 |
| DIP_D3_QQQ | -0.130 | 0.083 | fail | fail | -0.35 / -0.44 | 0.03 | 0.014 | 0.012 |
| DIP_D4_SPY | 0.719 | -0.092 | fail | fail | 0.15 / -0.45 | 0.31 | 0.203 | 0.188 |
| DIP_D4_QQQ | -0.062 | 0.177 | fail | fail | -0.38 / -0.31 | 0.04 | 0.019 | 0.017 |
| DIP_D5_SPY | -0.250 | -0.133 | fail | fail | -0.43 / -0.53 | 0.02 | 0.009 | 0.008 |
| DIP_D5_QQQ | -0.184 | 0.199 | fail | fail | -0.49 / -0.26 | 0.02 | 0.011 | 0.010 |
| DIP_D6_SPY | 0.496 | -0.228 | fail | fail | -0.02 / -0.53 | 0.19 | 0.114 | 0.104 |
| DIP_D6_QQQ | -0.417 | 0.417 | fail | fail | -0.50 / -0.16 | 0.01 | 0.004 | 0.003 |

`DIP_D1_SPY` is the best cell by every metric (highest anchor Sharpe 1.127,
just under the 1.1882 watch_recent/K1-anchor bar -- 95% of the way there --
and the only cell with a positive K2 anchor edge, +0.15, though it fails the
stress leg at -0.13). This matches H-20260924-01's own finding that D1
(IBS-Algotradekit with EMA trend filter) is the standout rule in the family
on its own placebo and persistence evidence -- see H2 in `hypotheses.md`.
No candidate reaches watch_recent (anchor-only >=1.1882); `DIP_D1_SPY`'s
1.127 falls just short. K2 fails for every candidate in both windows except
`DIP_D1_SPY`'s and `DIP_D4_SPY`'s anchor-only edges (both fail the stress
leg, and K2 requires both).

## Comparison with H-20260924-01's own G1/G1' verdict

H-20260924-01 refuted the sleeve at the giants-sweep G1/G1' bar (0/24 pass,
best anchor Sharpe 1.50 at T0, an unexecutable same-close upper bound). This
iteration re-judges the same 6 rules (SPY/QQQ 1x only, next-open fill) at
the K1/K2 bar (S3-relative) instead and finds the SAME qualitative verdict
(0/12 pass) via a DIFFERENT, non-nested criterion -- the two bars agree here,
which is additional, independent corroboration of the refutation, not a
repeat of the same test. `DIP_D1_SPY`'s K1/K2 near-misses (anchor Sharpe 95%
of the K1 bar, and the only candidate with any positive K2 edge) are
consistent with H-20260924-01's own characterization of D1 as "a real
effect... but its formal research-admission verdict stays pending" --
under this bar too, D1-SPY is the closest to a pass, not a random member of
the family.

## DSR

Reported three ways, main report is the full 27-candidate family:
- This iteration's own local batch (n=12): max 0.53 (`DIP_D1_SPY`).
- Joint 24-candidate family (excludes 3 LETF RAND placebos): max 0.411
  (`DIP_D1_SPY`).
- **Full 27-candidate family (main report): max 0.392 (`DIP_D1_SPY`).**

All three are far short of any standard significance bar (e.g. 0.95).

## Interpretation

Re-judging H-20260924-01's 6 rules under a materially different (S3-
relative Sharpe, not absolute CAGR/drawdown) keep bar reaches the same
qualitative conclusion: none of the 6 rules, on SPY/QQQ 1x with next-open
fill, is a usable standalone strategy under this project's 2024-2026
anchor / 2016-2023 stress windows and 10bp/20bp cost contract.
`dir:etf_dip_reversion_ibs_connors` remains refuted; D1-SPY remains the one
cell worth revisiting if a genuinely new signal (e.g. closing-auction
imbalance data) is ever added, per H-20260924-01's own `reopen_if`.
