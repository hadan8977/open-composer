# ruff: noqa: E501
"""Build the T-20261006-22 preregistration artifacts (spec, source cards, trial grid, config)
and run scripts/new_lightweight_iteration.py.  Contains no market data and computes no return."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IT = "t20261006_22_st_reversal"
D = ROOT / "reports/research/iterations" / IT
SRC = "reports/research/intel/sources/st-reversal-2026-10-06"
OLD = "reports/research/intel/sources/mid-frequency-2026-10-04"
CARDS = ROOT / f"reports/harness/source_cards/{IT}.jsonl"
SPEC = ROOT / f"strategy_specs/drafts/{IT}.yaml"
NOW = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


# ------------------------------------------------------------------ trial grid
UNIVERSES = (500, 1000, 3000)
LS = (5, 21)
RESIDS = ("ind", "pca")
HS = (1, 5)
ROBUST = ("lowturn", "nonews", "vixscale", "exec_close")
MODELS = ("ridge", "lgbm")


def trial_grid() -> list[dict]:
    """Addendum 2 (contract.md section 16): 24 main cells + 4 robustness cells + 2 model cells."""
    rows = []
    for u, r, ell, h in itertools.product(UNIVERSES, RESIDS, LS, HS):
        rows.append(
            {
                "cell_id": f"R_U{u}_{r}_L{ell}_H{h}_open",
                "kind": "main",
                "family": f"MAIN_{r}_U{u}",
                "universe": u,
                "resid": r,
                "L": ell,
                "H": h,
                "exec": "open",
                "cond": "none",
            }
        )
    for c in ROBUST:
        rows.append(
            {
                "cell_id": f"ROB_{c}_on_selected_spec",
                "kind": "robustness",
                "family": f"ROBUST_{c}",
                "applies_to": "selected spec (second-ranked of the top three main cells by recent net Sharpe)",
            }
        )
    for m in MODELS:
        rows.append(
            {
                "cell_id": f"MODEL_{m}_on_selected_universe_H",
                "kind": "model",
                "family": f"MODEL_{m}",
                "applies_to": "universe and H of the selected spec",
            }
        )
    return rows


def power() -> dict:
    from statistics import NormalDist

    z = NormalDist().inv_cdf
    sessions = 685
    years = sessions / 252
    out = {
        "recent_sessions": sessions,
        "years": years,
        "min_detectable_sharpe_single_test_5pct_80pct": (z(0.95) + z(0.8)) / math.sqrt(years),
        "min_detectable_sharpe_bonferroni_24": (z(1 - 0.05 / 24) + z(0.8)) / math.sqrt(years),
        "lo_se_at_sharpe_1.0": math.sqrt((1 + 0.5) / years),
        "note": "iid null standard error 1/sqrt(years); Lo (2002) se at Sharpe s is sqrt((1 + s^2/2)/years)",
    }
    return out


def main() -> None:
    grid = trial_grid()
    assert len(grid) == 30, len(grid)
    D.mkdir(parents=True, exist_ok=True)
    (D / "trial-grid.json").write_text(
        json.dumps(
            {"iter_id": IT, "n_cells": len(grid), "created_at": NOW, "cells": grid}, indent=1
        )
        + "\n"
    )
    (D / "power.json").write_text(json.dumps(power(), indent=1) + "\n")

    # source cards: reuse the verified P1 cards (same primary snapshots) + new snapshots of this task
    cards = []
    reuse = {
        "dlsa_2021_sharpe_half_life_seven_days",
        "da_liu_schaumburg_2014_residual_reversal_three_times",
        "lou_polk_skouras_2019_overnight_intraday_tug_of_war",
        "avellaneda_lee_2010_residual_mean_reversion",
        "attention_factors_2025_cost_in_objective",
        "frazzini_israel_moskowitz_2012_reversal_cost_constrained",
        "blitz_huij_lansdorp_verbeek_2013_residual_reversal_net",
    }
    for line in (
        (ROOT / "reports/harness/source_cards/t20261005_p1_s0_decay.jsonl").read_text().splitlines()
    ):
        c = json.loads(line)
        if c["claim_id"] in reuse:
            c["applies_to"] = ["dir:short_horizon_residual_reversal_statarb", IT]
            cards.append(c)

    def card(
        cid,
        url,
        snap,
        claim,
        quote,
        applic,
        limits,
        ptype="paper",
        pub="",
        status="opened_primary_source",
        method="snapshot_text_read_by_research_agent",
        repl="",
    ):
        return {
            "accessed_at": NOW,
            "applies_to": ["dir:short_horizon_residual_reversal_statarb", IT],
            "claim": claim,
            "claim_id": cid,
            "fetched_at": NOW,
            "impact_on_spec": applic,
            "independent_replication": repl,
            "limitations": limits,
            "published_or_updated_at": pub,
            "quote": quote,
            "source_sha256": sha(snap),
            "source_snapshot": snap,
            "source_type": ptype,
            "source_url": url,
            "status": "verified",
            "verification_method": method,
            "verification_status": status,
        }

    cards += [
        card(
            "avellaneda_lee_2010_pca_sharpe_decline_costs_5bp",
            "https://math.nyu.edu/~avellane/AvellanedaLeeStatArb071008.pdf",
            f"{SRC}/avellaneda-lee-statarb.txt",
            "Avellaneda and Lee (Quantitative Finance 2010, working-paper version): on US stocks above 1 bn market cap, 60-day residual window, ETF or PCA factors, entry at 1.25 sd and exit at 0.5 sd, 5 bp per trade slippage; PCA strategies have an average annual Sharpe of 1.44 over 1997-2007 and only 0.9 in 2003-2007; ETF strategies about 1.1; volume-adjusted (trading-time) signals reach 1.51 in 2003-2007.",
            "PCA-based strategies have an average annual Sharpe ratio of 1.44 over the period 1997 to 2007",
            "Fixes the PCA residual construction (top components, trailing window, standardised returns) and the volume/turnover conditioning idea; the decline after 2002 is the prior for our 2024+ window.",
            "Authors' own backtest ending 2007, flat 5 bp per trade, no borrow cost, market cap above 1 bn only.",
            pub="2010-07-01",
        ),
        card(
            "nagel_2012_reversal_is_liquidity_provision_vix",
            "https://www.nber.org/system/files/working_papers/w17653/w17653.pdf",
            f"{SRC}/nagel-evaporating-liquidity-w17653.txt",
            "Nagel (NBER w17653, Review of Financial Studies 2012): short-term reversal returns proxy the return to liquidity provision; the expected return is strongly time-varying and highly predictable with the VIX index; conditional Sharpe ratios rise with VIX in turmoil such as 2007-09.",
            "the expected return from liquidity provision is strongly time-varying and highly predictable with the VIX index",
            "Basis for the `vixscale` condition (scale the gross up when VIX is high relative to its trailing median).",
            "Sample ends 2009; the VIX predictability in 2024-2026 is untested by this paper.",
            pub="2011-12-01",
        ),
        card(
            "da_liu_schaumburg_2014_management_science_large_stocks_recent",
            "https://academicweb.nd.edu/~zda/Reversal.pdf",
            f"{SRC}/da-liu-schaumburg-closer-look.txt",
            "Da, Liu and Schaumburg (Management Science 60(3), 2014): the part of a past return not explained by fundamental (cash-flow) news reverses; the monthly Sharpe of the residual-based reversal is 0.52 versus 0.14 for the standard one; the effect still exists among large stocks in more recent years once the industry momentum effect is controlled for.",
            "the short-term reversal effect still exists even among large stocks for the more recent years",
            "Supports the industry-adjusted residual and the no-news condition; the large-stock survival statement is the prior for the liquid universes.",
            "Monthly horizon, 1982-2009 sample, analyst-revision proxy for news, not daily trading with costs.",
            pub="2014-03-01",
        ),
        card(
            "farkas_neszveda_2024_laggard_reversal",
            "http://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2024-Lisbon/papers/underreaction_STReversal.pdf",
            f"{SRC}/efma2024-underreaction.txt",
            "Farkas and Neszveda (EFMA 2024 draft, January 2024): short-term reversals and industry momentum arise from stocks that under-react to industry information (Laggards); long-short strategies trading Laggards double the profitability of industry momentum and short-term reversal, while the same strategies on Leader stocks are typically not profitable.",
            "longshort strategies trading Laggards doubles the profitability of industry momentum and short-term reversal strategies",
            "Motivates the industry-residual variant and an industry feature in the models; the Laggard proxy itself is not built here.",
            "Working paper, monthly CRSP, sample years and post-2010 split not verified by this agent.",
            pub="2024-01-01",
        ),
        card(
            "equity_statarb_github_oos_2019_2024_negative",
            "https://github.com/andrewzhang615-star/equity-statarb",
            f"{SRC}/equity-statarb-github-summary.md",
            "Open-source test (CRSP daily 2000-2024, survivorship-free, one-day hold, 7 bp flat cost): leave-one-out sector-residual reversal has in-sample 2000-2018 gross Sharpe 0.90 and net 0.34, and out-of-sample 2019-2024 gross 0.23 and net -0.15 (breakeven 4.2 bp); the alpha sits in short positions and low-priced names; the PCA(15) variant had no gross edge 2019-2024 (-0.07).",
            "Out-of-sample 2019-2024: gross 0.23, net -0.15, breakeven 4.2 bp",
            "The strongest local prior against the family: the cheapest test is whether gross edge exists at all in 2024-2026 for liquid names, and what the measured costs do to it.",
            "README summary through the fetch tool, code and tables not read; single author; flat cost; includes low-priced names and long/short symmetric shorts without a borrow rule.",
            ptype="platform_docs",
            pub="2025-01-01",
            status="opened_secondary_summary",
            method="fetch_tool_summary_of_readme",
        ),
    ]
    CARDS.parent.mkdir(parents=True, exist_ok=True)
    CARDS.write_text("".join(json.dumps(c, sort_keys=True) + "\n" for c in cards))

    # StrategySpec draft from the P1 Stage-0 draft
    spec = yaml.safe_load((ROOT / "strategy_specs/drafts/t20261005_p1_s0_decay.yaml").read_text())
    spec["name"] = IT
    spec["description"] = (
        "T-20261006-22: US short-horizon residual-reversal stat-arb book, preregistered 2026-10-06. Daily cross-sectional "
        "reversal of 1/5/10/21-session residual returns (beta, industry, PCA(10) residuals), 500/1000/3000 liquid "
        "names, held 1/5/10 sessions as overlapping batches, dollar neutral with a SPY beta hedge, shorts in the "
        "easy-to-borrow proxy only, cost model v1, ridge and LightGBM ranker variants. Research test for a paper sub-strategy; "
        "not a paper or live strategy."
    )
    spec["factors"] = {
        "residual_reversal": {
            "source": "expression",
            "expression": "-(close / lag(close, 5) - 1)",
            "default": 0.0,
            "description": "Documentation-only stand-in. The real signal is -sum of the last L daily residual returns (beta, industry or PCA residual) built by scripts/t22_build.py; decision at the close of t, trade at the open or close of t+1.",
            "params": {"decision_lag_sessions": 0},
        }
    }
    spec["portfolio"]["selected_route_label"] = f"{IT}:residual_reversal"
    spec["portfolio"]["max_symbol_weight"] = 0.005
    spec["risk"]["max_position_weight"] = 0.005
    rd = spec["research_design"]
    rd["iter_id"] = IT
    rd["candidate_manifest_path"] = f"reports/research/iterations/{IT}/candidate-manifest.json"
    rd["data_feasibility_path"] = f"reports/research/iterations/{IT}/data-feasibility.json"
    rd["source_cards_path"] = f"reports/harness/source_cards/{IT}.jsonl"
    rd["source_card_claim_ids"] = [c["claim_id"] for c in cards]
    rd["parameter_space"] = {
        "universe_top_adv": list(UNIVERSES),
        "lookback_L": list(LS),
        "residual": list(RESIDS),
        "holding_H": list(HS),
        "execution_main": ["open"],
        "robustness_on_selected_spec": list(ROBUST),
        "model_second_stage": list(MODELS),
    }
    rd["candidate_budget"] = 12
    rd["selection_objective"] = (
        "Recent-window (2024-01-08..2026-09-15) net Sharpe at 1x cost through the full run_book engine; tier by scorecard_v2 with N = 24 main-grid trials; the spec selection rule is contract.md section 16 item 3."
    )
    rd["candidate_budget_note"] = (
        "12 candidate families group 30 registered cells (24 main + 4 robustness + 2 model); the DSR family is the 24 main cells (trial-grid.json, contract.md section 16)."
    )
    rd["anti_overfit_notes"] = [
        "contract.md was frozen before any return of this book was computed; only data-coverage counts were read.",
        "Grid, conditions, selection rule, tier and depth rule are not changed after results; later bugs are dated amendments.",
        "Forward holdout 2026-09-16..2026-09-30 is not read until the final scoring.",
        "The closest prior (equity-statarb repo, OOS net -0.15) is disclosed and shapes the cheapest test (Stage A gross screen).",
    ]
    rd["validation_plan"] = [
        "Identity and no-lookahead checks of contract.md section 13 before any net result.",
        "Stage A: 24 main cells, recent window, full engine, costs 0.5x/1x/2x.",
        "Stage B: all 24 on the diagnostic window (V4); selected spec: 100-seed placebo, six robustness checks, whole-share check, scorecard tier, then 4 robustness and 2 model cells.",
        "Report: gross/net/cost share/turnover/correlation with the stock long-short book/market-cap split by variant.",
    ]
    spec["notes"] = {
        "intent": "Find out whether a daily, many-bet residual-reversal book keeps a net Sharpe after measured costs in 2024-2026 and is uncorrelated with the monthly stock long-short book, to decide a paper sub-strategy.",
        "hypothesis_id": "T-20261006-22",
        "previous_link": "t20261005_p1_s0_decay",
        "broker_writes": False,
        "promotion_eligible": False,
        "contract_status": "preregistered",
    }
    SPEC.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=200))

    # candidate families (15)
    cands = []
    for r, u in itertools.product(RESIDS, UNIVERSES):
        cands.append(
            {
                "candidate_id": f"MAIN_{r}_U{u}",
                "parameters": {
                    "kind": "main",
                    "universe": f"top {u} adv_rank at t",
                    "residual": r,
                    "lookback_L": list(LS),
                    "holding_H": list(HS),
                    "execution": "open of t+1",
                    "condition": "none",
                    "cells": len(LS) * len(HS),
                    "book": "contract.md sections 3, 5-8 as amended by section 16 (100 names per side, equal weight, 300,000 USD)",
                },
            }
        )
    for c in ROBUST:
        cands.append(
            {
                "candidate_id": f"ROBUST_{c}",
                "parameters": {
                    "kind": "robustness",
                    "applies_to": "selected spec only (contract.md section 16 item 3), not used for selection",
                    "variant": c,
                    "definition": "contract.md sections 4, 7 and 16",
                },
            }
        )
    for m in MODELS:
        cands.append(
            {
                "candidate_id": f"MODEL_{m}",
                "parameters": {
                    "kind": "model",
                    "model": m,
                    "applies_to": "universe and H of the selected spec, second stage",
                    "features_labels_training": "contract.md section 10 as amended by section 16",
                },
            }
        )
    quotes = {c["claim_id"]: c for c in cards}
    sources = [
        {
            "claim_id": c["claim_id"],
            "url": c["source_url"],
            "published_or_updated_at": c.get("published_or_updated_at") or "2026",
            "source_type": c["source_type"],
            "credibility": c.get("credibility", "peer_reviewed_or_working_paper"),
            "core_claim": c["claim"],
            "project_applicability": c.get("impact_on_spec") or c.get("applicability", ""),
            "reflection": c.get("limitations", ""),
        }
        for c in quotes.values()
    ]
    config = {
        "iter_id": IT,
        "strategy_name": IT,
        "representative_spec_path": f"strategy_specs/drafts/{IT}.yaml",
        "path_name": "short_horizon_residual_reversal_statarb",
        "hypothesis_id": "T-20261006-22",
        "objective": "Test whether a daily residual-reversal book (industry and PCA residuals, 3 liquid universes, 5 and 21 day lookbacks, 1 and 5 day holds, 100 names per side for a 300,000 USD account; conditions and ridge/LightGBM rankers as second-stage robustness) keeps a net Sharpe after measured costs in 2024-2026 and is uncorrelated with the existing stock long-short book.",
        "benchmark_family": [
            "equal_weight_universe",
            "market_proxy_spy",
            "cash_proxy_bil",
            "placebo_random_rank_same_construction",
            "existing_stock_long_short_book_v12",
        ],
        "candidates": cands,
        "cost_table": {
            "base_cost_bps": "model",
            "judged_cost": "cost model v1 via costfn.make_cost_fn (half spread by price/ADV/vol/year, square-root impact at actual trade dollars, 0.5 bp fees, borrow 25 bp a year on short notional)",
            "stress_cost_bps": "2x model (also 0.5x), borrow 100 bp stress",
            "two_x_cost_check": "net_k = gross - k * costs on the same weight paths for every cell",
        },
        "sources": sources,
        "topic_coverage": [
            "short_term_reversal_residual",
            "statistical_arbitrage_pca_etf_residual",
            "liquidity_provision_vix_conditioning",
            "turnover_conditioned_reversal",
            "news_vs_no_news_reversal",
            "overnight_intraday_components",
            "transaction_cost_and_capacity",
            "post_publication_decay_out_of_sample",
            "model_ranker_vs_rule",
        ],
        "hypothesis": {
            "statement": "Residual returns of liquid US stocks reverse over 1-10 sessions, and a daily many-bet book that trades the reversal in overlapping batches earns a net Sharpe in 2024-2026 that survives measured spreads, impact and borrow, with low correlation to the monthly stock long-short book.",
            "failure_mode": "The reversal has decayed to near zero gross in liquid names (equity-statarb repo: OOS 2019-2024 gross 0.23, net -0.15), the edge is concentrated in illiquid or hard-to-borrow names that the cost and borrow rules exclude, or daily turnover consumes the gross edge.",
            "measurement": "contract.md: Stage A 24 main cells on 2024-01-08..2026-09-15 through run_book with cost_model_v1; Stage B diagnostic window, placebo, six robustness checks and scorecard_v2 tier for the top cells.",
            "stop_pivot": "If every cell has recent gross Sharpe below 0.3 the family is closed at this depth (not at depth if any of the five depth conditions in contract.md section 12 is missing); if a cell reaches tier P1 write paper-sleeve-spec.md.",
        },
        "decision": {
            "path": "short_horizon_residual_reversal_statarb",
            "decision": "pending",
            "reason": "Preregistered 2026-10-06 before any return of this book was computed; executed by brief T-20261006-22.",
            "next_iteration_suggestion": "Depends on Stage A: promoted cell -> paper sleeve spec; otherwise record the death cause and depth shortfall.",
        },
        "source_cards_path": f"reports/harness/source_cards/{IT}.jsonl",
    }
    cfg_path = D / "lightweight-config.json"
    cfg_path.write_text(json.dumps(config, indent=1) + "\n")
    r = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/new_lightweight_iteration.py",
            str(cfg_path),
            "--overwrite",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    print(r.stdout[-1500:], r.stderr[-1500:])


if __name__ == "__main__":
    main()
