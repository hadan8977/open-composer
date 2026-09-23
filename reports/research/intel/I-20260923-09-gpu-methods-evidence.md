# I-20260923-09: What a GPU would actually buy us — published evidence, method by method

Scope: the owner is holding an RTX 5070 Ti laptop (~12GB VRAM, i9-13th gen, 16GB system RAM) and asked for a sourced answer before deciding whether to connect it (`docs/plan-research-coverage-2026-09-23.zh.md` section 7 parked this pending "有来源的说明"). This brief answers with published evidence for five method families, then ranks the GPU-dependent tests worth running and gives a plain verdict against spending the same effort on CPU/API-only work. It builds on `reports/research/intel/intel-quant-llm-frontier-2026-09-18.md` (LLM alpha-mining agents, tabular-model evidence in its section 4, and the Qlib staleness finding in section 6) rather than repeating those; this brief is narrower and deeper on the five families the owner asked about.

**Method note, for calibration** (same discipline as `I-20260923-08`): claims marked **verified-live** were opened directly this session (`WebFetch` on the primary page/repo, or a GitHub README actually read). Claims marked **search-summary** came only through `WebSearch`'s own extraction/synthesis of a page I did not separately open — per the project rule "搜索摘要不算读过原文," these are weaker and flagged inline. Claims marked **abstract only** came from an arXiv/SSRN abstract or landing page I did open, but not the full paper. Several arXiv-hosted PDFs (Gu-Kelly-Xiu, Chen-Pelger-Zhu, Chen-Kelly-Xiu, the Jiang-Kelly-Xiu original PDF, and one 2026 TSFM paper) returned FlateDecode-compressed streams that my `WebFetch` tool could not decode into readable text — those are explicitly marked **search-summary** below rather than presented as if I read the table myself, even where the underlying finding is well corroborated. One source (MDPI's DRL survey) returned **HTTP 403** and was never read; I say so where it would otherwise look like a citation. No files were touched besides this one; no downloads beyond `WebFetch`'s own internal cache.

---

## 0. Our situation, in one line

Long-only US stocks/ETFs via Alpaca, daily + intraday, costs tested at 10-20bp/side, no paid data; local data covers minute+daily bars 2016-2026 (~4,800 symbols incl. delisted), Alpha158/101/191+OSAP factor panels, Form 4/13D/earnings-dates/8-K text, ~680k timestamped news items (2024+), FINRA short data, macro; compute is a 3.9GB CPU box plus a DeepSeek text-scoring endpoint on a rolling 5h quota. Past local results: price-volume LightGBM lost to rules, momentum meta-labeling lost, news-count attention and event gates were refuted (`docs/plan-research-coverage-2026-09-23.zh.md` §1).

---

## 1. Deep nets vs. gradient-boosted trees, cross-sectional stock prediction

| Source | Sample / market | Setup | Reported result | Status |
|---|---|---|---|---|
| Gu, Kelly, Xiu (2020), *Empirical Asset Pricing via Machine Learning*, RFS 33(5) — [NBER w25398](https://www.nber.org/papers/w25398), [RFS](https://academic.oup.com/rfs/article/33/5/2223/5758276) | US individual stocks, ~1957-2016, 94 characteristics × 8 macro predictors (~920 features via interactions) | OLS/PLS/PCR/GLM/RF/GBRT/NN1-NN5, decile long-short portfolios | Trees and neural nets (3-5 layer) win; gains come from nonlinear interactions, not new information — **every method's dominant signals are variants of momentum, liquidity, volatility**; "in some cases doubling" the Sharpe of leading linear strategies | Search-summary. I attempted the primary PDF twice (`dachxiu.chicagobooth.edu/download/ML.pdf`, NBER mirror); both returned undecodable compressed streams, so exact R²ₒₒₛ/Sharpe digits below are **not independently verified by me this session** despite being widely and consistently cited |
| Chen, Pelger, Zhu, *Deep Learning in Asset Pricing*, Management Science 2024 (arXiv [1904.00745](https://arxiv.org/abs/1904.00745)) | US individual stocks, conditional autoencoder + no-arbitrage/SDF loss, adversarial test-asset construction, 178 macro series → learned economic states | Out-of-sample optimal-SDF portfolio | Beats benchmarks on Sharpe, explained variation, pricing errors; **out-of-sample annual Sharpe ≈ 2.1**; feeding all 178 raw macro series in *without* dimension reduction **collapsed** performance vs. no macro info at all | Search-summary (PDF undecodable) |
| Qlib official benchmark README — [github.com/microsoft/qlib/examples/benchmarks](https://github.com/microsoft/qlib/blob/main/examples/benchmarks/README.md) | CSI300/CSI500, China A-shares, Alpha158 (engineered factors) vs. Alpha360 (raw OHLCV sequence) | LightGBM/XGBoost/DoubleEnsemble vs. LSTM/GRU/ALSTM/TRA/HIST/IGMTF/TCTS/GATs | See table below | **Verified-live**, fetched directly |
| Grinsztajn et al., *Why do tree-based models still outperform deep learning on typical tabular data?*, NeurIPS 2022 D&B | 45 general (non-finance) tabular datasets | XGBoost/RF vs. several DL tabular architectures, tuned | Trees remain SOTA at medium size (~10k rows) even ignoring their speed edge; gap persists after tuning, isn't mainly about categoricals | Search-summary, but this is a heavily-cited consensus result |
| TabReD/TabArena/OmniTabBench (via `intel-quant-llm-frontier-2026-09-18.md` §4, already read that brief) | General tabular benchmarks, **time-based** (not IID) splits | GBDT vs. attention/transformer tabular architectures vs. TabPFN v2 | Under realistic walk-forward-style splits, GBDT stays the robust default; attention architectures degrade faster under drift; TabPFN v2 (Nature, real gains) has **"no CPU fallback,"** needs GPU, and its edge is for *small* datasets, not our large rolling panel | Search-summary (that brief's own label, reused here) |

**Qlib's own numbers** (verified-live, `examples/benchmarks/README.md`, mean±std over 20 seeded runs):

*CSI300, Alpha158 (engineered factors):*

| Model | IC | ICIR | Ann. Return | Info Ratio | Max DD |
|---|---|---|---|---|---|
| DoubleEnsemble (boosting) | 0.0521 | 0.422 | 11.58% | 1.34 | -9.2% |
| LightGBM | 0.0448 | 0.366 | 9.01% | 1.02 | -10.4% |
| XGBoost | 0.0498 | 0.378 | 7.80% | 0.91 | -11.7% |
| TRA (deep) | 0.0440 | 0.354 | 7.18% | 1.08 | -7.6% |
| ALSTM (deep) | 0.0362 | 0.279 | 4.70% | 0.70 | -10.7% |
| LSTM (deep) | 0.0318 | 0.237 | 3.81% | 0.56 | -12.1% |
| GRU (deep) | 0.0315 | 0.245 | 3.44% | 0.52 | -10.2% |

*CSI300, Alpha360 (raw price/volume sequence — the one setting favoring deep models' end-to-end feature learning):*

| Model | IC | ICIR | Ann. Return | Info Ratio | Max DD |
|---|---|---|---|---|---|
| HIST (deep, graph/relational) | 0.0522 | 0.353 | 9.87% | 1.37 | -6.8% |
| IGMTF (deep) | 0.0480 | 0.359 | 9.46% | 1.35 | -7.2% |
| TCTS (deep) | 0.0508 | 0.393 | 8.93% | 1.23 | -8.6% |
| TRA (deep) | 0.0485 | 0.379 | 9.20% | 1.28 | -8.3% |
| GATs (deep) | 0.0476 | 0.351 | 8.24% | 1.11 | -8.9% |

*CSI500, Alpha158:* LightGBM (IC 0.040, AR 12.84%, IR 1.57, MDD -6.4%) clearly beats DoubleEnsemble here (AR 3.82%, IR 0.17, **MDD -48.8%** — a reminder that a more complex winner on one slice can be badly unstable on another).

A second, **search-summary-only** CSI500 slice (2021-01-01 to 2024-12-31, source/provenance not independently confirmed) shows the opposite pattern: LightGBM AR turns *negative* (-1.18%, IR -0.16) while LSTM/Transformer/TRA stay positive (AR 2.9-5.0%, IR 0.4-0.6) — i.e., in the most recent window shown, GBDT's edge on engineered factors did not hold. I could not verify this table's source; treated as a directional hint, not evidence.

**Reading across all of this**: (1) Trees are not obsolete — they win or tie on engineered-factor inputs (Alpha158), which is our situation (Alpha158/101/191+OSAP factor panels). (2) Deep models' edge shows up specifically on *raw sequential* inputs (Alpha360) and via *relational* structure (HIST uses industry/concept graphs) — a different feature space than what we've tried. (3) **None of this is US-equity-validated.** The Sept-18 brief already found Qlib's official US-region path has an open, unfixed bug (Issue #1428) and no independently-published third-party US benchmark exists. (4) GBDT itself needs no GPU — nothing here explains our prior LightGBM-lost-to-rules result as a compute problem.

**Compute**: GBDT/linear/small-MLP — CPU, already true. Deep sequence/relational models at Qlib's CSI300/500 scale (300-500 names × ~10-15y daily) train in minutes on any consumer GPU. At our scale (~4,800 symbols × 10y daily, or minute bars) this is materially larger but still squarely laptop-GPU territory, not datacenter territory — this is where the 5070 Ti would matter most concretely if we pursue Alpha360-style raw-sequence models. Minute-bar deep sequence models at 4,800-symbol scale would be painful on CPU-only. TabPFN v2 needs GPU but doesn't fit our panel size regardless.

---

## 2. Chart-image CNNs — Jiang, Kelly, Xiu (2023)

[*(Re-)Imag(in)ing Price Trends*](https://onlinelibrary.wiley.com/doi/10.1111/jofi.13268), Journal of Finance 78(6):3193-3249 (SSRN since 2020). US CRSP common stocks; OHLC+volume+moving-average bar charts rendered as binary images (5/20/60-day lengths, I5/I20/I60), CNN trained to predict forward-return sign/magnitude (R5/R20/R60). **Train 1993-2000, test 2001-2019** (search-summary for the split, confirmed independently by the replication repo below).

Reported (search-summary, LinkedIn/blog-level, original PDF undecodable): CNN one-month-holding strategies have turnover similar to short-term-reversal (STR) but **>3× STR's Sharpe** and **2× weak-STR's Sharpe**; classic momentum has much lower turnover but a Sharpe an "order of magnitude" smaller than the CNN strategy. I could **not** verify the paper's exact EW-vs-VW split or explicit post-cost Sharpe numbers within budget — flagged as a gap, not fabricated.

**Independent replication** — [George-hardworking/reimaging-price-trends-replication-and-extension](https://github.com/George-hardworking/reimaging-price-trends-replication-and-extension) (**verified-live**, README read directly):

| Spec | Original paper | Replication |
|---|---|---|
| I5/R5 (equal-weight H-L) | 0.83%*** | 0.71%*** |
| I20/R5 | 0.84%*** | 0.68%*** |
| I60/R5 | 0.54%*** | 0.41%*** |

Direction and significance **replicate**; magnitude shrinks ~15-25% — normal replication attenuation, not a refutation. The same replication tested transfer to China A-shares (2015-2019 OOS): direct US→China transfer was **weak/negative** (-6.82% weekly), local retraining recovered it (34.71%), fine-tuning partially did (28.24%) — a caution against assuming zero-shot cross-market transfer, even though the original paper itself claims the patterns generalize to 26 international markets (tension between the two claims noted, not resolved here). **No post-2019/2023 US out-of-sample test was found** in this sweep — this is the single most valuable gap: nobody we found has checked whether the decile spread survived 2020-2026.

**Data**: full daily OHLCV history — we already have this in full, no blocker. **Compute**: small image CNNs (a handful of conv layers over binary bar-chart images) are lightweight by 2026 standards; at our scale (10y × ~4,800 symbols × multiple horizons ≈ low millions of images at most) this is an afternoon-to-a-day on a 12GB laptop GPU, and meaningfully slower (likely 1-2 orders of magnitude) on CPU-only — conv nets don't play to CPU strengths the way GBDT does. **This is the cleanest concrete case where the GPU changes "impractical" to "an afternoon."**

---

## 3. Text and LLMs

| Source | What | Result | Status |
|---|---|---|---|
| Lopez-Lira & Tang, *Can ChatGPT Forecast Stock Price Movements?* ([arXiv:2304.07619](https://arxiv.org/abs/2304.07619), multiply revised through ~2025) | GPT scores headlines good/bad/irrelevant → numeric score → next-day return | GPT-4: ~90% hit rate on the (non-tradable) initial same-day reaction; **predicts subsequent drift, concentrated in small stocks and negative news**; GPT-1/GPT-2/BERT show no such predictability ("emergent" claim | Search-summary. **Could not confirm or refute decay in later revisions** within budget — flagged as open, not claimed either way |
| Chen, Kelly, Xiu, *Expected Returns and Large Language Models* ([SSRN 4416687](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416687), 2023 GSU-RFS FinTech Best Paper) | LLM **embeddings** (ChatGPT + LLaMA family) of news, not prompted scores; portfolio sort on LLM-implied expected returns | Beats bag-of-words/Word2Vec; "economically meaningful Sharpe ratios after transaction costs" (exact figure not extracted — PDF undecodable); 16 markets, 13 languages; **predictability concentrated in small stocks, dissipates fast in large/liquid names** — a direct caution for our liquid-stock mandate | Search-summary; by-model-size scaling result mentioned to exist but digits not extracted |
| FinBERT vs. GPT-4 sentiment, multiple 2024-2026 studies | Financial headline/sentence sentiment classification | Mixed: one study has logistic regression (81.8%) beat *both* FinBERT and zero-shot GPT-4 (54.2%); another has prompted "expert" GPT (~79%) clearly beat vanilla FinBERT (~56%); a third puts FinBERT ~85-87% F1 vs. GPT-4 ~90-93%, at **300-500× the per-document cost** and 20-40× the latency | Search-summary, several independent studies, consistent *direction* (prompting matters a lot; a dumb baseline sometimes wins) |
| FinGPT (open 7B) vs. GPT-4 ([arXiv:2507.08015](https://arxiv.org/pdf/2507.08015) and others) | Financial NLP benchmark suite | Sentiment: FinGPT 87.6% (FPB), 95.7% (FiQA-SA) — matches/marginally beats GPT-4 and FinMA-7B **on sentiment specifically**; but stock-movement prediction only 45-53% (near coin-flip) and financial QA exact-match 28.5% vs. GPT-4's 76% | Search-summary |

**Reading**: for straightforward sentiment/headline classification, a local 7B model is genuinely competitive with GPT-4-class APIs at a fraction of the cost — real, evidence-backed. For harder reasoning (return prediction, QA) the gap to frontier APIs stays large; don't trust a local 7B model there without task-specific validation. The most credible *return-predictive* text result (Chen-Kelly-Xiu) uses embeddings, not prompted scores, and needs the edge concentrated in **small stocks** we should expect to shrink materially in our **liquid-stock** setting — mark down the headline economics accordingly.

**Compute**: prompted scoring (Lopez-Lira & Tang style) is a short classification call per headline — **API is fine, no GPU needed**; this already matches our configured DeepSeek endpoint (rolling 5h quota, subject to project's "no bulk labeling on Claude tokens" rule). Embedding extraction (Chen-Kelly-Xiu style) from an open 7B-13B model is a single forward pass per document — comfortably fits a 12GB GPU, and over ~680k headlines this is hours not days; this does *not* strictly require a GPU either (quantized CPU inference works, just 10-50×-class slower by general rule of thumb — I did not find a stack-specific multiplier, so treat this as a qualitative estimate). General (non-finance) LLM-serving evidence (search-summary): a 14B model at Q4 fits 12GB, ~23-29 tok/s; local-vs-API break-even is roughly 5-20M tokens/month — but since DeepSeek's API is already cheap and configured, the marginal case for local inference *specifically for cost* is weaker than generic "local vs. GPT-4-pricing" comparisons suggest; worth measuring directly rather than researching further.

---

## 4. Time-series foundation models on stock returns

| Source | Claim | Status |
|---|---|---|
| Kronos, [arXiv:2508.02739](https://arxiv.org/abs/2508.02739), AAAI 2026 | Decoder-only transformer, tokenizes OHLCV into discrete "K-line language," pretrained on 12B+ bars from 45 exchanges (crypto/forex/futures/stocks, US-equity share unconfirmed). Small/base/large family; **Kronos-large — the variant behind the strongest reported portfolio results — is not publicly downloadable.** Authors claim price-forecast RankIC 93% above "leading TSFM," 87% above best non-pretrained baseline, 9% lower volatility-forecast MAE, all zero-shot | **Abstract only** (I opened the arXiv abstract page directly; full paper not read) |
| Independent test — [Say43/Finance-ETF-Forecasting](https://github.com/Say43/Finance-ETF-Forecasting) | Fine-tuned `Kronos-small` on 22 ETFs, 360-day context, 20-day horizon, 3 held-out ETFs OOS, with bias correction + conformal calibration | **Directional forecasts indistinguishable from a random walk — slightly *inverted* at the extremes (worse than chance).** No fee level, threshold, or asymmetric rule produced an edge. Robustness battery (zero fees, asymmetric thresholds, one month of live paper trading) confirmed the negative result was real. One partial positive: volatility forecasts had "real if modest" skill, **on par with plain GARCH(1,1)** — i.e., no better than a classical CPU-trivial model | **Verified-live** — I read this repo directly |
| A second independent claim (via aggregated search, source not confirmed) | Kronos "ranked last," realized-vol errors **2.4-2.6× higher than HAR-RV**; fine-tuning made it worse | **Search-summary only** — consistent in direction with Say43's finding but I did not open this source myself; lower confidence |
| TSFM-in-finance literature: "Re(Visiting) Time Series Foundation Models in Finance" ([arXiv:2511.18578](https://arxiv.org/pdf/2511.18578)), "Deep Learning for Financial Time Series" ([arXiv:2603.01820](https://arxiv.org/html/2603.01820v1)), "Pretrained TSFM for Financial Return Forecasting" ([arXiv:2606.27100](https://arxiv.org/pdf/2606.27100)) | Off-the-shelf TimesFM/Chronos/Moirai evaluated zero-shot and fine-tuned on financial returns | Consistent finding (per the 2026-09-18 brief's own reading, and my attempted re-fetch of 2606.27100 confirmed the model list but not the numeric table — PDF undecodable): **off-the-shelf TSFMs underperform standard ensemble/NN baselines**; finance-native pretraining (i.e., Kronos's whole pitch) narrows the gap but needs pretraining-scale compute we don't have — and Kronos itself just failed an independent directional test | Search-summary |
| Generic (non-finance) TSFM finding | Zero-shot reliability needs 50-100+ historical points; below that, ARIMA/Holt-Winters win | Search-summary; low relevance to us (we have long histories) |

**Verdict for this family**: the clearest "don't bother" of the five. The one independent test I directly opened, on the most-hyped, most-recent (2025), finance-native model, on liquid ETFs, found **no directional edge — worse than a coin flip at the extremes** — and only GARCH-level skill on volatility. The broader off-the-shelf-TSFM literature agrees. **Compute is not the obstacle here**: Kronos-small fine-tuning and zero-shot inference for any of these models fit easily on a 12GB GPU (small-to-mid parameter counts, short training runs) — the evidence is what's weak, not our hardware.

---

## 5. Other GPU-bottlenecked methods with high claimed returns

| Method | Claim | Evidence quality | Data/compute reality for us |
|---|---|---|---|
| Deep RL for trading | Various papers claim beating buy-and-hold | Mixed and setup-dependent (search-summary across several arXiv papers); buy-and-hold is *already* the benchmark in 68-77% of papers surveyed; when transaction costs rise, well-behaved agents **degenerate toward buy-and-hold themselves** rather than beating it net of costs — telling. MDPI's *"Deep Reinforcement Learning for Trading — A Critical Survey"* was targeted specifically for this brief but returned **HTTP 403 — never read**; do not treat its title as evidence of anything beyond its own existence. No long-only, cost-aware, liquid-US-equity RL result with independent replication was found in this sweep | GPU-accelerable but not GPU-blocked (CPU-feasible, just slow); the real problem is evidence quality and the hours needed for environment/reward design, which are the same regardless of GPU |
| Deep learning on limit order books (DeepLOB, [arXiv:1808.03668](https://arxiv.org/html/1808.03668v3); 2024 "LOBCAST" 15-model benchmark) | CNN+LSTM on L2/L3 order-book snapshots predicts short-term direction | Benchmarked on FI-2010 (5 Nasdaq Nordic stocks, 10 days) — narrow, non-US, tiny-N. DeepLOB itself trains on a **single Tesla P100** (much weaker than our 5070 Ti), 0.253ms forward pass | **Blocked on data, not GPU**: this needs Level-2/3 order-book depth, which we explicitly do not have and Alpaca's plan doesn't provide at that depth — acquiring it would mean paid data, contradicting the owner's no-paid-data decision. Park unless that decision changes |
| Deep sequence models on intraday futures ([arXiv:2605.17724](https://arxiv.org/pdf/2605.17724), "LSTM vs Gradient Boosting on MNQ") | Directly on-topic (minute-bar futures, LSTM vs. GBM) | **Not read** — PDF undecodable within budget; title/topic only, results not extracted. Listed as a pointer for follow-up, not a claim | — |
| RD-Agent(Q)-style automated factor/model search (already covered in the 2026-09-18 brief, not re-derived here) | LLM-driven factor+model co-optimization | The deep-model baselines it benchmarks against (MASTER/TRA) were trained on **dual Xeon + 4×RTX A6000 48GB** — roughly **16× the VRAM** of our one 12GB laptop card | Calibration point: frontier "auto-ML for factors" work assumes datacenter-class multi-GPU compute for its deep baselines. Our card is adequate for the LLM-driven factor-*generation* loop itself (CPU/API-class per that brief) but not for replicating frontier deep-model baselines at their own reported scale |

---

## 6. Ranked list of GPU-dependent tests worth running

| Rank | Candidate | Evidence | Realistic expectation for us (long-only, liquid, cost-aware) | Cost (hours/data) | Cheapest kill test |
|---|---|---|---|---|---|
| 1 | **Chart-image CNN** (Jiang-Kelly-Xiu replica, walk-forward 2020-2026) | Published JoF result + independent replication holds direction/significance with ~20% shrinkage; genuinely novel feature space vs. our factor-based work; no post-2019 US OOS test found anywhere | Expect further shrinkage from published/replicated numbers once we add 10-20bp costs and restrict to liquid names (published edge's cost-sensitivity is implied by "turnover similar to STR" — a high-turnover strategy); still the best-evidenced GPU candidate we found | ~1 day: render charts from existing daily bars (no new data), train small CNN on a 12GB GPU | First reproduce I20/R5 decile spread on the *already-published* 2001-2019 window on a liquid subset (e.g. top-1000); if our pipeline can't recover a signal where the authors did, stop before testing 2020-2026 |
| 2 | **LLM embeddings as a ranking-model feature** (Chen-Kelly-Xiu style, local 7B-13B) | Real academic result, transaction-cost-aware, but small-stock-concentrated — mark down hard for our liquid universe | Modest incremental IC at best; this is a feature-engineering add-on to the existing pipeline, not a standalone strategy | Low: reuses the multi-source ranking model v1 already planned for 09-27–09-29 (CPU); embeddings step adds a few hours on GPU for ~680k headlines | Add embeddings to the existing (already-scheduled) CPU ranking pipeline on a 1-2y liquid-only subset; check IC uplift over the text-free baseline before scaling further |
| 3 | **Deep relational/sequence model on raw price-volume** (HIST/TRA-equivalent on Alpha360-style input, not engineered factors) | Only place Qlib's own numbers show deep beating trees; China-only, unreplicated on US data, and unstable even within Qlib (CSI500 DoubleEnsemble MDD -48.8% shows complexity ≠ safety) | Unknown, no US precedent; our existing LightGBM-on-factors baseline already lost to rules, so the bar is "does raw-sequence + relational structure do something factors couldn't," not "beat the old baseline" per se | Moderate: full daily panel already available; a single held-out walk-forward window is a reasonable first cut | One model, one universe/period/cost setting, vs. existing LightGBM baseline; if it doesn't clear that already-modest bar, deprioritize immediately |
| 4 | **Kronos/TSFM zero-shot probe** (no fine-tuning) | Directly-opened independent test found no edge (worse than random at extremes) on liquid ETFs; broader TSFM literature agrees | Low — going in expecting a negative, cheaply confirming that expectation on our own universe is still worth doing once, given the cost | Very low: small pretrained weights, zero-shot needs no training, an afternoon | The zero-shot probe *is* the kill test — one run, no fine-tuning investment, on our own liquid names |
| 5 | **RL for trading** | Weakest, most setup-dependent evidence found; literature's own agents regress to buy-and-hold under real costs; worst hours-to-evidence ratio (env/reward design is the real cost, not GPU) | Low; no long-only cost-aware liquid-equity precedent found | High: environment design, reward shaping, extensive tuning | Not worth a kill test yet — no credible published target to falsify first |
| — | LOB/order-flow deep learning | DeepLOB-class GPU need is trivial (a single P100 was enough) | N/A | Blocked on data we don't have (order-book depth), not on GPU | Revisit only if the no-paid-data decision changes |

---

## 7. Plain verdict

**How much does the GPU change our near-term profit odds?** Modestly, and concentrated in **one** family: chart-image CNNs (rank 1) are the single clearest case where a 12GB laptop GPU turns a well-evidenced, independently-replicated, not-yet-tried-on-our-data method from "impractical" into "an afternoon." A second item (LLM embeddings, rank 2) benefits from the GPU but doesn't strictly need it — it's a speed/cost multiplier on something an API can already do. The other three families are weak on the merits, not on compute: raw-sequence deep cross-sectional models are unreplicated outside China A-shares and unstable even there; Kronos/TSFMs have a directly-verified independent negative result against them; RL's own literature shows agents retreating to buy-and-hold once costs are realistic; and order-book deep learning is blocked on data we don't have and aren't buying, not on GPU.

**Versus spending the same effort on new information with CPU/API models**: our own diagnosis (`docs/plan-research-coverage-2026-09-23.zh.md` §1) is that the CPU/API path — combining price-volume factors with events, alt-data, and text in one ranking model — has *not* actually been tried yet; we tested those signals individually against a strategy-level bar, mostly bolted onto momentum, rather than combining sources the way the literature that works (Chen-Kelly-Xiu, GKX) does. That work is CPU-only, already scheduled (multi-source ranking model v1, 09-27–09-29), and plausibly has *higher* near-term expected value per hour than four of these five GPU families — except the chart-image CNN, which is a genuinely different feature space and isn't a substitute for factor/text combination work or vice versa.

**What can be done without the GPU, and at what cost**: everything in family 1 except raw-sequence/relational deep nets (GBDT, small MLPs — CPU, already our practice); prompted LLM scoring (family 3's Lopez-Lira & Tang style) — API-only, no GPU, already have the endpoint, cost is API calls within the existing 5h-quota discipline; FinBERT-class sentiment — CPU-feasible (BERT-size), cheap. What genuinely needs the GPU to be practical rather than just faster: chart-image CNNs at our data scale, and raw-sequence/relational deep cross-sectional models if we pursue rank 3. Local 7B-13B embeddings/inference are a "nice to have, not a blocker" — quantized CPU inference works, just an order of magnitude or more slower, and DeepSeek's API is already cheap enough that local inference's main draw is iteration speed, not unlocking something otherwise impossible.

**Recommendation**: don't reopen the GPU as a blanket yes. Green-light the one narrow, cheap, well-evidenced test (rank 1, chart-image CNN, starting with the reproduce-the-published-window kill test) plus a same-afternoon zero-shot Kronos probe (rank 4) since it's nearly free to falsify, while continuing the already-planned CPU-only multi-source ranking work in parallel. Revisit ranks 2-3 only after rank 1's kill test and the multi-source ranking model v1 report in.

---

## Appendix: not verified / could not open this session

- Gu-Kelly-Xiu (2020) exact R²ₒₒₛ and Sharpe table: PDF undecodable by my fetch tool (twice); relied on consistent secondary characterization only.
- Chen-Pelger-Zhu (2024) exact Sharpe/compute details beyond the "2.1" figure found via search: PDF undecodable.
- Jiang-Kelly-Xiu (2023) exact EW-vs-VW split and explicit post-cost Sharpe numbers: original PDF not fetched directly (LinkedIn summary and replication repo used instead); no post-2019 US OOS test found by anyone.
- Lopez-Lira & Tang: whether later (2024-2025) arXiv revisions show decay — not found within budget, worth a dedicated follow-up search.
- Chen-Kelly-Xiu: exact post-cost Sharpe number and the by-LLM-size scaling result: PDF undecodable.
- Kronos: exact model parameter counts per variant, and pretraining GPU/hardware: not disclosed in what I could open (abstract + alphaXiv overview).
- "Kronos ranked last, 2.4-2.6× HAR-RV" and Pretrained-TSFM (arXiv:2606.27100) exact numeric tables: both undecodable/unconfirmed, presented as lower-confidence.
- MDPI *"Deep Reinforcement Learning for Trading — A Critical Survey"*: blocked with HTTP 403, never read; do not cite beyond its title existing.
- arXiv:2605.17724 (LSTM vs. GBM on MNQ futures minute bars): PDF undecodable; topic noted, results not extracted — a good candidate for a focused follow-up read given how directly it matches "deep models on minute bars."
