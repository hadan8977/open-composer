# R9 Backtest Forensics

- Conclusion: `blocked`
- Workflow pass: `true`
- Research pass: `false`
- Paper-ready pass: `false`
- Window: `2017-02-01` through `2026-07-17` (`2,376` return intervals)

No timing lookahead or future-label leak was found. Daily signals use month-end closes and the immediate next session open, and the full daily panel is finite and complete through July 17, 2026.

R9 still fails promotion. R9D04's DSR probability is `0.207732` at the recorded lower-bound `N=8006`, below `0.95`. The reported PBO `0.0` is not candidate-specific: all six coarse partitions selected non-promotable R9D02. With only six partitions, it cannot establish a precise `<=0.20` gate.

The frozen BIL raw-Sharpe hurdle (`9.381916`) is arithmetically reproducible but is not a sound risky-alpha hurdle because BIL is the reserve/cash proxy and the calculation subtracts no risk-free return. The frozen rule is not revised after results, so its failure remains binding.

Accounting is internally reproducible under the declared approximation, but reported turnover uses half-L1 convention at cash boundaries, the cost model is not an exact self-financing solver, and event-level aggregate/fold reconciliation is absent. Capacity and opening-auction TCA also remain unverified.

R9D02 is retained only as exposed historical challenge evidence. A D02-shaped successor requires a new fixed preregistration and a forward epoch after July 19, 2026.
