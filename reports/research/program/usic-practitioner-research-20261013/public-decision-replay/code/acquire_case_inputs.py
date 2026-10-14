"""Case-bound raw inputs; no credentials/network before independent entry grant."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import resource
from pathlib import Path
from urllib.parse import urlparse

P = Path(__file__).resolve().parents[1]
B = P.parent
ROOT = B.parents[3]
OUT = P / "acquisition"
AUTHOR = "f9add224-744b-471c-b812-c43cc179fa38"
REVIEWER = "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3"
spec = importlib.util.spec_from_file_location(
    "usic_existing_intake", B / "code/acquire_components.py"
)
INTAKE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(INTAKE)


def load_scope():
    path = OUT / "request-manifest.json"
    manifest = json.loads(path.read_text())
    limits = manifest["request_limits"]
    assert 0 < limits["requests"] <= 19
    assert 0 < limits["entity_bytes"] <= 39845888
    assert sum(r["max_pages"] for r in manifest["requests"]) == limits["requests"]
    assert (
        sum(r["max_pages"] * r["per_page_byte_cap"] for r in manifest["requests"])
        == limits["entity_bytes"]
    )
    assert len(manifest["requests"]) == 7
    for r in manifest["requests"]:
        url = (
            r["path"]
            if r["path"].startswith("https://")
            else "https://data.alpaca.markets/v2" + r["path"]
        )
        assert urlparse(url).hostname == "data.alpaca.markets"
        assert urlparse(url).scheme == "https"
        assert r["per_page_byte_cap"] == 2097152
    return path, manifest


def check_entry():
    path, manifest = load_scope()
    receipt = json.loads((OUT / "independent-entry-acceptance.json").read_text())
    assert receipt.get("accepted_for_execution") is True
    assert receipt.get("reviewer") == REVIEWER and receipt.get("author") == AUTHOR
    assert receipt["reviewer"] != receipt["author"]
    assert receipt["request_manifest"] == INTAKE.binding(path)
    assert receipt["allocation"] == manifest["request_limits"]
    assert receipt["entry_bindings"] == manifest["entry_bindings"]
    assert receipt.get("economic_execution_admitted") is False
    for b in manifest["entry_bindings"]:
        assert INTAKE.binding(ROOT / b["path"]) == b
    science = json.loads((ROOT / manifest["independent_scientific_review"]["path"]).read_text())
    assert science.get("verdict") == "approve_deep_plan"
    assert science.get("reviewer") == REVIEWER and science.get("author") == AUTHOR
    reviewed = science.get("bindings", {}).get("plan", {})
    assert (ROOT / reviewed["path"]).resolve() == (
        ROOT / manifest["scientific_plan"]["path"]
    ).resolve()
    assert reviewed["sha256"] == manifest["scientific_plan"]["sha256"]
    hold = json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())
    assert hold.get("research_paused") is False
    day = json.loads((ROOT / "reports/research/control/day-goal.json").read_text())
    owners = [t for t in day["tasks"] if t["id"] == "USIC-PRACTITIONER-RESEARCH"]
    assert len(owners) == 1 and owners[0].get("active_owner") == AUTHOR
    assert os.sched_getaffinity(0) == {0}
    prior = [json.loads((ROOT / x["path"]).read_text()) for x in manifest["prior_request_ledgers"]]
    assert (
        sum(x["requests_used"] for x in prior)
        == manifest["aggregate_used_before"]["requests"]
        == 63
    )
    assert (
        sum(x["complete_entity_bytes"] + x["incomplete_response_reserved_bytes"] for x in prior)
        == manifest["aggregate_used_before"]["entity_bytes"]
        == 44065545
    )
    assert not (OUT / "market/request-ledger.json").exists(), "consumed_ledger_no_reset"
    return path, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["offline", "execute"])
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU, (60, 61))
    if args.mode == "offline":
        _, m = load_scope()
        print(
            json.dumps(
                {
                    "calls_proposed": m["request_limits"]["requests"],
                    "HTTP": 0,
                    "credentials_initialized": False,
                }
            )
        )
        return
    path, m = check_entry()
    from open_composer.adapters.data.alpaca_snapshot import _stock_data_client
    from open_composer.cli import _load_env

    _load_env()
    client = _stock_data_client()
    INTAKE.SCOPE_SHA = INTAKE.binding(path)["sha256"]
    try:
        ledger = INTAKE.collect(
            {"requests": m["requests"]}, m["request_limits"], client._client, OUT / "market"
        )
    finally:
        client.close()
    print(
        json.dumps(
            {
                "requests": ledger["requests_used"],
                "entity_bytes": ledger["complete_entity_bytes"],
                "unknown_reserved_bytes": ledger["incomplete_response_reserved_bytes"],
                "economic_execution_admitted": False,
            }
        )
    )


if __name__ == "__main__":
    main()
