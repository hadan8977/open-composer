# Report: h20260928_40_equity_etf_menus

Batch-screening pass for T-20260928-40: 24 candidates, the same cross-sectional
momentum rotation mechanism already live on S1-S3
(`run_h20260918_05_recent_menu.py:rotation_cell`, unedited), applied to a
FACTOR-style ETF menu (MTUM, QUAL, USMV, VLUE, SIZE) and a narrow INDUSTRY ETF
menu (SMH, XBI, KRE, ITB, IGV, XOP, XRT, IHI), grid = lookback {63,126,252}
trading days x top_n {1,2} x rebalance {monthly, weekly}. Run via
`scripts/screen_batch.py --batch h20260928_40_equity_etf_menus --iteration
h20260928_40_equity_etf_menus`; raw output at
`reports/research/screens/h20260928_40_equity_etf_menus/leaderboard.json`.
Every number below is read directly from that file and
`reports/research/iterations/h20260928_40_equity_etf_menus/results.json`, and
checked candidate-by-candidate against `candidate-manifest.json`'s
preregistered K1/K2/watch_recent/strong_keep thresholds -- no candidate,
grid point, or threshold was changed after seeing a result.

## S3 reference (from `h20260928_01_s3_rebalance_tranching/results.json`)

Anchor median Sharpe (net10) 1.4853, K1 anchor bar (80%) 1.1882. Stress
median Sharpe (net10) 0.8059, K1 stress bar (80%) 0.6447.

## Result: 0 kept, 0 strong_keep, 5 watch_recent, 19 refuted

None of the 24 candidates clears full K1 (both windows) or K2 (both windows).
Every candidate's stress-window edge with S3 (`diversifier_edge_stress`) is
negative (range -0.08 to -0.31), so K2 fails on the stress leg for all 24
regardless of the anchor-window edge -- both menus track S3's own
equity-momentum exposure too closely to add diversification value in the
2016-2023 stress window. Full K1 also fails for all 24 because every
candidate's stress-window Sharpe (0.15-0.62) is well below the 0.6447 bar,
even though several FACTOR candidates clear the anchor-window bar alone.

### watch_recent (5, all FACTOR menu -- anchor-only K1, forward-tracked, not a keep)

| id | anchor Sharpe (10bp, judged) | stress Sharpe (10bp, judged) | K2 edge anchor/stress | DSR anchor |
|---|---|---|---|---|
| FACTOR_L252_N1_WK | 1.437 | 0.176 | 0.03 / -0.31 | 0.643 |
| FACTOR_L252_N1_MO | 1.378 | 0.247 | 0.01 / -0.30 | 0.607 |
| FACTOR_L63_N1_MO  | 1.364 | 0.405 | 0.05 / -0.15 | 0.600 |
| FACTOR_L252_N2_WK | 1.254 | 0.149 | -0.02 / -0.31 | 0.529 |
| FACTOR_L252_N2_MO | 1.249 | 0.266 | -0.02 / -0.29 | 0.526 |

All five clear the anchor-only watch_recent bar (median-offset anchor Sharpe
>= 1.1882) but fail the K1 stress bar (>= 0.6447) by a wide margin (best
stress Sharpe among the five is 0.405). Per the runbook's watch_recent rule,
these are recorded in `reports/research/screens/kept.jsonl` with
`tier: watch_recent` for forward-only tracking; they are not promoted and no
further optimization is preregistered for them (the owner has not named this
FACTOR menu for optimization the way EOM reversal and sector seasonality were
named on 2026-09-28).

### Best-DSR refuted candidate reported for context

`FACTOR_L252_N1_WK` has the highest DSR (0.643) among all 24 -- still well
below any adoption bar and driven by the anchor-only Sharpe (1.437), not by
clearing both windows.

### INDUSTRY menu: refuted outright, closest to watch_recent

`INDUSTRY_L252_N1_WK` (anchor Sharpe 0.987, stress Sharpe 0.404) is the best
INDUSTRY candidate and does not reach even the anchor-only watch_recent bar
(1.1882). No INDUSTRY candidate reaches the K1 anchor bar at any grid point --
the higher idiosyncratic dispersion of narrow single-industry ETFs (the
hypothesized advantage in `hypotheses.md`'s H2) did not translate into a
higher cross-sectional-momentum Sharpe than the FACTOR menu or S1's own
11-broad-sector menu; if anything `INDUSTRY_L63_N1_MO`'s anchor Sharpe is
negative (-0.09), consistent with idiosyncratic noise dominating the top-1
pick at the shortest lookback.

## Why K2 fails everywhere: correlation with S3

`correlation_with_s3.anchor` is 0.63-0.81 for every candidate (FACTOR
0.66-0.72, INDUSTRY 0.45-0.81, highest for INDUSTRY_L252_N1_WK at 0.81 which
directly overlaps SMH-driven semiconductor exposure with S3's own levered
holdings). This high correlation is exactly why the 63-session inverse-vol
blend with S3 adds little to no diversification benefit, and turns negative
in the stress window for all 24.

## Verdict

Both `dir:factor_style_etf_momentum_rotation` and
`dir:narrow_industry_etf_momentum_rotation` are refuted for this scope (no
K1 or K2 pass; FACTOR reaches watch_recent only). See `decision-record.md`
for the stop decision and `reports/research/harvest/directions.jsonl` for the
registry update.
