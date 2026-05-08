---
name: python-backtest-writer
description: Implement or update deterministic Python signal, scanner, and backtest behavior for a StrategySpec.
---

1. Treat `StrategySpec` as the source of truth.
2. Preserve bar-close signal confirmation and next-bar-open fill assumptions.
3. Do not introduce lookahead bias.
4. Write signal logs before review or order submission.
5. Run focused tests plus `uv run pytest`.
