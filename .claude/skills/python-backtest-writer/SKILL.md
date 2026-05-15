---
name: python-backtest-writer
description: Implement or update deterministic Python signal, scanner, and backtest behavior for a StrategySpec.
---

1. Treat `StrategySpec` as the source of truth.
2. Preserve bar-close signal confirmation and next-bar-open fill assumptions.
3. Do not introduce lookahead bias.
4. LLM/news/event/macro factors must read point-in-time feature packets by visible_at, never future rows or live model calls.
5. Report benchmark family, data mode, fallback state, trial count, and quality flags when research output can influence promotion.
6. Write signal logs before review or order submission.
7. Run focused tests plus `uv run pytest`.
