"""Bind three actual source probes and compare observed price representations."""

from __future__ import annotations

import hashlib
import json
import os
import resource
from collections import Counter
from datetime import UTC, date
from decimal import Decimal, localcontext

import pyarrow.parquet as pq
from build_finite_raw_diagnostic import BASE, OUT, ROOT, feature_row, stamp

PROBES = OUT / "full-cohort-route/source-link-probes"


def bind(p):
    return {"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def save(name, obj):
    p = PROBES / name
    assert not p.exists()
    p.write_text(json.dumps(obj, indent=2, default=str, allow_nan=False) + "\n")


def main():
    assert os.sched_getaffinity(0) == {0}
    resource.setrlimit(resource.RLIMIT_CPU, (30, 31))
    ledger = json.loads((PROBES / "market/request-ledger.json").read_text())
    assert ledger["requests_used"] == 3
    entities, payloads, summaries = [], {}, []
    with localcontext() as ctx:
        ctx.prec = 60
        for a in ledger["attempts"]:
            p = ROOT / a["entity"]["path"]
            assert bind(p) == a["entity"] and a["http_status"] == 200 and a["entity_complete"]
            entities.append(a["entity"])
            b = json.loads(p.read_bytes(), parse_float=Decimal, parse_int=Decimal)
            assert b["next_page_token"] is None
            payloads[a["id"]] = b
            summaries.append(
                {
                    "id": a["id"],
                    "source": a["entity"],
                    "symbols": [
                        {
                            "symbol": s,
                            "rows": len(rows),
                            "first_observed_t": rows[0]["t"] if rows else None,
                            "last_observed_t": rows[-1]["t"] if rows else None,
                        }
                        for s, rows in b["bars"].items()
                    ],
                    "source_first_last_is_not_validity_or_birth": True,
                    "historical_first_visible": None,
                    "current_fetched_at": a["current_fetched_at"],
                }
            )
        old = json.loads((OUT / "market/request-ledger.json").read_text())
        raw_day = next(a for a in old["attempts"] if a["id"] == "raw_RTH_2024-01-02")
        raw = json.loads(
            (ROOT / raw_day["entity"]["path"]).read_bytes(), parse_float=Decimal, parse_int=Decimal
        )["bars"]
        current = payloads["four_current_vintage_all_minute"]["bars"]
        comparisons = []
        for s in ("PCAR", "ROST", "GEHC", "TSLA"):
            previous = json.loads(
                (OUT / f"full-cohort-route/cache-basis-probe/{s}.json").read_text()
            )
            source = next(
                m["file"]
                for m in previous["source_files"]
                if "file" in m and "/2024/01/" in m["file"]["path"]
            )
            p = ROOT / source["path"]
            assert bind(p) == source
            rows = pq.read_table(
                p,
                columns=[
                    "symbol",
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "trade_count",
                    "vwap",
                ],
                filters=[("symbol", "==", s)],
            ).to_pylist()
            cache = {
                r["timestamp"].astimezone(UTC).isoformat().replace("+00:00", "Z"): r for r in rows
            }
            all_by_t = {r["t"]: r for r in current[s]}
            counts, examples, inverse, collisions = Counter(), [], {}, []
            for ordinal, r in enumerate(raw[s]):
                t = r["t"]
                if t not in all_by_t or t not in cache:
                    counts["missing_match"] += 1
                    continue
                a, c = all_by_t[t], cache[t]
                fields = (
                    ("o", "open"),
                    ("h", "high"),
                    ("l", "low"),
                    ("c", "close"),
                    ("v", "volume"),
                    ("n", "trade_count"),
                    ("vw", "vwap"),
                )
                counts["matched_rows"] += 1
                counts["raw_equals_current_all_7"] += int(all(r[k] == a[k] for k, _ in fields))
                counts["cache_equals_current_all_7"] += int(
                    all(Decimal(str(c[ck])) == a[k] for k, ck in fields)
                )
                counts["raw_current_volume_and_trades_equal"] += int(
                    r["v"] == a["v"] and r["n"] == a["n"]
                )
                if len(examples) < 2 and any(Decimal(str(c[ck])) != a[k] for k, ck in fields):
                    examples.append(
                        {
                            "t": t,
                            "raw": r,
                            "current_ALL": a,
                            "oldcache": c,
                            "raw_pointer": f"/bars/{s}/{ordinal}",
                            "cache_file": source,
                        }
                    )
                key = a["h"]
                previous_pair = inverse.get(key)
                if previous_pair and previous_pair["raw_h"] != r["h"] and len(collisions) < 2:
                    collisions.append(
                        {
                            "same_current_ALL_high": key,
                            "pairs": [
                                previous_pair,
                                {"t": t, "raw_h": r["h"], "raw_pointer": f"/bars/{s}/{ordinal}"},
                            ],
                        }
                    )
                inverse.setdefault(
                    key, {"t": t, "raw_h": r["h"], "raw_pointer": f"/bars/{s}/{ordinal}"}
                )
            comparisons.append(
                {
                    "symbol": s,
                    "counts": dict(counts),
                    "actual_version_examples": examples,
                    "current_ALL_high_collisions": collisions,
                    "not_raw_inverse_or_fullperiod_certificate": True,
                }
            )
        prefix = {}
        for a in old["attempts"]:
            if a["id"] == "diagnostic_daily_raw":
                b = json.loads(
                    (ROOT / a["entity"]["path"]).read_bytes(),
                    parse_float=Decimal,
                    parse_int=Decimal,
                )
                prefix.update({stamp(r).date(): r for r in b["bars"].get("GEHC", [])})
        earlier = payloads["GEHC_GEHCV_birth_prefix"]["bars"]
        extended = {**{stamp(r).date(): r for r in earlier["GEHC"]}, **prefix}
        old_feature = feature_row("GEHC", date(2024, 1, 2), prefix, [])
        extended_feature = feature_row("GEHC", date(2024, 1, 2), extended, [])
        save(
            "actual-result.json",
            {
                "actual_source_packets": summaries,
                "current_ALL_oldcache_raw_comparisons": comparisons,
                "GEHC_source_window_sensitivity": {
                    "old_July_source_window": old_feature,
                    "earlier_regular_symbol_window": extended_feature,
                    "GEHCV_whenissued_prefix_not_silently_joined": True,
                    "neither_window_certified_first_real_episode_seed": True,
                    "old1000_diagnostic_and_frozen_definition_unchanged": True,
                },
                "TSLA_cold_packet": "Pre2016 complete200 empty; no older seed in this packet",
                "not_global_data_absence_or_all_symbols_provider_bound": True,
                "source_history_birth_qualification_still_unknown": True,
                "locator_historical_SHA_mismatch_retained_current_snapshot_only": True,
                "strict_full101_input_ready": False,
                "economic_execution_admitted": False,
                "aggregate_market_requests_used": 63,
                "aggregate_complete_entity_bytes": 44065545,
                "aggregate_remaining_requests_bytes": [33, 90152183],
                "unused_reservation_bytes_released_after_complete3pages": 4548388,
                "new_source_public_units": 0,
                "source_public_used_cap": [37, 40],
            },
        )
        paths = [
            PROBES / "request-manifest.json",
            PROBES / "independent-entry-acceptance.json",
            PROBES / "independent-current-layout-snapshot.json",
            PROBES / "market/request-ledger.json",
            PROBES / "acquisition-resource.txt",
            PROBES / "actual-result.json",
            BASE / "code/build_source_link_probe_result.py",
        ]
        save(
            "actual-manifest.json",
            {
                "files": [bind(p) for p in paths] + entities,
                "role": "Same-cohort source evidence; no scientific or economic upgrade",
                "old_accepted_packages_unmodified": True,
            },
        )
    print(
        json.dumps(
            {
                "manifest": bind(PROBES / "actual-manifest.json"),
                "comparisons": [
                    {"symbol": r["symbol"], "counts": r["counts"]} for r in comparisons
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
