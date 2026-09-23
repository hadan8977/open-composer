# I-20260923-08: Free substitutes for data types we would otherwise pay for

Scope: the owner has ruled out paid data. This brief checks, for eight categories of data a US-equity shop would normally buy, whether a free (or free-with-registration) substitute exists, whether it is point-in-time (PIT) usable, and what it would unlock against `docs/plan-research-coverage-2026-09-23.zh.md` section 3's coverage map. It builds on `reports/research/intel/intel-free-alt-data-signals-2026-09-18.md` (event/alt-data signal survey) and `intel-intraday-and-options-runnable-2026-09-18.md` (options/intraday) rather than repeating them; where this brief only cross-references a source those two already covered in depth, it says so and does not re-litigate it.

**Method note, for calibration**: sources marked "verified live" below were read from the primary page (`WebFetch`) or probed directly against the live API with `curl` (outputs kept under `/tmp/intel-probe/`, nothing written to the repo, well under the 50MB cap). Sources marked "search-summary" came through `WebSearch`'s own extraction of the primary page and were not independently re-fetched in full; I treat those as weaker evidence per the project's "a search snippet does not count as reading" rule and flag the ones material to the ranking. No sign-ups, no paid trials, no `.env`/credential files were touched. Existing Alpaca/FRED/SEC credentials already in `capabilities/registry.yaml`'s `env:` lists are referenced only to note that a given free source needs no *new* registration.

**What's already in flight, so this brief doesn't re-recommend it**: `docs/current-view.zh.md`'s 2026-09-20 entry says FINRA's **daily short *sale* volume** file (a different construct from short *borrow* fee/utilization, see §5) is already collected locally at `data/features/short_volume_broad/{2018..2026}.parquet`. `capabilities/registry.yaml` already has stub/trial entries for Cboe VIX/VIX3M, FRED, GDELT, Alpaca news, and — notably — an **unconfigured** `options.trial_chain` placeholder that this brief's §1 finding fills in.

---

## 1. Options history (EOD IV/skew/volume/OI, intraday option trades)

**Verified live** against `docs.alpaca.markets/us/docs/historical-option-data` (WebFetch of the actual page) and Alpaca's support pages:

| Fact | Detail |
|---|---|
| Historical coverage start | "Currently we only offer historical option data since February 2024" — a hard floor, not a rolling window. As of 2026-09-23 that is ~31 months of backfill, not the multi-year history a paid vendor (ORATS, CBOE DataShop, Polygon — see the 2026-09-18 brief's cost table) would sell. |
| Free tier ("Indicative") | A free, *derived* feed: quotes are not real OPRA quotes but Alpaca-computed indicative values; trades are real but delayed 15 minutes. Snapshot endpoints (`/v1beta1/options/snapshots`) return latest trade/quote/**greeks**/**IV** computed by Alpaca on top of whichever feed is active. |
| Paid tier ("OPRA") | Real consolidated OPRA BBO, subscription-gated (Algo Trader Plus). |
| Open interest | Served from a **separate** contract endpoint sourced from OCC's end-of-day calculation, **one calendar day lagged**, one call per contract — this part is not OPRA-gated, so it is available on the free tier too. |
| Access | We already hold `ALPACA_API_KEY_ID`/`ALPACA_API_SECRET_KEY` (used for `market.alpaca_bars`, `news.alpaca`); no new registration needed. |
| Rate limits | Not documented on the fetched page; the API reference elsewhere mentions up to 1,000 calls/min for market data generally, tier-dependent — needs confirming against our actual plan before a bulk backfill job, not before a small probe. |
| Licence | Same Alpaca market-data terms as our existing bars/news capabilities. |

**Correction to the 2026-09-18 brief**: that brief concluded free option sources give only live snapshots with "no backtestable PIT history" and treated options as flatly not doable. That is no longer accurate for us specifically: because we already have an Alpaca account, the free Indicative feed gives 31 months of **stored, replayable** historical trades (Feb 2024+), which is enough to prototype and cross-validate short-dated strategies (0DTE/weekly put-write per the 2026-09-18 options brief), just not enough for a 2016-style long-history backtest. This matches `docs/plan-research-coverage-2026-09-23.zh.md` §3 row 6's own open item ("先用 Alpaca 2024 年以来的期权数据做可行性") — this brief is that feasibility check.

**Adjacent, already-partially-registered**: Cboe publishes the SKEW Index (tail-risk skew, EOD, free CSV, same `cdn.cboe.com/api/global/us_indices/...` pattern as the existing `market.cboe_volatility_indices` capability) — an index-level, not per-stock, skew proxy; extending that capability with one more URL is near-zero-cost but only gives a market-wide reading, not cross-sectional skew.

**Coverage cell**: #6 (期权信息), currently empty. **Ingest effort**: ~4-6 hours to point our existing Alpaca collector pattern at the options endpoints and fill in `options.trial_chain`'s `provider` field. **Best published signal**: still governed by the 2026-09-18 brief's finding that put/call and GEX evidence is thin or commercially self-interested; this brief does not add new signal evidence, only new *access* evidence.

---

## 2. Analyst consensus EPS estimates and revisions, point in time

The 2026-09-18 brief already found the free retail sources (Zacks web, Seeking Alpha's 90-day summary) give only current snapshots, no downloadable PIT history, and that the academic-standard source (I/B/E/S) is paid. This brief re-checked for a free PIT alternative and found one candidate, with a hard catch:

| Source | What it is | PIT? | Access | Licence/effort |
|---|---|---|---|---|
| [Estimize](https://www.estimize.com/) | Crowdsourced EPS/revenue estimates, buy-side + sell-side + independents + academics; [~3,000 US tickers, history from Jan 2012](https://www.estimize.com/data) (search-summary level) | Yes by construction — each estimate is timestamped before the print | Free only in exchange for **contributing your own estimates**, or via an [academic-access request](https://www.estimize.com/access/academic) (a sign-up/approval flow) — **this is a registration-gated owner action under our hard rules, not something this brief can activate** | Bulk/institutional-grade feed is resold through WRDS (paid); a self-serve free bulk download without registering was not found |

Academic evidence that Estimize consensus predicts EPS better than I/B/E/S exists (e.g., a University of San Diego working paper hosted on Estimize's own domain — note the affiliation, treat as closer to author-reported than independent), but this brief did not verify a specific *return* backtest for it in the time available.

**Verdict: still a real gap for an unattended agent.** No free, no-signup, bulk-downloadable PIT analyst-estimate history was found. The nearest zero-registration proxy is not a substitute at all: use realized EPS *surprise* from free SEC XBRL as-reported data (§4) against the market's own pre-print price drift, which sidesteps needing a consensus number but also isn't the same construct. **Coverage cell**: none newly unlocked; flag Estimize academic access as an owner decision if this gap matters enough to justify a sign-up.

---

## 3. Earnings call transcripts, point in time

Also a confirmed gap in the 2026-09-18 brief (no free bulk historical source; paid vendors only). This brief looked specifically for free datasets and found only stale, one-time academic snapshots, not a live free feed:

| Source | Coverage | Currency | Verdict |
|---|---|---|---|
| [GeminiLn/EarningsCall_Dataset](https://github.com/GeminiLn/EarningsCall_Dataset) (GitHub) | S&P 500 companies, **2017 only**, transcript text + audio (via linked Google Drive, too large for GitHub itself) | Frozen at 2017, not maintained | Companion data to Qin & Yang, *What You Say and How You Say It Matters* (ACL 2019) — predicts post-earnings **volatility**, not returns; author-reported, reused by follow-on NLP papers as a benchmark corpus (methodological reuse, not an independent return-signal replication) |
| [revdotcom/speech-datasets](https://github.com/revdotcom/speech-datasets) (Earnings-21) | 44 calls, **2020 only**, 9 sectors | Frozen, built for ASR benchmarking not trading | Too small/stale for signal work |
| [cdubiel08/Earnings-Calls-NLP](https://github.com/cdubiel08/Earnings-Calls-NLP) | Scraped Seeking Alpha S&P 500 transcripts, coverage years unclear from the repo listing | Personal project, scrape target (Seeking Alpha) now paywalls most transcripts | Not verified further given time budget |

**Verdict: no viable free, currently-collectible substitute.** The free datasets that exist are frozen single-year academic snapshots (2017, 2020) with no forward-collection path — Seeking Alpha, the common scrape target, has since paywalled most transcripts. This confirms and hardens the 2026-09-18 conclusion rather than changing it. **Coverage cell**: none unlocked; do not spend engineering time here until the owner is willing to pay for a transcript vendor or a scrape-tolerant free source turns up.

---

## 4. As-first-reported fundamentals (SEC XBRL) — verified in depth, recommended first ingest

This is the strongest finding in this brief. I probed the live API directly (`curl` against `data.sec.gov`, contact email in the User-Agent per SEC's policy) rather than trusting docs alone.

**Verified live, `companyconcept`/`companyfacts` API** (`https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/{tag}.json`, `.../companyfacts/CIK##########.json`): every fact row carries `accn` (accession number), `filed` (filed date), `form` (10-K/10-Q/10-K/A/...), `fy`/`fp` (fiscal year/period), `end` (period end date), and `val`. Example pulled live (Apple, `us-gaap:Assets`):

```
{'end': '2008-09-27', 'val': 39572000000, 'accn': '0001193125-09-214859', 'form': '10-K',   'filed': '2009-10-27'}
{'end': '2008-09-27', 'val': 36171000000, 'accn': '0001193125-10-012091', 'form': '10-K/A', 'filed': '2010-01-25'}
```

That is a **directly observed restatement**: Total Assets for FY2008 as originally filed was $39.572B; a 10-K/A five months later revised it to $36.171B, and every subsequent 10-K carried the revised figure forward as the comparative. This answers the task's specific question — **restatement handling is fully recoverable for free**: take the *minimum* `filed` date per (`concept`, `end`) pair for "as originally reported," and any later row with the same `end` but a different `val` (typically `form ∈ {10-K/A, 10-Q/A}` or a later periodic filing whose comparative column changed) is a restatement, not a new fact. 18 of Apple's own 146 `Assets` rows show this multi-filing pattern for a single period — restatement/re-reporting is common enough that a naive "one row per period" ingest would silently pick up look-ahead-biased revised numbers.

**Frames API** (`.../xbrl/frames/us-gaap/{concept}/{unit}/CY{yyyy}Q{q}I.json`) gives one cross-sectional snapshot per concept per calendar-aligned period across *all* filers — useful for building a broad PIT panel (e.g., Assets, Revenues, EPS) without looping per-company, at the cost of the frame being anchored to nearest-fit calendar quarters rather than each firm's own fiscal calendar (documented limitation).

**Financial Statement Data Sets** (`sec.gov/data-research/sec-markets-data/financial-statement-data-sets`, bulk quarterly ZIPs): covers **2009-01 through the present quarter**, "presented without change from the as-filed reports," ZIPs from 13KB (2009Q1) to ~122MB (2025Q3+); a Dec-2024 reprocessing added a `segments` field. This is the cheap bulk-ingest path once the per-company API above has validated the restatement logic on a small sample; I did not independently re-verify its SUB/NUM schema's restatement flag (`prevrpt`) against the live files this session — the per-company API proof above is the one I'd trust first.

**No key required**, only a descriptive `User-Agent` with a contact email (we already comply via `SEC_USER_AGENT`, the same env var `events.sec_filings`/`events.sec_form4_insider` already use). No documented rate limit beyond SEC's general fair-access policy. Data is public-domain filings; `events.sec_filings`'s existing caveat ("EDGAR public access does not establish reuse rights for issuer-authored filing content") applies equally here.

**Known real cost, not a blocker but not free lunch either**: companies pick their own `us-gaap` tags for economically similar line items (e.g. `NetIncomeLoss` vs `ProfitLoss`), so a clean multi-concept, multi-thousand-issuer panel needs a tag-mapping layer — this is the standard, well-documented pain point of using SEC XBRL at scale, not a surprise specific to us.

**Coverage cell**: this is the single highest-leverage gap-filler in the brief — it unlocks **both** #3 (个股事件 — PEAD via free as-reported EPS/revenue surprise, which `docs/plan-research-coverage-2026-09-23.zh.md` explicitly schedules for 09-26/09-27 as "PEAD 用免费 XBRL 算业绩超预期") and #7 (基本面/会计 — earnings/quality/accrual features, currently "搁置：缺时点财报"). **Ingest effort**: ~4-8 hours for a narrow prototype (single concept — EPS or Revenue — top-500 universe, via `companyconcept`, to prove PEAD is computable and the restatement filter works); ~3-5 days for a clean multi-concept (EPS, revenue, net income, assets, shares out) panel across the full local universe (~4,800 symbols incl. delisted) once tag-mapping is built. **Best published signal**: PEAD itself (Bernard & Thomas 1989/1990) is one of the most heavily replicated anomalies in the literature and, unlike the accrual/F-Score findings the 2026-09-18 brief already flagged as decayed, PEAD specifically still appears in modern factor libraries (Alpha158/OSAP-style panels we already hold) — this brief did not re-run a fresh performance number for it since that is the owner's own next scheduled step, not a gap in coverage.

---

## 5. Short borrow fee / utilization / availability history

| Source | What it is | Historical backfill? | Access | Verdict |
|---|---|---|---|---|
| [iBorrowDesk](https://www.iborrowdesk.com/) | Aggregates Interactive Brokers stock-loan fee + shares-available, per-symbol history **charts on-site** | The site itself has accumulated some history by polling IBKR, but no documented free bulk historical export/API was found (search-summary level; an unofficial "hidden" API returns current/recent only per third-party write-ups) | Scraping; ToS not verified this session — **flag before persistent scraping** | Forward-collect only for us |
| IBKR's own shortable-securities file | Official `usa.txt`-style FTP feed of current borrow rates/availability | **No historical archive on the FTP** (confirmed via a Portfolio123 community thread describing exactly this limitation) | Free, no login for the current file | Forward-collect only |
| [aziegenhirt/short-lend-dashboard](https://github.com/aziegenhirt/short-lend-dashboard) (GitHub) | Open-source tracker combining IBorrowDesk + MarketWatch + TheDesperateTrader, refreshed daily via GitHub Actions | Only as deep as its own collector has been running — itself a forward-collector, not a backfill source | Free, open source | Confirms: nobody has free multi-year borrow-fee history sitting anywhere |

**Verdict: this data type is free but forward-collect only — there is no free backfill anywhere we found.** That matters for evidentiary sequencing: we could start scraping today, but cannot backtest a borrow-fee-based signal against 2016-2024 history, and the one classic academic anchor for this construct (Engelberg, Reed & Ringgenberg 2018, *Journal of Finance*, "short selling risk") uses proprietary Markit/IHS securities-lending data, not anything free — so even a well-built free scrape from today forward is testing a different (thinner, retail-broker-only) data-generating process than the one the literature validated. **Coverage cell**: partially fills the gap the 2026-09-18 brief flagged (no free historical cost-to-borrow for squeeze/crowding signals), but only from whenever we start collecting, not retroactively. **Ingest effort**: ~2-3 hours to stand up a daily cron scrape; the decisive test (does this correlate with anything) can't run until months of forward data accumulate, so this is a "start the clock" item, not a near-term profit lever.

---

## 6. Holdings and flows: 13F, N-PORT, ETF daily holdings/creation-redemption

**13F**: already covered in depth by the 2026-09-18 brief (45-day structural lag, one uncorroborated 24.3%-alpha SSRN paper, free SEC bulk data) — not re-litigated here.

**N-PORT** (new this brief): [SEC DERA bulk data sets](https://www.sec.gov/newsroom/whats-new/2407-form-nport-data-sets), free, "as-filed" XML flattened to bulk files, covering **every N-PORT/N-PORT-A filing since October 2019** — mutual funds, ETFs (structured as open-end funds), and closed-end funds' *actual* monthly portfolio holdings (not just 13F's quarterly view, and covering position types 13F misses, e.g. bonds/derivatives). Key structural catch, confirmed via search-summary of the SEC/sec-api.io pages: **only the fiscal quarter's third month is disclosed publicly; the first two months of each quarter stay confidential** — so in practice this is a quarterly, not monthly, public feed, with its own multi-week disclosure lag (SEC rule targets roughly 60 days after quarter-end) — comparable in staleness to 13F, not better. **Ingest effort**: ~1 day, reusing the existing EDGAR-bulk-file collector pattern from `scripts/collect_sec_13d_filings.py`. **Coverage cell**: extends #6/holdings-flows to registered funds' own book (useful for "what does a specific tracked mutual fund/ETF actually hold," e.g. cross-checking a smart-beta ETF's true exposure) rather than adding a new alpha family.

**ETF daily holdings (portfolio composition files)**: since the SEC's 2019 ETF Rule (6c-11), transparent ETFs must post full daily holdings on a public website — but each issuer (iShares, SPDR, Invesco, ...) hosts its own **current-day-only** file with no centralized historical archive; Nasdaq Data Link lists an "ETFC" database that looked relevant but its pricing/licence was not verified this session (Quandl/Nasdaq Data Link's premium databases are mostly paid post-acquisition — **treat as unconfirmed, not assume-free**). **True creation/redemption unit-level data** (as opposed to resulting holdings) is not published anywhere free that this brief found; DTCC's ETF Processing is an institutional clearing service, not a public feed. The closest free proxy is deriving *net* flow from daily shares-outstanding/AUM deltas, which we'd have to build ourselves from whatever NAV/shares data we can source. **Verdict: real gap**, low feasibility without either scraping ~50+ issuer sites daily (forward-only) or paying. **Coverage cell**: #4 (资金流/结构性效应) stays mostly open on the ETF-flow side.

---

## 7. Other alt data with a published return link

### 7a. Wikipedia pageviews — verified live, fills an explicitly named coverage-map gap

Probed directly: `GET wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/Apple_Inc./daily/2015070100/2015070700` → HTTP 200, clean daily counts. Free, **no key**, daily granularity, per-article REST coverage from **July 2015** onward (the older, hourly `pagecounts-raw` dumps go back to 2007-2015 but in a messier format without bot/agent filtering — usable but lower quality). Counts are append-only publication stats, not later rescaled, which is a better PIT property than Google Trends' relative index (already flagged by the 2026-09-18 brief as revision-prone). No hard rate limit confirmed this session; be a considerate caller.

**Best published signal**: Moat, Curme, Avakian, Kenett, Stanley & Preis, *Quantifying Wikipedia Usage Patterns Before Stock Market Moves* (*Scientific Reports* 2013). DJIA constituents, 2007-2012 sample; a trading strategy on page-view changes for finance-related pages is reported to have returned up to 141% cumulatively, and a companion Google-Trends-based variant up to 297% — **author-reported, back-tested, transaction costs not mentioned**. The same paper reports its own **negative control**: neither edit-activity nor a placebo topic set (actor/filmmaker pages) showed predictive power — a genuine internal robustness check, but not a third-party replication, and I found no independent post-2013 replication in the time available (say "no independent replication found" rather than implying one exists).

**Coverage cell**: directly named in `docs/plan-research-coverage-2026-09-23.zh.md` §3 row 5 ("Wikipedia 浏览量（免费）") as a priority gap. **Ingest effort**: ~1 day for a name→Wikipedia-article mapping (the real cost — many tickers don't map 1:1 to a clean article title) plus a daily/weekly pull; the decisive test is cheap (pull 2016-2026 pageviews for ~200 large caps, check IC against forward returns, done in an afternoon once article mapping exists).

### 7b. Google Trends — cross-reference only

Already covered by the 2026-09-18 brief (weekly granularity, relative not absolute, non-PIT rescaling risk, post-2021 evidence points to decay/reversal). Nothing new found this session; not re-verified.

### 7c. Tranco (web-traffic rank list) — verified live, no signal found yet

Fetched `tranco-list.eu` directly: free, **no registration** to download, ranks blend Cisco Umbrella / Majestic / Farsight / Chrome UX Report / Cloudflare Radar averaged over a trailing 30 days; historical daily list snapshots are retrievable by list ID (good PIT property — each list is immutable and dated). Underlying source rankings carry mixed licences, including at least one CC BY-**NC** (non-commercial) component — fine for personal research, worth remembering if this project's scope ever changes. **No published stock-return signal using Tranco specifically was located in the time available** — this is a promising raw ingredient (proxy for consumer/DTC-brand web traffic momentum) with zero existing evidence base, not a validated source. **Coverage cell**: #5, but flag as "needs its own search pass before any ingest," not ready to rank on value.

### 7d. GitHub activity (GH Archive) — verified live, no signal found

`gharchive.org`: free, complete public GitHub event stream (commits, stars, forks, issues, PRs), hourly compressed JSON files from **2011-02-12** (pre-2015 via the deprecated Timeline API, 2015+ via the Events API), plus a BigQuery public dataset with 1TB/month free query allowance. **No academic paper linking GitHub commit/star activity to stock returns was found** — search only turned up papers predicting GitHub-repo popularity itself, not equity returns. Deep, clean, free, PIT-honest data with **zero evidence base** for our use case. **Verdict**: park it; do not spend engineering time without a signal to test first, consistent with the project's own "direction before effort" rule.

### 7e. Job postings and layoffs — two free sources, thin/indirect evidence

| Source | What | PIT | Access | Evidence |
|---|---|---|---|---|
| [DOL OFLC LCA disclosure data](https://www.dol.gov/agencies/eta/foreign-labor/performance) (H-1B/H-1B1/E-3) | Employer, job title/SOC code, worksite, wage, receipt/decision dates | Reasonable — released as quarterly files ~4-6 weeks after each fiscal quarter closes, i.e. release date is itself the visibility timestamp | Free, no key, large XLSX per quarter (~600MB) | No direct signal test found; nearest analogue (below) uses different, paid data |
| WARN Act layoff notices (state-published, aggregated free by e.g. [layoffdata.com](https://layoffdata.com/), [warntracker.com](https://www.warntracker.com/)) | Plant closing/mass layoff notices, 60-day advance notice by law | Notice-date based, reasonable | Free public records; aggregator ToS not verified | A study using 574 WARN-sourced downsizing events (author/venue not fully pinned down this session) reported plant-**closure** firms outperforming benchmarks by 7.9% over the following year, while plain layoffs (no closure) showed no effect — treat as weak/unverified secondary evidence pending a proper citation check |

The strongest *published* result adjacent to this category, Kothari & O'Doherty, *Job Postings and Aggregate Stock Returns* (*Journal of Financial Markets*, 2023), reports its job-openings-to-employment ratio beating 20+ other equity-premium predictors with an out-of-sample Sharpe of 0.47 vs 0.27 for the historical mean — but it is built on **paid** Burning Glass/Lightcast data and is a **market-level** (not stock-level) timing signal, so it validates the category, not our free H-1B proxy specifically. Also note: LCA employer names are free text, not mapped to CIK/ticker — the same entity-resolution cost `capabilities/registry.yaml` already flags for Form 4 issuer symbols would recur here. **Coverage cell**: #5/#3 (event-ish, company-specific hiring/layoff catalysts). **Ingest effort**: ~1-2 days once you add employer-name matching. **Verdict**: real free data, genuine but only indirect literature support — worth a cheap scoping test, not a priority build.

### 7f. Patents (PatentsView / KPSS) — cross-reference only

Already covered in depth by the 2026-09-18 brief (KPSS extended value data free through 2022, PatentsView raw grant data free and continuously updated). Nothing new found; one nuance already present in that brief bears repeating: the raw grant-event stream is current even though KPSS's *value* companion series lags to 2022.

### 7g. Government contracts (USAspending.gov), lobbying (LDA), congressional trades — cross-reference only

All three already covered in depth by the 2026-09-18 brief (practitioner-only evidence for contracts; mixed/no-consensus evidence for lobbying; congressional-trade evidence partly reversed by later independent work, with the NANC/KRUZ ETF track record cited as real-money evidence). Not re-verified this session.

### 7h. FDA calendar vs. ClinicalTrials.gov — new angle, distinct from what 2026-09-18 covered

The 2026-09-18 brief looked at *PDUFA decision-date* calendars and found FDA doesn't publish one; third-party calendars are practitioner narratives with no backtest evidence. This brief checked **ClinicalTrials.gov** specifically (trial-*readout* timing, a different and earlier catalyst than the PDUFA decision) and probed the live API:

- `GET clinicaltrials.gov/api/v2/studies/{nctId}` → 200, clean JSON (`protocolSection` with status/phase/sponsor/dates modules). Free, **no key** (NIH/NLM .gov data).
- Looked for a version-history endpoint to support true PIT replay: `GET .../studies/{nctId}/history` → **404**; `GET .../studies/{nctId}/versions` → **404**. The classic website's HTML "history" tab (`clinicaltrials.gov/study/{nctId}?tab=history`) does return 200, so per-study version history exists for a human but **is not exposed in the JSON API** — meaning this source is forward-collect-if-we-snapshot-it-ourselves for PIT purposes, not retroactively queryable for free.
- No documented rate limit found this session; treat as unconfirmed.

**No published-signal search was run for "trial primary-completion date → stock return" in the time available** — I am flagging this explicitly as unresearched rather than implying either a positive or negative finding. That search is the required next step before any ingest here. **Coverage cell**: #3 (biotech/pharma catalysts), currently the weakest-evidenced item in the FDA-calendar family per 2026-09-18; this source is more rigorous (official registry, structured fields) but its signal value is simply unknown yet.

### 7i. GDELT — cross-reference only

Already an existing `trial`-status capability (`news.gdelt` in `capabilities/registry.yaml`) with documented caveats (noisy, fetch-time visibility only, no reuse-rights guarantee for linked articles). No new search run this session; nothing to add beyond what the registry already records.

---

## 8. Other paid-feed substitutes

### 8a. Free NBBO/quote history for spread estimation — the cheapest item in this brief

No free source of genuine historical NBBO/consolidated-quote tick data was found (Databento, Polygon, Algoseek, WRDS TAQ are all paid or paid-with-a-one-time-credit-that-needs-a-payment-method — the latter is explicitly out of scope under the "no sign-ups, no payment methods" rule). IEX's own free historical DEEP/TOPS files exist but are IEX-only volume (~2-3% of the tape), already implicitly acknowledged by `market.alpaca_bars`'s "free IEX feed is not consolidated full-market SIP data" caveat.

**The better answer is to not acquire a new data source at all.** We already hold SIP-consolidated OHLC minute and daily bars for the full local universe (2016-2026). Corwin & Schultz, *A Simple Way to Estimate Bid-Ask Spreads from Daily High and Low Prices* (*Journal of Finance*, Vol. 67, 2012) give a closed-form effective-spread estimator using only daily high/low prices — no quotes needed. This is a genuinely well-adopted estimator: beyond the original paper, it has been extended and reused by unrelated researchers across asset classes (e.g. an extension to corporate-bond spreads, and newer GMM-based estimators that benchmark against it), which is about as close to "independently validated by adoption" as market-microstructure tooling gets — though it carries a known downward bias for thinly-traded names, which matters for our smaller-cap universe and should be reported alongside any use of it, not silently.

**Ingest effort: effectively zero** — this is a formula over data we already own, computable in under an hour for the full universe. It directly serves the project's own promotion-gate requirement to check "costs, data source sensitivity" (CLAUDE.md) and the `execution-reality-reviewer`/`backtest-forensics` skills' TCA requirements, for which we currently have no free per-name liquidity/cost proxy beyond raw dollar-ADV. **Coverage cell**: not a new alpha cell, but unlocks a cost-hygiene input every other cell's promotion review needs.

### 8b. ALFRED — vintage/point-in-time macro, fixes an existing documented gap

Verified via multiple corroborating official/near-official sources (St. Louis Fed's own `alfred.stlouisfed.org`, the FRED API docs, the `fredapi` PyPI wrapper, Wikipedia's FRED article): **ALFRED (ArchivaL FRED)** has been live since 2006 and serves **vintage** values for FRED series — i.e., what a series' value looked like as originally published, before subsequent revisions — via the *same* FRED API, using `realtime_start`/`realtime_end` parameters per observation. This is served through the identical `FRED_API_KEY`-gated endpoint the existing `macro.fred_series` capability already uses.

This is a near-exact fix for a gap `capabilities/registry.yaml` **already documents against itself**: `macro.fred_series`'s own caveats say "the current observations endpoint is a latest snapshot, is revision-prone, and supplies no historical vintage identity." ALFRED closes that with no new credential, no new provider, just different query parameters on a capability we already have `trial` status for. This is infrastructure, not a standalone alpha source — its value is preventing look-ahead bias in any macro-conditioned rule (e.g., a GDP/payrolls/ISM regime gate that would otherwise silently condition on numbers not actually knowable at the time), which is exactly the kind of PIT correctness CLAUDE.md requires ("News, event, macro, LLM inputs must become point-in-time feature packets before they can affect trading behavior"). Real-time-vintage macro data is standard academic infrastructure (Croushore & Stark's 2001 real-time dataset is the field's foundational, widely-cited methodology reference), not a novel or contested idea.

**Ingest effort: 1-2 hours** to add vintage parameters to the existing FRED collector. **Coverage cell**: fixes #11 (跨资产/宏观状态) at the infrastructure level, applicable to anything already or later using macro gates (e.g. the batch-3 defense-rotation work mentioned in `docs/current-view.zh.md`).

---

## 9. Ranked top 10 (value for near-term, after-cost, long-only US-equity profit × feasibility)

| # | Source | Value | Feasibility | Why |
|---|---|---|---|---|
| 1 | **SEC XBRL as-first-reported fundamentals** (companyconcept/frames + bulk Financial Statement Data Sets) | High — unlocks PEAD + fundamentals, the owner's own next-scheduled item | High — free, keyless, restatement handling verified live; tag-mapping is real but bounded work | Directly matches `docs/plan-research-coverage-2026-09-23.zh.md`'s 09-26/09-27 plan; restatement question answered with a live example |
| 2 | **Corwin-Schultz spread estimator on existing bars** | Moderate (cost hygiene, not alpha itself) but required by the promotion gate for every other candidate | Extremely high — zero new data, an afternoon of coding | Cheapest possible item in this brief; peer-reviewed, widely reused estimator |
| 3 | **ALFRED vintage macro** | Moderate — bias-prevention infrastructure, not a standalone P&L source | Extremely high — same key we already hold, 1-2 hours | Fixes a gap `capabilities/registry.yaml` already calls out against itself |
| 4 | **Alpaca free historical options (Feb 2024+)** | Moderate-high — unlocks a fully empty coverage cell | High — creds already held, but 31-month depth caps backtest ambition | Directly answers the plan doc's open options-feasibility question |
| 5 | **SEC Form N-PORT bulk data** | Low-moderate — same lag profile as 13F, no independent signal evidence | Moderate-high — free, reuses existing EDGAR collector pattern | Extends holdings/flows coverage to funds' actual books |
| 6 | **Wikipedia pageviews API** | Low-moderate — one 2013 paper, no independent replication found | High — verified free/keyless/PIT-decent | Named explicitly in the owner's own coverage-gap list; cheap decisive test |
| 7 | **ClinicalTrials.gov trial-readout calendar** | Unknown — no signal search run yet | Moderate-high — free, well-structured, but PIT only if we self-snapshot (no history API) | More rigorous than the already-checked PDUFA-calendar dead end, but needs its own literature pass first |
| 8 | **H-1B LCA + WARN layoff data** | Low-moderate — adjacent literature uses paid data for a market-level signal; free-data event study is thin | Moderate — free, but real entity-resolution cost (employer name → ticker) | Two distinct free government sources, genuinely PIT, weak direct evidence |
| 9 | **iBorrowDesk / IBKR shortable list** | Moderate if it ever pans out (fills the crowding/squeeze data gap) | Low near-term — forward-collect only, no free backfill, ToS unverified | Start the clock, don't expect a near-term backtest |
| 10 | **Tranco web-traffic ranks** | Unknown — no signal found | High — verified free, no signup, PIT-clean by list ID | Cheap raw ingredient; needs its own search pass before any ingest work |

**Explicitly left out of the top 10, with reasons**: GH Archive (deep, free, zero evidence base found — park it per "direction before effort"); ETF daily holdings/creation-redemption (no free bulk historical archive exists); Estimize (best free-ish analyst-estimate fix, but blocked by the no-signup hard rule — an owner decision, not an ingest task); earnings call transcripts (confirmed dead end, stale one-off academic snapshots only).

---

## 10. Recommended first ingest

Build the **SEC XBRL as-first-reported fundamentals pipeline**, starting narrow: pull `companyconcept` EPS (`us-gaap:EarningsPerShareDiluted` or similar) and Revenue for the existing top-500-ish liquid universe back to 2009, apply the "minimum `filed` date per (concept, end) pair, watch for later rows with a changed `val`" restatement filter verified live in §4, and compute a standard PEAD-style surprise feature (actual vs. a naive prior-year-same-quarter or trailing-estimate baseline, since we don't have a free consensus number per §2) against forward returns. This is the single highest-leverage item because it is independently corroborated three ways: it is free and keyless with fields verified against the live API (not just documentation), it fills two coverage-map cells at once (#3 event/PEAD and #7 fundamentals), and — most importantly — it is literally the next thing the owner's own `docs/plan-research-coverage-2026-09-23.zh.md` execution plan schedules (09-26 to 09-27), so this is confirmation the direction is sound, not a new proposal competing for attention.

**Cheapest test that would kill it**: before building the full tag-mapping/multi-concept panel, pull just `EarningsPerShareDiluted` via `companyconcept` for ~50 liquid names for 2016-2025 (an afternoon), apply the restatement filter, and check whether a simple "surprise vs. own trailing-4-quarter average" sorted quintile shows a monotonic, cost-surviving return spread in the days after the *filed* date (not the period end date). If the spread isn't there even in this classic, heavily-replicated construct on free data, that is strong evidence the effort is not worth scaling to the full universe — this mirrors the project's own "cheapest decisive test before scaling" discipline and reuses infrastructure (EDGAR collector patterns, point-in-time visibility rules) we already have rather than inventing new plumbing.

Do the two near-zero-cost items (§8a Corwin-Schultz spread estimator, §8b ALFRED vintage parameters) in parallel the same day — neither competes for the same engineering time and both remove standing caveats already written into the registry/promotion gates.

---

## 11. Owner actions needed (things this brief cannot do under the hard rules)

- **Estimize academic access** (§2): closest free-ish fix for point-in-time analyst consensus, but requires either contributing estimates or requesting academic access — a registration decision, not something to activate unattended.
- **iBorrowDesk / borrow-fee scraping** (§5): terms of use were not verified this session; confirm before standing up a recurring scrape.
- **Nasdaq Data Link "ETFC" database and any similar aggregator** (§6): pricing/licence not confirmed this session — do not assume free.
- **Databento's one-time free credit** (§8a): requires a payment method on file; out of scope under the no-payment-method rule, noted only for completeness.

All URLs above were accessed 2026-09-23. Nothing in this brief modifies code, specs, or `capabilities/registry.yaml`; recommendations name the registry entries a follow-up engineering task would touch (`options.trial_chain`'s unconfigured `provider` field, a new `fundamentals.sec_xbrl` entry, `macro.fred_series` vintage parameters) without editing them here.
