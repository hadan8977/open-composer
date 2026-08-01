# R7 Backtest Forensics

- Conclusion: `blocked`
- Workflow pass: `false`
- Research pass: `false`
- Paper-ready pass: `false`
- Selected candidates: none

The quant feature timing itself uses complete close data before a next-open fill, and no event or LLM packet entered the historical run. The raw aggregate accounting is useful as a diagnostic, but the candidate gates are not promotion evidence.

Contract defects block the round. Fold entry and liquidation cost semantics were not frozen; StrategySpec and the candidate manifest disagree on whether 40% is a continuous or target-only cap; D06 changes both execution time and target holdings; and the exact benchmark subset used for candidate parity was not preregistered. The claimed exact D04 mask also drops the `2024-07-22` parent execution and starts from cash. The simulator lacks a fail-closed non-finite state check, although the bound source loader rejects non-finite OHLCV and no impact on stored R7 values was demonstrated.

The statistical outcome independently blocks selection: DSR probability is `0.57848` versus `0.95`, and D02 fails the 100-replicate permutation control. PBO `0.0` is a four-fold proxy with no CSCV or cumulative-project authority; `0/4` has a one-sided 95% upper bound near `0.527`, and the tie rule can pass an all-tied family. Raw candidate returns remain audit-only.
