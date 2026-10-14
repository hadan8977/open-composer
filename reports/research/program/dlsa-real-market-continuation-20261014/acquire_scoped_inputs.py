"""Proposed local source executor: inert until task-scoped Root admission."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, indent=2) + "\n")
    temp.replace(path)


def main():
    admission = json.loads((OUT / "root-admission.json").read_text())
    manifest_path = OUT / "source-request-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if (
        admission.get("market_input_preparation_admitted") is not True
        or admission.get("source_request_manifest_sha256")
        != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ):
        raise SystemExit("No bound current source admission; zero requests sent")
    hold = json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())
    if hold.get("research_paused") or admission.get("task_id") != manifest["task_id"]:
        raise SystemExit("Current authority/task mismatch; zero requests sent")
    review = json.loads((OUT / "independent-plan-review.json").read_text())
    if review.get("verdict") != "approve_deep_plan" or review.get("reviewer") == review.get(
        "author"
    ):
        raise SystemExit("Independent complete-plan review not approved")
    ledger_path = OUT / "acquisition/request-ledger.json"
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text())
        if ledger["manifest_sha256"] != manifest_sha:
            raise SystemExit("Existing source ledger belongs to another definition")
    else:
        ledger = {
            "manifest_sha256": manifest_sha,
            "requests_used": 0,
            "bytes_received": 0,
            "unknown_bytes_reserved": 0,
            "attempts": [],
            "complete_input_ids": [],
        }
    from open_composer.adapters.data.alpaca_snapshot import _stock_data_client
    from open_composer.cli import _load_env

    _load_env()
    transport = _stock_data_client()
    for spec in manifest["requests"]:
        if spec["id"] in ledger["complete_input_ids"]:
            continue
        # Resume only known received pages. An ambiguous in-flight request retains
        # its exposure; no automatic resend or quota reset.
        prior = [x for x in ledger["attempts"] if x["input_id"] == spec["id"]]
        if any(x["status"] != "received_complete" for x in prior):
            raise SystemExit("Unresolved source attempt requires same-definition reconciliation")
        cursor = prior[-1]["next_page_token"] if prior else None
        for page in range(len(prior) + 1, manifest["caps"]["pages_per_input_max"] + 1):
            cap = manifest["caps"]
            if (
                ledger["requests_used"] >= cap["requests"]
                or ledger["bytes_received"]
                + ledger["unknown_bytes_reserved"]
                + cap["per_response_bytes_max"]
                > cap["bytes"]
            ):
                raise SystemExit("Original source cap reached; retain partial pages")
            assert urlparse(spec["endpoint"]).hostname == "data.alpaca.markets"
            params = dict(spec["params"])
            if cursor:
                params["page_token"] = cursor
            attempt = {
                "input_id": spec["id"],
                "page": page,
                "params": params,
                "requested_at": datetime.now(UTC).isoformat(),
                "status": "started",
            }
            ledger["attempts"].append(attempt)
            ledger["requests_used"] += 1
            ledger["unknown_bytes_reserved"] += cap["per_response_bytes_max"]
            save(ledger_path, ledger)
            response = transport.get_raw(path=spec["factory_path"], data=params, headers={})
            body = response.entity_bytes
            target = OUT / f"acquisition/entities/{spec['id']}-p{page:02}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(body)
            ledger["unknown_bytes_reserved"] -= cap["per_response_bytes_max"]
            ledger["bytes_received"] += len(body)
            attempt.update(
                {
                    "status_code": response.status_code,
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "entity_path": str(target.relative_to(OUT)),
                    "entity_sha256": hashlib.sha256(body).hexdigest(),
                    "entity_bytes": len(body),
                    "historical_first_visible_at": None,
                    "historical_first_published_at": None,
                }
            )
            if response.status_code != 200 or len(body) > cap["per_response_bytes_max"]:
                attempt["status"] = "failed_or_oversized"
                save(ledger_path, ledger)
                raise SystemExit("Source response not accepted; no retry/provider substitution")
            payload = json.loads(body)
            cursor = payload.get("next_page_token")
            attempt.update(status="received_complete", next_page_token=cursor)
            if not cursor:
                ledger["complete_input_ids"].append(spec["id"])
            save(ledger_path, ledger)
            if not cursor:
                break
    save(
        OUT / "acquisition/execution-receipt.json",
        {
            "requests": ledger["requests_used"],
            "bytes": ledger["bytes_received"],
            "all_registered_inputs_complete": len(ledger["complete_input_ids"])
            == len(manifest["requests"]),
            "economic_or_training_admission": False,
            "terminal_and_episode_normalization_next": True,
        },
    )


if __name__ == "__main__":
    main()
