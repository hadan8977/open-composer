---
card_id: H-20260928-02
status: executed, mixed (D1 kept via K1, D2 refuted; 0/2 K2) (round 1, 2026-09-28)
lane: preregistered
previous: H-20260927-01
direction_id: dir:cross_asset_trend_sleeve_with_s3
iteration: h20260928_02_cross_asset_sleeve
criteria:
  - name: k2_combination_sharpe_edge_anchor
    threshold: 0.05
    direction: ">="
  - name: k2_combination_sharpe_edge_stress
    threshold: 0.05
    direction: ">="
  - name: k1_standalone_offset_median_sharpe_anchor
    threshold: 1.1882
    direction: ">="
  - name: k1_standalone_offset_median_sharpe_stress
    threshold: 0.6447
    direction: ">="
  - name: k1_net20_cagr_positive_both_windows
    threshold: 0
    direction: ">"
---
# H-20260928-02 cross-asset defensive-trend sleeve vs delevered S3 control

- Status: **executed, mixed** (round 1) -- hypothesis family: cross_asset_trend_sleeve_with_s3 --
  layer: portfolio construction, one additional sleeve alongside the frozen S3 book -- data tier:
  **tier 3** (OHLCV-derived quantities only)
- Previous link: H-20260927-01 (S1/S2/S3 combination refuted: too correlated with S3)
- Iteration dossier: `reports/research/iterations/h20260928_02_cross_asset_sleeve/`
  (direction-review, external-brief, candidate-manifest with 2 candidates, search-space,
  cost-contract, data-feasibility, trial-ledger, results.json, report.md; passed
  `oc research direction-check` and `oc research iteration validate --stage pre-backtest` and
  `--stage final`)
- One-line hypothesis: does adding one cross-asset defensive-trend sleeve (D1 Carlson's Defense
  First TAA, D2 12-month-vs-SHY absolute momentum with inverse-63-session-vol sizing) to S3, via
  the same trailing-63-session inverse-volatility combination math H-20260927-01 used, beat a
  volatility-matched delevered-S3 control on Sharpe in both the anchor and stress windows (K2), or,
  failing that, is either sleeve standalone-competitive with S3 (K1)?

## Why

H-20260927-01 found S1/S2 too correlated with S3 (0.79-0.83 stress/anchor) for combination to add
value. The queue's local prior art (Step 10 W1 F2, `reports/research/control/step10-w1-cross-asset-trend-2026-09.md`,
not yet registry-backfilled) already found 0/12 broad cross-asset TSMOM candidates standalone
against SPY. This round asks a mechanistically different question -- a defensive four-asset basket
(bonds/gold/commodities/dollar, not broad equity/bond/commodity momentum) judged primarily against
S3-combination value (K2), not standalone excess return against SPY. Registry dedup
(`oc research directions check "cross asset trend sleeve S3 combination TSMOM ETF"`, 2026-09-28)
found no exact prior local test. `dir:defense_first_taa_carlson_concretum` (harvested 2026-09-23)
and `dir:s3_defense_first_remainder` (refuted 2026-09-23, H-20260923-12) are distinguished in
direction-review.json: the remainder round tested Defense First only as a sub-allocation of S3's
own idle cash against plain SHY; this round tests it as an independent full-size sleeve against the
K2 vol-matched-combination bar.

Mechanism is not invented: Carlson (2025, SSRN preprint 10.2139/ssrn.5334772), independently
replicated by AllocateSmartly and Quantitativo, publishes D1's exact rules. D2's own-asset absolute
momentum is grounded in Moskowitz-Ooi-Pedersen (2012, JFE) and Hurst-Ooi-Pedersen (2017, JPM);
its specific thresholds (12-month lookback, 63-session vol, SHY hurdle) are the queue task's round
numbers, not tuned. The combination math (inverse-63-session-vol weighting, vol-matched k*S3+(1-k)*SHY
control) is reused unedited from H-20260927-01's `combo.combine_portfolio` / this round's
`screen_lane.combine_two_sleeves`.

## Design

Machine (frozen, not searched): D1 = `run_h20260923_12_s3_defense_first.defense_weights`'s rules
generalized to an arbitrary signal date (`calendar_return`), rank TLT/GLD/DBC/UUP by the mean of
1/3/6/12 calendar-month returns, weight 40/30/20/10 by rank, any tier below BIL's own score
redirected to SPY. D2 = TLT/GLD/DBC/UUP each held only when trailing-12-month return beats SHY's,
sized by inverse 63-session trailing daily-return volatility, otherwise 100% SHY. Both monthly,
swept across all 21 monthly rebalance-day offsets (`screen_lane.MONTHLY_OFFSETS`) and judged by the
median -- no cherry-picked rebalance date. Cost 10 bp/side primary, 20 bp/side stress on each
candidate's own turnover plus the same rate on the combination's rebalance turnover.

Candidates (2, no ranking between them -- each judged independently against K1/K2):
- **D1**: Carlson's Defense First TAA, published rules, SPY fallback.
- **D2**: absolute momentum vs SHY, inverse-63-session-vol sized.

Windows: select 2023-09-18..2025-12-31, anchor 2024-01-08..2026-09-17 (frozen gate), stress
2016-05-02..2023-09-15, 2026-01-02..2026-09-17 holdout reported but contaminated.

## Gates (adoption rule)

Per candidate, either tier clears it:
- **K2** (primary): judged (median-offset) combination Sharpe (S3+D, inverse-63-session-vol
  weighted) minus vol-matched delevered-S3 control Sharpe >= 0.05 in **both** the anchor window and
  the stress period.
- **K1** (fallback): standalone judged (median-offset) 10bp Sharpe >= 80% of S3's own median Sharpe
  in both windows (anchor bar 1.1882 = 80% of 1.4853; stress bar 0.6447 = 80% of 0.8059, from
  `reports/research/iterations/h20260928_01_s3_rebalance_tranching/results.json`), AND 20bp CAGR
  positive in both windows.
- Strong: K2 edge >= 0.10 both windows, or K1's Sharpe not below S3's own in either window.

G3 (placebo) does not apply: D1's ranking and D2's eligibility are both fully deterministic, no
discretionary pick or gate-timing signal to randomize; the vol-matched control is the
placebo-equivalent check.

## Results

Executed 2026-09-28 (`scripts/screen_batch.py --batch h20260928_02_cross_asset --iteration
h20260928_02_cross_asset_sleeve`; report `reports/research/iterations/h20260928_02_cross_asset_sleeve/report.md`,
`results.json`; raw leaderboard `reports/research/screens/h20260928_02_cross_asset/leaderboard.json`).
**Mixed: D1 kept via K1, D2 refuted; 0/2 cleared K2.**

D1 (Defense First TAA): judged 10bp Sharpe 1.4819 anchor / 0.7292 stress, both clearing the 80%-of-S3
bars (1.1882 / 0.6447); 20bp CAGR +22.80% anchor / +7.68% stress, both positive -> **K1 pass**.
Combination Sharpe edge over vol-matched S3: +0.575 anchor but only +0.037 stress -> **K2 fail**
(needs >=0.05 in both windows). Not strong (anchor Sharpe 1.4819 is 0.0034 below S3's own 1.4853;
stress edge 0.037 well short of the 0.10 strong bar). Correlation with S3: stress 0.272, anchor
0.301, 2022 0.189 -- moderate, well below S1/S2's 0.79-0.83 in H-20260927-01. DSR at anchor
(n_trials=2): 0.968.

D2 (absolute momentum vs SHY, inverse-vol sized): judged 10bp Sharpe 1.1294 anchor (below the 1.1882
bar) / 0.2336 stress (far below 0.6447) -> **K1 fail**. Combination Sharpe edge: +0.637 anchor but
**-0.227 stress** (negative) -> **K2 fail**. Correlation with S3: stress 0.052, anchor 0.035, 2022
0.038 -- essentially decorrelated, ruling out "too correlated" as the failure mode; D2's problem is
weak standalone stress-period return, not correlation. DSR at anchor: 0.905.

Lesson: both candidates are far less correlated with S3 than S1/S2 were (H-20260927-01), and that
shows up as a large anchor-window combination edge for both (+0.575, +0.637) -- but the anchor
window (2024-2026, largely a calm bull market) is not a hard enough test. Neither converts that
decorrelation into a stress-period (2016-05..2023-09, includes 2018Q4/2020/2022) combination edge
>=0.05, which is the bar K2 requires in both windows. Low correlation with S3 is necessary but not
sufficient for a combination edge to survive the harder historical window. D1's standalone result
(K1 pass) is new evidence: Defense First alone, at 10-20bp, is competitive with S3's own
risk-adjusted return, though it does not add combination value once blended with S3. Reopen only
with a new defensive-asset set, a new published combination rule, or new disclosed data -- not by
re-tuning D1/D2's published/round-number parameters or by cherry-picking a rebalance offset.
