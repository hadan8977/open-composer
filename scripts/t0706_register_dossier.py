# ruff: noqa: E501  (long prose strings are the frozen preregistration text)
"""T-20261007-06: write the preregistration dossier (cards, spec, manifest, feasibility, cost table,
search space, direction review, brief JSON). Run once before any backtest; timestamps come from the
clock at run time. Needs data/research/t0706_quotes/cost_table_raw.json (from t0706_cost_table.py)."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from math import sqrt
from pathlib import Path
from statistics import NormalDist

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import t0706_grid as G  # noqa: E402

ITER = "t20261007_06_intraday_batch2"
D = ROOT / "reports/research/iterations" / ITER
NEW = "reports/research/intel/sources/intraday-batch2-2026-10-07/"
SURVEY = "reports/research/intel/sources/hft-intraday-2026-10-06/"
T15SRC = "reports/research/iterations/t20261006_15_intraday_rules/sources/"
CARDS = f"reports/harness/source_cards/{ITER}.jsonl"
SPEC = f"strategy_specs/drafts/{ITER}.yaml"
SURVEY_FETCH = "2026-10-06T17:07:00Z"
T15_SPEC = ROOT / "strategy_specs/drafts/t20261006_15_intraday_rules.yaml"


def sha(p: str) -> str:
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


T0 = now()


def snap_fetch(path: str) -> str:
    """Fetched-at stamp stored in the snapshot header."""
    for line in (ROOT / path).read_text().splitlines():
        if line.startswith("- fetched_at:"):
            return line.split(":", 1)[1].strip().split(" ")[0].replace("Z", "") + (
                "Z" if "T" in line else ""
            )
    return T0


SOURCES = [
    dict(
        claim_id="bds_2025_end_of_day_reversal",
        snapshot=NEW + "baltussen-da-soebhag-eod-notes.md",
        url="https://academicweb.nd.edu/~zda/EOD.pdf",
        source_type="paper",
        credibility="working_paper_2025_quantpedia_award",
        published="2025-04-01",
        claim=(
            "Baltussen, Da and Soebhag (2025): in US stocks 1993-2019 the return from the previous close to 15:00 predicts a reversal in 15:30-16:00; "
            "long-short 3.78 bp a day value-weighted and 6.86 bp equal-weighted gross, 14.71 bp for the smallest 20 percent and 3.41 bp for the largest 20 percent; "
            "the authors say the strategy might not be exploitable by many investors after transaction costs."
        ),
        quote="might not be exploitable by many investors after accounting for transaction costs",
        market="US stocks 1993-2019 (TAQ/CRSP), 30-minute windows",
        applicability="Group G2 signal, window and the paper-faithful variant (pc_to_1500); source of the cost caveat.",
        limitations="Gross numbers, value-weighted by lagged market cap, no ETFs, working paper; no independent replication found.",
        replication="None found 2026-10-07.",
        reflection="Our 2024-2026 liquid-stock and ETF test is a true out-of-sample extension; the paper itself warns costs may remove the edge.",
    ),
    dict(
        claim_id="bdlm_2021_intraday_momentum_futures",
        snapshot=SURVEY + "baltussen-da-lammers-martens-2021.md",
        url="https://academicweb.nd.edu/~zda/intramom.pdf",
        source_type="paper",
        credibility="jfe_peer_reviewed",
        published="2021-10-01",
        claim=(
            "Baltussen, Da, Lammers and Martens (JFE 2021): in 60+ futures 1974-2020 the last 30 minutes' return is positively predicted by the rest-of-day return; "
            "linked to gamma hedging of options market makers and leveraged ETFs; out-of-sample R2 up to about 2.9 percent for equity index futures."
        ),
        quote="Out-of-sample R2 for equity index futures up to about 2.9%",
        market="60+ futures, 1974-2020",
        applicability="Mechanism behind group G1: hedging demand from options and leveraged ETFs, strongest where both are active.",
        limitations="Futures not single stocks; effect reverts over following days.",
        replication="Gao et al. 2018 for SPY; local T-15 B group did not reproduce the size out of sample.",
        reflection="Supports an economic cause for the QQQ noise band but the local evidence is QQQ-only.",
    ),
    dict(
        claim_id="concretum_gap_fill_2024",
        snapshot=NEW + "concretum-gap-fill-intraday-momentum.md",
        url="https://concretumgroup.com/backtesting-7-years-of-free-data-beat-the-market-an-effective-intraday-momentum-strategy-for-the-sp500-etf-spy/",
        source_type="industry_standard",
        credibility="practitioner_author_reported",
        published="2024-06-05",
        claim=(
            "Concretum Research: SPY overnight-gap-reversal signal combined with noise-area intraday momentum, 2018-01-01 to 2024-06-05, Sharpe 1.95, "
            "31.3 percent a year, max drawdown 10.0 percent, commission only; the gap leg alone is not reported."
        ),
        quote="an overnight gap reversal signaling strategy",
        market="SPY 2018-2024, Alpaca 1-minute bars, commission $0.0035/share",
        applicability="Group G3: ETF gap leg alone and combined with the QQQ noise band.",
        limitations="Combination only, no spread or slippage, 2 percent overnight threshold is rare; no third-party replication found.",
        replication="None found 2026-10-07.",
        reflection="The headline mixes two legs; the test separates them.",
    ),
    dict(
        claim_id="direxion_single_stock_launch_2022",
        snapshot=NEW + "direxion-single-stock-launch-2022.md",
        url="https://www.prnewswire.com/news-releases/direxion-launches-first-amazon-google-and-microsoft-single-stock-leveraged-and-inverse-etfs-301619324.html",
        source_type="industry_standard",
        credibility="issuer_press_release",
        published="2022-09-07",
        claim=(
            "Direxion launched AMZU, GGLL and MSFU (1.5X single-stock bull ETFs) on 2022-09-07, after TSLL and AAPU; "
            "so TSLA, AAPL, AMZN, GOOGL and MSFT had single-stock leveraged ETFs well before the 2024-01-08 window start (NVDA from 2023-09 per search summaries)."
        ),
        quote="Amazon, Google and Microsoft are three of the world's largest stocks, are heavily traded, and are widely recognized.",
        market="US single-stock leveraged ETFs, 2022-2023",
        applicability="Point-in-time definition of the G1 pool LETF6.",
        limitations="NVDU/T-REX dates come from search summaries; issuer product pages returned 403; AUM not obtained.",
        replication="None needed.",
        reflection="Defines the pool before looking at results.",
    ),
    dict(
        claim_id="zab_2024_noise_area_intraday_momentum",
        snapshot=T15SRC + "btm_full.txt",
        url="https://alexandria.unisg.ch/server/api/core/bitstreams/a99aba00-f967-49b3-aceb-f544dc386e0b/content",
        source_type="paper",
        credibility="working_paper_author_reported",
        published="2024-11-27",
        claim=(
            "Zarattini, Aziz and Barbon (SFI WP 24-97, 2024): SPY noise-area intraday momentum, band = max/min(open, previous close) x (1 +/- VM x sigma), sigma the mean absolute "
            "move from the open over 14 days at the same minute, positions set at semi-hourly checks, stopped by band and VWAP, flat at the close; Sharpe 1.33 with volatility targeting 2007-2024."
        ),
        quote="trading is restricted to semi-hourly intervals",
        market="SPY, 2007-05 to 2024-04",
        applicability="Rule for G1 (and the QQQ leg of the G3 combination).",
        limitations="Author-reported, no out-of-sample split, SPY only.",
        replication="T-20261006-15 reproduced the relative conclusions on SPY 2016-2024-04 (0.76/1.11 vs 1.24/1.33) and found the recent edge in QQQ only.",
        reflection="G1 asks whether the QQQ result generalises to stocks with the same hedging flows.",
    ),
    dict(
        claim_id="ghlz_2018_market_intraday_momentum",
        snapshot=T15SRC + "ghlz_full.txt",
        url="https://c.mql5.com/forextsd/forum/173/intraday_momentum_-_the_first_half-hour_return_predicts_the_last_half-hour_return.pdf",
        source_type="paper",
        credibility="jfe_peer_reviewed",
        published="2018-01-01",
        claim="Gao, Han, Li and Zhou (JFE 2018): the first half-hour return on the market predicts the last half-hour return (SPY 1993-2013); local T-15 found the published size absent after 2016.",
        quote="the first half-hour return on the market predicts the",
        market="SPY 1993-2013",
        applicability="Background for the last-hour structure that G2 and the hedging-demand mechanism of G1 share; local replication already negative.",
        limitations="Index level, 1993-2013; local T-20261006-15 group B did not reproduce the size out of sample.",
        replication="T-20261006-15 (negative after 2016).",
        reflection="Why G1 uses the noise-band rule, not the first-half-hour predictor.",
    ),
    dict(
        claim_id="heston_korajczyk_sadka_2010_intraday_periodicity",
        snapshot=SURVEY + "heston-korajczyk-sadka-2010.md",
        url="https://ar5iv.arxiv.org/html/1005.3535",
        source_type="paper",
        credibility="jf_peer_reviewed",
        published="2010-01-01",
        claim="Heston, Korajczyk and Sadka (JF 2010): return continuation at half-hour intervals that are multiples of a trading day; the authors say exploiting it loses money after the bid-ask spread.",
        quote="lose money, after paying the bid-ask spread",
        market="US stocks 2001-2005",
        applicability="Why G2 uses a 30-minute gap between signal and trade in the paper-faithful variant and why spreads decide the result.",
        limitations="2001-2005; different mechanism (continuation).",
        replication="Local T-13 on a different pool negative after costs.",
        reflection="Cost realism: spreads, not gross patterns, decide.",
    ),
    dict(
        claim_id="alpaca_orders_semantics",
        snapshot=SURVEY + "alpaca-orders-docs.md",
        url="https://docs.alpaca.markets/us/docs/orders-at-alpaca",
        source_type="broker_official_docs",
        credibility="broker_official",
        published="unknown",
        claim="Alpaca orders: time in force includes opg and cls auction orders; bracket orders do not support extended hours; stop orders convert to market orders when triggered.",
        quote="Extended hours are not supported.",
        market="Alpaca equities",
        applicability="Execution semantics for the 15:30-15:55 market exit of G2 and the plugin interface.",
        limitations="Current page, undated.",
        replication="None needed.",
        reflection="Closing-auction fills only as a diagnostic.",
    ),
    dict(
        claim_id="iex_market_share_2026_07",
        snapshot=SURVEY + "iex-market-share-rosenblatt.md",
        url="https://www.rblt.com/market-structure-reports/us-securities-volumes-july-2026",
        source_type="industry_standard",
        credibility="secondary_market_structure_report",
        published="2026-08-07",
        claim="IEX reached 4.43 percent of US equity volume in July 2026, so IEX minute volume is a sample of about 4 percent of consolidated volume.",
        quote="IEX reached a new all-time high of 4.43%",
        market="US equities July 2026",
        applicability="Why the IEX-versus-SIP consistency check is required before any paper run.",
        limitations="Secondary source.",
        replication="None.",
        reflection="Prices on liquid names usable; volume ratios are not.",
    ),
    dict(
        claim_id="alpaca_paper_fill_model",
        snapshot=SURVEY + "alpaca-paper-trading-docs.md",
        url="https://docs.alpaca.markets/us/docs/paper-trading",
        source_type="broker_official_docs",
        credibility="broker_official",
        published="unknown",
        claim="Alpaca paper trading matches orders against the NBBO, quantity is not checked against NBBO size, partial fills of random size happen 10 percent of the time.",
        quote="Your order quantity is not checked against the NBBO quantities.",
        market="Alpaca paper",
        applicability="Paper fills are optimistic; the paper stage tests plumbing and costs, not the edge.",
        limitations="Page silent on auctions and extended hours.",
        replication="Local probe 2026-10-06: opg orders expired.",
        reflection="Closing-auction fills are a diagnostic only.",
    ),
]
for s in SOURCES:
    s["fetched"] = snap_fetch(s["snapshot"]) or T0
    text = (ROOT / s["snapshot"]).read_text(errors="ignore")
    assert s["quote"] in text, (s["claim_id"], s["quote"])


def build_cards() -> list[dict]:
    return [
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
        for s in SOURCES
    ]


def brief_sources() -> list[dict]:
    return [
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
        for s in SOURCES
    ]


def power_table(n_sessions: int) -> dict:
    nd = NormalDist()
    yrs = n_sessions / 252.0
    out = {"recent_sessions": n_sessions, "years": yrs}
    for alpha, label in (
        (0.05, "one_sided_5pct"),
        (0.05 / 3, "one_sided_1.67pct_3groups"),
        (0.005, "one_sided_0.5pct"),
    ):
        z = nd.inv_cdf(1 - alpha) + nd.inv_cdf(0.8)
        out[f"mde_annual_sharpe_80pct_power_{label}"] = z / sqrt(yrs)
    out["power_at_sharpe_one_sided_5pct"] = {
        f"sharpe_{sr}": nd.cdf(sr * sqrt(yrs) - nd.inv_cdf(0.95)) for sr in (0.5, 1.0, 1.5, 2.0)
    }
    out["note"] = (
        "G3 trades only on gap days (P95 gives about 12 days a year per ETF), so its effective sample is far smaller than the session count; "
        "the MDE for G3 is reported again in results.json from the actual number of trade days."
    )
    return out


def main() -> int:
    D.mkdir(parents=True, exist_ok=True)
    (ROOT / "reports/harness/source_cards").mkdir(parents=True, exist_ok=True)
    cards = build_cards()
    (ROOT / CARDS).write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards))

    spy = pd.read_parquet(ROOT / "data/features/t15_minute/SPY.parquet", columns=["date"])[
        "date"
    ].unique()
    spy = pd.DatetimeIndex(sorted(spy))
    n_sessions = int(((spy >= G.RECENT_START) & (spy <= G.DATA_END)).sum())
    pw = power_table(n_sessions)

    trials = {"G1": len(G.grid_g1()), "G2": len(G.grid_g2()), "G3": len(G.grid_g3()) + 2}
    total = sum(trials.values())

    # ---------------------------------------------------------------- spec (derived from the T-15 draft)
    spec = yaml.safe_load(T15_SPEC.read_text())
    spec["name"] = ITER
    spec["description"] = (
        "Preregistered T-20261007-06: intraday batch 2 for quant2 (G1 noise band on options-active mega caps, G2 end-of-day reversal, G3 ETF gap fill and its "
        "combination with the QQQ noise band). Signal on bar close, fill at next bar open, flat at the close. Research only, no broker writes."
    )
    spec["universe"] = ["SPY", "QQQ", "IWM", "DIA"]
    spec["factors"]["intraday_rules"]["description"] = (
        "Documentation-only stand-in. Noise bands, end-of-day reversal ranks and gap percentiles are built inside scripts/run_t20261007_06_intraday_batch2.py from SIP minute and 5-minute bars."
    )
    rd = spec["research_design"]
    rd["iter_id"] = ITER
    rd["candidate_manifest_path"] = f"reports/research/iterations/{ITER}/candidate-manifest.json"
    rd["data_feasibility_path"] = f"reports/research/iterations/{ITER}/data-feasibility.json"
    rd["source_cards_path"] = CARDS
    rd["source_card_claim_ids"] = [s["claim_id"] for s in SOURCES]
    rd["parameter_space"] = {
        "G1_pool": G.G1_POOLS,
        "G1_interval_min": G.G1_INTERVAL,
        "G1_mult": G.G1_MULT,
        "G2_universe": G.G2_UNIVERSE,
        "G2_grouping": G.G2_GROUP,
        "G2_signal": G.G2_SIGNAL,
        "G3_gap_percentile": G.G3_PCT,
        "G3_entry_min": G.G3_ENTRY,
        "G3_exit_min": G.G3_EXIT,
    }
    rd["candidate_budget"] = 11
    rd["candidate_budget_note"] = (
        "11 anchor candidates; the full grid (71 versions) is in grid-registry.json and counted in the trial ledger."
    )
    rd["selection_objective"] = (
        "Depth curves, not a return search: median of the top three recent net Sharpe variants per depth point; every registered version is a counted trial for DSR."
    )
    spec["notes"]["intent"] = (
        "Find new independent intraday sleeves for quant2 (low correlation to the QQQ noise band)."
    )
    spec["notes"]["hypothesis_id"] = "T-20261007-06"
    spec["notes"]["previous_link"] = "t20261006_15_intraday_rules"
    (ROOT / SPEC).write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))

    from open_composer.models.strategy_spec import load_strategy_spec
    from open_composer.research.iteration_dossier import candidate_authorization_binding_sha256
    from open_composer.strategy_versions import strategy_content_hash

    spec_hash = strategy_content_hash(load_strategy_spec(ROOT / SPEC))

    # ---------------------------------------------------------------- candidates
    cands = []
    for p in G.G1_POOLS:
        cands.append(
            dict(
                id=f"G1_anchor_{p}",
                params={
                    "group": "G1",
                    "pool": p,
                    "interval": 30,
                    "mult": 1.0,
                    "rule": "selection = median of top-3 variants of the pool",
                },
            )
        )
    for u in G.G2_UNIVERSE:
        cands.append(
            dict(
                id=f"G2_anchor_{u}",
                params={
                    "group": "G2",
                    "universe": u,
                    "grouping": "decile",
                    "signal": "pc_to_1500",
                    "rule": "selection = median of top-3 variants of the universe",
                },
            )
        )
    for b in G.G3_DEPTH_BASKETS:
        cands.append(
            dict(
                id=f"G3_anchor_{b}",
                params={
                    "group": "G3",
                    "basket": b,
                    "pct": 0.90,
                    "entry": 5,
                    "exit": 30,
                    "rule": "selection = median of top-3 of the INDEX4 main grid, applied to the basket",
                },
            )
        )
    cands.append(
        dict(
            id="G3_combo_qqq_noiseband",
            params={
                "group": "G3",
                "combination": "G3 selected spec + QQQ noise band A_paper (k30, M1, both, cap 1)",
                "weights": ["equal", "inverse_vol"],
            },
        )
    )
    manifest_c = [
        {
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
            "path": "intraday_batch2_scale_curve",
            "role": "deterministic_mechanism_candidate",
            "spec_path": SPEC,
            "validation_contract": "fixture",
        }
        for c in cands
    ]
    gen = datetime.now(UTC).isoformat()
    grid = G.all_trials()
    reg = {
        "iter_id": ITER,
        "registered_at": gen,
        "trial_counts": {**trials, "total": total},
        "versions": grid,
    }
    (D / "grid-registry.json").write_text(json.dumps(reg, ensure_ascii=False) + "\n")
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
            "registry_sha256": sha(f"reports/research/iterations/{ITER}/grid-registry.json"),
            "trial_counts": {**trials, "total": total},
            "note": "Decision candidates are depth-point anchors; every version of the full grid is a counted trial listed in grid-registry.json.",
        },
    }
    (D / "candidate-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    man_sha = sha(f"reports/research/iterations/{ITER}/candidate-manifest.json")

    # ---------------------------------------------------------------- cost table (measured)
    raw = json.loads((ROOT / "data/research/t0706_quotes/cost_table_raw.json").read_text())
    cost_table = {
        "base_cost_bps": raw["summary"]["base_cost_bps"],
        "stress_cost_bps": raw["summary"]["stress_cost_bps"],
        "method": "scripts/t0706_quote_sample.py (SIP NBBO last valid quote in [T-60s,T)) aggregated by scripts/t0706_cost_table.py; see hypotheses.md section 0",
        "slippage_bp": {"stock_per_side": 0.5, "etf_per_side": 0.02},
        "sec_fee_bp_sell": 0.206,
        "multipliers": [0.5, 1.0, 2.0, 4.0],
        "sample": raw["sample"],
        "per_symbol_median_hs_bp": raw["per_symbol"],
        "bucket_median_hs_bp": raw["bucket"],
        "min_days_per_symbol": 8,
        "snapshot_for_fill": {
            "G1": {
                "before_1000": "0945",
                "1000_to_1530": "1200",
                "from_1530": "1545",
                "session_close": "1555",
            },
            "G2": {"entry_1530": "1530", "exit_1555": "1555"},
            "G3": {"entry_0935": "0935", "entry_0945": "0945", "exit": "0945"},
        },
    }
    (D / "cost-table.json").write_text(json.dumps(cost_table, indent=2, ensure_ascii=False) + "\n")
    cost_sha = sha(f"reports/research/iterations/{ITER}/cost-table.json")

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
            "intraday_batch2_scale_curve": {
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
            "etf_minutes": "data/features/t15_minute/<SYM>.parquet (SIP 1-minute 2016-2026, read only up to 2026-09-15)",
            "stock_minutes_g1": "data/features/t0706_minute/<SYM>.parquet built by scripts/t0706_build_panels.py from data/sip-hist/minute and data/sip/minute",
            "stock_5min_g2": "data/features/intraday5m (T-20261006-21), months with .READY, read only up to 2026-09-15",
            "power": pw,
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
                    "random_direction_placebo_100_seeds",
                    "cross_sectional_random_rank_placebo_100_seeds",
                    "same_entry_times_buy_and_hold_exposure",
                    "qqq_noise_band_correlation_benchmark",
                ],
                "candidate_count": len(ids),
                "hypothesis_refs": ["T-20261007-06"],
                "name": "intraday_batch2_scale_curve",
                "parameters": rd["parameter_space"],
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
    (D / "trial-ledger.jsonl").write_text(
        "".join(
            json.dumps({"ts": T0, "group": g, "kind": "main_grid", "versions": n}) + "\n"
            for g, n in trials.items()
        )
    )

    # ---------------------------------------------------------------- brief + direction review
    brief = json.load(open(D / "external-brief.json"))
    bs = brief_sources()
    objective = (
        "T-20261007-06: do end-of-day reversal (G2), ETF gap fill (G3) and the noise band generalised to options- and leveraged-ETF-active mega caps (G1) keep a net-of-cost, "
        "low-correlation edge in 2024-01-08..2026-09-15, so that quant2 (intraday account) gets new independent sleeves?"
    )
    brief.update(
        {
            "candidate_matrix_revisions": [
                {
                    "decision": "keep",
                    "path": "intraday_batch2_scale_curve",
                    "reason": "initial preregistration",
                }
            ],
            "current_source_card_paths": [CARDS],
            "difference_from_existing": [
                {
                    "existing": "direction:cross_sectional_gap_fade",
                    "difference": "Not the single-stock gap fade (refuted: gross +11.5 bp a day, cost -38.5 bp a day, full turnover): ETF-only, trades only on large-gap days, entries at 09:35/09:45, ETF costs below 1 bp.",
                },
                {
                    "existing": "iteration:t20261006_15_intraday_rules",
                    "difference": "T-15 tested the noise band on ETFs and found the edge in QQQ only; G1 asks the same rule on single stocks by pre-defined pools (top dollar volume, stocks with leveraged single-stock ETFs).",
                },
                {
                    "existing": "direction:end_of_day_reversal",
                    "difference": "Never tested (parked for lack of minute data); now run on 5-minute SIP bars with measured 15:30/15:55 costs, as a true out-of-sample extension of the paper (sample ends 2019).",
                },
            ],
            "hypothesis_links": [
                {"hypothesis_id": "T-20261007-06", "source_urls": [s["url"] for s in bs[:4]]}
            ],
            "mechanism_description": "G1 hedging-demand noise-band momentum on mega-cap stocks; G2 retail-attention and short-seller risk-management reversal in the last hour; G3 overnight-gap reversion in ETFs in the first hour.",
            "mechanism_family": "intraday_rule_based_depth_curve_batch2",
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
                "end_of_day_reversal_baltussen_da_soebhag",
                "hedging_demand_intraday_momentum_baltussen",
                "gap_fill_plus_intraday_momentum_concretum",
                "single_stock_leveraged_etf_listing_dates",
                "noise_band_rule_zarattini",
                "measured_nbbo_half_spreads",
                "paper_fill_model_optimism",
            ],
        }
    )
    (D / "external-brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n")

    reviewed = now()
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
            "query": "Baltussen Da Soebhag End-of-day reversal",
            "searched_at": reviewed,
            "opened_urls": [bs[0]["url"]],
        },
        {
            "query": "Concretum Research gap fill intraday momentum SPY Sharpe 1.95 replication",
            "searched_at": reviewed,
            "opened_urls": [bs[2]["url"]],
        },
        {
            "query": "single-stock leveraged ETF NVDA TSLA launch date issuer Direxion",
            "searched_at": reviewed,
            "opened_urls": [bs[3]["url"]],
        },
        {
            "query": "Zarattini Aziz Barbon noise area intraday momentum",
            "searched_at": reviewed,
            "opened_urls": [bs[4]["url"]],
        },
        {
            "query": "Baltussen Da Lammers Martens hedging demand market intraday momentum (T-20261006-12 snapshot reused)",
            "searched_at": SURVEY_FETCH,
            "opened_urls": [bs[1]["url"]],
        },
        {
            "query": "Alpaca paper trading fill model NBBO partial fills (T-20261006-12 snapshot reused)",
            "searched_at": SURVEY_FETCH,
            "opened_urls": [bs[-1]["url"]],
        },
        {
            "query": "Gao Han Li Zhou market intraday momentum first half-hour last half-hour (T-20261006-15 snapshot reused)",
            "searched_at": SURVEY_FETCH,
            "opened_urls": [bs[5]["url"]],
        },
        {
            "query": "Heston Korajczyk Sadka intraday patterns in the cross-section of stock returns (T-20261006-12 snapshot reused)",
            "searched_at": SURVEY_FETCH,
            "opened_urls": [bs[6]["url"]],
        },
        {
            "query": "Alpaca orders time in force opg cls bracket extended hours (T-20261006-12 snapshot reused)",
            "searched_at": SURVEY_FETCH,
            "opened_urls": [bs[7]["url"]],
        },
        {
            "query": "IEX share of US equity volume 2026 (T-20261006-12 snapshot reused)",
            "searched_at": SURVEY_FETCH,
            "opened_urls": [bs[8]["url"]],
        },
    ]
    dr = json.load(open(D / "direction-review.json"))
    dr.update(
        {
            "decision": "proceed",
            "reviewed_at": reviewed,
            "objective": objective,
            "target_regime_and_horizon": (
                f"Decision window 2024-01-08 to 2026-09-15 ({n_sessions} sessions), split into the 11 phases of reports/research/program/regimes-2026-10-01 (P11 to 2026-09-15); "
                "2017-10..2023-08 is the V4 crash check only. Holding: minutes to one session (G1), 25 minutes (G2), 25-55 minutes (G3). Validity ends when the forward 63-session net mean falls below zero."
            ),
            "existing_solution_comparison": (
                "Published: Baltussen-Da-Soebhag 2025 (gross 3.78-6.86 bp a day, authors say costs may remove it), Baltussen et al. JFE 2021 (hedging-demand intraday momentum), "
                "Concretum 2024 (SPY gap fill + momentum Sharpe 1.95, commission only, no replication), Zarattini et al. 2024 (noise area). No source gives a net-of-spread live record. "
                "Local: T-15 found the noise-band edge in QQQ only; the portfolio layer (T-20261006-24) says account Sharpe 2 needs about six independent Sharpe-1 sleeves and only two of today's six are independent. "
                "Reuse: T-15 engine and statistics (scripts/t15_engine.py, t15_stats.py), D4 quote fetcher, the 5-minute panel of T-21; new: pools, measured NBBO costs at fill times, G2/G3 engines."
            ),
            "remaining_evidence_gap": (
                "Not measured before this task: mega-cap and ETF half spreads at 09:35-09:45, 15:30 and 15:55 (sampled here); IEX versus SIP agreement for the new symbols (done for any passing candidate before paper); "
                "G2 top-100/500 1-minute data for the V4 check and the 1-minute phase test (5-minute bars only); closing-auction fills (diagnostic only); G3 effective sample is small because gap days are rare."
            ),
            "negative_experiments_checked": (
                "Registry rows read 2026-10-07: dir:cross_sectional_gap_fade refuted (single stocks: gross +11.5 bp a day vs cost -38.5 bp, daily full turnover; short leg tested at ADV buckets); "
                "dir:end_of_day_reversal parked, never tested; dir:overnight_intraday_gap_retail_pwb refuted; dir:letf_close_rebalancing_flow_reversal refuted (next-day reversal in the index ETF); "
                "dir:smallcap_gap_down_fade_auction_execution refuted; T-15 B group (market intraday momentum) not holding out of sample. Differences: ETF-only gap leg at 09:35/09:45 rather than open-to-close single stocks; "
                "end-of-day reversal is a separate last-hour mechanism; G1 pools are defined before results."
            ),
            "cost_and_execution_assumptions": (
                "Signal on the close of bar t, fill at the open of bar t+1, flat at the 15:59 close (G1, G3 on 1-minute bars) or the 15:55 close (G2, 5-minute bars). Per-side cost = measured SIP NBBO half spread at the fill time "
                "(per symbol median if >= 8 sampled days, else rank-bucket median) + slippage (0.5 bp stocks, 0.02 bp ETFs) + 0.206 bp SEC fee on sells; multipliers 0.5/1/2/4 on the spread part. "
                "Shorts: easy-to-borrow liquid names only, intraday, no borrow fee. Paper fills are NBBO-based and optimistic on size."
            ),
            "stop_condition": (
                "Per group, frozen in hypotheses.md: 'not holding' only if reproduction, faithful implementation, three or more depth points, budget and power are all satisfied; otherwise 'not at depth' with the missing item. "
                "Budget: 71 registered versions, heavy runs via scripts/heavy_run.sh, Modal at most 2 USD, results by 2026-10-11, report by 2026-10-12 06:00 UTC. No change to versions, windows, gates or costs after results."
            ),
            "queries": queries,
            "sources": dr_sources,
            "cheapest_decisive_test": {
                "action": "scripts/run_t20261007_06_intraday_batch2.py: G3 and G2-ETF14 on the existing 1-minute ETF panels first, then G2 TOP100/500 on the 5-minute panel and G1 on the stock minute panels; results.json.",
                "pass_condition": "P1 paper incubation: recent-window net Sharpe positive with DSR >= 0.7, net placebo percentile >= 0.9, >= 3 of 6 robustness checks, no veto (config/evaluation-standard-v2.json v2.1, section 5b).",
                "falsification_condition": "A group is 'not holding' only if reproduction, faithful implementation, three depth points, full registered grid and power are all satisfied and the best candidate's recent net Sharpe <= 0 or its net placebo percentile < 0.9; otherwise 'not at depth'.",
                "max_compute_minutes": 360,
            },
        }
    )
    (D / "direction-review.json").write_text(json.dumps(dr, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
