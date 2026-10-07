# ruff: noqa: E501
"""Write direction-review.json and external-brief.md for T-20261006-22 (no market data)."""

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IT = "t20261006_22_st_reversal"
D = ROOT / "reports/research/iterations" / IT
NOW = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
cards = [
    json.loads(x)
    for x in (ROOT / f"reports/harness/source_cards/{IT}.jsonl").read_text().splitlines()
]
p1 = {
    s["claim_id"]: s
    for s in json.loads(
        (
            ROOT / "reports/research/iterations/t20261005_p1_s0_decay/direction-review.json"
        ).read_text()
    )["sources"]
}
extra = {
    "avellaneda_lee_2010_pca_sharpe_decline_costs_5bp": (
        "US stocks above 1 bn market cap, 1996/2002-2007, daily",
        "Fixes the PCA residual recipe and gives the pre-/post-2003 decline as the prior.",
        "Authors' backtest ending 2007, flat 5 bp, no borrow cost.",
        "Khandani and Lo 2007 contrarian strategies reproduced in the same paper; no 2024+ replication found.",
    ),
    "nagel_2012_reversal_is_liquidity_provision_vix": (
        "US stocks 1926-2009, daily and monthly reversal portfolios",
        "Basis of the VIX-scaled condition.",
        "Sample ends 2009; no cost-net trading result.",
        "Hameed-Kang-Viswanathan 2010 find reversal returns after market declines (cited in the paper).",
    ),
    "da_liu_schaumburg_2014_management_science_large_stocks_recent": (
        "US stocks 1982-2009, monthly",
        "Supports the industry/no-news residual and the large-stock prior.",
        "Monthly, analyst-revision proxy for news, no daily costs.",
        "Blitz et al. 2013 reach the same direction with a Fama-French residual.",
    ),
    "farkas_neszveda_2024_laggard_reversal": (
        "US CRSP stocks, monthly, sample years not verified",
        "Motivates the industry residual and an industry feature.",
        "Working paper draft, post-2010 split not verified.",
        "None found.",
    ),
    "equity_statarb_github_oos_2019_2024_negative": (
        "US CRSP daily 2000-2024, one-day hold",
        "Strongest local prior against the family; shapes the cheapest test.",
        "README summary through the fetch tool; code not read; single author; flat 7 bp cost.",
        "Independent of the original papers; consistent with Avellaneda-Lee's own post-2003 decline.",
    ),
}
sources = []
for c in cards:
    if c["claim_id"] in p1:
        e = dict(p1[c["claim_id"]])
        e["source_card_path"] = f"reports/harness/source_cards/{IT}.jsonl"
        sources.append(e)
        continue
    mp, ap, lim, rep = extra[c["claim_id"]]
    sources.append(
        {
            "claim_id": c["claim_id"],
            "url": c["source_url"],
            "source_type": c["source_type"],
            "published_or_updated_at": c["published_or_updated_at"],
            "snapshot_path": c["source_snapshot"],
            "sha256": c["source_sha256"],
            "source_card_path": f"reports/harness/source_cards/{IT}.jsonl",
            "fetched_at": c["fetched_at"],
            "claim": c["claim"],
            "core_claim": c["claim"],
            "credibility": "peer_reviewed_or_working_paper",
            "applicability": ap,
            "independent_replication": rep,
            "limitations": lim,
            "market_and_period": mp,
        }
    )
_unused = [
    {
        "claim_id": c["claim_id"],
        "url": c["source_url"],
        "source_type": c["source_type"],
        "published_or_updated_at": c.get("published_or_updated_at") or "2026",
        "snapshot_path": c["source_snapshot"],
        "sha256": c["source_sha256"],
        "source_card_path": f"reports/harness/source_cards/{IT}.jsonl",
        "fetched_at": c["fetched_at"],
        "claim": c["claim"],
    }
    for c in cards
]
q = [
    (
        "Blitz Huij Lansdorp Verbeek Short-term residual reversal Journal of Financial Markets results transaction costs",
        ["https://repub.eur.nl/pub/40707"],
        "abstract page only; full text not reachable",
    ),
    (
        "Avellaneda Lee Statistical arbitrage in the US equities market PCA ETF residual Sharpe decline after 2002",
        ["https://math.nyu.edu/~avellane/AvellanedaLeeStatArb071008.pdf"],
        "PDF saved, method and 5 bp cost read",
    ),
    (
        "short-term reversal residual stat arb replication 2024 2025 Nagel Evaporating liquidity",
        [
            "https://www.nber.org/system/files/working_papers/w17653/w17653.pdf",
            "https://academicweb.nd.edu/~zda/Reversal.pdf",
        ],
        "both PDFs saved and quoted",
    ),
    (
        "github statistical arbitrage PCA residual mean reversion equities backtest",
        ["https://github.com/andrewzhang615-star/equity-statarb"],
        "README read through the fetch tool (summary)",
    ),
    (
        "github residual reversal strategy daily US equities CRSP short-term reversal backtest net of costs out-of-sample 2019-2024",
        ["https://github.com/andrewzhang615-star/equity-statarb"],
        "no further repo with OOS net numbers found",
    ),
    (
        "Medhat Schmeling Short-term momentum turnover reversal",
        ["https://openaccess.city.ac.uk/id/eprint/31278/"],
        "search summary only (not opened in full)",
    ),
    (
        "Lou Polk Skouras tug of war overnight intraday",
        ["https://researchonline.lse.ac.uk/id/eprint/87481"],
        "search summary; the NBER snapshot of the P1 dossier was reused",
    ),
    (
        "short-term reversal anomaly 2024 2025 decline stat arb crowding",
        [
            "http://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2024-Lisbon/papers/underreaction_STReversal.pdf"
        ],
        "2024 working paper saved; press on 2025-26 quant crowding is secondary and not used as evidence",
    ),
]
reuse_urls = sorted({s["url"] for s in sources if s["claim_id"] in p1})
q.append(
    (
        "Reused primary-source snapshots of the P1 Stage-0 dossier (T-20261005-01 / T-80, fetched 2026-10-04..05): DLSA, Da-Liu-Schaumburg NY Fed, Avellaneda-Lee 2010, Attention Factors, Frazzini-Israel-Moskowitz, Lou-Polk-Skouras, Blitz et al.",
        reuse_urls,
        "snapshots and source cards copied unchanged from reports/research/intel/sources/mid-frequency-2026-10-04 and p1-s0-decay-2026-10-05",
    )
)
queries = [{"query": s, "searched_at": NOW, "opened_urls": u, "note": n} for s, u, n in q]
dr = {
    "schema_version": 1,
    "iter_id": IT,
    "reviewed_at": NOW,
    "decision": "proceed",
    "objective": "Decide, within 48 hours, whether a daily residual-reversal book (industry and PCA residuals, three liquid universes, 5 and 21 day lookbacks, 1 and 5 day holds, 100 names per side, turnover/news/VIX conditions and ridge/LightGBM rankers as second-stage robustness) keeps a net Sharpe after measured costs in the 2024-2026 window and is uncorrelated enough with the existing stock long-short book to be a paper sub-strategy of the quant1 account.",
    "target_regime_and_horizon": "US stocks and ETF hedge, top 500/1000/3000 by ADV, signals at the close of t from 5 or 21 sessions of residual returns, 1 or 5 session holds as overlapping batches, trade at the open of t+1 (close of t+1 as a robustness cell). Judged on 2024-01-08..2026-09-15 and by market phase; 2017-10..2023-08 only for crash veto and diagnostics; the regime in which it should work is high cross-sectional dispersion / elevated VIX (Nagel 2012), the failure signal is a negative 63-session z of the book and breakdown of the PCA residual explanatory share.",
    "existing_solution_comparison": "Published residual-reversal stat-arb: Avellaneda-Lee PCA 1.44 net (1997-2007, 0.9 in 2003-07, 5 bp, cap above 1 bn), Blitz et al. monthly residual reversal net of costs among large caps after 1990, Da-Liu-Schaumburg monthly Sharpe 0.52 vs 0.14, DLSA about 1.5 on 550 stocks with a learned model (2002-2016), Attention Factors 2.3 net with costs in the objective (to 2021). Independent post-2019 evidence is negative: the equity-statarb repo (CRSP, daily sector residual) has OOS 2019-2024 gross 0.23, net -0.15 at 7 bp. Funds run this class at scale with execution infrastructure; our edge, if any, is the measured liquid-name spread model and a short-capable book at small size.",
    "remaining_evidence_gap": "No published or open number for a daily residual-reversal book in 2024-2026 with measured spread/impact/borrow, a PCA residual versus beta/industry residual comparison on the same data, or the VIX/turnover/news conditions out of sample. Our own panel can supply exactly that.",
    "negative_experiments_checked": "Registry rows read (last row each): sector_residual_reversal_statarb_decay (external negative, reopened because shorts are in scope and costs are measured), news_vs_nonews_drop_reversal (refuted: event study of >=5% drops in ADV top 1500, 12 candidates, best Sharpe 0.67; this book is a cross-sectional rank book, different estimator, the news condition is one cell group and the overlap is disclosed), no_news_price_shock_reversal_chan (harvested, monthly), etf_constituent_lead_lag_reversion and letf_close_rebalancing_flow_reversal (ETF-level, refuted, not reopened), deep_learning_stat_arb_residual (not executable then; this is its engine), end_of_day_reversal (parked, minute data, not touched), cross_sectional_gap_fade (closed one-day round trips, not touched); t20261005_p1_s0_decay (P1 Stage 0 measurement of REV5/RREV5 decay, overlapping objects, disclosed in contract.md section 0).",
    "cost_and_execution_assumptions": "Decision at the close of t; trade at the open of t+1 (close of t+1 robustness only) through backtest.run_book; costfn.make_cost_fn (cost_model_v1 half spread by price/ADV/vol/year plus square-root impact at actual dollars of a 300,000 USD sub-account, 0.5 bp fees); borrow 25 bp a year (100 bp stress) on shorts in the easy-to-borrow proxy only; 0.5x/1x/2x cost scaling; ADV participation reported and flagged above 1%.",
    "stop_condition": "Stage A (24 main cells, recent window) is the decisive cheap test: if no cell has gross Sharpe above 0.3 the family is closed at this depth; a negative verdict needs all five depth conditions (reproduction, faithful implementation, three-point scale curves, full preregistered budget, adequate power), otherwise the verdict is 'not at depth' with the missing item. Compute stop: 48 hours from 2026-10-06 22:41 UTC, Modal cap 4 USD.",
    "cheapest_decisive_test": {
        "action": "Stage A: full run_book engine over 2024-01-08..2026-09-15 for the 24 main cells (4 robustness and 2 model cells follow on the selected spec), gross, cost components and net per cell; first batch L=5, H=5, three universes, industry and PCA residuals within 24 hours.",
        "pass_condition": "At least one cell reaches recent net Sharpe above 0 at 1x cost and the 2x-cost net is above half of it; then Stage B scoring with scorecard_v2 (DSR >= 0.70 with N = 24, net placebo >= 0.90, robustness >= 3, no veto) for P1.",
        "falsification_condition": "Every cell has recent gross Sharpe < 0.3 or net Sharpe <= 0 at 1x cost with consistent sign across universes and executions, and the five depth conditions are met: then the family is not viable at this depth.",
        "max_compute_minutes": 1440,
    },
    "queries": queries,
    "sources": sources,
}
(D / "direction-review.json").write_text(json.dumps(dr, indent=1, ensure_ascii=False) + "\n")
eb = json.loads((D / "external-brief.json").read_text())
eb["mechanism_family"] = "short_horizon_residual_reversal_statarb"
eb["mechanism_description"] = (
    "Daily cross-sectional reversal of 1-21 session residual returns (beta, industry, PCA residuals), long the biggest residual losers and short the biggest residual winners among liquid US stocks, held 1-10 sessions as overlapping batches, dollar neutral with a SPY beta hedge."
)
(D / "external-brief.json").write_text(json.dumps(eb, indent=1, ensure_ascii=False) + "\n")
