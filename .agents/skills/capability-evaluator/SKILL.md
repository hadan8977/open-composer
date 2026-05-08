---
name: capability-evaluator
description: Evaluate market, event, macro, and news data capabilities before allowing a strategy to depend on them.
---

1. Read `capabilities/registry.yaml` before choosing any data source.
2. Run `uv run oc capability test` and inspect `reports/capabilities/evaluation.md`.
3. Prefer `approved` capabilities for strategy execution; use `trial` capabilities only as context with caveats.
4. Do not let a strategy reference unregistered capabilities.
5. Record source caveats in `StrategySpec.notes.open_questions` when coverage or reliability is uncertain.
