---
name: pine-exporter
description: Export TradingView Pine Script from an Open Composer StrategySpec.
---

1. Generate Pine v6 under `strategies_pine/generated/`.
2. Preserve entry and exit expressions from the spec.
3. Use `barstate.isconfirmed` for bar-close alert semantics.
4. Include `alertcondition()` for entry and exit.
5. Preserve StrategySpec timeframe and signal semantics; flag unsupported timeframe or expression behavior instead of silently changing it.
6. Write or update a parity note when assumptions change.
