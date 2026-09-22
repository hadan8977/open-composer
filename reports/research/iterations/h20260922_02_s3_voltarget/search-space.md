# Search space: h20260922_02_s3_voltarget

One mechanism, twelve frozen cells, written to candidate-manifest.json before any return was
computed. The base sleeve is not re-searched: menu A4 (TQQQ, SOXL, UPRO, USD, TECL), top two,
month-end rebalance and the absolute-momentum filter against SHY are inherited unchanged from
H-20260918-05.

| axis | values |
|---|---|
| annualized volatility target | 40%, 60%, none |
| realized volatility window | 21 sessions (fixed) |
| leverage cap | 1.0, down-only, remainder to SHY (fixed) |
| drawdown brake | none, or halve exposure at -25% from the sleeve equity peak and restore on a new high or after 21 sessions |
| momentum lookback | 63 sessions, or the equal blend of 21/63/126/252 |
| holdings | 2 (fixed) |
| rebalance | month end (fixed) |
| cost view | 10 bp and 20 bp per side, both reported for every cell |

3 x 2 x 2 = 12 candidates, VT01..VT12, one path. No model training, no mutation, no adaptive
expansion. The selection rule is fixed in advance: rank by selection-window Sharpe at 10 bp per
side and report the holdout for whatever that rule picked.
