# Hypotheses: mom_minute_r4_portfolio

## H1

- Hypothesis: removing the ATR filter or adding bounded exit hysteresis changes the frozen rule's participation and return profile.
- Failure mode: apparent improvement is selection bias from reusing the visible 102-session window.
- Measurement: record historical diagnostics, then compare frozen sleeves only on new completed sessions without retuning.
- Stop/Pivot criterion: stop a sleeve if forward data, costs, or operational errors invalidate its frozen definition.

## H2

- Hypothesis: a 15m ROC144 rule provides approximately the same three-day horizon with more responsive state updates and lower drawdown.
- Failure mode: higher sampling frequency amplifies microstructure noise or incomplete-session errors.
- Measurement: require exact QQQ/TQQQ timestamp alignment, complete sessions, and isolated virtual equity.
- Stop/Pivot criterion: stop if data completeness fails or forward risk is worse without compensating return.

## H3

- Hypothesis: failed Logistic and LightGBM gates may still provide useful forward diagnostics without controlling orders.
- Failure mode: they remain overselective, unstable, or indistinguishable from the rule fallback.
- Measurement: record model hash, target weight, mark price, turnover, cost, and virtual equity per fresh session.
- Stop/Pivot criterion: stop model observation if provenance changes, inference falls back, or no incremental evidence appears; never authorize broker writes from this round.
