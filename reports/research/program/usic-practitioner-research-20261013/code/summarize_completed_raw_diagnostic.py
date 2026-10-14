"""Seal full diagnostics and extend only the frozen roster's dated local ID map."""

from __future__ import annotations

import hashlib
import json
import resource
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

import pyarrow.parquet as pq
from build_finite_raw_diagnostic import BASE, OUT, ROOT

TARGET = OUT / "diagnostic-completion"
ROUTE = OUT / "full-cohort-route"


def bind(p):
    return {"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def save(p, obj):
    assert not p.exists(), "preserve_sealed_output"
    p.write_text(json.dumps(obj, indent=2, default=str, allow_nan=False) + "\n")


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (30, 31))
    paths = sorted((TARGET / "cases").glob("*.json"))
    assert len(paths) == 1000
    values = [json.loads(p.read_text()) for p in paths]
    per_symbol = defaultdict(Counter)
    adrs, source_fit, geometry = [], Counter(), Counter()
    for row in values:
        per_symbol[row["symbol"]].update(row["counts"])
        per_symbol[row["symbol"]].update(row["geometry_counts"])
        geometry.update(row["geometry_counts"])
        feature = row["feature"]
        if "ADR20" in feature:
            adr = Decimal(feature["ADR20"])
            adrs.append(adr)
            source_fit["observed_ADR_features"] += 1
            source_fit["ADR_above_source_usual5pct_preference_not_eligibility_rule"] += int(
                adr > Decimal("0.05")
            )
    result = json.loads((TARGET / "result.json").read_text())
    assert sum(r["counts"]["cells"] for r in values) == 1000
    summary = {
        "actual_result": result,
        "per_symbol": {k: dict(v) for k, v in per_symbol.items()},
        "source_fit_only": {**dict(source_fit), "ADR_min": min(adrs), "ADR_max": max(adrs)},
        "selection": "All original25 hash-frozen issues x first40 frozen sessions; none resampled",
        "numeric_geometry_is_not_eligibility_fill_or_PnL": True,
        "full101_rank_and_episode_seed": None,
        "AVWAP_missing_not_EMA_fallback_block": True,
        "SGEN_slots_retained": per_symbol["SGEN"],
        "firstvisible": None,
    }
    save(TARGET / "summary.json", summary)
    previous = json.loads((OUT / "identity-candidates.json").read_text())
    roster = json.loads((OUT / "frozen-historical-roster.json").read_text())["rows"]
    candidates = []
    wanted = {r["cusip"] for r in roster}
    ftd_sources = []
    for src in previous["FTD_sources"]:
        path = ROOT / src["path"]
        assert bind(path) == src
        ftd_sources.append(src)
        rows = pq.read_table(
            path, columns=["settlement_date", "cusip", "symbol", "description"]
        ).to_pylist()
        candidates.extend(
            r for r in rows if r["cusip"] in wanted and r["settlement_date"] < date(2024, 1, 2)
        )
    mapping = []
    for issue in sorted(roster, key=lambda r: r["diagnostic_hash"]):
        points = sorted(
            (r for r in candidates if r["cusip"] == issue["cusip"]),
            key=lambda r: (r["settlement_date"], r["symbol"]),
        )
        recent = (
            [r for r in points if r["settlement_date"] == points[-1]["settlement_date"]]
            if points
            else []
        )
        symbols = sorted({r["symbol"] for r in recent if r["symbol"]})
        symbol = issue["ticker"] or (symbols[0] if len(symbols) == 1 else None)
        mapping.append(
            {
                "issue_key": issue["issue_key"],
                "diagnostic_hash": issue["diagnostic_hash"],
                "source_ticker_candidate": symbol,
                "roster_name": issue["name"],
                "source_issue_title": issue["title"],
                "NPORT_ticker": issue["ticker"],
                "FTD_dated_points": recent,
                "episode_validity_interval": None,
                "first_real_episode_EMA_seed": None,
                "qualification": "actual_dated_identity_candidate_not_interval_certificate",
                "no_current_map_no_resample": True,
            }
        )
    assert len(mapping) == 101
    assert all(mapping[i]["issue_key"] == previous["records"][i]["issue_key"] for i in range(25))
    ROUTE.mkdir(exist_ok=True)
    save(
        ROUTE / "identity-candidates.json",
        {
            "roster": bind(OUT / "frozen-historical-roster.json"),
            "FTD_sources": ftd_sources,
            "records": mapping,
            "resolved": sum(bool(r["source_ticker_candidate"]) for r in mapping),
            "unknown_retained": sum(not r["source_ticker_candidate"] for r in mapping),
            "first25_unchanged": True,
            "new_source_market_requests": 0,
            "source_publication_or_life_interval_certified": False,
        },
    )
    save(
        TARGET / "accounting.json",
        {
            "previous_Martin_CPU": 261.44,
            "lint_failure_CPU": 0.03,
            "completed_diagnostic_CPU": 36.46,
            "summary_lint_failures_CPU": 0.13,
            "setup_reads_code_seal_handoff_conservative_CPU": 10,
            "Martin_CPU_before_this_summary_job": 308.06,
            "original_cap": 2000,
            "old120_tranche119_98_unchanged_and_already_in261_44": True,
            "summary_job_profile": (
                "summary-resource.txt; append actual charge to sole current-state"
            ),
            "comparison_CPU": 223.53,
            "source_units_used_cap": [37, 40],
            "aggregate_market_used_requests_bytes": [60, 43895341],
            "aggregate_market_remaining_requests_bytes": [36, 90322387],
            "economic_CPU_used_allocated": [0, 0],
            "new_network_calls": 0,
        },
    )
    bindings = [bind(p) for p in paths]
    bindings += [
        bind(TARGET / name)
        for name in (
            "config.json",
            "result.json",
            "summary.json",
            "accounting.json",
            "resource.txt",
            "lint-attempt1-resource.txt",
            "summary-lint-attempt1-resource.txt",
            "summary-lint-attempt2-resource.txt",
            "fresh-memory-run1.json",
        )
    ]
    bindings += [
        bind(BASE / "code" / name)
        for name in ("complete_existing_raw_diagnostic.py", "summarize_completed_raw_diagnostic.py")
    ]
    bindings.append(bind(ROUTE / "identity-candidates.json"))
    save(
        TARGET / "manifest.json",
        {
            "scope": "Fixed25x40 causal features/raw-minute geometry; no economics",
            "files": bindings,
            "original_accepted_manifest": bind(OUT / "actual-diagnostic-package-manifest.json"),
            "root_pool_authority": bind(OUT / "root-task-pool-continuation.json"),
            "no_old_author_sealed_or_independent_receipt_modified": True,
            "first_episode_seed_rank_and_full_economic_input_not_upgraded": True,
        },
    )
    print(
        json.dumps(
            {
                "manifest": bind(TARGET / "manifest.json"),
                "counts": result,
                "full101_resolved": sum(bool(r["source_ticker_candidate"]) for r in mapping),
            },
            default=str,
        )
    )


if __name__ == "__main__":
    main()
