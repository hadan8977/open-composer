# Decision Record: t20261001_01_dash_for_cash_settlement

## Path

dash_for_cash_settlement_timing: SPY held from the open after the settlement-implied marginal cash-raising day b (tau-4 before 2024-05-28, tau-3 after) to the open after tau+3 (T-20261001-01), plus a cross-sectional mechanism measurement on P500 momentum losers (T-20261001-02, M1-M3).

## Decision

Stop (lead review, 07:07 UTC round, 2026-10-01). The preregistered rule "指数候选全不过且 M1 不过：关闭 dash-for-cash 线，E0 不变" applies: both judged index candidates fail the replacement rule, K1 and K2, and M1 fails. E0 and C2 stay unchanged.

T-20261001-01 (`results.json`, parity ok: E0_REF reproduces 1.339 / 1.241 / 0.584 / -0.574 exactly, engine diffs 0.0):

- DFC_U: selection 10 bp -0.765, 20 bp -1.329, anchor -0.500, stress 0.112, 2026 0.787; K2 -0.554 / -0.252; placebo beat 0.03 / 0.16 / 0.77 (selection / anchor / stress).
- DFC_C: selection 10 bp -0.379, 20 bp -0.633, anchor -0.104, stress 0.359, 2026 1.230; K2 -0.349 / -0.082; placebo beat 0.14 / 0.60 / 0.94.
- Replacement: only clause b (2026 >= -0.674) passes for either; a (>= 1.439), c (>= 1.271), d (>= 0.584) and the placebo clause fail. K1 fails on the anchor bar (1.19). K2 is negative in both windows.

T-20261001-02 (`results_xs.json`, 115 months 2017-02 to 2026-08, P500 median 500 names, 219 delisted symbols ever in the pool):

- M1 (gate): D1 dollar-volume-weighted pre-window [b-5, b] minus other days -7.66 bp/day, NW t -0.86 (pre-reform -9.57, t -0.88; post-reform -1.75, t -0.12). The bar is t <= -2.0. Fail.
- M2 (report only): post-window [b+1, tau+3] +10.86 bp/day, t 2.02.
- M3 (report only): the T+1 shift replicates at the single-day level. theta = 125.7 bp, t 3.05 combined; 2024-06 to 2025-12 127.8 bp, t 3.00; out of the paper's sample (2026, 8 months) 120.7 bp, t 1.58. Pre-reform the selling day was tau-4 (-37.6 bp vs control days); post-reform tau-4 is +51.4 bp and tau-3 -40.1 bp.
- Trade economics (design evidence only): long D1 from b+1 open to tau+4 open, net 10 bp, Sharpe 0.70 stress / 0.60 anchor, but hedged D1 minus SPY only 0.27 / 0.39. The raw number is mostly market beta of the losers.

## Reason

Audit of the five standing checks:

- Look-ahead: b is fixed by the NYSE calendar, which is published in advance. The conditional variant uses close(b-6) to close(b) with a signal at close b and a fill at open b+1. Cross-sectional groups are formed at the month-end close tau_f and used from tau_f+4, so no group uses later prices.
- Survivorship: T-01 trades SPY only. T-02 reads `data/sip-delisted`. Missing post-delisting returns are dropped, which favours the losers and so biases M1 toward failing. The bias cannot bridge the gap: moving t from -0.86 to -2.0 needs the coefficient to move by about 10 bp/day over roughly 690 pre-window days, i.e. on the order of a hundred -30% delistings at 2% D1 weight inside six-day windows. P500 names do not delist that way.
- Placebo: T-01 used 100 random-entry seeds. The judged candidates lose to the median seed in the selection window (beat 0.03 and 0.14).
- Costs: 10 bp judged, 20 bp reported. Both candidates are negative at 20 bp in the selection window.
- Rebalance-day choice: the window has no free parameter (settlement rule plus the paper's tau+3 exit), and the placebo randomises the entry day.

Executor deviations (listed in the queue notes) do not touch the verdict. The incomplete 2026-09 month is excluded. The shift t uses OLS with HAC(3) instead of `newey_west_t`; it is a report-only number. The cross-section starts in 2017-02 because 12-1 momentum needs a year of history. The executor set the group freeze window, removed suspected split days and dropped missing delisting returns. M1 misses its bar by a factor of two in t.

Cause of death: the signal is too weak at a tradable horizon, not an execution problem. The institutional cash-raising day exists in our data as a one-day effect that moved with the settlement reform. Over the six-day window it is small next to the noise, both for SPY and for P500 losers. The index window is noise relative to random entry days.

## Rejected variants

None added after results. The fixed tau-4 controls are not adoptable by preregistration and are no better (DFC_U_FIX4 anchor -0.429, DFC_C_FIX4 -0.108). A one-day short of losers on tau-3 is suggested by M3. It is not tested here: it was not preregistered, M3 rests on 27 post-reform months, and per `docs/research-program.zh.md` fast single-stock signals enter only the equity book's ML layer.

## Next iteration suggestion

Close the dash-for-cash line and add no further ETF calendar rules (program, main line 2). Reopen only with new identifiable information, such as an independent flow dataset that shows the window effect, not the single-day shift. The settlement-calendar x loser interaction is recorded as a possible ML feature for Stage 2b of the equity book, judged only by the book's marginal contribution rules.
