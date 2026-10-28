---
name: pine-exporter
description: Export TradingView Pine Script from an Open Composer StrategySpec.
---

Generate Pine v6 under `strategies_pine/generated/` from the validated spec, preserving entry/exit expressions, timeframe and signal semantics. Use `barstate.isconfirmed` for bar-close alerts and include entry/exit `alertcondition()` calls. Flag unsupported expressions or timeframes instead of silently changing behavior; update the parity note when assumptions change.
