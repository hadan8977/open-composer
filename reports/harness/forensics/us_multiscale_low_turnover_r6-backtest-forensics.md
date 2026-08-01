# R6 Backtest Forensics

R6 is blocked and has no contract-valid performance result. The raw data are real Alpaca IEX snapshots through 2026-07-17, but the multi-asset evaluator applies unchanged target weights on every return row without simulating holdings drift. D02-D06, N01, and the equal-weight benchmark therefore have invalid returns, exposure, turnover, and costs.

D06 is also not a matched D05 timing overlay. In the shared window, D05 has 30 execution dates and D06 has 29 independently anchored rebalance dates; only 2025-12-22 overlaps. Their first dates are 2024-01-19 and 2024-01-02. The preregistered D05 same-window benchmark is absent.

D01-D04 violate the StrategySpec 40 percent symbol cap. The future-feature control is a direct exception stub rather than an end-to-end feature-path test. The single shuffled-score run is not a placebo distribution, and its parent result is invalid. The DSR and PBO values are retained as non-authoritative proxies only; the 0.95 DSR threshold was not numerically preregistered.

The previously reported D01 raw return of 51.13 percent and D05 raw return of 22.37 percent are audit records, not evidence of strategy performance. No R6 candidate may be promoted, observed as a selected forward candidate, or connected to paper simulation. Correct self-financing accounting, cap enforcement, schedule parity, statistical thresholds, and benchmark parity belong to a new preregistered iteration.
