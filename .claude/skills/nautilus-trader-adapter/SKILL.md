---
name: nautilus-trader-adapter
description: Implement or update NautilusTrader-backed execution, backtest, and custom data adapters for Open Composer StrategySpecs.
---

1. Treat `StrategySpec` as the source of truth.
2. Check `oc spec capabilities <spec>` before mapping a strategy to NautilusTrader.
3. Keep the in-repo Python engine as the deterministic reference for the supported subset.
4. Map replayable factors and `llm_feature` packets to timestamped custom data; do not call LLMs inside the backend loop.
5. Preserve `version_id`, `spec_hash`, and audit metadata across backtest and paper flows.
6. Preserve data manifest, feature packet, backend plan, signal, paper order, and audit links for paper parity evidence.
7. Fail fast when a timeframe is not supported by the selected provider or Nautilus mapping.
8. Run backend-specific tests plus `uv run pytest`.
9. Keep paper gating intact; real-money writes remain out of scope.
