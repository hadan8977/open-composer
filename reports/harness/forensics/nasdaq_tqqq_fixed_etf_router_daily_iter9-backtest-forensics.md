# Backtest Forensics: nasdaq_tqqq_fixed_etf_router_daily_iter9

- Conclusion: `warning`
- Overfit risk: `medium`
- Lookahead check: `pass`
- Future-leak check: `pass`
- Formal fixed-route replay trials: `1`
- Trading days: `3356`
- Round trips: `836`

The selected route uses prior confirmed daily data and next-open fills. The final fixed-route replay now writes standard router `search-space`, `trial-ledger`, `candidate-set`, and `walk-forward` artifacts so downstream checks can audit the route without reading only the large router report.

The current evidence line is materially better than the prior rejected variants: Longbridge full annualized return is about `34.77%`, Sharpe is about `1.11`, and max drawdown is about `-33.48%`; OOS annualized return is about `61.20%`, Sharpe is about `1.52`, and max drawdown is about `-28.10%`. Alpaca/IEX cross-check is stronger, with full annualized return about `46.81%`, Sharpe about `1.32`, and max drawdown about `-26.92%`.

This is still not a paper-auto approval. The formal replay ledger covers the selected fixed route, while earlier exploratory searches were iterative and not fully represented as a single standardized trial ledger. Alpaca IEX is also not consolidated SIP evidence. The strategy should stay `draft/manual_signal` until the user explicitly approves lifecycle and paper-auto activation after paper safety review and order authorization.
