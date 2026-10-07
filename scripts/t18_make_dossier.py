# ruff: noqa: E501
"""T-20261006-18: write the preregistration dossiers (main = 19 factor books, lane = 8 ETF/calendar ids).

Builds on ``scripts/new_lightweight_iteration.py`` (each dossier is a single-mechanism lightweight path, at
most 24 candidates).  Run once, before any return is computed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import new_lightweight_iteration as nli  # noqa: E402

from scripts import t18_factors as F  # noqa: E402

BOOK = ROOT / "reports/research/iterations/t20261002_book_v12"
SRC = "reports/research/intel/sources/library-batch1-2026-10-06"
MAIN, LANE = "t20261006_18_library_batch1", "t20261006_18_library_batch1_lane"
NOW = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(p: str) -> str:
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


NEW_CARDS = [
    dict(
        claim_id="hxz_2020_replicating_anomalies",
        claim="Hou, Xue and Zhang (RFS 2020, NBER w23394): of 447 anomaly variables, 286 (64%) including 95 of 102 liquidity variables (93%) are insignificant at the 5% level once microcaps are tamed with NYSE breakpoints and value weights; at a t-value of 3, 85% are insignificant.",
        quote="286 anomalies (64%) including 95 out of 102 liquidity variables (93%) are insignificant at the conventional 5% level.",
        snap=f"{SRC}/hxz_nber_w23394.html",
        url="https://www.nber.org/papers/23394",
        date="2017-03-01",
        impact="Single published anomalies must be treated as likely false until they survive our own cost-aware, multiple-testing-corrected tests; the batch therefore reports every factor in the same portfolio frame and counts every trial.",
        limits="US stocks 1967-2014 era; our window is 2016-2026 and the universe is price >= 5 with a top-3000 liquidity filter, so most OSAP microcap anomalies are excluded by construction.",
        stype="paper",
    ),
    dict(
        claim_id="mclean_pontiff_2016_publication_decay",
        claim="McLean and Pontiff (JF 2016): across 97 published predictors, portfolio returns are 26% lower out of sample and 58% lower after publication; declines are larger for predictors with higher in-sample returns, and returns remain higher among high idiosyncratic risk and low liquidity stocks.",
        quote="Portfolio returns are 26% lower out-of-sample and 58% lower post-publication.",
        snap=f"{SRC}/mclean_pontiff_2016_p1-2.txt",
        url="https://counterpointfunds.com/wp-content/uploads/2017/07/PredictabilityMcleanPontiff.pdf",
        date="2016-02-01",
        impact="Candidates published 2007-2016 (this batch) are expected to be weaker in 2024-26 than in the original sample; the decision window is recent only and published t-values are not used as evidence.",
        limits="Working-paper copy of the JF article; effect sizes are averages over 97 predictors, not per factor.",
        stype="paper",
    ),
    dict(
        claim_id="osap_chen_zimmermann_open_source_asset_pricing",
        claim="Open Source Asset Pricing (Chen and Zimmermann, Critical Finance Review 2022) publishes signal definitions (SignalDoc.csv) and code replicating the academic cross-section, with a chart comparing published t-statistics to the replication; releases add signals every year (portfolios updated to end 2023 as of the August 2024 release).",
        quote="t-statistics in published studies against our replication",
        snap=f"{SRC}/osap_home.html",
        url="https://www.openassetpricing.com/",
        date="2024-08-01",
        impact="Supplies the 24 OSAP definitions used here (SignalDoc.csv, snapshot 2026-10-06); every factor in this batch is implemented against that text and deviations from it are listed.",
        limits="Definitions are CRSP/Compustat based; our implementation uses SEC XBRL facts and Alpaca prices, so item coverage and timing differ (see hypotheses.md section 2).",
        stype="paper",
    ),
]


def cards() -> list[dict]:
    rows = [
        json.loads(line)
        for line in (ROOT / "reports/harness/source_cards/t20261002_book_v12.jsonl")
        .read_text()
        .splitlines()
    ]
    for r in rows:
        r["applies_to"] = sorted({*r.get("applies_to", []), MAIN, LANE})
    for n in NEW_CARDS:
        rows.append(
            {
                "accessed_at": NOW,
                "applies_to": [MAIN, LANE],
                "claim": n["claim"],
                "claim_id": n["claim_id"],
                "fetched_at": NOW,
                "impact_on_spec": n["impact"],
                "independent_replication": "see sibling source cards (HXZ, McLean-Pontiff, OSAP are mutually independent replications of the anomaly literature)",
                "limitations": n["limits"],
                "published_or_updated_at": n["date"],
                "quote": n["quote"],
                "source_sha256": sha(n["snap"]),
                "source_snapshot": n["snap"],
                "source_type": n["stype"],
                "source_url": n["url"],
                "status": "verified",
                "verification_method": "quote matched in the saved snapshot by the T-20261006-18 executor (grep / pdftotext of the saved file)",
                "verification_status": "source_verified",
            }
        )
    return rows


def sources_for(book_sources: list[dict]) -> list[dict]:
    out = list(book_sources)
    for n in NEW_CARDS:
        out.append(
            {
                "claim_id": n["claim_id"],
                "url": n["url"],
                "published_or_updated_at": n["date"],
                "source_type": n["stype"],
                "credibility": "peer_reviewed_or_working_paper",
                "core_claim": n["claim"],
                "project_applicability": n["impact"],
                "reflection": n["limits"],
            }
        )
    return out


def write_specs() -> None:
    tpl = (ROOT / "strategy_specs/drafts/t20261002_book_v12.yaml").read_text()
    for it, desc in (
        (
            MAIN,
            "Library batch 1, factor books: 19 OSAP / QuantConnect stock factors, each tested alone, against the nine v1.2 themes and added to the v1.2 composite, judged on the recent window. Research only, no broker writes.",
        ),
        (
            LANE,
            "Library batch 1, ETF and calendar rules: 8 QuantConnect rules (opex week, pre-holiday, turn of month, dynamic breakout II, Ichimoku energy, CAPM alpha ranking, January barometer, oil to equity) under the screen-lane contract, long-only with SHY remainder. Research only, no broker writes.",
        ),
    ):
        txt = tpl.replace("t20261002_book_v12", it)
        lines = txt.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("description:"):
                lines[i] = "description: " + json.dumps(desc)
        (ROOT / f"strategy_specs/drafts/{it}.yaml").write_text("\n".join(lines) + "\n")


def candidate_params() -> list[dict]:
    out = []
    for name in F.COMPUTED:
        d = F.DEFINITIONS[name]
        out.append(
            {
                "candidate_id": name,
                "parameters": {
                    "first_batch_id": "qc-standardized-unexpected-earnings"
                    if name == "SUE"
                    else f"osap-{name}",
                    "definition": d["note"],
                    "orientation_sign": d["sign"],
                    "kind": d["kind"],
                    "tier1": "month-end decision, close of t+1 fill, universes U3000 and P1000, processing raw and FF-industry demeaned, long 1 / short 1 rank-normal weights, easy-to-borrow shorts, EWMA SPY hedge, VIX halving, fitted costs, 25 bp borrow",
                    "tier2": "monthly gross return regression on the nine theme books and M0; correlation with each theme",
                    "tier3": "added to the v1.2 M0 composite as a tenth category at weight 0.5 / 1 / 2 of one theme (scale matched to the average theme dispersion) plus a merge into the closest theme; weekly 5 offsets; recent window 2024-01-08 decides",
                },
            }
        )
    return out


def main() -> None:
    book_cfg = json.loads((BOOK / "lightweight-config.json").read_text())
    rows = cards()
    for it in (MAIN, LANE):
        p = ROOT / f"reports/harness/source_cards/{it}.jsonl"
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    write_specs()
    topics = [
        *book_cfg["topic_coverage"],
        "published_anomaly_replication_and_decay",
        "calendar_effect_etf_rules",
    ]
    common = dict(
        benchmark_family=[
            "cash_proxy_bil_excess_return",
            "v12_m0_u3000_base_same_decisions_same_costs",
            "within_date_score_permutation_placebo_gross",
            "nine_theme_spanning_regression",
            "dsr_family_all_trials_of_the_batch",
        ],
        sources=sources_for(book_cfg["sources"]),
        topic_coverage=topics,
    )
    cfg_main = {
        **common,
        "iter_id": MAIN,
        "strategy_name": MAIN,
        "representative_spec_path": f"strategy_specs/drafts/{MAIN}.yaml",
        "path_name": "library_factor_books_batch1",
        "hypothesis_id": "T-20261006-18",
        "objective": "Library batch 1 (T-20261006-18): test 19 computable stock factors from the OSAP / QuantConnect strategy library (6 more are data-insufficient and listed) in three layers - alone, overlap with the nine v1.2 themes, and as a tenth category of the v1.2 composite at the same construction and costs - so that factors which raise the recent net Sharpe of the stock long/short book at equal volatility enter the next book version and factors with a standalone case can go to paper. Recent window 2024-01-08..2026-09-17 decides; 2017-10..2023-08 is a crash diagnostic.",
        "candidates": candidate_params(),
        "cost_table": {
            "base_cost_bps": 10,
            "stress_cost_bps": 20,
            "judged_cost": 'cost model v1 at the close snapshot (make_cost_fn("close")): fitted half-spread + square-root impact at E = $1M + 0.5 bp fees; borrow 25 bp a year on easy-to-borrow shorts (T-25 convention)',
            "two_x_cost_check": "2x trading costs plus 100 bp borrow, reported for standalone candidates",
            "fixed_comparison": "v1.2 M0_U3000 base rebuilt with the same engine from 2023-12; identity check against the saved R6 series",
        },
        "hypothesis": {
            "statement": "H1: at least one of the 19 factors, added to the v1.2 M0 composite as a tenth category, raises the recent (2024-01-08..2026-09-17) 5-offset blended net Sharpe at equal volatility by the preregistered margin at the depth points, without a crash-diagnostic deterioration.",
            "failure_mode": "Published factors decay after publication (McLean-Pontiff 58%); recent window has 33 monthly points so power is low; fundamentals proxied from XBRL differ from Compustat definitions; most factors overlap the value / quality / momentum / investment themes.",
            "measurement": "Delta Sharpe of the blended net series versus the base at weights 0.5 / 1 / 2 and merge, paired bootstrap, minimum detectable improvement reported, DSR over all trials of the batch, within-date permutation placebo.",
            "stop_pivot": "Factors not reaching the full depth in budget are marked not-at-depth; no factor is called unfounded unless the preregistered recent-window failure rule holds on both universes and all depth points.",
        },
        "decision": {
            "path": "library_factor_books_batch1",
            "decision": "pending",
            "reason": "Preregistered 2026-10-06 by the T-20261006-18 executor before any return of this batch was computed.",
            "next_iteration_suggestion": "Report book-addition-proposal.md to the coordinator; a factor that enters the next composite version needs its own forward shadow record.",
        },
        "source_cards_path": f"reports/harness/source_cards/{MAIN}.jsonl",
    }
    lane_cands = []
    first = [
        i
        for i in json.loads(
            (ROOT / "reports/research/strategy-library/first-batch.json").read_text()
        )["items"]
        if i["engine"] == "lane"
    ]
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "t18lane_mod", ROOT / "scripts/screen_batches/t20261006_18_library_lane.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "scripts"))
    spec.loader.exec_module(mod)
    for i in first:
        g = mod.GROUPS[i["id"]]
        lane_cands.append(
            {
                "candidate_id": i["id"],
                "parameters": {
                    "primary_member": g["primary"],
                    "member_prefixes": list(g["prefix"]),
                    "contract": "scripts/screen_lane.py: 10/20 bp per side, next-open fill, excess over BIL, vol-matched S3 control, long-only with SHY remainder",
                    "placebo": "200 circular shifts of the weight path (>= 126 sessions)",
                },
            }
        )
    cfg_lane = {
        **common,
        "iter_id": LANE,
        "strategy_name": LANE,
        "representative_spec_path": f"strategy_specs/drafts/{LANE}.yaml",
        "path_name": "library_etf_calendar_rules_batch1",
        "hypothesis_id": "T-20261006-18",
        "objective": "Library batch 1, ETF and calendar rules (T-20261006-18): run the 8 first-batch lane ids (63 member rules including existing opex-week and pre-holiday members and the new rules) under the screen-lane contract, with the anchor window 2024-01-08..2026-09-17 deciding, so that rules passing the incubation proxy get a paper-sleeve note.",
        "candidates": lane_cands,
        "cost_table": {
            "base_cost_bps": 10,
            "stress_cost_bps": 20,
            "judged_cost": "lane contract 10 bp per side primary",
            "two_x_cost_check": "20 bp per side",
            "fixed_comparison": "vol-matched S3 control (k*S3 + (1-k)*SHY), 21 monthly offsets for M rules",
        },
        "hypothesis": {
            "statement": "H1: at least one primary member passes the preregistered incubation proxy (judged anchor edge over the vol-matched S3 control >= 0.10, anchor net-20bp Sharpe > 0, DSR over the 63 trials >= 0.70, circular-shift placebo >= 0.90).",
            "failure_mode": "Calendar effects are weak after publication; 33 months of anchor data; long-only versions drop the original short legs.",
            "measurement": "lane leaderboard fields plus circular-shift placebo; all members counted as trials.",
            "stop_pivot": "Members not primary are sensitivity only; a passing non-primary member is marked 'needs confirmation'.",
        },
        "decision": {
            "path": "library_etf_calendar_rules_batch1",
            "decision": "pending",
            "reason": "Preregistered 2026-10-06 before any lane return of this batch.",
            "next_iteration_suggestion": "paper-sleeve notes for incubation-proxy passers.",
        },
        "source_cards_path": f"reports/harness/source_cards/{LANE}.jsonl",
    }
    for cfg in (cfg_main, cfg_lane):
        (ROOT / f"reports/research/iterations/{cfg['iter_id']}").mkdir(parents=True, exist_ok=True)
        try:
            nli.build_dossier(cfg, ROOT, overwrite=True)
        except SystemExit as exc:  # direction-review.json is hand-written afterwards
            print("build_dossier exit:", exc)
        print("built", cfg["iter_id"])


if __name__ == "__main__":
    main()
