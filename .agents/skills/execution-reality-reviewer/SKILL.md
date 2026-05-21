---
name: execution-reality-reviewer
description: >
  Reviews execution reality for strategies with daily open execution, leveraged ETFs,
  or paper_auto mode. Compares at least two order styles, analyzes slippage stress,
  gap scenarios, capacity, and produces a TCA plan. Required before paper_auto
  activation for any daily open strategy.
  Use when fill_assumption=next_bar_open, execution.mode=paper_auto, or risk domains
  daily_open_execution or leveraged_etf are active.
---

## Inputs

- StrategySpec (execution section, universe, timeframe)
- Source cards from `source-researcher` for broker/exchange order type support
- Harness plan showing active risk domains

## Mandatory outputs

- `reports/harness/execution/{strategy}-execution-policy.json`
- `reports/harness/execution/{strategy}-execution-reality.json`
- `reports/harness/execution/{strategy}-execution-reality.md` (human-readable summary)

## Execution policy comparison

Compare at minimum two of the following order styles:

| Style | Description | When to prefer |
|---|---|---|
| DAY market | Immediate fill at any open price | Highest liquidity, no price protection |
| MOO / OPG limit | Market-on-open or limit at opening auction | Better price discovery, exchange-guaranteed fill |
| LOO / OPG limit | Limit-on-open at auction | Price-protected; may miss fill if price gaps |
| Delayed open (5m/15m) | Wait for opening volatility to settle | Reduces gap risk; misses opening momentum |
| TWAP | Time-weighted average over a window | Low participation cap for large orders |

## Slippage stress scenarios

Document at least three scenarios:

```json
{
  "scenarios": [
    {"name": "low",    "slippage_bps": 5,  "open_gap_pct": 0.2},
    {"name": "medium", "slippage_bps": 15, "open_gap_pct": 0.8},
    {"name": "high",   "slippage_bps": 35, "open_gap_pct": 2.5}
  ]
}
```

## Gap stress (leveraged ETF)

For strategies holding TQQQ, SQQQ, UPRO, SPXL, or similar:
- Document maximum historical overnight gap for the instrument.
- Assess fill model's handling of gap-open (next_bar_open assumption vs. actual open).
- Recommend gap filter: skip trade if open gap exceeds threshold (e.g. 2.5%).
- Document path-dependency and daily rebalance decay impact on multi-day positions.

## TCA plan

Every execution_policy must include a TCA plan:

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

## Step sequence

1. Read spec execution section and active risk domains.
2. Read broker source cards for supported order types and TIF values.
3. Draft at least two execution policy alternatives.
4. Score each alternative on: price protection, fill certainty, slippage risk, complexity.
5. Select the recommended policy with written justification.
6. Run slippage stress and gap stress for the selected policy.
7. Write execution_policy.json, execution-reality.json, execution-reality.md.
8. If recommended policy is naked DAY market order, write a justification paragraph in execution_policy.json under `naked_market_justification`.

## Blocking rules

- Cannot use naked DAY market order for paper_auto without `naked_market_justification` field present.
- Must compare at least two methods; `alternatives_compared` list must have >= 2 entries.
- Leveraged ETF strategies must have `gap_stress_report` artifact.

## References

- `harness/artifact_contracts.yaml` — execution_policy, execution_reality_report schemas
- `harness/risk_domains.yaml` — daily_open_execution, leveraged_etf blocking rules
- `harness/source_cards/{strategy}.jsonl` — broker/exchange source cards
