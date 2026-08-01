# R5 Backtest Forensics

## Verdict

`blocked`. The time boundary and future-feature rejection checks pass, but no deterministic candidate is profitable at the lowest preregistered cost. D07 is the report-only leader at -10.94% total return, -0.59 Sharpe, and -14.05% maximum drawdown.

## Economic Test

D07 earns only 3.21 bps gross per traded day on average. The lowest contract charges 5 bps each at entry and exit, or 10 bps round trip. All four chronological slices are negative after cost. This is an economic rejection, not a marginal miss.

## Controls

The future-close feature was correctly rejected. The shuffled D08 score failed: N01 improved Sharpe by 0.73 and cumulative return by 5.01 percentage points. A four-slice PBO rank of zero does not rescue the family because every strategy loses and the placebo wins materially.

## Evidence Boundary

The panel is a survivorship-labelled current basket using IEX-only bars. There are no real PIT event packets, no formal-forward observations, and no matched quote/order/fill data. These results cannot support promotion or paper simulation.
