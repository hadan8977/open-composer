# Preregistration: equity book v1 construction post-mortem (T-20261001-19)

Written 2026-10-01 18:02 UTC by the executor of T-20261001-19 (coordinator code R1001-1755-T19), before any ladder number exists. The brief is `reports/research/control/briefs/T-20261001-19.md`. Nothing below is changed after a result is seen; a change would be a new, dated amendment file.

State at the time of writing: the L1, L2c and L2a paths have not been run. The only new computation is the identity check (`identity-check.json`), which reproduces an existing path: the new runner with the default style cap and close fills equals the v1 runner's `M0_A_o0_close` over 2024-01-02..2024-03-28 (61 sessions, last session before the 03-29 holiday), max abs difference of daily `net` 0.0 (threshold 1e-12), and the targets frames are identical. Also read before writing: the M0 signal reference convention reproduces the lead's quoted 1.68 (A) and 3.06 (B) with the raw mean/std convention below (1.676, 3.058). Those are existing numbers, not new results.

## 1. Sources (Part 0)

`reports/research/intel/sources/book-construction-2026-10-01/INDEX.md`. Facts that shape this design:
- Four primary journal papers (Lee-Stefek 2008, Ceria et al. 2012, Saxena-Stubbs 2013, Clarke et al. 2002) are paywalled and were NOT read; open secondary texts were read instead (MSCI 2012, Beheshti 2018, Durin 2014, Ding 2010, CFA Digest of Clarke et al. 2004). The literature claim "risk models make the optimizer over-bet residual alpha; aligning risk and alpha may help" is about the risk model, not about hard style caps; no source quantifies alpha lost to style caps. D1 therefore tests our own book; the literature does not predict its sign.
- Transfer coefficient (Clarke, de Silva & Thorley 2002, as quoted by Ding 2010, eq. 59): cross-sectional correlation of residual-volatility-adjusted active weights with alpha/residual volatility. Section 5 uses that form as the risk-adjusted TC.
- Opening versus closing auctions (Goyal, Jegadeesh & Wu, JFQA 2026, NYSE/Nasdaq 2012-2021): closing-auction price impact is lower than continuous trading except for Nasdaq microcaps; opening-auction impact is "much larger" than closing (qualitative; no bp table extracted).
- Alpaca: OPG orders submitted between 9:28 and 19:00 ET are rejected (queued after 19:00); CLS orders after 15:50 ET are rejected. Alpaca staff (forum, 2024) say paper OPG/CLS orders fill like market orders at the quote, not at the auction price. So a D2 pass says the opening fill is better in the cost model; it does not say paper will show it (paper opening fills must be measured before relying on them).

## 2. Configurations

Variants M0_A and M1_C (T-08 method/universe definitions, `scripts/run_book_v1_stage2.py`), rebalance offsets 0-4, weekly, window 2017-10-02..2026-09-17, initial T-bill 1.0, equity 1,000,000, whole-share and other mechanics unchanged. Paths `PM_{L1|L2c|L2a}_{M0_A|M1_C}_o{k}`.

| rung | style_cap | order fill | optimiser cost snapshot (`OptConfig.snapshot`) | realised cost snapshot |
|---|---|---|---|---|
| L0 | 0.25 (size 0.10) | close | close | close (T-08 `*_close` paths, reused, not re-run) |
| L1 | None (size keeps 0.10) | close | close | close |
| L2c | None | open | open | open (conservative; same mechanics as T-08 `*_open`) |
| L2a | None | open | close | close (optimistic bound for an opening-auction fill) |

Unchanged in all rungs: beta_cap 0.02 (ewma), industry cap 0.01, name cap 1%, ex-ante vol 5%, gross 1.0, size cap 0.10, participation 1%, borrow 25 bp, IC window logic, solver and retry ladder. L2a is built with `book_config(exec_price="open")` then `dataclasses.replace(cfg, cost_fn=make_cost_fn(snapshot_for("close")))` and `OptConfig(snapshot="close")`; no bound file is edited. Code: `scripts/run_book_postmortem.py`, which imports `Context`, `AlphaSource` and helpers from `scripts/run_book_v1_stage2.py` (not edited).

Trial accounting: three new rungs x two variants = six new trials; program total 89 (77 + 6 RF1 + 6 here) for any future DSR. The offsets are not trials.

## 3. Windows and statistics

- A 2024-01-08..2026-06-30; B 2026-07-01..2026-09-17; stress 2017-10-02..2023-08-31; anchor 2024-01-08..2026-09-17.
- Per path and window: net Sharpe = min(plain, cash-aligned) where cash-aligned is `net - BIL + SHY` (`eval_book_rf1.min_stat`); gross Sharpe from `daily.gross`, plain excess over BIL; annualised net excess (same min rule); realised vol, max drawdown and OLS beta on SPY (plain net); Dimson beta (`dimson_beta`); one-sided annualised turnover; costs in bp per year by component (`cost_spread, cost_impact, cost_fees, cost_borrow, cost_margin` from `daily`); style exposure from `records.exposures_target`: signed mean, mean absolute and the share of rebalances with |exposure| >= reference cap - 1e-4, where the reference cap is the L0 cap (0.10 size, 0.25 other styles; in L1/L2 rungs this is a descriptive threshold, not an active constraint, except size).
- Every per-window statistic is first computed per offset, then the median over the 5 offsets is reported. All functions are `window_metrics` and the `eval_book_rf1` / `eval_book_v1_stage2` helpers, imported.
- M0 signal reference: `data/research/equity_book/regimes/signal_ls_daily.parquet`, column `m0_composite`, Sharpe = mean/std x sqrt(252) of the raw daily series (no risk-free subtraction; the series ends 2026-09-15), windows A, B, stress, anchor.

## 4. Decision rules (mechanical, per variant; D = both variants)

Write `X(L, v, w)` for the median-over-offsets net (or gross) Sharpe of rung L, variant v, window w.
- **D1 (style alignment).** For both v in {M0_A, M1_C}: gross(L1,v,A) - gross(L0,v,A) >= +0.30 AND gross(L1,v,stress) - gross(L0,v,stress) >= -0.30. If true, the candidate v1.1 change is: replace the caps on alpha-aligned styles by a risk budget.
- **D2 (execution).** For both v: net(L2c,v,A) - net(L1,v,A) >= +0.15 AND net(L2c,v,stress) - net(L1,v,stress) >= 0. If true, the candidate change is: execute in the opening auction. If D2 is false but D2a (the same with L2a in place of L2c) is true for both v, the candidate is: measure opening-auction costs on paper first. Given Alpaca's quote-based paper simulation of OPG (section 1), a D2 pass is a model result, not a paper result.
- **D3 (costs).** For each v: cost drag = gross(L1,v,A) - net(L1,v,A) > 0.30. D3 is true if it holds for both v (both values are reported). If true: record "v1.1 needs a slower rebalance or a stronger cost penalty" as a candidate change, not a decision.
- Boolean outcomes only; no verdict wording in the report. The lead decides v1.1.

## 5. Transfer coefficient (L0 and L1, both variants, offsets 0-4, every rebalance)

At each decision date t (every row of `targets.parquet`, i.e. every successful rebalance) rebuild the alpha with the same `AlphaSource` call used by the runner (M0: equal-weight composite; M1: the monthly reweighting, one source per path so its monthly update dates match the path) over the universe `attrs.at(t)[universe column] ∩ risk-model names`. TC = Pearson correlation over the names with a finite score between the target stock weight (names not held = 0; hedge ETFs, T-bill ETFs and `TBILL` excluded) and the rank-normal score. Risk-adjusted TC = Pearson correlation between `w_i * sigma_i` and the score, sigma_i = sqrt of the risk model's specific variance (Clarke et al. form with residual volatility; alpha_i / sigma_i = IC x score_i). Reported: median over all rebalances of all five offsets pooled, per window (A, B, stress, anchor), per rung and variant. The raw per-rebalance rows are saved (`tc_rebalances.parquet`, uncommitted).

## 6. P&L attribution (L0 and L1, both variants, offset-blended)

Per path, daily: holdings are rebuilt from `targets.parquet` (target weight x `daily.equity` at the decision close, because L0 and L1 fill at the close), drifted with close-to-close stock returns from the price panel (NaN return = 0), and the day's contribution of each name is its start-of-day weight (fraction of the previous close equity) times its return. Stock-book return = market + industry + 9 styles + specific, where for day t the factor part is sum_k (sum_i w_i x_ik) f_kt using the exposures of the latest saved risk-model date strictly before t (the model saves Fridays and month-ends; never a later date) and the model's daily factor returns f_kt for t; specific = stock-book return - factor part (names without an exposure row are all specific). Separately: ETF-hedge leg (hedge ETFs held, close-to-close), T-bill leg (previous-day `tbill_exp` x BIL return), costs (minus the five cost columns), and an "unreconciled" line = reported `gross` - (stock + ETF + T-bill legs), which absorbs delisting handling, halted names and equity-timing differences and is reported, not hidden. Components are averaged over the 5 offsets day by day (blended), then per window the annualised contribution (mean x 252) and the Sharpe (mean/std x sqrt 252) of each component are reported. The top components by A-window contribution are read from that table by absolute size.

## 7. Compute and outputs

Modal: 30 paths as 30 shards, 1 CPU, 4 GiB, `--timeout-min 20`, `python3 scripts/modal_budget.py check --job book-postmortem --cpu 1 --memory-gib 4 --timeout-min 20 --count 30` must exit 0, cap USD 2; exit 2 stops the Modal part and is reported. Raw outputs in `postmortem/cache/` (uncommitted); `run-manifest.json` records sha256, rows and first/last dates. Analysis and report: `scripts/eval_book_postmortem.py`, `postmortem/results.json`, `postmortem/report.md` (Chinese, facts and the D1-D3 booleans only, ends with "v1.1 设计由主审决定"). One number is independently recomputed and shown to match `results.json` to 1e-9.

If a path fails or times out it is re-run once (budget check first); a path that still fails is reported as missing and the medians are over the remaining offsets, said explicitly.
