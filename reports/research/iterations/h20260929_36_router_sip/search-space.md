# Search Space: h20260929_36_router_sip

One path, `router_sip_recheck`, 7 candidates (no parameter search). Frozen route parameters (decoded from label lb10_entry2_top1_open0_mom0_rv1_qprior_negative_reversal_maxopen0_maxmomnone, see decision-record.md for the line-number table): lookback_days 10, entry_after_bars 2, top_n 1, min_opening_return_pct 0.0, min_prior_momentum_pct 0.0, min_relative_volume 1.0, market_gate qqq_prior_negative, selection_style opening_reversal, max_opening_return_pct 0.0, max_prior_momentum_pct None.

- R0: frozen route, both legs as coded.
- R0_long / R0_short: the same route keeping only long or only short selections.
- P1, P2, P3: random-pick placebos (seeds 20260929, 20260930, 20261001) on QQQ-gate days, plus 200 distribution seeds 100000..100199.
- B_ew: equal-weight long of the 12 names, entry bar 2, exit at close, every day.

Costs 10 bp / 20 bp / 2.5 bp per side; borrow 0.5 percent a year on short days. Windows: anchor 2024-01-08..data end, select 2023-09-18..2025-12-31, contaminated holdout 2026-01-02..2026-09-17, new holdout 2026-09-18.., partial stress 2023-01..2023-08 (full stress period pending), iex_comparison 2024-05-31..2026-05-29 (the recorded IEX window, report only). Keep rule K1/K2/G3 in candidate-manifest.json.
