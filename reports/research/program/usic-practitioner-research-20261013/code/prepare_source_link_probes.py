"""Freeze exact same-cohort source-link probes; offline, no credentials or HTTP."""

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
V3 = BASE / "revisions/v3-finite-qqq"
OUT = V3 / "full-cohort-route/source-link-probes"


def bind(p):
    return {"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def main():
    assert not OUT.exists()
    OUT.mkdir()
    requests = []
    for ident, symbols, timeframe, start, end, adjustment in (
        (
            "TSLA_pre2016_raw_history",
            "TSLA",
            "1Day",
            "1970-01-01T00:00:00Z",
            "2016-01-01T00:00:00Z",
            "raw",
        ),
        (
            "GEHC_GEHCV_birth_prefix",
            "GEHC,GEHCV",
            "1Day",
            "2016-01-01T00:00:00Z",
            "2023-07-01T00:00:00Z",
            "raw",
        ),
        (
            "four_current_vintage_all_minute",
            "PCAR,ROST,GEHC,TSLA",
            "1Min",
            "2024-01-02T14:30:00Z",
            "2024-01-02T20:59:59Z",
            "all",
        ),
    ):
        requests.append(
            {
                "id": ident,
                "path": "/stocks/bars",
                "params": {
                    "symbols": symbols,
                    "timeframe": timeframe,
                    "start": start,
                    "end": end,
                    "adjustment": adjustment,
                    "feed": "sip",
                    "asof": "-",
                    "sort": "asc",
                    "currency": "USD",
                    "limit": 10000,
                },
                "max_pages": 1,
                "per_page_byte_cap": 1572864,
            }
        )
    bindings = [
        bind(p)
        for p in (
            BASE / "code/query_remaining_source_links.py",
            BASE / "code/acquire_components.py",
            ROOT / "open_composer/adapters/data/alpaca_snapshot.py",
            V3 / "root-task-pool-continuation.json",
            V3 / "scientific-plan.json",
            V3 / "state-and-ledger-contract.json",
            V3 / "diagnostic-completion/independent-input-acceptance.json",
            V3 / "full-cohort-route/cache-basis-probe/manifest.json",
            V3 / "full-cohort-route/cache-price-collisions.json",
        )
    ]
    manifest = {
        "author": "f9add224-744b-471c-b812-c43cc179fa38",
        "role": "Necessary bounded source-route tests within unchanged finite101 cohort",
        "requests": requests,
        "request_limits": {"requests": 3, "entity_bytes": 4718592},
        "aggregate_used_before": {"requests": 60, "entity_bytes": 43895341},
        "aggregate_remaining_before": {"requests": 36, "entity_bytes": 90322387},
        "entry_bindings": bindings,
        "factory": "Existing _stock_data_client()._client; _load_env only after entry acceptance",
        "collector": "Existing accepted collect/bounded_get; no implicit retries or fallback URLs",
        "source_family": "Alpaca licensed historical SIP bars, existing authorization/config only",
        "firstseen_policy": "No new firstvisible hunt; all historical_first_visible remainnull",
        "purpose_by_id": {
            "TSLA_pre2016_raw_history": (
                "Test archive2016 boundary as fetch range versus provider coverage. "
                "Empty is only this packet, not market impossibility."
            ),
            "GEHC_GEHCV_birth_prefix": (
                "Same36266G107 source name_change/0 Jan4 2023. "
                "GEHCV is prior-symbol lineage, not an extra investment member. "
                "No certified common-share interval."
            ),
            "four_current_vintage_all_minute": (
                "CurrentALL versus oldcache version and non-injective prices. "
                "RawJan2 already retained; no new raw cohort or sample."
            ),
        },
        "bounds": {
            "new_scientific_cohort_threshold_seed_clock_changes": False,
            "new_investment_symbols": False,
            "new_source_family_paid_keys_broker_orders": False,
            "economic_execution_admitted": False,
            "market_grant_now": False,
            "independent_entry_acceptance_required_before_HTTP": True,
        },
        "stop_conditions": [
            "Maxonepageperobject, token means incomplete object not fullhistory",
            "401/403/429 or incompleteentity stops remainingbatch; other failure slot retained",
            "No request identity/header secrets logged; normalresponse metadata retained",
            "No seed inferred from first row; no inverse reconstruction without proof",
        ],
        "cached_collision_caveat": (
            "P_ref ambiguity applies to samehigh collisions. "
            "Close collision alone does not prove rawhigh ambiguity."
        ),
    }
    p = OUT / "request-manifest.json"
    p.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(bind(p)))


if __name__ == "__main__":
    main()
