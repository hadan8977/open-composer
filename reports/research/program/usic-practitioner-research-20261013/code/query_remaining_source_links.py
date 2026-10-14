"""Three same-cohort source probes after independent precise entry admission."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import resource
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "revisions/v3-finite-qqq/full-cohort-route/source-link-probes"
spec = importlib.util.spec_from_file_location(
    "usic_existing_intake", BASE / "code/acquire_components.py"
)
INTAKE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(INTAKE)


def check_entry():
    manifest_path = OUT / "request-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    receipt = json.loads((OUT / "independent-entry-acceptance.json").read_text())
    assert receipt.get("accepted_for_execution") is True
    assert receipt["reviewer"] != receipt.get("author")
    assert receipt["reviewer"] == "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3"
    assert receipt["author"] == manifest["author"]
    assert receipt["allocation"] == manifest["request_limits"]
    assert receipt.get("economic_execution_admitted") is False
    assert receipt["request_manifest"] == INTAKE.binding(manifest_path)
    assert receipt["entry_bindings"] == manifest["entry_bindings"]
    for b in manifest["entry_bindings"]:
        assert INTAKE.binding(ROOT / b["path"]) == b
    assert manifest["request_limits"] == {"requests": 3, "entity_bytes": 4718592}
    assert sum(r["max_pages"] for r in manifest["requests"]) == 3
    assert sum(r["max_pages"] * r["per_page_byte_cap"] for r in manifest["requests"]) == 4718592
    hold = json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())
    assert hold["research_paused"] is False
    day = json.loads((ROOT / "reports/research/control/day-goal.json").read_text())
    tasks = [t for t in day["tasks"] if t["id"] == "USIC-PRACTITIONER-RESEARCH"]
    assert len(tasks) == 1 and tasks[0]["active_owner"] == manifest["author"]
    assert os.sched_getaffinity(0) == {0}
    prior_ledgers = [
        json.loads((BASE / "acquisition/request-ledger.json").read_text()),
        json.loads((BASE / "revisions/v3-finite-qqq/market/request-ledger.json").read_text()),
    ]
    assert sum(x["requests_used"] for x in prior_ledgers) == 60
    assert (
        sum(
            x["complete_entity_bytes"] + x["incomplete_response_reserved_bytes"]
            for x in prior_ledgers
        )
        == 43895341
    )
    assert not (OUT / "market/request-ledger.json").exists(), "consumed_ledger_no_quota_reset"
    return manifest_path, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["offline", "execute"])
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU, (120, 121))
    if args.mode == "offline":
        manifest = json.loads((OUT / "request-manifest.json").read_text())
        assert sum(r["max_pages"] for r in manifest["requests"]) == 3
        print(json.dumps({"proposed_calls": 3, "credential_initialization": False, "HTTP": 0}))
        return
    manifest_path, manifest = check_entry()
    from open_composer.adapters.data.alpaca_snapshot import _stock_data_client
    from open_composer.cli import _load_env

    _load_env()
    client = _stock_data_client()
    INTAKE.SCOPE_SHA = INTAKE.binding(manifest_path)["sha256"]
    try:
        ledger = INTAKE.collect(
            {"requests": manifest["requests"]},
            manifest["request_limits"],
            client._client,
            OUT / "market",
        )
    finally:
        client.close()
    print(
        json.dumps(
            {
                "requests": ledger["requests_used"],
                "complete_entity_bytes": ledger["complete_entity_bytes"],
                "economic_execution_admitted": False,
            }
        )
    )


if __name__ == "__main__":
    main()
