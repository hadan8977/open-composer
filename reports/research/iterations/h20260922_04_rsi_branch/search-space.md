# Search space: h20260922_04_rsi_branch

One path, 16 candidates, frozen in `candidate-manifest.json` before any price
was read. Lightweight single-mechanism path: no campaign contract, no archive,
no genetic search.

## Path `rsi_branch_sector_rotation` (16 candidates)

| Dimension | Values |
|---|---|
| `rsi_ref` | SPY, QQQ |
| `overheat_asset` | UVXY, BIL |
| `menu` | sector1x (XLK XLV XLF XLE XLI XLY XLP XLU XLB XLRE XLC), levered3x (TECL FAS ERX CURE DUSL) |
| `rebalance` | daily, friday |

Fixed, because the source strategy publishes them: `rsi_window` = 10,
`overheat_threshold` = 80, `oversold_threshold` = 30, `oversold_asset` = TQQQ,
`normal_lookback_days` = 21.

Fixed by protocol: signal on the close, fill at the next session's open; costs
`sum(|delta w|) * slippage` charged on the execution session at 10 bp per side
primary and 20 bp per side stress; SIP fully adjusted daily bars; long-only;
short-volatility products excluded by product category.

## Why 16 and not the brief's upper bound of 32

The brief allows up to 32 cells and lists `overheat_threshold` in {80, 85}. Two
reasons it is fixed at 80 instead:

1. The primary snapshot taken for this iteration discloses the threshold --
   "a 10-day 'heat gauge' (RSI) above 80" -- so round 1 replicates a published
   value rather than searching one. Because our proxy computes RSI on a single
   index instead of per sector, the branch already fires less often than in the
   original; moving to 85 pushes further in the wrong direction.
2. `oc research iteration validate` caps a single-mechanism iteration that is
   not bound to a campaign contract at 24 candidates. 32 cannot pass that gate;
   16 passes it and halves the multiple-testing exposure.

This is a narrowing, not a widening. No threshold, window, cost, benchmark or
gate from the brief has been relaxed.

## Benchmark family

Buy-and-hold SPY, MTUM, SPMO, QQQ and TQQQ; the live S1 sleeve
(`rot_A2_sector_lb252_top2_weekly`); equal-weight holdings of both menus. All on
the same windows, the same fill assumption and the same cost model.

## Budget accounting

16 preregistered candidates x 2 cost views = 32 evaluated series, plus 20
calendar-shift placebo seeds and 60 random-pick placebo seeds on the
selection-window winner of each menu. The trial count is reported as-is in the
report; no FDR correction is applied because the selection rule is "highest
selection-window Sharpe per menu", not a significance screen.
