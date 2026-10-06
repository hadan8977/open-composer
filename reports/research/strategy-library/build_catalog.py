"""Assemble catalog.json (T-20261006-13). Reads only snapshots under
reports/research/intel/sources/strategy-library-2026-10-06/ and the read-only
direction registry; writes catalog.json and families.json next to this file.

Rows come from four origins:
  k151   Kakushadze-Serur "151 Trading Strategies" table of contents (every
         numbered strategy entry; 'Generalities' and 'A few comments' are
         background sections and are not strategies)
  osap   Open Source Asset Pricing SignalDoc.csv (all 331 rows incl. Placebo/Drop)
  qc     QuantConnect Strategy Library tutorials (titles, Quantpedia/paper source)
  reg    local registry directions in categories where the three public lists
         are thin (intraday, hf_factor, event, alt_data, crypto, options,
         text_llm), so that coverage of those classes can be judged at all.
         Fields of reg rows are coarser (derived from the registry record).

No backtest is run here. Judgements (tradability, local data, prior depth) are
written down by hand in the tables below and are the reviewable part.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "reports/research/intel/sources/strategy-library-2026-10-06"
SRC_REL = "reports/research/intel/sources/strategy-library-2026-10-06"

DIRS = {r["id"]: r for r in json.load(open(HERE / "_directions_latest.json"))}

D_DAILY = "data/sip/daily (2016-2026), data/features/daily_broad"
D_MIN = "data/sip/minute (2023-26), data/sip-hist/minute (2016-22)"
D_FUND = "data/features/sec_fundamentals_daily (eps, revenue, NI, GP, op inc, TA, equity, OCF, shares)"
D_XBRL = "data/raw/sec_xbrl/companyfacts.zip (all XBRL tags, adapter needed)"
D_OPT_OWN = "data/options (own chain recorder, from 2026-10-06), data/dolthub_options (free EOD chains, 2019+, partial)"

NO_BROKER = "no: not tradable at Alpaca ({})"


def _check(ids: list[str]) -> list[str]:
    bad = [i for i in ids if i not in DIRS]
    if bad:
        raise SystemExit(f"unknown registry ids {bad}")
    return ids


def _locally_tested(i: str) -> bool:
    """Heuristic (rule v2): 'tested locally' = our own experiment produced the registry status.
    refuted and partial count as tested unless the verdict says not tested; parked never counts
    (parked = not pursued); evidence_too_weak counts only if the record cites a local experiment path
    (iterations/, screens/, hypotheses/, signal-cards/) and the verdict does not say not tested.
    The registry mixes literature-only dismissals into evidence_too_weak, so this is a heuristic."""
    r = DIRS[i]
    st = r["status"]
    ev = " ".join(r.get("evidence") or [])
    local = any(p in ev for p in ("reports/research/iterations/", "reports/research/screens/",
                                  "reports/research/hypotheses/", "reports/research/signal-cards/"))
    untested = re.search(r"not tested|untested|needs_modal|primary source", r.get("verdict") or "", re.I) is not None
    if st == "parked":
        return False
    if st in ("refuted", "partial"):
        return not untested
    if st == "evidence_too_weak":
        return local and not untested
    return local and not untested


def status_of(i: str) -> str:
    r = DIRS.get(i)
    return r["status"] if r else "missing"


def prior_str(ids: list[str]) -> str:
    if not ids:
        return "none"
    return "; ".join(f"{i} [{status_of(i)}]" for i in ids)


def row(**kw) -> dict:
    base = dict(
        id="", name="", source="", original_paper="", origin_list="", asset_class="us_equity",
        frequency="monthly", direction="long_short", data_needed="", data_local="partial",
        data_local_detail="", alpaca_tradable="yes", alpaca_note="", alpaca_basis="documented",
        prior_local="none", prior_ids=[], prior_best_status="none", prior_depth_ok="unknown",
        screen_lane_ready=False, engine="new", lane_adapter="", complexity="M", family_key="",
        notes="", entry_type="strategy", needs_gpu=False, adapter_1d=False, adapter_note="",
    )
    base.update(kw)
    ids = _check(base["prior_ids"])
    base["prior_local"] = prior_str(ids)
    sts = [status_of(i) for i in ids]
    for s in ("passed", "testing", "queued", "partial", "triaged", "harvested", "parked",
              "evidence_too_weak", "refuted", "not_executable", "duplicate"):
        if s in sts:
            base["prior_best_status"] = s
            break
    if not ids:
        base["prior_depth_ok"] = "n/a (never tested)"
    generic = {"dir:osap_ml_ranking", "dir:ml_ranking_liquid500_recent_vs_momentum_rule", "dir:classic_long_short_anomalies_recent",
               "dir:ml_ranking_broad_universe_custom"}
    base["prior_locally_tested"] = any(_locally_tested(i) for i in ids)
    base["prior_scope"] = "none" if not ids else ("generic_only" if set(ids) <= generic else "specific")
    return base


# --------------------------------------------------------------------------
# 151 Trading Strategies
# --------------------------------------------------------------------------
K151_URL = "https://papers.ssrn.com/abstract=3247865 (PDF read from mirror smallake.kr SSRN-id3247865.pdf, sha256 def6a23d...)"
K151_PAPER = "Kakushadze & Serur (2018), 151 Trading Strategies, SSRN 3247865 / Palgrave Macmillan"

OPT_YES_DOC = {"2.2", "2.4", "2.5", "2.6", "2.9", "2.22", "2.23", "2.24", "2.34", "2.35", "2.32", "2.33", "2.53"}
OPT_YES_INFER = {"2.7", "2.8", "2.18", "2.19", "2.20", "2.21", "2.40", "2.40.1", "2.41", "2.41.1", "2.42", "2.43",
                 "2.44", "2.45", "2.46", "2.47", "2.48", "2.49", "2.50", "2.51", "2.52", "2.54", "2.55", "2.57",
                 "2.36", "2.37", "2.10", "2.12"}
OPT_REASON_NO = {
    "2.3": "covered put = short stock + short put; short put on a short-stock position is not a covered/cash-secured Level-1 structure",
    "2.11": "short synthetic forward = short call + long put with an uncovered short call",
    "2.13": "short combo = short call + long put with an uncovered short call",
    "2.14": "bull call ladder sells two call strikes against one long: uncovered short call",
    "2.15": "bull put ladder: uncovered short put leg beyond cash secured",
    "2.16": "bear call ladder: uncovered short call",
    "2.17": "bear put ladder: uncovered short put leg",
    "2.25": "short straddle = naked short call and put",
    "2.26": "short strangle = naked short call and put",
    "2.27": "short guts = naked short call and put",
    "2.28": "long call synthetic straddle includes a short stock plus long calls (OK) -- but uses 2 calls vs stock; treated as no until a paper probe",
    "2.29": "long put synthetic straddle (long stock + 2 puts) -- treated as no until a paper probe",
    "2.30": "short call synthetic straddle: uncovered short calls",
    "2.31": "short put synthetic straddle: uncovered short puts beyond cash secured",
    "2.38": "ratio call spread sells more calls than it buys: uncovered short call",
    "2.39": "ratio put spread sells more puts than it buys: uncovered short put",
    "2.56": "bearish short seagull has an uncovered short OTM call",
}

# non-option chapters: id -> dict of overrides.  Format of value:
# (asset, freq, direction, data_needed, local, tradable, note_tradable, family, prior ids, engine, cx, notes)
K = {}


def k(i, *a):
    K[i] = a


L_ETF = "lane"
# ---- chapter 3 stocks
k("3.1", "us_equity", "monthly", "long_short", "adjusted close, 12-1 month return", "yes", "", "xs_price_momentum",
  ["dir:equity_momentum_concentrated_pwb", "dir:step10_xsmom_pit_liquidity_liquid500", "dir:signal_library_v1_price_anomalies",
   "dir:multi_signal_risk_controlled_equity_book", "dir:clenow_stocks_on_the_move_momentum"], "book", "S",
  "feature column data/features/osap_price.mom12m exists; part of the live-tracked equity book signal library (mom_12_1)")
k("3.2", "us_equity", "event", "long_short", "earnings surprise (SUE) and/or analyst revisions", "yes", "", "earnings_surprise_pead",
  ["dir:pead_classic_sue_microcap_decay", "dir:pead_xbrl_sue_filing_date", "dir:ml_multiquarter_sue_history", "dir:pead_xbrl_8k_llm"],
  "book", "S", "sue_eps/sue_rev in sec_fundamentals_daily; analyst revisions not local")
k("3.3", "us_equity", "monthly", "long_short", "book-to-market / earnings / sales yield", "yes", "", "value_composite",
  ["dir:classic_long_short_anomalies_recent", "dir:multi_signal_risk_controlled_equity_book", "dir:long_only_fundamental_decile_10k"], "book", "S", "bm, ep, sp, cfp in the equity-book signal table")
k("3.4", "us_equity", "monthly", "long_short", "daily returns (volatility, beta)", "yes", "", "low_risk_beta",
  ["dir:signal_library_v1_price_anomalies", "dir:multi_signal_risk_controlled_equity_book"], "book", "S", "beta_252, idio_vol_63 in the equity-book table")
k("3.5", "us_equity", "monthly", "long_short", "stock option implied volatility", "yes", "", "option_implied_stock_signals",
  ["dir:iv_hv_spread_stock_ranking_dolthub", "dir:options_derived_signals_retail", "dir:alpaca_free_options_iv_signals"], "new", "M",
  "needs DoltHub EOD chains (2019+, partial coverage) -- see registry iv_hv_spread (testing)")
k("3.6", "us_equity", "monthly", "long_short", "multiple factor signals", "yes", "", "value_composite",
  ["dir:multi_signal_risk_controlled_equity_book", "dir:ml_ranking_liquid500_recent_vs_momentum_rule"], "book", "M", "this is the equity book (M0 composite) itself")
k("3.7", "us_equity", "monthly", "long_short", "adjusted close, market/industry residuals", "yes", "", "residual_momentum",
  ["dir:multi_signal_risk_controlled_equity_book"], "book", "S", "resid_mom_12_1 in the book table; osap_price.residualmom_252_21")
k("3.8", "us_equity", "daily", "relative_value", "daily prices of pairs", "yes", "", "stat_arb_pairs",
  ["dir:intraday_cointegration_pairs_pca", "dir:deep_learning_stat_arb_residual"], "new", "M", "plan-v2 notes shallow single-signal PCA/OU stat-arb is net-negative at 5 bp")
k("3.9", "us_equity", "daily", "long_short", "daily prices, cluster (industry) residuals", "yes", "", "stat_arb_cluster_reversion",
  ["dir:sector_residual_reversal_statarb_decay", "dir:etf_constituent_lead_lag_reversion"], "new", "M", "")
k("3.9.1", "us_equity", "daily", "long_short", "daily prices, multiple clusters", "yes", "", "stat_arb_cluster_reversion",
  ["dir:sector_residual_reversal_statarb_decay"], "new", "M", "")
k("3.10", "us_equity", "daily", "long_short", "daily prices, weighted regression residuals", "yes", "", "stat_arb_cluster_reversion",
  ["dir:sector_residual_reversal_statarb_decay"], "new", "M", "")
k("3.11", "us_equity", "daily", "market_timing", "adjusted close", "yes", "", "ma_trend_rules",
  ["dir:levered_single_asset_sma_trend_gate", "dir:ema_crossover_atr_paper_track"], "lane", "S", "owner ranks pure technical indicators lowest (09-11); keep as cheap batch filler only")
k("3.12", "us_equity", "daily", "market_timing", "adjusted close", "yes", "", "ma_trend_rules",
  ["dir:ema_crossover_atr_paper_track"], "lane", "S", "")
k("3.13", "us_equity", "daily", "market_timing", "adjusted close", "yes", "", "ma_trend_rules", [], "lane", "S", "")
k("3.14", "us_equity", "daily", "market_timing", "daily high/low/close", "yes", "", "breakout_channel", [], "lane", "S", "pivot-point support/resistance")
k("3.15", "us_equity", "daily", "market_timing", "daily high/low/close", "yes", "", "breakout_channel", [], "lane", "S", "Donchian-style channel")
k("3.16", "us_equity", "event", "long_only", "M&A announcement dates, deal terms", "yes", "", "merger_arbitrage_target_drift",
  ["dir:merger_arbitrage_target_announcement_drift"], "new", "M", "data/features/sec_8k_ma_announcements exists")
k("3.17", "us_equity", "daily", "long_short", "adjusted close, lagged returns (KNN)", "yes", "", "ml_single_asset_direction",
  ["dir:collective2_adaptive_investments_knn_tqqq_sqqq", "dir:fischer_krauss_lstm_xs_ranking"], "new", "M", "")
k("3.18", "us_equity", "daily", "long_short", "returns, covariance, alpha forecasts", "yes", "", "stat_arb_optimization",
  ["dir:multi_signal_risk_controlled_equity_book"], "book", "L", "optimiser/risk-model layer, already in equity-book design (cvxpy)")
k("3.18.1", "us_equity", "daily", "long_short", "returns, covariance", "yes", "", "stat_arb_optimization",
  ["dir:multi_signal_risk_controlled_equity_book"], "book", "L", "dollar-neutrality constraint, already in equity-book design")
k("3.19", "us_equity", "intraday", "relative_value", "quotes/order book, latency", "no", "market making needs rebates and low-latency connectivity; registry dir:true_hft_market_making is not_executable", "hft_market_making",
  ["dir:true_hft_market_making"], "new", "L", "")
k("3.20", "us_equity", "daily", "long_short", "many alpha signals", "yes", "", "alpha_combination",
  ["dir:multi_signal_risk_controlled_equity_book", "dir:ml_ranking_liquid500_recent_vs_momentum_rule", "dir:ml_ranking_broad_universe_custom"], "book", "M", "")
# ---- chapter 4 ETFs
k("4.1", "etf", "monthly", "long_only", "ETF adjusted close", "yes", "", "etf_momentum_rotation",
  ["dir:s1_sector_rotation_voltarget", "dir:recent_window_etf_menu_rotation", "dir:narrow_industry_etf_momentum_rotation", "dir:sector_momentum_middle_tier_buy"], "lane", "S", "")
k("4.1.1", "etf", "monthly", "long_only", "ETF adjusted close", "yes", "", "etf_momentum_rotation",
  ["dir:s1_sector_rotation_voltarget", "dir:recent_window_etf_menu_rotation"], "lane", "S", "")
k("4.1.2", "etf", "monthly", "long_only", "ETF adjusted close", "yes", "", "etf_momentum_rotation",
  ["dir:etf_dual_momentum_rotation_gem_pools", "dir:recent_window_etf_menu_rotation"], "lane", "S", "")
k("4.2", "etf", "monthly", "long_only", "ETF adjusted close, benchmark regression alpha", "yes", "", "etf_momentum_rotation", [], "lane", "S", "rank by regression alpha vs a benchmark ETF")
k("4.3", "etf", "monthly", "long_only", "ETF adjusted close, trend R-squared", "yes", "", "etf_momentum_rotation", [], "lane", "S", "")
k("4.4", "etf", "weekly", "long_only", "ETF adjusted close", "yes", "", "short_term_etf_dip_reversion",
  ["dir:etf_dip_reversion_ibs_connors", "dir:tactical_mean_reversion_multi_asset_pwb"], "lane", "S", "")
k("4.5", "etf", "daily", "long_only", "leveraged ETF adjusted close", "yes", "", "levered_sector_trend",
  ["dir:s3_levered_rotation_voltarget_dip_boost", "dir:letf_published_rules_live_tracked", "dir:levered_menu_expansion"], "lane", "S", "S3 incumbent is a leveraged-ETF rotation")
k("4.6", "etf", "monthly", "long_only", "multi-asset ETF adjusted close", "yes", "", "cross_asset_etf_trend",
  ["dir:step10_cross_asset_trend_tsmom_etf", "dir:keller_antonacci_faber_taa_batch1_2026", "dir:defense_first_taa_carlson_concretum"], "lane", "S", "")
# ---- chapter 5 fixed income (all not tradable)
for sid in ["5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8", "5.8.1", "5.9", "5.10", "5.11", "5.12", "5.13", "5.14", "5.15"]:
    k(sid, "fixed_income", "monthly", "relative_value", "bond / swap / yield-curve data", "no",
      "cash bonds, swaps and CDS are not tradable at Alpaca (bond ETFs would be a different strategy)", "fixed_income_" + sid.split(".")[1],
      [], "new", "L", "")
# ---- chapter 6 indexes
k("6.2", "futures", "daily", "relative_value", "index futures and cash index", "no", "index futures not tradable at Alpaca", "index_cash_and_carry", [], "new", "L", "")
k("6.3", "options", "monthly", "volatility", "index and constituent options", "no", "dispersion needs short index straddles (uncovered short options)", "dispersion_trading", [], "new", "L", "")
k("6.3.1", "options", "monthly", "volatility", "index and subset constituent options", "no", "short index straddles are uncovered short options", "dispersion_trading", [], "new", "L", "")
k("6.4", "etf", "intraday", "relative_value", "minute/tick prices of index ETFs (SPY/IVV/VOO etc.)", "yes", "", "intraday_etf_arbitrage",
  ["dir:etf_constituent_lead_lag_reversion"], "new", "M", "same-index ETFs differ by cents: expect cost-bound; minute data local")
k("6.5", "etf", "daily", "market_timing", "index ETF adjusted close, realized vol", "yes", "", "volatility_target_overlay",
  ["dir:s1_sector_rotation_voltarget", "dir:momentum_risk_control_vs_spmo"], "lane", "S", "owner rule: sizing overlays must raise Sharpe vs vol-matched incumbent")
# ---- chapter 7 volatility
k("7.2", "futures", "daily", "volatility", "VIX futures curve", "no", "VIX futures not tradable at Alpaca; VXX/UVXY ETNs are the proxy (7.3)", "vix_term_structure_carry",
  ["dir:vix_term_structure_short_vol"], "new", "M", "")
k("7.3", "etf", "daily", "volatility", "VXX/XIV-type ETN prices", "yes", "VXX/UVXY/SVXY-style ETPs trade as stocks", "vix_term_structure_carry",
  ["dir:vix_term_structure_short_vol", "dir:composer_rsi_branch_uvxy"], "lane", "S", "")
k("7.3.1", "futures", "daily", "volatility", "VXX plus VIX futures hedge", "no", "needs VIX futures leg", "vix_term_structure_carry", ["dir:vix_term_structure_short_vol"], "new", "M", "")
k("7.4", "options", "monthly", "volatility", "options chains, implied vs realized vol", "no", "classic VRP harvest is short straddle/strangle (uncovered short options)", "variance_risk_premium_options",
  ["dir:options_premium_selling_real_chain_batch", "dir:put_credit_spread_income", "dir:naked_options_income_0dte"], "new", "L", "defined-risk spread restructurings are tracked under dir:options_premium_selling_real_chain_batch")
k("7.4.1", "options", "daily", "volatility", "options chains, delta/gamma hedge", "no", "short gamma needs uncovered short options", "variance_risk_premium_options", ["dir:options_premium_selling_real_chain_batch"], "new", "L", "")
k("7.5", "options", "monthly", "volatility", "options chains (skew)", "yes", "long call + cash-secured short put, Level 1-2 pieces", "volatility_skew_risk_reversal", [], "new", "M", "alpaca_basis inferred for the combined order")
k("7.6", "other", "monthly", "volatility", "variance swap quotes", "no", "variance swaps are OTC", "variance_swap", [], "new", "L", "")
# ---- chapter 8 FX
for sid, nm in [("8.1", "fx_ma_hp"), ("8.2", "fx_carry"), ("8.2.1", "fx_carry"), ("8.3", "fx_carry"), ("8.4", "fx_momentum_carry"), ("8.5", "fx_triangular_arb")]:
    k(sid, "fx", "daily", "long_short", "FX spot and rates", "no", "spot FX is not tradable at Alpaca (UUP/FXE ETFs are a different instrument)", nm, [], "new", "L", "")
# ---- chapter 9 commodities, 10 futures
for sid, nm in [("9.1", "commodity_roll_yield"), ("9.2", "commodity_hedging_pressure"), ("9.3", "commodity_diversification"),
                ("9.4", "commodity_value"), ("9.5", "commodity_skew"), ("9.6", "commodity_pricing_models")]:
    k(sid, "futures", "monthly", "long_short", "commodity futures data", "no", "commodity futures not tradable at Alpaca", nm, [], "new", "L", "")
for sid, nm in [("10.1", "futures_hedging"), ("10.1.1", "futures_hedging"), ("10.1.2", "futures_hedging"), ("10.2", "futures_calendar_spread"),
                ("10.3", "futures_mean_reversion"), ("10.3.1", "futures_mean_reversion"), ("10.4", "futures_trend_following")]:
    k(sid, "futures", "daily", "long_short", "futures data", "no", "futures not tradable at Alpaca (ETF trend proxies are covered by 4.6)", nm, [], "new", "L", "")
# ---- chapter 11-14 not tradable
for sid in ["11.2", "11.3", "11.4", "11.5", "11.6", "11.7"]:
    k(sid, "fixed_income", "monthly", "relative_value", "CDO / CDS / MBS data", "no", "structured credit is not tradable at Alpaca", "structured_credit_" + sid.split(".")[1], [], "new", "L", "")
for sid in ["12.1", "12.2"]:
    k(sid, "other", "daily", "relative_value", "convertible bond and equity data", "no", "convertible bonds are not tradable at Alpaca", "convertible_arbitrage", [], "new", "L", "")
for sid in ["13.1", "13.2", "13.2.1"]:
    k(sid, "other", "event", "relative_value", "muni / cross-border dividend tax data", "no", "tax arbitrage needs municipal bonds or foreign tax positions", "tax_arbitrage_" + sid.split(".")[1], [], "new", "L", "")
for sid, nm in [("14.1", "inflation_swaps"), ("14.2", "tips_treasury_arbitrage"), ("14.3", "weather_risk"), ("14.4", "spark_spread")]:
    k(sid, "other", "monthly", "relative_value", "swap / TIPS / weather / energy data", "no", "not tradable at Alpaca", nm, [], "new", "L", "")
# ---- chapter 15 distressed
for sid in ["15.1", "15.2", "15.2.1", "15.2.2", "15.2.3"]:
    k(sid, "fixed_income", "event", "long_only", "distressed debt / reorganisation data", "no", "distressed debt and loan-to-own are not tradable at Alpaca", "distressed_debt_" + sid.split(".")[1], [], "new", "L", "")
k("15.3", "us_equity", "monthly", "long_short", "failure probability / O-score / Z-score from XBRL", "yes", "", "distress_risk",
  [], "book", "M", "O-score etc. need extra XBRL tags (current assets, liabilities, debt)")
k("15.3.1", "us_equity", "monthly", "long_short", "failure probability plus risk model", "yes", "", "distress_risk", [], "book", "M", "")
# ---- chapter 16 real estate, 17 cash
for sid in ["16.2", "16.3", "16.3.1", "16.3.2", "16.3.3", "16.5", "16.6"]:
    k(sid, "other", "monthly", "long_only", "real estate / property data", "no", "physical real estate is not tradable at Alpaca (REIT ETFs are a different instrument)", "real_estate_" + sid.split(".")[1], [], "new", "L", "")
k("16.4", "other", "monthly", "long_short", "regional real estate indices", "no", "regional property indices are not tradable at Alpaca (REIT momentum is covered by the QC Momentum Effect in REITs entry)", "real_estate_momentum", [], "new", "L", "")
for sid in ["17.2", "17.3", "17.4", "17.5", "17.6"]:
    k(sid, "other", "event", "relative_value", "cash / repo / lending data", "no", "cash management, repo, pawn and lending are not trading strategies Alpaca supports", "cash_" + sid.split(".")[1], [], "new", "L", "")
# ---- chapter 18 crypto
k("18.2", "crypto", "daily", "long_only", "crypto spot prices (neural net forecast)", "yes", "spot long only", "crypto_ml_direction",
  ["dir:crypto_trend_btc", "dir:crypto_xs_momentum"], "new", "M", "local crypto bars in data/research/crypto (BTC/ETH)")
k("18.3", "crypto", "daily", "long_only", "tweet/news text sentiment, crypto prices", "yes", "spot long only", "crypto_sentiment",
  ["dir:crypto_trend_btc"], "new", "L", "sentiment text data not local")
# ---- chapter 19 macro
k("19.2", "futures", "monthly", "long_short", "macro fundamentals, global asset futures/FX", "no", "global macro book trades futures and FX", "global_macro_momentum", [], "new", "L", "")
k("19.3", "futures", "monthly", "long_short", "inflation data, commodity futures", "no", "commodity futures", "global_macro_inflation_hedge", [], "new", "L", "")
k("19.4", "fixed_income", "monthly", "long_short", "global bond yields", "no", "global bonds not tradable", "global_fixed_income", [], "new", "L", "")
k("19.5", "etf", "event", "market_timing", "economic announcement calendar (CPI, NFP, FOMC), index ETF prices", "yes", "", "macro_announcement_drift",
  ["dir:pre_fomc_announcement_drift", "dir:prediction_market_macro_release_uncertainty_premium"], "lane", "S",
  "release dates need a FRED/BLS calendar (data/raw/macro is empty); fetchable in a day")

K151_CH_NAME = {"2": "Options", "3": "Stocks", "4": "ETFs", "5": "Fixed income", "6": "Indexes", "7": "Volatility", "8": "FX", "9": "Commodities",
                "10": "Futures", "11": "Structured assets", "12": "Convertibles", "13": "Tax arbitrage", "14": "Misc assets", "15": "Distressed",
                "16": "Real estate", "17": "Cash", "18": "Crypto", "19": "Global macro", "20": "Infrastructure"}

OPT_PRIOR = ["dir:options_premium_selling_real_chain_batch", "dir:earnings_iv_crush_defined_risk_condor", "dir:put_credit_spread_income"]


def build_k151() -> list[dict]:
    toc = json.load(open(SRC / "k151_toc.json"))
    out = []
    for sid, title, page in toc["entries"]:
        if not (title.startswith("Strategy") or sid == "3.10"):
            continue
        name = title.replace("Strategy: ", "").strip()
        ch = sid.split(".")[0]
        src = f"{K151_URL}; Ch.{ch} {K151_CH_NAME.get(ch, '')}, section {sid}, p.{page}"
        if ch == "2":
            if sid in OPT_YES_DOC:
                tr, note, basis = "yes", "built from Level 1-3 documented pieces", "documented"
            elif sid in OPT_YES_INFER:
                tr, note, basis = "yes", "defined-risk multi-leg; Alpaca doc lists only 'buy call/put spread' at Level 3, legality of this exact structure inferred", "inferred"
            else:
                tr, note, basis = "no", OPT_REASON_NO.get(sid, "contains uncovered short options"), "documented"
            fam = "options_structure_" + re.sub(r"[^a-z]+", "_", name.lower()).strip("_")
            fam = {"options_structure_covered_call": "options_covered_call_income",
                   "options_structure_protective_put": "options_protective_put_collar",
                   "options_structure_collar": "options_protective_put_collar"}.get(fam, fam)
            out.append(row(
                id=f"k151-{sid}", name=name, source=src, original_paper=K151_PAPER, origin_list="k151",
                asset_class="options", frequency="monthly", direction="volatility",
                data_needed="option chains with bid/ask (and the underlying)",
                data_local="partial", data_local_detail=D_OPT_OWN,
                alpaca_tradable=tr, alpaca_note=note, alpaca_basis=basis,
                prior_ids=OPT_PRIOR if sid in ("2.2", "2.4", "2.53", "2.7", "2.8", "2.44", "2.45", "2.50", "2.51") else [],
                engine="new", complexity="M", family_key=fam,
                notes="payoff-structure entry: the book gives payoffs, not an entry signal; testable only inside a signal/vol-premium rule"))
            continue
        if sid not in K:
            raise SystemExit(f"missing K151 table entry {sid} {name}")
        asset, freq, direc, need, trad, trnote, fam, prior, engine, cx, notes = K[sid]
        if trad == "no":
            ld, ldd = "no", "n/a (not tradable)"
        elif asset == "etf" or (asset == "us_equity" and freq in ("daily", "monthly", "weekly")) :
            ld, ldd = "yes", D_DAILY
        elif freq == "intraday":
            ld, ldd = "yes", D_MIN
        else:
            ld, ldd = "partial", D_DAILY
        if asset == "crypto":
            ld, ldd = "partial", "data/research/crypto (daily BTC/ETH), no sentiment text"
        if sid in ("3.2", "3.3", "3.6", "3.20", "15.3", "15.3.1"):
            ld, ldd = ("yes" if sid in ("3.3", "3.6", "3.20") else "partial"), D_FUND
        if sid in ("3.5",):
            ld, ldd = "partial", D_OPT_OWN
        if sid in ("3.16",):
            ld, ldd = "partial", "data/features/sec_8k_ma_announcements (8-K M&A items), deal terms not local"
        if sid in ("19.5",):
            ld, ldd = "partial", "prices local; release-date calendar must be fetched"
        lane_ok = engine == "lane"
        out.append(row(
            id=f"k151-{sid}", name=name, source=src, original_paper=K151_PAPER, origin_list="k151",
            asset_class=asset, frequency=freq, direction=direc, data_needed=need, data_local=ld, data_local_detail=ldd,
            alpaca_tradable=trad, alpaca_note=trnote, prior_ids=prior, screen_lane_ready=lane_ok, engine=engine,
            lane_adapter=("template+params" if lane_ok else ""), complexity=cx, family_key=fam, notes=notes))
    # chapter 20 (no numbered strategy, one prose section)
    out.append(row(
        id="k151-20", name="Infrastructure investing", source=f"{K151_URL}; Ch.20 Infrastructure, p.123",
        original_paper=K151_PAPER, origin_list="k151", asset_class="other", frequency="monthly", direction="long_only",
        data_needed="infrastructure project / fund data", data_local="no", data_local_detail="n/a",
        alpaca_tradable="no", alpaca_note="direct infrastructure assets are not tradable at Alpaca",
        engine="new", complexity="L", family_key="infrastructure_investing", entry_type="strategy",
        notes="chapter is a prose section with no numbered strategy; registered for completeness"))
    return out


# --------------------------------------------------------------------------
# OSAP
# --------------------------------------------------------------------------
FAM = {}


def fam(name, accs):
    for a in accs.split():
        FAM[a] = name


fam("xs_price_momentum", "Mom12m Mom6m Mom12mOffSeason MomOffSeason MomOffSeason06YrPlus MomOffSeason11YrPlus MomOffSeason16YrPlus IntMom MomRev Mom6mJunk FirmAgeMom MomVol")
fam("residual_momentum", "ResidualMomentum ResidualMomentum6m")
fam("price_52wk_high", "High52")
fam("lead_lag_economic_links", "CustomerMomentum iomom_cust iomom_supp retConglomerate")
fam("industry_momentum", "IndMom IndRetBig")
fam("seasonality_same_calendar_month_xs", "MomSeason MomSeason06YrPlus MomSeason11YrPlus MomSeason16YrPlus MomSeasonShort")
fam("short_term_reversal", "STreversal REV6")
fam("long_term_reversal", "LRreversal MRreversal")
fam("trend_ma_factor", "TrendFactor")
fam("low_risk_beta", "Beta BetaFP BetaSquared BetaDimson DownsideBeta BetaLiquidityPS BetaTailRisk betaVIX BetaBDLeverage betaCC betaCR betaNet betaRC betaRR")
fam("idio_vol", "IdioVol3F IdioVolAHT IdioVolCAPM IdioVolQF RealizedVol")
fam("skewness_lottery", "ReturnSkew ReturnSkew3F ReturnSkewCAPM ReturnSkewQF Coskewness CoskewACX MaxRet ConsNegRet ConsPosRet PosNegCons")
fam("price_delay", "PriceDelayRsq PriceDelaySlope PriceDelayTstat")
fam("liquidity_volume", "DolVol Illiquidity ShareVol std_turn VolSD zerotrade6M zerotrade1M zerotrade12M BidAskSpread BidAskTAQ ProbInformedTrading VolMkt VolumeTrend")
fam("size_price", "Size Price")
fam("value_composite", "BM BMdec EP SP AM CF cfp EBM EntMult BPEBM IntanBM IntanCFP IntanEP IntanSP NetPayoutYield PayoutYield DivYieldST EquityDuration NetDebtPrice DivYield")
fam("profitability_quality", "GP OperProf OperProfRD roaq RoE CBOperProf MS PS OPLeverage AOP ChAssetTurnover CashProd Cash cashdebt")
fam("accruals", "Accruals AbnormalAccruals TotalAccruals PctAcc PctTotAcc AccrualsBM ChForecastAccrual DelCOA DelCOL")
fam("investment_growth", "AssetGrowth Investment InvGrowth InvestPPEInv grcapx grcapx3y ChInv ChInvIA ChEQ ChNWC ChNNCOA ChTax dNoa NOA GrLTNOA OrderBacklog OrderBacklogChg")
fam("external_financing_issuance", "ShareIss1Y ShareIss5Y NetEquityFinance NetDebtFinance XFIN CompEquIss CompositeDebtIssuance ConvDebt DelEqu DelFINL DelLTI DelNetFin ShareRepurchase DebtIssuance")
fam("earnings_surprise_pead", "EarningsSurprise RevenueSurprise SurpriseRD EarnSupBig EarningsStreak AnnouncementReturn NumEarnIncrease EarningsConsistency")
fam("analyst_forecast_revisions", "AnalystRevision ChangeInRecommendation ChNAnalyst FEPS fgr5yrLag ForecastDispersion EarningsForecastDisparity sfe PredictedFE Recomm_ShortInterest ConsRecomm DownRecomm UpRecomm AnalystValue")
fam("short_sale_constraints", "ShortInterest IO_ShortInterest")
fam("option_implied_stock_signals", "CPVolSpread dVolCall dVolPut dCPVolSpread OptionVolume1 OptionVolume2 RIVolSpread SmileSlope skew1")
fam("institutional_13f", "RIO_Disp RIO_MB RIO_Turnover RIO_Volatility DelBreadth Activism1 Activism2")
fam("rd_intangibles", "RD RDAbility RDcap RDS OrgCap PatentsRD CitationsRD AdExp GrAdExp BrandInvest hire")
fam("distress_risk", "OScore ZScore FailureProbability KZ WW CredRatDG")
fam("dividend_ipo_corporate_events", "DivInit DivOmit DivSeason ExchSwitch IndIPO RDIPO AgeIPO Spinoff")

PRIOR_BY_FAM = {
    "xs_price_momentum": ["dir:equity_momentum_concentrated_pwb", "dir:step10_xsmom_pit_liquidity_liquid500", "dir:signal_library_v1_price_anomalies", "dir:ml_ranking_liquid500_recent_vs_momentum_rule"],
    "residual_momentum": ["dir:multi_signal_risk_controlled_equity_book", "dir:signal_library_v1_price_anomalies"],
    "price_52wk_high": ["dir:skewness_preference_52wk_high_pwb", "dir:signal_library_v1_price_anomalies"],
    "industry_momentum": ["dir:industry_relative_momentum_and_peer_earnings_spillover", "dir:multi_signal_risk_controlled_equity_book"],
    "seasonality_same_calendar_month_xs": ["dir:multi_signal_risk_controlled_equity_book", "dir:front_running_sector_seasonality"],
    "short_term_reversal": ["dir:signal_library_v1_price_anomalies", "dir:sector_residual_reversal_statarb_decay"],
    "long_term_reversal": ["dir:signal_library_v1_price_anomalies"],
    "low_risk_beta": ["dir:signal_library_v1_price_anomalies", "dir:multi_signal_risk_controlled_equity_book"],
    "idio_vol": ["dir:signal_library_v1_price_anomalies", "dir:multi_signal_risk_controlled_equity_book"],
    "skewness_lottery": ["dir:signal_library_v1_price_anomalies"],
    "liquidity_volume": ["dir:signal_library_v1_price_anomalies"],
    "value_composite": ["dir:multi_signal_risk_controlled_equity_book", "dir:classic_long_short_anomalies_recent"],
    "profitability_quality": ["dir:multi_signal_risk_controlled_equity_book", "dir:sec_xbrl_accounting_signals_v1"],
    "accruals": ["dir:multi_signal_risk_controlled_equity_book", "dir:sec_xbrl_accounting_signals_v1"],
    "investment_growth": ["dir:multi_signal_risk_controlled_equity_book", "dir:sec_xbrl_accounting_signals_v1"],
    "external_financing_issuance": ["dir:net_share_issuance_pontiff_woodgate_recent", "dir:multi_signal_risk_controlled_equity_book"],
    "earnings_surprise_pead": ["dir:pead_classic_sue_microcap_decay", "dir:pead_xbrl_sue_filing_date", "dir:multi_signal_risk_controlled_equity_book"],
    "analyst_forecast_revisions": ["dir:analyst_estimate_revisions"],
    "short_sale_constraints": ["dir:short_interest_ratio_crowding_factor", "dir:short_interest_avoidance_gate"],
    "option_implied_stock_signals": ["dir:options_derived_signals_retail", "dir:iv_hv_spread_stock_ranking_dolthub"],
    "institutional_13f": ["dir:13f_holdings_replication", "dir:event_13d_drift"],
    "dividend_ipo_corporate_events": [],
}
# OSAP acronyms that are an exact component of the equity-book v1.x signal table (docs/equity-book-design.zh.md section 4)
IN_BOOK = set("BM EP SP cfp CF GP RoE OperProf Accruals AssetGrowth ShareIss1Y NetEquityFinance Mom12m IndMom ResidualMomentum Beta IdioVol3F IdioVolCAPM EarningsSurprise ShortInterest MomSeason".split())
# OSAP acronyms with a column in data/features/osap_price (scripts/build_osap_price_features.py)
IMPL = set("Mom6m Mom12m Mom12mOffSeason MomSeasonShort MomSeason MomOffSeason STreversal LRreversal MaxRet RealizedVol IdioVolCAPM ResidualMomentum DolVol Price PriceDelayRsq Coskewness TrendFactor MomVol".split())

CORE_TOK = set("at atq ceq ceqq seq seqq ib ibq ni niq oancf oancfq sale saleq revt revtq gp gpq oiadp oiadpq epspx epspxq epspiq csho cshoq shrout prc ret vol".split())

TRADING_NO = {"BidAskSpread": "needs quote data; Alpaca NBBO can be sampled but not for 2016+ history at scale",
              "BidAskTAQ": "needs TAQ quotes", "ProbInformedTrading": "needs TAQ trade classification",
              "BetaBDLeverage": "needs broker-dealer leverage series (Fed flow of funds)"}
OTHER_LOCAL = {"Herf": "partial", "HerfBE": "partial", "HerfAsset": "partial", "hire": "partial", "FirmAge": "partial",
               "sinAlgo": "partial", "sinOrig": "partial"}


def osap_data_local(r: dict) -> tuple[str, str]:
    a, cd, dd = r["Acronym"], r["Cat.Data"], r["Detailed Definition"]
    if cd == "Price":
        if a in ("betaVIX",):
            return "partial", "prices local; VIX history partial (data/features/regime_daily)"
        if a in ("AnnouncementReturn",):
            return "partial", "prices local; earnings announcement dates (data/features/earnings_events, 2024+) incomplete before 2024"
        if a in ("FirmAgeMom", "retConglomerate"):
            return "partial", "prices local; listing age / segment data missing"
        if a in ("IndMom", "IndRetBig"):
            return "yes", D_DAILY + "; data/features/sic_map"
        return "yes", D_DAILY + ("; data/features/osap_price column exists" if a in IMPL else "")
    if cd == "Trading":
        if a in TRADING_NO:
            return "no", TRADING_NO[a]
        if a == "ShortInterest":
            return "yes", "data/features/short_interest (FINRA bi-monthly, PIT visible_date)"
        if a in ("std_turn",):
            return "partial", "volume local; shares outstanding from " + D_FUND
        return "yes", D_DAILY + ("; data/features/osap_price column exists" if a in IMPL else "")
    if cd == "Accounting":
        toks = set(re.findall(r"\(([a-z][a-z0-9_]{1,8})\)", dd))
        extra = sorted(t for t in toks if t not in CORE_TOK)
        if not extra:
            return "yes", D_FUND + "; prices " + D_DAILY
        return "partial", f"needs XBRL tags for Compustat items {','.join(extra)} from {D_XBRL}"
    if cd == "Analyst":
        return "no", "needs IBES analyst forecasts/recommendations; no local analyst data"
    if cd == "13F":
        return "no", "needs 13F holdings (Thomson/WRDS or parsed SEC 13F); not local"
    if cd == "Options":
        return "partial", "needs option volume/IV by stock; " + D_OPT_OWN
    if cd == "Event":
        if a == "Spinoff":
            return "partial", "needs spin-off event list (SEC Form 10 / 8-K)"
        return "partial", "needs corporate-event dates (dividends from price adjustments, IPO dates); not built"
    if cd == "Other":
        if a in ("CitationsRD", "PatentsRD", "CustomerMomentum", "iomom_cust", "iomom_supp", "Governance"):
            return "no", "needs patent/citation, customer-supplier, input-output or governance data; not local"
        return OTHER_LOCAL.get(a, "partial"), "needs segment/SIC/employee data from XBRL or sic_map; adapter needed"
    return "partial", ""


def build_osap() -> list[dict]:
    rows = list(csv.DictReader(open(SRC / "osap_SignalDoc.csv")))
    out = []
    for r in rows:
        a = r["Acronym"]
        f = FAM.get(a) or "osap_econ_" + re.sub(r"[^a-z]+", "_", (r["Cat.Economic"] or "other").lower()).strip("_")
        ld, ldd = osap_data_local(r)
        cs = r["Cat.Signal"]
        in_book = a in IN_BOOK
        prior = list(PRIOR_BY_FAM.get(f, []))
        prior.append("dir:osap_ml_ranking")
        if r["Cat.Data"] in ("Price", "Trading") and a in IMPL:
            prior.append("dir:ml_ranking_liquid500_recent_vs_momentum_rule")
        if cs != "Predictor":
            prior = []
        paper = f"{r['Authors']} ({r['Year']}), {r['LongDescription']}, {r['Journal']}"
        tr, trn = "yes", "long leg at Alpaca; short leg only on easy-to-borrow names with borrow cost modeled (equity-book SE_t)"
        if r["Cat.Data"] == "Event" and a in ("ExchSwitch",):
            pass
        cx = "S" if (ld == "yes" and (a in IMPL or r["Cat.Data"] in ("Price", "Trading") or a in IN_BOOK)) else ("M" if ld in ("yes", "partial") else "L")
        if r["Cat.Data"] == "Accounting" and ld == "yes":
            cx = "S"
        notes = f"OSAP Cat.Signal={cs}; predictability in OP={r['Predictability in OP']}; replication quality={r['Signal Rep Quality']}; sample {r['SampleStartYear']}-{r['SampleEndYear']}; economic category={r['Cat.Economic']}"
        if cs != "Predictor":
            notes += ". Not a published predictor (placebo/drop) -- registered but excluded from screening."
        if in_book:
            notes += ". Already a component of the equity-book v1.x signal table (testing)."
        e = row(
            id=f"osap-{a}", name=r["LongDescription"] or a,
            source=f"Open Source Asset Pricing SignalDoc.csv row {a} (https://github.com/OpenSourceAP/CrossSection/blob/master/SignalDoc.csv; https://www.openassetpricing.com)",
            original_paper=paper, origin_list="osap", asset_class="us_equity",
            frequency=("event" if r["Cat.Data"] == "Event" else "monthly"), direction="long_short",
            data_needed=f"{r['Cat.Data']} data: " + (r["Detailed Definition"][:160] + "...") if r["Detailed Definition"] else r["Cat.Data"],
            data_local=ld, data_local_detail=ldd, alpaca_tradable=tr, alpaca_note=trn,
            prior_ids=_check(prior), engine="book", complexity=cx, family_key=f, notes=notes,
            entry_type=("strategy" if cs == "Predictor" else cs.lower()))
        e["prior_scope"] = "none" if not e["prior_ids"] else ("specific" if (a in IN_BOOK or a in IMPL) else "family_level")
        e["osap_predictability"] = r["Predictability in OP"]
        e["osap_rep_quality"] = r["Signal Rep Quality"]
        e["osap_year"] = int(r["Year"]) if r["Year"].isdigit() else 0
        e["osap_cat_signal"] = cs
        e["osap_cat_data"] = r["Cat.Data"]
        e["feature_column_exists"] = a in IMPL
        e["in_equity_book"] = in_book
        out.append(e)
    return out


# --------------------------------------------------------------------------
# QuantConnect Strategy Library
# --------------------------------------------------------------------------
QC = {}


def q(slug, asset, freq, direc, local, trad, trnote, family, prior, engine, cx, notes=""):
    QC[slug] = (asset, freq, direc, local, trad, trnote, family, prior, engine, cx, notes)


NOF = "futures/FX/CFD not tradable at Alpaca"
q("12-month-cycle-in-cross-section-of-stocks-returns", "us_equity", "monthly", "long_short", "yes", "yes", "", "seasonality_same_calendar_month_xs", ["dir:multi_signal_risk_controlled_equity_book"], "book", "S", "Heston-Sadka same-calendar-month seasonality")
q("accrual-anomaly", "us_equity", "monthly", "long_short", "yes", "yes", "", "accruals", ["dir:multi_signal_risk_controlled_equity_book"], "book", "S")
q("asset-class-momentum", "etf", "monthly", "long_only", "yes", "yes", "", "cross_asset_etf_trend", ["dir:step10_cross_asset_trend_tsmom_etf", "dir:keller_antonacci_faber_taa_batch1_2026"], "lane", "S")
q("asset-class-trend-following", "etf", "monthly", "long_only", "yes", "yes", "", "cross_asset_etf_trend", ["dir:step10_cross_asset_trend_tsmom_etf"], "lane", "S")
q("asset-growth-effect", "us_equity", "monthly", "long_short", "yes", "yes", "", "investment_growth", ["dir:multi_signal_risk_controlled_equity_book"], "book", "S")
q("beta-factor-in-country-equity-indexes", "etf", "monthly", "long_short", "yes", "yes", "", "low_risk_beta", ["dir:international_country_etf_momentum_rotation"], "lane", "S", "long-only low-beta country ETF variant fits the lane")
q("beta-factors-in-stocks", "us_equity", "monthly", "long_short", "yes", "yes", "", "low_risk_beta", ["dir:multi_signal_risk_controlled_equity_book", "dir:signal_library_v1_price_anomalies"], "book", "S")
q("book-to-market-value-anomaly", "us_equity", "monthly", "long_short", "yes", "yes", "", "value_composite", ["dir:multi_signal_risk_controlled_equity_book"], "book", "S")
q("can-crude-oil-predict-equity-returns", "etf", "monthly", "market_timing", "partial", "yes", "", "oil_predicts_equity_timing", [], "lane", "S", "oil price proxied by USO/DBO ETF closes; futures series not local")
q("capm-alpha-ranking-strategy-on-dow-30-companies", "us_equity", "monthly", "long_only", "yes", "yes", "", "capm_alpha_ranking", [], "lane", "S", "30 large caps, long-only fits lane")
q("combining-mean-reversion-and-momentum-in-forex-market", "fx", "daily", "long_short", "no", "no", NOF, "fx_momentum_carry", [], "new", "L")
q("combining-momentum-effect-with-volume", "us_equity", "monthly", "long_short", "yes", "yes", "", "momentum_with_volume", ["dir:signal_library_v1_price_anomalies"], "book", "S")
q("commodities-futures-trend-following", "futures", "daily", "long_short", "no", "no", NOF, "futures_trend_following", [], "new", "L")
q("dual-thrust-trading-algorithm", "us_equity", "intraday", "long_short", "yes", "yes", "", "intraday_breakout_dual_thrust", ["dir:orb_etf_opening_range_breakout", "dir:spy_noise_band_intraday"], "new", "M", "hourly/intraday range breakout; minute data local")
q("earnings-quality-factor", "us_equity", "monthly", "long_short", "partial", "yes", "", "profitability_quality", ["dir:multi_signal_risk_controlled_equity_book"], "book", "M", "needs extra XBRL tags")
q("expected-idiosyncratic-skewness", "us_equity", "monthly", "long_short", "yes", "yes", "", "skewness_lottery", ["dir:signal_library_v1_price_anomalies"], "book", "S")
q("exploiting-term-structure-of-vix-futures", "futures", "daily", "volatility", "no", "no", "VIX futures not tradable at Alpaca (VXX/SVXY ETP proxy is k151-7.3)", "vix_term_structure_carry", ["dir:vix_term_structure_short_vol"], "new", "M")
q("fama-french-five-factors", "us_equity", "monthly", "long_short", "partial", "yes", "", "ff5_style_factors", ["dir:classic_long_short_anomalies_recent"], "book", "M", "profitability/investment need accounting tags")
q("forecasting-stock-prices-using-a-temporal-cnn-model", "us_equity", "intraday", "long_short", "no", "yes", "", "lob_deep_learning", ["dir:deep_sequence_tabular_foundation_models_gpu"], "new", "L", "needs limit-order-book data (FI-2010 style); not local; deep model", )
q("forex-carry-trade", "fx", "monthly", "long_short", "no", "no", NOF, "fx_carry", [], "new", "L")
q("forex-momentum", "fx", "monthly", "long_short", "no", "no", NOF, "fx_momentum_carry", [], "new", "L")
q("fundamental-factor-long-short-strategy", "us_equity", "monthly", "long_short", "yes", "yes", "", "value_composite", ["dir:multi_signal_risk_controlled_equity_book", "dir:fundamental_scoring_dcf_lynch_retail_product"], "book", "S")
q("g-score-investing", "us_equity", "monthly", "long_short", "partial", "yes", "", "profitability_quality", [], "book", "M", "Mohanram G-score: growth stocks, needs R&D/capex/advertising tags")
q("gold-market-timing", "etf", "monthly", "market_timing", "yes", "yes", "", "gold_timing", ["dir:levered_gold_trend_sleeve"], "lane", "S", "trade GLD/UGL instead of futures")
q("gaussian-naive-bayes-model", "us_equity", "daily", "long_short", "yes", "yes", "", "ml_single_asset_direction", [], "new", "M")
q("gradient-boosting-model", "us_equity", "intraday", "long_short", "yes", "yes", "", "ml_intraday_direction", ["dir:minute_bar_momentum_multipath"], "new", "M", "minute-bar GBDT direction model")
q("ichimoku-clouds-in-the-energy-sector", "us_equity", "daily", "long_short", "yes", "yes", "", "ichimoku_technical", [], "lane", "S", "owner ranks pure technical indicators lowest (09-11)")
q("improved-momentum-strategy-on-commodities-futures", "futures", "monthly", "long_short", "no", "no", NOF, "futures_trend_following", [], "new", "L")
q("intraday-arbitrage-between-index-etfs", "etf", "intraday", "relative_value", "yes", "yes", "", "intraday_etf_arbitrage", ["dir:etf_constituent_lead_lag_reversion"], "new", "M")
q("intraday-dynamic-pairs-trading-using-correlation-and-cointegration-approach", "us_equity", "intraday", "relative_value", "yes", "yes", "", "intraday_pairs", ["dir:intraday_cointegration_pairs_pca"], "new", "M")
q("intraday-etf-momentum", "etf", "intraday", "long_short", "yes", "yes", "", "single_etf_intraday_momentum", ["dir:single_etf_intraday_momentum_cost_adjusted", "dir:spy_noise_band_intraday"], "new", "M")
q("january-barometer", "etf", "monthly", "market_timing", "yes", "yes", "", "calendar_seasonality_index", [], "lane", "S")
q("january-effect-in-stocks", "etf", "monthly", "long_only", "yes", "yes", "", "calendar_seasonality_index", ["dir:tax_loss_selling_year_end_rebound"], "lane", "S", "small-cap vs large-cap January")
q("leveraged-etfs-with-systematic-risk-management", "etf", "daily", "long_only", "yes", "yes", "", "levered_sector_trend", ["dir:letf_published_rules_live_tracked", "dir:s3_levered_rotation_voltarget_dip_boost"], "lane", "S")
q("liquidity-effect-in-stocks", "us_equity", "monthly", "long_short", "yes", "yes", "", "liquidity_volume", ["dir:signal_library_v1_price_anomalies"], "book", "S")
q("lunar-cycle-in-equity-market", "etf", "daily", "market_timing", "yes", "yes", "", "lunar_cycle_timing", [], "lane", "S", "lunar calendar is computable; no data purchase")
q("mean-reversion-effect-in-country-equity-indexes", "etf", "monthly", "long_only", "yes", "yes", "", "country_etf_mean_reversion", ["dir:international_country_etf_momentum_rotation"], "lane", "S")
q("mean-reversion-statistical-arbitrage-strategy-in-stocks", "us_equity", "daily", "long_short", "yes", "yes", "", "stat_arb_cluster_reversion", ["dir:deep_learning_stat_arb_residual", "dir:sector_residual_reversal_statarb_decay"], "new", "M", "Avellaneda-Lee PCA/ETF residual reversion")
q("momentum-and-reversal-combined-with-volatility-effect-in-stocks", "us_equity", "monthly", "long_short", "yes", "yes", "", "momentum_with_volume", ["dir:signal_library_v1_price_anomalies"], "book", "S")
q("momentum-and-state-of-market-filters", "us_equity", "monthly", "long_short", "yes", "yes", "", "xs_price_momentum", ["dir:momentum_daily_crash_guard", "dir:equity_momentum_concentrated_pwb"], "book", "S")
q("momentum-and-style-rotation-effect", "etf", "monthly", "long_only", "yes", "yes", "", "factor_style_etf_rotation", ["dir:factor_style_etf_momentum_rotation"], "lane", "S")
q("momentum-effect-combined-with-term-structure-in-commodities", "futures", "monthly", "long_short", "no", "no", NOF, "futures_trend_following", [], "new", "L")
q("momentum-effect-in-commodities-futures", "futures", "monthly", "long_short", "no", "no", NOF, "futures_trend_following", [], "new", "L")
q("momentum-effect-in-country-equity-indexes", "etf", "monthly", "long_only", "yes", "yes", "", "country_etf_momentum", ["dir:international_country_etf_momentum_rotation"], "lane", "S")
q("momentum-effect-in-reits", "us_equity", "monthly", "long_short", "yes", "yes", "", "xs_price_momentum", [], "lane", "S", "REIT universe; long-only top-N fits lane")
q("momentum-effect-in-stocks-in-small-portfolios", "us_equity", "monthly", "long_only", "yes", "yes", "", "xs_price_momentum", ["dir:equity_momentum_concentrated_pwb", "dir:clenow_stocks_on_the_move_momentum"], "book", "S")
q("momentum-effect-in-stocks", "us_equity", "monthly", "long_short", "yes", "yes", "", "xs_price_momentum", ["dir:equity_momentum_concentrated_pwb", "dir:step10_xsmom_pit_liquidity_liquid500"], "book", "S")
q("momentum-in-mutual-fund-returns", "other", "monthly", "long_short", "no", "no", "mutual funds are not tradable at Alpaca; tutorial page returns 'Page Not Found' in the 2026-10-06 snapshot", "mutual_fund_momentum", [], "new", "L")
q("momentum-short-term-reversal-strategy", "us_equity", "monthly", "long_short", "yes", "yes", "", "momentum_with_volume", ["dir:signal_library_v1_price_anomalies"], "book", "S")
q("optimal-pairs-trading", "us_equity", "daily", "relative_value", "yes", "yes", "", "stat_arb_pairs", ["dir:intraday_cointegration_pairs_pca"], "new", "M")
q("option-expiration-week-effect", "etf", "event", "long_only", "yes", "yes", "", "option_expiration_week", ["dir:option_expiration_week_calendar_effect"], "lane", "S", "lane template h20260928_42_opex_week exists")
q("overnight-anomaly", "etf", "daily", "long_only", "yes", "yes", "", "overnight_return", ["dir:overnight_return_persistence_auction", "dir:overnight_intraday_gap_retail_pwb"], "new", "S", "close-to-open holding: lane fills at next open, so needs a close-fill variant")
q("paired-switching", "etf", "monthly", "long_only", "yes", "yes", "", "etf_pair_relative_strength", ["dir:etf_pair_relative_strength_switch"], "lane", "S")
q("pairs-trading-copula-vs-cointegration", "us_equity", "daily", "relative_value", "yes", "yes", "", "stat_arb_pairs", [], "new", "M")
q("pairs-trading-with-country-etfs", "etf", "daily", "relative_value", "yes", "yes", "", "stat_arb_pairs", [], "new", "M")
q("pairs-trading-with-stocks", "us_equity", "daily", "relative_value", "yes", "yes", "", "stat_arb_pairs", [], "new", "M")
q("pre-holiday-effect", "etf", "event", "long_only", "yes", "yes", "", "pre_holiday_effect", ["dir:pre_holiday_effect_small_cap_tier"], "lane", "S", "lane template h20260929_02_pre_holiday_etf exists")
q("price-and-earnings-momentum", "us_equity", "monthly", "long_short", "yes", "yes", "", "earnings_surprise_pead", ["dir:multi_signal_risk_controlled_equity_book"], "book", "S")
q("price-earnings-anomaly", "us_equity", "monthly", "long_short", "yes", "yes", "", "value_composite", ["dir:multi_signal_risk_controlled_equity_book"], "book", "S")
q("residual-momentum", "us_equity", "monthly", "long_short", "yes", "yes", "", "residual_momentum", ["dir:multi_signal_risk_controlled_equity_book"], "book", "S")
q("risk-premia-in-forex-markets", "fx", "monthly", "long_short", "no", "no", NOF, "fx_carry", [], "new", "L")
q("roa-effect-within-stocks", "us_equity", "monthly", "long_short", "yes", "yes", "", "profitability_quality", ["dir:multi_signal_risk_controlled_equity_book"], "book", "S")
q("seasonality-effect-based-on-same-calendar-month-returns", "us_equity", "monthly", "long_short", "yes", "yes", "", "seasonality_same_calendar_month_xs", ["dir:multi_signal_risk_controlled_equity_book", "dir:front_running_sector_seasonality"], "book", "S")
q("sector-momentum", "etf", "monthly", "long_only", "yes", "yes", "", "etf_momentum_rotation", ["dir:s1_sector_rotation_voltarget", "dir:sector_momentum_middle_tier_buy"], "lane", "S")
q("sentiment-and-style-rotation-effect-in-stocks", "etf", "monthly", "long_only", "partial", "yes", "", "factor_style_etf_rotation", ["dir:factor_style_etf_momentum_rotation"], "lane", "M", "sentiment series (AAII-type) not local")
q("short-term-reversal-strategy-in-stocks", "us_equity", "weekly", "long_short", "yes", "yes", "", "short_term_reversal", ["dir:signal_library_v1_price_anomalies"], "lane", "S", "top-100 liquid, weekly; long-worst-decile leg fits the lane")
q("short-term-reversal-with-futures", "futures", "weekly", "long_short", "no", "no", NOF, "short_term_reversal", [], "new", "L")
q("short-term-reversal", "us_equity", "weekly", "long_short", "yes", "yes", "", "short_term_reversal", ["dir:signal_library_v1_price_anomalies"], "lane", "S")
q("small-capitalization-stocks-premium-anomaly", "etf", "monthly", "long_short", "yes", "yes", "", "size_price", ["dir:small_cap_background_drift_short_basket"], "lane", "S", "IWM/IJR vs SPY")
q("standardized-unexpected-earnings", "us_equity", "event", "long_short", "yes", "yes", "", "earnings_surprise_pead", ["dir:pead_classic_sue_microcap_decay", "dir:pead_xbrl_sue_filing_date"], "book", "S")
q("stock-selection-strategy-based-on-fundamental-factors", "us_equity", "monthly", "long_only", "yes", "yes", "", "value_composite", ["dir:multi_signal_risk_controlled_equity_book"], "book", "S")
q("svm-wavelet-forecasting", "us_equity", "daily", "market_timing", "yes", "yes", "", "ml_single_asset_direction", [], "new", "M")
q("term-structure-effect-in-commodities", "futures", "monthly", "long_short", "no", "no", NOF, "futures_trend_following", [], "new", "L")
q("the-dynamic-breakout-ii-strategy", "us_equity", "daily", "market_timing", "yes", "yes", "", "breakout_channel", [], "lane", "S", "original system is futures-based; QC tutorial applies it to a liquid instrument -- asset unverified")
q("the-momentum-strategy-based-on-the-low-frequency-component-of-forex-market", "fx", "daily", "long_short", "no", "no", NOF, "fx_ma_hp", [], "new", "L")
q("time-series-momentum-effect", "futures", "monthly", "long_short", "no", "no", "futures; tutorial page returns 'Page Not Found' in the snapshot (ETF TSMOM is k151-4.6)", "futures_trend_following", ["dir:step10_cross_asset_trend_tsmom_etf"], "new", "L")
q("trading-with-wti-brent-spread", "futures", "daily", "relative_value", "no", "no", NOF, "commodity_spread", [], "new", "L")
q("turn-of-the-month-in-equity-indexes", "etf", "event", "long_only", "yes", "yes", "", "turn_of_month", ["dir:turn_of_month_equity_seasonality"], "lane", "S")
q("using-news-sentiment-to-predict-price-direction-of-drug-manufacturers", "us_equity", "event", "long_short", "partial", "yes", "", "news_sentiment_trading", ["dir:news_sentiment_trading_pwb", "dir:news_attention_features"], "new", "M", "news packets 2024+ only (data/features/news_packets)")
q("value-effect-within-countries", "etf", "monthly", "long_only", "partial", "yes", "", "country_etf_value", [], "lane", "M", "CAPE/valuation by country not local")
q("vix-predicts-stock-index-returns", "etf", "monthly", "market_timing", "partial", "yes", "", "vix_timing", ["dir:vix_term_structure_short_vol"], "lane", "S", "VIX history in data/features/regime_daily / data/options/vix_term (short)")
q("volatility-effect-in-stocks", "us_equity", "monthly", "long_short", "yes", "yes", "", "low_risk_beta", ["dir:signal_library_v1_price_anomalies"], "book", "S")
q("volatility-risk-premium-effect", "options", "monthly", "volatility", "partial", "no", "tutorial sells ATM options (uncovered short); defined-risk restructuring tracked in registry", "variance_risk_premium_options", ["dir:options_premium_selling_real_chain_batch"], "new", "L")

QC_SRC_URL = "https://www.quantconnect.com/tutorials/strategy-library/"


def build_qc() -> list[dict]:
    meta = json.load(open(SRC / "qc_meta.json"))
    by = {}
    for m in meta:
        s = m["slug"].lower()
        if s in by:
            continue  # the low-frequency-component forex page appears under two capitalisations
        by[s] = m
    out = []
    for slug_l, m in by.items():
        key = slug_l if slug_l in QC else next((k_ for k_ in QC if k_.lower() == slug_l), None)
        if key is None:
            raise SystemExit(f"missing QC table entry {slug_l}")
        asset, freq, direc, local, trad, trnote, family, prior, engine, cx, notes = QC[key]
        ref = m.get("ref", "").strip() or "reference not extracted"
        ldd = {"yes": D_DAILY if freq != "intraday" else D_MIN, "partial": "see notes", "no": "n/a" if trad == "no" else "not local"}[local]
        title = m["title"] if m["title"] != "Sorry Page Not Found" else key.replace("-", " ").title() + " (page not found in snapshot)"
        e = row(
            id="qc-" + key, name=title, source=f"QuantConnect Strategy Library: {QC_SRC_URL}{key} (fetched 2026-10-06)",
            original_paper=ref, origin_list="qc", asset_class=asset, frequency=freq, direction=direc,
            data_needed=("QC tutorial: " + (m.get("intro", "")[:120] or "see page")),
            data_local=local, data_local_detail=ldd, alpaca_tradable=trad, alpaca_note=trnote,
            prior_ids=_check(prior), screen_lane_ready=(engine == "lane" and trad == "yes" and local == "yes"),
            engine=engine, lane_adapter=("template+params" if engine == "lane" else ""), complexity=cx, family_key=family, notes=notes)
        out.append(e)
    return out


# --------------------------------------------------------------------------
# Registry supplement (categories where the three public lists are thin)
# --------------------------------------------------------------------------
REG_CATS = {"intraday": "intraday", "hf_factor": "intraday", "event": "event", "alt_data": "monthly", "crypto": "daily",
            "options": "event", "text_llm": "event"}
REG_ASSET = {"intraday": "us_equity", "hf_factor": "us_equity", "event": "us_equity", "alt_data": "us_equity", "crypto": "crypto",
             "options": "options", "text_llm": "us_equity"}
REG_ENGINE_OK = {"intraday", "hf_factor"}


def build_reg() -> list[dict]:
    out = []
    for i, r in DIRS.items():
        if r["category"] not in REG_CATS or r["status"] == "duplicate":
            continue
        slug = i.replace("dir:", "")
        cat = r["category"]
        exe = str(r.get("executable_for_us") or "")
        notexec = r["status"] == "not_executable"
        srcs = r.get("sources") or []
        src_txt = "; ".join(s.get("url", "") for s in srcs[:2]) or "registry record (reports/research/harvest/directions.jsonl)"
        ldesc = r.get("data_needs") or ""
        if notexec:
            local, ldd = "no", "registry status not_executable: " + (exe[:100] or r.get("verdict", "")[:100])
        elif cat in ("intraday", "hf_factor"):
            partial_ids = {"dir:closing_auction_imbalance_signal", "dir:high_freq_news_return_underreaction_drift",
                           "dir:extended_hours_earnings_post_announcement_drift"}
            local = "partial" if i in partial_ids else "yes"
            ldd = D_MIN + " (broad-universe minute panel is heavy: Modal)" + ("; extra feed/coverage not verified" if i in partial_ids else "")
        elif cat == "crypto":
            local, ldd = "partial", "data/research/crypto (daily BTC/ETH)"
        elif cat == "options":
            local, ldd = "partial", D_OPT_OWN
        else:
            low = str(ldesc).lower()
            have = ("(have" in low or "have)" in low or "on hand" in low or "all have" in low or "built," in low)
            lack = any(t in low for t in ("do not have", "not yet", "not budgeted", "paywalled", "not acquired", "paid ", "not currently", "no free", "(not "))
            local = "yes" if have and not lack else "partial"
            ldd = "registry data_needs: " + str(ldesc)[:140]
        trad = "no" if notexec else "yes"
        e = row(
            id="reg-" + slug, name=r["name"], source=f"local registry {i} ({src_txt})", original_paper="; ".join(r.get("aliases", [])[:3]),
            origin_list="reg", asset_class=REG_ASSET[cat], frequency=REG_CATS[cat],
            direction=("long_short" if cat in ("intraday", "hf_factor", "event", "alt_data") else "long_only"),
            data_needed=str(ldesc)[:200], data_local=local, data_local_detail=ldd,
            alpaca_tradable=trad, alpaca_note=(exe[:160] or ""), prior_ids=[i], engine="new", complexity=("M" if not notexec else "L"),
            family_key=r.get("family_key") or slug,
            notes=f"registry-derived row (category {cat}); fields are coarser than the three public lists. registry status {r['status']}, updated {r['updated']}")
        e["registry_priority"] = r.get("priority", "")
        out.append(e)
    return out


ONE_DAY_IDS = {
    "k151-19.5": "FRED/BLS release-date calendar fetch",
    "qc-can-crude-oil-predict-equity-returns": "USO/DBO ETF closes already in data/sip/daily",
    "qc-vix-predicts-stock-index-returns": "VIX daily history from Cboe/FRED",
    "osap-betaVIX": "VIX daily history from Cboe/FRED",
    "osap-std_turn": "shares outstanding from sec_fundamentals_daily joined to SIP volume",
}


def flag_adapters(rows: list[dict]) -> None:
    """adapter_1d: a missing input that one scripted fetch/parse closes within a day.
    Rule (fixed before selection): OSAP Accounting rows missing at most 2 Compustat tags
    (one extra XBRL parse pass over companyfacts.zip), plus the explicit ids above."""
    for r in rows:
        if r["data_local"] == "yes":
            r["adapter_1d"] = True
            continue
        if r["id"] in ONE_DAY_IDS:
            r["adapter_1d"], r["adapter_note"] = True, ONE_DAY_IDS[r["id"]]
        elif r["origin_list"] == "osap" and r["osap_cat_data"] == "Accounting" and r["data_local"] == "partial":
            m = re.search(r"Compustat items ([a-z0-9_,]+) from", r["data_local_detail"])
            tags = m.group(1).split(",") if m else []
            if 0 < len(tags) <= 2:
                r["adapter_1d"], r["adapter_note"] = True, f"one XBRL parse pass for {','.join(tags)}"


def main() -> None:
    rows = build_k151() + build_osap() + build_qc() + build_reg()
    flag_adapters(rows)
    # mark registry-derived rows that duplicate a public-list family so they are merged in families.json
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate ids"
    json.dump(rows, open(HERE / "catalog.json", "w"), ensure_ascii=False, indent=1)
    fams: dict[str, dict] = {}
    for r in rows:
        f = fams.setdefault(r["family_key"], {"family_key": r["family_key"], "members": [], "origins": set(), "asset_classes": set()})
        f["members"].append(r["id"])
        f["origins"].add(r["origin_list"])
        f["asset_classes"].add(r["asset_class"])
    fl = [dict(family_key=f["family_key"], n_members=len(f["members"]), origins=sorted(f["origins"]),
               asset_classes=sorted(f["asset_classes"]), members=f["members"]) for f in fams.values()]
    json.dump(sorted(fl, key=lambda x: -x["n_members"]), open(HERE / "families.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(len(rows), Counter(r["origin_list"] for r in rows), len(fl), "families")


if __name__ == "__main__":
    main()
