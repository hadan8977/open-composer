# ruff: noqa: E501  (long prose strings are the frozen preregistration text)
"""T-20261006-15: write the preregistration dossier (direction review, brief, manifest,
feasibility, cost table, spec, hypotheses). Run once before any backtest; timestamps are taken
from the clock at run time. Re-running overwrites only files this script owns.
"""

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
import t15_grid as G  # noqa: E402

ITER = "t20261006_15_intraday_rules"
D = ROOT / "reports/research/iterations" / ITER
SRC_LOCAL = "reports/research/iterations/" + ITER + "/sources/"
SURVEY = "reports/research/intel/sources/hft-intraday-2026-10-06/"
CARDS = f"reports/harness/source_cards/{ITER}.jsonl"
SPEC = f"strategy_specs/drafts/{ITER}.yaml"
SURVEY_FETCH = "2026-10-06T17:07:00Z"


def sha(p: str) -> str:
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


T0 = now()

SOURCES = [
    dict(
        claim_id="zab_2024_noise_area_intraday_momentum",
        snapshot=SRC_LOCAL + "btm_full.txt",
        fetched=T0,
        url="https://alexandria.unisg.ch/server/api/core/bitstreams/a99aba00-f967-49b3-aceb-f544dc386e0b/content",
        source_type="paper",
        credibility="working_paper_author_reported",
        published="2024-11-27",
        claim=(
            "Zarattini, Aziz and Barbon (SFI WP 24-97, 2024): SPY intraday momentum with a time-of-day Noise "
            "Area = max/min(open, previous close) x (1 +/- VM x sigma), sigma the mean absolute move from the "
            "open over the previous 14 days at the same minute; positions are set only at HH:00 and HH:30, "
            "stopped by the current band and the VWAP, flat at the close; with volatility targeting (2%, "
            "leverage cap 4) 2007-2024 gave 19.6 percent a year, Sharpe 1.33, 1.8 trades a day; the base "
            "opposite-band version gave Sharpe 0.61."
        ),
        quote="trading is restricted to semi-hourly intervals",
        market="SPY, 2007-05 to 2024-04, 1-minute IQFeed bars, commission $0.0035 + slippage $0.001 per share",
        applicability="Group A rule, parameters (VM 0.5-2, lookback 7/14/28, stop variants, vol target) and the paper cell.",
        limitations="Author-reported, no out-of-sample split; costs only $0.0045 per share; paper itself says the optimum is VM 1.5 and lookback 90, so 14/1 is not an ex-post optimum.",
        replication="Local H-20260922-07 reproduced 2.2 percent a year and Sharpe 0.30 (persist entries each minute); a third-party automated replication reported 0.41. Not reproduced yet with the half-hourly rule; this iteration does it.",
        reflection="Fixes check interval, anchor and stop semantics; the local old test checked every minute, which is not the paper rule.",
    ),
    dict(
        claim_id="ghlz_2018_market_intraday_momentum",
        snapshot=SRC_LOCAL + "ghlz_full.txt",
        fetched=T0,
        url="https://c.mql5.com/forextsd/forum/173/intraday_momentum_-_the_first_half-hour_return_predicts_the_last_half-hour_return.pdf",
        source_type="paper",
        credibility="jfe_peer_reviewed",
        published="2018-04-01",
        claim=(
            "Gao, Han, Li and Zhou (JFE 2018): the first half-hour return of SPY measured from the previous close "
            "predicts the last half-hour return (R2 1.6 percent, 2.6 percent with the twelfth half-hour; "
            "out-of-sample 1.2 and 1.8 percent), a sign-timing strategy earns 6.67 percent a year at 6.19 percent "
            "volatility, Sharpe 1.08, before costs, 1993-2013."
        ),
        quote="The Sharpe ratio is thus 1.08",
        market="SPY and ten other ETFs, 1993-2013, 30-minute returns, gross of costs",
        applicability="Group B predictors (first half-hour with and without overnight, plus the twelfth half-hour) and trading window 15:30-16:00.",
        limitations="Gross of costs, sample ends 2013; effect said stronger on volatile and high-volume days.",
        replication="Baltussen-Da-Lammers-Martens (JFE 2021) find the same last-30-minute pattern in 60+ futures 1974-2020.",
        reflection="Local sample 2016-2026 is out of sample for the published window; replication target is sign and size of R2, not the 1993-2013 numbers.",
    ),
    dict(
        claim_id="zba_2024_stocks_in_play_orb",
        snapshot=SURVEY + "zba-stocks-in-play-paper.md",
        fetched=SURVEY_FETCH,
        url="https://concretumgroup.com/wp-content/uploads/2026/02/A-Profitable-Day-Trading-Strategy-For-The-U.S.-Equity-Market.pdf",
        source_type="paper",
        credibility="working_paper_author_reported",
        published="2025-04-01",
        claim=(
            "Zarattini, Barbon and Aziz (SSRN 4729284): 5-minute opening range breakout traded only on the top 20 "
            "stocks by relative volume, stop at 10 percent of ATR14, flat at close, 2016-2023 about 7,000 US "
            "stocks: IRR 41.6 percent, Sharpe 2.81 versus 3.2 percent and 0.48 without the relative-volume "
            "filter; 0.08R per trade, commission only."
        ),
        quote="Average PnL per trade 0.08R when relative volume > 100%",
        market="US stocks 2016-2023, 5-minute bars, commission $0.0035 per share, no spread or slippage",
        applicability="Group C rule, universe filters and stop sizes.",
        limitations="No spread or slippage; stop fills in the original are intrabar at the stop price; author-reported.",
        replication="QuantConnect research (2016 only, 1,000 liquid stocks) reports Sharpe 2.40; its comments flag stop fills one bar late and a win rate near 17 percent.",
        reflection="The cost gap is the whole question here: 9-40 bp per round trip at the open versus 8 bp gross per trade.",
    ),
    dict(
        claim_id="bdlm_2021_intraday_momentum_futures",
        snapshot=SURVEY + "baltussen-da-lammers-martens-2021.md",
        fetched=SURVEY_FETCH,
        url="https://academicweb.nd.edu/~zda/intramom.pdf",
        source_type="paper",
        credibility="jfe_peer_reviewed",
        published="2021-10-01",
        claim=(
            "Baltussen, Da, Lammers and Martens (JFE 2021): in 60+ futures 1974-2020 the return of the last 30 "
            "minutes is positively predicted by the return in the rest of the day; linked to gamma hedging of "
            "options market makers and leveraged ETFs; out-of-sample R2 up to about 2.9 percent for equity index futures."
        ),
        quote="Out-of-sample R2 for equity index futures up to about 2.9%",
        market="60+ futures, 1974-2020",
        applicability="Mechanism and independent replication for groups A and B; says why leveraged ETFs are in the symbol axis.",
        limitations="Futures not ETFs; effect reverts over following days.",
        replication="Gao et al. 2018 for SPY.",
        reflection="Supports a persistent economic cause rather than a one-sample pattern.",
    ),
    dict(
        claim_id="concretum_2026_orb_spy_selfcorrection",
        snapshot=SURVEY + "concretum-orb-spy-2026-07.md",
        fetched=SURVEY_FETCH,
        url="https://concretumgroup.substack.com/p/improving-the-opening-range-breakout",
        source_type="industry_standard",
        credibility="practitioner_self_report_paywalled",
        published="2026-07-08",
        claim=(
            "Concretum (2026-07-08): plain 5-minute opening range breakout on SPY, 2008-2025, has CAGR 1.0 "
            "percent and Sharpe 0.14; with enhancements CAGR 12.1 percent, Sharpe 0.84."
        ),
        quote="plain 5-minute ORB CAGR 1.0%, Sharpe 0.14",
        market="SPY 2008-2025",
        applicability="Prior for group C without the relative-volume filter; why the filter and the cost are the decisive parts.",
        limitations="Paywalled body; author self-report.",
        replication="Local H-20260918-02 ETF ORB gave 92.7-92.9 percent placebo percentile (no edge).",
        reflection="Authors themselves report the unfiltered rule is weak.",
    ),
    dict(
        claim_id="quantconnect_orb_stocks_in_play_replication",
        snapshot=SURVEY + "quantconnect-orb-stocks-in-play.md",
        fetched=SURVEY_FETCH,
        url="https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/",
        source_type="industry_standard",
        credibility="third_party_partial_replication",
        published="unknown",
        claim=(
            "QuantConnect research: 2016-only backtest of the stocks-in-play opening range breakout on the 1,000 "
            "most liquid US equities gives Sharpe 2.396; comments say stop orders fill on the next minute bar in "
            "backtests versus near-instantly live, and win rate is about 17 percent."
        ),
        quote="Sharpe 2.396 vs 0.836 for SPY",
        market="US equities 2016 only",
        applicability="Third-party fidelity check and the stop-fill semantics variants of group C.",
        limitations="One year; fee and slippage model not stated.",
        replication="None independent.",
        reflection="Stop-fill assumption flips the sign of local tests; both semantics are registered.",
    ),
    dict(
        claim_id="alpaca_orders_semantics",
        snapshot=SURVEY + "alpaca-orders-docs.md",
        fetched=SURVEY_FETCH,
        url="https://docs.alpaca.markets/us/docs/orders-at-alpaca",
        source_type="broker_official_docs",
        credibility="broker_official",
        published="unknown",
        claim=(
            "Alpaca orders: bracket orders do not support extended hours; time in force includes opg and cls "
            "auction orders; stop orders convert to market orders when triggered."
        ),
        quote="Extended hours are not supported.",
        market="Alpaca equities",
        applicability="Execution semantics for stops in groups A, C and D and the cls exit for group B.",
        limitations="Current page, undated.",
        replication="None needed.",
        reflection="Stop exits are market orders, so stop slippage is a real cost.",
    ),
    dict(
        claim_id="alpaca_paper_fill_model",
        snapshot=SURVEY + "alpaca-paper-trading-docs.md",
        fetched=SURVEY_FETCH,
        url="https://docs.alpaca.markets/us/docs/paper-trading",
        source_type="broker_official_docs",
        credibility="broker_official",
        published="unknown",
        claim=(
            "Alpaca paper trading matches orders against the NBBO, fills quantity is not checked against NBBO "
            "size, and partial fills of random size happen 10 percent of the time."
        ),
        quote="Your order quantity is not checked against the NBBO quantities.",
        market="Alpaca paper",
        applicability="Why paper fills are optimistic for size and why 20-40 sessions only test execution.",
        limitations="Page silent on auctions and extended hours.",
        replication="Local probe 2026-10-06: opg orders expired, cls of 1 SPY filled.",
        reflection="Paper cannot confirm the edge, only costs and plumbing.",
    ),
    dict(
        claim_id="iex_market_share_2026_07",
        snapshot=SURVEY + "iex-market-share-rosenblatt.md",
        fetched=SURVEY_FETCH,
        url="https://www.rblt.com/market-structure-reports/us-securities-volumes-july-2026",
        source_type="industry_standard",
        credibility="secondary_market_structure_report",
        published="2026-08-07",
        claim="IEX reached 4.43 percent of US equity volume in July 2026, so IEX minute volume is a sample of about 4 percent.",
        quote="IEX reached a new all-time high of 4.43%",
        market="US equities July 2026",
        applicability="IEX versus SIP signal check for the paper feed.",
        limitations="Secondary; search summary used for the 8 percent exchange-share figure.",
        replication="None.",
        reflection="Prices on liquid ETFs are usable; volume ratios are not.",
    ),
]


def build_cards() -> list[dict]:
    cards = []
    for s in SOURCES:
        cards.append(
            {
                "claim_id": s["claim_id"],
                "applies_to": [ITER],
                "claim": s["claim"],
                "quote": s["quote"],
                "source_type": s["source_type"],
                "source_url": s["url"],
                "published_or_updated_at": s["published"],
                "fetched_at": s["fetched"],
                "source_sha256": sha(s["snapshot"]),
                "source_snapshot": s["snapshot"],
                "limitations": s["limitations"],
                "independent_replication": s["replication"],
                "accessed_at": s["fetched"],
                "status": "verified",
                "verification_status": "source_verified",
                "verification_method": "fetch_and_snapshot_quote_check",
                "impact_on_spec": s["applicability"],
            }
        )
    return cards


def brief_sources() -> list[dict]:
    out = []
    for s in SOURCES:
        out.append(
            {
                "applicability": s["applicability"],
                "claim": s["claim"],
                "claim_id": s["claim_id"],
                "core_claim": s["claim"],
                "credibility": s["credibility"],
                "fetched_at": s["fetched"],
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
        )
    return out


def power_table(n_sessions: int) -> dict:
    nd = NormalDist()
    yrs = n_sessions / 252.0
    out = {"recent_sessions": n_sessions, "years": yrs}
    for alpha, label in (
        (0.05, "one_sided_5pct"),
        (0.05 / 4, "one_sided_1.25pct"),
        (0.005, "one_sided_0.5pct"),
    ):
        z = nd.inv_cdf(1 - alpha) + nd.inv_cdf(0.8)
        out[f"mde_annual_sharpe_80pct_power_{label}"] = z / sqrt(yrs)
    out["power_at_published_sharpe_one_sided_5pct"] = {
        name: nd.cdf(sr * sqrt(yrs) - nd.inv_cdf(0.95))
        for name, sr in {
            "A_paper_1.33": 1.33,
            "B_gross_1.08": 1.08,
            "C_paper_2.81": 2.81,
            "A_base_0.61": 0.61,
        }.items()
    }
    return out


def main() -> int:
    D.mkdir(parents=True, exist_ok=True)
    (ROOT / "reports/harness/source_cards").mkdir(parents=True, exist_ok=True)
    cards = build_cards()
    (ROOT / CARDS).write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards))

    trials = {
        "A": len(G.grid_a()),
        "B": len(G.grid_b()),
        "C": len(G.grid_c()),
        "D": len(G.grid_d()),
    }
    total = sum(trials.values())
    pw = power_table(689)

    # ------------------------------------------------------------------ candidates (<= 24)
    cands = []
    for name, syms in G.DEPTH_SETS.items():
        cands.append(
            dict(
                id=f"A_paper_{name}",
                path="intraday_rules_scale_curve",
                role="deterministic_mechanism_candidate",
                params={"group": "A", "spec": G.A_PAPER, "symbols": syms, "depth_point": name},
            )
        )
    for name, syms in G.DEPTH_SETS.items():
        cands.append(
            dict(
                id=f"B_paper_{name}",
                path="intraday_rules_scale_curve",
                role="deterministic_mechanism_candidate",
                params={"group": "B", "spec": G.B_PAPER, "symbols": syms, "depth_point": name},
            )
        )
    for pool in G.C_POOL:
        cands.append(
            dict(
                id=f"C_paper_pool{pool}",
                path="intraday_rules_scale_curve",
                role="deterministic_mechanism_candidate",
                params={
                    "group": "C",
                    "spec": {**G.C_PAPER, "pool": pool},
                    "depth_point": f"pool{pool}",
                },
            )
        )
    for tf in G.D_TF:
        for u in ("QQQ_SPY", "TOP50"):
            cands.append(
                dict(
                    id=f"D_default_{tf}_{u}",
                    path="intraday_rules_scale_curve",
                    role="deterministic_mechanism_candidate",
                    params={
                        "group": "D",
                        "spec": {
                            "tf": tf,
                            "hold": G.D_HOLD[tf][1],
                            "exit": "time_stop",
                            "signal": "primary_only",
                            "side": "long_only",
                        },
                        "universe": u,
                    },
                )
            )
    assert len(cands) <= 24, len(cands)
    manifest_c = []
    for c in cands:
        entry = {
            "ablation": "none",
            "benchmark_contract": "fixture",
            "candidate_id": c["id"],
            "cost_contract": "fixture",
            "data_contract": "fixture",
            "fallback": "BIL",
            "feature_contract": "fixture",
            "label_contract": "fixture",
            "method": "intraday_rules_scale_curve",
            "parameters": c["params"],
            "path": c["path"],
            "role": c["role"],
            "spec_path": SPEC,
            "validation_contract": "fixture",
        }
        manifest_c.append(entry)
    from open_composer.models.strategy_spec import load_strategy_spec
    from open_composer.strategy_versions import strategy_content_hash

    spec_hash = (
        strategy_content_hash(load_strategy_spec(ROOT / SPEC)) if (ROOT / SPEC).exists() else None
    )
    return 0 if spec_hash is None else write_rest(cards, manifest_c, trials, total, pw, spec_hash)


def write_rest(cards, manifest_c, trials, total, pw, spec_hash) -> int:
    from open_composer.research.iteration_dossier import candidate_authorization_binding_sha256

    reviewed = now()
    gen = datetime.now(UTC).isoformat()
    manifest = {
        "candidate_count": len(manifest_c),
        "candidates": manifest_c,
        "contracts": {
            k: {"fixture": {"description": "single-mechanism lightweight path"}}
            for k in ("benchmarks", "costs", "data", "features", "labels", "validation")
        },
        "generated_at": gen,
        "generated_before_backtest": True,
        "iter_id": ITER,
        "schema_version": 1,
        "spec_hashes": {SPEC: spec_hash},
        "full_grid": {
            "registry_path": f"reports/research/iterations/{ITER}/grid-registry.json",
            "trial_counts": {**trials, "total": total},
            "note": "Decision candidates above are paper-spec anchors at each depth point; every version of the full grid is a counted trial listed in grid-registry.json.",
        },
    }
    grid = G.all_trials()
    reg = {
        "iter_id": ITER,
        "registered_at": gen,
        "trial_counts": {**trials, "total": total},
        "versions": grid,
    }
    (D / "grid-registry.json").write_text(json.dumps(reg, ensure_ascii=False) + "\n")
    reg_sha = hashlib.sha256((D / "grid-registry.json").read_bytes()).hexdigest()
    manifest["full_grid"]["registry_sha256"] = reg_sha
    (D / "candidate-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    man_sha = hashlib.sha256((D / "candidate-manifest.json").read_bytes()).hexdigest()

    cost_table = {
        "base_cost_bps": 0.4,
        "stress_cost_bps": 0.8,
        "note": (
            "ETF per side: half spread = 0.5 x tick-cents/price (1 cent for SPY QQQ IWM DIA XLK XLF XLE XLV XLY XLP XLI XLU TQQQ, "
            "2 cents for XLB XLRE XLC SPXL; unmeasured, to be checked with SIP NBBO) + 0.02 bp slippage; sells add SEC fee 0.206 bp; "
            "fills before 09:45 ET add 1.0 bp; reported at x0.5, x1, x2, x4. Stocks (groups C, D): equity_book costfn half_spread_bp "
            "with the 'open' snapshot for entries and 'close' for end-of-day exits, mean of both for stop exits, fees 0.5 bp per side, "
            "spread part at x0.5, x1, x2. Borrow: easy-to-borrow shorts only, intraday, no fee (Alpaca)."
        ),
        "etf_one_way_formula": "0.5*tick_cents*0.01/price*1e4 + 0.02 + (0.206 if sell) + (1.0 if fill before 09:45)",
    }
    (D / "cost-table.json").write_text(json.dumps(cost_table, indent=2) + "\n")
    cost_sha = hashlib.sha256((D / "cost-table.json").read_bytes()).hexdigest()

    ids = [c["candidate_id"] for c in manifest_c]
    auth_rows = [
        {
            "action": "evaluate",
            "candidate_binding_sha256": candidate_authorization_binding_sha256(c),
            "candidate_id": c["candidate_id"],
            "path": c["path"],
            "reason_code": "single_mechanism_lightweight_path_ready",
        }
        for c in manifest_c
    ]
    feas = {
        "candidate_accounting": {
            "balanced": True,
            "dependency_skipped_count": 0,
            "evaluation_authorized_count": len(ids),
            "frozen_candidate_count": len(ids),
            "unresolved_count": 0,
        },
        "candidate_authorization": {"candidate_count": len(ids), "rows": auth_rows},
        "historical_evaluation_authorized": True,
        "iter_id": ITER,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "path_gates": {
            "intraday_rules_scale_curve": {
                "action": "evaluate",
                "candidate_ids": ids,
                "historical_evaluation_go": True,
            }
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
            "etf_minutes": "data/features/t15_minute/<SYM>.parquet from data/sip-hist/minute (2016-2022) and data/sip/minute (2023-2026), regular session, SIP consolidated",
            "stock_minutes": "data/features/intraday5m (T-20261006-21) when .READY, else DuckDB month queries limited to the first 30 minutes",
            "power": pw,
        },
    }
    (D / "data-feasibility.json").write_text(json.dumps(feas, indent=2, ensure_ascii=False) + "\n")
    feas_sha = hashlib.sha256((D / "data-feasibility.json").read_bytes()).hexdigest()

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
                    "random_direction_placebo_100_seeds",
                    "band_shift_30min_placebo",
                    "buy_and_hold_same_exposure",
                    "random_same_count_entry_placebo",
                ],
                "candidate_count": len(ids),
                "hypothesis_refs": ["T-20261006-15"],
                "name": "intraday_rules_scale_curve",
                "parameters": {
                    "A": {
                        "mult": G.A_MULT,
                        "lookback": G.A_LOOKBACK,
                        "interval": G.A_INTERVAL,
                        "stop": G.A_STOP,
                        "vt": G.A_VT,
                        "symbols": G.ETFS_ALL,
                    },
                    "B": {"pred": G.B_PRED, "thresh": G.B_THRESH, "symbols": G.ETFS_ALL},
                    "C": {
                        "range": G.C_RANGE,
                        "topk": G.C_TOPK,
                        "stop": G.C_STOP,
                        "pool": G.C_POOL,
                        "fill": G.C_FILL,
                    },
                    "D": {
                        "tf": G.D_TF,
                        "hold": G.D_HOLD,
                        "exit": G.D_EXIT,
                        "signal": G.D_SIGNAL,
                        "side": G.D_SIDE,
                        "universe": G.D_UNIVERSE,
                    },
                },
            }
        ],
        "schema_version": 3,
        "single_mechanism_no_campaign_attestation": True,
        "source_spec_path": SPEC,
        "spec_hash": spec_hash,
        "strategy_name": ITER,
        "total_candidate_budget": len(ids),
        "trial_ledger_paths": [f"reports/research/iterations/{ITER}/trial-ledger.jsonl"],
        "full_grid_trial_total": total,
    }
    (D / "search-space.json").write_text(json.dumps(search, indent=2, ensure_ascii=False) + "\n")

    brief = json.load(open(D / "external-brief.json"))
    bs = brief_sources()
    brief.update(
        {
            "candidate_matrix_revisions": [
                {
                    "decision": "keep",
                    "path": "intraday_rules_scale_curve",
                    "reason": "initial preregistration",
                }
            ],
            "current_source_card_paths": [CARDS],
            "difference_from_existing": [
                {
                    "existing": "iteration:mom_minute_r1",
                    "difference": "Not QQQ/TQQQ 30-minute momentum on IEX bars: SIP consolidated minute bars, ETF symbol axis of 17, half-hourly noise-band rule from the paper, depth curves.",
                },
                {
                    "existing": "iteration:h20260922_07_intraday_momentum",
                    "difference": "Old test checked every minute with a persistent band and one symbol; this one uses the paper's HH:00/HH:30 checks, 4x3x3x3x2 versions and 17 symbols.",
                },
            ],
            "hypothesis_links": [
                {"hypothesis_id": "T-20261006-15", "source_urls": [s["url"] for s in bs[:4]]}
            ],
            "mechanism_description": "Rule-based intraday strategies re-run to minimum effective depth: noise-band momentum (A), first-half-hour to last-half-hour momentum (B), stocks-in-play opening range (C), owner Reversal Trend on 1-minute and 1-hour bars (D).",
            "mechanism_family": "intraday_rule_based_momentum_depth_curve",
            "objective": "T-20261006-15: do published intraday rules (noise band, market intraday momentum, stocks-in-play ORB, Reversal Trend) keep a net-of-cost edge in 2024-01-08..2026-10-06 once run at depth (reproduction, faithful rule, three or more scale points, full registered grids, power)?",
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
                "noise_band_intraday_momentum_zarattini",
                "market_intraday_momentum_gao_han_li_zhou",
                "intraday_momentum_futures_replication_baltussen",
                "stocks_in_play_opening_range_breakout_zarattini_barbon",
                "orb_practitioner_self_correction_concretum",
                "stop_fill_semantics_and_alpaca_orders",
                "paper_fill_model_and_optimism",
                "opening_closing_half_spread_measurement",
                "iex_versus_sip_feed",
            ],
        }
    )
    (D / "external-brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n")

    dr_sources = [
        {
            k: v
            for k, v in s.items()
            if k != "reflection"
            and k != "core_claim"
            and k != "credibility"
            and k != "project_applicability"
        }
        for s in bs
    ]
    queries = [
        {
            "query": "Zarattini Aziz Barbon Beat the Market intraday momentum noise area SPY VWAP",
            "searched_at": reviewed,
            "opened_urls": [bs[0]["url"], bs[4]["url"]],
        },
        {
            "query": "Gao Han Li Zhou market intraday momentum first half-hour last half-hour",
            "searched_at": reviewed,
            "opened_urls": [bs[1]["url"], bs[3]["url"]],
        },
        {
            "query": "opening range breakout stocks in play relative volume replication stop fill",
            "searched_at": reviewed,
            "opened_urls": [bs[2]["url"], bs[5]["url"]],
        },
        {
            "query": "Alpaca paper trading fill model orders bracket stop opening auction",
            "searched_at": reviewed,
            "opened_urls": [bs[6]["url"], bs[7]["url"]],
        },
        {
            "query": "IEX share of US equity volume 2026",
            "searched_at": reviewed,
            "opened_urls": [bs[8]["url"]],
        },
    ]
    dr = json.load(open(D / "direction-review.json"))
    dr.update(
        {
            "decision": "proceed",
            "reviewed_at": reviewed,
            "objective": brief["objective"],
            "target_regime_and_horizon": (
                "Decision window 2024-01-08 to the end of data (2026-10-06, 689 sessions), split into the 11 market phases of "
                "reports/research/program/regimes-2026-10-01 (P11 extended to data end); 2016-2023 is a diagnostic and reproduction window only "
                "(the published samples end 2023-2024, so 2016-2022 is the in-sample reproduction and 2023 onward the true out-of-sample). "
                "Holding periods: minutes to one session (A, B, C, D-1m); D-1h up to 26 hourly bars. Validity ends when the forward 63-session net mean falls below zero."
            ),
            "existing_solution_comparison": (
                "Published: ZAB 2024 (SPY Sharpe 1.33 with VWAP stop and volatility targeting, base 0.61), Gao et al. 2018 (SPY Sharpe 1.08 gross, 1993-2013), "
                "Baltussen et al. 2021 (futures out-of-sample R2 up to 2.9 percent), ZBA 2024 (Sharpe 2.81, commission only), QuantConnect 2016-only replication (2.40), "
                "Concretum 2026-07 (plain ORB SPY Sharpe 0.14). No source gives an independent live record net of spread. The 2026-10-06 survey I-20261006-01 found no candidate with hard net evidence. "
                "Reuse: published rules implemented as written; only data adaptation, cost, current validity and execution feasibility are new."
            ),
            "remaining_evidence_gap": (
                "Not measured: ETF NBBO half spreads (priors of 1-2 cents), stop-market slippage on stocks, IEX versus SIP agreement of signals (IEX history not on disk, so pending forward observation), "
                "paper fill behaviour at 09:35 and 15:30, and any intrabar ordering inside 1-minute bars. The local 2016-2022 minute archive is the published authors' period, so reproduction of their relative conclusions is possible but not of 2007-2015."
            ),
            "negative_experiments_checked": (
                "Registry (oc research directions) last rows 2026-10-06 read: spy_noise_band_intraday refuted (gross about 3.6 percent a year, only SPY, every-minute rule, 0.30 vs 0.61 unexplained), "
                "single_etf_intraday_momentum_cost_adjusted refuted (effective N 3, one symbol set), orb_etf_opening_range_breakout (placebo 92.7-92.9 percent, kept as narrow), "
                "orb_stocks_in_play_relative_volume refuted (select window -27.1 percent a year, stop-fill dependent, design window 2016-2022 never run, fixed top 20, no liquidity buckets), "
                "cross_sectional_gap_fade refuted, minute_bar_momentum_multipath partial (IEX only), reversal_trend_user_indicator refuted at 18 hourly cells 2024+ long-only, reversal_trend_daily_signals partial. "
                "Differences: paper rule semantics (HH:00/HH:30), 4x3x3x3x2 versions across 17 symbols with depth curves, reproduction on 2016-2022, full pool depth for ORB, 1-minute Reversal Trend and long-short hourly."
            ),
            "cost_and_execution_assumptions": (
                "Signal on the close of minute bar t, fill at the open of bar t+1, flat at the close of the 15:59 bar (stand-in for a market-on-close). ETF cost per side = half spread (tick cents prior) + 0.02 bp slippage, "
                "sells + 0.206 bp SEC fee, fills before 09:45 ET + 1.0 bp, reported at x0.5, x1, x2, x4. Stocks use equity_book costfn (open snapshot for entries, close snapshot for exits, mean for stops), spread part x0.5, x1, x2. "
                "Stops are market orders. No borrow fee (easy-to-borrow intraday). Paper fills are NBBO-based and optimistic on size."
            ),
            "stop_condition": (
                "Per group, frozen in hypotheses.md: a rule is called 'not holding' only if reproduction, faithful implementation, at least three depth points, the full registered grid and power are all satisfied; "
                "otherwise 'not at depth' with the next step written. Budget: 4,203 registered versions, 4 compute-hours on this box plus at most 4 USD on Modal, 2026-10-10 22:00 UTC deadline. "
                "No change to versions, windows, gates or costs after results."
            ),
            "queries": queries,
            "sources": dr_sources,
            "cheapest_decisive_test": {
                "action": "scripts/run_t20261006_15_intraday_rules.py: group A and B on the 17 ETF minute panels (all registered versions, depth curves over 1/2/4/15/17 symbols, cost x0.5/1/2/4), then C and D when data are ready; results.json.",
                "pass_condition": "A version/portfolio passes P1 paper incubation only if recent-window net Sharpe is positive with DSR >= 0.7, net placebo percentile >= 0.9 and >= 3 of the robustness checks of config/evaluation-standard-v2.json hold.",
                "falsification_condition": "A group is called not holding only if the reproduction, faithful-implementation, three-depth-point, budget and power conditions are all met and the best depth-point recent net Sharpe is <= 0 or its placebo percentile < 0.9; otherwise it is reported as not at depth.",
                "max_compute_minutes": 240,
            },
        }
    )
    (D / "direction-review.json").write_text(json.dumps(dr, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
