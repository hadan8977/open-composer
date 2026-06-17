---
name: data-capability-reviewer
description: >
  Reviews market, event, macro, news, and LLM data capabilities used by a strategy
  before promotion or paper readiness. Reads capabilities/registry.yaml, runs
  capability evaluation, flags sample/fixture/cache-fallback evidence as not paper
  ready, and checks PIT metadata (visible_at, published_at, fetched_at, source,
  input_hash, prompt_hash). Use when a strategy declares LLM/news/event/macro
  capabilities, when adding a new required capability, or when risk domain
  llm_or_news_signal is active.
---

## Inputs

- StrategySpec (capabilities section, factors, llm_review)
- `capabilities/registry.yaml`
- Strategy capability output from `uv run oc spec capabilities <spec> --json`
- Registry fixture output from `uv run oc capability test`

## Mandatory output

`reports/harness/data/{strategy}-capability-review.json`

## Step sequence

1. Read `spec.required_capabilities` and any factor whose `source` is `llm_feature`
   or `feature_packet`. List the capability IDs that the strategy depends on.
2. Run `uv run oc spec capabilities <spec> --json` to capture strategy-specific
   compatibility. Run `uv run oc capability test` when registry fixture hygiene
   or provider coverage is in question.
3. For every capability whose `strict_behavior` is `workflow_only`, mark the
   capability as `sample_evidence` and add a `sample_data_caveat` line to the
   output. Such evidence cannot back paper readiness.
4. For every LLM, news, event, or macro capability, verify the strategy has a
   feature packet schema with `visible_at`, `published_at`, `fetched_at`,
   `source`, `input_hash`, and `prompt_hash` fields.
5. Identify any capability whose registry entry is `unsupported` for the
   strategy's timeframe. These block research_pass.
6. Write `reports/harness/data/{strategy}-capability-review.json`.

## Output schema (json)

```json
{
  "strategy_name": "...",
  "reviewed_at": "YYYY-MM-DD",
  "capabilities": [
    {
      "capability_id": "market.alpaca_bars",
      "kind": "market",
      "status": "ok | partial | blocked | unsupported",
      "strict_behavior": "live | cache_fallback | workflow_only",
      "paper_ready": true,
      "notes": "..."
    }
  ],
  "feature_packet_pit_check": "pass | warning | fail",
  "sample_data_caveats": [],
  "conclusion": "pass | warning | blocked"
}
```

## Blocking rules

- `conclusion: blocked` if any required capability is `unsupported` for the
  strategy timeframe.
- `conclusion: blocked` if any LLM/news/event/macro packet is missing PIT
  metadata fields.
- `conclusion: warning` if all paper-ready evidence is from sample or fixture
  data (a `sample_data_caveat` must be present).

## Rules this skill does NOT cover

- Adding new data providers — that is a separate capability registration task.
- Validating PIT replay during backtest — that is `backtest-forensics`.

## References

- `capabilities/registry.yaml`
- `harness/risk_domains.yaml` — `llm_or_news_signal` domain
- `harness/artifact_contracts.yaml` — capability_review schema (if added)
- AGENTS.md — capability and PIT rules
