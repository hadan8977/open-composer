# Backtest Forensics: nasdaq_tqqq_pdr_router_mlgate_iter2

Conclusion: `warning`, draft-only negative result.

Checks:

- Lookahead: pass. PDR ML features are index-1 route features; labels are future path outcomes and never reused as features.
- Future leak: pass. Training used stitched OOS folds with purged+embargo windows; embargo equals horizon for every trial.
- Multiple testing: 8 bounded combinations, no expanded search.
- Overfit risk: high. The selected gate failed five of six acceptance gates and materially degraded crisis protection.
- Sample: 3342 trading days, 802 round trips in the gated full-window replay.
- Data caveat: Longbridge materialized adjusted daily history is research replay cache evidence, not paper-ready market evidence.

Key negative evidence:

- Baseline: total return `5643.76%`, Sharpe `1.014`, MaxDD `-43.24%`.
- Gated: total return `7441.82%`, Sharpe `0.982`, MaxDD `-47.61%`.
- Crisis protection degraded in q4_2018, covid_crash, and calendar_2022 despite still beating TQQQ.
- Non-hard-stress state or weight changes were `0`, so the failure is from the intended gate decision surface, not route drift.

Decision:

- Keep `strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter2.yaml` as draft research only.
- Do not promote or modify active/paper behavior from this result.
