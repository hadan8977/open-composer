---
name: execution-reality-reviewer
description: >
  Review daily-open, leveraged-ETF or paper_auto execution: compare order styles,
  stress slippage/gaps, assess capacity and plan TCA. Required before daily-open
  paper_auto activation; applies to next_bar_open and the corresponding risk domains.
---

# Execution reality

Read the StrategySpec execution/universe/timeframe, harness risk domains and verified broker/exchange cards from [source-researcher](../source-researcher/SKILL.md).

Write `reports/harness/execution/{strategy}-execution-policy.json`, `{strategy}-execution-reality.json` and its `.md` summary. Use the exact required fields in [artifact contracts](../../../harness/artifact_contracts.yaml); [risk domains](../../../harness/risk_domains.yaml) determine additional artifacts.

## Compare policies

Compare at least two supported styles on price protection, fill certainty, slippage and complexity. Candidates include DAY market, MOO (`market` + `opg`), LOO (`limit` + `opg`), a delayed open (5/15 minutes), and TWAP. Confirm account, order-type and TIF support from sources; an opening-auction order is not a guaranteed fill. Delaying trades changes the strategy's opportunity and must be represented faithfully.

Record the recommendation and fallback, gap/spread filters, participation cap, `source_card_ids`, and `alternatives_compared` (at least two entries). A naked DAY market recommendation for paper_auto needs `naked_market_justification`.

## Stress and monitoring

Document at least three slippage/gap scenarios. These values are illustrative, not universal thresholds:

```json
{
  "scenarios": [
    {"name": "low", "slippage_bps": 5, "open_gap_pct": 0.2},
    {"name": "medium", "slippage_bps": 15, "open_gap_pct": 0.8},
    {"name": "high", "slippage_bps": 35, "open_gap_pct": 2.5}
  ]
}
```

For leveraged ETFs such as TQQQ/SQQQ/UPRO/SPXL, document the largest historical overnight gap, actual gap-open treatment versus `next_bar_open`, a justified gap filter, and path dependence/daily-rebalance decay for multi-day positions. Write `{strategy}-gap-stress.json` and the applicable leveraged-ETF risk note.

Every execution policy needs a TCA plan:

```json
{
  "tca_plan": {
    "reference_prices": ["decision_price", "official_open", "arrival_price"],
    "record_submitted_at": true,
    "record_fill_price": true,
    "record_slippage_vs_reference": true,
    "review_frequency": "weekly"
  }
}
```

Missing required comparison, naked-market justification or leveraged-ETF gap evidence blocks the affected execution step. Paper auction fills and live executability are different evidence; consult [the data guide](../../../docs/data-layer-pitfalls-and-capabilities.zh.md) for recorded account limitations.
