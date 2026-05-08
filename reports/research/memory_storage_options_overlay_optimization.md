# Memory/Storage Options Overlay Optimization

- Scope: paper/research only.
- Underlying: existing equity StrategySpec signals.
- Pricing: Black-Scholes approximation with spread haircut, not historical option quotes.
- Execution: no option orders are submitted by this command.
- Selection: best overlays are research candidates, not activation recommendations.
- Minimum executable trades threshold: 3
- Max premium weight: 0.03

## Selected

### SNDK: memory_storage_momentum_15m_sndk_alpaca_15m_trend_hold_options_debit_spread_30d

- Overlay: `debit_call_spread`
- Return: -2.53%
- Underlying equity return: 3.21%
- Trades: 3
- Score: -12.59
- Decision: reject; option overlay underperformed under current assumptions

### MU: memory_storage_momentum_15m_mu_alpaca_1h_trend_hold_options_debit_spread_otm_30d

- Overlay: `debit_call_spread`
- Return: -2.80%
- Underlying equity return: 7.64%
- Trades: 6
- Score: -12.92
- Decision: reject; option overlay underperformed under current assumptions

### WDC: memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold_options_debit_spread_otm_30d

- Overlay: `debit_call_spread`
- Return: -3.26%
- Underlying equity return: 0.77%
- Trades: 6
- Score: -13.38
- Decision: reject; option overlay underperformed under current assumptions

### STX: memory_storage_momentum_15m_stx_alpaca_1h_trend_hold_options_debit_spread_30d

- Overlay: `debit_call_spread`
- Return: -4.57%
- Underlying equity return: 2.59%
- Trades: 7
- Score: -14.71
- Decision: reject; option overlay underperformed under current assumptions

## All Candidates

- `memory_storage_momentum_15m_sndk_alpaca_15m_trend_hold_options_debit_spread_30d` SNDK debit_call_spread return=-2.53% trades=3 underlying=3.21% score=-12.59
- `memory_storage_momentum_15m_mu_alpaca_1h_trend_hold_options_debit_spread_otm_30d` MU debit_call_spread return=-2.80% trades=6 underlying=7.64% score=-12.92
- `memory_storage_momentum_15m_mu_alpaca_1h_trend_hold_options_debit_spread_30d` MU debit_call_spread return=-2.80% trades=6 underlying=7.64% score=-12.92
- `memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold_options_debit_spread_otm_30d` WDC debit_call_spread return=-3.26% trades=6 underlying=0.77% score=-13.38
- `memory_storage_momentum_15m_stx_alpaca_1h_trend_hold_options_debit_spread_30d` STX debit_call_spread return=-4.57% trades=7 underlying=2.59% score=-14.71
- `memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold_options_debit_spread_30d` WDC debit_call_spread return=-4.66% trades=6 underlying=0.77% score=-14.78
- `memory_storage_momentum_15m_stx_alpaca_1h_trend_hold_options_debit_spread_otm_30d` STX debit_call_spread return=-5.42% trades=7 underlying=2.59% score=-15.56
- `memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold_options_long_call_atm_30d` WDC long_call return=2.73% trades=1 underlying=0.77% score=-22.29
- `memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold_options_long_call_otm_liquid_30d` WDC long_call return=1.80% trades=2 underlying=0.77% score=-23.24
- `memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold_options_long_call_otm_30d` WDC long_call return=1.54% trades=2 underlying=0.77% score=-23.50
- `memory_storage_momentum_15m_mu_alpaca_1h_trend_hold_options_long_call_otm_liquid_30d` MU long_call return=0.95% trades=1 underlying=7.64% score=-24.07
- `memory_storage_momentum_15m_mu_alpaca_1h_trend_hold_options_long_call_atm_30d` MU long_call return=0.00% trades=0 underlying=7.64% score=-25.00
- `memory_storage_momentum_15m_mu_alpaca_1h_trend_hold_options_long_call_otm_30d` MU long_call return=0.00% trades=0 underlying=7.64% score=-25.00
- `memory_storage_momentum_15m_sndk_alpaca_15m_trend_hold_options_long_call_atm_30d` SNDK long_call return=0.00% trades=0 underlying=3.21% score=-25.00
- `memory_storage_momentum_15m_sndk_alpaca_15m_trend_hold_options_long_call_otm_30d` SNDK long_call return=0.00% trades=0 underlying=3.21% score=-25.00
- `memory_storage_momentum_15m_sndk_alpaca_15m_trend_hold_options_long_call_otm_liquid_30d` SNDK long_call return=0.00% trades=0 underlying=3.21% score=-25.00
- `memory_storage_momentum_15m_stx_alpaca_1h_trend_hold_options_long_call_atm_30d` STX long_call return=0.00% trades=0 underlying=2.59% score=-25.00
- `memory_storage_momentum_15m_stx_alpaca_1h_trend_hold_options_long_call_otm_30d` STX long_call return=0.00% trades=0 underlying=2.59% score=-25.00
- `memory_storage_momentum_15m_stx_alpaca_1h_trend_hold_options_long_call_otm_liquid_30d` STX long_call return=0.00% trades=0 underlying=2.59% score=-25.00
- `memory_storage_momentum_15m_sndk_alpaca_15m_trend_hold_options_debit_spread_otm_30d` SNDK debit_call_spread return=-2.25% trades=2 underlying=3.21% score=-37.29
