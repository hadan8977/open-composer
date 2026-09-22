# Decision Record: giants_sweep_20260922

## Path

giants_replication_sweep

## Decision

stop_the_giants_route_as_a_source_of_high_return_cells

## Reason

24 published specifications ran under the frozen protocol. **Zero** cleared all
gates: G1 0/24, G1' 0/24, G2 7/24, G3 4/24, G4 0/24. No cell reached 50% anchor
CAGR with a drawdown inside 35%, and none reached a 2.0 anchor Sharpe. The
census's headline numbers (140%-350% annualized on Composer, 39% on 9-sig, 20%+
on BAA) do not survive our windows, our next-open fills and 10 bp per side.

Three findings worth keeping:

1. **The one honest survivor is a cash-heavy Sharpe cell, not a return cell.**
   `f1_tqqq_rsi_no_hedge_ablation` -- the published Composer TQQQ RSI tree with
   its UVXY/TECL volatility legs replaced by cash -- returns 15.9% annualized on
   the anchor window with a -5.2% drawdown, a 1.37 anchor Sharpe, a 1.50 holdout
   Sharpe and **0 of 20** calendar-shift placebo seeds matching it. It is the
   only cell in the sweep with a positive vol-matched excess against the whole
   benchmark family (+12.0% vs SPY, +14.2% vs SPMO, +20.7% vs QQQ). It fails only
   the return bar, which is a sizing question, not an evidence question.
2. **The volatility hedge legs destroy value here.** The same tree *with* UVXY
   and TECL (`f1_composer_tqqq_rsi`) drops to a 0.79 anchor Sharpe and 26.8%
   CAGR with far higher turnover. UVXY's daily reset is paid for and not earned
   back in this window.
3. **Nothing in F2, F5 or F7 has a signal.** Every F2 and F5 cell is beaten by
   its own random-pick placebo on 95-100% of seeds; the two-leg "2.46 Sharpe"
   structure returns 4.8% annualized here. The overnight family loses 20%+ a
   year purely to the frozen cost model.

## Next iteration suggestion

Do not widen this grid on the same holdout. The one thing worth a follow-up is
the `f1_tqqq_rsi_no_hedge_ablation` cell: it is a low-exposure, high-Sharpe,
placebo-clean book, so the open question is whether the already-frozen
H-20260922-02 volatility-target machinery can scale it up to the return bar
without reintroducing drawdown. That is an overlay question against an existing
frozen contract, not a new search. Everything else in the census that is still
untested (Kipnis KDA, Keller LAA, the minute-bar ORB work) needs a different
data path and belongs in its own iteration.
