# Hypotheses: mom_minute_r2

## H1

- Hypothesis: medium-horizon QQQ time-series momentum, filtered by a rolling ATR
  distance rule, can produce positive next-open TQQQ returns after realistic
  research costs without relying on the withdrawn same-close result.
- Failure mode: leverage drag, reversals, open gaps, or turnover erase the
  apparent trend premium; validation selection does not survive the lockbox.
- Measurement: select one of nine fixed variants using development and
  validation only, then measure base-cost and two-times-cost return, Sharpe,
  MaxDD, trades, and the complete benchmark family on the untouched lockbox.
- Stop/Pivot criterion: stop this method family if the selected candidate fails
  any lockbox hard gate. Do not add parameters, P3, ML, news, or macro data to
  rescue it.

## H2

- Hypothesis: slower lookbacks and the rolling ATR filter reduce false entries
  enough to improve risk-adjusted performance over naive same-frequency
  momentum.
- Failure mode: the filter merely reduces exposure during profitable periods or
  overfits the validation window.
- Measurement: compare all nine development/validation trials with a fixed naive
  momentum baseline and inspect the untouched lockbox only after selection.
- Stop/Pivot criterion: stop if no validation candidate is positive after cost;
  pivot only if lockbox is positive but misses a stated risk/benchmark gate.

