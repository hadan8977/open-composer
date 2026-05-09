# Signal Parity Checklist: qqq_pullback_15m

- Pine file: `/root/codex-test/open-composer/strategies_pine/generated/qqq_pullback_15m.strategy.pine`
- Python signal semantics: bar-close confirmation.
- Pine signal semantics: `barstate.isconfirmed`.
- Backtest fill assumption: next bar open.
- Repaint risk: low for supported OHLCV and ta.* expressions without lookahead.
- Manual check: compare TradingView alert timestamps against `signal_logs/*.jsonl`.
