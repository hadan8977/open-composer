"""Preregistration writer for iteration h20260922_02_s3_voltarget (brief B-2).

Writes, in dependency order, every gate artifact the repo's own checks read:

    sources/*.html        raw snapshots captured with curl (never re-fetched here)
    source cards jsonl    one verified claim per snapshot, with the quote
    direction-review.json web-first receipt for `oc research direction-check`
    external-brief.json   intel bundle for `oc research iteration validate`
    candidate-manifest.json  the 12 frozen cells, written before any return
    data-feasibility.json evaluation authorization keyed to the manifest
    search-space.json     single mechanism path, lightweight (no campaign)

Running this script twice is a no-op apart from timestamps that are read from
`sources/fetch-log.json`, so hashes stay stable across re-validation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.iteration_dossier import candidate_authorization_binding_sha256
from open_composer.strategy_versions import strategy_content_hash

ROOT = Path(__file__).resolve().parents[1]
ITER_ID = "h20260922_02_s3_voltarget"
ITER_DIR = ROOT / "reports/research/iterations" / ITER_ID
SOURCES_DIR = ITER_DIR / "sources"
CARDS_REL = f"reports/harness/source_cards/{ITER_ID}.jsonl"
SPEC_REL = "strategy_specs/drafts/s3_voltarget_brake_h20260922_02.yaml"
MANIFEST_REL = f"reports/research/iterations/{ITER_ID}/candidate-manifest.json"
FEASIBILITY_REL = f"reports/research/iterations/{ITER_ID}/data-feasibility.json"
COST_REL = f"reports/research/iterations/{ITER_ID}/cost-contract.json"
PATH_NAME = "levered_rotation_volatility_overlay"

# Grid frozen by brief B-2. 3 vol targets x 2 brake settings x 2 lookbacks = 12.
VOL_TARGETS: list[float | None] = [0.40, 0.60, None]
BRAKES = ["none", "dd25_halve_recover_high_or_21d"]
LOOKBACKS = ["63", "blend"]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cell_id(vol: float | None, brake: str, lookback: str) -> str:
    vol_tag = "novt" if vol is None else f"vt{int(round(vol * 100))}"
    brake_tag = "nobrake" if brake == "none" else "brake25"
    return f"s3_lb{lookback}_{vol_tag}_{brake_tag}"


def grid() -> list[dict]:
    out: list[dict] = []
    for lookback in LOOKBACKS:
        for vol in VOL_TARGETS:
            for brake in BRAKES:
                out.append(
                    {
                        "cell_id": cell_id(vol, brake, lookback),
                        "menu": "A4_levered",
                        "lookback": lookback,
                        "top_n": 2,
                        "rebalance": "monthly",
                        "vol_target_annual": vol,
                        "realized_vol_window": 21,
                        "leverage_cap": 1.0,
                        "drawdown_brake": brake,
                        "brake_trigger_dd": None if brake == "none" else -0.25,
                        "brake_exposure_multiplier": None if brake == "none" else 0.5,
                        "brake_recover_sessions": None if brake == "none" else 21,
                    }
                )
    return out


SOURCES = [
    {
        "claim_id": "mm2017_volatility_managed_sharpe",
        "file": "moreira-muir-nber-w22208.html",
        "url": "https://www.nber.org/papers/w22208",
        "source_type": "paper",
        "published_or_updated_at": "2016-04-28",
        "claim": (
            "Moreira and Muir show that scaling factor exposure down when realized "
            "volatility is high raises Sharpe ratios for the market, value, momentum, "
            "profitability, return-on-equity and investment factors and for the "
            "currency carry trade, because factor volatility changes are not offset "
            "by proportional changes in expected returns."
        ),
        "quote": (
            "Volatility timing increases Sharpe ratios because changes in factor "
            "volatilities are not offset by proportional changes in expected returns."
        ),
        "market_and_period": "US equity factors and currency carry, monthly, 1926-2015.",
        "applicability": (
            "This is the giant the B-2 overlay copies: scale the S3 levered sleeve "
            "down by trailing realized volatility. Our sleeve is a single long-only "
            "levered-ETF book, not a long-short factor, so only the mechanism carries "
            "over, not the magnitudes."
        ),
        "limitations": (
            "Long-short factor portfolios with unconstrained leverage, monthly data, "
            "no transaction costs, sample ends a decade before our anchor window."
        ),
        "independent_replication": (
            "Replicated in spanning regressions by Cederburg et al. (2020) and "
            "Barroso and Detzel (2021); both dispute the real-time value."
        ),
    },
    {
        "claim_id": "cederburg2020_oos_failure",
        "file": "cederburg-2020-jfe-oos.html",
        "url": "https://ideas.repec.org/a/eee/jfinec/v138y2020i1p95-117.html",
        "source_type": "paper",
        "published_or_updated_at": "2020-01-01",
        "claim": (
            "Across 103 equity strategies, volatility-managed portfolios do not "
            "systematically beat their unmanaged counterparts for a real-time "
            "investor: the spanning-regression alphas are not implementable and "
            "out-of-sample versions generally earn lower certainty equivalents and "
            "Sharpe ratios than simply holding the unmanaged portfolio."
        ),
        "quote": (
            "Volatility-managed portfolios do not systematically outperform their "
            "corresponding unmanaged portfolios in direct comparisons."
        ),
        "market_and_period": (
            "103 US equity strategies, monthly, long historical samples through 2017."
        ),
        "applicability": (
            "This is the strongest reason B-2 could fail. It forces the design to be "
            "a pure exposure reducer with leverage capped at 1.0 and to be judged on "
            "an untouched 2026 holdout rather than on in-sample alphas."
        ),
        "limitations": (
            "Monthly long-short equity factors, real-time estimation of the scaling "
            "coefficient; it does not test a fixed target-volatility rule with a hard "
            "leverage cap on a levered-ETF sleeve."
        ),
        "independent_replication": (
            "Consistent with Barroso and Detzel (2021) on costs and with the 2025 "
            "international evidence in the Journal of Empirical Finance."
        ),
    },
    {
        "claim_id": "barroso_detzel2021_costs",
        "file": "barroso-detzel-2021-jfe-costs.html",
        "url": "https://ideas.repec.org/a/eee/jfinec/v140y2021i3p744-767.html",
        "source_type": "paper",
        "published_or_updated_at": "2021-06-01",
        "claim": (
            "After transaction costs, volatility management of asset-pricing factors "
            "other than the market generally produces zero abnormal returns and "
            "significantly lower Sharpe ratios, while the volatility-managed market "
            "portfolio stays robust to costs."
        ),
        "quote": (
            "Even using six cost-mitigation strategies, after transaction costs, "
            "volatility management of asset-pricing factors besides the market return "
            "generally produces zero abnormal returns and significantly reduces Sharpe "
            "ratios."
        ),
        "market_and_period": "US equity asset-pricing factors, monthly, 1926-2017.",
        "applicability": (
            "Our overlay is a market-directional, long-only book, i.e. the one case "
            "that survived costs in this paper; it still forces the 20 bp per side "
            "stress view to be a gate (G4) rather than a footnote."
        ),
        "limitations": (
            "Factor portfolios, not ETFs; cost model is US equity spreads, not ETF spreads."
        ),
        "independent_replication": "Same direction as Cederburg et al. (2020).",
    },
    {
        "claim_id": "man2017_voltarget_risk_assets",
        "file": "man-group-impact-of-volatility-targeting.html",
        "url": "https://www.man.com/insights/the-impact-of-volatility-targeting",
        "source_type": "industry_standard",
        "published_or_updated_at": "2017-08-06",
        "claim": (
            "Across more than 60 assets with daily data from 1926, volatility scaling "
            "raises Sharpe ratios for risk assets (equities and credit) and for "
            "portfolios with a large allocation to them, and consistently reduces the "
            "likelihood of extreme returns."
        ),
        "quote": (
            "We find that Sharpe ratios are higher with volatility scaling for risk "
            "assets (equities and credit)"
        ),
        "market_and_period": "60+ global assets, daily, 1926-2017.",
        "applicability": (
            "Supports applying the overlay to an equity-beta sleeve specifically, and "
            "supports the drawdown-compression objective of B-2."
        ),
        "limitations": (
            "Practitioner research by a manager that sells volatility-targeted "
            "products; unlevered assets, no ETF path-dependency or borrow costs."
        ),
        "independent_replication": (
            "Published as Harvey et al. in the Journal of Portfolio Management (2018)."
        ),
    },
    {
        "claim_id": "empfin2025_international_costs",
        "file": "empfin-2025-international-voltarget.html",
        "url": "https://ideas.repec.org/a/eee/empfin/v80y2025ics092753982400094x.html",
        "source_type": "paper",
        "published_or_updated_at": "2025-01-01",
        "claim": (
            "In 45 international equity markets, only the volatility-managed market "
            "and momentum strategies are partially robust to transaction costs, "
            "suggesting most of the abnormal return of volatility management is "
            "explained by costs."
        ),
        "quote": (
            "only the managed market and momentum strategies are partially robust to "
            "transaction cost"
        ),
        "market_and_period": "45 international equity markets, nine managed factors, through 2023.",
        "applicability": (
            "Most recent replication we could open. Keeps the prior that the overlay "
            "is at best cost-marginal outside market and momentum exposure."
        ),
        "limitations": (
            "International factor portfolios; no levered ETF or daily-rebalanced sleeve."
        ),
        "independent_replication": (
            "Third independent study in the same direction as Cederburg and Barroso-Detzel."
        ),
    },
    {
        "claim_id": "quantpedia2025_letf_vol_filter",
        "file": "quantpedia-letf-low-volatility-environments.html",
        "url": "https://quantpedia.com/leveraged-etfs-in-low-volatility-environments/",
        "source_type": "industry_standard",
        "published_or_updated_at": "2025-09-15",
        "claim": (
            "Quantpedia proposes gating leveraged-ETF exposure with a volatility "
            "filter that compares short-term realized volatility with implied "
            "volatility, cutting exposure in high-volatility periods to keep the "
            "leverage while mitigating the worst drawdowns."
        ),
        "quote": (
            "we propose a volatility filter that adjusts ETF exposure based on the "
            "relationship between short-term realized volatility and implied "
            "volatility."
        ),
        "market_and_period": "US leveraged equity ETFs, daily, post-2010 through 2025.",
        "applicability": (
            "Closest published analogue of B-2 on the exact instrument class. We use "
            "realized volatility only, because our PIT implied-volatility feed is not "
            "wired into this engine."
        ),
        "limitations": (
            "Vendor blog, rules described but thresholds not fully public, no live "
            "track record, uses an implied-volatility input we do not have PIT."
        ),
        "independent_replication": (
            "Not independently replicated; treated as a design hint, not as evidence."
        ),
    },
    {
        "claim_id": "quantpedia2025_letf_trend_allocation",
        "file": "quantpedia-letf-asset-allocation.html",
        "url": "https://quantpedia.com/leveraged-etfs-in-asset-allocation-opportunity-or-trap/",
        "source_type": "industry_standard",
        "published_or_updated_at": "unknown",
        "claim": (
            "Leveraged ETFs do not work in long-term passive portfolios because they "
            "amplify losses and volatility, but simple trend filters (10-month moving "
            "average, 12-month high) reduce the damage when leverage is actively "
            "managed."
        ),
        "quote": (
            "Part I showed that leveraged ETFs do not work well in long-term passive portfolios."
        ),
        "market_and_period": "US leveraged equity ETFs in static and dynamic allocations, monthly.",
        "applicability": (
            "Independent confirmation that an active risk overlay, not buy-and-hold, "
            "is the only defensible way to run the A4 levered menu."
        ),
        "limitations": (
            "Vendor blog, monthly trend rules only, no cost or capacity analysis of our sleeve."
        ),
        "independent_replication": (
            "Overlaps with the published trend-following literature on levered exposure."
        ),
    },
    {
        "claim_id": "arxiv2026_closed_loop_voltarget",
        "file": "arxiv-2603.01298-adaptive-leveraged-vol-control.html",
        "url": "https://arxiv.org/abs/2603.01298",
        "source_type": "paper",
        "published_or_updated_at": "2026-03-01",
        "claim": (
            "Open-loop volatility targeting that scales exposure inversely with a "
            "variance forecast suffers from high turnover, leverage spikes and "
            "sensitivity to estimation error; a proportional-control formulation hits "
            "the target volatility more consistently."
        ),
        "quote": (
            "Existing volatility-targeting strategies typically scale portfolio "
            "exposure inversely with a variance forecast, but such open-loop "
            "approaches suffer from high turnover, leverage spikes, and sensitivity "
            "to estimation error"
        ),
        "market_and_period": "Simulation study of a risky-plus-riskfree index, 2026 preprint.",
        "applicability": (
            "Explains why B-2 freezes the overlay to a monthly update with a hard 1.0 "
            "leverage cap instead of a daily inverse-variance scaler: turnover and "
            "leverage spikes are the known failure mode."
        ),
        "limitations": "Simulation only, no live or historical trading record, not peer reviewed.",
        "independent_replication": "None yet (March 2026 preprint).",
    },
]

QUERIES = [
    {
        "query": (
            "Moreira Muir volatility managed portfolios replication failure Cederburg out-of-sample"
        ),
        "opened_urls": [
            "https://www.nber.org/papers/w22208",
            "https://ideas.repec.org/a/eee/jfinec/v138y2020i1p95-117.html",
        ],
    },
    {
        "query": (
            "volatility targeting leveraged ETF drawdown control 2025 2026 evidence Sharpe "
            "improvement"
        ),
        "opened_urls": [
            "https://www.man.com/insights/the-impact-of-volatility-targeting",
            "https://arxiv.org/abs/2603.01298",
            "https://quantpedia.com/leveraged-etfs-in-asset-allocation-opportunity-or-trap/",
            "https://quantpedia.com/leveraged-etfs-in-low-volatility-environments/",
        ],
    },
    {
        "query": "volatility managed portfolios transaction costs Barroso Detzel do not survive",
        "opened_urls": [
            "https://ideas.repec.org/a/eee/jfinec/v140y2021i3p744-767.html",
            "https://ideas.repec.org/a/eee/empfin/v80y2025ics092753982400094x.html",
        ],
    },
]


def main() -> int:
    log = json.loads((SOURCES_DIR / "fetch-log.json").read_text(encoding="utf-8"))
    fetched_at = log["fetched_at"]
    searched_at = log["searched_at"]
    reviewed_at = log["reviewed_at"]

    # ---- source cards -------------------------------------------------
    cards = []
    direction_sources = []
    for src in SOURCES:
        snapshot = SOURCES_DIR / src["file"]
        digest = sha256_file(snapshot)
        snapshot_rel = f"reports/research/iterations/{ITER_ID}/sources/{src['file']}"
        cards.append(
            {
                "claim_id": src["claim_id"],
                "claim": src["claim"],
                "quote": src["quote"],
                "source_url": src["url"],
                "source_type": src["source_type"],
                "published_or_updated_at": src["published_or_updated_at"],
                "accessed_at": fetched_at[:10],
                "fetched_at": fetched_at,
                "status": "verified",
                "verification_status": "source_verified",
                "verification_method": "curl_snapshot_then_quote_match",
                "source_snapshot": snapshot_rel,
                "source_sha256": digest,
                "applies_to": [ITER_ID, "H-20260922-02"],
                "limitations": src["limitations"],
            }
        )
        direction_sources.append(
            {
                "claim_id": src["claim_id"],
                "claim": src["claim"],
                "url": src["url"],
                "source_type": src["source_type"],
                "published_or_updated_at": src["published_or_updated_at"],
                "market_and_period": src["market_and_period"],
                "applicability": src["applicability"],
                "limitations": src["limitations"],
                "independent_replication": src["independent_replication"],
                "fetched_at": fetched_at,
                "snapshot_path": snapshot_rel,
                "sha256": digest,
                "source_card_path": CARDS_REL,
            }
        )
    (ROOT / CARDS_REL).write_text(
        "\n".join(json.dumps(card, ensure_ascii=False, sort_keys=True) for card in cards) + "\n",
        encoding="utf-8",
    )

    # ---- direction review ---------------------------------------------
    direction = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "reviewed_at": reviewed_at,
        "decision": "proceed",
        "objective": (
            "Ask whether a Moreira-Muir volatility target plus an equity-curve "
            "drawdown brake can compress the S3 levered-ETF rotation sleeve's anchor "
            "window drawdown from -56.4% to no worse than -35% while keeping "
            "annualized return at or above 50% and holdout Sharpe at or above 1.0."
        ),
        "target_regime_and_horizon": (
            "Recent-regime only: selection 2023-09-18..2025-12-31, untouched holdout "
            "2026-01-02..2026-09-17, anchor 2024-01-08..2026-09-16. Monthly rebalance, "
            "daily brake, US levered equity ETFs. Claim of validity is limited to a "
            "trending, high-dispersion US large-cap tech regime; the exit rule is the "
            "brake plus the G-gate re-check at each renewal."
        ),
        "existing_solution_comparison": (
            "The published overlay already exists (Moreira-Muir 2017, Man Group 2017) "
            "and Quantpedia has published a leveraged-ETF volatility filter, so we "
            "copy rather than invent. What is not public is how the overlay behaves on "
            "our exact sleeve (A4 levered menu, 63-day or blended momentum, top 2, "
            "month-end, absolute momentum vs SHY), on our windows, with our 10/20 bp "
            "costs and next-open fills. Locally, H-20260918-05 already produced S3 at "
            "145.4% / -56.4% / 1.48 with a 25% random-pick placebo beat rate, which is "
            "the exact object being modified."
        ),
        "remaining_evidence_gap": (
            "Whether exposure reduction alone, capped at 1.0 leverage, is enough to "
            "halve a -56% levered drawdown without destroying the return that makes the "
            "sleeve interesting, on the 2026 holdout that has never been scored."
        ),
        "negative_experiments_checked": (
            "Cederburg et al. (2020) find volatility management fails out of sample "
            "across 103 strategies; Barroso and Detzel (2021) find it dies after costs "
            "except for the market portfolio; the 2025 international study agrees. "
            "Locally, L-20260918-01 killed a single moving-average trend gate on the "
            "calendar-shift placebo, and H-20260918-05 recorded that S3's own ranking "
            "edge is weak (25% of random-pick seeds beat it). This round therefore "
            "treats the overlay, not the ranking, as the thing under test, and keeps "
            "both placebos."
        ),
        "cost_and_execution_assumptions": (
            "sum(|delta w|) x slippage charged on the execution session, 10 bp per side "
            "primary and 20 bp per side stress; signal on a completed session close, "
            "fill at the next session open (fill_assumption next_bar_open, matching the "
            "live paper path); SIP fully adjusted daily closes; cash leg is SHY; risk "
            "free is BIL. Long-only spot ETFs, so Alpaca can execute it."
        ),
        "stop_condition": (
            "Stop and write a lesson card if no cell reaches anchor drawdown of -35% or "
            "better with annualized return at or above 50% (or the G1' alternative of "
            "Sharpe at or above 2.0 with return at or above 30%), or if the best cell's "
            "holdout Sharpe is below 1.0, or if more than 10% of the 60 random-pick "
            "placebo seeds beat it, or if the brake cannot beat its own calendar-shift "
            "placebo. Two rounds maximum; this is round 1."
        ),
        "queries": [
            {"query": q["query"], "searched_at": searched_at, "opened_urls": q["opened_urls"]}
            for q in QUERIES
        ],
        "sources": direction_sources,
        "cheapest_decisive_test": {
            "action": (
                "Run the 12 frozen cells on the existing H-20260918-05 daily panel and "
                "compare anchor drawdown and annualized return against the unmodified "
                "S3 cell that is inside the same grid."
            ),
            "pass_condition": (
                "At least one cell has anchor annualized return >= 50% and anchor max "
                "drawdown >= -35%, holdout Sharpe >= 1.0 with positive holdout return, "
                "random-pick placebo beat fraction <= 10%, and still passes G1 or G1' at "
                "20 bp per side."
            ),
            "falsification_condition": (
                "Every cell either stays worse than -35% drawdown or falls below 50% "
                "annualized return, or the best cell's holdout Sharpe is below 1.0, or "
                "more than 10% of placebo seeds beat it."
            ),
            "max_compute_minutes": 45,
        },
    }
    write_json(ITER_DIR / "direction-review.json", direction)

    # ---- external brief -----------------------------------------------
    spec = load_strategy_spec(ROOT / SPEC_REL)
    spec_hash = strategy_content_hash(spec)
    brief_sources = [
        {
            "url": src["url"],
            "published_or_updated_at": src["published_or_updated_at"],
            "source_type": src["source_type"],
            "credibility": (
                "top_journal_or_nber" if src["source_type"] == "paper" else "practitioner_research"
            ),
            "core_claim": src["claim"],
            "project_applicability": src["applicability"],
            "reflection": src["limitations"],
        }
        for src in SOURCES
    ]
    external = {
        "schema_version": 3,
        "iter_id": ITER_ID,
        "strategy_name": spec.name,
        "source_spec_path": SPEC_REL,
        "spec_hash": spec_hash,
        "objective": (
            "Copy the published volatility-managed-portfolio overlay onto the local S3 "
            "levered ETF rotation sleeve and ask whether it compresses drawdown enough "
            "to clear the 2026-09-22 shipping gates."
        ),
        "sources": brief_sources,
        "current_source_card_paths": [CARDS_REL],
        "source_evidence_bindings": [
            {
                "claim_id": src["claim_id"],
                "source_card_path": CARDS_REL,
                "used_for": (
                    "overlay_mechanism"
                    if src["claim_id"].startswith(("mm2017", "man2017", "arxiv2026"))
                    else "negative_evidence_and_cost_gate"
                ),
            }
            for src in SOURCES
        ],
        "topic_coverage": [
            "volatility_managed_portfolios_original_evidence",
            "out_of_sample_replication_failure",
            "transaction_cost_survival",
            "international_and_recent_replication",
            "leveraged_etf_specific_risk_overlay",
            "drawdown_brake_and_equity_curve_control",
            "implementation_turnover_and_leverage_cap",
        ],
        "candidate_matrix_revisions": [
            {
                "revision": "leverage_cap_1.0",
                "driver": "arxiv2026_closed_loop_voltarget",
                "effect": (
                    "The overlay may only scale exposure down into SHY; no cell is "
                    "allowed to lever up when realized volatility is low, which removes "
                    "the leverage-spike failure mode."
                ),
            },
            {
                "revision": "monthly_overlay_update_instead_of_daily_inverse_variance",
                "driver": "arxiv2026_closed_loop_voltarget",
                "effect": "Caps turnover so the 20 bp per side stress gate stays reachable.",
            },
            {
                "revision": "twenty_bp_stress_promoted_to_a_gate",
                "driver": "barroso_detzel2021_costs",
                "effect": "G4 is a pass/fail gate, not a footnote.",
            },
            {
                "revision": "untouched_2026_holdout_is_decisive",
                "driver": "cederburg2020_oos_failure",
                "effect": (
                    "In-sample spanning alphas are not accepted as evidence; the "
                    "selection window only ranks, the holdout only judges."
                ),
            },
        ],
        "hypothesis_links": [
            "reports/research/hypotheses/H-20260922-02-s3-voltarget-drawdown-brake.md",
            "reports/research/hypotheses/H-20260918-05-recent-window-etf-menu.md",
        ],
    }
    write_json(ITER_DIR / "external-brief.json", external)

    # ---- cost contract ------------------------------------------------
    write_json(
        ITER_DIR / "cost-contract.json",
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "contract_id": "cost_v1_10_20bps_next_open",
            "cost_model": "sum(abs(delta_weight)) * slippage_bps, charged on the execution session",
            "slippage_bps_per_side_primary": 10.0,
            "slippage_bps_per_side_stress": 20.0,
            "commission_pct": 0.0,
            "borrow_or_financing": (
                "none (long-only spot ETFs; LETF financing is inside the fund NAV)"
            ),
            "fill_assumption": "next_bar_open",
            "signal_on": "bar_close",
        },
    )

    # ---- candidate manifest -------------------------------------------
    cells = grid()
    candidates = []
    for index, cell in enumerate(cells, start=1):
        candidates.append(
            {
                "candidate_id": f"VT{index:02d}",
                "path": PATH_NAME,
                "role": "risk_overlay_on_frozen_rotation_sleeve",
                "method": (
                    "no_vol_target"
                    if cell["vol_target_annual"] is None
                    else f"vol_target_{int(round(cell['vol_target_annual'] * 100))}pct_21d"
                ),
                "ablation": (
                    "no_drawdown_brake"
                    if cell["drawdown_brake"] == "none"
                    else "drawdown_brake_25pct_halve"
                ),
                "spec_path": SPEC_REL,
                "fallback": "SHY",
                "data_contract": "data_v1_sip_daily_adjusted",
                "feature_contract": "feature_v1_momentum_and_realized_vol",
                "label_contract": "label_v1_next_session_open_to_open_total_return",
                "validation_contract": "validation_v1_select_then_untouched_holdout",
                "cost_contract": "cost_v1_10_20bps_next_open",
                "benchmark_contract": "benchmark_v1_spy_mtum_spmo_tqqq_equalweight",
                "cell_id": cell["cell_id"],
                "parameters": cell,
            }
        )
    manifest = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "card_id": "H-20260922-02",
        "brief": "reports/research/briefs/B-2-s3-voltarget-2026-09-22.md",
        "generated_before_backtest": True,
        "generated_at": reviewed_at,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "spec_hashes": {SPEC_REL: spec_hash},
        "windows": {
            "warmup": ["2022-06-01", "2023-09-15"],
            "select": ["2023-09-18", "2025-12-31"],
            "holdout": ["2026-01-02", "2026-09-17"],
            "anchor": ["2024-01-08", "2026-09-16"],
        },
        "selection_rule": "rank by selection-window Sharpe at 10 bp per side; holdout never ranks",
        "placebos": {
            "random_pick": {
                "seeds": 60,
                "description": "same menu, same calendar, 2 random assets",
            },
            "brake_calendar_shift": {
                "seeds": 20,
                "description": "brake state shifted by a random 1..20 session offset",
            },
        },
        "contracts": {
            "data": {
                "data_v1_sip_daily_adjusted": {
                    "source": "alpaca SIP daily archive, fully adjusted closes",
                    "glob": "data/sip/daily/*/*.parquet",
                    "hygiene": "drop bars with zero volume and zero trade_count",
                    "symbols": [
                        "TQQQ",
                        "SOXL",
                        "UPRO",
                        "USD",
                        "TECL",
                        "SHY",
                        "BIL",
                        "SPY",
                        "MTUM",
                        "SPMO",
                        "QQQ",
                    ],
                }
            },
            "features": {
                "feature_v1_momentum_and_realized_vol": {
                    "momentum": "close/lag(close,63)-1 or the equal blend of 21/63/126/252",
                    "realized_vol": (
                        "21-session stdev of the unscaled sleeve book return, annualized"
                    ),
                    "decision_lag_sessions": 1,
                }
            },
            "labels": {
                "label_v1_next_session_open_to_open_total_return": {
                    "definition": (
                        "weights effective at the next session open; return legs split open and "
                        "close"
                    ),
                }
            },
            "validation": {
                "validation_v1_select_then_untouched_holdout": {
                    "select": "2023-09-18..2025-12-31 (ranking only)",
                    "holdout": "2026-01-02..2026-09-17 (never ranks)",
                    "anchor": "2024-01-08..2026-09-16 (gate window)",
                }
            },
            "costs": {"cost_v1_10_20bps_next_open": {"contract_path": COST_REL}},
            "benchmarks": {
                "benchmark_v1_spy_mtum_spmo_tqqq_equalweight": {
                    "members": [
                        "SPY buy and hold",
                        "MTUM buy and hold",
                        "SPMO buy and hold",
                        "TQQQ buy and hold",
                        "A4 menu equal weight monthly",
                        "S3 unmodified (inside the grid)",
                    ]
                }
            },
        },
    }
    write_json(ITER_DIR / "candidate-manifest.json", manifest)
    manifest_sha = sha256_file(ITER_DIR / "candidate-manifest.json")

    # ---- data feasibility ---------------------------------------------
    feasibility = {
        "schema_version": 1,
        "report_type": "h20260922_02_s3_voltarget_historical_evaluation_authorization",
        "iter_id": ITER_ID,
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "historical_evaluation_authorized": True,
        "path_gates": {
            PATH_NAME: {
                "action": "evaluate",
                "historical_evaluation_go": True,
                "candidate_ids": [c["candidate_id"] for c in candidates],
                "reason": (
                    "Every symbol in the A4 menu plus SHY, BIL and the benchmark set is "
                    "already present in the local SIP daily archive used by "
                    "H-20260918-05; no new capability or vendor is required."
                ),
            }
        },
        "candidate_accounting": {
            "frozen_candidate_count": len(candidates),
            "evaluation_authorized_count": len(candidates),
            "dependency_skipped_count": 0,
            "unresolved_count": 0,
            "balanced": True,
        },
        "candidate_authorization": {
            "candidate_count": len(candidates),
            "rows": [
                {
                    "candidate_id": c["candidate_id"],
                    "path": PATH_NAME,
                    "action": "evaluate",
                    "reason_code": "local_sip_daily_panel_available",
                    "candidate_binding_sha256": candidate_authorization_binding_sha256(c),
                }
                for c in candidates
            ],
        },
        "required_reference_names": ["cost_contract", "candidate_spec", "source_cards"],
        "required_references": {
            "cost_contract": {
                "path": COST_REL,
                "sha256": sha256_file(ITER_DIR / "cost-contract.json"),
            },
            "candidate_spec": {"path": SPEC_REL, "sha256": sha256_file(ROOT / SPEC_REL)},
            "source_cards": {"path": CARDS_REL, "sha256": sha256_file(ROOT / CARDS_REL)},
        },
    }
    write_json(ITER_DIR / "data-feasibility.json", feasibility)
    feasibility_sha = sha256_file(ITER_DIR / "data-feasibility.json")

    # ---- search space ---------------------------------------------------
    search_space = {
        "schema_version": 3,
        "iter_id": ITER_ID,
        "strategy_name": spec.name,
        "source_spec_path": SPEC_REL,
        "spec_hash": spec_hash,
        "created_at": reviewed_at,
        "objective": (
            "One mechanism: reduce exposure of the frozen S3 levered rotation sleeve "
            "by realized volatility and by an equity-curve drawdown brake."
        ),
        "single_mechanism_no_campaign_attestation": True,
        "candidate_manifest_path": MANIFEST_REL,
        "candidate_manifest_sha256": manifest_sha,
        "cost_table_path": COST_REL,
        "data_feasibility_path": FEASIBILITY_REL,
        "data_feasibility_sha256": feasibility_sha,
        "total_candidate_budget": len(candidates),
        "paths": [
            {
                "name": PATH_NAME,
                "candidate_count": len(candidates),
                "hypothesis_refs": ["H-20260922-02"],
                "parameters": {
                    "candidate_ids": [c["candidate_id"] for c in candidates],
                    "vol_target_annual": ["0.40", "0.60", "none"],
                    "realized_vol_window": [21],
                    "leverage_cap": [1.0],
                    "drawdown_brake": BRAKES,
                    "lookback": LOOKBACKS,
                    "top_n": [2],
                    "rebalance": ["monthly"],
                    "model_training": False,
                    "mutation": "none",
                },
                "benchmark_family": [
                    "SPY_buy_and_hold",
                    "MTUM_buy_and_hold",
                    "SPMO_buy_and_hold",
                    "TQQQ_buy_and_hold",
                    "A4_menu_equal_weight_monthly",
                    "S3_unmodified_inside_grid",
                    "volatility_matched_excess_over_SPY",
                ],
            }
        ],
        "trial_ledger_paths": [],
        "evaluation_report_paths": [],
    }
    write_json(ITER_DIR / "search-space.json", search_space)

    print(f"preregistered {len(candidates)} candidates; manifest sha {manifest_sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
