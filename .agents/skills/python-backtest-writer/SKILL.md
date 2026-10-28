---
name: python-backtest-writer
description: Implement or update deterministic Python signal, scanner, and backtest behavior for a StrategySpec.
---

Implement the validated StrategySpec's signal confirmation and fill clock; preserve bar-close/next-bar-open semantics when specified. Do not introduce lookahead. LLM/news/event/macro factors replay PIT packets by `visible_at`, without future rows or live model calls.

For stock-level work on `data/sip/daily`, apply the price-hygiene requirements in [the data guide](../../../docs/data-layer-pitfalls-and-capabilities.zh.md). When results can influence promotion, report the benchmark family, data mode, fallback state, trial count and quality flags. Write signal logs before review or order submission.

Run focused checks for changed signal, scanner or backtest behavior; shared production changes retain their applicable release checks.
