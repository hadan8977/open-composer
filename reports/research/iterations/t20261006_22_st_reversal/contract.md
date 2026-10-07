# T-20261006-22 contract: short-horizon residual-reversal stat-arb book (frozen before any return of this book is computed)

Written 2026-10-06 by the T-20261006-22 research agent (Sonnet 5.5). Everything below is fixed before the first backtest of this dossier. No return, IC or Sharpe of any variant of this book had been computed when this file was frozen; the only numbers read beforehand are the data-coverage counts in section 1 (symbols, mcap source, news coverage), no returns.

## 0. What is tested, and how it differs from closed directions

Mechanism (sources in external-brief.md): short-horizon (1-21 session) reversal of the part of a stock's return that is not explained by common factors; held 1-10 sessions as overlapping daily batches, long the lowest residual and short the highest, dollar neutral, SPY beta hedge, costs from the measured spread model, shorts only in the easy-to-borrow proxy.

Differences from the registry rows (each id read, last row):
- `sector_residual_reversal_statarb_decay` (external, OOS 2019-2024 net -0.15, "needs a short leg we cannot execute"): reopened because the owner's 2026-09-29 scope makes shorts available and our cost model is measured (close/open quote snapshots by liquidity), not a flat 7 bp. New: PCA and beta residuals, 1-21 day lookbacks, 1-10 day holds, turnover/news/VIX conditions, ridge and LightGBM rankers, liquid-universe buckets.
- `news_vs_nonews_drop_reversal` (refuted, h20260929_20): event study of >=5% one-day drops at 1-5 session holds in ADV top 1500 / 1000, using news_packets headlines. This book is a daily cross-sectional rank book on all names; the no-news condition here only filters the cross-section (names with a news_attention row and news_count_1d = 0), and is one of four conditions. Not the same estimator; any overlap is disclosed in the report.
- `no_news_price_shock_reversal_chan` (harvested, monthly horizon): not tested here.
- `etf_constituent_lead_lag_reversion`, `letf_close_rebalancing_flow_reversal` (refuted): ETF-level mechanisms; not reopened.
- `deep_learning_stat_arb_residual` (not executable then): this dossier is the "dedicated residual/PCA engine with realistic turnover-cost accounting" its reopen_if asks for, with ridge/LightGBM instead of a transformer.
- `t20261005_p1_s0_decay` (P1 Stage 0, measurement of fast-signal IC decay and speed; no results at the time of writing): covers REV5/IREV5/RREV5/RREV21 as 4 of 10 objects at partial-trading speeds in U3000. This dossier is a full strategy test of the residual-reversal family (3 residual methods, 3 universes, holds as overlapping batches, models); results of the two are not pooled and the program trial count disclosure is in section 9.

## 1. Data (all from existing stores; nothing new is bought or downloaded)

- Prices: `data/research/equity_book/prices/<year>.parquet` and `etf_daily.parquet` via `panel.PricePanel` (hygiene applied, manifest 2026-10-01T06:48Z, sessions 2016-01-04..2026-09-30).
- Attributes: `data/research/equity_book/panel/<year>.parquet` (`adv_rank`, `dollar_adv_21`, `mcap`, `mcap_source`, `ff48`, `beta_252_spy`, `vol_21`, `idio_vol_63`, `is_tradeable`). All attributes at close t are known at close t.
- News: `data/features/news_attention/<year>.parquet` (2024-2026 only; about 776 of about 2,221 top-3000 names have a row on a typical 2025 day, 68% of rows have news_count_1d = 0). VIX: `regimes/market_state.parquet` / FRED VIXCLS as `book_v12`/`realism_ladder` load it.
- Windows: recent (decides) 2024-01-08..2026-09-15; diagnostic 2017-10-02..2023-08-31 (crash veto V4 and phase diagnostics only; signals warm up from 2016-01); forward holdout 2026-09-16..2026-09-30 (11 sessions), computed once at the end for the promoted variants, never used to select, reported as "too short to test". Phases: `regimes/phases.json` phases_recent.
- Survivorship: the panel keeps delisted names (prices end at the last valid close); the engine's delisting rule applies (no haircut in the main run; -30% long haircut as a sensitivity on the promoted variants).

## 2. Universe

Top N by `adv_rank` at the signal close t (N = 500, 1000, 3000), `is_tradeable`, finite close at t. `adv_rank` and `dollar_adv_21` at t use only data through t.

## 3. Residual returns (daily, close to close)

Let r_i,t be the daily close-to-close return.
- `beta`: e = r_i,t - beta_i,t-1 * r_SPY,t with beta = panel `beta_252_spy` at t-1 (NaN -> 1, clipped to [-0.5, 3]).
- `ind`: e = r_i,t - mean of r_j,t over names j in the same FF48 group that are in the top-3000 universe on t (groups with fewer than 5 names use the cross-sectional mean of the top-3000 universe).
- `pca`: loadings from the top 10 principal components of the correlation matrix of the last 252 sessions of daily returns of the top-4000 `adv_rank` names with at least 200 valid returns in the window, re-estimated every 21 sessions at the close of the refresh session and used from the next session on. e_i,t = vol_i * (z_i,t - sum_k b_ik f_k,t), z = r / vol (vol = std of the window), f_k,t = cross-sectional OLS of z_t on the loadings. Names not in the PCA set on a day have no residual that day.

Reversal signal S_L,i,t = - sum of e over the last L sessions (L = 1, 5, 10, 21; for L = 10 and 21 at least ceil(0.8 L) valid days, scaled by L/count; for L = 1 and 5 all days). High S = buy.

## 4. Conditions (applied inside the universe before ranking)

- `none`.
- `lowturn`: keep names with dollar_adv_21 / mcap below the cross-sectional median among universe names with `mcap_source == "sec"` that day (names with an ADV-fallback market cap are dropped; turnover is a proxy for share turnover, Medhat-Schmeling).
- `nonews`: keep names that have a news_attention row on day t with news_count_1d = 0 (names with no row are uncovered, not "no news", and are dropped). Only defined from 2024-01-02, so evaluated in the recent window only; no diagnostic-window number exists for it.
- `vixscale`: all names, but the gross of the single-day book is multiplied by s_t = clip(VIX_t / median(VIX over the last 252 sessions), 0.5, 1.8) (Nagel 2012: reversal returns rise with VIX). VIX_t is the VIXCLS close of t, forward filled at most as in `realism_ladder_book_ls`.

## 5. Single-day book at close t

Per-side gross G_t = 0.5 * s_t (s_t = 1 except `vixscale`). Long candidates: the top quintile of S (the biggest recent residual losers) in the conditioned universe. Short candidates: the same quintile rule applied only to the short-eligible subset (`borrow.short_eligible` v1: adv_rank <= 2000, price >= 10, no reverse split in 252 sessions; the short-interest clause is skipped because no point-in-time short-interest column is in the panel). Within each side weights are proportional to the rank from the quintile boundary (1 at the boundary, n at the extreme), normalised to G_t per side, then each name is capped at 0.5% of equity (no renormalisation: the realised gross is reported). SPY hedge = - sum_i w_i beta_i (beta as in `beta` above). Remaining equity in the T-bill sleeve (SGOV/BIL) so excess return = book spread.

## 6. Holding period H (1, 5, 10)

Target book at close t = mean of the single-day books of t, t-1, ..., t-H+1 (H overlapping batches, each 1/H of the book). A name's weights net across batches; the engine trades only the net.

## 7. Execution

Decision at close t, trade at open t+1 (`open`, cost snapshot open) or at close t+1 (`close`, cost snapshot close), through `backtest.run_book` (`BookConfig(freq="D", exec_price=...)`), initial equity 300,000 USD (the planned quant1 sub-account; the cost model's impact term scales with it).

## 8. Costs (all through `costfn.make_cost_fn`, cost_model_v1)

Half spread by price / ADV / volatility / year per side, square-root impact at the actual trade dollars, 0.5 bp fees per side (covers the SEC sell fee, about 0.2 bp on sells at the current rate; documented, not separately added), borrow 25 bp per year on short notional (stress 100 bp), margin interest 6.5% on any debit. Reported at 0.5x, 1x, 2x of all cost components (components are scaled in the daily series after the run: net_k = gross - k * costs). Capacity: per trade, trade dollars / dollar_adv_21; the share of traded dollars above 1% of ADV and the median are reported.

## 9. Trial grid (every cell counts toward the trial total, with `trial-grid.json` as the machine-readable list)

- Rule cells: 3 universes x 4 L x 3 residuals x 4 conditions x 3 H x 2 executions = 864.
- Model cells: 2 models (ridge, LightGBM) x 3 universes x 3 H x 2 executions = 36 (section 10).
- Total N = 900 for the DSR family. N_eff = 1 + (N-1)(1 - rho_bar) with rho_bar the mean pairwise correlation of the daily net returns of all variants in the recent window (computed after Stage A, by the scorecard code). Program disclosure: the P1 Stage-0 dossier registers 70 configurations; this dossier adds 900; the two share the REV5/RREV5 objects but different engines, so they are disclosed, not merged.
- The 15 candidates in the manifest group the cells: 9 rule families (residual x universe) and 6 model families (model x universe); the grid inside a family is listed in the candidate's `parameters` and in `trial-grid.json`.

## 10. Model variants

Ridge and LightGBM predict the forward H-session open-to-open return from t+1 (`returns.forward_open_to_open`) minus beta * SPY's same-period return, winsorised at the 1st/99th percentile per date and demeaned per date. Features at close t, each rank-normalised per date: residual sums (pca) over 1, 5, 10, 21 sessions, `ind` residual over 5, raw returns over 1, 5, 21, overnight mean and intraday mean over the last 5 sessions (`signals.overnight_matrix`), log dollar ADV, ADV/mcap, vol_21, idio_vol_63, beta, FF48 code (LightGBM only), news_count_1d and attention_surge_5d (NaN before 2024; ridge adds a missing indicator and fills 0). Training: expanding window, refit every calendar year (first prediction year 2018, trained on 2017-01 .. previous year end minus H+1 sessions to purge label overlap), at most 1.5 million rows per fit by a fixed-seed random subsample of dates. Ridge alpha = 1.0 on rank-normalised features (no tuning). LightGBM: 200 trees, 31 leaves, learning rate 0.05, min_child_samples 200, feature fraction 0.8, bagging 0.8, seed 20261006, no tuning. Prediction -> score -> sections 5-8 identical to the rules (rank-weighted quintiles, H batches). The model-over-rule contribution test is the standard's section 7: same universe, H and execution, rule `pca`/L=5/`none` versus the model.

## 11. Scoring, stages and selection (fixed)

Stage A: all 900 cells on the recent window with the full engine. Reported per cell: gross, cost components, net, annualised Sharpe vs BIL, vol, max drawdown, turnover, avg gross exposures, trade count, ADV participation, return correlation with the existing stock long-short book (the v1.2 book's daily series from `data/research/book_v12`, or if unavailable, the 9-theme M0 composite from `regimes/signal_ls_daily.parquet`, named in the report), split by market-cap tercile of traded names, and by recent phase.
Stage B: the 30 cells with the highest recent net Sharpe at 1x cost, plus the 18 canonical cells (L = 5, H = 5, `none`, all residuals, all universes, both executions), run on the diagnostic window and on 2016-2026 full for the crash veto V4 and the stress report; for the top 3 net-Sharpe cells in the recent window: 100-seed placebo (net and gross definitions of standard section 3), the six robustness checks, the scorecard tier. Selection of the top 3 is by recent net Sharpe at 1x cost among cells that pass V2 whole-share feasibility at 300,000 USD and V3; this rule is fixed here.
Tier: `scorecard_v2.score_family` with N = 900 trials and N_eff from the measured correlation; P1 needs DSR >= 0.70, net placebo >= 0.90, robustness >= 3, no veto.
Offsets: a daily-rebalanced H-batch book has no calendar offset; robustness check d (5 offsets) is computed on five sub-books, each trading batches that start on a different weekday phase (batch day of the week), reported as is.

## 12. Power (computed by code in `power.json`)

With D = 685 recent sessions (2.72 years): minimum detectable annual Sharpe at one-sided 5% size and 80% power for a single test is 1.51 (z = 2.485 / sqrt(years)); with Bonferroni over 900 cells the same power needs about 2.5; with the DSR's expected-maximum null for N_eff the DSR >= 0.70 line is the operative bar. The number of independent daily bets is about 2 x quintile size x (1/H overlap factor): U500 about 200, U1000 about 400, U3000 about 1,200 names traded per day. A Sharpe of 1.0 is therefore not detectable at the family level in this window; the verdict categories are:
- positive result: tier P1 or higher by the scorecard;
- negative ("not viable"): requires all five of the owner's 2026-10-04 conditions: (1) the published result reproduced (see 13), (2) faithful implementation (identity checks of section 13), (3) scale curve with at least three depth points along universe, lookback and holding period (the grid has three or four of each), (4) the preregistered budget fully used (all 900 cells), (5) power adequate (best-case cell's upper 95% bound for Sharpe vs the 1.19 K1-like bar, using the Lo standard error, below the bar);
- otherwise "not at depth", stating which condition is missing and how to supply it.

## 13. Identity and reproduction checks (before reading any net result)

- Convention identity: for `beta` L=1 H=1 `none` U1000 `open`, the engine's gross daily series equals an independent numpy computation (weights x open-to-open next-session returns) to 1e-9 on 20 random sessions; failing this stops the run.
- Held-position identity: `compound_legs` over H sessions equals the labels used by the models (existing tested identity, re-run once).
- No-lookahead: the signal at close t uses only prices through close t; the PCA loadings for session t use returns through the last refresh session <= t-1 (tested by recomputing two sessions with the future truncated).
- Reproduction anchor (diagnostic, not a gate): gross L/S Sharpe of `ind` L=1 H=1 U1000 in 2017-2018 versus 2019-2023 versus recent, to be compared with the published decay pattern (0.90 in-sample to 0.23 out-of-sample, gross, equity-statarb repo) and the sign and size of Avellaneda-Lee's pre-/post-2003 drop.

## 14. Stop conditions and use limits

- Stage A is the cheapest decisive test of the whole family: if every cell has recent gross Sharpe below 0.3 before costs, Stage B is skipped except for the canonical set, and the report states the family is not viable at this depth.
- Compute: local (one heavy job at a time under `flock /tmp/oc-heavy.lock`, 1.2 GB cap). Modal only if Stage A cannot finish in 30 hours locally; budget cap 4 USD, `modal_budget.py check` first. The 48-hour limit of the brief ends 2026-10-08 23:00 UTC; the first batch (L=5, H=5, three universes, rule versions) is due in report.md by 2026-10-07 23:00 UTC.
- Nothing here places orders or touches broker authorisation, crontab, the queue or the direction registry.
- The pre-registered grid and pass standard are not changed after results; deviations (bugs found later) are appended as dated amendments with the effect stated.

## 15. Addendum 1 (written 2026-10-06T23:25Z, before any return of this book was computed; implementation details only, no grid or standard changed)

- PCA estimation: the 252-session window returns are winsorised at each name's 1st/99th percentile for the covariance/SVD step only; residuals are computed from the unwinsorised returns. The correlation matrix is of per-name standardised (demeaned, divided by std) returns; the cross-sectional regression regresses z = r / sigma (sigma = window std) on the loadings over the names with a valid return that day.
- Returns are close-to-close; a return is NaN if either close is missing (a hole is not bridged). The price hygiene mask of the panel (manifest 2026-10-01) is used as is.
- Short eligibility proxy is computed with `borrow.detect_reverse_splits` on the same prices (adv_rank and price from the panel at t).
- The backtest symbol set is every name that is in the adv_rank <= 3000 universe on any session plus the hedge ETFs (6,046 names + ETFs); the PCA set is every name with adv_rank <= 4000 at a refresh session.
- Trade attributes for the cost model (dollar_adv_21, vol_21, prior close) come from the same panel at the decision close, exactly as `PanelAttributes.trade_attrs`; they are read from a memory-mapped copy to stay under the 1.2 GB cap.
- Stage A runs start with the book flat at 2024-01-08 (first signal close 2024-01-05, first trade 2024-01-08 for H overlap warm-up: the H batches of the sessions before 2024-01-08 are included so the book is fully invested from the first trade); the daily series is judged from 2024-01-08.

## 16. Addendum 2 (written 2026-10-06T23:43Z; supersedes sections 4, 9, 10, 11 and the book of section 5 where they conflict; follows the coordinator's additional instruction 1 of 2026-10-06 23:32 UTC and review R1006-V3)

State when written: the contract of sections 0-15 had been frozen and validated at 2026-10-06T23:23Z. No backtest of this book had been run: the feature-store build job never started (it was queued behind another heavy job and was killed before running), `data/research/t22_streversal/` did not exist, and no residual, IC, return or Sharpe of any variant had been computed. This addendum therefore changes the contract before any result, and the earlier 900-cell grid is withdrawn (the 900-cell `trial-grid.json` of 23:23Z is replaced; its hash stays in `prebacktest-validated-at.txt` history for audit).

1. **Main grid, 24 trading variants** (this is the DSR family; N = 24, the variance of Sharpe across these 24): universe top 500 / 1000 / 3000 by adv_rank x residual {ind, pca} x lookback L {5, 21} x holding H {1, 5}, execution at the open of t+1 only, condition `none`. Residual `beta` is dropped from the main grid (the industry residual already contains the market), L = 1 and 10 are dropped (literature: 5-day and 1-month are the standard horizons).
2. **Robustness cells (4), on the selected spec only, counted separately, not used to select**: condition `lowturn`, condition `nonews`, condition `vixscale`, and execution at the close of t+1. **Second-stage model cells (2)**: ridge and LightGBM on the selected universe and H. Total registered cells = 24 + 4 + 2 = 30; all 30 enter the global trial ledger; the DSR uses the 24 main cells.
3. **Spec selection rule (standard 5b item 6)**: among the 24 main cells, rank by recent net Sharpe at 1x cost; take the three highest and use the **middle-ranked** of the three (second highest) as the selected spec, not the highest.
4. **Book for a 300,000 USD sub-account** (replaces the rank-weighted quintiles): per side N = 100 names: long the 100 highest S in the candidate set, short the 100 lowest S among short-eligible candidates (N = 100 is fixed; with H = 5 the net book holds up to 500 names per side). Equal weights within a side, per-side gross 0.5 of equity (= 150,000 USD per side, 1,500 USD = 0.5% of equity per name per batch, so the 0.5% single-name cap is met without clipping), SPY hedge as in section 5. Candidates must have a close between 5 and 750 USD on t (a 1,500 USD slot then holds at least 2 shares); shorts additionally need the easy-to-borrow proxy. Net target weights below 100 USD (the engine's minimum notional) are dropped before trading. Whole-share feasibility (standard V2) is checked on the selected spec's target books on at least 20 sampled sessions with rounded share counts at 300,000 USD: realised short exposure / target >= 0.90, relative L1 error <= 30%, net dollar deviation <= 5% of equity, and the median ADV participation <= 1%.
5. **PCA without look-ahead**: the loadings used for session t are estimated only from returns through the last refresh session p <= t-1 (252-session window ending at p, refresh every 21 sessions, so the loadings are at most 21 sessions old), the regression of day t uses only the day-t cross-section; nothing is chunked by calendar year or uses data after t-1 (the build iterates refresh by refresh from 2016 forward). A test recomputes two sessions with the data after t-1 removed and requires identical residuals.
6. **News condition**: only the `news_attention` row of day t whose `visible_at` (09:30 ET on the trade date) is at or before the decision time is used; the feature covers news visible by the open of t, not news published later on day t, so `nonews` means "no visible news by the open of t" (disclosed weakness, robustness only).
7. **Borrow**: `borrow.py` does not use a historical Alpaca easy-to-borrow list (none exists); it is a point-in-time proxy rule (adv_rank <= 2000, price >= 10, no reverse split in 252 sessions) calibrated once against the 2026-10-01 Alpaca flags (precision 0.985, recall 0.67, 20 false positives of 1,374 in 2026-09; report `borrow-proxy-v1-2026-10-01`). Applying it to 2017-2025 assumes borrow status is as stable as in 2026, so the historical short availability is an assumption, not a record. Conservative handling: borrow carry 25 bp a year in the base case and 100 bp in the stress case, plus one more stress run on the selected spec with shorts restricted to adv_rank <= 1000 (precision 0.993 in the calibration; short interest is not in the panel, so the rule's short-interest clause is skipped).
8. **Open execution cost**: the `open` snapshot of cost_model_v1 (median quotes 09:35-09:45 ET; year effects 2025 +0.67 and 2026 +0.80 in log half spread) is used for t+1 open fills; the report states the realised average half spread in bp by liquidity bucket for the traded names and compares it with the 9-40 bp opening range cited in the coordinator's instruction. Missing inputs cost 40 bp.
9. **Judgement**: tier by P1 and `docs/evaluation-standard.zh.md` section 5b / 5; section 12's verdict categories stay, with the depth conditions applied to the 24-cell grid; the stop rule of section 14 (recent gross Sharpe below 0.3 everywhere) still applies. Section 11's Stage B now means: diagnostic window and V4 for all 24 main cells; placebo (100 seeds, net and gross, section 3 of the standard), six robustness checks and the scorecard for the selected spec; the five robustness/model cells run on the selected spec after selection.
10. **Compute**: heavy commands only through `scripts/heavy_run.sh --mem 0.8G -- ...` (quiet window 18:00-00:45 UTC, one heavy job, resumable); build, PCA and model fits go to Modal first if local memory stays short (cap 4 USD, `modal_budget.py check` first). The ML stage waits for the main grid. Launch into the paper account is not scheduled by this task; a passing spec is handed to the coordinator, who sets the date after the quant1 sub-ledger isolation (v1.2 planning against its own sub-ledger) is done.

## 17. Addendum 3 (written 2026-10-07T01:15Z, AFTER the main grid, the robustness cells, the placebo and the two model cells were run; exploratory, not used for the verdict, the tier or the DSR)

What was known when this was written: all 24 main cells had negative recent net Sharpe (best -0.28, the selected spec R_U500_ind_L21_none_H5_open at -0.54); LightGBM on U500 H5 had recent gross Sharpe 1.37 and net -0.09 (net +0.64 at 0.5x cost), ridge gross 0.97 and net -0.26; the selected rule spec's placebo percentile was 0.53 net / 0.54 gross. The pre-registered verdict is not changed by anything below.

Exploratory cells, run once, no tuning, all counted in the trial ledger as exploratory (total 5), each reported next to the registered ones and labelled post hoc:
- E1a, E1b: the already trained ridge and LightGBM scores (U500, H5) traded at the close of t+1 (cost snapshot close) instead of the open.
- E2a, E2b: LightGBM with the same features, training rule and parameters on U1000 and U3000 (H5, open of t+1), to give the model family a three-point universe curve.
- E3: LightGBM on U500 with H = 10 (open of t+1), a second holding point.
Reading rule: a cell that looks good here is a hypothesis for a new preregistered contract, never a pass. The model-over-rule contribution is computed as the Newey-West t of the daily net-return difference between LightGBM and the selected rule spec on the recent window (standard section 7), reported, with N = 24 + 2 for the DSR of the model cells.
