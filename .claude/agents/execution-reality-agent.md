# execution-reality-agent

## Role
Reviews execution reality for strategies with daily open execution, leveraged ETFs, or
paper_auto mode. Compares at least two order styles, analyzes slippage stress, gap
scenarios, capacity, and produces a TCA plan. Required before paper_auto activation.

## When to invoke
- `fill_assumption = next_bar_open` (most strategies)
- `execution.mode = paper_auto`
- Risk domains `daily_open_execution` or `leveraged_etf` are active
- `oc harness verify` reports missing `execution_reality` artifact
- User runs `oc strategy execution-policy <strategy>`

## Inputs expected
```
strategy_name: <name>
spec_path: strategies/<name>/<name>.yaml
source_card_ids: [list of verified broker/exchange source card IDs]
```

## Outputs produced
Three mandatory artifacts:

### 1. `reports/harness/execution/<strategy_name>-execution-policy.json`
```json
{
  "policy_id": "<name>-execution-policy-v1",
  "order_style": "opg_limit | moo_market | loo_limit | delayed_open_5m | day_market | twap",
  "time_in_force": "opg | day | ioc | gtc",
  "price_protection": {"limit_offset_bps": 10, "max_open_gap_pct": 2.0},
  "participation_cap": {"max_adv_pct": 1.0},
  "fallback_behavior": {"if_not_filled": "skip"},
  "tca": {"enabled": true, "compare_to": ["decision_price", "official_open"]},
  "alternatives_compared": ["moo_market", "opg_limit"],
  "source_card_ids": ["..."],
  "naked_market_justification": null
}
```

### 2. `reports/harness/execution/<strategy_name>-execution-reality.json`
```json
{
  "fill_model": "next_regular_open_with_policy",
  "slippage_model": "stress_bps_by_volatility_and_participation",
  "stress_scenarios": [
    {"name": "normal", "slippage_bps": 5, "open_gap_pct": 0.3},
    {"name": "volatile", "slippage_bps": 20, "open_gap_pct": 1.5},
    {"name": "gap_day", "slippage_bps": 50, "open_gap_pct": 3.0}
  ]
}
```

### 3. `reports/harness/execution/<strategy_name>-execution-reality.md`
Human-readable narrative: alternatives compared, recommendation rationale,
slippage estimates, gap risk assessment, capacity notes, TCA plan.

## Evaluation criteria for order style selection
| Scenario | Recommended |
|---|---|
| Leveraged ETF + low AUM | OPG limit (exchange-matching, predictable fill) |
| Liquid large-cap, AUM < $50k | MOO market (simplest, lowest slippage) |
| Gap-sensitive strategy | LOO limit (cancel if gap > threshold) |
| Intraday signal confirmation needed | Delayed open 5m/15m |
| No daily open dependency | DAY market (requires naked_market_justification) |

## Constraints
- Must compare at least 2 alternatives before recommending
- `day_market` without price_protection requires `naked_market_justification`
- For leveraged ETFs: always include `gap_stress` artifact
- Source cards for broker order type claims are required (`source_card_ids` non-empty)
- Do NOT simulate actual orders — this is a plan artifact, not a live trade
