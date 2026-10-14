"""Bounded cache/raw basis comparison on four existing diagnostic issues."""

from __future__ import annotations

import hashlib
import json
import os
import resource
from collections import Counter, defaultdict
from datetime import UTC
from decimal import Decimal, localcontext

import pyarrow.parquet as pq
from build_finite_raw_diagnostic import BASE, OUT, ROOT

TARGET = OUT / "full-cohort-route/cache-basis-probe"
SYMBOLS = ["PCAR", "ROST", "GEHC", "TSLA"]


def bind(p):
    return {"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def save(p, obj):
    assert not p.exists()
    p.write_text(json.dumps(obj, indent=2, default=str) + "\n")


def main():
    assert os.sched_getaffinity(0) == {0}
    resource.setrlimit(resource.RLIMIT_CPU, (90, 91))
    assert not TARGET.exists()
    TARGET.mkdir()
    layout_path = ROOT / "data/sip/minute/_LAYOUT.json"
    layout = json.loads(layout_path.read_text())
    ledger = json.loads((OUT / "market/request-ledger.json").read_text())
    raw = defaultdict(dict)
    daily_raw, daily_all = defaultdict(dict), defaultdict(dict)
    with localcontext() as ctx:
        ctx.prec = 60
        for attempt in ledger["attempts"]:
            kind = attempt["id"]
            if not kind.startswith("raw_RTH_") and kind not in {
                "diagnostic_daily_raw",
                "diagnostic_daily_all",
            }:
                continue
            payload = json.loads(
                (ROOT / attempt["entity"]["path"]).read_bytes(),
                parse_float=Decimal,
                parse_int=Decimal,
            )
            for s in SYMBOLS:
                for ordinal, r in enumerate(payload.get("bars", {}).get(s, [])):
                    if kind.startswith("raw_RTH_"):
                        key = r["t"]
                        assert key not in raw[s]
                        raw[s][key] = (
                            r,
                            {
                                "entity_sha256": attempt["entity"]["sha256"],
                                "pointer": f"/bars/{s}/{ordinal}",
                            },
                        )
                    else:
                        destination = daily_raw if kind == "diagnostic_daily_raw" else daily_all
                        destination[s][r["t"][:10]] = r
        summaries, bindings = [], [bind(layout_path)]
        for s in SYMBOLS:
            shards = sorted(k for k, v in layout["shard_symbols"].items() if s in v)
            assert len(shards) <= 4, "bounded_locator_not_whole_archive_scan"
            cached = defaultdict(list)
            metadata = []
            for month in ("01", "02"):
                for shard in shards:
                    p = ROOT / f"data/sip/minute/2024/{month}/shard-{shard}.parquet"
                    if not p.exists():
                        metadata.append({"path": str(p.relative_to(ROOT)), "status": "missing"})
                        continue
                    b = bind(p)
                    bindings.append(b)
                    pf = pq.ParquetFile(p)
                    table = pq.read_table(
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
                    )
                    metadata.append(
                        {
                            "file": b,
                            "metadata_rows": pf.metadata.num_rows,
                            "selected_symbol_rows": table.num_rows,
                            "schema": str(table.schema),
                        }
                    )
                    for row in table.to_pylist():
                        t = row["timestamp"].astimezone(UTC).isoformat().replace("+00:00", "Z")
                        if t in raw[s]:
                            cached[t].append((row, b))
            counts, mismatches = Counter(), []
            for t, (r, pointer) in raw[s].items():
                counts["actual_raw_rows"] += 1
                matches = cached.get(t, [])
                if len(matches) != 1:
                    counts["cache_missing_or_duplicate"] += 1
                    continue
                c, b = matches[0]
                counts["unique_time_matches"] += 1
                fields = (
                    ("o", "open"),
                    ("h", "high"),
                    ("l", "low"),
                    ("c", "close"),
                    ("v", "volume"),
                    ("n", "trade_count"),
                    ("vw", "vwap"),
                )
                equal = {k: r[k] == Decimal(str(c[ck])) for k, ck in fields}
                for k, v in equal.items():
                    counts[f"exact_{k}"] += int(v)
                counts["exact_all_7_fields"] += int(all(equal.values()))
                counts["exact_OHLC4"] += int(all(equal[k] for k in ("o", "h", "l", "c")))
                if not all(equal.values()) and len(mismatches) < 3:
                    factor = daily_raw[s][t[:10]]["c"] / daily_all[s][t[:10]]["c"]
                    mismatches.append(
                        {
                            "t": t,
                            "raw_pointer": pointer,
                            "cache_file": b,
                            "cache_predicate_key": [s, t],
                            "raw": r,
                            "cached": c,
                            "current_daily_raw_all_close_factor": factor,
                            "scaled_cached_close": Decimal(str(c["close"])) * factor,
                            "scaled_minus_actual_raw_close": Decimal(str(c["close"])) * factor
                            - r["c"],
                            "factor_is_probe_not_certified_inverse": True,
                        }
                    )
            record = {
                "symbol": s,
                "locator_shards": shards,
                "source_files": metadata,
                "counts": dict(counts),
                "counterexamples": mismatches,
                "entire2024_25_raw_cache_certified": False,
                "no_fitted_inverse_or_price_repair": True,
                "basis_and_version_not_upgraded_by_sample_equality": True,
            }
            save(TARGET / f"{s}.json", record)
            summaries.append({"symbol": s, "counts": dict(counts)})
        save(
            TARGET / "result.json",
            {
                "selection": "First3 frozen hashes plus existingTSLA nonaction control",
                "not_new_investment_population": True,
                "symbols": summaries,
                "raw_price_field_disagreement_observed": any(
                    r["counts"].get("unique_time_matches", 0) > r["counts"].get("exact_OHLC4", 0)
                    for r in summaries
                ),
                "current_daily_factor_not_automatically_old_cache_inverse": True,
                "full_execution_route_not_certified": True,
                "new_market_source_calls": 0,
                "mounted_filesystem_wire_requests_bytes": None,
            },
        )
        save(
            TARGET / "manifest.json",
            {
                "files": bindings + [bind(p) for p in sorted(TARGET.glob("*.json"))],
                "code": bind(BASE / "code/probe_exact_cached_basis.py"),
                "original_market_ledger": bind(OUT / "market/request-ledger.json"),
            },
        )
    print(json.dumps(summaries))


if __name__ == "__main__":
    main()
