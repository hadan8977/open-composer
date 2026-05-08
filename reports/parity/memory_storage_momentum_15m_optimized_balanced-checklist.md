# Signal Parity Checklist: memory_storage_momentum_15m_optimized_balanced

- Pine file: `/root/codex-test/open-composer/strategies_pine/generated/memory_storage_momentum_15m_optimized_balanced.pine`
- Python signal semantics: bar-close confirmation.
- Pine signal semantics: `barstate.isconfirmed`.
- Backtest fill assumption: next bar open.
- Repaint risk: low for supported OHLCV and ta.* expressions without lookahead.
- Manual check: compare TradingView alert timestamps against `signal_logs/*.jsonl`.
