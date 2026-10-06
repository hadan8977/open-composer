"""Build the preregistration dossier of t20261006_p1_v12_small (T-20261005-37).

Written by the 10-06 01:07 lead round.  Writes the source cards, the lightweight-iteration
config (then run ``scripts/new_lightweight_iteration.py``) and ``direction-review.json``.

    uv run python reports/research/iterations/t20261006_p1_v12_small/build_dossier.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ITER = "t20261006_p1_v12_small"
IDIR = ROOT / "reports/research/iterations" / ITER
SNAP = "reports/research/intel/sources/p1-v12-small-2026-10-06"
CARDS = f"reports/harness/source_cards/{ITER}.jsonl"
SPEC = f"strategy_specs/drafts/{ITER}.yaml"
FETCHED = {  # from SNAP/fetch-log.txt (curl, HTTP 200)
    "alpaca-fractional-trading.md": "2026-10-06T01:31:05Z",
    "alpaca-paper-trading.md": "2026-10-06T01:31:05Z",
    "alpaca-margin-short.md": "2026-10-06T01:31:06Z",
    "repec-blitz-2020-drop-shorts.html": "2026-10-06T01:31:07Z",
    "repec-clarke-2002-tc.html": "2026-10-06T01:31:07Z",
}
URL = {
    "alpaca-fractional-trading.md": "https://docs.alpaca.markets/docs/fractional-trading.md",
    "alpaca-paper-trading.md": "https://docs.alpaca.markets/docs/paper-trading.md",
    "alpaca-margin-short.md": "https://docs.alpaca.markets/docs/margin-and-short-selling.md",
    "repec-blitz-2020-drop-shorts.html": "https://ideas.repec.org/a/taf/ufajxx/v76y2020i4p73-99.html",
    "repec-clarke-2002-tc.html": "https://ideas.repec.org/a/taf/ufajxx/v58y2002i5p48-66.html",
}

CARDED = [
    {
        "claim_id": "alpaca_2026_fractional_day_only",
        "file": "alpaca-fractional-trading.md",
        "source_type": "broker_official_docs",
        "quote": "Alpaca currently supports fractional trading for market, limit, stop & stop limit orders with a time in force=Day, accommodating both fractional quantities and notional values.",
        "claim": "Alpaca fractional orders are supported for market, limit, stop and stop limit orders with time in force Day only, so fractional longs cannot use the opening or closing auction (opg/cls).",
        "market_and_period": "Alpaca US equities Trading API, documentation fetched 2026-10-06",
        "applicability": "Forces the small-capital book to trade its fractional long leg with DAY orders; the contract therefore trades the whole book as DAY orders around 15:50 ET.",
        "limitations": "Documentation, not a fill study; says nothing about fill quality at 15:50.",
        "independent_replication": "Same rule in the 2026-10-05 snapshot of the research agent (I-20261005-01) and in T-71 rules_checked (2026-10-05).",
    },
    {
        "claim_id": "alpaca_2026_fractional_no_short",
        "file": "alpaca-fractional-trading.md",
        "source_type": "broker_official_docs",
        "quote": "We do not support short sales in fractional orders.",
        "claim": "Alpaca does not support short sales in fractional orders, so every short position must be a whole number of shares.",
        "market_and_period": "Alpaca US equities Trading API, documentation fetched 2026-10-06",
        "applicability": "The reason the 1,784-name v1.2 short leg rounds to zero shares for most names at $50,000 (T-71) and the reason for the top-K concentration.",
        "limitations": "Documentation only.",
        "independent_replication": "T-71 rules_checked 2026-10-05 (fractional_short: not supported).",
    },
    {
        "claim_id": "alpaca_2026_paper_nbbo_matching",
        "file": "alpaca-paper-trading.md",
        "source_type": "broker_official_docs",
        "quote": "all orders submitted in paper trading will be matched against the best available current market price (NBBO).",
        "claim": "Alpaca paper trading matches every order against the current NBBO (the same page states random partial fills 10% of the time and no NBBO depth check), so paper cannot reproduce auction fills.",
        "market_and_period": "Alpaca paper trading, documentation fetched 2026-10-06",
        "applicability": "A 15:50 DAY-order book is executed the same way on paper and live (quote-based), unlike auction orders; the 10-15 paper account can test the chosen execution path.",
        "limitations": "Paper ignores depth and borrow fees; partial fills are random, not market-driven.",
        "independent_replication": "Alpaca staff forum answers on paper MOO/CLS fills (forum 19155, snapshots in small-capital-ls-2026-10-07 and T-20261005-02).",
    },
    {
        "claim_id": "alpaca_2026_short_min_equity_2000",
        "file": "alpaca-margin-short.md",
        "source_type": "broker_official_docs",
        "quote": "In order to trade on margin or sell short, you must have $2,000 or more account equity.",
        "claim": "Alpaca requires at least $2,000 of account equity to trade on margin or sell short.",
        "market_and_period": "Alpaca margin and short selling documentation, fetched 2026-10-06",
        "applicability": "Not binding at the $25,000-$100,000 tiers of this contract; recorded so the minimum-capital answer is complete.",
        "limitations": "Documentation only.",
        "independent_replication": "T-71 rules (short_min_equity $2,000).",
    },
    {
        "claim_id": "alpaca_2026_etb_zero_fee",
        "file": "alpaca-margin-short.md",
        "source_type": "broker_official_docs",
        "quote": "Alpaca offers 5,000+ ETB (Easy-to-Borrow) securities that are approved for locates with zero fees.",
        "claim": "Alpaca offers more than 5,000 easy-to-borrow securities approved for locates with zero fees, so ETB shorts carry no borrow fee.",
        "market_and_period": "Alpaca margin and short selling documentation, fetched 2026-10-06",
        "applicability": "Main borrow cost 0 bp for the ETB-restricted short leg (v1.2 convention), 25 bp sensitivity kept.",
        "limitations": "ETB status changes daily; our ETB proxy (D7, precision 0.985) is not the broker list.",
        "independent_replication": "v1.2 contract (borrow 0 bp main) and T-71 (ETB live $0).",
    },
    {
        "claim_id": "blitz_baltussen_vanvliet_2020_drop_shorts",
        "file": "repec-blitz-2020-drop-shorts.html",
        "source_type": "paper",
        "quote": "we found that (1) most added value comes from the long legs, (2) the long legs offer more diversification than the short legs, and (3) the performance of the short legs is generally subsumed by that of the long legs.",
        "claim": "Blitz, Baltussen and van Vliet (Financial Analysts Journal 76(4), 2020): most factor value comes from the long legs, long legs diversify more than short legs, and short-leg performance is generally subsumed by the long legs.",
        "market_and_period": "US and international equity factor portfolios, multi-decade samples (abstract)",
        "applicability": "Basis of candidate R3 (drop the short stock leg, hedge its beta with SPY); R1 must beat R3 to justify whole-share shorts at small capital.",
        "limitations": "Abstract only; factor portfolios, not our composite; ignores short-implementation costs that would favour R3 further.",
        "independent_replication": "Not checked; Robeco authors disclose a commercial interest in long-only factor products.",
    },
    {
        "claim_id": "clarke_desilva_thorley_2002_constraints_transfer",
        "file": "repec-clarke-2002-tc.html",
        "source_type": "paper",
        "quote": "Constraints on short positions and turnover, for example, are fairly common and materially restrictive.",
        "claim": "Clarke, de Silva and Thorley (Financial Analysts Journal 58(5), 2002): constraints on short positions and turnover are common and materially restrictive; the generalized fundamental law splits performance into forecast skill and constraint noise (transfer coefficient).",
        "market_and_period": "Theory plus Monte Carlo (abstract)",
        "applicability": "Frames the expected Sharpe loss of the whole-share and concentration constraints; measured here with return-based retention and tracking error, not weight correlation (I-20261005-01 probe: weight correlation 0.999 is uninformative).",
        "limitations": "Abstract only; the 0.73 / 0.3 transfer coefficients come from press coverage, not the paper text read here.",
        "independent_replication": "Transfer-coefficient framework widely used (Grinold-Kahn; State Street per Institutional Investor 2002).",
    },
]

EXTRA = [  # read by the research agent on 2026-10-05 (I-20261005-01), not carded here
    {
        "claim_id": "clarke_desilva_sapra_thorley_2008_extensions",
        "url": "https://rpc.cfainstitute.org/en/research/financial-analysts-journal/2008/longshort-extensions-how-much-is-enough",
        "source_type": "paper",
        "credibility": "medium",
        "core_claim": "Long-short extension (130/30-type) portfolios relax the long-only constraint; the benefit depends on how much shorting is allowed (FAJ 64(1), 2008, abstract).",
        "project_applicability": "F2 is a SPY core plus overlay; index-relative underweights are the extension view of its short leg.",
        "reflection": "Index-relative underweights need point-in-time index weights we do not have; recorded as not done.",
    },
    {
        "claim_id": "benidis_feng_palomar_2018_sparse_tracking",
        "url": "https://palomar.home.ece.ust.hk/papers/2018/BenidisFengPalomar-TSP2018%20-%20index_tracking.pdf",
        "source_type": "paper",
        "credibility": "medium",
        "core_claim": "Sparse index tracking by majorization-minimization selects names and weights jointly with tracking comparable to or better than benchmarks at far lower run time (IEEE TSP 66(1), 2018, abstract and introduction).",
        "project_applicability": "Named follow-up if R1 fails retention: a sparse tracking optimizer instead of a top-K cut.",
        "reflection": "GPL R package; long-only index tracking; would need a re-implementation for long-short.",
    },
    {
        "claim_id": "nepc_2025_extension_strategies",
        "url": "https://nepc.com/wp-content/uploads/2025/04/Extension-Strategies-Come-Into-Their-Own.pdf",
        "source_type": "practitioner_report",
        "credibility": "low",
        "core_claim": "Median extension strategies beat median long-only strategies on rolling three-year net returns in eVestment data (NEPC, April 2025).",
        "project_applicability": "Industry context for keeping a short leg; not small-account evidence.",
        "reflection": "Consultant survey, survivorship and selection unknown.",
    },
    {
        "claim_id": "pypfopt_discrete_allocation_long_short",
        "url": "https://pyportfolioopt.readthedocs.io/en/latest/Postprocessing.html",
        "source_type": "provider_official_docs",
        "credibility": "medium",
        "core_claim": "PyPortfolioOpt's DiscreteAllocation rounds continuous weights to whole shares greedily or by integer programming and splits long and short books before allocating.",
        "project_applicability": "Same split as R1 (shorts rounded on their own); confirms the two-step approach is the common open-source practice.",
        "reflection": "Does not select names, so it does not solve sub-one-share short targets.",
    },
    {
        "claim_id": "smartleaf_direct_index_small_accounts",
        "url": "https://www.thewealthadvisor.com/article/smartleaf-asset-management-yes-direct-indexes-make-sense-investors-worth-less-1m-and-over",
        "source_type": "vendor_article",
        "credibility": "low",
        "core_claim": "Whole-share rounding zeroes small weights and creates tracking error; the vendor says the problem binds below about $50,000 for US large-cap accounts.",
        "project_applicability": "Order of magnitude consistent with T-71; vendor claim, not used as evidence.",
        "reflection": "Long-only direct indexing, not long-short.",
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    cards = []
    sources_dr = []
    for c in CARDED:
        snap = f"{SNAP}/{c['file']}"
        digest = sha256(ROOT / snap)
        cards.append(
            {
                "accessed_at": now,
                "applies_to": str([f"dir:{ITER}", ITER]),
                "claim": c["claim"],
                "claim_id": c["claim_id"],
                "fetched_at": FETCHED[c["file"]],
                "impact_on_spec": c["applicability"],
                "independent_replication": c["independent_replication"],
                "limitations": c["limitations"],
                "published_or_updated_at": "unknown",
                "quote": c["quote"],
                "source_sha256": digest,
                "source_snapshot": snap,
                "source_type": c["source_type"],
                "source_url": URL[c["file"]],
                "status": "verified",
                "verification_method": "snapshot_text_read_by_lead_round",
                "verification_status": "opened_primary_source",
            }
        )
        sources_dr.append(
            {
                "claim_id": c["claim_id"],
                "market_and_period": c["market_and_period"],
                "limitations": c["limitations"],
                "independent_replication": c["independent_replication"],
                "url": URL[c["file"]],
                "source_type": c["source_type"],
                "published_or_updated_at": "unknown",
                "snapshot_path": snap,
                "sha256": digest,
                "source_card_path": CARDS,
                "fetched_at": FETCHED[c["file"]],
                "claim": c["claim"],
                "core_claim": c["claim"],
                "credibility": "high" if c["source_type"] == "broker_official_docs" else "medium",
                "applicability": c["applicability"],
            }
        )
    (ROOT / CARDS).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / CARDS).write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards))

    brief_sources = [
        {
            "claim_id": s["claim_id"],
            "url": s["url"],
            "published_or_updated_at": "unknown",
            "source_type": s["source_type"],
            "credibility": s["credibility"],
            "core_claim": s["claim"],
            "project_applicability": s["applicability"],
            "reflection": s["limitations"],
        }
        for s in sources_dr
    ] + [dict(e, published_or_updated_at="unknown") for e in EXTRA]

    candidates = []
    for form in ("F1", "F2"):
        for k in (50, 100, 200, 300, "all"):
            candidates.append(
                {
                    "candidate_id": f"{form}_R1_K{k}",
                    "parameters": {"form": form, "method": "R1", "k_per_side": k, "capital": 50000},
                }
            )
        for k in (100, 200):
            candidates.append(
                {
                    "candidate_id": f"{form}_R1B_K{k}",
                    "parameters": {
                        "form": form,
                        "method": "R1B",
                        "k_per_side": k,
                        "replacement_hurdle": 0.25,
                        "capital": 50000,
                    },
                }
            )
        candidates.append(
            {
                "candidate_id": f"{form}_R3",
                "parameters": {"form": form, "method": "R3", "k_per_side": "all", "capital": 50000},
            }
        )
    config = {
        "iter_id": ITER,
        "strategy_name": ITER,
        "representative_spec_path": SPEC,
        "path_name": "v12_small_capital_construction",
        "hypothesis_id": "T-20261005-37",
        "objective": (
            "v1.2 small-capital construction: can the unchanged v1.2 M0_U3000 book run in a "
            "$50,000 Alpaca account (fractional DAY-order longs, whole-share ETB shorts) and keep "
            ">= 0.80 of the full $1M account's recent Sharpe (F1 excess over BIL, F2 information "
            "ratio over SPY), with V2 feasibility, by concentrating to the top-K names per side "
            "(R1, R1B) or by dropping the short stock leg (R3)?"
        ),
        "benchmark_family": [
            "full_v12_account_1m_A1_M0_U3000_identity",
            "r0_k_all_no_concentration_same_capital",
            "r3_drop_short_leg_spy_beta_hedge",
            "random_name_placebo_same_k_20_seeds",
            "two_x_cost_same_path",
            "cash_proxy_bil_and_spy_for_f2",
        ],
        "candidates": candidates,
        "cost_table": {
            "base_cost_bps": "make_cost_fn('close') at the tier's own notional (half-spread from D4 15:45 NBBO samples, square-root impact, 0.5 bp fees); borrow 0 bp ETB",
            "stress_cost_bps": "2x trading cost on the same path plus 25 bp borrow on short notional",
        },
        "sources": brief_sources,
        "topic_coverage": [
            "small_account_whole_share_rounding_feasibility",
            "cardinality_constrained_portfolio_concentration",
            "long_leg_versus_short_leg_factor_value",
            "constraint_cost_transfer_coefficient",
            "broker_fractional_and_short_sale_rules",
            "paper_simulator_fill_realism",
            "sharpe_difference_inference_low_power",
            "index_relative_underweight_extension",
        ],
        "hypothesis": {
            "statement": (
                "Concentrating each side of the v1.2 book to its top-K names (K* = the largest K "
                "that is whole-share feasible at $50,000) keeps at least 0.80 of the full "
                "account's recent Sharpe, because the target weights are concentrated in the "
                "largest names and the dropped tail carries little of the composite's edge."
            ),
            "failure_mode": (
                "The edge sits in the many small positions (breadth), so retention falls below "
                "0.80; or the K boundary churns and costs eat the edge; or the short leg adds "
                "nothing over R3."
            ),
            "measurement": (
                "Sharpe retention vs the $1M A1 account in the recent window 2024-01-08..2026-09-15 "
                "(stress 2017-10-02..2023-08-31 reported), V2 feasibility per session, tracking "
                "error vs the full account, 20-seed random-name placebo, 2x cost, 36-series DSR."
            ),
            "stop_pivot": (
                "No deployable config at $50,000: report the minimum tier ($100,000 or above), "
                "keep the ETF pilot as the live path, and the next step is a sparse tracking "
                "optimizer or exact whole-share MILP (not a refutation of v1.2)."
            ),
        },
        "decision": {
            "path": "v12_small_capital_construction",
            "decision": "pending",
            "reason": "Preregistered 2026-10-06 01:07 lead round before any small-capital return series.",
            "next_iteration_suggestion": "Production target generator for the small account and a 10-15 paper start if a config is deployable and the owner approves the account.",
        },
        "source_cards_path": CARDS,
    }
    cfg_path = IDIR / "lightweight-config.json"
    cfg_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    proc = subprocess.run(
        [sys.executable, "scripts/new_lightweight_iteration.py", str(cfg_path), "--overwrite"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    print(proc.stdout[-1500:], proc.stderr[-1500:])

    review = {
        "schema_version": 1,
        "iter_id": ITER,
        "reviewed_at": now,
        "decision": "proceed",
        "objective": config["objective"],
        "target_regime_and_horizon": (
            "US equities, the v1.2 M0_U3000 book (weekly 5 tranches, decision at close D, fill "
            "at close D+1), account simulation 2017-10-02..2026-09-15; recent window "
            "2024-01-08..2026-09-15 decides, stress window 2017-10-02..2023-08-31 is reported and "
            "used only as a crash diagnostic (stress retention >= 0.60 for the same_strategy "
            "class). Deployment horizon: the owner's extra paper account from 2026-10-15."
        ),
        "existing_solution_comparison": (
            "Practice for small accounts is to round long and short books separately "
            "(PyPortfolioOpt DiscreteAllocation) or to hold fewer names (direct-index vendors, "
            "150-300 names); exact cardinality MIQPs do not scale (Murray-Shek 2012, read by "
            "I-20261005-01). Nobody publishes a verified small long-short account record "
            "(I-20261005-01 evidence tier 0). Our own T-71 measured only one day's rounding "
            "feasibility (top-200 per side passes V2 at $50,000, top-300 fails), not the Sharpe "
            "cost, which is what this contract measures."
        ),
        "remaining_evidence_gap": (
            "(1) Sharpe retention and tracking error of the concentrated book over 2017-2026 at "
            "$25k/$50k/$100k; (2) whether the short leg earns its whole-share cost (R1 vs R3); "
            "(3) whether top-K by weight beats random K names (placebo); (4) turnover and order "
            "counts of a 15:50 DAY-order book at small capital."
        ),
        "negative_experiments_checked": (
            "Registry check 'small capital concentrated top-N long short whole share fractional' "
            "found no duplicate (best match 0.44, unrelated). Local: v1 Stage 2a and RF1 "
            "refuted on construction (t20261001_book_v1 decision record), so this contract "
            "changes only capital, rounding and name count of the v1.2 construction that reached "
            "P1; v1.3 kept full rebalancing (no-trade bands failed E3), so the trading rule "
            "stays full rebalancing; T-19 pure price long-only books failed, so R3 keeps the "
            "v1.2 composite, not a price signal."
        ),
        "cost_and_execution_assumptions": (
            "Whole book as DAY orders around 15:50 ET (fractional longs cannot use opg/cls; "
            "paper matches at the NBBO), backtest fill at the close of D+1 with "
            "make_cost_fn('close') at the tier's own notional (D4 15:45 half-spreads, "
            "square-root impact, 0.5 bp fees); ETB shorts only, borrow 0 bp main and 25 bp "
            "sensitivity; 2x trading cost on the same path; Reg T and Alpaca maintenance "
            "margin as in the v1.2 account layer; long orders below $1 dropped (Alpaca minimum), "
            "short orders in whole shares."
        ),
        "stop_condition": (
            "Measurement with a mechanical classification (hypotheses.md section 9): "
            "same_strategy / related_strategy / not_deployable per form at $50,000, plus the "
            "minimum capital tier. Identity failure (I1 or I2) stops the run with status "
            "identity_failed. Not deployable is 'not at depth', never a refutation of v1.2."
        ),
        "cheapest_decisive_test": {
            "action": (
                "Brief T-20261005-37: identity I1/I2, then one local pass of 76 simulated "
                "accounts (16 candidates at $50k, 20 tier-sensitivity series, 40 placebo "
                "series), evaluation and classification."
            ),
            "pass_condition": (
                "A form has a deployable config at $50,000: V2 feasibility, recent Sharpe "
                "retention >= 0.80 of the $1M account, 2x-cost recent excess return > 0 "
                "(same_strategy additionally TE <= 0.25 x vol and stress retention >= 0.60; "
                "related_strategy needs its own DSR >= 0.70 and placebo percentile >= 0.80)."
            ),
            "falsification_condition": (
                "No config keeps 0.80 of the recent Sharpe at $50,000 for either form: v1.2 is "
                "not deployable at the owner's capital with top-K concentration; report the "
                "minimum tier and move to the named follow-up."
            ),
            "max_compute_minutes": 360,
        },
        "queries": [
            {
                "query": "direct fetch of the primary pages behind I-20261005-01 (Alpaca fractional, paper, margin/short docs; RePEc abstracts of Blitz-Baltussen-van Vliet 2020 and Clarke-de Silva-Thorley 2002)",
                "searched_at": "2026-10-06T01:31:00Z",
                "opened_urls": [URL[f] for f in URL],
                "note": f"curl, HTTP 200, snapshots and fetch log in {SNAP}/",
            },
            {
                "query": "reuse: I-20261005-01 small-capital long-short research (T-20261005-36a, 2026-10-05), snapshots in reports/research/intel/sources/small-capital-ls-2026-10-07/",
                "searched_at": "2026-10-05T07:21:00Z",
                "opened_urls": [e["url"] for e in EXTRA],
                "note": "Read by the research agent on 2026-10-05; used in the external brief only, not carded here.",
            },
        ],
        "sources": sources_dr,
    }
    (IDIR / "direction-review.json").write_text(
        json.dumps(review, indent=2, ensure_ascii=False) + "\n"
    )
    print("wrote", CARDS, "and direction-review.json at", now)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
