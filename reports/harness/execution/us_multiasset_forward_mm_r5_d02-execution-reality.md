# Execution Reality — us_multiasset_forward_mm_r5_d02

Generated: 2026-07-30

## Context
- timeframe: daily
- execution.mode: manual_signal
- execution.fill_assumption: next_bar_open
- execution.broker: none
- leveraged_etf: False
- daily_open: True
- paper_auto: False

## Recommended Policy
- order_style: opg_limit
- time_in_force: opg
- price_protection: limit_price
- fill_certainty: medium
- slippage_risk: low
- description: Limit-on-open routed to exchange opening auction.

## Alternatives Compared
- moo_market
- opg_limit
- delayed_open_30m_shadow

## Rationale
Recommended opg_limit (Limit-on-open routed to exchange opening auction.). Daily next-bar-open execution → opening-auction routing preferred.

## Reviewer Notes
- Source cards for broker support of the chosen `time_in_force` must be present before paper_auto activation.
- Slippage scenarios use deterministic defaults; replace with strategy-specific stress.
- `gap_stress.max_adverse_gap_pct` is a placeholder — replace with empirically observed worst case.
