# Search Space: h20260928_43_political_etf_rotation

One path, `political_etf_rotation_screen`, 24 candidates: the POLITICAL menu
(NANC, GOP, MAGA, DEMZ) and the PLACEBO_BIGTECH menu (QQQ, XLK, SPY, DIA),
each swept over lookback in {63, 126, 252} trading days, top_n in {1, 2}, and
rebalance in {monthly, weekly} -- 3 x 2 x 2 = 12 combinations per menu, 24
total. This is the full preregistered grid; no candidate is added, removed or
retuned after seeing a result.

Every candidate reuses `run_h20260918_05_recent_menu.py:rotation_cell`'s
mechanism unedited: rank the menu by `momentum_score(close, str(lookback))`,
take the top `top_n`, keep only picks that beat SHY's own score over the same
lookback (absolute-momentum filter), equal-weight the survivors. Costs are
10bp primary / 20bp stress per side, next-session-open fill after a
close-session signal. A 40bp-per-side wide-spread sensitivity is computed
separately (scripts/analyze_h20260928_43_wide_spread.py) only for POLITICAL
candidates reaching watch_recent or better.

Judged on the select (2023-09-18..2025-12-31) and anchor (2024-01-08..
2026-09-17) windows only -- the 2016-05-02..2023-09-15 stress window is not
computed because NANC/GOP (launched 2023-02-07) have zero coverage of it.
This caps every POLITICAL/PLACEBO_BIGTECH candidate at `watch_recent`, never
a full keep, per the runbook's short-sample rule. A placebo-dominance
disqualifier (any watch_recent+ POLITICAL candidate whose same-grid-cell
PLACEBO_BIGTECH counterpart matches or beats its anchor Sharpe is downgraded
to not_kept) is preregistered per the queue task's requirement to test
whether the "political" framing adds anything over plain big-tech momentum.
DSR is reported at n_trials=24 (full batch).
