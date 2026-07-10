# Decision Record: mom_minute_r1

This record is pending Wave 9.4 results. Pre-backtest decisions are only the
matrix revisions from Wave 9.3; final continue/pivot/stop calls must be filled
after trial ledgers and evaluation reports exist.

## P1

- Path: P1_time_series_etf_momentum
- Decision: pending
- Reason: retained for bounded QQQ `30m`/`1h` non-ML testing because time-series
  momentum is a credible baseline and Wave 9.2 data coverage is sufficient.
- Next iteration suggestion: if P1 survives cost and recent-fold gates, consider
  a small volatility-managed extension before ML.

## P2

- Path: P2_cross_sectional_etf_rotation
- Decision: pending
- Reason: pre-backtest stop/defer because Wave 9.2 found insufficient same-
  timeframe ETF coverage for an honest cross-sectional run.
- Next iteration suggestion: reopen only after broader ETF minute history is
  materialized with PIT universe caveats.

## P3

- Path: P3_overnight_intraday_decomposition
- Decision: pending
- Reason: retained as a separate hypothesis because overnight and intraday
  return components can differ.
- Next iteration suggestion: if P3 survives, compare the best split against P1
  before adding ML features.

## P4

- Path: P4_volatility_adjusted_momentum
- Decision: pending
- Reason: deferred as a separate path to keep the first round at 28 combinations
  and avoid adding regime parameters before base evidence exists.
- Next iteration suggestion: use only as a follow-up risk-control layer if P1 or
  P3 produces a stable base-cost candidate.

## Later Entry Conditions

- Path: ML_round_candidate
- Decision: pending
- Reason: Step 9 requires ML, but only after at least one non-ML path survives
  the full Wave 9.4 gate and produces enough OOS decisions for training.
- Next iteration suggestion: if a path survives and has >=800 OOS decisions,
  evaluate LightGBM versus a linear baseline with purged/embargoed splits.

- Path: AI_information_candidate
- Decision: pending
- Reason: news/LLM features need point-in-time packets and marginal-lift
  evidence before they affect trading.
- Next iteration suggestion: keep advisory-only until a quant candidate survives
  and capability evaluation for news/event sources passes.
