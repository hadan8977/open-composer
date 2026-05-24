# Strategy Project Context: NASDAQ long-short event router

Open Composer is a personal AI strategy workbench. StrategySpec is the source of truth for strategy behavior.
Use repo Harness, reports, capabilities, and paper readiness gates. Do not treat sample data or worker self-report as paper-ready evidence.

## Project
- project_id: `nasdaq-long-short-event-router`
- state: `blocked`
- thesis: Build a NASDAQ long-short strategy that detects market regime and daily state, scans stocks for long or short candidates, uses materialized event-risk LLM features, and iterates until paper-ready.
- current_spec_path: `strategy_specs/drafts/nasdaq_long_short_event_router_15m_sweep_001.yaml`
- latest_run_path: `projects/nasdaq-long-short-event-router/runs/round-005.yaml`
- next_action: `Keep widening the route search and collect independent LLM/options evidence before paper_auto.`

## Evidence Tracks
- Factor Quality: `warning`; artifact=`reports/research/nasdaq_long_short_event_router_15m_sweep_001-promotion.json`; blockers=`oos_no_annualized_alpha_vs_benchmark_buy_hold`, `does_not_beat_ex_post_best_symbol`; summary=Factor Lab is PIT-complete and now only weak-rank-IC warnings remain, but promotion still fails the buy-hold and ex-post best-symbol checks.
- Execution Reality: `ok`; artifact=`reports/execution/nasdaq_long_short_event_router_15m_sweep_001-target-weights.json`; blockers=none; summary=Observation-only adaptive target weights and parity checks pass for the selected route.
- Alt/LLM Evidence: `warning`; artifact=`reports/research/nasdaq_long_short_event_router_15m_sweep_001-llm-intraday-selection.json`; blockers=none; summary=Event-risk packets are PIT-complete and the LLM selection report now exists, but the selection fell back to a non-independent choice so LLM contribution is still not positive.

## Iteration
- current_round: 5
- max_rounds: 8
- mode: `auto_continue_until_stop`
- stop_conditions: target_met, max_rounds_reached, no_material_improvement, overfit_risk_high, data_or_execution_blocked, worker_failed

## Artifact State
- artifact_state_path: `projects/nasdaq-long-short-event-router/artifact-state.json`
- last_successful_step: `promotion`
- blocked_items: promotion_warning:oos_no_annualized_alpha_vs_benchmark_buy_hold, promotion_warning:does_not_beat_ex_post_best_symbol, factor_lab_warning:weak_rank_ic, llm_contribution_warning:external_llm_api_not_called_or_not_used, alt_data_warning:cache_data_used, paper_ready_blocked:lifecycle_not_active, paper_ready_blocked:execution_not_paper_auto, paper_ready_blocked:broker_not_alpaca_paper
- warning_items: promotion:adaptive_router_research, promotion:out_of_sample, promotion:factor_lab, promotion:alternative_data, promotion:llm_contribution, router:execution_observation_only
- next_minimal_actions: widen the route search and collect independent LLM/options evidence before paper_auto
- do_not_repeat: none
- evidence.factor_quality: `warning`
- evidence.execution_reality: `ok`
- evidence.alt_llm_evidence: `warning`

## Latest Queue Commands
- queue: `empty`

## Latest Trace
- trace: `empty`

## Latest Run Ledger
- latest_run: `n/a`

## Current Task
Queued at: 2026-05-23T19:25:27.149269+00:00
Iteration intent: resolve_blockers
Rounds requested: 1

Agent operating principle:
Use the active Codex/Claude Code session context when available. The product queue is a durable command channel, not a rigid step planner.
Choose the exact tool order yourself, but write durable artifacts, trace entries, and Project run summaries for any material result.

User command:
Use the current candidate spec to keep iterating the NASDAQ long-short router, refresh research and promotion evidence, and keep paper_auto and short orders disabled until broker and short-readiness evidence pass.

Current blockers:
- promotion_warning:oos_no_annualized_alpha_vs_benchmark_buy_hold
- promotion_warning:does_not_beat_ex_post_best_symbol
- factor_lab_warning:weak_rank_ic
- llm_contribution_warning:external_llm_api_not_called_or_not_used
- alt_data_warning:cache_data_used

Next minimal actions:
- widen the route search and collect independent LLM/options evidence before paper_auto
