# Memory/Storage Options Overlay Optimization

- Scope: paper/research only.
- Underlying: existing equity StrategySpec signals.
- Pricing: Black-Scholes approximation with spread haircut, not historical option quotes.
- Execution: no option orders are submitted by this command.
- Selection: best overlays are research candidates, not activation recommendations.

## Selected

### MU: memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation_options_long_call_otm_liquid_30d

- Overlay: `long_call`
- Return: 0.02%
- Underlying equity return: 7.83%
- Trades: 6
- Score: -0.10
- Decision: research only; did not improve on the equity strategy

### SNDK: memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold_options_debit_spread_otm_30d

- Overlay: `debit_call_spread`
- Return: -2.16%
- Underlying equity return: 4.43%
- Trades: 2
- Score: -12.20
- Decision: reject; option overlay underperformed under current assumptions

### WDC: memory_storage_momentum_15m_wdc_alpaca_optimized_volume_options_long_call_atm_30d

- Overlay: `long_call`
- Return: -3.21%
- Underlying equity return: 2.13%
- Trades: 14
- Score: -13.49
- Decision: reject; option overlay underperformed under current assumptions

### STX: memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation_options_long_call_atm_30d

- Overlay: `long_call`
- Return: 0.00%
- Underlying equity return: 1.68%
- Trades: 0
- Score: -25.00
- Decision: reject; no executable option trades under current budget/liquidity assumptions

## All Candidates

- `memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation_options_long_call_otm_liquid_30d` MU long_call return=0.02% trades=6 underlying=7.83% score=-0.10
- `memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation_options_long_call_otm_30d` MU long_call return=-0.52% trades=3 underlying=7.83% score=-10.58
- `memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold_options_debit_spread_otm_30d` SNDK debit_call_spread return=-2.16% trades=2 underlying=4.43% score=-12.20
- `memory_storage_momentum_15m_wdc_alpaca_optimized_volume_options_long_call_atm_30d` WDC long_call return=-3.21% trades=14 underlying=2.13% score=-13.49
- `memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold_options_debit_spread_30d` SNDK debit_call_spread return=-3.54% trades=4 underlying=4.43% score=-13.62
- `memory_storage_momentum_15m_wdc_alpaca_optimized_volume_options_long_call_otm_liquid_30d` WDC long_call return=-4.42% trades=25 underlying=2.13% score=-14.92
- `memory_storage_momentum_15m_wdc_alpaca_optimized_volume_options_long_call_otm_30d` WDC long_call return=-5.54% trades=21 underlying=2.13% score=-15.96
- `memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation_options_long_call_atm_30d` MU long_call return=0.00% trades=0 underlying=7.83% score=-25.00
- `memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold_options_long_call_atm_30d` SNDK long_call return=0.00% trades=0 underlying=4.43% score=-25.00
- `memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold_options_long_call_otm_30d` SNDK long_call return=0.00% trades=0 underlying=4.43% score=-25.00
- `memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold_options_long_call_otm_liquid_30d` SNDK long_call return=0.00% trades=0 underlying=4.43% score=-25.00
- `memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation_options_long_call_atm_30d` STX long_call return=0.00% trades=0 underlying=1.68% score=-25.00
- `memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation_options_long_call_otm_30d` STX long_call return=0.00% trades=0 underlying=1.68% score=-25.00
- `memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation_options_long_call_otm_liquid_30d` STX long_call return=0.00% trades=0 underlying=1.68% score=-25.00
- `memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation_options_debit_spread_otm_30d` STX debit_call_spread return=-20.11% trades=27 underlying=1.68% score=-30.65
- `memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation_options_debit_spread_30d` STX debit_call_spread return=-20.26% trades=29 underlying=1.68% score=-30.84
- `memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation_options_debit_spread_otm_30d` MU debit_call_spread return=-24.76% trades=38 underlying=7.83% score=-35.52
- `memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation_options_debit_spread_30d` MU debit_call_spread return=-24.98% trades=40 underlying=7.83% score=-35.78
- `memory_storage_momentum_15m_wdc_alpaca_optimized_volume_options_debit_spread_30d` WDC debit_call_spread return=-29.91% trades=44 underlying=2.13% score=-40.79
- `memory_storage_momentum_15m_wdc_alpaca_optimized_volume_options_debit_spread_otm_30d` WDC debit_call_spread return=-30.68% trades=44 underlying=2.13% score=-41.56
