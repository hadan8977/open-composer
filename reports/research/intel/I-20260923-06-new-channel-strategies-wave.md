# I-20260923-06: New-channel search wave -- second-edge candidates beside semis-momentum

Scope: 19 searches (archive articles/pine, site-restricted web, X timelines, exa). Goal: a
second long-only US stock/ETF edge, distinct from the S1-S3 semis-momentum mechanism. No
backtests run, no code changed. All numbers below are author-reported, not reproduced by us.

## Searches run

| # | id (search:20260923:...) | channel | query | results | useful |
|---|---|---|---|---:|---:|
| 1 | archive:fomc_articles_56b834 | archive/articles | FOMC | 6 | 0 |
| 2 | archive:turn_month_articles_a5757b | archive/articles | turn month | 0 | 0 |
| 3 | archive:rotation_articles_f5cfd0 | archive/articles | rotation | 20 | 2 |
| 4 | archive:out_of_sample_articles_ff2865 | archive/articles | out-of-sample | 18 | 0 |
| 5 | archive:seasonality_articles_80e8ed | archive/articles | seasonality | 20 | 1 |
| 6 | archive:leveraged_pine_d317da | archive/pine | leveraged | 12 | 0 |
| 7 | archive:tqqq_pine_15bcd6 | archive/pine | TQQQ | 4 | 0 |
| 8 | archive:rotation_pine_66c552 | archive/pine | rotation | 13 | 0 |
| 9 | web:site_quantconnect_com_forum_a643ca | web (quantconnect.com/forum) | leveraged ETF rotation live trading results | 6 | 0 |
| 10 | web:site_quantconnect_com_forum_f55321 | web (quantconnect.com/forum) | momentum strategy live results 2025 | 6 | 2 |
| 11 | web:site_quantitativo_com_strategy_fe6516 | web (quantitativo.com) | strategy backtest results | 7 | 1 |
| 12 | web:site_algomatictrading_substack_com_d51ea1 | web (algomatictrading.substack.com) | strategy | 7 | 0 |
| 13 | web:site_roguequant_substack_com_c10e8c | web (roguequant.substack.com) | strategy code backtest | 20 | 0 |
| 14 | x:quantifiabledgs_timeline_..._dcbca7 | x | @QuantifiablEdgs timeline | 40 | 0 |
| 15 | x:pedma7_timeline_..._789c34 | x | @pedma7 timeline | 40 | 0 |
| 16 | x:momentmal2022_timeline_..._1a2aa2 | x | @momentmal2022 timeline | 40 | 1 (+1 channel) |
| 17 | x:tradequantix_timeline_..._38e4ad | x | @TradeQuantiX timeline | 40 | 0 |
| 18 | x:garyantonacci_timeline_..._c6d706 | x | @GaryAntonacci timeline | 40 | 1 (update only) |
| 19 | exa:strategy_with_verified_live_be79b0 | exa | verified live track record since 2024, US ETFs, Collective2/Kinfo | 20 | 4 |

10 new directions registered, 1 existing direction updated (not reopened), 1 new channel
(WSOT), 1 channel updated (Collective2 read-path). `directions validate` = ok.

## Top 5 directions (ranked by evidence quality + fit, not by 2026 return)

1. **`dir:defense_first_taa_carlson_concretum`** -- Quantitativo's independent backtest of Thomas
   Carlson's 2025 "Defense First" paper: monthly rotation among TLT/GLD/DBC/UUP (40/30/20/10 by
   momentum rank, absolute-momentum screened), SPY as fallback. ~1990-2025 (pre-holdout): CAGR
   10.4%/Sharpe 0.95/MDD -19.4% vs SPY 10.6%/0.64/-55.2%; Fama-French alpha ~6.8%/yr (t=3.58);
   3x-equity-sleeve variant CAGR 16.2%/Sharpe 0.97. Zero overlap with semis (0.27-0.58 corr to
   equities by design). Test: replicate the 5-ticker unleveraged version, data on hand.
2. **`dir:collective2_etf_timer_17yr_live`** -- "ETF Timer", continuously live on Collective2
   (third-party tracked) since Jan 2008, >15%/yr net of all fees over ~17.5 years, survived 2008
   GFC and 2020 COVID. Best raw evidence tier this pass, but rules not read yet (forum/leaderboard
   only) -- open the vendor's own strategy page next.
3. **`dir:front_running_sector_seasonality`** -- Quantpedia: rank 9 sector SPDRs by return in the
   same calendar month one year ago, shifted a month early; long top-2, monthly. Dec1998-Sep2024
   (pre-holdout); author claims it beats benchmark on Sharpe/Calmar "particularly since 2009"
   (numbers in chart images, not extracted). No semis overlap; distinct from `dir:sectoral_intramonth_momentum`.
4. **`dir:spy_sso_tlt_vix_regime_rotation`** -- Alvarez Quant Trading: monthly regime switch --
   SSO (2x S&P) if SPY>200dma & VIX<25, plain SPY if SPY>200dma & VIX>=25, TLT/cash if SPY<200dma.
   2007-2024 (pre-holdout); author reports CAGR "slightly better than B&H", MDD "greatly reduced"
   (no exact figures extracted). Minimal semis overlap.
5. **`dir:capital_gain_momentum_no_dividend`** -- QuantConnect forum build of Cannon & Lynch
   (2025): 11-month momentum, long only no-dividend stocks above the 95th NYSE momentum
   percentile, top-1000-liquid universe, monthly. Jul2016-Jul2026: Sharpe 0.602 vs SPY B&H 0.552;
   92% of a 25-cell parameter grid beat the benchmark. **Window overlaps our 2026 holdout** --
   flagged, not used to rank. Modest edge, no CAGR/MDD given.

Also registered, lower priority: `dir:collective2_adaptive_investments_knn_tqqq_sqqq` (real C2
live record, 26mo, undisclosed ML rules, trades TQQQ/SQQQ so adds correlated Nasdaq risk rather
than diversifying); `dir:momentmal2022_wsot_live_multi_strategy` (real competition-judged live
record, rules fully undisclosed); `dir:collective2_us_stock_momentum_top10_sp500` and
`dir:clenow_stocks_on_the_move_momentum` (weak/caution: marketing-vs-audit inconsistencies in
the first, underperforms B&H in the second); `dir:sector_momentum_middle_tier_buy` (concrete,
only marginal edge per source). `dir:giants_sweep_published_etf_rules` updated: Concretum/Antonacci
released code for a paper we already refuted in the 09-22 sweep -- does not meet its reopen bar.

## Channels that were useless this pass (do not repeat as-is)

- **archive/pine** (`leveraged`/`TQQQ`/`rotation`): only unvalidated community TradingView
  scripts, no quantified backtest text (jev tier "none" almost throughout).
- **algomatictrading.substack.com**, **roguequant.substack.com**: futures/commodities/crypto
  focused (Gold, ES/NQ, crude, silver, BTC) -- out of our US-stock/ETF, Alpaca scope.
- **x:@QuantifiablEdgs**: calendar musings, no in-tweet numbers (charts only).
- **x:@pedma7**: crypto/perp trader, out of scope.
- **x:@TradeQuantiX**: mostly its own skepticism of a data-mined NASDAQ filter result, plus an
  ASX (Australian) momentum series -- no new US-equity direction.
- **archive/articles** `turn month` (two words): 0 results -- match-every-word is too strict for
  this phrase; we already hold `dir:turn_of_month_equity_seasonality` from prior passes.
