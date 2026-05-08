---
name: strategy-researcher
description: Turn a natural-language trading idea into a tested Open Composer strategy workflow using registered capabilities.
---

1. Start from the user's natural-language idea.
2. Run `uv run oc capability list` and choose registered capabilities that match the idea.
3. Draft a spec with `uv run oc strategy draft --idea "<idea>"` or edit the draft manually.
4. Validate the spec with `uv run oc spec validate <spec>`.
5. Replay event/news/macro fixtures with `oc events fetch` and `oc macro fetch` before context-dependent tests.
6. Run `oc backtest`, `oc scan --with-context`, and, when enabled, `oc review-signal <signal-id>`.
7. Only move to Alpaca Paper after backtest, context, review, and risk checks are satisfactory.
8. Never enable live broker writes for real-money trading.
