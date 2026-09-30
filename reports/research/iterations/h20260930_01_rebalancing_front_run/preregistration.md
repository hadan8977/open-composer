# Preregistration h20260930_01_rebalancing_front_run (written before any return or coefficient was computed)

Task T-20260930-01. Sources: sources/ and reports/harness/source_cards/h20260930_01_rebalancing_front_run.jsonl.
Deviations from the paper (disclosed): normalisation 0.012 (QuantReturns) not 1.5 percent; 25 deltas 0.1%..2.5% (the paper also gives a variant excluding delta = 0); Calendar reversal on the last session of the month (QuantReturns) not the first business day of the next month (paper).

## Data
SIP daily bars data/sip/daily (SPY, IEF, TLT, QQQ, TQQQ, SQQQ, BIL), session date = America/New_York date of the bar timestamp, 2016-01-04..2026-09-29. c(t) close, o(t) open. R_S(t) = c_SPY(t)/c_SPY(t-1) - 1, R_I(t) likewise for IEF. Dividend check of SPY/IEF/TLT closes against the local Longbridge adjusted cache is reported (results.json dividend_check); signals use the SIP closes as they are.

## Signals (formulas frozen)
For each simulated portfolio, w_post(2016-01-04) = 0.6. For each session t after that:
w_pre(t) = w_post(t-1)(1+R_S(t)) / [ w_post(t-1)(1+R_S(t)) + (1-w_post(t-1))(1+R_I(t)) ],  dev(t) = w_pre(t) - 0.6.
Threshold portfolio with delta: if |dev(t)| > delta then s_delta(t) = dev(t) and w_post(t) = 0.6, otherwise s_delta(t) = 0 and w_post(t) = w_pre(t). THR(t) = mean of s_delta(t) over delta in {0.001, 0.002, ..., 0.025} (25 values). No warm-up trimming.
Calendar portfolio: s_c(t) = dev_c(t); w_post(t) = 0.6 when t is the last session of its calendar month (a later data session exists in a different month), otherwise w_pre(t). k(t) = 1 + number of later sessions in the same month; defined only for months that are followed by a later month in the data (the incomplete last month gets CalMod = 0).
CalMod(t) = -sign(dev_c(t)) for k(t) in {2,3,4,5}; CalMod(t) = +sign(dev_c(t*)) for k(t) = 1 where t* is the session of the same month with k = 5 (the negative of the modified value at the 5th-last session); CalMod(t) = 0 otherwise. sign(0) = 0.
W(t) = 0.6 * (-THR(t)/0.012) + 0.4 * CalMod(t). The position for session t+1 is decided from W(t).

## Regression negation test
y = segment return of session t+1: overnight ON = o(t+1)/c(t) - 1; intraday ID = c(t+1)/o(t+1) - 1; total CC = c(t+1)/c(t) - 1. Legs: SPY, and spread SPY minus IEF (difference of the same segment returns). Regressors (one at a time, OLS with intercept, HC3 standard errors): THR (expected sign negative), CAL_L4 = dev_c(t) * 1{k(t) in 2..5} (expected negative), CALMOD (expected positive), W (expected positive). Windows by the return date t+1: full 2016-01-05..2026-09-29; stress 2016-05-02..2023-08-31; anchor 2024-01-08..2026-09-29.
Placebo: 500 circular shifts of the regressor by a random integer in +/-[10,60] sessions (seed 20260930); report the share of placebo t-statistics at or beyond the real one in the expected direction (one-sided quantile) and two-sided.

## Gate (numbers frozen; equity leg SPY intraday is the tradable leg)
G1 SPY ID coefficient on THR, full sample, negative. G2 full-sample HC3 t <= -2.5. G3 anchor window coefficient negative and |t| >= 2.0. G4 (only if G1-G3 pass, needs the ledger) at least one of R3, R4, R5, R6, R8 has 10 bp net Sharpe >= 0.8 in the full sample and >= 0.8 in the anchor window (open-to-close hold is the primary variant). If the effect is mainly in the overnight leg (SPY ON t more negative than ID t and ID fails G2 or G3): write "not obtainable at a next-open fill" and stop. Spread results are diagnostics. If any of G1-G3 fails, no ledger is run.

## Candidates R1-R8 and ledger (only after G1-G3 pass)
R1 SPY-IEF weight clip(W,-2,2) long SPY / short IEF (diagnostic). R2 SPY-TLT same clip (diagnostic). R3 SPY, sign(W)*min(|W|,1). R4 QQQ same. R5 TQQQ if W>0, SQQQ if W<0 (both long), size min(|W|,1). R6 R3 on days |W| >= 1 only. R7 R1 on days |W| >= 1 only (diagnostic). R8 SPY weight = CalMod (Calendar part only).
Costs: 10 bp per side per leg on weight change (20 bp check); open-to-close variant flat each night so entry and exit both pay; open-to-open pays on change in weight. Borrow on shorts of SPY/QQQ/IEF/TLT 0.3 percent per year (3 percent sensitivity) per session held short. Net daily returns, Sharpe via base.metrics with BIL, windows from scripts/screen_lane.py WINDOWS plus the anchor 2024-01-08..2026-09-29. Tiers: K1 anchor >= 1.1882 and stress >= 0.6447; K2 diversifier edge >= 0.05 in both windows versus S3; DSR with 8 trials; date-shift placebo share <= 10 percent. No kept.jsonl entry is written by this task.
