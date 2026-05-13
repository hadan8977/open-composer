# Dashboard D0 Review

- Generated at: `2026-05-12T18:46:57.835302+00:00`
- Source root: `/root/codex-test/open-composer`

## Current Capability Baseline

- Strategies indexed: `3`
- Versions indexed: `3`
- Runs indexed: `1`
- Signals indexed: `0`
- Reviews indexed: `0`
- Context packets indexed: `0`
- Journal entries indexed: `0`
- Data comparisons indexed: `0`
- Feature packets indexed: `0`
- Workflow reports indexed: `0`
- Readiness status: `warning` ready=`True`
- Deployment status: `warning` ready=`True`

## Backend Snapshot

- Strategy backends: `{'python_reference': 3}`
- Backend readiness: `{'partial': 2, 'supported': 1}`
- Paper kill switch: `off`
- Paper order status counts: `{'warning': 1}`
- Paper account equity: `n/a`
- Paper account snapshot: `n/a`
- Paper positions: `0`
- Paper positions snapshot: `n/a`
- Paper unrealized PnL: `$0.00`
- Paper reconciliation: `warning` issues=`1`
- Paper alerts: `warning` alerts=`2`

## What The Dashboard Can Trust Now

- Strategy catalog can be rebuilt from repo files and report artifacts.
- Capability badges can come from `StrategySpec` and `assess_strategy_capabilities` instead of mock data.
- Version views can show current file snapshots and file provenance.
- Signal, review, context, and journal pages can be populated from existing artifacts.
- Paper status and kill switch events can be read from local paper artifacts.
- Data comparison reports can show latest low-cost source coverage and caveats.
- Feature packet logs can show replay inputs for llm_feature and feature_packet factors.
- Backtest rows can show `data_sanity` evidence levels and warning counts, so sample/fallback/short-window results are not presented as benchmark evidence.
- A static read-only Dashboard can now be generated at `reports/dashboard/index.html` and `reports/dashboard/strategies/*.html` from this catalog.

## What The Dashboard Should Not Pretend Yet

- Historical version lineage is now partially available from version manifests, but a full immutable event log is still not present.
- Remote paper write actions must stay disabled until the Dashboard calls the existing command gate and confirmation flow.
- LLM pages must stay advisory until their prompts, model refs, and replay caches are wired through the backend.
- Warning-level backtests must not be promoted from Dashboard metrics alone.

## Strategy Mix

- Active strategies: `0`
- Active paper_auto strategies: `0`
- Paper kill switch: `off`
- Open paper orders: `0`
- Paper positions: `0`
- Paper reconciliation issues: `1`
- Paper alerts: `2`
- Pure quant strategies: `2`
- Quant + review strategies: `0`
- Quant + scan strategies: `1`
- Quant + orchestrator strategies: `0`

## Review Verdict

- The current Figma dashboard can be turned into a real control plane, but only after it reads from this catalog instead of hard-coded mock arrays.
- The first production version should be read-only, capability-aware, and source-linked.
- Paper kill switch/status can be displayed now; Dashboard write controls still need a command-service wrapper and explicit confirmation.

## Recommended Next Steps

1. Keep the static read-only HTML Dashboard as the first real product surface for Dashboard review, including per-strategy detail pages.
2. If the Figma frontend is restored, wire it to `reports/dashboard/catalog.json` instead of mock arrays.
3. Render the read-only pages first: overview, strategy library, strategy detail, versions, context, review, and audit.
4. Add write buttons only after command service, confirmation flow, and audit records exist.

## Active Strategy Snapshot

- No active strategies were indexed.

## Paper Auto Snapshot

- No active paper_auto strategies were indexed.
