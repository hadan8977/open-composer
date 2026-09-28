# Registry backfill 2026-09-28 (T-20260928-05)

Executor pass. No backtests were run for this task; all rows below restate
conclusions that were already reached in existing report files. Appended
34 rows to `reports/research/harvest/directions.jsonl` (21 new + 2
evidence-only updates for Job A, 11 judged for Job B). `oc research
directions validate` is **ok, 0 problems** after the append.

## Job A: backfill

### Source list built

- Iteration folders under `reports/research/iterations/` not starting with
  `h2026`: 52 folders (`/tmp/iter_folders.txt`).
- `reports/research/control/*.md` containing a verdict marker
  (结论/verdict/0/N/通过/否定): 29 files.
- Distinct `family` values in `reports/research/ledger/experiments.jsonl`:
  `groupb_recent_regime_high_hit_rate`, `step11_baseline_chain`,
  `step13_recent_high_return`.

### New directions (missing from the registry before this pass)

| direction id | source report path | status | one-line verdict |
|---|---|---|---|
| `dir:step10_beta_exposure_vol_managed_router` | `reports/research/control/step10-w1-beta-exposure-2026-09.md` | refuted | 0/24: de-risking lowers drawdown but excess CAGR (best +0.99pp vs >=5pp) and Sharpe-ex-BIL (best 0.59 vs >1.0) never clear the vol-matched-benchmark gate |
| `dir:step10_cross_asset_trend_tsmom_etf` | `reports/research/control/step10-w1-cross-asset-trend-2026-09.md` | refuted | 0/12: cross-asset TSMOM on 10 ETFs+BIL, same failure mode as beta exposure (best excess CAGR +1.33pp, best Sharpe-ex-BIL 0.65) -- the direction named in this backfill's brief as the missing example |
| `dir:step10_xsmom_pit_liquidity_liquid500` | `reports/research/control/step10-w2-cross-sectional-liquid500-2026-09.md` | refuted | 0/4: only family where the capture gate itself also fails (0.97-0.999 vs 1.0); survivorship bias confirmed non-material for this filtered universe |
| `dir:step10_sleeve_combination_beta_crossasset` | `reports/research/control/step10-w3-combination-2026-09.md` | refuted | 6/8 gates: combining the two failing Step-10 sleeves raises Sharpe-ex-BIL to 0.743 and excess CAGR to +2.44pp, still short of >1.0/>=5pp |
| `dir:core_satellite_momentum_sector_etf_r7` | `reports/research/control/us_core_satellite_momentum_r7-memory.md` | refuted | no candidate selected; DSR 0.578 failed 0.95 gate, contract-validity problems invalidated workflow_pass; best later-cited candidate 18.98% CAGR still below the TQQQ anchor that triggered the R8 pivot |
| `dir:dynamic_theme_semantic_chain_momentum` | `reports/research/iterations/mom_pit_semantic_theme_r24/decision-record.md` | refuted | 17 rounds (R8-R24), none cleared its own development gate; terminal R24: stop this price-history transformation line |
| `dir:etf_structural_family_daily_r9` | `reports/research/iterations/mom_etf_structural_family_r9/decision-record.md` | refuted | only promotion-eligible candidate (R9D04) failed the frozen benchmark-Sharpe hurdle and cumulative-DSR (0.208 vs 0.95) gates |
| `dir:minute_bar_momentum_multipath` | `reports/research/iterations/mom_minute_r2/decision-record.md` | partial | R2 lockbox passed all 5 preregistered gates (Sharpe 1.88) but lagged naive momentum (39.7%) and TQQQ B&H (54.8%); ML challengers (R3) each won only 1/3 folds |
| `dir:multiscale_intraday_event_r5` | `reports/research/iterations/mom_multiscale_event_r5/decision-record.md` | refuted | no deterministic candidate cleared every frozen gate; placebo pass was False |
| `dir:multiscale_low_turnover_etf_r6` | `reports/research/iterations/mom_multiscale_low_turnover_r6/decision-record.md` | refuted | contract-invalid (40% symbol-cap violation, non-self-financing accounting) -- no valid historical result at all |
| `dir:robust_momentum_deterministic_ml_r4` | `reports/research/iterations/mom_robust_momentum_r4/decision-record.md` | refuted | both deterministic and ML allocators stopped; ML path also failed its own shuffled-label control |
| `dir:spy_dual_trend_core_r8` | `reports/research/iterations/mom_spy_dual_trend_core_r8/decision-record.md` | refuted | passed return/drawdown/fold checks but failed the matched 40/60 SPY-cash Sharpe gate (0.737 vs 0.887) and DSR (0.075) |
| `dir:nasdaq_long_short_event_router_1m` | `reports/research/control/nasdaq_long_short_event_router_1m_sweep_002-memory.md` | partial | research_pass with strong walk-forward support on cached/IEX data, but not paper-ready (cached_live tier) and needs short-selling authorization the owner has not granted |
| `dir:multiasset_ml_ranking_vs_12_1_baseline` | `reports/research/iterations/mom_multiasset_ml_r1/decision-record.md` | refuted | four rounds (R1/R2/R3 + ML variants), no ML/AI ranker ever beat the frozen deterministic 12-1 momentum route-selection baseline |
| `dir:tqqq_post_drawdown_reentry_router` | `reports/research/control/strategy-iteration-progress-2026-07-01.md` | refuted | former paper champion route; 2026-09-02 SIP re-verification confirms qqq_capture_ratio still fails, ~half of QQQ upside given up for almost no drawdown protection |
| `dir:pdr_router_ml_gate` | `reports/research/control/strategy-iteration-progress-2026-07-01.md` | refuted | two ML-gate iterations on the PDR router, both `ml_gate_beats_fixed_route=False`, both degraded crisis-window protection |
| `dir:single_etf_intraday_momentum_cost_adjusted` | `reports/research/control/goal-first-2026-09-02-progress.md` | refuted | 0/36 candidates promotable; Sharpe-excess-BIL negative for both SPY and QQQ variants |
| `dir:groupb_recent_regime_screen` | `reports/research/control/step12-groupb-recent-regime-2026-09.md` | partial | best candidate (F1, ETF pullback MR) 7/8 gates, short only on absolute-return magnitude; leveraged reference variant (F5) clears CAGR but fails everything else |
| `dir:ml_ranking_liquid500_recent_vs_momentum_rule` | `reports/research/control/step13-recent-high-return-2026-09.md` | refuted | 480-factor screen (5 libraries) + cross-sectional ML ranking, every cell loses to a simple risk-adjusted-momentum rule baseline (33.7%/yr) net of cost |
| `dir:reversal_trend_user_indicator` | `reports/research/control/step13-recent-high-return-2026-09.md` | refuted | user's reconstructed indicator: daily event study "informative: no"; hourly 18-cell grid 0/18 gates pass |
| `dir:baseline_chain_b0_b1_b2_market_neutral_vs_long` | `reports/research/control/step11-w2-model-ranking-2026-09.md` | refuted | B0/B1/B2/B3 chain, best is B1 (12-1 momentum, 4/8 gates); ridge and LightGBM both lose to B1; market-neutral (SPY-beta-hedged) variants uniformly worse |

### Already-present directions (evidence path added, status unchanged)

| direction id | source report path | status | one-line verdict |
|---|---|---|---|
| `dir:short_interest_avoidance_gate` | `reports/research/control/short-interest-precheck-2026-09-17.md` | refuted (unchanged) | already fully captured; added this report's path to evidence |
| `dir:short_interest_ratio_crowding_factor` | `reports/research/control/short-interest-precheck-2026-09-17.md` | refuted (unchanged) | already fully captured; added this report's path to evidence |
| `dir:giants_sweep_published_etf_rules` | `reports/research/iterations/giants_sweep_20260922/report.md` | refuted (unchanged) | already cites this exact report as its source; no update needed |

### Not backfilled (no concluded verdict to backfill)

These folders/files were reviewed and found to have **no completed
decision** (still "pending", mid-setup, or never reached a candidate
return), so there is no conclusion to register under the brief's four
target statuses (refuted/partial/passed/evidence_too_weak). Listed here
for transparency rather than silently skipped:

- `mom_breadth_calendar_flow_r1`, `mom_breadth_crossasset_trend_r1`,
  `mom_breadth_cross_session_r1`, `mom_breadth_pit_xsmom_r1`,
  `mom_breadth_short_reversal_r1`, `mom_breadth_static_hotspot_control_r1`,
  `mom_breadth_volatility_beta_r1` -- all 7 record `Decision: pending`,
  no candidate return inspected yet.
- `mom_multiasset_forward_multimodal_r4/r5/r6` -- all `workflow_pass=false,
  research_pass=false`, no historical result authorized.
- `mom_etf_core_diversifier_forward_r10` -- "pending forward evidence",
  successor of the now-registered `dir:etf_structural_family_daily_r9`.
- `mom_high_beta_sleeve_ensemble_r1` -- pending, evaluation not yet run.
- `mom_vix_term_structure_overlay_r1` and its `_implfix1` variant --
  evaluation forbidden until pre-backtest gates pass; never run.
- `mom_dynamic_theme_stock_r9`, `mom_event_seeded_theme_stock_r10`,
  `mom_stock_intraday_codesign_q1` -- intermediate pivots folded as
  evidence into `dir:dynamic_theme_semantic_chain_momentum` /
  `dir:minute_bar_momentum_multipath` rather than registered separately.
- `mom_multiasset_paper_control_r7` -- an ex-ante equal-weight broker-free
  operational control, not itself a tested alpha candidate; mentioned as
  context inside `dir:multiasset_ml_ranking_vs_12_1_baseline`.
- Control docs reviewed and judged to be infra/audit/survey documents
  without a strategy-mechanism verdict (skipped): `audit-2023-minute-
  layout-2026-09-24.md`, `decision-s3-live-pilot-2026-09-24.zh.md`,
  `next-iteration-readiness-20260703.md`,
  `research-loop-designs-survey-2026-09-15.md`,
  `price-hygiene-fix-2026-09-17.md`, `universe-cohort-fix-2026-09-16.md`,
  `informed-flow-sources-and-strategy-families-2026-09-16.md`,
  `broad-universe-2026-09-17.md`, `llm-quant-landscape-2026-09-15.md`,
  `minute-momentum-feasibility-mom_stock_intraday_codesign_q1-q1.md`
  (superseded by the mom_minute_r1-r4 entry above).

### One flagged discrepancy for a future session

`dir:single_etf_intraday_momentum_cost_adjusted` (goal_first_w5, 2026-09-02,
0/36) may overlap with hypothesis card H-20260918-02's "SPY noise-band
intraday momentum" sub-hypothesis, whose own status as of 2026-09-18 was
still recorded as "approved, not yet run" -- inconsistent with the 2026-09-02
result already existing. Not resolved here; flagged in the new row's
`notes` field for a future session to read both in full.

## Job B: text-only triage of 11 unjudged rows

| direction id | decision | new status | one-line verdict |
|---|---|---|---|
| `dir:llm_acceptance_judge_forward_shadow` | (ii) needs LLM scoring | triaged | queue-ready DeepSeek pilot: weekly keep/half/skip filter on the existing momentum top-50, forward-shadow only, placebo already designed |
| `dir:llm_earnings_call_transcript_pricing` | none of i-iv cleanly fits: blocked on paid-data acquisition | not_executable | no free transcript data exists to score at all; distinct from an LLM-scoring pilot we could run today |
| `dir:text_to_pit_feature_extraction` | (ii) needs LLM scoring | triaged | 400-sample (50 tickers x 8 quarters) 10-K/8-K risk-label pilot via DeepSeek (not Claude), added as one feature to the existing ranking pipeline |
| `dir:news_sentiment_trading_pwb` | (ii) needs LLM scoring, but evidence too weak to prioritize | evidence_too_weak | single unreplicated third-party backtest, overlaps two locally-refuted news-signal families, matches the owner's own low-prior note on this exact class of work |
| `dir:llm_8k_gdelt_sentiment_acceleration` | (ii) needs LLM scoring | triaged | one-quarter IC pilot reproducing the source's feature construction via DeepSeek, pre-committed stop rule from the source's own disclosed weakness |
| `dir:llm_hypothesis_code_backtest_loop` | (iii) research method | triaged | adopt the hypothesis->code->IC-feedback loop itself as the primary action; 5-10 Claude-authored factors on the existing zoo, judged only on beating it |
| `dir:cogalpha_llm_code_alpha_generation` | (iii) research method | parked | fold its 5-dimension filter into the adopted loop's screening step rather than run as a separate direction |
| `dir:alphaeval_backtest_free_prescreening` | (iii) research method | parked | fold its backtest-free pre-screen in once the adopted loop is actually producing candidates that need one |
| `dir:pead_xbrl_8k_llm` | (i) testable today, no LLM, for its accounting half | triaged | rebuild SUE using the 8-K 2.02 exhibit timestamp instead of the filing date -- the exact reopen condition the already-refuted filing-date version named for itself; LLM guidance/tone overlay is a gated second stage |
| `dir:momentmal2022_wsot_live_multi_strategy` | (iv) not replicable | not_executable | 20-40+ underlying strategies, none disclosed |
| `dir:kinfo_verified_discretionary_traders` | (iv) not replicable | not_executable | discretionary traders, no disclosed rules, no annualized/Sharpe/drawdown stats on the public leaderboard |

### Plans verbatim (queue-ready)

**`dir:llm_acceptance_judge_forward_shadow` (ii, DeepSeek pilot).** Run the
H-20260916-04 design's first 2-week shadow-only pilot on the current
momentum top-50 (no position impact): weekly dossiers (returns/vol, news
headlines via `visible_at`, insider filings, latest 8-K date) -> DeepSeek
keep/half/skip decision with reasons -> log decisions -> compare 4-week
forward excess of skip vs keep names, plus the built-in mismatched-symbol/
news placebo. Decision rule: continue to an 8-week full evaluation only if,
after the 2-week pilot, the mechanism looks directionally sane (no
disqualifying hallucination rate); stop per H-20260916-04's own criteria
(skip not worse than keep at 8 weeks, or placebo matches real, or >10%
hallucinated reasons) at the full evaluation.

**`dir:text_to_pit_feature_extraction` (ii, DeepSeek pilot).** Structured
risk-label extraction on ~50 tickers x 8 quarters (400 filing-quarters) via
the DeepSeek endpoint (not Claude), added as one feature to the existing
cross-sectional ranking pipeline. Decision rule: continue to a larger run
only if the pilot's IC lift over the existing factor zoo is positive and
stable-signed, and a mismatched-filing placebo does not reproduce it.

**`dir:llm_8k_gdelt_sentiment_acceleration` (ii, DeepSeek pilot).**
Reproduce only the feature construction (rank of short-MA minus long-MA of
polarity*magnitude, i.e. sentiment acceleration) on the existing 8-K
text-score pipeline + Alpaca/Benzinga news for one recent quarter, via
DeepSeek in place of the source's Claude Haiku. Check IC against next-5-day
returns before building the full purge(5)+embargo(5) walk-forward CV
harness. Decision rule: stop before building the full harness if the pilot
IC is not stable-signed or a shuffled-news placebo reproduces it;
separately, do not override a failed validation gate the way the source
paper's own disclosed IR -1.50 override did.

**`dir:llm_hypothesis_code_backtest_loop` (iii, adopt as method).** 5-10
Claude-authored candidate factors on top of the existing Alpha101/158/191/
OSAP zoo, screened through the existing IC/RankIC pipeline on a recent
out-of-sample slice. Judged only on whether the batch beats the existing
zoo's best factors; no prompt iteration after seeing results within the
bounded batch.

**`dir:pead_xbrl_8k_llm` (i, no LLM, accounting half).** Rebuild the SUE
feature using the 8-K item-2.02 exhibit receipt timestamp (not the 10-Q/
10-K filing date) as `visible_at`, reusing the existing fundamentals-v1
signal-card pipeline and its redated placebo unchanged. Rerun through the
existing admission rule (stable_years, beats the redated placebo, G1 at
10/20bp). Decision rule: only if this accounting-only stage clears the
admission rule, add the LLM-read guidance/tone overlay via DeepSeek
(sample 2 quarters first, per H-20260916-06) as a second-stage test.

## Validation

`uv run oc research directions validate` -> `{"status": "ok", "problems": 0}`
after the append (checked against the full file, including any concurrent
rows from other agents present at the time this report was written).
