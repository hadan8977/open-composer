# Research Memory: us_robust_momentum_ensemble_r4

- Iteration: `mom_robust_momentum_r4`; completed diagnostic, rejected for research and paper use.
- Thesis: combine ETF time-series trend, residual stock momentum, sector-relative momentum, cash, and deterministic risk controls. Raw stock 12-1 is benchmark-only.
- Candidate accounting: 15 preregistered (`D01-D07`, `M01-M06`, `N01-N02`); no selected or forward-observation candidate.
- Report-only leader: `D06`, 370 OOS sessions, return 45.564988%, Sharpe 2.277608, max drawdown -11.188328%, first fold -0.854521%, 40 bps return 41.760526%.
- ML rejection: shuffled-label `N01` returned 47.723085% with Sharpe 2.726463 and materially beat parent `D07`; stop the whole ML path for this epoch.
- Multiple testing: coarse PBO 0.166667 is unstable; DSR proxy failed because observed max Sharpe 2.277608 was below expected max 2.52499.
- Data boundary: current-survivor 40-stock snapshot, 1,000 common sessions, no inactive securities, delisting returns, permanent IDs, or versioned corporate-action lineage.
- Execution boundary: Nasdaq Basic adjusted bars are not SIP or official-open evidence; no matched opening-order TCA, capacity proof, or broker authorization exists.
- Formal forward start is 2026-07-20 and current formal-forward observation count is zero.
- Do not repeat another parameter/model search on this frozen epoch. Fix PIT/delisting/action data, longer cross-source history, official-open comparison, and TCA first.
- No model warm start, serialized estimator, LLM/text alpha, observation route, simulated broker route, or paper order is authorized.
