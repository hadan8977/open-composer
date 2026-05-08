# Memory/Storage Universe Expansion

## User Intent

Continue optimizing the memory/storage intraday momentum strategy by looking across more related stocks, scanning the universe, and forming a more useful strategy set.

## Research Notes

- The memory/storage theme remains tied to AI data-center demand, HBM/DRAM tightness, HDD capacity constraints, and NAND/datacenter storage demand.
- Directly related tradable symbols for this MVP pass: `MU`, `WDC`, `STX`, `SNDK`.
- Use the same long-only 15m momentum family, but optimize per symbol instead of forcing one set of parameters on every stock.
- Penalize excessive trades/signals because high churn is less useful for personal paper/live execution even when sample returns look better.

## Product Prompt

Take the existing memory/storage intraday momentum strategy and expand it into a per-symbol universe strategy set.

Use Alpaca IEX 15m bars for `MU,WDC,STX,SNDK`. For each symbol, test the same candidate families:

- fast EMA/RSI/volume continuation;
- balanced EMA trend continuation;
- volume surge continuation;
- opening continuation with slower EMA exit;
- trend-hold continuation;
- fast re-entry.

Select the best candidate per symbol using period account-level return, signal count, closed trades, and a turnover penalty. Write one StrategySpec per symbol and a universe optimization report. Do not enable Alpaca Paper orders until a later explicit activation step.

## Latest Run

Report: `reports/research/memory_storage_momentum_15m-universe-optimization.md`

Selected:

- `MU`: `memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation`
- `SNDK`: `memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold`
- `WDC`: `memory_storage_momentum_15m_wdc_alpaca_optimized_volume`
- `STX`: `memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation`

Latest scan:

- `MU`: no latest-bar signal.
- `SNDK`: no latest-bar signal.
- `WDC`: latest-bar exit signal.
- `STX`: latest-bar exit signal.
