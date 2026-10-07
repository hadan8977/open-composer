# ruff: noqa: E501
"""T-20261006-18: fill the hand-written parts of both dossiers and stamp hashes (run before any backtest)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import t18_factors as F  # noqa: E402

IT = ROOT / "reports/research/iterations"
MAIN, LANE = "t20261006_18_library_batch1", "t20261006_18_library_batch1_lane"
SRCDIR = "reports/research/intel/sources/library-batch1-2026-10-06"
BOOK_DR = json.loads((IT / "t20261002_book_v12/direction-review.json").read_text())


def sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def now() -> str:
    return subprocess.run(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], capture_output=True, text=True, check=True
    ).stdout.strip()


def def_table() -> str:
    rows = ["| id | sign | status | definition used / missing item |", "|---|---|---|---|"]
    for k, v in F.DEFINITIONS.items():
        rows.append(
            f"| {k} | {v['sign']:+d} | {v['status']} | {v.get('note') or v.get('missing')} |"
        )
    return "\n".join(rows)


def stamp(path: Path, ts: str) -> None:
    t = path.read_text()
    for token, rel in (
        ("__SHA_FACTORS__", "scripts/t18_factors.py"),
        ("__SHA_ENGINE__", "scripts/t18_engine.py"),
        ("__SHA_XBRL__", "scripts/t18_extra_xbrl.py"),
        ("__SHA_LANE__", "scripts/t18_lane.py"),
        ("__SHA_LANEMOD__", "scripts/screen_batches/t20261006_18_library_lane.py"),
    ):
        t = t.replace(token, sha(rel))
    t = t.replace("__FREEZE_TS__", ts).replace("__DEF_TABLE__", def_table())
    path.write_text(t)


NEW_QUERIES = [
    (
        'Hou Xue Zhang "Replicating Anomalies" Review of Financial Studies 2020 452 anomalies replicate fraction',
        "2026-10-06T23:09:30Z",
        ["https://www.nber.org/papers/23394"],
    ),
    (
        'McLean Pontiff "Does Academic Research Destroy Stock Return Predictability" post-publication decline',
        "2026-10-06T23:10:00Z",
        [
            "https://counterpointfunds.com/wp-content/uploads/2017/07/PredictabilityMcleanPontiff.pdf"
        ],
    ),
    (
        "Open Source Asset Pricing signal replication t-statistics published versus replication",
        "2026-10-06T23:08:50Z",
        ["https://www.openassetpricing.com/"],
    ),
    (
        "QuantConnect strategy library rule pages for the eight ETF / calendar ids (fetched and saved 2026-10-06)",
        "2026-10-06T23:12:00Z",
        [
            "https://www.quantconnect.com/tutorials/strategy-library/can-crude-oil-predict-equity-returns",
            "https://www.quantconnect.com/tutorials/strategy-library/capm-alpha-ranking-strategy-on-dow-30-companies",
            "https://www.quantconnect.com/tutorials/strategy-library/ichimoku-clouds-in-the-energy-sector",
            "https://www.quantconnect.com/tutorials/strategy-library/january-barometer",
            "https://www.quantconnect.com/tutorials/strategy-library/the-dynamic-breakout-ii-strategy",
            "https://www.quantconnect.com/tutorials/strategy-library/turn-of-the-month-in-equity-indexes",
        ],
    ),
]
NEW_SRC = {
    "hxz_2020_replicating_anomalies": (
        "US stocks, anomalies replicated on 1967-2014 CRSP/Compustat with NYSE breakpoints and value weights",
        f"{SRCDIR}/hxz_nber_w23394.html",
    ),
    "mclean_pontiff_2016_publication_decay": (
        "US stocks, 97 predictors, out of sample and after publication, sample ends around 2013",
        f"{SRCDIR}/mclean_pontiff_2016_p1-2.txt",
    ),
    "osap_chen_zimmermann_open_source_asset_pricing": (
        "US stocks CRSP/Compustat, signals 1926-2023, replication of published predictors",
        f"{SRCDIR}/osap_home.html",
    ),
}


def direction(iter_id: str, main: bool, ts: str) -> dict:
    cards = [
        json.loads(x)
        for x in (ROOT / f"reports/harness/source_cards/{iter_id}.jsonl").read_text().splitlines()
    ]
    by = {c["claim_id"]: c for c in cards}
    sources = []
    for s in BOOK_DR["sources"]:
        c = by[s["claim_id"]]
        s = dict(s)
        s["source_card_path"] = f"reports/harness/source_cards/{iter_id}.jsonl"
        s["claim"] = c["claim"]
        sources.append(s)
    for cid, (mp, snap) in NEW_SRC.items():
        c = by[cid]
        sources.append(
            {
                "claim_id": cid,
                "claim": c["claim"],
                "source_type": "paper",
                "published_or_updated_at": c["published_or_updated_at"],
                "market_and_period": mp,
                "applicability": c["impact_on_spec"],
                "limitations": c["limitations"],
                "independent_replication": c["independent_replication"],
                "fetched_at": c["fetched_at"],
                "snapshot_path": snap,
                "sha256": c["source_sha256"],
                "source_card_path": f"reports/harness/source_cards/{iter_id}.jsonl",
                "url": c["source_url"],
            }
        )
    queries = [dict(q, note=q.get("note", "")) for q in BOOK_DR["queries"]]
    for q, t, urls in NEW_QUERIES:
        queries.append(
            {
                "query": q,
                "searched_at": t,
                "opened_urls": urls,
                "note": "T-20261006-18 executor; time taken from the session log (to the minute).",
            }
        )
    objective = (
        "Library batch 1: test 19 computable stock factors of the OSAP / QuantConnect library alone, for overlap with the nine v1.2 themes and as a tenth category of the v1.2 composite at equal construction and costs; recent window decides."
        if main
        else "Library batch 1, ETF and calendar rules: eight QuantConnect rules (63 member rules incl. the existing opex-week and pre-holiday batches) under the screen-lane contract with a vol-matched control, long-only; recent window decides."
    )
    return {
        "schema_version": 1,
        "iter_id": iter_id,
        "reviewed_at": ts,
        "decision": "proceed",
        "objective": objective,
        "target_regime_and_horizon": "US equities (U3000 / P1000 members of the equity book panel) and US ETFs; monthly decisions for the single-factor books and weekly five-offset decisions for the composite; recent window 2024-01-08..2026-09-17 decides, 2017-10..2023-08 is only the crash diagnostic. Effect is expected to be regime specific (up_mid state, VIX below 20.60); validity to 2026-12-31 then a forward review.",
        "existing_solution_comparison": "Public reproductions exist for every definition (OSAP SignalDoc and code for the 24 OSAP ids; QuantConnect tutorials for the rules) and are reused as definitions, not re-derived. Their published results come from CRSP-era samples: Hou-Xue-Zhang find 64% of 447 anomalies insignificant with value weights and NYSE breakpoints, McLean-Pontiff a 58% post-publication decline, Chen-Velikov 4 bp a month net for single anomalies after 2005. The book v1.2 already carries nine themes built on the same logic, so the value of a new factor is the marginal Sharpe inside the composite, which no public source reports for our universe and costs.",
        "remaining_evidence_gap": "Marginal contribution of each factor to the v1.2 composite at equal volatility on the 2024-26 cross-section with fitted costs, easy-to-borrow shorts and the VIX rule; the OSAP definitions rebuilt from SEC XBRL facts (not Compustat); the power of a 33-month window (reported per comparison).",
        "negative_experiments_checked": "T-20261002-24 (ml_pv, low MAX, near 52-week high, Alpha158 FDR composite add no residual IC in 2024-26); book v1.1 cancelled; dir:net_share_issuance_pontiff_woodgate_recent refuted (OSAP issuance family, family-level only); dir:pead_xbrl_sue_filing_date refuted and dir:pead_classic_sue_microcap_decay evidence_too_weak (the SUE id is the book's own earnings-theme member, so it is run as an overlap check); dir:option_expiration_week_calendar_effect, dir:pre_holiday_effect_small_cap_tier and dir:turn_of_month_equity_seasonality refuted without depth (rerun with a vol-matched control and circular-shift placebo, all members counted). None of the 24 OSAP ids was tested individually before (prior_scope family_level or none).",
        "cost_and_execution_assumptions": "Stock books: cost model v1 at the close snapshot (fitted half-spread + square-root impact at E = $1M + 0.5 bp fees), borrow 25 bp a year on the easy-to-borrow proxy, fill at the close of t+1, VIX > 20.60 halves the book, EWMA SPY hedge. Lane rules: 10 bp per side primary, 20 bp stress, next-open fill, long-only with SHY remainder.",
        "stop_condition": "Stage identity check failure stops the batch; factors not reached by 2026-10-10 22:00 UTC are labelled not at depth; a factor is called unfounded only under the recent-window rule of hypotheses.md section 5; no rule is changed after a result is seen.",
        "cheapest_decisive_test": {
            "action": "Identity check of the rebuilt v1.2 base against the saved R6 series, then tier 1 (76 single-factor monthly books), tier 2 (nine theme books and spanning regressions) and tier 3 (composite plus factor, 4 variants, 5 offsets) for each of the 19 factors; the lane runner for the eight ETF / calendar ids.",
            "pass_condition": "At least one factor meets the 'into the book' rule or at least one primary lane member meets the incubation proxy of the preregistered rules.",
            "falsification_condition": "No factor meets either rule and the recent-window rule of hypotheses.md section 5 labels them unfounded or not at depth; no primary lane member meets the proxy.",
            "max_compute_minutes": 1440,
        },
        "queries": queries,
        "sources": sources,
    }


def patch_external(iter_id: str, family: str, mech: str, diff: str) -> None:
    p = IT / iter_id / "external-brief.json"
    d = json.loads(p.read_text())
    d["mechanism_family"] = family
    d["mechanism_description"] = mech
    ref_scores = (
        json.loads((ROOT / "reports/research/control/t18_similarity_refs.json").read_text())
        if (ROOT / "reports/research/control/t18_similarity_refs.json").exists()
        else {}
    )
    d["difference_from_existing"] = [{"ref": r, "difference": diff} for r in ref_scores]
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    ts = now()
    for it, main_flag in ((MAIN, True), (LANE, False)):
        (IT / it / "direction-review.json").write_text(
            json.dumps(direction(it, main_flag, ts), indent=2, ensure_ascii=False) + "\n"
        )
        stamp(IT / it / "hypotheses.md", ts)
    mech_main = "Cross-sectional stock factors from the published OSAP / QuantConnect library, each added as a tenth category to the nine-theme v1.2 long/short stock composite; the test is the marginal net Sharpe of the weekly five-offset book at equal construction and costs on 2024-2026 US stocks, plus single-factor monthly books and spanning regressions on the nine theme books."
    mech_lane = "Published calendar and technical ETF rules (option expiration week, pre-holiday, turn of the month, dynamic breakout, Ichimoku on energy ETFs, CAPM alpha ranking on the most liquid names, January barometer, oil to equity forecast) run long-only under the screen-lane contract against a vol-matched control with circular-shift placebos."
    diff = "Different universe and question: this iteration tests published library factors one by one inside the existing v1.2 composite and as single-factor books; it does not build a new model, intraday strategy or reversal signal."
    patch_external(MAIN, "equity_factor_library_batch", mech_main, diff)
    patch_external(LANE, "etf_calendar_rules_library_batch", mech_lane, diff)
    print("frozen at", ts)


if __name__ == "__main__":
    main()
