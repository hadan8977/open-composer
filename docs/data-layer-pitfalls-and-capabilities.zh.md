# Data pitfalls and capability inventory

This is a reference inventory, not a schedule or resource admission. Status labels below preserve the documented findings through the last additions on 2026-10-06; they are not a fresh code/provider audit. Keep discovered failure modes and their evidence when updating a status. Historical reports and source snapshots remain the evidence of record.

Sources include [the IEX adjustment investigation](finding-iex-cache-price-adjustment-defect-2026-09-01.zh.md), [the kernel-search review](review-kernel-search-2026-09-01.zh.md), and [the capability-gap analysis](capability-gap-analysis-2026-09-02.zh.md). `Fixed`, `Partial` and `Open` describe those recorded states; `Observed` means this project encountered the failure. The original inventory used #9 twice; both references remain below. Old summary totals were inconsistent, so they are not a current coverage metric.

## Price identity and point-in-time data

| ID | Failure/capability | Recorded status | Evidence and operational implication |
|---|---|---|---|
| 1 | Unadjusted splits create false crashes | Fixed; observed | Six roughly -50% TQQQ/QLD daily jumps in the IEX cache; none in matched SIP. |
| 2 | Missing dividend adjustment erases cash-leg return | Fixed; observed | BIL annualized 2024-2026 return was 0.01% in IEX versus 4.42% in SIP. |
| 3 | Survivorship bias from active-only assets | Open; observed | SIVB/FRC/TWTR/ATVI/VMW/CS were absent from the active universe, while QQQ/AAPL/MSFT had 2,680 rows each. Direct SIP requests returned delisted-name history (SIVB: 297 rows through 2023-03-09), but the 19,187-name inactive list omitted those names. External historical membership/delisting evidence is needed. |
| 4 | Irreversible adjustments and batch seams | Open; observed | Store raw prices plus dated corporate-action factors to reproduce vintage views. The account's corporate-action API was usable in the recorded check; pre-2020 raw/all ratios were a possible fallback. In T-20261004-55, SHY seams near +0.30% across appended batches distorted its 63-day return by 0.285 percentage points: an UPRO-versus-SHY margin was only 4.7 bp. The paper/backtest gap was 3.75% over nine days. Archive repair/rewrite removed those seams, but raw-plus-factor storage remained unfinished. |
| 5 | Missing bitemporal/vintage model | Open | Preserve `event_time` and `knowledge_time`; revised fundamentals/macro are not their historical vintages. FRED's `realtime_start`, `realtime_end` and `vintage_dates` provide the ALFRED route with the same key. |
| 6 | Reused tickers merge distinct securities | Open | Use permanent identity such as PERMNO/FIGI; bars `asof` can resolve dated renames but was not used locally. A ticker alone does not establish security continuity. |
| 7 | Missing historical universe/index membership | Open | Cross-sectional eligibility must be reconstructed at the historical decision date, rather than from current constituents. |
| 8 | Unpinned feed/adjustment | Fixed | `frame.attrs` records feed and adjustment; provider feed was disabled in `auto_research`. SIP parquet specs use `data.source: alpaca` plus `data.path: data/sip/daily`; `sip_parquet` is a mode, not a supported source Literal. `load_ohlcv_for_spec`, `fetch_ohlcv` and `load_daily_dataset` propagate `frame.attrs["data_source_mode"]="sip_parquet"` into reports. |
| 9 (price hygiene) | Relistings, bad prints and missed splits bypass sanitization | Partial; observed | T-20260929-20 found WOLF 1.21 to 22.1 after restructuring (a false -1,757% short result), KIDZ 510 to 9.495 to 421, IXHL 4.76 to 0.167 to 4.24, and an unadjusted APH 161.34 to 80.69 split. Apply the contract below. |

Every stock-level backtest using `data/sip/daily` must pass close/open matrices through `open_composer.research.features.price_hygiene.sanitize_price_matrices` with defaults and report `PriceHygieneReport` counts. Its large-jump/suspension checks do not capture every small-ratio split. Exclude split-like signals on the trigger session only; never filter by hold-window outcomes, which can remove real short squeezes. In the recorded 2024-2026 scan, 62 sessions matched common split ratios within 2%, but some were real news moves (NBIS +49%, CRNX +99%). Corporate actions can enter the existing `known_corporate_actions` hook; verify the source and applicability before treating that as a complete repair.

## Time and resampling

| ID | Pitfall | Recorded status | Evidence/required handling |
|---|---|---|---|
| 9 (sessions) | Extended-hours contamination | Open | 1,903 of 3,463 QQQ minute bars in a sampled week were outside regular hours. Filter the session before aggregation. |
| 10 | Arithmetic-mean VWAP | Open | Aggregate as `sum(vwap * volume) / sum(volume)`. |
| 11 | Hourly bars anchored to clock hours | Open | Regular sessions start at 09:30; plain `resample('1h')` shifts boundaries. Use `market_calendar.expected_us_equity_rth_bar_starts()`. |
| 12 | Missing-minute coverage invisible in schema | Open | Alpaca omits no-trade minutes; VUSE had only 59 bars in a week. Track coverage before treating sparse aggregates as complete bars. |
| 13 | Half-day partial bars | Open | Use `market_calendar.us_equity_session_close()` and account for incomplete final intervals. |
| 14 | Minute-derived daily bars miss official daily tape | Open | Opening/closing auctions make the official daily bar differ; use daily data for daily prices. |
| 15 | Silent archive staleness | Fixed; observed | Skipping existing shards left the retired IEX cache frozen at 2026-08-04 while callers kept using it. |
| 16 | Shard IDs change meaning with batch size | Fixed; observed | Changing `BATCH_SIZE` from 40 to 12 reassigned symbols to the same shard number; a larger batch could silently omit data. Bind actual symbol/date content. |

## Tradability and scale

| ID | Gap | Recorded status | Implication |
|---|---|---|---|
| 17 | Liquidity/ADV eligibility | Open | A selected symbol such as VUSE may be impossible to execute. |
| 18 | Actual bid/ask spread | Open | Fixed 20 bp slippage is not measured NBBO spread. |
| 19 | Size-dependent market impact | Open | Evaluate an actual participation/size model, such as square-root impact or Almgren-Chriss. |
| 20 | Auction execution | Open | Opening/closing auctions account for substantial volume; simulated auction fills need separate evidence. |
| 21 | Borrow availability and fees | Open | A short return is not executable without dated borrow evidence and costs. |
| 22 | Minute-panel memory | Fixed; observed | Ten symbols for one quarter used about 1 GB RSS; one year exhausted the small host. Use [memory admission](runbook-memory.zh.md), chunking and admitted remote compute. |

## Evaluation failure modes

These findings were recorded as fixed by the kernel-search review; new search implementations can reintroduce them.

| ID | Failure | Evidence or safeguard |
|---|---|---|
| 23 | A fixed parameter set is called workflow validation | Existing `router_common.walk_forward_router` reselects within folds; the separate kernel implementation originally did not. |
| 24 | Selection sees OOS under a misleading name | All 1,240 `development_fold_returns` values equaled `oos_return_stream`. Verify actual partitions, not labels. |
| 25 | DSR trial count includes only survivors | Sixty candidates became five, then three clusters; this is not three trials. `campaign.py` forbids clustering a hand-picked subset to reduce exposure. |
| 26 | Fixed lookahead-probe blind spots | Probes at 40%/90% missed date-anchored tail leakage. More probes alone do not repair the validation premise. |
| 27 | Success thresholds can change after results | Bind the committed, unchanged frozen contract and `promotion_eligible`. |
| 28 | Inconsistent metric denominators | `raw_candidate_count=65` alongside a breadth ratio using six as denominator implied the wrong scale. |
| 29 | Near-cash signals inflate raw Sharpe | Tiny variance plus slight positive drift creates huge ratios; shared quality checks need a suitable floor without discarding real defensive strategies. |
| 30 | Structural pass counted as empirical success | Capture gates can pass automatically for uncorrelated QQQ returns; disclose the distinction. |
| 31 | Zero detector hits treated as proof | `rejected_lookahead_count: 0` also fits a dead detector. Inject a known violation to validate the relevant guard. |
| 32 | Frozen structure hides selection noise | Fold-wise GP evolution changed churn from 0.25 to 1.00 (five different structures in five folds); the frozen pool had concealed it. |
| 33 | Absolute adjusted-price operators | Back-adjusted historical levels are not the prices visible then (for example BIL at 81.74). GP terminals moved to ratios. |

Actual PBO/DSR definitions and trial accounting belong to [backtest-forensics](../.agents/skills/backtest-forensics/SKILL.md), not another local proxy definition.

## Search and additional data capabilities

| ID | Capability | Recorded gap or research caveat |
|---|---|---|
| 34 | Multi-period resampling | Open: jointly handle sessions, coverage, VWAP, half days and official daily bars (#9-14). |
| 35 | Feature store | Open: PIT semantics plus content-hash caching for reusable computation. |
| 36 | Cross-sectional universe | Open in the original search inventory, which searched QQQ/BIL; later studies do not retroactively fix that evidence. |
| 37 | Columnar queries | Open: investigate DuckDB/Polars direct parquet queries rather than repeated shard scans; no performance guarantee without measurement. |
| 38 | Persisted shard index | Open: recorded cold starts were 15 seconds for daily and 47 for minute data per process. |
| 39 | Options-derived IV/skew/gamma features | Candidate capability; historical coverage and access still need evaluation. |
| 40 | LLM features with a valid information clock | A later-trained model may know outcomes of old news. Extraction-only tasks or a model predating the test can mitigate some risk; record model cutoff and remaining contamination limits. |
| 41 | Order-flow/microstructure features | Candidate signed-volume/Kyle-lambda work; minute bars do not automatically provide true order-book evidence. |
| 42 | Shared regime features | Candidate common data product rather than separate undocumented labels per strategy. |
| 43 | Synthetic augmentation | Generated artifacts can become spurious learnable signals; require controls. |

## Evidence and operational gaps

| ID | Failure | Recorded status | Evidence and qualification |
|---|---|---|---|
| 44 | Accepting agent summaries without raw artifacts | Fixed; observed | A claimed 47 degraded cases corresponded to 108 artifacts; a claim that all eight gates failed contradicted three passes. |
| 45 | Rebuilding existing solutions without inspection | Fixed; observed | Existing `campaign.py`, `router_common.py` and `optimizers/` already covered several attempted reinventions. |
| 46 | Missing scheduled post-close refresh/alerting | Open in the September check | Fetch/freshness tools existed, but crontab was empty and paper systemd units masked then. This is not today's scheduler status. |
| 47 | Paper and research feed mismatch | Open | Runtime `ALPACA_DATA_FEED=iex`/`data_feed()` versus SIP fetch scripts; trace each affected path. |
| 48 | Different cost accounting across engines | Open | `backtest_engine.py` used per-trade multiplicative costs; `router_common.backtest_router_params` used L1 turnover. Existing reference parity covered only the former. |
| 49 | Negative weights omitted from returns but charged turnover | Open | The review identified `if weight > 0` in `router_common.py`; do not assume a long/short backtest handles this correctly without inspection. |
| 50 | Walk-forward without embargo | Open; observed | `router_common.walk_forward_router` used `end_index=test_start`; a newer nested implementation had not replaced all router CLI paths. |
| 51 | Impact labels hide constant bps | Open | `_impact_rate` mapped square-root to `eta/1e4` and Almgren-Chriss to `(eta+gamma)/1e4`, with no actual size dependence. |
| 52 | Nautilus readiness label lacks parity evidence | Open | A single-symbol guard and empty `reports/parity/` did not justify a `nautilus_backend` readiness check. |
| 53 | Alerts never delivered | Open; observed | The recorded notification log had 24 rows; Telegram was disabled and skipped 23/23, with no email route then. Do not infer current delivery. |
| 54 | TCA gates without observations | Open | The recorded `paper_tca.py` report had `valid_observation_count: 0`; broker fills were not automatically observations. |
| 55 | Paper opening/closing auctions unreliable | Partial; account tests recorded | The October probes accepted `cls` but had incomplete fills: three CLS orders, two filled (SPY); two OPG orders, none filled. Quant1's test SPY position was later closed; quant2's short AAPL expired unfilled. The cited Alpaca staff account described paper CLS as market-at-close quotes with possible random partials, not actual auction price, and live MOC as generally requiring Elite routing. These are historical account/source findings, not newly verified provider rules. Use the runner's regular-hours flattening and fresh source verification for design changes. |
| 56 | Day-trading rule assumptions | Partial; historical external claim | The old inventory recorded SEC approval on 2026-04-14 and effectiveness on 2026-06-04 under FINRA Notice 26-10. This cleanup did not verify that legal claim. Verify current primary rules before using it for an execution decision. |
| 57 | Central readiness lacks LLM contribution result | Open | `llm_contribution_pass` was hardcoded `None` in the reviewed `paper_readiness.py` path; a named requirement is not evidence of passing it. |
| 58 | Daily Abdi-Ranaldo spread overestimation | Open; observed | `ml30.spread_estimate_from_ohlc` produced median 36 bp on 2024+ P500 and 26 bp on AAPL versus a 0.43 bp tick: 20-60x too large. T-13 costs were invalidated by amendment A1 (2026-09-30). For `dv21 >= $20M`, use measured Alpaca NBBO, not this daily-volatility proxy. |
| 59 | Minute/daily adjustment mismatch | Open; observed | Of 2,446 names in 2025, 30 had median log-level gaps above 0.4%, 74 above 0.1%. Mixing daily close and minute prices created most of T-13's apparent 17.1 bp edge (2.3 bp gross after removal). Align same-day factors or use a 5 bp consistency bound instead of 10%. Trades/quotes are raw; compare with adjusted daily bars only after applying that day's factor derived from raw daily data. |
| 60 | v1.2 returns indexed by decision date | Partial; observed | `data/research/book_v12/A1_*_F{1,2}.parquet` row t realizes a t+1 closing-auction to t+2 close trade. Its SPY return matches t+2 SIP close-to-close (correlation 1.000; 99.96% within 1e-4). T-20261002-43's unaligned F2/S3 correlation was -0.01 instead of 0.51; C2/F2 was 0.08 instead of 0.88, invalidating the first run. Before correlations, combinations or calendar attribution, shift two sessions with `scripts/run_program_dd30_allocation.py:realization_dated()`; see `tests/test_program_dd30_allocation.py`. Preserve the files' decision-date convention. |
| 61 | Double conversion of 8-K acceptance timestamps | Partial; observed | `data/features/earnings_events/{2024,2025,2026}.parquet` stored true UTC interpreted again as ET, delaying it four/five hours. T-20261004-51 misclassified premarket events; 98.3% of the affected positive controls were already near-certain at the signal time. Eleven EDGAR Accepted-page spot checks and 1,055 matches supported the correction. Until repaired, use each index page's ET Accepted timestamp for pre/postmarket or intraday alignment. This is delayed visibility, not an earlier-time leak. A separate 10-K submissions finding does not generalize to this table. |
| 62 | Final quarterly ladder changes historical SUE | Open; observed | A late 10-Q altered 67 earlier SHPH rows. Rebuild the ladder by filing date for PIT values. T-20261004-54 quantified differences of 30-1,211 `sue_eps` rows/year across 1-13 names (at most 0.12%); non-SUE differences in T-22 were refresh revisions rather than this ladder leak. The recorded v1.2 M0 impact was immaterial; the leak remains a distinct issue. |
| 63 | Full-year median market-cap fallback leaks forward | Open; observed | About 20% of rows used `adv_fallback`/`adv_fallback_outlier`: full-year median `close * shares / dollar_adv_21` in 250-ADV-rank buckets, multiplied by ADV. Replace with a trailing 252-session median strictly before t; actual buckets use round-half-even. T-54 found 16-43% of U3000 market caps and 6-12% of ep/bm/sp/cfp values changed; daily-rank p5 was 0.986-0.991, combined-score p5 0.999 and recent M0 IC changed -0.3% relatively. Small portfolio impact does not make the definition causal. The original repair task was T-20261004-57. |
| 64 | Rebuilding a partition imports all intervening restatements | Partial; observed | CMND triggered a 2022-2025 rebuild that also imported earlier archive repairs, causing nsi to gain 1,620/lose 1,750 keys. `--init-cursor` had marked repairs handled without rebuilding older partitions. Commit `5e1f3fd` allowed `keys_follow_prices` key changes only for relevant later-detected, same-year restatements with split-level size >=0.2 or row-count changes; 88 symbols passed with zero unexplained keys. Keep the first backup/build time for repeated runs that day. The recorded 2016-2021 partitions still had seams at 2021/2022 (48 split/row-count cases and roughly 4,500 dividend cases); cross-boundary research needs a rebuild. The then-current v1.2 target used 2024+ history and was unaffected. |
| 65 | Price-derived levels have stricter gates than price inputs | Fixed; observed | `short_interest.adv_shares_63`/`short_interest_ratio` changed after permitted volume/dividend revisions. Commit `559a869` used `values_follow="daily"`: compare only through the last date minus three sessions and exclude/report rows for symbols restated after partition construction, including dividends. One check excluded 116 symbols and found zero changes in the other 142,141 rows; FINRA source columns were unchanged. Insider/short-volume/news tables did not depend on price levels. |

Registry admission and strategy-specific readiness belong to [capability-evaluator](../.agents/skills/capability-evaluator/SKILL.md) and [data-capability-reviewer](../.agents/skills/data-capability-reviewer/SKILL.md). A historical fix, a successful pipeline run or a small measured impact does not by itself establish current PIT correctness, profitability or paper readiness.
