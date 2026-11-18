---
name: data-capability-reviewer
description: >
  Review strategy data dependencies before promotion or paper readiness. Use for
  new required capabilities, LLM/news/event/macro inputs or llm_or_news_signal;
  check compatibility, PIT metadata and non-paper-ready data caveats.
---

# Strategy capability review

Read the StrategySpec's `required_capabilities`, factors using `llm_feature`/`feature_packet`, and [the registry](../../../capabilities/registry.yaml). Run `uv run --no-sync oc spec capabilities <spec> --json` for compatibility. Use [capability-evaluator](../capability-evaluator/SKILL.md) when registry fixtures or provider coverage need checking.

For each required capability, assess timeframe support, `strict_behavior` and actual evidence quality. `workflow_only` is `sample_evidence` and needs a `sample_data_caveat`. Sample, fixture, cache fallback and trial/research-only inputs cannot establish paper readiness. Every LLM/news/event/macro feature-packet schema must include `visible_at`, `published_at`, `fetched_at`, `source`, `input_hash` and `prompt_hash`.

Write `reports/harness/data/{strategy}-capability-review.json`:

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
      "paper_ready": false,
      "notes": "..."
    }
  ],
  "feature_packet_pit_check": "pass | warning | fail",
  "sample_data_caveats": [],
  "conclusion": "pass | warning | blocked"
}
```

Unsupported required timeframes block `research_pass`; missing PIT metadata also blocks the review. Sample-only evidence requires `warning` and caveats, never paper readiness. Registering a new provider is separate work; replay correctness belongs to [backtest-forensics](../backtest-forensics/SKILL.md).

See [capability_review and feature_packet_schema contracts](../../../harness/artifact_contracts.yaml) and [risk domains](../../../harness/risk_domains.yaml).
