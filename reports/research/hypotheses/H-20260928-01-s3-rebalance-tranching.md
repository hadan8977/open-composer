---
card_id: H-20260928-01
status: executed, refuted (round 1, 2026-09-28)
lane: preregistered
previous: H-20260927-01
direction_id: dir:s3_rebalance_timing_luck_tranching
iteration: h20260928_01_s3_rebalance_tranching
criteria:
  - name: anchor_max_drawdown_vs_o00
    threshold: 0
    direction: "shallower"
  - name: stress_max_drawdown_vs_o00
    threshold: 0
    direction: "shallower"
  - name: sharpe_giveup_vs_o00_anchor_and_stress
    threshold: 0.05
    direction: "<="
  - name: anchor_g1_or_g1alt_10bp_and_20bp
    threshold: pass
    direction: required
---
# H-20260928-01 S3 rebalance timing luck and four-tranche execution

- Status: **executed, refuted** (round 1). Data tier 3 (OHLCV only). Execution-layer question
  on the frozen S3 book; no pick, lookback or overlay parameter re-searched.
- Iteration dossier: `reports/research/iterations/h20260928_01_s3_rebalance_tranching/`
  (passed `oc research direction-check`, `iteration validate --stage pre-backtest` and `final`).
- Question: S3 trades once a month at the month-end close. Does splitting it into four tranches
  that trade on different days lower max drawdown without costing Sharpe or the G1 bar?

## Why

Published work (Hoffstein, Sibears, Faber 2019; Hoffstein, Faber, Braun 2020; Concretum 2025;
Allocate Smartly) finds rebalance timing luck above 100 bp a year for concentrated monthly books
(348 bp on a 20-stock momentum portfolio) and shows that tranching leaves mean CAGR and Sharpe
unchanged while cutting the dispersion. None reports drawdowns for tranched books or covers a
two-ETF leveraged rotation with a volatility target.

## Design

- O00..O20: live S3 (vt40 + QQQ dip boost 0.60/10) with the monthly signal close moved 0..20
  sessions after month end. O00 is the live rule, asserted bit-equal to `salvage.run_cell`.
  O01..O20 are descriptive only.
- T4: one account, four equal tranches at offsets 0/5/10/15, each with its own picks and vol
  multiplier; weights averaged, cost on netted turnover.
- Pass (all four, net 10 bp): (a) anchor max DD shallower than O00; (b) stress (2016-05..2023-08)
  max DD shallower; (c) Sharpe not lower by more than 0.05 in anchor and stress; (d) anchor G1 or
  G1' at 10 and 20 bp.

## Results

`scripts/run_h20260928_01_s3_rebalance_tranching.py`, `results.json`, `report.md`.
**Refuted 0/4.**

| | anchor CAGR | anchor Sharpe | anchor max DD | stress Sharpe | stress max DD |
|---|---|---|---|---|---|
| O00 (live) | 116.3% | 1.82 | -32.3% | 0.87 | -48.0% |
| T4 | 87.0% | 1.52 | -35.2% | 0.90 | -52.0% |
| 21-offset median | 85.8% | 1.49 | -35.4% | 0.81 | -56.8% |
| 21-offset range | 59.9..116.3% | 1.12..1.82 | -49.7..-28.9% | 0.62..0.92 | -71.0..-44.3% |

- O00 is rank 1 of 21 on CAGR and Sharpe in both the select and the anchor window. Only 10 of 21
  offsets pass G1/G1' in the anchor window (8 of 21 in select). In the stress window O00 is
  ordinary (CAGR rank 9) and no offset passes G1. In the contaminated 2026 window all 21 pass.
- T4 sits at the median of the offsets, as the literature predicts; it fails because the live
  month-end date happens to be the luckiest one in the recent windows.

## Lesson

S3 was chosen from a grid on the select window where its month-end date was the best of 21. Part
of its headline edge is date luck. Date-neutral expectation for 2024-01..2026-09: about 86% CAGR,
Sharpe 1.5, max DD about -35%. Tranching is not adopted; use the date-neutral figures for any live
sizing, and check S1/S2 the same way (T-20260928-01). Reopen tranching only with a new mechanism,
not a different tranche count.
