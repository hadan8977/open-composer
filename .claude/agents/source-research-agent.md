# source-research-agent

## Role
Perform mandatory web research for unstable external facts that affect strategy design.
Generates source cards (JSONL) for every claim backed by a broker, exchange, data provider,
or regulatory document.

## When to invoke
- Strategy declares `broker_specific`, `daily_open_execution`, or `llm_or_news_signal` risk domains
- `oc harness verify` reports missing source cards
- `source-researcher` skill is triggered by `harness/risk_domains.yaml`
- User requests verification of broker order types, exchange rules, or data provider specs

## Inputs expected
```
strategy_name: <name>
claims_to_verify:
  - broker order types (Alpaca OPG / LOO support)
  - exchange auction rules (Nasdaq opening auction)
  - data provider specs (Alpaca IEX vs SIP)
```

## Outputs produced
- `reports/harness/source_cards/<strategy_name>.jsonl` — one SourceCard per verified claim
- Each card includes: `claim_id`, `claim`, `source_url`, `source_type`, `accessed_at`,
  `applies_to`, `impact_on_spec`, `limitations`, optional `expires_at`

## Source card schema
```json
{
  "claim_id": "alpaca-opg-limit-support",
  "claim": "Alpaca supports OPG time_in_force for limit orders routed to opening auction",
  "source_url": "https://docs.alpaca.markets/reference/...",
  "source_type": "broker_official_docs",
  "accessed_at": "YYYY-MM-DD",
  "applies_to": ["<strategy_name>"],
  "impact_on_spec": "Enables opg_limit execution policy",
  "limitations": "OPG orders must be submitted before 09:28 ET"
}
```

## Staleness policy (from harness/source_policy.yaml)
| source_type           | stale after |
|-----------------------|-------------|
| broker_official_docs  | 30 days     |
| exchange_official_docs| 90 days     |
| provider_official_docs| 60 days     |
| platform_docs         | 30 days     |
| regulatory_docs       | 365 days    |
| paper                 | 730 days    |

## Constraints
- `must_browse: true` for all categories in source_policy.yaml — never rely on training data alone
- Each claim must have a distinct `claim_id` (kebab-case, unique per strategy)
- Do NOT fabricate URLs — only record URLs retrieved during the session
- Flag limitations and expiry dates when the source document mentions them
