"""Preregistration builder for iteration h20260922_04_rsi_branch (brief B-1).

Writes every gate artifact the `oc research direction-check` and
`oc research iteration validate` entry points read, with hashes computed from
the files on disk so nothing can silently drift:

  * reports/harness/source_cards/h20260922_04_rsi_branch.jsonl  (verified cards,
    each quote re-extracted from its own HTML snapshot at build time)
  * .../iterations/h20260922_04_rsi_branch/direction-review.json
  * .../external-brief.json, search-space.json, candidate-manifest.json,
    cost-table.json, data-feasibility.json

The 16-cell grid is frozen here, before any price is read. See
reports/research/hypotheses/H-20260922-04-rsi-branch-rotation.md section 3 for
why the published overheat threshold (80) is fixed rather than searched.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITER_ID = "h20260922_04_rsi_branch"
ITER_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
SOURCES_DIR = ITER_DIR / "sources"
CARDS_PATH = ROOT / "reports" / "harness" / "source_cards" / f"{ITER_ID}.jsonl"
SPEC_PATH = "strategy_specs/drafts/h20260922_04_rsi_branch_family.yaml"

REVIEWED_AT = "2026-09-22T03:10:00+00:00"
SEARCHED_AT = "2026-09-22T03:03:00+00:00"
FETCHED_AT = "2026-09-22T03:06:00+00:00"

RSI_REFS = ["SPY", "QQQ"]
OVERHEAT_ASSETS = ["UVXY", "BIL"]
MENUS = ["sector1x", "levered3x"]
REBALANCES = ["daily", "friday"]
PATH_NAME = "rsi_branch_sector_rotation"


def normalized_text(path: Path) -> str:
    raw = path.read_bytes().decode(errors="replace")
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", raw)).split())


def quote_between(path: Path, start: str, end: str) -> str:
    text = normalized_text(path)
    i = text.find(start)
    if i < 0:
        raise SystemExit(f"quote start not found in {path.name}: {start!r}")
    j = text.find(end, i)
    if j < 0:
        raise SystemExit(f"quote end not found in {path.name}: {end!r}")
    return text[i : j + len(end)]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, indent=2, sort_keys=True).encode()).hexdigest()


def write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def candidate_authorization_binding_sha256(candidate: dict) -> str:
    binding = dict(candidate)
    if str(binding.get("campaign_id") or "").strip():
        binding.pop("universe_contract_sha256", None)
        binding.pop("development_partition_contract_sha256", None)
    return hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# --------------------------------------------------------------------------
# 1. source cards, bound to the HTML snapshots fetched at 2026-09-22T03:05Z
# --------------------------------------------------------------------------

SNAPSHOTS = {
    "sector_rotator": SOURCES_DIR / "composer-sector-rotator-ms.html",
    "vol_minimization": SOURCES_DIR / "composer-volatility-minimization.html",
    "uvxy": SOURCES_DIR / "proshares-uvxy.html",
}

SOURCE_DEFS = [
    {
        "key": "sector_rotator",
        "claim_id": f"{ITER_ID}:composer_sector_rotator_rule_and_oos",
        "url": (
            "https://www.composer.trade/trading-strategies/"
            "sector-rotator-ms-cms-update-2025-09-08-nRUmDZa2ZGUemOBh0tdc"
        ),
        "source_type": "platform_docs",
        "published_or_updated_at": "2025-09-08",
        "claim": (
            "Composer's published Sector Rotator MS symphony states its full branch rule in "
            "plain English -- a 10-day RSI above 80 on a sector sends the book to UVXY, an RSI "
            "below 30 buys a short-term rebound in that sector, and otherwise it holds the "
            "month's strongest of the 11 US sector ETFs -- and reports an out-of-sample "
            "annualized return near 98% with Sharpe near 1.44 and max drawdown near 29%, "
            "against a 134.72% annualized / 1.7 Sharpe headline that includes in-sample history."
        ),
        "quote_anchors": (
            "Each day it scans the 11 big US stock sectors",
            "it bets on a short‑term rebound in that sector",
        ),
        "market_and_period": (
            "US sector ETFs plus leveraged sector ETFs and UVXY; page backtest starts "
            "2019-10-30 and the page was read 2026-09-22."
        ),
        "applicability": (
            "Gives the exact rule tree, the RSI window, both thresholds and the hedge asset "
            "this iteration replicates, so no parameter search is needed for them."
        ),
        "limitations": (
            "Composer's discovery page shows winners only (survivorship), the author can edit "
            "the recipe and reset the out-of-sample start, and the numbers are platform-"
            "computed, not independently audited. RSI is computed per sector in the original; "
            "this iteration's preregistered proxy computes it on SPY or QQQ."
        ),
        "independent_replication": (
            "No independent audited replication exists. This iteration is the local "
            "replication under our own windows, costs and placebos."
        ),
    },
    {
        "key": "vol_minimization",
        "claim_id": f"{ITER_ID}:composer_vol_minimization_oos",
        "url": (
            "https://www.composer.trade/trading-strategies/"
            "portfolio-experiment-volatility-minimization-olR3E8zE5wCiK7qlJ7Xj"
        ),
        "source_type": "platform_docs",
        "published_or_updated_at": "2026-09-22",
        "claim": (
            "The second instance of the same family, Composer's Portfolio Experiment: "
            "Volatility Minimization, reports an out-of-sample annualized return near 43.7% "
            "with Sharpe near 1.92 and max drawdown near 15.1%, well below its 116.11% "
            "annualized / 3.52 Sharpe headline."
        ),
        "quote_anchors": (
            "Out-of-sample edge: annualized return ~43.7%",
            "with max drawdown ~15.1% vs ~8.9%.",
        ),
        "market_and_period": (
            "127 US stocks and ETFs including TQQQ, UPRO, TECL, SOXL, UVXY, VIXY, BIL; page "
            "backtest starts 2022-04-13 and the page was read 2026-09-22."
        ),
        "applicability": (
            "Second, independent instance of the RSI-branch structure; its much lower "
            "out-of-sample number sets the honest bar this replication should be measured "
            "against, rather than the headline."
        ),
        "limitations": (
            "Same platform survivorship and recipe-reset caveats; the 127-asset universe is "
            "far wider than the preregistered 18-asset menu tested here."
        ),
        "independent_replication": "None published.",
    },
    {
        "key": "uvxy",
        "claim_id": f"{ITER_ID}:proshares_uvxy_daily_reset",
        "url": "https://www.proshares.com/our-etfs/strategic/uvxy",
        "source_type": "provider_official_docs",
        "published_or_updated_at": "unknown",
        "claim": (
            "ProShares states that UVXY targets 1.5x the daily performance of the S&P 500 VIX "
            "Short-Term Futures Index for a single day and that, because daily returns "
            "compound, holding periods longer than one day can return something significantly "
            "different from that target."
        ),
        "quote_anchors": (
            "This leveraged ProShares ETF seeks a return that is 1.5x",
            "returns that are significantly different than the target return",
        ),
        "market_and_period": "US-listed ETF, issuer page read 2026-09-22.",
        "applicability": (
            "The overheat branch holds UVXY for whole sessions, so the hedge leg's holding "
            "days and its decay are a reported diagnostic, not an assumption."
        ),
        "limitations": (
            "Issuer marketing page, not the statutory prospectus; the 1.5x multiple has "
            "changed historically, so pre-2021 UVXY bars are not the same instrument."
        ),
        "independent_replication": (
            "Daily-reset path dependence for leveraged ETFs is established in the academic "
            "literature (e.g. Avellaneda and Zhang), independent of the issuer."
        ),
    },
]


def build_source_cards() -> list[dict]:
    cards = []
    for spec in SOURCE_DEFS:
        snapshot = SNAPSHOTS[spec["key"]]
        quote = quote_between(snapshot, *spec["quote_anchors"])
        cards.append(
            {
                "claim_id": spec["claim_id"],
                "claim": spec["claim"],
                "quote": quote,
                "source_url": spec["url"],
                "source_type": spec["source_type"],
                "source_snapshot": snapshot.relative_to(ROOT).as_posix(),
                "source_sha256": sha256_file(snapshot),
                "fetched_at": FETCHED_AT,
                "accessed_at": "2026-09-22",
                "verification_status": "source_verified",
                "verification_method": "curl_snapshot_then_quote_extracted_from_that_snapshot",
                "verified_at": REVIEWED_AT,
                "iteration_id": ITER_ID,
                "applies_to": [ITER_ID, "rsi_branch_rotation_family"],
                "limitations": spec["limitations"],
            }
        )
    return cards


def build_direction_review(cards: list[dict]) -> dict:
    by_id = {card["claim_id"]: card for card in cards}
    sources = []
    for spec in SOURCE_DEFS:
        card = by_id[spec["claim_id"]]
        sources.append(
            {
                "claim": spec["claim"],
                "claim_id": spec["claim_id"],
                "url": spec["url"],
                "source_type": spec["source_type"],
                "published_or_updated_at": spec["published_or_updated_at"],
                "market_and_period": spec["market_and_period"],
                "applicability": spec["applicability"],
                "limitations": spec["limitations"],
                "independent_replication": spec["independent_replication"],
                "fetched_at": FETCHED_AT,
                "snapshot_path": card["source_snapshot"],
                "sha256": card["source_sha256"],
                "source_card_path": CARDS_PATH.relative_to(ROOT).as_posix(),
            }
        )
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "reviewed_at": REVIEWED_AT,
        "decision": "proceed",
        "objective": (
            "Replicate the Composer RSI-extreme branch family (overheat -> volatility hedge or "
            "cash, oversold -> leveraged rebound, otherwise -> last month's strongest sector) "
            "under our frozen recent-window protocol, and decide whether it clears G1-G5 or "
            "joins L-20260918-05 as a second confirmation that single-gate leveraged ETF "
            "timing does not survive placebos in this bull window."
        ),
        "target_regime_and_horizon": (
            "US ETFs, daily bars, selection window 2023-09-18..2025-12-31, untouched holdout "
            "2026-01-02..2026-09-17, anchor window 2024-01-08..2026-09-16. The claim under "
            "test is recent-regime-only; it carries an explicit exit rule and no multi-year "
            "robustness claim."
        ),
        "existing_solution_comparison": (
            "Two published instances of this exact rule family already run publicly on "
            "Composer with out-of-sample tracking (~98% annualized / Sharpe 1.44 and ~43.7% / "
            "Sharpe 1.92). Their rules, RSI window (10), overheat threshold (80) and oversold "
            "threshold (30) are disclosed in plain English on the pages, so nothing is "
            "reinvented here and no threshold search is run. What the platform does not give "
            "is a cost-aware, placebo-controlled, holdout-separated evaluation on our data, "
            "which is the only thing this iteration adds."
        ),
        "remaining_evidence_gap": (
            "Composer's discovery page shows winners only and lets authors reset the "
            "out-of-sample start after editing a recipe, so the published numbers cannot be "
            "treated as live evidence. Missing locally: whether the branch signal (not the "
            "menu and not the bull market) carries the return, whether it survives 20 bp per "
            "side at daily rebalancing turnover, and whether the UVXY hedge leg earns anything "
            "net of its 1.5x daily-reset decay."
        ),
        "negative_experiments_checked": (
            "L-20260918-05: a single moving-average gate on leveraged ETFs failed the "
            "calendar-shift placebo in this same window. H-20260918-05: the S3 leveraged menu "
            "reached 145% anchor CAGR but with a 25% placebo-beat rate, i.e. the ranking was "
            "weak evidence and the return came from leverage. This card is only reopened "
            "because it adds two elements those runs did not have -- an RSI extreme branch and "
            "a volatility hedge leg -- and it is set up so the same placebo can kill it."
        ),
        "cost_and_execution_assumptions": (
            "sum(|delta w|) * slippage charged on the execution session, 10 bp per side primary "
            "and 20 bp per side stress; signal on the close, fill at the next session's open "
            "(matching the live paper path's fill_assumption); fully adjusted SIP daily closes; "
            "long-only Alpaca-tradable US ETFs, no shorting, no options, no intraday."
        ),
        "stop_condition": (
            "Stop and write L-20260922-04 if no cell clears G1 or G1' on the anchor window, or "
            "if the surviving cell's holdout Sharpe is below 1.0, or if placebos beat the true "
            "cell more than 10% of the time, or if 20 bp per side breaks G1/G1'. One round; the "
            "brief allows at most two and the second may only use preregistered variations."
        ),
        "queries": [
            {
                "query": 'composer.trade trading-strategies "Sector Rotator MS" symphony',
                "searched_at": SEARCHED_AT,
                "opened_urls": [SOURCE_DEFS[0]["url"]],
            },
            {
                "query": (
                    'composer.trade trading-strategies "Portfolio Experiment: '
                    'Volatility Minimization"'
                ),
                "searched_at": SEARCHED_AT,
                "opened_urls": [SOURCE_DEFS[1]["url"]],
            },
            {
                "query": (
                    "ProShares UVXY Ultra VIX Short-Term Futures ETF daily rebalance decay "
                    "prospectus 2026"
                ),
                "searched_at": SEARCHED_AT,
                "opened_urls": [SOURCE_DEFS[2]["url"]],
            },
        ],
        "sources": sources,
        "cheapest_decisive_test": {
            "action": (
                "One CPU pass over 16 preregistered cells on SIP daily bars: rank on the "
                "selection window only, report the untouched holdout, then run both placebos "
                "(RSI signal calendar-shifted 1-20 sessions x 20 seeds, and random single pick "
                "from the same menu x 60 seeds) plus the 20 bp per side stress view."
            ),
            "pass_condition": (
                "At least one cell with anchor CAGR >= 50% and max drawdown <= 35% (or Sharpe "
                ">= 2.0 with CAGR >= 30%), holdout Sharpe >= 1.0 and positive, placebo beat "
                "rate <= 10%, and the same verdict still standing at 20 bp per side."
            ),
            "falsification_condition": (
                "Calendar-shifting the RSI signal does not degrade the result, or more than "
                "10% of placebo seeds match the true cell -- then the return is the menu and "
                "the bull market, the branch tree adds nothing, and the family is refuted."
            ),
            "max_compute_minutes": 45,
        },
    }


# --------------------------------------------------------------------------
# 2. external brief (schema v1: eight sources, at least three papers)
# --------------------------------------------------------------------------


def build_external_brief(spec_hash: str) -> dict:
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "generated_at": REVIEWED_AT,
        "strategy_name": "h20260922_04_rsi_branch_family",
        "source_spec_path": SPEC_PATH,
        "spec_hash": spec_hash,
        "title": "RSI-extreme branch rotation with a volatility hedge leg -- replication brief",
        "topic_coverage": [
            "published rule tree of the Composer RSI-branch symphony family",
            "out-of-sample versus headline performance reported by the platform",
            "sector/industry momentum as the normal-branch ranking mechanism",
            "cross-sectional and time-series momentum menus for the leveraged variant",
            "volatility-managed exposure as the economic story behind the overheat branch",
            "leveraged and VIX-futures ETF daily reset, decay and holding-period risk",
            "short-horizon RSI mean reversion as the oversold-branch mechanism",
            "local negative evidence on single-gate leveraged ETF timing in this window",
        ],
        "candidate_matrix_revisions": [
            (
                "Overheat threshold fixed at 80 instead of searching {80, 85}: the primary "
                "snapshot discloses 'a 10-day heat gauge (RSI) above 80', so round 1 is a "
                "replication of a published value, not a parameter search."
            ),
            ("RSI window fixed at 10 and oversold threshold at 30 for the same reason."),
            (
                "Grid cut from the brief's upper bound of 32 cells to 16: halves multiple "
                "testing and fits the 24-candidate ceiling the iteration gate imposes on a "
                "single-mechanism iteration that is not bound to a campaign contract."
            ),
            (
                "Short-volatility products (SVXY, SVIX) excluded by product category, per the "
                "brief; the overheat branch may only hold long volatility (UVXY) or cash (BIL)."
            ),
            (
                "Benchmarks extended beyond SPY/MTUM/SPMO to include the live S1 sleeve and "
                "equal-weight holdings of both menus, so 'the menu did it' is testable."
            ),
        ],
        "sources": [
            {
                "url": SOURCE_DEFS[0]["url"],
                "published_or_updated_at": "2025-09-08",
                "source_type": "platform_docs",
                "credibility": (
                    "Primary: the strategy author's own published page on the platform that "
                    "executes it. Performance is platform-computed and unaudited, and the "
                    "discovery listing is survivorship-filtered."
                ),
                "core_claim": SOURCE_DEFS[0]["claim"],
                "project_applicability": SOURCE_DEFS[0]["applicability"],
                "reflection": (
                    "The headline 134.72% is in-sample-inclusive; the honest target is the "
                    "~98% / 1.44 out-of-sample line on the same page. Our intel card copied "
                    "the headline and is corrected in H-20260922-04."
                ),
            },
            {
                "url": SOURCE_DEFS[1]["url"],
                "published_or_updated_at": "2026-09-22",
                "source_type": "platform_docs",
                "credibility": "Primary but unaudited, same platform caveats.",
                "core_claim": SOURCE_DEFS[1]["claim"],
                "project_applicability": SOURCE_DEFS[1]["applicability"],
                "reflection": (
                    "Two instances of one structure with out-of-sample Sharpe 1.44 and 1.92 is "
                    "weak-but-real evidence that the structure, not one lucky recipe, is doing "
                    "something. Neither reaches the 3.52 headline out of sample."
                ),
            },
            {
                "url": SOURCE_DEFS[2]["url"],
                "published_or_updated_at": "unknown",
                "source_type": "provider_official_docs",
                "credibility": "Issuer's own product page; authoritative on fund mechanics.",
                "core_claim": SOURCE_DEFS[2]["claim"],
                "project_applicability": SOURCE_DEFS[2]["applicability"],
                "reflection": (
                    "Forces the hedge leg to be judged on realized contribution and holding "
                    "days, not on the intuition that 'a VIX ETF protects you'."
                ),
            },
            {
                "url": "https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00146",
                "published_or_updated_at": "1999-08-01",
                "source_type": "paper",
                "credibility": (
                    "Moskowitz and Grinblatt, Journal of Finance 54(4):1249-1290; one of the "
                    "most replicated results in the momentum literature."
                ),
                "core_claim": (
                    "Industry components of stock returns carry a strong momentum effect that "
                    "accounts for much of individual-stock momentum."
                ),
                "project_applicability": (
                    "This is the published mechanism behind the normal branch: rank sectors by "
                    "trailing return and hold the leader."
                ),
                "reflection": (
                    "The paper supports medium-horizon industry momentum; the 21-day lookback "
                    "used here is shorter than its 1-12 month evidence, so the normal branch is "
                    "the part most at risk of being noise -- which is why the random-pick "
                    "placebo runs 60 seeds on it."
                ),
            },
            {
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2042750",
                "published_or_updated_at": "2016-10-01",
                "source_type": "ssrn",
                "credibility": (
                    "Antonacci, widely replicated practitioner-academic work on dual momentum; "
                    "public long-run tracking exists for the monthly global version."
                ),
                "core_claim": (
                    "Combining relative-strength selection with an absolute-momentum filter "
                    "raises risk-adjusted returns versus either alone."
                ),
                "project_applicability": (
                    "The Composer tree is a branch-shaped dual momentum: the RSI extremes play "
                    "the role the absolute-momentum filter plays in Antonacci."
                ),
                "reflection": (
                    "Public dual-momentum trackers earn 10-15% annualized, two orders below "
                    "the platform headlines. The gap is leverage plus window selection, and "
                    "that is exactly the thing the placebos here have to separate."
                ),
            },
            {
                "url": "https://www.nber.org/papers/w22208",
                "published_or_updated_at": "2016-04-01",
                "source_type": "working_paper",
                "credibility": (
                    "Moreira and Muir, NBER w22208, published as Journal of Finance 72(4):"
                    "1611-1644; multiple independent replications and critiques."
                ),
                "core_claim": (
                    "Portfolios that take less risk when realized volatility is high earn "
                    "higher Sharpe ratios, because volatility changes are not matched by "
                    "proportional changes in expected returns."
                ),
                "project_applicability": (
                    "This is the economic case for the overheat branch existing at all: cut or "
                    "invert exposure when the market is stretched."
                ),
                "reflection": (
                    "Moreira-Muir scales exposure by realized volatility; RSI > 80 is a price-"
                    "extreme proxy, not a volatility measure, so a pass here would not be "
                    "evidence for Moreira-Muir and a failure would not refute it. Candidate "
                    "B-2 tests the volatility-target version directly."
                ),
            },
            {
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5095447",
                "published_or_updated_at": "2025-01-01",
                "source_type": "ssrn",
                "credibility": (
                    "Working paper with a public QuantConnect notebook; no live track record."
                ),
                "core_claim": (
                    "A cross-asset ETF momentum strategy holding the four strongest ETFs with a "
                    "30% short leg on the weakest reports a Sharpe near 0.5 over 2007-2026."
                ),
                "project_applicability": (
                    "Reference point for what a disciplined, long-sample ETF rotation actually "
                    "earns once it is not window-selected."
                ),
                "reflection": (
                    "Sharpe 0.5 over 19 years versus 1.4-1.9 over one to four recent years is "
                    "the size of the window-selection effect we are knowingly accepting. "
                    "I-20260922-02 already ruled this candidate out on return grounds; it is "
                    "kept here only as the honest long-sample anchor."
                ),
            },
            {
                "url": (
                    "https://quantpedia.com/strategies/"
                    "sectoral-intramonth-momentum-cycle-in-us-equities/"
                ),
                "published_or_updated_at": "2026-08-17",
                "source_type": "industry_standard",
                "credibility": (
                    "Quantpedia strategy write-up with a linked paper; descriptive, no live "
                    "tracking."
                ),
                "core_claim": (
                    "A long/short sectoral momentum cycle over 9 SPDR sectors plus SPY with "
                    "252-day momentum and intramonth rebalancing reports about 5.99% "
                    "annualized at Sharpe 0.55."
                ),
                "project_applicability": (
                    "Independent, same-universe evidence on how much a pure sector-momentum "
                    "ranking is worth without leverage or branch logic."
                ),
                "reflection": (
                    "Roughly 6% annualized from the ranking alone means any 50%+ result here "
                    "is coming from leverage and from the branch tree, not from sector "
                    "selection. That framing decides how the contribution decomposition in the "
                    "report is read."
                ),
            },
        ],
    }


# --------------------------------------------------------------------------
# 3. frozen 16-cell grid
# --------------------------------------------------------------------------


def build_cells() -> list[dict]:
    cells = []
    n = 0
    for rsi_ref in RSI_REFS:
        for overheat_asset in OVERHEAT_ASSETS:
            for menu in MENUS:
                for rebalance in REBALANCES:
                    n += 1
                    cells.append(
                        {
                            "candidate_id": f"C{n:02d}",
                            "cell_id": (f"rsib_{rsi_ref}_oh{overheat_asset}_{menu}_{rebalance}"),
                            "rsi_ref": rsi_ref,
                            "rsi_window": 10,
                            "overheat_threshold": 80,
                            "overheat_asset": overheat_asset,
                            "oversold_threshold": 30,
                            "oversold_asset": "TQQQ",
                            "menu": menu,
                            "normal_lookback_days": 21,
                            "rebalance": rebalance,
                        }
                    )
    return cells


def main() -> int:
    ITER_DIR.mkdir(parents=True, exist_ok=True)
    cards = build_source_cards()
    CARDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CARDS_PATH.write_text(
        "\n".join(json.dumps(card, sort_keys=True) for card in cards) + "\n", encoding="utf-8"
    )

    write_json(ITER_DIR / "direction-review.json", build_direction_review(cards))

    spec_file = ROOT / SPEC_PATH
    if not spec_file.exists():
        raise SystemExit(f"write {SPEC_PATH} before running prepare")
    from open_composer.models.strategy_spec import load_strategy_spec
    from open_composer.strategy_versions import strategy_content_hash

    spec_hash = strategy_content_hash(load_strategy_spec(spec_file))
    write_json(ITER_DIR / "external-brief.json", build_external_brief(spec_hash))

    cost_table = {
        "iter_id": ITER_ID,
        "base_cost_bps_per_side": 10,
        "stress_cost_bps_per_side": 20,
        "note": (
            "Frozen H-20260918-05 convention reused unchanged: sum(|delta w|) * slippage "
            "charged on the execution session, signal on close, fill at next session open."
        ),
    }
    cost_sha = write_json(ITER_DIR / "cost-table.json", cost_table)

    cells = build_cells()
    manifest_candidates = []
    for cell in cells:
        manifest_candidates.append(
            {
                "ablation": f"overheat_branch_{cell['overheat_asset']}",
                "benchmark_contract": "recent_window_etf_benchmarks_v1",
                "candidate_id": cell["candidate_id"],
                "cell_id": cell["cell_id"],
                "cost_contract": "sip_daily_10bp_primary_20bp_stress",
                "data_contract": "sip_daily_adjusted_close_open",
                "fallback": "BIL",
                "feature_contract": "rsi10_and_21d_return_rank",
                "label_contract": "next_session_open_to_open_total_return",
                "method": "rsi_extreme_branch_tree_with_sector_rotation",
                "parameters": {
                    key: cell[key]
                    for key in (
                        "rsi_ref",
                        "rsi_window",
                        "overheat_threshold",
                        "overheat_asset",
                        "oversold_threshold",
                        "oversold_asset",
                        "menu",
                        "normal_lookback_days",
                        "rebalance",
                    )
                },
                "path": PATH_NAME,
                "role": "deterministic_mechanism_candidate",
                "spec_path": SPEC_PATH,
                "validation_contract": "select_rank_holdout_report_plus_two_placebos",
            }
        )

    manifest = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "generated_at": REVIEWED_AT,
        "generated_before_backtest": True,
        "candidate_count": len(manifest_candidates),
        "candidates": manifest_candidates,
        "contracts": {
            "benchmarks": {
                "recent_window_etf_benchmarks_v1": {
                    "description": (
                        "SPY, MTUM, SPMO, QQQ, TQQQ buy-and-hold, the live S1 sleeve "
                        "(rot_A2_sector_lb252_top2_weekly) and equal-weight holdings of both "
                        "menus, all on the same windows and fill assumption."
                    )
                }
            },
            "costs": {
                "sip_daily_10bp_primary_20bp_stress": {
                    "description": "See cost-table.json.",
                    "cost_table_sha256": cost_sha,
                }
            },
            "data": {
                "sip_daily_adjusted_close_open": {
                    "description": (
                        "SIP archive fully adjusted daily open/close from "
                        "data/sip/daily/*/*.parquet; zero-volume zero-trade ghost bars dropped."
                    )
                }
            },
            "features": {
                "rsi10_and_21d_return_rank": {
                    "description": (
                        "Wilder RSI(10) on the reference symbol's adjusted close, and the "
                        "21-session simple return used to rank the menu."
                    )
                }
            },
            "labels": {
                "next_session_open_to_open_total_return": {
                    "description": (
                        "No supervised labels. Weights decided on the signal close take effect "
                        "at the next session's open."
                    )
                }
            },
            "validation": {
                "select_rank_holdout_report_plus_two_placebos": {
                    "description": (
                        "Rank on 2023-09-18..2025-12-31 only; report the untouched holdout "
                        "2026-01-02..2026-09-17 and the anchor 2024-01-08..2026-09-16; "
                        "placebos are a 1-20 session RSI calendar shift x 20 seeds and a "
                        "random single pick from the same menu x 60 seeds."
                    )
                }
            },
        },
        "spec_hashes": {SPEC_PATH: spec_hash},
    }
    manifest_path = ITER_DIR / "candidate-manifest.json"
    manifest_sha = write_json(manifest_path, manifest)

    feasibility = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "report_type": "rsi_branch_rotation_daily_etf_data_feasibility",
        "generated_at": REVIEWED_AT,
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "historical_evaluation_authorized": True,
        "coverage_note": (
            "All 20 symbols verified present in data/sip/daily with full history from "
            "2016-01-04 except DUSL (2017-05-03) and XLC (2018-06-19); both start well before "
            "the 2022-06-01 warmup, so no window is shortened and no gap is imputed."
        ),
        "path_gates": {
            PATH_NAME: {
                "action": "evaluate",
                "historical_evaluation_go": True,
                "candidate_ids": [row["candidate_id"] for row in manifest_candidates],
                "reason": (
                    "Daily SIP bars cover every menu, hedge and cash symbol across the warmup, "
                    "selection, holdout and anchor windows."
                ),
            }
        },
        "candidate_accounting": {
            "frozen_candidate_count": len(manifest_candidates),
            "evaluation_authorized_count": len(manifest_candidates),
            "dependency_skipped_count": 0,
            "unresolved_count": 0,
            "balanced": True,
        },
        "candidate_authorization": {
            "candidate_count": len(manifest_candidates),
            "rows": [
                {
                    "candidate_id": row["candidate_id"],
                    "path": row["path"],
                    "action": "evaluate",
                    "reason_code": "sip_daily_coverage_complete_for_all_windows",
                    "candidate_binding_sha256": candidate_authorization_binding_sha256(row),
                }
                for row in manifest_candidates
            ],
        },
        "required_reference_names": ["candidate_manifest", "cost_table"],
        "required_references": {
            "candidate_manifest": {
                "path": manifest_path.relative_to(ROOT).as_posix(),
                "sha256": manifest_sha,
            },
            "cost_table": {
                "path": (ITER_DIR / "cost-table.json").relative_to(ROOT).as_posix(),
                "sha256": cost_sha,
            },
        },
    }
    feasibility_path = ITER_DIR / "data-feasibility.json"
    feasibility_sha = write_json(feasibility_path, feasibility)

    search_space = {
        "schema_version": 3,
        "iter_id": ITER_ID,
        "created_at": REVIEWED_AT,
        "strategy_name": "h20260922_04_rsi_branch_family",
        "source_spec_path": SPEC_PATH,
        "spec_hash": spec_hash,
        "single_mechanism_no_campaign_attestation": True,
        "candidate_manifest_path": manifest_path.relative_to(ROOT).as_posix(),
        "candidate_manifest_sha256": manifest_sha,
        "cost_table_path": (ITER_DIR / "cost-table.json").relative_to(ROOT).as_posix(),
        "data_feasibility_path": feasibility_path.relative_to(ROOT).as_posix(),
        "data_feasibility_sha256": feasibility_sha,
        "total_candidate_budget": len(manifest_candidates),
        "paths": [
            {
                "name": PATH_NAME,
                "candidate_count": len(manifest_candidates),
                "hypothesis_refs": ["h_rsi_extreme_branch_carries_the_return"],
                "parameters": {
                    "rsi_ref": RSI_REFS,
                    "overheat_asset": OVERHEAT_ASSETS,
                    "menu": MENUS,
                    "rebalance": REBALANCES,
                    "rsi_window": [10],
                    "overheat_threshold": [80],
                    "oversold_threshold": [30],
                    "oversold_asset": ["TQQQ"],
                    "normal_lookback_days": [21],
                },
                "benchmark_family": [
                    "buy_and_hold_spy",
                    "buy_and_hold_mtum",
                    "buy_and_hold_spmo",
                    "buy_and_hold_qqq",
                    "buy_and_hold_tqqq",
                    "live_sleeve_s1_rot_a2_sector_lb252_top2_weekly",
                    "equal_weight_sector1x_menu",
                    "equal_weight_levered3x_menu",
                ],
            }
        ],
        "trial_ledger_paths": [],
        "evaluation_report_paths": [],
    }
    write_json(ITER_DIR / "search-space.json", search_space)
    print(f"prepared {len(manifest_candidates)} preregistered cells for {ITER_ID}")
    print(f"manifest sha256 {manifest_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
