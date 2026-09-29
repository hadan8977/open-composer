# Search Space: h20260928_44_etf_pair_switch

One path, `etf_pair_switch_screen`, 18 candidates: 12 PAIR_* candidates --
six highly correlated ETF pairs (QQQ/SPY, SMH/QQQ, XLE/XOP, KRE/XLF, IWM/SPY,
ARKK/QQQ) x lookback in {63, 126} trading days, monthly rebalance -- plus 6
STATIC5050_* placebo candidates (one per pair), a fixed monthly-rebalanced
50/50 blend of the same two legs with no ranking and no cash filter. This is
the full preregistered grid; no candidate is added, removed or retuned after
seeing a result.

Every PAIR candidate reuses `run_h20260918_05_recent_menu.py:rotation_cell`'s
mechanism unedited at the degenerate menu size of 2, top_n=1: rank the pair
by `momentum_score(close, str(lookback))`, pick the higher-scoring leg, keep
it only if it beats SHY's own score over the same lookback (absolute-
momentum filter), else hold SHY. Every STATIC5050 candidate ignores momentum
entirely and holds a fixed 0.5/0.5 book on the same two legs, rebalanced
monthly. Costs are 10bp primary / 20bp stress per side, next-session-open
fill after a close-session signal, identical to every prior batch-screening
round in this repository.

Candidates are judged against S3's frozen anchor (2024-01-08..2026-09-17)
and stress (2016-05-02..2023-09-15) windows via K1 (own date-neutral Sharpe
>= 80% of S3's in both windows) or K2 (a 63-session inverse-vol blend with
S3 beats a vol-matched control by >=0.05 Sharpe in both windows), with DSR
reported at n_trials=18 (the full 18-candidate batch, conservative). A PAIR
candidate that clears K1/K2/watch_recent is additionally checked against its
own paired STATIC5050 control: if it does not beat that control's judged
Sharpe in every window it passed on, it is downgraded to "not kept (no
switching increment)". STATIC5050 candidates are reported for context only
and are never themselves eligible for keep/strong/watch_recent.
