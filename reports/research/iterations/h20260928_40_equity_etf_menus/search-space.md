# Search Space: h20260928_40_equity_etf_menus

One path, `equity_etf_menus_screen`, 24 candidates: the FACTOR menu (MTUM,
QUAL, USMV, VLUE, SIZE) and the INDUSTRY menu (SMH, XBI, KRE, ITB, IGV, XOP,
XRT, IHI), each swept over lookback in {63, 126, 252} trading days, top_n in
{1, 2}, and rebalance in {monthly, weekly} -- 3 x 2 x 2 = 12 combinations per
menu, 24 total. This is the full preregistered grid; no candidate is added,
removed or retuned after seeing a result.

Every candidate reuses `run_h20260918_05_recent_menu.py:rotation_cell`'s
mechanism unedited: rank the menu by `momentum_score(close, str(lookback))`,
take the top `top_n`, keep only picks that beat SHY's own score over the same
lookback (absolute-momentum filter), equal-weight the survivors. Costs are
10bp primary / 20bp stress per side, next-session-open fill after a
close-session signal, identical to every prior batch-screening round in this
repository. Candidates are judged against S3's frozen anchor
(2024-01-08..2026-09-17) and stress (2016-05-02..2023-09-15) windows via K1
(own date-neutral Sharpe >= 80% of S3's in both windows) or K2 (a 63-session
inverse-vol blend with S3 beats a vol-matched control by >=0.05 Sharpe in both
windows), with DSR reported at n_trials=24.
