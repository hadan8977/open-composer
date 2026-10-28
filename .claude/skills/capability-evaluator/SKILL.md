---
name: capability-evaluator
description: Evaluate registered market, event, macro, and news capabilities and fixture hygiene before a strategy depends on them.
---

Read [the registry](../../../capabilities/registry.yaml) before selecting a source. Run `uv run --no-sync oc capability test` and inspect `reports/capabilities/evaluation.md` for fixture and provider coverage. Check timeframe support and `strict_behavior`; unregistered sources cannot become strategy dependencies.

Prefer `approved` capabilities for execution; `trial` capabilities provide context with caveats. Record uncertain coverage or reliability in `StrategySpec.notes.open_questions`.

Use [data-capability-reviewer](../data-capability-reviewer/SKILL.md) for strategy-specific compatibility, PIT packets, and paper-readiness evidence. Sample, fixture, cache fallback, and trial/research-only data cannot establish paper readiness.
