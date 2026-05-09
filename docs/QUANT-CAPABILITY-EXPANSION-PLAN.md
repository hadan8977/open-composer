# Quant Capability Expansion Plan

Date: 2026-05-09

## Summary

Open Composer should not try to force every strategy into TradingView Pine. The reliable architecture is:

```text
StrategySpec source of truth
  -> Python research/backtest runtime as the primary truth engine
  -> TradingView Pine export for a deterministic compatible subset
  -> Alpaca Paper for controlled execution validation
  -> LLM components as structured, replayable research/review inputs
```

The current MVP supports only a narrow single-symbol OHLCV rule set: `open`, `high`, `low`, `close`, `volume`, and `sma/ema/rsi`. It is useful for simple pullback and momentum prototypes, but it does not yet support broad factor research, portfolio construction, ML signals, or LLM-in-the-loop strategy logic.

## Research Base

The machine-readable research notes are stored in `knowledge/quant_capability_knowledge_base.yaml`.

Key conclusions:

- TradingView Pine strategies are useful for Strategy Tester checks, but they run inside a broker emulator and are constrained by script, data-request, intrabar, plotting, and order limits. They are a compatibility target, not the master runtime.
- Alpaca is an execution and market-data API. It can paper trade and place orders, but Open Composer must own strategy logic, audit, reconciliation, and risk controls.
- Mature platforms separate concerns: LEAN/QuantConnect emphasizes streaming backtest/live parity and reality models; NautilusTrader emphasizes event-driven backtest/sandbox/live architecture; vectorbt and QuantRocket Moonshot emphasize vectorized factor research; Qlib and PyBroker show that ML trading requires dataset, model, walk-forward, and prediction-store workflows.
- Closed-source products such as Composer validate the user-facing pattern of structured strategies, filters, weights, backtests, and execution, but Open Composer should keep local files, auditability, and explicit capability reporting as its differentiators.
- Recent LLM strategy-generation research warns that syntactically valid code is not enough; generated strategies must be checked for real trades, semantic alignment, and API-correct execution behavior.

## Strict Multi-Perspective Review

Product review:

- Necessary: capability flags before more strategy features. Without them, users will assume a strategy can be Pine-exported or paper-traded when only a subset is supported.
- Necessary: preserve CLI/files as the first product surface. It keeps the workflow auditable and matches current repo direction.
- Revision: do not claim "supports all strategies." Use "extensible strategy runtime with explicit compatibility classes."

Quant research review:

- Necessary: factor store, point-in-time data, ranking, rebalance, and portfolio targets. These are required for cross-sectional strategies and prevent false confidence from single-symbol tests.
- Necessary: train/test, walk-forward, transaction-cost sensitivity, and parameter stability checks before any strategy is promoted.
- Revision: indicator catalog is useful but insufficient. It must be paired with lagged values, crossovers, rolling windows, and leakage checks.

Backtest engineering review:

- Necessary: two engine modes. Vectorized research is fast for sweeps; event-driven simulation is needed for order lifecycle and paper/live parity.
- Necessary: explicit fill, fee, slippage, corporate-action, timezone, and data-adjustment assumptions in every report.
- Revision: do not replace the simple engine immediately. Keep it as a deterministic smoke-test engine while adding new engines behind adapters.

Execution/risk review:

- Necessary: paper-only automation, active lifecycle gating, idempotent order submission, order reconciliation, kill switch, and position limits.
- Necessary: support target-position execution, not only one-off market orders, before portfolio strategies are allowed to automate.
- Revision: Alpaca Paper support should expand gradually: market orders first, then limit/bracket/stop, then fractional/notional, then reconciliation.

LLM/AI review:

- Necessary: LLM outputs must be structured, timestamped, versioned, and replayable. Otherwise backtests cannot reproduce decisions.
- Necessary: LLM review stays advisory until an explicit, audited `llm_feature` or `llm_gate` primitive exists.
- Revision: do not put raw LLM calls inside backtest loops. Use cached point-in-time artifacts generated before replay.

Security/compliance review:

- Necessary: real-money broker writes remain out of scope until paper workflows have audit logs, explicit approvals, and operational controls.
- Necessary: all docs and reports must label outputs as research, not financial advice.
- Revision: "best recent strategies" must be treated as research examples only; no return claim should become a product promise.

## Formal Roadmap

Phase 1: Capability Classification

- Add a strategy capability report that classifies each spec for Python MVP backtest, TradingView Pine strategy export, Alpaca Paper execution, and LLM-assisted workflow support.
- Report unsupported reasons such as unsupported expressions, non-replayable LLM/event dependencies, lifecycle blockers, or missing Alpaca execution settings.
- Use this report as a required checklist before Pine export, backtest promotion, or paper automation.

Phase 2: Indicator and Expression Expansion

- Add a typed feature catalog with built-in primitives for lag, returns, rolling stats, crossover/crossunder, ATR, Bollinger Bands, MACD, ADX, VWAP, Donchian, volatility, beta, and z-score.
- Prefer library-backed implementations where stable, with local wrappers that define exact semantics and validation.
- Add Pine translation only for primitives with clean Pine equivalents; mark the rest as Python-only.

Phase 3: StrategySpec v2 Graph

- Extend StrategySpec from simple entry/exit strings into a typed graph:
  `universe -> data -> features -> filters -> ranking -> portfolio target -> order policy -> risk -> review`.
- Keep existing v1 specs valid through a migration layer.
- Add compatibility metadata directly to generated reports.

Phase 4: Data and Factor Store

- Add point-in-time stores for OHLCV, adjusted prices, corporate actions, fundamentals, earnings, SEC filings, macro, news, and model predictions.
- Require every non-price capability to declare provider, timestamp semantics, delay, coverage, and replay fixture.
- Add leakage tests for features that depend on future revisions or publication delays.

Phase 5: Research Engines

- Add a vectorized research engine for parameter sweeps, factor ranking, rebalance strategies, and portfolio-level metrics.
- Add an event-driven engine for order lifecycle, fills, slippage, commissions, partial fills, cancellations, and execution parity.
- Keep reports comparable across engines by using shared run metadata and acceptance metrics.

Phase 6: Portfolio and Risk Layer

- Add target weights, top-N selection, equal/inverse-vol/score weighting, rebalance schedules, exposure caps, max drawdown guardrails, and volatility targeting.
- Add multi-strategy portfolio reports and correlation/drift checks.
- Add pre-trade and post-trade risk checks before any paper order is sent.

Phase 7: LLM+Quant Runtime

- Add prompt/version registry, structured output schemas, replay cache, confidence thresholds, and deterministic fallback behavior.
- Allow LLM outputs to become point-in-time features only after they are stored and reproducible.
- Add review gates that can block paper orders, but keep the final execution logic deterministic and auditable.

Phase 8: Alpaca Paper Execution Maturity

- Expand from simple market orders to target-position reconciliation, bracket/stop/limit order policies, fractional/notional sizing, and order status sync.
- Add kill switch, max daily order count, max daily loss, symbol denylist, and stale-signal checks.
- Keep real-money broker writes out of scope until explicitly re-scoped.

## Second Review of the Formal Plan

- The plan is necessary because current support is narrower than user expectations for "quant strategy."
- The sequencing is correct: compatibility reporting must precede feature expansion, because it prevents silent overclaiming.
- The plan avoids the main trap: making Pine export the center of the product. Pine remains useful, but Python remains the authority.
- The plan avoids the second trap: adding many indicators before data and replay semantics. Indicators expand Phase 2, but advanced factors require Phase 4.
- The plan avoids the LLM trap: LLM decisions are not allowed to mutate execution semantics unless cached as structured features.
- The biggest risk is scope creep. The mitigation is to ship each phase behind CLI commands and explicit reports, with tests before moving to the next phase.

## Immediate Execution Slice

Implement Phase 1 now:

- Add `oc spec capabilities <spec>` to print a compatibility table.
- Classify `python_mvp_backtest`, `tradingview_pine_strategy`, `alpaca_paper_execution`, and `llm_quant_workflow`.
- Add tests for a pure sample strategy and an LLM/context strategy.
- Use the command before future Pine export, promotion, or paper execution work.
