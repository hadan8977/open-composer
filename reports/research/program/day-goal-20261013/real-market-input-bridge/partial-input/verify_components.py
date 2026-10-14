"""Verify only new partial components and the accepted parent manifest binding."""

import hashlib
import json
import math
import resource
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[5]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    started = time.monotonic()
    parent_sha = sha(OUT.parent / "package-manifest.json")
    assert parent_sha == "e1f20bd777aaa3356bdc9ec575cdb67243ae9bbb010885b97c8156a15fc5faf3"
    result = json.loads((OUT / "local-source-result.json").read_text())
    component = json.loads((OUT / "partial-source-components.json").read_text())
    assert result["metadata_json_files_read"] == 159
    assert result["cache_manifest_count"] == 153
    assert result["stock_NBBO_rows_read"] == 333
    assert result["RF_numeric_rows_read"] == 6
    assert result["new_stock_price_value_files_read"] == 0
    assert all(result[k] == 0 for k in ["APP_price3_rows", "APP_full7_rows", "APP_0945_labels"])
    assert component["price3"] == component["full7"] == component["0945labels"] == []
    assert not result["whole_direction_refuted"]
    for binding in result["source_inputs"]:
        # Hashes only: do not repeat metadata/market decoding or the old101-file audit.
        assert sha(ROOT / binding["path"]) == binding["sha256"]
    quotes = component["stock_NBBO_examples"]
    assert len(quotes) == 9 and {x["symbol"] for x in quotes} == {"IBM", "AAPL"}
    for example in quotes:
        q = example["record"]
        assert 0 < float(q["bp"]) <= float(q["ap"])
        assert (
            hashlib.sha256(json.dumps(q, sort_keys=True).encode()).hexdigest()
            == example["source_record_sha256"]
        )
        observed = datetime.fromisoformat(q["t"].replace("Z", "+00:00")).astimezone(
            ZoneInfo("America/New_York")
        )
        assert (observed.hour, observed.minute) in {(9, 59), (10, 0)}
        assert not example["APP_0945_endpoint_qualified"]
    rf = component["RF_observations"]
    assert [x["observation_date"] for x in rf] == [
        "20160104",
        "20160105",
        "20160106",
        "20160107",
        "20160108",
        "20160111",
    ]
    assert all(math.isfinite(x["value_decimal"]) for x in rf)
    assert all(x["historical_published_at"] is None and not x["APP_Rf_qualified"] for x in rf)
    assert all(x["value_decimal"] == float(x["source_value_text"]) / 100 for x in rf)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    verified = {
        "mechanical_verification_pass": True,
        "independent_input_acceptance": False,
        "parent_v2_manifest_unchanged": parent_sha,
        "scope": "New metadata/9quote examples/6RF facts only; no old six-case repetition",
        "quote_source_fields_exist": True,
        "RF_source_values_exist_and_not_zero_imputation": True,
        "price3_qualified": False,
        "full7_qualified": False,
        "0945labels_qualified": False,
        "no_global_unavailability_or_scientific_refutation": True,
        "source_requests_new": 0,
        "market_requests_new": 0,
        "fits": 0,
        "cpu_seconds": usage.ru_utime + usage.ru_stime,
        "wall_seconds": time.monotonic() - started,
        "max_rss_kib": usage.ru_maxrss,
    }
    (OUT / "verification.json").write_text(json.dumps(verified, indent=2) + "\n")
    print(json.dumps(verified))


if __name__ == "__main__":
    main()
