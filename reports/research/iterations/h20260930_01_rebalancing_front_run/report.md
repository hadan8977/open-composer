# T-20260930-01 60/40 rebalancing front-run, equity leg: regression gate failed, stopped

Iteration `h20260930_01_rebalancing_front_run`. Numbers are from `results.json` (script `scripts/run_h20260930_01_rebalancing.py regress`, capped 600M). Formulas, windows and gates were frozen in `preregistration.md` and validated (`--stage pre-backtest`, `prebacktest-validated-at.txt`) before any coefficient was computed. Status: workflow_pass true, research_pass false, llm_contribution_pass false, paper_ready_pass false. No orders, no paper authorization touched.

## Data and dividend check
SIP daily SPY, IEF, TLT, QQQ, TQQQ, SQQQ, BIL: 2,700 sessions 2016-01-04..2026-09-29. SPY/IEF/TLT are not in `data/research/longbridge_adjusted_daily`; QQQ is. QQQ adjusted/SIP close ratio is 1.0018 on 2016-01-04 and 0.99999 on 2026-05-21, so the SIP daily bars are already dividend-adjusted (not raw). For SPY/IEF/TLT the same convention is inferred: ex-dividend overnight gap means are -3.6 bp (SPY, quarterly ex days), -3.2 bp (IEF), -7.0 bp (TLT, monthly first business day) against dividends of roughly 30 bp (SPY, TLT) and 15-20 bp (IEF, approximate), so no full unadjusted gap is present. The bond leg therefore includes coupon carry approximately; the bond leg is a diagnostic anyway.

## Regression (SPY next-session return on Threshold, HC3; coef, t, one-sided placebo share)
| segment | full 2016-01-05..2026-09-29 (n 2699) | stress 2016-05-02..2023-08-31 (n 1847) | anchor 2024-01-08..2026-09-29 (n 684) |
|---|---|---|---|
| overnight (close t to open t+1, not capturable) | -0.467, t -1.82, 0.06 | -0.637, t -2.20, 0.01 | +0.156, t +0.22, 0.61 |
| intraday (open to close t+1, capturable) | -0.520, t -2.84, 0.02 | -0.564, t -2.68, 0.03 | -0.400, t -0.84, 0.27 |
| total close to close | -0.989, t -3.19, 0.01 | -1.207, t -3.51, 0.00 | -0.233, t -0.27, 0.40 |

The full table (SPY and SPY-IEF, ON/ID/CC, signals THR, CAL_L4, CALMOD, W, three windows, 500 date-shift placebos each) is `results.json["regression_table"]`. SPY-IEF intraday Threshold: full -0.714 t -3.02, stress -0.758 t -2.67, anchor -0.597 t -1.15.

## Gate (preregistered numbers, unchanged)
- G1 intraday SPY Threshold coefficient negative, full sample: pass (-0.520).
- G2 full-sample HC3 t <= -2.5: pass (-2.84).
- G3 anchor window coefficient negative and |t| >= 2.0: FAIL (coefficient -0.400, t -0.84; placebo share 0.27).
- Overnight-dominance clause: not triggered (overnight full t -1.82 is weaker than intraday -2.84).
Decision: stop. No candidate ledger was run; R1-R8 have no Sharpe (results.json `candidate_net_sharpe` all null). The SPY-IEF spread version (the registry's stop condition wording) fails the same anchor bar (t -1.15).

## Observations that are not gates (do not change the verdict)
- The Calendar-containing signals keep some anchor-window intraday sign: W t +1.99, CALMOD t +2.09 (SPY); these were not the preregistered gate signal and 1.99 is below 2.0.
- Effect size is small relative to costs: regression-implied gross for an R3-style SPY book is 1.36 bp per day against 2.47 bp per day of open-to-close cost at 10 bp per side (mean position 0.123; `informational_implied_gross_vs_cost`), using the in-sample full-sample coefficient. Only 0.15% of days have |W| >= 1, so R6/R7 would trade about 4 days in 2,700.
- The effect is stronger in the 2016-2023 stress window (t -2.68) than in 2024-2026 (t -0.84), consistent with decay after publication and crowding (Daniel; Bloomberg), but 684 observations cannot separate decay from noise.

## Caveats
Signal deviation convention: pre-rebalance weight at the close; no warm-up trim; 25 deltas (paper also uses delta = 0); normalisation 0.012 and last-session Calendar reversal follow the queue task, not the paper (1.5 percent, first business day). Spreads and bond legs are diagnostics only (owner rejected cross-asset 2026-09-28).
