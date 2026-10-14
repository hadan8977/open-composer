"""Reviewed finite-cohort source intake, reusing the accepted bounded transport."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import resource
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from open_composer.market_sessions import us_equity_session_dates

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "revisions/v3-finite-qqq"
DECISION = BASE / "continuity-source-locator/root-scope-and-resource-decision.json"
AUTHOR = "f9add224-744b-471c-b812-c43cc179fa38"
SPEC = importlib.util.spec_from_file_location(
    "accepted_intake", BASE / "code/acquire_components.py"
)
INTAKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INTAKE)
save = INTAKE.save
bind = INTAKE.binding


def guard():
    assert os.sched_getaffinity(0) == {0}
    resource.setrlimit(resource.RLIMIT_CPU, (45, 46))
    decision = json.loads(DECISION.read_text())
    assert decision["author"] == AUTHOR and decision["allocation"]["requests_max"] == 48
    review = json.loads((OUT / "independent-delta-review.json").read_text())
    assert review["reviewer"] != AUTHOR
    assert review["verdict"] in (
        "approve_deep_plan",
        "approve_affected_delta_and_bounded_input_entry",
    )
    for item in review["entry_bindings"]:
        assert bind(ROOT / item["path"]) == item
    assert decision["allocation"]["economic_CPU_allocated_now"] == 0
    hold = json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())
    day = json.loads((ROOT / "reports/research/control/day-goal.json").read_text())
    assert hold["research_paused"] is False
    task = [t for t in day["tasks"] if t["id"] == "USIC-PRACTITIONER-RESEARCH"]
    assert len(task) == 1 and task[0]["active_owner"] == AUTHOR


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def value(node, name):
    found = next((c for c in node.iter() if local_name(c.tag) == name), None)
    return None if found is None else (found.text or found.attrib.get("value", "")).strip()


def parse_roster(body):
    tree = ET.fromstring(body)
    report_date = value(tree, "repPdDate")
    assert report_date == "2023-09-30", "actual_holdings_date_required"
    assert "QQQ" in (value(tree, "regName") or ""), "actual_QQQ_registrant_required"
    rows = []
    for ordinal, node in enumerate(n for n in tree.iter() if local_name(n.tag) == "invstOrSec"):
        row = {
            k: value(node, k)
            for k in ("name", "title", "cusip", "assetCat", "issuerCat", "invCountry")
        }
        row.update(
            source_ordinal=ordinal,
            isin=value(node, "isin"),
            ticker=value(node, "ticker"),
            source_holdings_date=report_date,
            historical_first_visible=None,
        )
        row["issue_key"] = (row["cusip"] or "") + "|" + (row["isin"] or "")
        row["diagnostic_hash"] = hashlib.sha256(
            ("USIC-RAW-BRIDGE-20261013|" + row["issue_key"]).encode()
        ).hexdigest()
        row["source_equity_common"] = row["assetCat"] == "EC"
        row["US_listing_episode_certified"] = False
        rows.append(row)
    assert rows and any(r["cusip"] == "88160R101" for r in rows)
    common = [r for r in rows if r["source_equity_common"]]
    assert len({r["issue_key"] for r in common}) == len(common), "retain_duplicate_issue_stop"
    assert all(r["issue_key"] != "|" for r in common)
    return rows, sorted(common, key=lambda r: (r["diagnostic_hash"], r["issue_key"]))[:25]


def source_phase():
    path = OUT / "source-request-ledger.json"
    assert not path.exists(), "no_implicit_source_rerun"
    import httpx

    scope = json.loads((OUT / "input-scope.json").read_text())
    ledger = {
        "pool": "originalMartin40publicunits",
        "prior_units": 35,
        "attempts": [],
        "direct_entity_bytes": 0,
        "unknown_reserved_bytes": 0,
        "Root_web_operations": {"open": 2, "find": 3, "HTTP": None, "wire": None},
    }
    save(path, ledger)
    roster = diagnostic = None
    with httpx.Client(
        timeout=25, headers={"User-Agent": "OpenComposer public-filing research/1.0"}
    ) as client:
        for spec in scope["source_form_requests"]:
            attempt = {
                "url": spec["url"],
                "requested_at": INTAKE.utc(),
                "reserved_bytes": spec["entity_cap"],
                "status": "started",
            }
            ledger["attempts"].append(attempt)
            ledger["unknown_reserved_bytes"] += spec["entity_cap"]
            save(path, ledger)
            try:
                body, packet = INTAKE.bounded_get(client, spec["url"], {}, spec["entity_cap"])
            except Exception as exc:
                attempt.update(status="transport_failure", exception_type=type(exc).__name__)
                save(path, ledger)
                break
            entity = OUT / "source-entities" / f"nport-{len(ledger['attempts'])}.bin"
            entity.parent.mkdir(exist_ok=True)
            entity.write_bytes(body)
            attempt.update(
                packet,
                entity=bind(entity),
                retained_bytes=len(body),
                current_fetched_at=INTAKE.utc(),
                historical_first_visible=None,
            )
            if packet["entity_complete"]:
                ledger["unknown_reserved_bytes"] -= spec["entity_cap"]
                ledger["direct_entity_bytes"] += len(body)
            if packet["http_status"] in (401, 403, 429) or not packet["entity_complete"]:
                attempt["status"] = "source_stop_no_retry"
                save(path, ledger)
                break
            if packet["http_status"] == 200:
                try:
                    roster, diagnostic = parse_roster(body)
                    attempt["status"] = "complete_actual_XML_roster"
                    break
                except (ET.ParseError, AssertionError) as exc:
                    attempt.update(
                        status="source_representation_not_certified",
                        parse_exception_type=type(exc).__name__,
                    )
            save(path, ledger)
    ledger["finished_at"] = INTAKE.utc()
    ledger["public_units_cumulative"] = 35 + len(ledger["attempts"])
    ledger["complete_roster"] = roster is not None
    save(path, ledger)
    if roster is None:
        save(
            OUT / "source-result.json",
            {
                "verdict": "actual_form_intake_failed_no_fabricated_roster_or_new_market_call",
                "ledger": bind(path),
                "economic_input_ready": False,
                "firstvisible_null_not_failure_reason": True,
            },
        )
        return
    # Freeze all actual issues and hash-selected diagnostic slots before any market values.
    frozen = OUT / "frozen-historical-roster.json"
    save(
        frozen,
        {
            "source": ledger["attempts"][-1]["entity"],
            "rows": roster,
            "selected_issue_keys": [r["issue_key"] for r in diagnostic],
            "publication_certified": False,
            "market_values_used_for_selection": False,
        },
    )
    import pyarrow.parquet as pq

    cusips = {r["cusip"] for r in diagnostic if r["cusip"]}
    candidates = []
    ftd_bindings = []
    for filename in scope["local_identity_files"]:
        file = ROOT / filename
        ftd_bindings.append(bind(file))
        rows = pq.read_table(
            file, columns=["settlement_date", "cusip", "symbol", "description"]
        ).to_pylist()
        candidates += [
            r for r in rows if r["cusip"] in cusips and r["settlement_date"] < date(2024, 1, 2)
        ]
    mapping = []
    for issue in diagnostic:
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
                "NPORT_ticker": issue["ticker"],
                "FTD_dated_points": [
                    {**r, "settlement_date": str(r["settlement_date"])} for r in recent
                ],
                "episode_validity_interval": None,
                "qualification": ("actual_dated_identity_candidate_not_interval_certificate")
                if symbol
                else "unresolved_mapping_retained",
                "no_current_map_no_resample": True,
            }
        )
    save(
        OUT / "identity-candidates.json",
        {
            "roster": bind(frozen),
            "FTD_sources": ftd_bindings,
            "records": mapping,
            "FTD_price_quantity_columns_read": False,
        },
    )
    symbols = sorted(
        {r["source_ticker_candidate"] for r in mapping if r["source_ticker_candidate"]}
    )
    assert all(INTAKE.urlparse("https://data.alpaca.markets").scheme == "https" for _ in symbols)
    assert all(__import__("re").fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", s) for s in symbols)
    requests = materialize_requests(symbols) if symbols else []
    save(
        OUT / "exact-materialized-request-manifest.json",
        {
            "scope": bind(OUT / "input-scope.json"),
            "roster": bind(frozen),
            "identity_candidates": bind(OUT / "identity-candidates.json"),
            "resolved_diagnostic_symbols": symbols,
            "diagnostic_slots": len(diagnostic),
            "missing_slots_not_resampled": 25 - len(symbols),
            "requests": requests,
            "not_investment_cohort": True,
            "full_rank_NA": True,
        },
    )
    save(
        OUT / "source-result.json",
        {
            "verdict": ("actual_roster_frozen_diagnostic_manifest_materialized"),
            "all_issue_rows": len(roster),
            "diagnostic_slots": len(diagnostic),
            "resolved_symbols": len(symbols),
            "economic_input_ready": False,
        },
    )


def materialize_requests(symbols):
    scope = json.loads((OUT / "input-scope.json").read_text())
    requests = []
    for spec in scope["market_prefix_objects"]:
        spec = json.loads(json.dumps(spec))
        if spec["params"].get("symbols") == "FROZEN_DIAGNOSTIC_SYMBOLS":
            spec["params"]["symbols"] = ",".join(symbols)
        requests.append(spec)
    ny = ZoneInfo("America/New_York")
    days = us_equity_session_dates(date(2024, 1, 1), date(2024, 12, 31))[:40]
    for day in days:
        start = (
            datetime.combine(day, time(9, 30), ny)
            .astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
        end = (
            datetime.combine(day, time(15, 59, 59), ny)
            .astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
        requests.append(
            {
                "id": "raw_RTH_" + day.isoformat(),
                "path": "/stocks/bars",
                "params": {
                    "symbols": ",".join(symbols),
                    "timeframe": "1Min",
                    "start": start,
                    "end": end,
                    "adjustment": "raw",
                    "feed": "sip",
                    "asof": "-",
                    "sort": "asc",
                    "limit": 10000,
                },
                "max_pages": 1,
                "per_page_byte_cap": 1310720,
            }
        )
    assert sum(r["max_pages"] for r in requests) == 48
    assert sum(r["max_pages"] * r["per_page_byte_cap"] for r in requests) == 65011712
    return requests


def market_phase():
    path = OUT / "exact-materialized-request-manifest.json"
    manifest = json.loads(path.read_text())
    assert manifest["roster"] == bind(OUT / "frozen-historical-roster.json")
    assert manifest["identity_candidates"] == bind(OUT / "identity-candidates.json")
    expected = materialize_requests(manifest["resolved_diagnostic_symbols"])
    assert manifest["requests"] == expected and expected
    from open_composer.adapters.data.alpaca_snapshot import _stock_data_client
    from open_composer.cli import _load_env

    _load_env()
    transport = _stock_data_client()
    INTAKE.SCOPE_SHA = bind(path)["sha256"]
    try:
        ledger = INTAKE.collect(
            {"requests": expected},
            {"requests": 48, "entity_bytes": 65011712},
            transport._client,
            OUT / "market",
        )
    finally:
        transport.close()
    print(
        json.dumps(
            {
                "actual_market_requests": ledger["requests_used"],
                "actual_complete_entity_bytes": ledger["complete_entity_bytes"],
            }
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["source", "market", "offline"])
    args = parser.parse_args()
    if args.stage == "offline":
        scope = json.loads((OUT / "input-scope.json").read_text())
        assert len(scope["source_form_requests"]) <= 2
        items = materialize_requests(["OFFLINE"])
        print(
            json.dumps(
                {
                    "market_calls_upper": sum(r["max_pages"] for r in items),
                    "network_calls": 0,
                    "credentials_initialized": False,
                }
            )
        )
        return
    guard()
    (source_phase if args.stage == "source" else market_phase)()


if __name__ == "__main__":
    main()
