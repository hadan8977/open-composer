---
name: strategy-researcher
description: >
  Turn a natural-language trading idea into a tested Open Composer strategy workflow
  using registered capabilities. For full orchestration (harness plan, source research,
  execution reality, forensics), delegate to strategy-research-orchestrator.
---

## Quick path (draft → research)

1. Start from the user's natural-language idea.
2. Run `uv run oc capability list` and choose registered capabilities that match the idea.
3. Draft a spec: `uv run oc strategy draft --idea "<idea>"`.
4. Validate: `uv run oc spec validate <spec>`.
5. Run `uv run oc harness plan <spec>` — read detected risk domains before proceeding.
6. Convert adjustable ideas into bounded parameter ranges before running optimization.
7. Replay event/news/macro fixtures with `oc events fetch` and `oc macro fetch`.
8. Run `oc backtest`, `oc strategy parameter-sweep` (if adjustable), `oc strategy promotion-report`.
9. Label `workflow_pass`, `research_pass`, `llm_contribution_pass`, `paper_ready_pass` separately.
10. For paper consideration: invoke `strategy-research-orchestrator` for full professional workflow.
11. Never enable live broker writes for real-money trading.

## When to escalate to strategy-research-orchestrator

Escalate when any of the following are true:
- Risk domain `daily_open_execution`, `leveraged_etf`, or `paper_auto` is detected.
- Strategy has adjustable parameters (risk domain `parameter_search`).
- Strategy uses LLM/news/event/macro factors (risk domain `llm_or_news_signal`).
- User explicitly requests paper_auto or paper_ready promotion.

## References

- `harness/risk_domains.yaml`
- `harness/skill_manifest.yaml`
