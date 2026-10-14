"""Bounded local metadata and cached stock NBBO/RF component intake, offline only."""

import csv
import hashlib
import json
import math
import resource
import time
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[5]
NY = ZoneInfo("America/New_York")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    started = time.monotonic()
    caps = json.loads((OUT / "selection.json").read_text())["stage_caps_no_reset"]
    inputs, cache_rows, meta_files, meta_bytes = [], [], 0, 0

    def bind(p, role):
        r = {
            "path": str(p.relative_to(ROOT)),
            "bytes": p.stat().st_size,
            "sha256": sha(p),
            "role": role,
        }
        inputs.append(r)
        return r

    def metadata(p):
        nonlocal meta_files, meta_bytes
        meta_files += 1
        meta_bytes += p.stat().st_size
        assert meta_files <= caps["metadata_json_files_max"]
        assert meta_bytes <= caps["metadata_bytes_max"]
        bind(p, "metadata_only")
        return json.loads(p.read_text())

    for p in sorted((ROOT / "data/cache/manifests").glob("*.json")):
        m = metadata(p)
        raw = m.get("adjustment") == "raw" or m.get("request_params", {}).get("adjustment") == "raw"
        reasons = []
        for condition, reason in [
            (raw, "raw_unadjusted_request_not_proved"),
            (m.get("timeframe") == "daily", "not_daily_price_primitive"),
            (m.get("corporate_action_manifest"), "no_bound_complete_action_or_no_action_chain"),
            (m.get("security_episode_manifest"), "historical_common_share_episode_not_bound"),
            (
                m.get("historical_visible_at_manifest"),
                "historical_bar_visibility_vintage_not_bound",
            ),
        ]:
            if not condition:
                reasons.append(reason)
        cache_rows.append(
            {
                "manifest": str(p.relative_to(ROOT)),
                "manifest_sha256": sha(p),
                "symbol": m.get("symbol"),
                "provider": m.get("provider"),
                "feed": m.get("feed"),
                "timeframe": m.get("timeframe"),
                "adjustment": m.get("adjustment"),
                "request_params": m.get("request_params"),
                "records": m.get("records"),
                "first_timestamp": m.get("first_timestamp"),
                "last_timestamp": m.get("last_timestamp"),
                "cache_path": m.get("cache_path"),
                "explicit_raw": raw,
                "price3_qualified": not reasons,
                "reasons": reasons,
            }
        )
    snapshot_path = (
        ROOT / "data/forward/alpaca_multiasset_paper_control_r7/2026-08-03/snapshot-manifest.json"
    )
    bundle = metadata(snapshot_path)
    bundle_summary = {
        "path": str(snapshot_path.relative_to(ROOT)),
        "symbols": sorted({i["symbol"] for i in bundle["items"]}),
        "item_count": len(bundle["items"]),
        "retrieved_at": bundle["retrieved_at"],
        "adjustments": bundle["adjustment_policy"]["requested_adjustments"],
        "contract_path": bundle["contract_path"],
        "reason": (
            "Versioned raw/split/dividend/all fund/control bundle, "
            "not stock episode/action chain; no ETF substitution or numerical bar read."
        ),
    }

    probe = ROOT / "reports/research/program/day-goal-20261011-2/chinco-raw-quote-probe"
    metadata(probe / "request-manifest.json")
    request_receipt = metadata(probe / "execution-receipt.json")
    quote_components, quote_coverage, quote_rows, quote_bytes = [], [], 0, 0
    for request in request_receipt["requests"]:
        p = ROOT / request["raw_path"]
        p.resolve().relative_to(probe.resolve())
        assert sha(p) == request["raw_sha256"]
        payload = json.loads(p.read_bytes())
        binding = bind(p, "existing_stock_NBBO_entity")
        symbol = request["params"]["symbols"]
        records = payload["quotes"][symbol]
        quote_rows += len(records)
        quote_bytes += binding["bytes"]
        assert quote_bytes <= caps["raw_quote_bytes_max"]
        candidates, good_clock = [], 0
        for ordinal, q in enumerate(records):
            bid, ask = float(q["bp"]), float(q["ap"])
            good = math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask
            stamp = datetime.fromisoformat(q["t"].replace("Z", "+00:00")).astimezone(NY)
            clock_ok = stamp.hour == 9 and stamp.minute == 45 and stamp.second <= 5
            good_clock += bool(good and clock_ok)
            if good:
                candidates.append((q["t"], ordinal, q))
        for _, ordinal, q in sorted(candidates)[:3]:
            quote_components.append(
                {
                    "component": "stock_NBBO_source_fields_only",
                    "symbol": symbol,
                    "window_id": request["window_id"],
                    "source_path": binding["path"],
                    "source_sha256": binding["sha256"],
                    "source_ordinal": ordinal,
                    "source_record_sha256": hashlib.sha256(
                        json.dumps(q, sort_keys=True).encode()
                    ).hexdigest(),
                    "record": q,
                    "fetched_at": request["finished_utc"],
                    "APP_0945_endpoint_qualified": False,
                    "reason": (
                        "Observed stock quotes at10:00NY, not approved09:45window; "
                        "no label/horizon substitution."
                    ),
                }
            )
        quote_coverage.append(
            {
                "window_id": request["window_id"],
                "symbol": symbol,
                "requested_start": request["params"]["start"],
                "requested_end": request["params"]["end"],
                "quote_rows": len(records),
                "positive_noncrossed": len(candidates),
                "eligible_0945_rows": good_clock,
                "pagination_complete": payload.get("next_page_token") is None,
                "missing_packet": (
                    "Same stock and session09:45:00..05 plus next-session same-clock entity; "
                    "these10:00entities cover neither."
                ),
            }
        )
    assert len(request_receipt["requests"]) <= caps["raw_quote_files_max"]

    pressure = (
        ROOT
        / "reports/research/program/day-goal-20261013/pressure-event-return/inputs"
        / "market-request-ledger.json"
    )
    pressure_records = metadata(pressure)
    pressure_summary = [
        {
            "name": r["name"],
            "params": r["params"],
            "binding": r.get("binding"),
            "numeric_rows_decoded": 0,
            "reason": (
                "Fund/control request scope, not a qualified stock episode. "
                "Metadata only; no corpus duplication."
            ),
        }
        for r in pressure_records
        if r.get("ok")
    ]

    french = ROOT / "reports/research/program/regime-french-source-20261010-1917"
    fetched = metadata(french / "receipt.json")["requests"][0]
    schema = metadata(french / "schema-evidence.json")
    p = french / "official-daily.zip"
    assert sha(p) == fetched["sha256"]
    bind(p, "existing_official_RF_zip_six_numeric_rows_only")
    rf_components = []
    with zipfile.ZipFile(p) as archive:
        member_name = schema["member_name"]
        assert archive.getinfo(member_name).file_size < 2 * 1024 * 1024
        with archive.open(member_name) as member:
            for ordinal, line in enumerate(member):
                cells = next(csv.reader([line.decode("utf-8-sig").strip()]))
                if len(cells) != 5 or len(cells[0].strip()) != 8 or not cells[0].strip().isdigit():
                    continue
                observation_date = cells[0].strip()
                if observation_date < "20160104":
                    continue
                text = cells[4].strip()
                value = float(text)
                assert math.isfinite(value) and value not in {-99.99, -999}
                rf_components.append(
                    {
                        "component": "official_RF_observation_not_causal_APP_Rf",
                        "observation_date": observation_date,
                        "source_value_text": text,
                        "source_unit": "daily_percent",
                        "value_decimal": value / 100,
                        "source_zip": str(p.relative_to(ROOT)),
                        "source_zip_sha256": fetched["sha256"],
                        "source_member": member_name,
                        "source_line": ordinal + 1,
                        "source_line_sha256": hashlib.sha256(line).hexdigest(),
                        "fetched_at": fetched["fetched_at_utc"],
                        "served_vintage": "202608CRSP; Last-Modified2026-09-25",
                        "historical_published_at": None,
                        "APP_Rf_qualified": False,
                        "reason": (
                            "RF exists; historicalpublication/vintage not bound. "
                            "No full7 or5sessioncarry; no requiredRF capability added."
                        ),
                    }
                )
                if len(rf_components) == 6:
                    break
    assert quote_rows + len(rf_components) <= caps["new_raw_record_read_occurrences_max"]

    (OUT / "metadata-coverage.jsonl").write_text("".join(json.dumps(r) + "\n" for r in cache_rows))
    write(
        "partial-source-components.json",
        {
            "stock_NBBO_examples": quote_components,
            "RF_observations": rf_components,
            "price3": [],
            "full7": [],
            "0945labels": [],
        },
    )
    result = {
        "scope": "Existing bounded metadata and source components, not a global market rejection",
        "metadata_json_files_read": meta_files,
        "metadata_bytes": meta_bytes,
        "cache_manifest_count": len(cache_rows),
        "explicit_raw_manifests": sum(x["explicit_raw"] for x in cache_rows),
        "explicit_raw_daily_symbols": sorted(
            {x["symbol"] for x in cache_rows if x["explicit_raw"] and x["timeframe"] == "daily"}
        ),
        "qualified_stock_raw_action_sequences": sum(x["price3_qualified"] for x in cache_rows),
        "new_stock_price_value_files_read": 0,
        "new_stock_price_rows_read": 0,
        "stock_NBBO_rows_read": quote_rows,
        "RF_numeric_rows_read": len(rf_components),
        "APP_price3_rows": 0,
        "APP_full7_rows": 0,
        "APP_0945_labels": 0,
        "APP_Rf_rows": 0,
        "raw_versioned_bundle": bundle_summary,
        "stock_NBBO_coverage": quote_coverage,
        "other_existing_request_metadata": pressure_summary,
        "price3_stop_reason": (
            "Checked local manifests do not bind raw common-stock prices with complete "
            "action/no-action episode and historicalvisibility/vintage evidence. "
            "Do not compute proxyprice3. Rf/ETB is not the reason to stopprice3."
        ),
        "Rf_stop_reason": (
            "Cached officialFrenchRF exists; historicalpublication/vintage missing. "
            "Registry macro.fred_series points to workflowfixture/latestrevision context, "
            "not this causalRf packet; data/raw/macro has no source file."
        ),
        "label_stop_reason": (
            "BoundstockNBBO data are10:00windows, not09:45pairs. "
            "No approvedendpoint pair/action-chain label; all actualquotes retained at source "
            "and no oldholdings or terminalrights dropped."
        ),
        "whole_direction_refuted": False,
        "economic_input_admitted": False,
        "source_requests_new": 0,
        "market_requests_new": 0,
        "fits": 0,
        "source_inputs": inputs,
    }
    write("local-source-result.json", result)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    receipt = {
        "command": "probe_local_sources.py",
        "cpu_seconds": usage.ru_utime + usage.ru_stime,
        "wall_seconds": time.monotonic() - started,
        "max_rss_kib": usage.ru_maxrss,
        "threads": 1,
        "new_requests": 0,
        "fits": 0,
        "raw_record_read_occurrences": quote_rows + len(rf_components),
    }
    write("probe-receipt.json", receipt)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "metadata_json_files_read",
                    "cache_manifest_count",
                    "explicit_raw_daily_symbols",
                    "stock_NBBO_rows_read",
                    "RF_numeric_rows_read",
                    "APP_price3_rows",
                    "APP_0945_labels",
                )
            }
        )
    )
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
