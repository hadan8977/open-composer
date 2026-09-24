# I-20260923-10: fmzquant/strategies — what the 5,800-strategy repo actually is, how people use it, and whether it helps us

Scope: owner question 2026-09-23 ~15:00 UTC: "https://github.com/fmzquant/strategies 这个你有没有看过，搜搜看大家都怎么用这个和评价和体验和分析等". Registry check first (`oc research directions check fmz fmzquant strategy square`): no prior row; nearest prior evidence is `dir:crypto_trend_btc` (evidence_too_weak) and our own technical-signal cards (library v1).

**Method note**: claims marked **verified-live** were opened this session (GitHub API, raw files, WebFetch on the primary page). Claims marked **search-only** come from search-result snippets and are not treated as read. Nothing was bought or signed up for.

---

## 1. What the repository is (verified-live, GitHub API + raw files, 2026-09-23 15:00 UTC)

- `fmzquant/strategies`: 5,861 stars, 1,858 forks, created 2016-04-03, **last push 2025-04-30**; 5,807 files, **all markdown**; commit messages are all `update` (bulk exports), no code, no tests, no license file.
- It is an export of FMZ's public strategy square (fmz.com, formerly BotVS, a Chinese crypto/futures bot platform). Each file: name, author, AI-style bilingual description, parameter table, source code, a link `https://www.fmz.com/strategy/<id>`, last-modified date.

Random sample, n = 160 of 5,807 (seed 7), parsed mechanically; per-file rows in `reports/research/intel/sources/20260923-fmzquant/sample-profile.json`:

| Property | Count / 160 | Share |
|---|---|---|
| Source is PineScript (TradingView script ported to FMZ) | 145 | 91% |
| Still carries TradingView's MPL licence or `// © author` header | 41 | 26% (lower bound for "copied from TradingView") |
| Posted by one account, `ChaoZhang` | 126 | 79% |
| Posted by FMZ staff-style accounts (ChaoZhang, ianzeng123, 发明者量化-小小梦) | 149 | 93% |
| Backtest config on BTC_USDT | 130 | 81% |
| Backtest on Binance perpetual futures | 131 | 82% |
| Median backtest window | 30 days | — |
| Backtest window ≤ 90 days / ≥ 3 years | 78 / 6 of 148 | 53% / 4% |
| Quotes any performance number (return, Sharpe, drawdown) | 2 | 1% |
| Any out-of-sample or live result attached | 0 | 0% |

The 15 non-Pine files are classics (Keltner, R-Breaker, Connors RSI(2), ahr999 DCA), **martingale / doubling bots** (布林马丁, 智能间隔倍投 — avoid), and platform tools or API demos (account transfer, K-line pagination, copy-trading bot).

Reading: this is a content-marketing corpus. Most entries are ports of public TradingView strategies, reposted by FMZ staff accounts with template text (Overview / Advantages / Risks / Optimization Directions). They are neither curated nor ranked by any evidence of performance.

## 2. How people use it and what reviewers say

- **Platform, not strategies, is what gets reviewed.**
  - Finestel's 2026 review (verified-live; no affiliate disclosure on the page) praises the all-in-one development-to-live workflow and the large library "to learn and benchmark ideas".
  - It also warns that "shared or rented strategies vary wildly in quality, transparency, and robustness".
  - It adds that "a bot that looks amazing in backtests can fail quickly in live markets because of friction". Pricing is $0.05 per live-bot hour.
  - CoinCodeCap and WunderTrading reviews exist (search-only); both are platform or affiliate listings.
- **Usage pattern**:
  - The forks and the Context7 index (context7.com/fmzquant/strategies, search-only) show the repo is used as a code and API-example corpus for writing FMZ bots, including by AI coding assistants.
  - It is also a learning resource. No thread was found where someone reports running a strategy from it live with results.
- **Chinese-language results** are almost all FMZ's own channels: the Zhihu org account 发明者量化, the cnblogs `fmzcom` blog, and CSDN tutorials (all search-only). General Chinese quant commentary on overfitting and "backtest 100% a year, live losses" is common (e.g. cnblogs warm3snow series, search-only) but not specific to this repo.
- **No independent evaluation of the repo's strategies was found.**
  - QuantCode-Bench (arXiv 2604.15151, verified-live) does not use it.
  - No paper, blog or forum post measures their out-of-sample performance.

## 3. Evidence on the strategy class itself (indicator-combination technical rules)

| Source | Market / sample | Finding | Status |
|---|---|---|---|
| Bajgrowicz & Scaillet (2012), *Technical trading revisited*, JFE 106(3) — [IDEAS](https://ideas.repec.org/a/eee/jfinec/v106y2012i3p473-491.html) | DJIA daily 1897-2011, thousands of rules, FDR data-snooping control | "an investor would never have been able to select ex ante the future best-performing rules"; "even in-sample, the performance is completely offset by the introduction of low transaction costs" | verified-live (abstract) |
| Hudson & Urquhart (2021), *Technical trading and cryptocurrencies*, Ann. Oper. Res. 297 — [IDEAS](https://ideas.repec.org/a/spr/annopr/v297y2021i1d10.1007_s10479-019-03357-1.html) | 2 BTC markets + 3 coins, ~15,000 rules, multiple-testing controls | significant in-sample predictability for crypto rules, **"However there is no predictability for Bitcoin in the out-of-sample period"** | verified-live (abstract) |
| arXiv 2608.27734, *What survives honest evaluation?* — [abs](https://arxiv.org/abs/2608.27734) | 453-stock PIT US universe + 39 ETFs, costs, trial-count deflation | rejects every LLM-discovered strategy across two frontier models, budgets up to 100 candidates, and 5 runs; passive benchmarks certified | verified-live (abstract) |
| Our library v1 cards (`reports/research/signal-cards/library-v1-summary.md`) | US stocks 2016-2026, top-3000 PIT | short-term reversal, Reversal Trend daily reclaim/bear rejected; RT bull admitted only as an exit signal | local |
| `dir:crypto_trend_btc` (`I-20260923-02`) | BTC trend following, 2025 paper | headline net numbers below our bar even at face value | local registry |

The repo's modal entry is a TradingView indicator combo tested on 30 days of BTC perpetuals. The class-level evidence is negative out of sample for exactly that instrument (Hudson & Urquhart). For stock-index rules the evidence is negative after costs (Bajgrowicz & Scaillet).

## 4. Verdict for Open Composer

1. **Not a source of tradeable strategies for us: `evidence_too_weak`.**
   - We trade long-only US stocks and ETFs through Alpaca. Crypto sits in the `out_of_scope.crypto_nonus` cell, and 82% of the corpus is BTC perpetual futures.
   - The strategies carry no out-of-sample or live evidence to reuse; median backtest window is 30 days.
2. **Do not mass-backtest it.**
   - Running thousands of indicator combinations and keeping the best is the data-snooping trap the three studies above measure. The winner's backtest would look strong by construction and predict nothing.
   - If we ever wanted to, it would need a preregistered family with trial-count deflation, like our signal-card and manifest discipline. The prior is too low to justify the compute.
3. **Do not spend DeepSeek quota classifying all 5,807 files** in the bottom-up feed. The n = 160 sample already fixes the composition: 91% ± ~4.5% (95%) Pine indicator strategies. A full pass would fill one low-tier cell.
4. **Narrow reuses, if ever needed**:
   - the Pine sources as fixtures for our own spec→Pine generator tests;
   - the classic non-Pine implementations (R-Breaker, Keltner, Connors RSI(2)) as reference code if a preregistered iteration ever tests those mechanisms on US ETFs. Our registry already covers ETF mean reversion under `reversal.etf_mean_reversion`.
5. **Owner-level note**: FMZ's public "live bot" pages could in principle be a live-record source, like `public_records.copy_verified_live`. They are crypto and self-reported, so they stay out of scope unless the owner brings crypto into scope, which is a separate decision (new asset class, new broker capability).

## Search log (2026-09-23, ~14:55-15:10 UTC)

- GitHub API: `repos/fmzquant/strategies`, `/languages`, `/contents/`, `/git/trees/master?recursive=1`, `/commits?per_page=5`; raw files via raw.githubusercontent.com (160 sampled).
- Web searches:
  - `fmzquant strategies github review`
  - `FMZ Quant platform review reddit experience`
  - `发明者量化 FMZ 评价 靠谱吗 实盘 体验`
  - `"fmzquant/strategies" dataset OR benchmark OR paper`
  - `reddit algotrading "fmz" OR "fmz.com" OR "botvs" strategies`
  - `tested hundreds of TradingView public strategies out of sample results overfitting study`
  - `发明者量化 策略广场 租用 策略 亏损 OR 过拟合 OR 割韭菜`
  - `Hudson Urquhart 2021 "Technical trading and cryptocurrencies"...`
- Opened: finestel.com/blog/fmz-quant-review; arXiv 2604.15151 (PDF); arXiv abs 2608.27734; IDEAS pages for Hudson & Urquhart (2021) and Bajgrowicz & Scaillet (2012). ScienceDirect returned 403.

---

## 5. Addendum 2026-09-24: the US-equity subset (owner: "里面的美股策略也可以看看")

Full clone (`git clone --depth 1`, commit 7853bb2, 5,807 files) at `/opt/oc-search/fmz-strategies` (outside the repo).

**Where the corpus is backtested.** All 5,262 backtest configs in the corpus point at crypto exchanges, except one on Chinese futures (CTP). None targets US stocks. The US-equity content is therefore TradingView scripts that were written for stocks and then rerun on BTC by FMZ.

**How the subset was found.** A regex scan for tickers, indices and ETFs, combined with equity context (session times, stock words, earnings/dividends, ETF rotation), found 132 files. They were grouped into mechanism families by title:

| Family | Files | Our prior evidence | Decision |
|---|---|---|---|
| Generic indicator combos (MA/MACD/RSI/ATR/Supertrend) naming SPY/QQQ/VIX | 91 | Owner tier view ranks these lowest; library v1 rejected the technical signals it tested | skip |
| Single-stock indicator scripts (TSLA, AAPL, NVDA) | 10 | none; one-name fits | skip |
| Relative strength / dual momentum / rotation | 9 | ETF rotation sleeves already on paper; `dir:etf_dual_momentum_rotation_gem_pools` (duplicate); giants sweep | covered |
| **Dip reversion: IBS, Connors R3, Connors 3-Day High/Low, VIX Fix** | 6 | **not in the registry.** Pagonidis (2014, NAAIM) documents a US-only close-to-close IBS effect through 2013-05. The giants sweep tested only Composer RSI(10) branch rules on TQQQ. | **testing: H-20260924-01, 24 preregistered candidates** |
| Pairs / ratio (SPY-QQQ Kalman) | 6 | `dir:intraday_cointegration_pairs_pca` evidence_too_weak | skip: no published edge; the SPY/QQQ ratio trends with tech leadership |
| Opening range / intraday session | 4 | `dir:orb_etf_opening_range_breakout` refuted; Stocks-in-Play ORB running (H-20260923-13) | covered |
| Leveraged ETF balancing / option selling | 3 | S3 levered sleeve on paper; options cell (Alpaca options data from 2024-02) | covered / data-limited |
| Seasonality / calendar | 3 | `dir:turn_of_month_equity_seasonality` harvested, untested | queue with the calendar cell |

**What the dip-reversion entries are.**
- The repo's "ETF 3-Day Reversion" (fmz 429146) and "Reversal RSI ETF" (fmz 439643) are ports of Connors & Alvarez (2009) *High Probability ETF Trading* rules: the 3-Day High/Low method and R3. Both enter on the close (`process_orders_on_close=true`).
- The IBS entry (fmz 484915) is Algotradekit's TradingView "IBS Trading Strategy for SPY and NDQ": IBS ≤ 0.09 / 0.11 with an EMA(220/200) filter, exit at IBS ≥ 0.985 / 0.995 or 14 days.
- Quality flag: the repo's MyLanguage "Larry Connors RSI2" script trades against the trend, the opposite of Connors' published rule.

**Test design.** H-20260924-01 tests these rules plus Connors RSI(2) and an IBS-filtered RSI(2) on QQQ and SPY, executed on 1x and 3x ETFs.
- Protocol: the giants-sweep protocol, unchanged (select, holdout and anchor windows; 10/20 bp; G1-G5).
- Execution: market-on-close orders from a 15:50 ET proxy signal.
- Placebos: random-entry-timing and calendar-shift.
