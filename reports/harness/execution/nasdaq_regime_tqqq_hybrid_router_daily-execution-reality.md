# Execution Reality — nasdaq_regime_tqqq_hybrid_router_daily

Generated: 2026-05-25

## Context
- timeframe: daily
- execution.mode: manual_signal
- execution.fill_assumption: next_bar_open
- execution.broker: none
- leveraged_etf: True
- daily_open: True
- paper_auto: False

## Recommended Policy
- order_style: loo_limit
- time_in_force: opg
- price_protection: limit_offset_bps
- fill_certainty: low
- slippage_risk: low
- description: Limit-on-open with explicit limit offset; cancel if not filled.

## Alternatives Compared
- day_market
- opg_limit

## Rationale
Recommended loo_limit (Limit-on-open with explicit limit offset; cancel if not filled.). Leveraged ETF universe → price protection prioritised over fill certainty. Daily next-bar-open execution → opening-auction routing preferred.

## Reviewer Notes
- Source cards for broker support of the chosen `time_in_force` must be present before paper_auto activation.
- Slippage scenarios use deterministic defaults; replace with strategy-specific stress.
- `gap_stress.max_adverse_gap_pct` is a placeholder — replace with empirically observed worst case.
