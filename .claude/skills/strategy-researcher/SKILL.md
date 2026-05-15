---
name: strategy-researcher
description: Turn a natural-language trading idea into a tested Open Composer strategy workflow using registered capabilities.
---

1. Start from the user's natural-language idea.
2. Run `uv run oc capability list` and choose registered capabilities that match the idea.
3. Draft a spec with `uv run oc strategy draft --idea "<idea>"` or edit the draft manually.
4. Validate the spec with `uv run oc spec validate <spec>`.
5. Convert adjustable ideas into bounded parameter ranges, method variants, factor variants, and a search space before running optimization.
6. Replay event/news/macro fixtures with `oc events fetch` and `oc macro fetch` before context-dependent tests.
7. Run `oc backtest`, `oc strategy parameter-sweep` when parameters are adjustable, and `oc strategy promotion-report` before paper consideration.
8. Require benchmark family, out-of-sample, walk-forward, cost sensitivity, data comparison, and feature packet validation before paper consideration.
9. Label workflow_pass, research_pass, llm_contribution_pass, and paper_ready_pass separately.
10. Only move to Alpaca Paper after backtest, context, review, risk checks, promotion gates, and paper readiness are satisfactory.
11. Never enable live broker writes for real-money trading.
