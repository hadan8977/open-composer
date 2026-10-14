"""One independently accepted declared-transport source repair; no market GET."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import resource
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "revisions/v3-finite-qqq"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ACQ = load_module("finite_bridge_intake", BASE / "code/acquire_finite_cohort_bridge.py")
save, bind = ACQ.save, ACQ.bind


def guard():
    ACQ.guard()
    resource.setrlimit(resource.RLIMIT_CPU, (35, 36))
    receipt = json.loads((OUT / "independent-transport-entry-diff-review.json").read_text())
    assert receipt["verdict"] == "accept_same_source_transport_entry_diff"
    assert receipt["reviewer"] != ACQ.AUTHOR
    assert receipt["prior_method_review"] == bind(
        OUT / "independent-source-access-and-method-review.json"
    )
    for item in receipt["repair_entry_bindings"]:
        assert bind(ROOT / item["path"]) == item
    parent = json.loads((OUT / "source-request-ledger.json").read_text())
    assert parent["public_units_cumulative"] == 36 and len(parent["attempts"]) == 1
    assert parent["attempts"][0]["http_status"] == 403
    assert parent["complete_roster"] is False


def collect_one():
    path = OUT / "source-repair-ledger.json"
    assert not path.exists(), "no_implicit_repair_rerun_or_marker_deletion"
    ledger = {
        "parent403": bind(OUT / "source-request-ledger.json"),
        "method_review": bind(OUT / "independent-source-access-and-method-review.json"),
        "source_units_before": 36,
        "maximum_new_actual_calls": 1,
        "actual_calls": 0,
        "attempts": [],
        "direct_entity_bytes": 0,
        "unknown_reserved_bytes": 0,
        "wire_bytes": None,
        "header_values_recorded": False,
    }
    save(path, ledger)
    sec = load_module("existing_declared_sec_client", ROOT / "scripts/collect_sec_13d_filings.py")
    # Reuse this existing client's normal configuration loader; inspect no other key/value.
    sec.load_dotenv(dotenv_path=ROOT / ".env")
    try:
        client = sec.SecClient()
    except RuntimeError:
        ledger.update(
            status="existing_SEC_USER_AGENT_configuration_missing_local_stop",
            source_units_after=36,
            finished_at=ACQ.INTAKE.utc(),
        )
        save(path, ledger)
        return
    scope = json.loads((OUT / "input-scope.json").read_text())
    url = scope["source_form_requests"][0]["url"]
    cap = 2097152
    attempt = {
        "url": url,
        "requested_at": ACQ.INTAKE.utc(),
        "reserved_bytes": cap,
        "status": "started",
        "current_fetched_at": None,
        "historical_first_visible": None,
    }
    ledger["attempts"].append(attempt)
    ledger.update(actual_calls=1, unknown_reserved_bytes=cap, source_units_after=37)
    save(path, ledger)
    try:
        # Never use SecClient.get: its retry helper is outside this single-call scope.
        body, packet = ACQ.INTAKE.bounded_get(client._client, url, {}, cap)
        target = OUT / "source-repair-entities/nport-1.bin"
        target.parent.mkdir(exist_ok=True)
        with target.open("xb") as handle:
            handle.write(body)
        attempt.update(
            packet,
            entity=bind(target),
            retained_bytes=len(body),
            current_fetched_at=ACQ.INTAKE.utc(),
            status="actual_response_retained",
        )
        if packet["entity_complete"]:
            ledger.update(direct_entity_bytes=len(body), unknown_reserved_bytes=0)
        ledger["status"] = (
            "complete200_for_offline_parse"
            if (packet["http_status"] == 200 and packet["entity_complete"])
            else "source_slot_stop_no_retry_or_fallback"
        )
    except Exception as exc:
        attempt.update(status="transport_failure", exception_type=type(exc).__name__)
        ledger["status"] = "source_slot_stop_no_retry_or_fallback"
    finally:
        client.close()
        ledger["finished_at"] = ACQ.INTAKE.utc()
        save(path, ledger)


def parse_retained():
    path = OUT / "source-repair-ledger.json"
    ledger = json.loads(path.read_text())
    if ledger.get("status") != "complete200_for_offline_parse":
        save(
            OUT / "source-repair-result.json",
            {
                "verdict": ledger["status"],
                "ledger": bind(path),
                "full_roster": False,
                "market_calls": 0,
                "no_fabricated_roster": True,
            },
        )
        return
    attempt = ledger["attempts"][0]
    entity = ROOT / attempt["entity"]["path"]
    assert bind(entity) == attempt["entity"]
    try:
        roster, diagnostic = ACQ.parse_roster(entity.read_bytes())
    except (ACQ.ET.ParseError, AssertionError) as exc:
        save(
            OUT / "source-repair-result.json",
            {
                "verdict": "retained200_schema_unidentified_offline_repair_only",
                "exception_type": type(exc).__name__,
                "exception_detail": str(exc)[:160],
                "ledger": bind(path),
                "entity": bind(entity),
                "market_calls": 0,
            },
        )
        return
    scope = json.loads((OUT / "input-scope.json").read_text())
    frozen = OUT / "frozen-historical-roster.json"
    assert not frozen.exists(), "do_not_overwrite_frozen_cohort"
    save(
        frozen,
        {
            "source": attempt["entity"],
            "rows": roster,
            "selected_issue_keys": [r["issue_key"] for r in diagnostic],
            "publication_certified": False,
            "market_values_used_for_selection": False,
        },
    )
    import pyarrow.parquet as pq

    cusips = {r["cusip"] for r in diagnostic if r["cusip"]}
    candidates, ftd_sources = [], []
    for filename in scope["local_identity_files"]:
        file = ROOT / filename
        ftd_sources.append(bind(file))
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
                "qualification": "actual_dated_identity_candidate_not_interval_certificate"
                if symbol
                else "unresolved_mapping_retained",
                "no_current_map_no_resample": True,
            }
        )
    save(
        OUT / "identity-candidates.json",
        {
            "roster": bind(frozen),
            "FTD_sources": ftd_sources,
            "records": mapping,
            "FTD_price_quantity_columns_read": False,
        },
    )
    symbols = sorted(
        {r["source_ticker_candidate"] for r in mapping if r["source_ticker_candidate"]}
    )
    assert all(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", s) for s in symbols)
    requests = ACQ.materialize_requests(symbols) if symbols else []
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
        OUT / "source-repair-result.json",
        {
            "verdict": "actual_declared_source_roster_frozen_and_manifest_materialized",
            "ledger": bind(path),
            "all_issue_rows": len(roster),
            "diagnostic_slots": len(diagnostic),
            "resolved_symbols": len(symbols),
            "economic_input_ready": False,
            "parent403_unchanged": bind(OUT / "source-request-ledger.json"),
        },
    )
    print(
        json.dumps(
            {
                "all_issues": len(roster),
                "selected": len(diagnostic),
                "resolved_symbols": len(symbols),
                "market_calls": 0,
            }
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["execute", "parse-retained"])
    args = parser.parse_args()
    guard()
    if args.stage == "execute":
        collect_one()
    parse_retained()


if __name__ == "__main__":
    main()
