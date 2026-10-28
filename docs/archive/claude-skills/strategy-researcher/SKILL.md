---
name: strategy-researcher
description: >
  Turn a natural-language trading idea into a tested strategy workflow using
  registered capabilities. Use strategy-research-orchestrator for optimization,
  paper readiness, source research, execution reality and forensics.
---

# Draft-to-research quick path

Choose registered inputs with `uv run oc capability list`, draft with `uv run oc strategy draft --idea "<idea>"`, and run `uv run oc spec validate <spec>` followed by `uv run oc harness plan <spec>`.

Use [strategy-research-orchestrator](../strategy-research-orchestrator/SKILL.md) when the plan detects `parameter_search`, `daily_open_execution`, `leveraged_etf`, `paper_auto` or `llm_or_news_signal`, or when the user requests promotion/paper readiness. This routes to the applicable specialist workflow, not a main-agent approval hop.

For a simple non-adjustable smoke check, `uv run oc backtest <spec>` and `uv run oc strategy promotion-report <spec>` provide workflow evidence only. Applicable economic admission still precedes a research backtest; a quick path does not bypass native gates. Use [owner-reporting definitions](../../../docs/owner-reporting.zh.md) to label the result and its limits.
