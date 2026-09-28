# I-20260928-02: Modal-lane intel — multi-source cross-sectional ranking model vs. chart-image CNN

Task: T-20260928-09. Research and preregistration-drafting only — no backtests, no training, no Modal runs, no code. Both directions were parked/deferred for **compute reasons**, not refuted; Modal cloud compute (~$6/direction) is now available and the owner set an explicit "spend as little Modal budget as possible" constraint mid-round: every prereg below is staged into a ≤$1 kill test and a ≤$3 full evaluation, with the full stage gated on the kill test's preset threshold.

**Method note** (same discipline as `I-20260923-09`): **verified-live** = a primary page/PDF/repo I opened directly this session. **search-summary** = only a search-engine snippet/synthesis, page not opened. **abstract-only** = an abstract/landing page opened, full text not read. Rows carried over from `I-20260923-09` (accessed 2026-09-23) are marked as such; this round did not re-open those PDFs (they were already confirmed undecodable there — Gu-Kelly-Xiu 2020, Chen-Pelger-Zhu 2024, Jiang-Kelly-Xiu 2023 original PDFs all return FlateDecode streams our fetch tool can't parse).

**Owner decisions applied mid-round (2026-09-28, superseding the original brief's framing)**:
1. **Direction A is GO.** Illiquid/small-cap US common stocks are acceptable to trade in this personal account; the universe is widened from "top ~1000 by dollar volume" to **all Alpaca-tradable US common stocks, price ≥ $3, 21-day dollar-ADV ≥ $1M**, with results also split by liquidity tercile. The literature's "ML edge concentrated in small/illiquid names" finding (section A.1) now argues *for* this universe rather than against it; the Avramov-Cheng-Metzker-style cost/turnover caution becomes the main risk, addressed with a real spread-cost model, a position cap, and slower rebalancing as preregistered variants (not post-hoc).
2. **Direction B is deprioritized, not refuted.** Registry status `parked`, verdict "owner deprioritized 2026-09-28; evidence summary kept." No preregistration is drafted for it.
3. Modal budget for A stays staged: kill test ≤$1, full ≤$3.

---

## Direction A — multi-source cross-sectional ranking model (GBDT / LambdaRank)

### A.1 Evidence table

| # | Source | Date read | Sample / universe / weighting | Costs | Result | Status |
|---|---|---|---|---|---|---|
| 1 | Gu, Kelly, Xiu (2020), *Empirical Asset Pricing via Machine Learning*, RFS 33(5); NBER w25398 | 2026-09-23 (carried over) | US individual stocks 1957-2016, ~920 features via interactions, decile long-short | Not reported (gross) | Trees/NNs "double" leading linear Sharpes; **dominant signals are momentum/liquidity/volatility variants, not new information** | search-summary — primary PDF undecodable both sessions |
| 2 | Qlib official benchmark README, microsoft/qlib | 2026-09-23 (carried over) | CSI300/CSI500, China A-shares, Alpha158 engineered factors | Backtested with Qlib's default cost model | LightGBM IC 0.0448/ICIR 0.366/AR 9.0%; DoubleEnsemble IC 0.0521/ICIR 0.422/AR 11.6%; trees beat deep nets on **engineered-factor** input, lose to deep nets on **raw-sequence** input (Alpha360) | verified-live |
| 3 | Grinsztajn et al. (NeurIPS 2022 D&B), tree-vs-DL on tabular data | 2026-09-23 (carried over) | 45 general tabular datasets, non-finance | n/a | Trees remain SOTA at medium size (~10k rows); gap persists after tuning | search-summary, heavily-cited consensus |
| 4 | TabReD/TabArena, time-based (walk-forward-style) tabular splits | 2026-09-23 (carried over) | General tabular, time-ordered splits | n/a | Under realistic (non-IID) splits GBDT stays the robust default; attention architectures degrade faster under drift | search-summary |
| 5 | H-20260917-02 (this repo), ridge on 29-factor price-volume+insider set | 2026-09-28 (repo-local) | US broad universe, 2016-2026, monthly, top/bottom decile of ~100 names | 10bp/side, next-open fill | Mean validation RankIC **0.0071** across 37 folds; top-decile book loses to momentum-twin and same-size random draw on Sharpe | verified-live (own report) |
| 6 | `dir:lightgbm_price_volume_recipe_v1_closed` (this repo) | 2026-09-28 (repo-local) | Same price-volume feature set, 60 trials | 10bp/side | Every ML unit (regression, ranking, meta-labeling) lost to the rule twin; family closed absent a new data layer | verified-live (own registry) |
| 7 | `dir:sec_xbrl_accounting_signals_v1` (this repo) | 2026-09-28 (repo-local) | US top-3000 PIT, XBRL fundamentals | 20bp | ROE alone: IC 0.026, t 3.0 (2024+: IC 0.021); gross profitability marginal (IC 0.019, t 2.2); asset growth/accruals rejected | verified-live (own registry) |
| 8 | `dir:composite_momentum_roe_v2` (this repo) | 2026-09-28 (repo-local) | US top-500-ish, 12-1 momentum + ROE, equal-weight linear composite | 20bp | Linear combination makes the book **more defensive, not better**: Sharpe 0.73 vs momentum-alone 0.82, in 2024-2026 trails badly by year | verified-live (own registry) |
| 9 | `dir:osap_ml_ranking` (this repo) | 2026-09-23 (carried over) | OSAP (openassetpricing.com) characteristics, GKX-style | n/a | Literature long-only top-decile ~15-25%/yr; **blocked locally on permno-to-ticker crosswalk** | parked, evidence not independently reverified this round |
| 10 | Qlib US-region path, GitHub issue tracker | 2026-09-23 (carried over, not re-checked this session) | Qlib's own US benchmark | n/a | Prior brief (2026-09-18) found an open, unfixed bug (Issue #1428); no independently published third-party US benchmark exists | search-summary, not re-verified 2026-09-28 |
| 11 | Avramov, Cheng, Metzker — "machine learning vs. economic restrictions" style caution (name only, cited by `dir:ml_ranking_broad_universe_custom`'s own verdict) | 2026-09-22 (carried over via registry citation, not independently opened) | ML factor predictability studies, cross-market | n/a | ML-driven return predictability concentrates in small, illiquid, high-cost-to-trade stocks and shrinks sharply after realistic transaction costs and short-sale constraints | **not independently verified this round** — registry cites the caution but nobody has opened the actual paper; flagged as a real gap |
| 12 | Chen, Pelger, Zhu (2024), *Deep Learning in Asset Pricing*, Management Science / arXiv 1904.00745 | 2026-09-23 (carried over) | US stocks, conditional autoencoder + SDF loss | n/a | Out-of-sample Sharpe ≈ 2.1 (headline); feeding all 178 macro series without dimension reduction **collapsed** performance | search-summary, PDF undecodable both sessions |

**Open gap, stated plainly**: item 11 (Avramov-Cheng-Metzker) is the single most load-bearing citation for this direction's main risk (cost/liquidity concentration of the ML edge) and it has never actually been opened locally — only cited secondhand through our own registry's prior verdict. A parallel web-research pass was launched this round specifically to open it and to check GKX/CPZ broken down by size/weighting/after-cost/post-2018, an OSAP ticker-crosswalk fix, and any 2023-2026 live ML long-only large-cap record; it was still running when the owner's GO decision landed and this brief was finalized without waiting on it, per instruction. **If it returns material new evidence, treat this brief's A.1 table as provisional and re-run `oc research directions check` before committing further compute.**

### A.2 What is new vs. our local failures

- Local units 1-8 above all tested **one data layer at a time** (price-volume alone: refuted; price-volume+insider in one flat feature vector but still linear/near-linear ridge: RankIC ~0; fundamentals alone: partial — only ROE survives; linear/equal-weight composites of momentum+fundamentals/insider: refuted, worse than momentum alone). **Nobody has trained a genuinely non-linear model (GBDT/LambdaRank) on all layers combined** (price-volume + XBRL fundamentals + Form-4 insider + FINRA short interest/volume + earnings-date event features) in one objective. That is the actual gap `dir:ml_ranking_broad_universe_custom` and `dir:qlib_lightgbm_doubleensemble_recipe` were deferred on in 2026-09-22, pending compute — now available via Modal.
- The universe widening (owner decision) is itself new relative to every prior local ML attempt, which ran on top-500/top-3000/broad-but-still-somewhat-liquid pools. If the ML edge is genuinely concentrated in the illiquid tail (item 11's claimed mechanism, unverified), this is the first local test able to see it at all.
- Genuinely NOT new: the fact that a linear/equal-weight combination fails (items 6, 8) does not by itself say anything about whether a non-linear GBDT would fail too — that is exactly the preregistered question below, not assumed either way.

### A.3 Go/no-go and realistic expectation vs. the bar

**GO** (owner decision, 2026-09-28). Realistic expectation, stated honestly before running anything: **low-to-modest probability of clearing K1** (date-neutral Sharpe ≥1.19 anchor / ≥0.65 stress). Reasons to expect a positive result: (a) ROE alone already carries real signal (IC 0.026, t 3.0) that a non-linear model could extract without being drowned by price-volume noise the way the linear composite was; (b) widening into the illiquid tail is the one place literature suggests uncaptured ML edge lives. Reasons to expect failure: (a) five of six single-layer/linear tests on this exact data already failed or turned defensive; (b) the plausible mechanism for any edge (illiquid-name concentration) is also exactly where transaction costs bite hardest — this is a real tension, not a free lunch, which is why the cost model and position cap are preregistered now rather than tuned after seeing results. The staged kill test below is designed to falsify this cheaply before spending the full budget.

### A.4 Preregistration draft — `H-20260928-0X-multi-source-ranking-modal`

**Universe**: all Alpaca-tradable US common stocks, price ≥ $3, 21-day median dollar volume ≥ $1M, PIT (no look-ahead membership). Reuse `open_composer/research/features/universe.py::build_pit_universe_panel` with `min_close=3.0, min_dollar_adv=1_000_000, top_n=None` — this floor-mode path already exists and already carries `adv_rank` for downstream liquidity-tercile splits, so no new universe code is needed. **Known implementation gap to fix before coding, not before this brief**: the function's `adv_lookback_days` window computes a trailing **mean**, not median, dollar ADV; the owner's "median dollar volume" phrasing should either be accepted as mean-ADV (matching existing code, cheapest) or the function extended to support median — a one-line SQL change, decide at coding time, not now.

**Target**: forward return over the rebalance horizon (21 or 10 trading days, see below), beta-adjusted and demeaned within (formation_date, dollar_adv quintile) — same construction as H-20260917-02, recomputed at the new horizon.

**Costs**: two tiers, both preregistered now.
- **Base**: 10bp commission-free-equivalent + half the estimated bid-ask spread from a free daily-OHLC spread estimator (Corwin-Schultz 2012 or Abdi-Ranaldo 2017 high-low-based estimator). **Confirmed via `grep -ril "abdi\|corwin\|spread_est\|bid_ask_spread\|effective_spread" open_composer scripts data/features` that neither estimator exists in this repo today** — implementing one is a small, cheap (CPU-only, no new data, operates on the daily OHLC parquet already on hand), pure-function coding prerequisite for T-20260928-10, not built in this research-only round.
- **Stress**: 20bp + full estimated spread.
- **Position cap**: 1% of 21-day dollar ADV per name, enforced in the simulated book (caps illiquid-name sizing directly rather than relying on the spread estimate alone).

**Walk-forward/embargo**: 3-year rolling training window, quarterly retrain, expanding-then-rolling per H-20260917-02's existing script; embargo = the horizon length (21 trading days for monthly candidates, 10 for biweekly) to prevent label leakage across the train/validation boundary.

**Candidates (12, model × feature-addition × rebalance frequency; the existing price-volume-only ridge and any single-layer result are baselines, not additional trials)**:

| # | Model | Feature addition over price-volume base | Rebalance | Target horizon |
|---|---|---|---|---|
| 1 | LightGBM regression | + XBRL fundamentals only | monthly (21d) | excess_21 |
| 2 | LightGBM regression | + XBRL fundamentals only | biweekly (10d) | excess_10 |
| 3 | LightGBM regression | + insider (Form 4) + short interest/volume only | monthly | excess_21 |
| 4 | LightGBM regression | + insider + short only | biweekly | excess_10 |
| 5 | LightGBM regression | + all (fundamentals + insider + short + earnings-date event) | monthly | excess_21 |
| 6 | LightGBM regression | + all | biweekly | excess_10 |
| 7 | LightGBM LambdaRank | + fundamentals only | monthly | excess_21 rank |
| 8 | LightGBM LambdaRank | + fundamentals only | biweekly | excess_10 rank |
| 9 | LightGBM LambdaRank | + insider + short only | monthly | excess_21 rank |
| 10 | LightGBM LambdaRank | + insider + short only | biweekly | excess_10 rank |
| 11 | LightGBM LambdaRank | + all | monthly | excess_21 rank |
| 12 | LightGBM LambdaRank | + all | biweekly | excess_10 rank |

**Required baselines**: (i) pure price-volume ridge, reused from H-20260917-02 (RankIC 0.0071) — not rerun; (ii) 12-1 momentum-rule twin, recomputed on the new (widened) universe since no prior card covers this exact universe; (iii) same-universe equal-weight buy-and-hold; (iv) vol-matched S3 for the final Sharpe judgment per the frozen G1-G5/K1-K2 protocol.

**Placebo**: shuffled-label placebo, run only in Stage 2 (skipped in the Stage 1 kill test, matching H-20260917-02's own `--skip-placebo` precedent for a fast single-cell check).

**Reporting**: split results by liquidity tercile (`adv_rank` already carries the full cross-section rank, so terciles are a free downstream cut, not a new trial) — this is a reporting split, not counted against the 12-candidate family for multiple-testing purposes.

**Kill test (Stage 1, ≤$1) — decided now, before any run**:
- Run candidates **5, 6, and 11 only** (the three "all layers combined" variants — richest feature set, most likely to show any signal at all; if these show nothing, no ablation subset should be expected to beat them, since ablations are strict feature subsets).
- Window: **stress only** (2016-05 → 2023-08 per the runbook's frozen window), walk-forward validation RankIC, no placebo, no Stage-2 cost/position-cap machinery — just the ranking signal itself.
- **Modal job**: 8 cores, 32 GiB, 90 min timeout, no GPU. Cost = (8×$0.0473 + 32×$0.008) × 1.5h = $0.6344 × 1.5 = **$0.95**.
- **Preset stop threshold**: proceed to Stage 2 only if at least one of candidates 5/6/11 has stress-window mean validation RankIC ≥ **0.02** (the same admission bar H-20260917-02 already used to call ridge "refuted") **and** at least **+0.01** above the local price-volume ridge baseline (0.0071), i.e. ≥ 0.017 absolute is not enough by itself — both conditions must hold. If neither clears both conditions, **stop**: log `refuted` on `dir:ml_ranking_broad_universe_custom` and `dir:qlib_lightgbm_doubleensemble_recipe` for the combined-model variant, and do not spend Stage 2 budget.

**Full evaluation (Stage 2, ≤$3) — only if Stage 1 passes**:
- Run the remaining 9 candidates (ablations across both models, both rebalance frequencies) across **both** the stress and anchor windows, with the full cost model (base + stress cost tiers), position cap, and shuffled-label placebo.
- **Modal job**: 12 cores, 48 GiB, 180 min timeout, no GPU. Cost = (12×$0.0473 + 48×$0.008) × 3h = $0.9516 × 3 = **$2.85**.
- Judge the surviving candidate(s) against K1 (date-neutral Sharpe ≥1.19 anchor / ≥0.65 stress vs. S3) and K2 (+0.05 combined Sharpe over vol-matched S3) per the runbook, plus the liquidity-tercile split to see where any edge actually sits, plus the placebo and G1-G5 gates before any promotion.
- **Direction A total Modal spend, worst case: $0.95 + $2.85 = $3.80**, within the $6 guidance and well under the monthly $25 spend-guard cap.

---

## Direction B — Jiang-Kelly-Xiu (2023) chart-image CNN: deprioritized, evidence kept

**Owner decision (2026-09-28): deprioritized, not refuted.** Registry status `parked`. No preregistration drafted; the parallel web-research subagent dispatched for this direction was still running when the owner's decision landed and this brief was finalized without waiting on it (per instruction). Everything below is the evidence already on file from `I-20260923-09` §2/§6 (accessed 2026-09-23), carried over rather than re-derived.

| Source | Date read | What it shows | Status |
|---|---|---|---|
| Jiang, Kelly, Xiu (2023), *(Re-)Imag(in)ing Price Trends*, JoF 78(6) | 2026-09-23 | CNN on OHLC+volume bar-chart images (I5/I20/I60 → R5/R20/R60), train 1993-2000, test 2001-2019; CNN one-month strategies reported >3× short-term-reversal's Sharpe | search-summary — original PDF undecodable |
| github.com/George-hardworking/reimaging-price-trends-replication-and-extension | 2026-09-23 | Independent MIT-licensed replication: I5/R5 0.83%\*\*\* (orig) vs 0.71%\*\*\* (repl), I20/R5 0.84%\*\*\* vs 0.68%\*\*\*, I60/R5 0.54%\*\*\* vs 0.41%\*\*\* — direction/significance hold, magnitude shrinks ~15-25%; US→China zero-shot transfer weak/negative (-6.82% weekly), local retrain recovers it | verified-live (README read directly) |
| Same replication repo | 2026-09-23 | **No post-2019/2023 US out-of-sample test found anywhere** in that sweep — the single most valuable open gap for this method | search sweep, negative result (absence of evidence) |
| `I-20260923-09` §6 ranking | 2026-09-23 | Ranked #1 of 5 GPU-dependent method families on evidence quality + cheapness; proposed kill test: train 2016-2019, validate 2020, test 2021-2023 on liquidity top-1000, long-only, 10bp | verified-live (own prior brief) |

This direction remains the best-evidenced GPU candidate found to date (independent replication holds direction/significance; genuinely different feature space than anything refuted locally; no post-2019 US test exists for anyone to have refuted it with). It is parked on an owner priority call, not on new negative evidence — `reopen_if` is set accordingly in the registry row below.

---

## EV-per-dollar ranking, A vs. B, for a long-only liquid-execution-relevant result

Owner asked for this ranking explicitly. Judged on the **kill-test stage only** (the only stage either would actually spend money on before its own gate reopens further spend):

| | Direction A (multi-source ranking) | Direction B (chart-image CNN) |
|---|---|---|
| Kill-test cost | $0.95 | ~$0.94 (2 cores/8GiB/T4/75min — computed but not run, direction parked) |
| Strength of prior evidence for a real, replicated effect | Weak-to-mixed: every single-layer/linear test on this exact data already failed; the one non-linear/combined test has never been run | Strongest of any GPU method surveyed: independently replicated, direction+significance intact |
| Fit to our mandate (long-only, liquid-execution-relevant, Alpaca-tradable) | Direction now explicitly targets the illiquid tail where any edge is claimed to live — cost/turnover risk is real and load-bearing, not yet independently verified (item A.1#11) | Original edge described as EW across all caps with STR-like turnover — untested at any liquidity restriction; the proposed kill test itself would need to check whether it survives on a liquid subset |
| **Net read** | Lower confidence the effect exists at all; if it does, immediately fights the cost model | Higher confidence the effect exists somewhere; unknown whether it survives our liquidity/cost constraints, but that is a real open question rather than a first-run bet |

**Plain statement**: on priors alone, Direction B has the stronger claim to a real, replicated, not-yet-U.S.-2019+-tested effect, and would arguably be the higher-EV kill test to spend the first $1 on. Direction A's kill test is *not* a low-EV bet either — it targets the one specific gap (non-linear, all-layers-combined, on the widened illiquid-inclusive universe) that no local or literature evidence directly refutes — but it inherits five adjacent local failures and one unverified cost-caution citation, so it should be read as "worth the cheap test, not obviously going to work." **Direction A is GO per owner instruction regardless of this ranking** (illiquid-tail trading is now in-mandate and this is the cheapest test of it); Direction B's kill test is fully specified and ready in `I-20260923-09` if the owner reprioritizes it later — it is not being recommended against, only deferred.
