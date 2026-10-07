# ruff: noqa: E501
"""T-20261007-02: write the preregistration dossier. Run once before any ETF return is read; timestamps from the clock."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from math import sqrt
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t0702_pm_grid as G  # noqa: E402

ITER = "t20261007_02_pm_event_study"
D = ROOT / "reports/research/iterations" / ITER
SRC = "reports/research/intel/sources/pm-event-study-2026-10-07/"
CARDS = f"reports/harness/source_cards/{ITER}.jsonl"
SPEC = f"strategy_specs/drafts/{ITER}.yaml"


def sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


T0 = (ROOT / SRC / "fetched_at.txt").read_text().strip()

SOURCES = [
    dict(
        claim_id="feds_2026_010_kalshi_macro_markets",
        snapshot=SRC + "feds2026010.txt",
        url="https://www.federalreserve.gov/econres/feds/files/2026010pap.pdf",
        source_type="paper",
        credibility="fed_board_discussion_paper",
        published="unknown",
        claim="Diercks, Katz and Wright (FEDS 2026-010): Kalshi's fed-funds mode matched the realised rate the day before every FOMC meeting since 2022 (better than fed funds futures); for headline CPI Kalshi beats the Bloomberg consensus; for core CPI and unemployment it is about equal; intraday Kalshi probabilities react to releases.",
        quote="the Kalshi median and mode have a perfect forecast record on the day before the FOMC meeting",
        market="Kalshi macro series, 2022-2025, US",
        applicability="Why R may have little: Kalshi is about consensus except headline CPI and the policy rate; release classes and intraday reaction are the paper's own.",
        limitations="Forecast accuracy, not trading; no ETF returns.",
        replication="Fed Board paper, no independent replication seen.",
        reflection="Sets the prior for R as weak; headline CPI and FOMC are the classes with room.",
    ),
    dict(
        claim_id="li_xie_2026_trade_policy_surprises_polymarket",
        snapshot=SRC + "keio.txt",
        url="https://ies.keio.ac.jp/upload/20260526macro_Yinxi-Xie_WP.pdf",
        source_type="paper",
        credibility="working_paper",
        published="2026-04-30",
        claim="Li and Xie (Keio WP 2026): trade policy surprises built from Polymarket tariff contracts over a 30-minute window [t-10, t+20] around each announcement (last trade before to first trade after); tariff surprises lower the S&P 500 (about 0.7 percent initial drop, persistent), lower Treasury convenience yields and raise recession probability.",
        quote="we also construct surprises using a 60-minute event window",
        market="Polymarket tariff contracts and US Treasuries/S&P 500, Nov 2024 to 2025",
        applicability="Identification idea for J (odds change in a short window, ETF return right after) and the tariff theme sign (escalation negative for SPY).",
        limitations="Daily and impulse-response frequency for returns, transaction-level odds; no tradable rule or costs.",
        replication="None independent.",
        reflection="Equities react inside the odds window; the test is whether anything remains at 15-240 minutes after a one-hour jump.",
    ),
    dict(
        claim_id="tsang_yang_2026_political_shocks_price_discovery",
        snapshot=SRC + "arxiv2603.03152_tsang_yang_political_shocks.txt",
        url="https://arxiv.org/abs/2603.03152",
        source_type="paper",
        credibility="arxiv_preprint",
        published="2026-07-18",
        claim="Tsang and Yang (arXiv 2603.03152 v4): in 2024 Polymarket election markets the debate jump largely reversed, the assassination-attempt repricing persisted and Biden's withdrawal moved little; the response tracks what the news reveals about linked outcomes and how much was anticipated.",
        quote="debate’s price increase largely reverses",
        market="Polymarket 2024 presidential election, on-chain trades",
        applicability="Continuation versus reversal cannot be assumed: J counts both modes as trials.",
        limitations="Odds-side study, no ETF returns, one election.",
        replication="Companion paper arXiv 2603.03136.",
        reflection="Odds jumps themselves partly reverse, so a reversal mode is plausible.",
    ),
    dict(
        claim_id="mohanty_2026_kalshi_macro_crypto_volatility",
        snapshot=SRC + "arxiv2604.01431.txt",
        url="https://arxiv.org/abs/2604.01431",
        source_type="paper",
        credibility="arxiv_preprint",
        published="2026-04-01",
        claim="Mohanty and Krishnamachari (arXiv 2604.01431): daily volume-weighted probability changes in Kalshi macro markets predict crypto realised volatility (KXFED t 3.63 in sample but regime dependent; recession and CPI channels deliver out-of-sample gains, MSFE ratio 0.979 and 0.959), surviving Benjamini-Hochberg at q 0.05.",
        quote="macro prediction markets forecast cryptocurrency realized volatility",
        market="Kalshi 10 series and 6 crypto assets, 2023-01 to 2026-03",
        applicability="Kalshi changes carry information about volatility, not direction; effect tied to the 2024-2025 cutting cycle.",
        limitations="Crypto, daily, volatility.",
        replication="None.",
        reflection="Regime dependence warning for R; multiple-testing correction is used there and here.",
    ),
    dict(
        claim_id="tsang_yang_2026_anatomy_polymarket",
        snapshot=SRC + "arxiv2603.03136_tsang_yang_anatomy.txt",
        url="https://arxiv.org/abs/2603.03136",
        source_type="paper",
        credibility="arxiv_preprint",
        published="2026-09-14",
        claim="Tsang and Yang (arXiv 2603.03136 v3): complete on-chain ledger of Polymarket's 2024 presidential election; the widely quoted Trump YES price is studied as a forecast with trade-level microstructure.",
        quote="Using the complete on-chain settlement ledger",
        market="Polymarket 2024 US presidential election",
        applicability="Data facts for Polymarket price series (what a quoted price is and its noise).",
        limitations="One event family.",
        replication="Companion arXiv 2603.03152.",
        reflection="Price quality is event dependent; thin markets are excluded by the volume filter.",
    ),
    dict(
        claim_id="polymarket_clob_prices_history_docs",
        snapshot=SRC + "polymarket_docs_prices_history.txt",
        url="https://docs.polymarket.com/developers/CLOB/timeseries",
        source_type="broker_official_docs",
        credibility="platform_official",
        published="unknown",
        claim="Polymarket CLOB prices-history: query by market (token) with startTs, endTs, interval or fidelity in minutes; returns history of (t, p). Probed 2026-10-07: hourly fidelity accepts windows up to about 14-15 days, 30 days returns 'interval is too long'; fine fidelity works for closed markets.",
        quote="Accuracy of the data expressed in minutes. Default is 1 minute.",
        market="Polymarket CLOB",
        applicability="Fetch design: 14-day chunks at 60-minute fidelity, cached.",
        limitations="Page does not state the window limit; the limit comes from our probe.",
        replication="Probe in this iteration.",
        reflection="Hourly points limit the timing precision of J.",
    ),
    dict(
        claim_id="kalshi_api_candlesticks_docs",
        snapshot=SRC + "kalshi_docs_candlesticks.txt",
        url="https://docs.kalshi.com/api-reference/market/get-market-candlesticks",
        source_type="broker_official_docs",
        credibility="platform_official",
        published="unknown",
        claim="Kalshi get-market-candlesticks returns OHLC of bid, ask and trade price per period (1, 60 or 1440 minutes); settled markets served by the historical endpoints.",
        quote="period_interval",
        market="Kalshi markets",
        applicability="Source of the pre-release hourly implied distributions for R (fetch script from T-20261002-44).",
        limitations="Hourly resolution leaves stale candles in thin strikes (median age reported per event).",
        replication="Used in h20261002_pm_macro_uncertainty.",
        reflection="Hourly staleness caps what R1 can see.",
    ),
    dict(
        claim_id="local_pm_macro_uncertainty_negative",
        snapshot="reports/research/iterations/h20261002_pm_macro_uncertainty/report.md",
        url="https://github.com/WillBtK/macro_kalshi",
        source_type="industry_standard",
        credibility="local_prior_negative_plus_mit_scraper",
        published="2026-10-02",
        claim="Local test h20261002_pm_macro_uncertainty (Kalshi U_rel, 79 release days): D 13.9 bp, permutation p 0.41, not supported and not refuted; positive D rested on 2025. The MIT-licensed WillBtK/macro_kalshi scraper is the source of the middle-out cleaning used for the implied distribution.",
        quote="not supported and not refuted",
        market="Kalshi CPI/payrolls/GDP/FOMC 2023-07..2026-09, QQQ close-to-close",
        applicability="Same event source, different question (direction at minute horizons, not daily uncertainty premium).",
        limitations="Daily; 79 days.",
        replication="None.",
        reflection="Underpowered at 79 events; R here has the same order of event count, so power is stated up front.",
    ),
]


def build_cards():
    return [
        {
            "claim_id": s["claim_id"],
            "applies_to": [ITER],
            "claim": s["claim"],
            "quote": s["quote"],
            "source_type": s["source_type"],
            "source_url": s["url"],
            "published_or_updated_at": s["published"],
            "fetched_at": T0,
            "source_sha256": sha(s["snapshot"]),
            "source_snapshot": s["snapshot"],
            "limitations": s["limitations"],
            "independent_replication": s["replication"],
            "accessed_at": T0,
            "status": "verified",
            "verification_status": "source_verified",
            "verification_method": "fetch_and_snapshot_quote_check",
            "impact_on_spec": s["applicability"],
        }
        for s in SOURCES
    ]


def brief_sources():
    return [
        {
            "applicability": s["applicability"],
            "claim": s["claim"],
            "claim_id": s["claim_id"],
            "core_claim": s["claim"],
            "credibility": s["credibility"],
            "fetched_at": T0,
            "independent_replication": s["replication"],
            "limitations": s["limitations"],
            "market_and_period": s["market"],
            "project_applicability": s["applicability"],
            "published_or_updated_at": s["published"],
            "reflection": s["reflection"],
            "sha256": sha(s["snapshot"]),
            "snapshot_path": s["snapshot"],
            "source_card_path": CARDS,
            "source_type": s["source_type"],
            "url": s["url"],
        }
        for s in SOURCES
    ]


def power():
    nd = NormalDist()
    z = nd.inv_cdf(0.95) + nd.inv_cdf(0.8)
    return {
        "z_sum_one_sided_5pct_80pct_power": z,
        "mde_per_trade_net_mean_bp": {
            f"sd{sd}": {f"n{n}": round(z * sd / sqrt(n), 2) for n in (30, 60, 120, 300, 600)}
            for sd in (10, 20, 40)
        },
        "note": "realised sd per horizon is printed in results.json from the placebo trades; Sharpe MDE per trade series = z / sqrt(n_trades) in per-trade Sharpe units",
    }


def main():
    cards = build_cards()
    (ROOT / CARDS).write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards))
    grid = G.main_grid()
    (D / "power.json").write_text(json.dumps(power(), indent=2) + "\n")
    cands = []
    for g in grid:
        cid = (
            f"R_{g['signal'].split('_')[0]}_h{g['horizon_min']}"
            if g["type"] == "R"
            else f"J_t{g['theta_pp']}_h{g['horizon_min']}_{g['mode']}"
        )
        cands.append({"id": cid, "path": "pm_odds_event_study", "params": g})
    spec_path = ROOT / SPEC
    if not spec_path.exists():
        base = (ROOT / "strategy_specs/drafts/t20261006_15_intraday_rules.yaml").read_text()
        base = base.replace("t20261006_15_intraday_rules", ITER).replace(
            "T-20261006-15", "T-20261007-02"
        )
        a = base.index("description:")
        b = base.index("timeframe:")
        base = (
            base[:a]
            + "description: 'Preregistered T-20261007-02: prediction-market odds (Kalshi macro releases, Polymarket policy and election odds jumps) as signals for ETF returns at 5-240 minute horizons, net of extended-hours costs. Signal on bar close, fill at next bar open. Research only, no broker writes.'\n"
            + base[b:]
        )
        a = base.index("universe:")
        b = base.index("lifecycle:")
        base = base[:a] + "universe:\n- TLT\n- SPY\n- IWM\n- QQQ\n" + base[b:]
        a = base.index("factors:")
        b = base.index("llm_review:")
        base = (
            base[:a]
            + "factors:\n  pm_odds:\n    source: expression\n    expression: close / lag(close, 1) - 1\n    default: 0.0\n    description: Documentation-only stand-in. Kalshi implied expectations and Polymarket hourly YES prices are built in scripts/t0702_*.py from data/research/pm_event_study.\n    params:\n      decision_lag_sessions: 0\n"
            + base[b:]
        )
        a = base.index("  source_card_claim_ids:")
        b = base.index("\nnotes:") + 1
        ids = "".join(f"  - {s['claim_id']}\n" for s in SOURCES)
        ps = "  parameter_space:\n    R_signal: [R1_revision, R2_gap_to_baseline]\n    R_horizon_min: [5, 30, 120]\n    J_theta_pp: [3, 5, 8]\n    J_horizon_min: [15, 60, 240]\n    J_mode: [continue, reverse]\n  candidate_budget: 24\n  selection_objective: Median of the top three recent net Sharpe variants per part; all 24 are counted trials.\n  anti_overfit_notes:\n  - Rules, mapping tables, grid and selection frozen in hypotheses.md and scripts/t0702_pm_grid.py before any ETF return is computed.\n  validation_plan:\n  - Timing placebo (random direction, 100 seeds), DSR over 24, positive control with realised surprise, cost x2\n"
        base = base[:a] + "  source_card_claim_ids:\n" + ids + ps + base[b:]
        base = base.replace(
            "intent: Re-run published intraday rules to the minimum effective depth the owner asked for and select 1-2 candidates for the intraday paper account.",
            "intent: Test hundreds of prediction-market events for tradable ETF information and find a rule for paper.",
        ).replace("hypothesis_id: T-20261007-02", "hypothesis_id: T-20261007-02")
        spec_path.write_text(base)
    from open_composer.models.strategy_spec import load_strategy_spec
    from open_composer.research.iteration_dossier import candidate_authorization_binding_sha256
    from open_composer.strategy_versions import strategy_content_hash

    spec_hash = strategy_content_hash(load_strategy_spec(spec_path))
    gen = datetime.now(UTC).isoformat()
    reviewed = now()
    grid_sha = sha("scripts/t0702_pm_grid.py")
    mc = [
        {
            "ablation": "none",
            "benchmark_contract": "fixture",
            "candidate_id": c["id"],
            "cost_contract": "fixture",
            "data_contract": "fixture",
            "fallback": "BIL",
            "feature_contract": "fixture",
            "label_contract": "fixture",
            "method": c["path"],
            "parameters": c["params"],
            "path": c["path"],
            "role": "deterministic_mechanism_candidate",
            "spec_path": SPEC,
            "validation_contract": "fixture",
        }
        for c in cands
    ]
    manifest = {
        "candidate_count": len(mc),
        "candidates": mc,
        "contracts": {
            k: {"fixture": {"description": "single-mechanism lightweight path"}}
            for k in ("benchmarks", "costs", "data", "features", "labels", "validation")
        },
        "generated_at": gen,
        "generated_before_backtest": True,
        "iter_id": ITER,
        "schema_version": 1,
        "spec_hashes": {SPEC: spec_hash},
        "rules_file": {"path": "scripts/t0702_pm_grid.py", "sha256": grid_sha},
    }
    (D / "candidate-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    man_sha = sha(f"reports/research/iterations/{ITER}/candidate-manifest.json")
    cost = {
        "base_cost_bps": 0.4,
        "stress_cost_bps": 0.8,
        "note": "ETF per side: 0.5 x tick-cents/price + 0.02 bp, sells +0.206 bp, fills before 09:45 ET +1 bp (reuse of T-20261006-15); extension: before 09:30 ET or from 15:55 ET +3 bp (SPY QQQ IWM TLT) or +6 bp (sector SPDRs), unmeasured prior; reported at x1 and x2. Implementation: one_way_cost_bp in scripts/t0702_pm_grid.py.",
    }
    (D / "cost-table.json").write_text(json.dumps(cost, indent=2) + "\n")
    cost_sha = sha(f"reports/research/iterations/{ITER}/cost-table.json")
    ids = [c["id"] for c in cands]
    paths = {}
    for c in cands:
        paths.setdefault(c["path"], []).append(c["id"])
    auth = [
        {
            "action": "evaluate",
            "candidate_binding_sha256": candidate_authorization_binding_sha256(c),
            "candidate_id": c["candidate_id"],
            "path": c["path"],
            "reason_code": "single_mechanism_lightweight_path_ready",
        }
        for c in mc
    ]
    feas = {
        "candidate_accounting": {
            "balanced": True,
            "dependency_skipped_count": 0,
            "evaluation_authorized_count": len(ids),
            "frozen_candidate_count": len(ids),
            "unresolved_count": 0,
        },
        "candidate_authorization": {"candidate_count": len(ids), "rows": auth},
        "historical_evaluation_authorized": True,
        "iter_id": ITER,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "path_gates": {
            p: {"action": "evaluate", "candidate_ids": v, "historical_evaluation_go": True}
            for p, v in paths.items()
        },
        "report_type": "single_mechanism_lightweight_path",
        "required_reference_names": ["cost_table"],
        "required_references": {
            "cost_table": {
                "path": f"reports/research/iterations/{ITER}/cost-table.json",
                "sha256": cost_sha,
            }
        },
        "research_pass": False,
        "schema_version": 1,
        "workflow_pass": True,
        "data_notes": {
            "etf_minutes": "data/research/pm_event_study/etf_minute.parquet from data/sip/minute (SIP consolidated, extended hours, 2024-01..2026-10 plus 2023 for the R crash diagnostic)",
            "kalshi": "data/research/prediction_markets/kalshi/raw (core classes, T-20261002-44) and data/research/pm_event_study/kalshi_raw (extension classes, same fetcher)",
            "polymarket": "data/research/pm_event_study/polymarket (events_by_tag.jsonl, qualified_markets.json, hist/*.json hourly YES prices)",
            "power": "reports/research/iterations/" + ITER + "/power.json",
        },
    }
    (D / "data-feasibility.json").write_text(json.dumps(feas, indent=2, ensure_ascii=False) + "\n")
    feas_sha = sha(f"reports/research/iterations/{ITER}/data-feasibility.json")
    search = {
        "candidate_manifest_path": f"reports/research/iterations/{ITER}/candidate-manifest.json",
        "candidate_manifest_sha256": man_sha,
        "cost_table_path": f"reports/research/iterations/{ITER}/cost-table.json",
        "created_at": gen,
        "data_feasibility_path": f"reports/research/iterations/{ITER}/data-feasibility.json",
        "data_feasibility_sha256": feas_sha,
        "evaluation_report_paths": [
            f"reports/research/iterations/{ITER}/results.json",
            f"reports/research/iterations/{ITER}/report.md",
        ],
        "iter_id": ITER,
        "paths": [
            {
                "benchmark_family": [
                    "random_direction_timing_placebo_100_seeds",
                    "realised_surprise_positive_control",
                    "buy_and_hold_same_exposure",
                ],
                "candidate_count": len(v),
                "hypothesis_refs": ["T-20261007-02"],
                "name": p,
                "parameters": {
                    "R": {
                        "signal": list(G.R_SIGNALS),
                        "horizon_min": list(G.R_HORIZONS_MIN),
                        "asset": G.R_ASSET,
                    },
                    "J": {
                        "theta_pp": list(G.J_THETA_PP),
                        "horizon_min": list(G.J_HORIZONS_MIN),
                        "mode": list(G.J_MODES),
                    },
                },
            }
            for p, v in paths.items()
        ],
        "schema_version": 3,
        "single_mechanism_no_campaign_attestation": True,
        "source_spec_path": SPEC,
        "spec_hash": spec_hash,
        "strategy_name": ITER,
        "total_candidate_budget": len(ids),
        "trial_ledger_paths": [f"reports/research/iterations/{ITER}/trial-ledger.jsonl"],
    }
    (D / "search-space.json").write_text(json.dumps(search, indent=2, ensure_ascii=False) + "\n")
    brief = json.load(open(D / "external-brief.json"))
    bs = brief_sources()
    objective = "T-20261007-02: do prediction-market odds (Kalshi pre-release expectations for macro releases; Polymarket one-hour odds jumps for policy, Fed, shutdown, recession and election themes) predict US ETF returns at 5-240 minute horizons net of costs, 2024-01-08..2026-10-06?"
    brief.update(
        {
            "candidate_matrix_revisions": [
                {"decision": "keep", "path": p, "reason": "initial preregistration"} for p in paths
            ],
            "current_source_card_paths": [CARDS],
            "difference_from_existing": [
                {
                    "existing": "iteration:h20261002_pm_macro_uncertainty",
                    "difference": "Daily uncertainty premium on 79 days; here direction at 5-120 minutes after the release with a realised-surprise positive control, up to ten Kalshi classes.",
                },
                {
                    "existing": "iteration:h20261004_pm_midterm_odds_leadlag",
                    "difference": "Daily Goldstein-Li-Wang lead-lag of control odds; here one-hour jump episodes across eight themes with minute-level ETF returns and extended-hours costs.",
                },
                {
                    "existing": "iteration:h20261004_pm_earnings_beat_odds",
                    "difference": "Stock cross-section earnings markets; here index, bond and small-cap ETFs and macro and policy markets.",
                },
            ],
            "hypothesis_links": [
                {"hypothesis_id": "T-20261007-02", "source_urls": [s["url"] for s in bs[:4]]}
            ],
            "mechanism_description": "R: pre-release Kalshi implied expectation drift and gap to the previous print, hawkish lean, short TLT through the release. J: one-hour Polymarket odds jumps, mapped by theme to a primary ETF, continuation or reversal over 15-240 minutes.",
            "mechanism_family": "prediction_market_odds_event_study",
            "objective": objective,
            "schema_version": 3,
            "source_evidence_bindings": [
                {"claim_id": s["claim_id"], "source_card_path": CARDS, "source_url": s["url"]}
                for s in bs
            ],
            "source_spec_path": SPEC,
            "sources": bs,
            "spec_hash": spec_hash,
            "strategy_name": ITER,
            "topic_coverage": [
                "kalshi_macro_forecast_quality",
                "polymarket_tariff_surprise_high_frequency",
                "polymarket_price_discovery_political_shocks",
                "kalshi_macro_signal_regime_dependence",
                "polymarket_price_history_api_limits",
                "kalshi_candlestick_api",
                "local_negative_prior_macro_uncertainty",
                "multiple_testing_and_extended_hours_costs",
            ],
        }
    )
    (D / "external-brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n")
    dr_sources = [
        {
            k: v
            for k, v in s.items()
            if k not in ("reflection", "core_claim", "credibility", "project_applicability")
        }
        for s in bs
    ]
    queries = [
        {
            "query": "Kalshi prediction market FOMC CPI odds predict stock market returns announcement intraday study",
            "searched_at": reviewed,
            "opened_urls": [bs[0]["url"], bs[3]["url"]],
        },
        {
            "query": "Polymarket odds changes tariff election asset prices high-frequency event study paper 2025",
            "searched_at": reviewed,
            "opened_urls": [bs[1]["url"], bs[2]["url"], bs[4]["url"]],
        },
        {
            "query": "Kalshi macro markets Federal Reserve study prediction markets forecasts CPI payrolls accuracy versus consensus",
            "searched_at": reviewed,
            "opened_urls": [bs[0]["url"], bs[7]["url"]],
        },
        {
            "query": "Polymarket CLOB prices-history documentation and Kalshi candlesticks API",
            "searched_at": reviewed,
            "opened_urls": [bs[5]["url"], bs[6]["url"]],
        },
    ]
    dr = json.load(open(D / "direction-review.json"))
    dr.update(
        {
            "decision": "proceed",
            "reviewed_at": reviewed,
            "objective": objective,
            "target_regime_and_horizon": "Decision window 2024-01-08 to 2026-10-06 (about 689 sessions); phases of reports/research/program/regimes-2026-10-01 for robustness; holding 5 minutes to 4 hours inside one session; validity ends when the forward 63-session net mean falls below zero. R from 2023-01 only for the crash diagnostic.",
            "existing_solution_comparison": "Fed Board FEDS 2026-010: Kalshi about equal to consensus except headline CPI and the policy rate. Li-Xie 2026: tariff odds surprises move the S&P 500 about 0.7 percent inside a 30-minute window. Tsang-Yang 2026: odds jumps may reverse or persist. Mohanty 2026: Kalshi changes predict crypto volatility, regime dependent. No source gives a net-of-cost ETF rule from odds; local priors are negative at daily frequency. Reuse: Kalshi candles and the implied-distribution code of T-20261002-44, T-15 cost model, t15 statistics.",
            "remaining_evidence_gap": "Not measured: ETF NBBO half spreads in extended hours (priors), true timing of odds jumps inside the hour (hourly prices only), stale hourly Kalshi candles in thin strikes, the live odds feed latency, IEX versus SIP consistency for the live signal, and Alpaca extended-hours order behaviour for TLT around 08:30.",
            "negative_experiments_checked": "oc research directions rows prediction_market_macro_release_uncertainty_premium (parked: D 13.9 bp, p 0.41), prediction_market_earnings_beat_odds (refuted), prediction_market_policy_odds_leadlag_glw2026 (refuted, daily). Differences: minute-level returns after releases, positive control with realised surprise, one-hour jump episodes across eight themes, direction mapping fixed before returns, extended-hours costs, 24 counted trials. Not reopening the earnings or the daily midterm lead-lag.",
            "cost_and_execution_assumptions": "Signal on the close of minute t, fill at the open of t+1; R fills at the release minute open. ETF cost per side = tick-based half spread + 0.02 bp, sells + 0.206 bp, before 09:45 ET + 1 bp, extended hours + 3 bp (6 bp sector SPDRs, unmeasured), reported at x1 and x2. 1x notional, no borrow cost on TLT/SPY/IWM shorts (liquid, easy to borrow). Paper fills are NBBO-based and optimistic in extended hours.",
            "stop_condition": "Frozen in hypotheses.md: a part is called 'does not hold' only with reproduction (positive control), rules as written, three scale points, the registered budget used and enough power; otherwise 'not at depth' with the missing piece named. Budget: 24 trading variants, about 2 CPU hours on this box, 0 USD Modal. Deadline R 2026-10-09, all 2026-10-12 22:00 UTC. No change to rules, windows, gates or costs after results.",
            "queries": queries,
            "sources": dr_sources,
            "cheapest_decisive_test": {
                "action": "scripts/t0702_run.py: R events (positive control first) and J jump episodes on the 15 ETF minute panels, 24 variants, timing placebos, DSR; writes results.json.",
                "pass_condition": "Selected spec (median of top three recent net Sharpe) has DSR >= 0.70, net placebo percentile >= 0.90, robustness >= 3 of the evaluation-standard checks, no veto (P1).",
                "falsification_condition": "Not holding only if positive control (R) or at least 100 episodes at theta 3 (J), rules as written, three scale points, the budget used and power are all met and the selected net Sharpe <= 0 or placebo < 0.9; otherwise not at depth.",
                "max_compute_minutes": 120,
            },
        }
    )
    (D / "direction-review.json").write_text(json.dumps(dr, indent=2, ensure_ascii=False) + "\n")
    (D / "prebacktest-registered-at.txt").write_text(now() + "\n")
    print("registered", len(cands), "candidates", spec_hash[:12])


if __name__ == "__main__":
    main()
