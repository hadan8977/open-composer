---
name: nautilus-trader-adapter
description: Implement or update NautilusTrader execution, backtest, and custom-data adapters for Open Composer StrategySpecs.
---

Check `uv run --no-sync oc spec capabilities <spec>` before mapping the validated StrategySpec. Keep the in-repo Python engine as the deterministic reference for the supported subset, and fail explicitly on unsupported provider timeframes or Nautilus mappings.

Map replayable factors and `llm_feature` packets to timestamped custom data; never call LLMs inside the backend loop. Preserve `version_id`, `spec_hash`, and links among the data manifest, feature packet, backend plan, signal, paper order and audit metadata across backtest and paper flows.

Run checks appropriate to the affected adapter and parity behavior. Paper gating and the live-code isolation rules in [AGENTS.md](../../../AGENTS.md) remain binding.
