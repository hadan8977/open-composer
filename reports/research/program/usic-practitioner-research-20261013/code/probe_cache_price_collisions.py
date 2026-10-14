"""Test unique inverse-price support using retained raw/cache pairs; no trading."""

from __future__ import annotations

import hashlib
import json
import os
import resource
from decimal import ROUND_CEILING, Decimal, localcontext

import pyarrow.parquet as pq
from build_finite_raw_diagnostic import OUT, ROOT

TARGET = OUT / "full-cohort-route/cache-price-collisions.json"


def main():
    assert os.sched_getaffinity(0) == {0}
    resource.setrlimit(resource.RLIMIT_CPU, (30, 31))
    assert not TARGET.exists()
    ledger = json.loads((OUT / "market/request-ledger.json").read_text())
    attempt = next(a for a in ledger["attempts"] if a["id"] == "raw_RTH_2024-01-02")
    data = json.loads(
        (ROOT / attempt["entity"]["path"]).read_bytes(), parse_float=Decimal, parse_int=Decimal
    )["bars"]
    records = []
    with localcontext() as ctx:
        ctx.prec = 60
        for symbol in ("PCAR", "ROST", "GEHC", "TSLA"):
            p = OUT / f"full-cohort-route/cache-basis-probe/{symbol}.json"
            probe = json.loads(p.read_text())
            files = [
                m["file"]
                for m in probe["source_files"]
                if "file" in m and "/2024/01/" in m["file"]["path"]
            ]
            assert len(files) == 1
            src = files[0]
            path = ROOT / src["path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == src["sha256"]
            table = pq.read_table(
                path,
                columns=["symbol", "timestamp", "high", "close"],
                filters=[("symbol", "==", symbol)],
            )
            cache = {
                r["timestamp"].isoformat().replace("+00:00", "Z"): r for r in table.to_pylist()
            }
            grouped, examples = {}, []
            for ordinal, raw in enumerate(data.get(symbol, [])):
                t = raw["t"]
                if t not in cache:
                    continue
                c = cache[t]
                for field, ck in (("h", "high"), ("c", "close")):
                    key = (field, Decimal(str(c[ck])))
                    pref = ((raw["h"] + Decimal("0.01")) / Decimal("0.01")).to_integral_value(
                        rounding=ROUND_CEILING
                    ) * Decimal("0.01")
                    row = {
                        "t": t,
                        "raw_value": raw[field],
                        "cache_value": key[1],
                        "P_ref_from_actual_raw_high": pref,
                        "raw_entity_sha256": attempt["entity"]["sha256"],
                        "raw_pointer": f"/bars/{symbol}/{ordinal}",
                        "cache_source": src,
                    }
                    prior = grouped.get(key)
                    if prior and prior["raw_value"] != row["raw_value"] and len(examples) < 4:
                        examples.append(
                            {
                                "field": field,
                                "same_cached_value_distinct_raw_values": [prior, row],
                                "different_P_ref_grid": prior["P_ref_from_actual_raw_high"] != pref,
                            }
                        )
                    grouped.setdefault(key, row)
            records.append(
                {
                    "symbol": symbol,
                    "observed_collisions": examples,
                    "absence_in_one_control_not_full_dataset_inverse_proof": True,
                }
            )
    TARGET.write_text(
        json.dumps(
            {
                "role": "Observed source non-injective price counterexamples",
                "same_fixed_day": "2024-01-02",
                "records": records,
                "no_inverse_repair_or_changed_rule": True,
                "no_market_source_calls_orders_PnL": True,
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    print(json.dumps({r["symbol"]: len(r["observed_collisions"]) for r in records}))


if __name__ == "__main__":
    main()
