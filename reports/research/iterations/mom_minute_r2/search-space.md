# Search Space: mom_minute_r2

Path: `P1_time_series_etf_momentum` only.

The matrix is fixed at nine candidates: QQQ signal, TQQQ exposure, `30m`,
lookback `{72,96,120}` and rolling ATR filter multiplier `{1.5,2.0,2.5}`.
The component is a trend filter, not a stateful trailing stop.

Selection uses development and validation only. The final chronological lockbox
is opened once for the selected candidate. A failure stops or pivots the method
family; it cannot expand the grid or introduce ML, news, macro, or a second path.

Artifacts are `trial-ledger.jsonl` and `evaluation-report.json/.md` in this
directory. The benchmark family includes same-symbol, leveraged exposure,
market, sector/theme, cash, equal-weight universe, ex-post best symbol, and a
naive same-frequency momentum baseline.

