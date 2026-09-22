# Decision record: h20260922_04_rsi_branch

## Path

`rsi_branch_sector_rotation` -- one path, 16 preregistered candidates, brief
B-1 round 1. Replication of the published Composer RSI-extreme branch tree
(overheat -> UVXY or BIL, oversold -> TQQQ, otherwise -> strongest 21-day
performer of a fixed sector menu) under the frozen H-20260918-05 windows,
costs, fill assumption and placebos.

## Decision

Pre-backtest: proceed. Direction review is `proceed`, three primary sources are
snapshotted and hash-bound, and the whole grid is frozen in
`candidate-manifest.json` before any price is read.

Post-backtest decision (continue / pivot / stop) is recorded in `report.md` in
this directory and summarized in `reports/research/briefs/B-1-result.md`; if the
verdict is stop, the lesson is `reports/research/lessons/L-20260922-04.md`.

## Reason

Three reasons this candidate got compute instead of something else:

1. It is the only family in intel harvest I-20260922-02 that combines a fully
   published rule, two independent live-tracked instances, and out-of-sample
   numbers (Sharpe 1.44 and 1.92) high enough to matter after costs.
2. Its two new elements relative to our refuted work -- an RSI extreme branch
   and a volatility hedge leg -- are exactly what L-20260918-05 did not contain,
   so reopening the area is justified by new mechanism, not by hope.
3. It is cheap and decisively falsifiable: 16 cells on daily bars, minutes of
   CPU, with two placebos that can kill it outright.

The threshold search in the brief was dropped because the primary snapshot
publishes the threshold, and because the iteration gate caps an uncampaigned
single-mechanism iteration at 24 candidates. That is a narrowing; no gate,
threshold, cost or window from brief B-1 or from the 2026-09-22 factory plan was
changed.

## Next iteration suggestion

Round 2 is allowed only if a cell clears G1/G1' and G2 but dies on cost or
turnover, since the weekly-rebalance remedy is already preregistered in this
grid. If instead the placebos kill it, the correct next step is not another
variant of this family: it is the second confirmation of L-20260918-05 -- that
in this bull window, single-signal gates on leveraged ETF menus do not survive a
calendar shift -- and the factory should spend week 2 on the LLM-text track
(H-20260922-01) rather than a third rule-tree replication.
