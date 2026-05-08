# Memory/Storage Options Expansion Analysis

## User Question

Can the current memory/storage equity momentum strategies be converted into options strategies to amplify returns?

## Current Product State

The current strategies are equity strategies, not options strategies.

Evidence:

- StrategySpecs use `data.source=alpaca` with stock OHLCV bars.
- Signals are generated from underlying stock price/volume indicators.
- Paper execution submits equity market orders through Alpaca.
- Current backtests do not model option chain selection, bid/ask spread, Greeks, implied volatility, expiration, assignment, exercise, or options buying power.

## Backtest Window

The latest universe optimization used Alpaca IEX 15m bars.

Observed bar window:

- `MU`: 648 bars, 2026-04-08 18:30 UTC to 2026-05-08 18:15 UTC.
- `SNDK`: 618 bars, 2026-04-08 18:30 UTC to 2026-05-08 18:15 UTC.
- `WDC`: 610 bars, 2026-04-08 18:30 UTC to 2026-05-08 18:15 UTC.
- `STX`: 577 bars, 2026-04-08 18:30 UTC to 2026-05-08 18:15 UTC.

This is roughly a 30-calendar-day lookback, using intraday 15m bars. Return is period account-level return, not annualized.

## Product Judgment

Options can amplify directional returns, but simply replacing equity buys with calls is not a valid optimization. It changes the strategy from price momentum to a leveraged derivative strategy exposed to:

- theta decay;
- implied-volatility expansion/compression;
- bid/ask spread and contract liquidity;
- strike and expiration selection;
- assignment/exercise and expiration handling;
- options approval level and buying-power rules;
- much higher sensitivity to stale signals.

The first options MVP should be paper-only and defined-risk.

## Recommended Options MVP

Start with two overlays, both triggered by the existing underlying equity signal:

1. Long call overlay
   - Entry: underlying strategy emits `entry`.
   - Contract: 14-45 DTE call, target delta 0.35-0.55 if Greeks are available; otherwise nearest 2-5% OTM liquid call.
   - Liquidity filters: minimum volume/open interest, max bid/ask spread percentage.
   - Risk: max premium per trade, max premium per strategy/day.
   - Exit: underlying exit signal, option stop loss, option take profit, or DTE floor.

2. Debit call spread overlay
   - Entry: underlying strategy emits `entry`.
   - Buy near target delta call, sell higher strike call.
   - Defined risk and lower premium than long calls.
   - Exit: underlying exit, spread P/L target, DTE floor.

Do not implement naked short options, cash-secured puts, covered calls, calendars, straddles, or iron condors in the first pass.

## Implemented Research Pass

The product now has a paper/research-only options overlay optimizer:

```bash
uv run oc options optimize \
  strategy_specs/drafts/memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation.yaml \
  strategy_specs/drafts/memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold.yaml \
  strategy_specs/drafts/memory_storage_momentum_15m_wdc_alpaca_optimized_volume.yaml \
  strategy_specs/drafts/memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation.yaml \
  --max-premium-weight 0.03
```

It creates `OptionOverlaySpec` files in `strategy_specs/options/`, runs long-call and debit-call-spread candidates, and writes reports under `reports/options/` plus the summary at `reports/research/memory_storage_options_overlay_optimization.md`.

Latest result using the same approximate 30-calendar-day Alpaca IEX 15m window:

- `MU`: best option overlay `long_call_otm_liquid_30d`, return `0.02%`, 6 option trades, versus `7.83%` underlying equity strategy return.
- `SNDK`: best option overlay `debit_spread_otm_30d`, return `-2.16%`, 2 option trades, versus `4.43%` underlying equity strategy return.
- `WDC`: best option overlay `long_call_atm_30d`, return `-3.21%`, 14 option trades, versus `2.13%` underlying equity strategy return.
- `STX`: best option overlay `long_call_atm_30d`, return `0.00%`, no executable option trades, versus `1.68%` underlying equity strategy return.

Conclusion: the first direct conversion from 15m stock momentum entries into 30D call/spread overlays did not improve the strategy. Under the current assumptions, options amplify transaction cost, theta, and churn more than they amplify the edge. These outputs should remain research artifacts, not active paper strategies.

The next useful optimization is not "use more premium." A 10% premium budget test was materially worse. The next iteration should first reduce signal churn: require stronger trend persistence, minimum expected holding time, wider exits, and real option-chain liquidity filters before considering paper option orders.

## Horizon Research Pass

I also compared scan frequency versus hold duration on the same memory/storage universe:

- 5m candidates produced more signals and trades, but the scoring collapsed because churn exploded.
- 15m lower-turnover and 1h trend-hold candidates dominated the selected set.
- Best equity result in this pass was `MU` on `1h` with `7.64%` return and only `6` closed trades.
- `SNDK` on `15m` and `STX` on `1h` also stayed positive.
- 5m fast-scan variants were not the right direction for this product if the goal is eventual options execution.

Follow-on option overlay with a minimum executable-trades threshold of `3` did not rescue the thesis:

- `SNDK` was the top robust option candidate, but still returned `-2.53%`.
- `MU`, `WDC`, and `STX` all remained negative under the same assumptions.
- The earlier one-trade positive `WDC` long-call result does not look robust enough to drive product decisions.

Practical conclusion: the strategy should move toward lower-frequency, stronger trend confirmation, and longer expected holding periods. That is more aligned with future Alpaca Paper options use than simply scanning faster.

## Required Product Work

Add models:

- `OptionStrategySpec`
- `OptionContractSelection`
- `OptionSignal`
- `OptionBacktestRun`
- `OptionOrderRecord`

Add data adapters:

- Alpaca option contracts/chain lookup.
- Alpaca option bars/quotes.
- Optional contract liquidity snapshots.

Add backtest engine:

- Underlying signal remains deterministic.
- Option fill should use contract bid/ask or midpoint with spread/slippage assumptions.
- Backtest must include theta/IV effects only if using actual option bars/quotes; otherwise label simulation as approximate and not trade-ready.

Add execution:

- Paper-only option order submission.
- Whole-number option quantities only.
- No notional/fractional options.
- Validate Alpaca account option level before placing paper orders.
- Use idempotent client order IDs linked to underlying signal and contract symbol.

## Product Prompt For Next Codex Iteration

Analyze and implement a paper-only options overlay for the memory/storage equity momentum strategy.

Use existing underlying signals for `MU`, `SNDK`, `WDC`, and `STX`, but do not directly trade options until contract selection, liquidity checks, and option backtesting are implemented.

Start with long-call and debit-call-spread overlays only. Use Alpaca option contracts and market data if available. Build a deterministic option backtest that records DTE, strike, contract symbol, bid/ask or midpoint fill assumption, spread/slippage, premium at risk, max loss, and exit reason.

Keep all real-money execution disabled. Paper execution must require explicit `--allow-paper-orders` and an options-specific `--allow-options-paper` flag.

Acceptance criteria:

- Equity strategy behavior remains unchanged.
- Option overlay can run in research mode without submitting orders.
- Missing option data or insufficient liquidity causes a skipped signal, not a forced trade.
- Reports clearly compare equity return versus option overlay return and drawdown.
- Tests cover contract selection, liquidity rejection, backtest fill assumptions, and idempotent paper order submission.
