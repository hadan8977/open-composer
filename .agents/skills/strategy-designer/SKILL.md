---
name: strategy-designer
description: Create or revise Open Composer StrategySpec YAML files from natural-language trading ideas.
---

Write drafts under `strategy_specs/drafts/`. Capture universe, timeframe, entry/exit, risk, execution, data source, broker, LLM review and assumptions. For choices the idea leaves open, conservative defaults are `manual_signal`, bar-close confirmation, next-bar-open fills, long-only and no leverage. Explicit timing, direction and leverage requirements take precedence; record unresolved choices in `notes.open_questions`.

Add `notes.research_design` with method/factor variants, parameter ranges, frequency assumptions, candidate cap and selection objective. Declare benchmark assumptions: same-symbol buy-and-hold, equal-weight universe, market, sector/theme and cash proxies, plus ex-post best symbol where available. Validate with `uv run --no-sync oc spec validate <spec>` before strategy code or Pine generation.
