---
name: capability-evaluator
description: Evaluate market, event, macro, and news data capabilities before allowing a strategy to depend on them.
---

1. Read `capabilities/registry.yaml` before choosing any data source.
2. Use this skill for global registry and fixture hygiene. For strategy-specific
   required capabilities, PIT metadata, or paper-readiness review, use
   `data-capability-reviewer`.
3. Run `uv run oc capability test` and inspect `reports/capabilities/evaluation.md`.
4. Prefer `approved` capabilities for strategy execution; use `trial` capabilities only as context with caveats.
5. Do not let a strategy reference unregistered capabilities.
6. Record source caveats in `StrategySpec.notes.open_questions` when coverage or reliability is uncertain.
7. Check provider timeframe support and strict behavior before marking a capability paper-ready.
8. Treat sample, fixture, cache fallback, and trial/research-only data as workflow or research evidence, not paper-ready market evidence.
