---
name: strategy-designer
description: Create or revise Open Composer StrategySpec YAML files from natural-language trading ideas.
---

1. Write draft specs under `strategy_specs/drafts/`.
2. Capture universe, timeframe, entry, exit, risk, execution, data source, broker, LLM review, and assumptions.
3. Use conservative defaults: `manual_signal`, bar-close signals, next-bar-open fills, long-only, no leverage.
4. Put unresolved choices in `notes.open_questions`.
5. Run `uv run oc spec validate <spec>` before finishing.
