---
name: strategy-designer
description: Create or revise Open Composer StrategySpec YAML files from natural-language trading ideas.
---

1. Write draft specs under `strategy_specs/drafts/`.
2. Capture universe, timeframe, entry, exit, risk, execution, data source, broker, LLM review, and assumptions.
3. Use conservative defaults: `manual_signal`, bar-close signals, next-bar-open fills, long-only, no leverage.
4. Add `notes.research_design` with method variants, factor variants, parameter ranges, frequency assumptions, candidate cap, and selection objective.
5. Include benchmark family assumptions: same-symbol buy-and-hold, equal-weight universe, market proxy, sector/theme proxy, cash proxy, and ex-post best symbol when available.
6. Put unresolved choices in `notes.open_questions`.
7. Run `uv run oc spec validate <spec>` before finishing.
