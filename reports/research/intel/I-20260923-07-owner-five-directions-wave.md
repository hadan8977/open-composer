# I-20260923-07: Owner's five directions -- events, alt-data, factors, HF, models (per-stock only)

Scope: 23 searches (`exa`, papers/blogs/repos), owner-specified five directions for US stocks: per-stock events, alt data, per-stock factors, HF/intraday single stocks, model training. No ETF rotation/TAA/leveraged-ETF timing. No backtests, no code changes. 18 new registry rows appended (`directions validate` = ok). All numbers below are from full text actually read (fetched pages, not just result titles), labeled by their own evidence window. All 23 searches logged as `search:20260923:exa:*` in `search-log.jsonl`; raw pages under `reports/research/harvest/raw/2026-09-23/`.

## Searches

| Direction | Queries run | Registered |
|---|---|---|
| Events (5) | PEAD 2023-25 replication; 8-K item-type drift; SEO/ATM dilution; spin-off outperformance; buyback execution vs announcement | 4 new (1 weak) |
| Alt data (5) | Wikipedia attention; SEC fails-to-deliver; ETF flow into constituents; job postings; GitHub activity | 5 new (3 weak, 1 parked) |
| Factors (4) | factor momentum/timing; long-only decile factors; industry-adj. short reversal; replication crisis / factor zoo | 3 new |
| HF (5) | ORB stocks-in-play update; closing-auction imbalance; VWAP deviation mean reversion; intraday momentum after news; ETF-to-small-cap lead-lag | 3 new |
| Models (4) | Gu-Kelly-Xiu ML decay; LLM features from news/filings OOS; GBM+text+event marginal value; meta-labeling OOS 2023-25 | 2 new (one search) |

## 1. Events

**New:** classic SUE-based PEAD is a documented microcap effect through Dec 2024 (UCLA's Subrahmanyam replication: t=2.18 all-stocks -> t=1.43 ex-microcap, not significant). 8-K Item 4.02 (restatement/non-reliance) drift is real and significant (n=8,143, 2004-2023, CAR -1.1%/-2.0% at day 1/20, p<0.001) -- a mechanism not previously in the registry. Spin-offs: one small independent 2023-cohort test underperformed SPY by ~23pp over 2 years at every entry delay; the only positive claim found has a commercial conflict of interest. SEO/ATM and buyback-execution-vs-announcement: nothing concrete surfaced.

**Refuted-status check:** distinct from refuted `dir:earnings_8k_tone_next_day` (tone-only) and harvested `dir:pead_xbrl_8k_llm` (guidance-tone) -- both new mechanisms. `dir:buyback_announcement_effect` and `dir:fda_calendar_binary_events` unchanged.

**Best testable ideas:** Item 4.02 as a long-only avoidance/exit gate on the existing momentum book -- cheap (filing-index item-type parse, not LLM work) but note two prior avoidance-gate overlays already failed locally, so treat as a probe. Nothing else in this section clears the bar to spend compute.

## 2. Alt data

**New:** every free-data candidate came back thin. Wikipedia attention: only a 2013 DJIA-30 paper and paywalled 2022/2024 abstracts. SEC fails-to-deliver: real informed-short-selling literature exists but only abstract-level text was readable; SEC publishes the raw data free, bi-monthly. ETF creation/redemption flow into constituents: no per-stock mechanism or free ticker-level flow data found. GitHub commit activity: one well-engineered pipeline, zero demonstrated edge. Job postings/hiring velocity: real academic backing (Campello-Kankanhalli-Muthukrishnan 2020) but every named vendor is $30K-$300K/yr -- fails the brief's own "free" filter; a budget decision, not a search gap.

**Refuted-status check:** does not reopen `dir:retail_sentiment_attention` (Google Trends already covered) or `dir:alt_data_satellite_app_supply_chain`.

**Best testable ideas:** none justify new data acquisition yet. Better use of alt-data effort: test the free dataset already built and untested -- `dir:finra_daily_short_volume_bjz` -- before adding fails-to-deliver as a second, overlapping short-selling source.

## 3. Factors

**New:** factor momentum/timing (Blitz/Robeco, full 1963-2024 sample) decays from 2.8%/yr (t=4.9, pre-2011) to 0.4%/yr post-2011 pre-cost, and the 12-month version is 67% correlated with plain WML -- largely our existing momentum re-labeled. A long-only automated-10-K value+momentum decile strategy (paperswithbacktest, 2009-2025) is real and long-only-native but mediocre: 12.97% CAGR / Sharpe 0.74, matching our already-established ~15-25%/yr unlevered ceiling. A rigorous open-source sector-residual short-horizon-reversal project (leak-safe CRSP, deflated Sharpe, one-shot sealed OOS) is a decisive **negative**: OOS 2019-2024 net Sharpe -0.15 (from IS gross 0.90), and the surviving alpha is short-side/low-price-name -- unexecutable for us regardless.

**Refuted-status check:** corroborates `dir:classic_long_short_anomalies_recent` (updated earlier today by a separate pass) without changing it. Does not change parked `dir:jkp_accounting_change_factors` or `dir:osap_ml_ranking` (Gu-Kelly-Xiu data now extends to 2021 via a Tidy Finance replication, still permno-keyed, same blocker).

**Best testable ideas:** none clear our gates standalone. The 10-K decile approach is the most "boringly real" positive result, worth revisiting only if we build point-in-time 10-K fundamentals extraction for other reasons.

## 4. HF / intraday (single stocks)

**New:** a peer-reviewed JFE paper (Jiang-Li-Wang) builds a **signed** high-frequency news-return score (15-minute decomposition, not a count/novelty measure) and finds one-week drift: gross 1.60-3.34%/mo, net ~1.37%/mo after realistic (18bp) costs, 2000-2012. One repo finds a **daily** ETF-to-constituent lead-lag that is real (Granger-causal 22/24 names, p<0.05) but pays only as **reversion**, macro-shock-gated (Sharpe ~0.9 -> ~1.3); the momentum version loses money by construction, honestly reported. Stocks-in-play itself has no fresh 2024-25 update; the only new critique found is of the sister SPY-only paper (already refuted as `dir:spy_noise_band_intraday`). Closing-auction imbalance: NYSE's own research is TCA, not a predictive signal, and needs imbalance-message data we lack.

**Refuted-status check:** does not reopen `dir:cross_sectional_gap_fade` or `dir:orb_stocks_in_play_relative_volume` (still untested). Both new findings are mechanistically distinct from anything already refuted.

**Best testable ideas:** (1) the signed high-frequency news-return score on our own Alpaca/Benzinga news + SIP minute bars -- genuinely different from refuted count-based `dir:news_attention_features`, both ingredients already in inventory. (2) the daily ETF-to-constituent reversion book, replicated once on our better-than-source data for one sector ETF before the intraday regime the source could not test.

## 5. Models (ML/DL/LLM)

**New:** an LLM-embedding-of-analyst-report-text study (arXiv 2502.20489, 1.2M Investext reports 2000-2023) finds 68bp/mo alpha (t=2.64) vs FF5+momentum, IR 0.73-1.41 vs 94+18 known factors -- strong, but gated on a paid Investext/Refinitiv subscription we lack. A free-data repo (`LLM_Alpha`) builds an Alpha101-style rank-weighted sentiment-**acceleration** signal (short-MA minus long-MA of LLM polarity*magnitude, Engelberg-McLean-Pontiff convention) from EDGAR 8-K + GDELT news, purge/embargo CV, frozen hyperparameters: OOS (Q1'22-Q4'24) Sharpe +0.78 net of 5bp costs -- but the author discloses the alpha t-stat (1.35) is not significant AND their own pre-registered validation gate failed in H2-2021 and was overridden.

**Refuted-status check:** distinct from refuted `dir:news_attention_features` (count only) and `dir:lightgbm_price_volume_recipe_v1_closed`/`dir:meta_labeling_position_tiers` (price-volume only). Gu-Kelly-Xiu and meta-labeling searches found nothing to reopen `dir:osap_ml_ranking` or the local meta-labeling refutation.

**Best testable ideas:** the sentiment-acceleration construction -- every input (8-K text scores, Alpaca/Benzinga news, DeepSeek endpoint) is already in inventory, zero new data acquisition. Compute the feature on one recent quarter and check IC against next-5-day returns before building any CV harness.

## Ranked top-6 (evidence quality x data/execution fit x plausible after-cost return; not 2026 returns)

1. **`dir:high_freq_news_return_underreaction_drift`** -- peer-reviewed, concrete net-of-cost number, both data ingredients on hand; risk is a dated (2000-2012) sample, no 2023-25 confirmation.
2. **`dir:etf_constituent_lead_lag_reversion`** -- single-repo evidence, but tests the intraday regime the source explicitly could not, on data we already have.
3. **`dir:llm_8k_gdelt_sentiment_acceleration`** -- weakest evidence (author's own validation gate failed), but the cheapest possible falsification test with zero new data.
4. **`dir:event_8k_item402_restatement_drift`** -- strongest significance found this wave, ranked below 1-3 because its best use (avoidance gate) matches a pattern that failed twice locally.
5. **`dir:long_only_fundamental_decile_10k`** -- real, long-only-native, positive OOS evidence; ranked low because Sharpe 0.74 is a confirmed ceiling, not a new edge.
6. **`dir:llm_analyst_report_narrative_alpha`** -- probably the best raw evidence quality of the wave (68bp/mo, t=2.64, multi-benchmark IR), last only because data-fit is zero: gated on a paid-subscription decision for the owner.

Excluded despite strong evidence: `dir:sector_residual_reversal_statarb_decay` (rigorous, decisive negative, zero long-only fit) and `dir:factor_momentum_timing_decay` (credible, decisive negative, decayed to ~0 pre-cost).
