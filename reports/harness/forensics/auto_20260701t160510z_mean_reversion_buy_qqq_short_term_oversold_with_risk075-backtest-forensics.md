# Backtest Forensics: auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_risk075

- Conclusion: `warning`
- Overfit risk: `medium`
- Lookahead check: `pass`
- Future-leak check: `pass`
- Candidate count reviewed this loop: `66`
- Trading days: `521`
- Round trips: `20`

## Result

`risk075` is the current research champion. It keeps the same ML features and
training setup as the prior champion, but raises `risk.max_position_weight` from
`0.50` to `0.75`.

Latest promotion smoke:

- Status: `warning`
- Ready: `no`
- Data tier: `research_strict`
- ML OOS: `ok`
- ML walk-forward: `ok`
- Fold count: `7`
- OOS predictions: `138`
- Return: `24.57%`
- Annualized return: `11.21%`
- Sharpe: `1.83`
- Max drawdown: `-5.15%`
- Trades: `20`

## Risks

- Trade count remains below the 30-trade adequacy target.
- Factor Lab still flags high correlation between RSI reversal and Bollinger
  location.
- Factor Lab still flags low coverage for the moving-average leverage gate.
- Benchmark family is still incomplete: `market_proxy` and `sector_theme_proxy`.
- The strategy still underperforms QQQ buy-and-hold in absolute return over the
  same window.
- Multiple-testing risk is material: 66 variants were reviewed in this loop and
  only 2 met the research threshold.

## Decision

Keep `risk075` as the draft research champion. Do not promote to paper. Further
strategy work should either improve trade count without destroying Sharpe, or
change the strategy family rather than continuing small threshold/window tweaks.
