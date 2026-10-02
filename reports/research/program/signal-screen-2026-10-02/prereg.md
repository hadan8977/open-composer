# Preregistration: residual-IC batch screen of candidate signals for book v1.1 (T-20261002-24)

Written 2026-10-02 04:02 UTC by the executor, before any candidate IC was computed. Source brief:
`reports/research/control/briefs/T-20261002-24.md` (copied here; the brief is the contract). Coordinator code
R1002-0400-T24. No backtest, no Modal.

## Candidates (no other candidate may be added after any number is seen)

1. `ml_pv`: the three T-19 walk-forward models `predictions_{LGBM,XGB,CAT}_WX_H63.parquet` under
   `reports/research/iterations/t20260930_17b_model_family_book/cache/`. Per model, each symbol's latest
   prediction with trade_date <= formation date (as-of join, never a later date); rank within the universe,
   (rank - 0.5)/n; average over the models present; inverse normal. Missing = NaN. Validity check: every
   prediction's fold has train_cutoff at least 63 trading sessions (the documented embargo, `embargo_days` 63 in
   `candidate-manifest.json`, applied by `h02.embargo_cutoff` before the validation quarter) before the first
   date it predicts; otherwise the candidate is `invalid`.
2. `alpha158_fdr`: equal-weight composite of the Alpha158 factors that passed BH-FDR in line
   `ml_ranking_liquid500_recent_vs_momentum_rule`. `audit.json` carries only the count (29 Alpha158 factors of 80
   FDR passes) and the data path; the factor list and signs are read from the raw output of that screen,
   `reports/research/factor_screen/step13f_screen.parquet` (rows with `fdr_pass`, library alpha158, 29 unique
   factors, matching the audit count). Sign = sign of `ic_mean_full` of that screen (identical across the two
   labels for every factor); never refitted here. Data `data/features/alpha158`; per factor, sign x value,
   rank-normal within the universe members with a finite value on the date, then the mean over the factors
   available; NaN when fewer than 15 of 29 are available. If the list could not be found: `unavailable`
   (it was found).
3. `low_max`: minus `maxret` from `data/features/osap_price_broad`, rows on the formation date exactly.
4. `near_52w_high`: close / max close over the trailing 252 sessions (the session calendar of
   `data/features/daily_broad`, rows <= the date only, at least 200 finite closes in the window). `osap_price_broad`
   has no such column; source `data/features/daily_broad` close. Diagnostic only (not in the admission rule): the
   same ratio from the research-panel close.
5. `reg` (return-earnings gap reversal): searched `scripts`, `open_composer`, `docs` for `ben_rephael`,
   `earnings_gap`, `return_earnings_gap`; the only hits are the 2026-10-01 prior-work audit text, no implementation.
   Marked `not_built`; not built now.

k = number of candidates actually tested (invalid / unavailable / not_built do not count). Expected k = 4
(ml_pv, alpha158_fdr, low_max, near_52w_high) unless a candidate is marked invalid.

## Machinery (reused, not reimplemented)

`scripts/build_book_v1_alpha.py`: `month_end_positions`, `residual_target` logic as in `build()` (21-session open-to-open
forward return minus `X_d . f_k` over sessions p+1..p+21, names = risk-model exposure names present in the panel),
`rank_ic`, `LAG`, `HORIZON`, `select_window`, `m1_weights`. Panel `PricePanel.from_dir(start="2016-09-01")`, `RiskModel`,
risk factor returns, themes_<year>.parquet (with `in_u3000`, `in_p1000`), `alpha/book_v1/formation_ic.parquet`.
Formation dates: those of `formation_ic.parquet`; windows from `residual-ic-summary.json`: stress 2017-10-02..2023-07-31,
anchor 2024-01-08..2026-08-14, anchor_2026 2026-01-01..2026-08-14. Candidate scores are rank-normal within the universe
(u3000, p1000) members with `n >= 300`, as in the build.

Identity check before any candidate: recompute, over all formation dates and both universes, the IC of one theme
(value), M0 and M1 and compare with `formation_ic.parquet`; max abs diff must be <= 1e-9, otherwise stop.

## Statistics per candidate x universe

Per window: monthly IC mean, sd, plain t, Newey-West t (lag 2, same formula as `summarize_book_residual_ic.py`),
share positive, n. Coverage: mean share of universe members with a finite score. Mean cross-sectional Spearman
correlation with the M1 and the M0 composite at the formation dates (composite = `sub @ w`, rank-normal; M1 weights
from the lagged theme ICs exactly as `FormationIC.m1_at`). Incremental residual IC: on each formation date regress the
candidate's rank-normal score (rank-normal within the rows where both are finite) on the M1 composite's rank-normal score
(OLS with intercept), take the rank IC of the residual against the residual target; report mean, t, NW t.
Placebo: 100 within-date permutations of the candidate's universe scores (NaNs included), seeds 20261002 + s
(s = 0..99); anchor residual-IC series per draw; the placebo anchor t is the Newey-West (lag 2) t, the same statistic as
condition (a); the plain-t analogue is reported too. Real t position = share of placebo draws below it.

## Admission rule (mechanical; all must hold on U3000)

- (a) anchor residual-IC NW t >= z_{1-0.025/k} (k=3: 2.394; k=4: 2.498; k=5: 2.576);
- (b) stress-window mean IC >= 0;
- (c) mean cross-sectional correlation with the M1 composite < 0.5;
- (d) incremental residual IC anchor NW t >= 2.0;
- (e) real anchor NW t above the placebo 95th percentile of anchor NW t.

Otherwise `rejected` with the failing conditions listed. P1000 is reported, never used to admit.
This file and the rule are not changed after any number is seen.
