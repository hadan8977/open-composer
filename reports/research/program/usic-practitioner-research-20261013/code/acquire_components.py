"""Bounded read-only intake; dry-run never loads credentials or makes requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "acquisition"
SCOPE_SHA = "ceb6f8196cd9e3de83d79d345da7658d68be18dddc0dce1f9739961766ccbd93"
ALLOWED_HEADERS = {
    "date",
    "content-type",
    "content-length",
    "content-encoding",
    "x-request-id",
    "request-id",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "last-modified",
    "etag",
}


def utc():
    return datetime.now(UTC).isoformat()


def binding(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def load_scope():
    path = BASE / "input-and-request-scope.json"
    if binding(path)["sha256"] != SCOPE_SHA:
        raise ValueError("frozen_request_scope_changed")
    scope = json.loads(path.read_text())
    if len(scope["requests"]) != 13 or sum(s["max_pages"] for s in scope["requests"]) != 32:
        raise ValueError("request_inventory_changed")
    for spec in scope["requests"]:
        route = spec["path"]
        url = route if route.startswith("https://") else "https://data.alpaca.markets/v2" + route
        if urlparse(url).hostname != "data.alpaca.markets" or urlparse(url).scheme != "https":
            raise ValueError("market_data_host_only")
        if spec["per_page_byte_cap"] != 2 * 1024 * 1024:
            raise ValueError("page_byte_cap_changed")
    return scope


def bounded_get(client, path, params, byte_cap):
    """Use the admitted factory's HTTP session, without inspecting authentication.

    Identity encoding and streaming add a local entity-size stop to the existing
    raw transport. A truncated prefix is never certified as a complete entity.
    No automatic retries or redirects; every caller invocation is charged first.
    """
    body = bytearray()
    with client.stream(
        "GET", path, params=params, headers={"Accept-Encoding": "identity"}, follow_redirects=False
    ) as response:
        headers = {k: v for k, v in response.headers.items() if k.lower() in ALLOWED_HEADERS}
        result = {
            "http_status": response.status_code,
            "headers": headers,
            "entity_complete": False,
            "stop_reason": None,
        }
        length = headers.get("content-length")
        if length is not None and int(length) > byte_cap:
            result["stop_reason"] = "declared_content_length_above_reserved_page_cap"
            return bytes(body), result
        # iter_bytes follows the existing response.content entity convention.
        # Wire buffering/HTTP overhead is unknown and is not mislabelled as entity bytes.
        # Stop at the reservation itself rather than read another chunk to probe EOF.
        # A response exactly at the cap is conservatively retained as an incomplete prefix.
        chunk_size = math.gcd(4096, byte_cap)
        try:
            for chunk in response.iter_bytes(chunk_size=chunk_size):
                body.extend(chunk)
                if len(body) == byte_cap:
                    result["stop_reason"] = "entity_prefix_cap_stop"
                    return bytes(body), result
        except Exception as exc:
            result["stop_reason"] = "response_stream_failure"
            result["stream_exception_type"] = type(exc).__name__
            return bytes(body), result
        result["entity_complete"] = True
        return bytes(body), result


def check_admission(path, implementation):
    """Read a concrete Root resource decision; a scientific receipt grants no quota."""
    approval = json.loads(path.read_text())
    required = {
        "request_scope": {
            "path": str((BASE / "input-and-request-scope.json").relative_to(ROOT)),
            "sha256": SCOPE_SHA,
        },
        "implementation_manifest": binding(implementation),
    }
    if approval.get("verdict") != "approve_bounded_input_acquisition":
        raise ValueError("actual_resource_allocation_not_granted")
    if approval.get("bindings") != required:
        raise ValueError("resource_decision_binding_mismatch")
    if approval.get("author") == approval.get("decision_owner"):
        raise ValueError("author_cannot_self_allocate")
    limits = approval["allocation"]
    if not (0 < limits["requests"] <= 32 and 0 < limits["entity_bytes"] <= 64 * 1024 * 1024):
        raise ValueError("initial_input_allocation_out_of_scope")
    if not (0 < limits["preparation_coreseconds"] <= 120):
        raise ValueError("preparation_allocation_out_of_scope")
    if approval.get("economic_execution_admitted") is not False:
        raise ValueError("not_an_economic_execution_manifest")
    manifest = json.loads(implementation.read_text())
    receipt_binding = manifest.get("independent_scientific_review")
    if not receipt_binding:
        raise ValueError("independent_scientific_acceptance_missing")
    receipt_path = ROOT / receipt_binding["path"]
    if binding(receipt_path) != receipt_binding:
        raise ValueError("independent_scientific_receipt_changed")
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("verdict") != "approve_deep_plan" or receipt.get("reviewer") == receipt.get(
        "author"
    ):
        raise ValueError("independent_scientific_plan_not_accepted")
    expected_plan = manifest["scientific_plan"]
    reviewed_plan = receipt.get("bindings", {}).get("plan", {})
    if any(reviewed_plan.get(key) != expected_plan[key] for key in ("path", "sha256")):
        raise ValueError("scientific_review_plan_binding_mismatch")
    hold = json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())
    day = json.loads((ROOT / "reports/research/control/day-goal.json").read_text())
    if hold.get("research_paused") is not False:
        raise ValueError("current_research_permission_missing")
    tasks = [t for t in day["tasks"] if t["id"] == "USIC-PRACTITIONER-RESEARCH"]
    if len(tasks) != 1 or tasks[0].get("active_owner") != approval["author"]:
        raise ValueError("current_exclusive_task_owner_mismatch")
    for item in manifest["implementation_bindings"]:
        if binding(ROOT / item["path"]) != item:
            raise ValueError("implementation_binding_changed")
    return limits


def collect(scope, limits, client, out):
    path = out / "request-ledger.json"
    if path.exists():
        raise ValueError("no_implicit_rerun_or_quota_reset")
    ledger = {
        "scope_sha256": SCOPE_SHA,
        "started_at": utc(),
        "attempts": [],
        "requests_used": 0,
        "complete_entity_bytes": 0,
        "incomplete_response_reserved_bytes": 0,
        "source_first_visible": None,
        "automatic_retries": 0,
        "wire_bytes": None,
        "market_equivalent_to_economic_input": False,
    }
    save(path, ledger)
    stop_all = False
    try:
        for spec in scope["requests"]:
            cursor, seen_tokens = None, set()
            for page in range(1, spec["max_pages"] + 1):
                cap = spec["per_page_byte_cap"]
                charge = (
                    ledger["complete_entity_bytes"] + ledger["incomplete_response_reserved_bytes"]
                )
                if (
                    ledger["requests_used"] >= limits["requests"]
                    or charge + cap > limits["entity_bytes"]
                ):
                    ledger["stop_reason"] = "cumulative_initial_input_cap"
                    stop_all = True
                    break
                params = dict(spec["params"])
                if cursor is not None:
                    params["page_token"] = cursor
                attempt = {
                    "ordinal": ledger["requests_used"],
                    "id": spec["id"],
                    "page": page,
                    "path": spec["path"],
                    "params": params,
                    "requested_at": utc(),
                    "current_fetched_at": None,
                    "historical_first_visible": None,
                    "status": "started",
                    "reserved_bytes": cap,
                }
                ledger["attempts"].append(attempt)
                ledger["requests_used"] += 1
                ledger["incomplete_response_reserved_bytes"] += cap
                save(path, ledger)
                try:
                    body, packet = bounded_get(client, spec["path"], params, cap)
                except Exception as exc:
                    # Do not persist exception text that could include authentication.
                    attempt.update(status="transport_failure", exception_type=type(exc).__name__)
                    stop_all = True
                    break
                packet_path = out / "entities" / f"{spec['id']}-p{page:02d}.bin"
                packet_path.parent.mkdir(exist_ok=True)
                with packet_path.open("xb") as handle:
                    handle.write(body)
                attempt.update(
                    packet,
                    current_fetched_at=utc(),
                    entity=binding(packet_path),
                    retained_bytes=len(body),
                    status="response_retained",
                )
                if not packet["entity_complete"]:
                    attempt["status"] = "incomplete_response_no_entity_certification"
                    stop_all = True
                    break
                ledger["incomplete_response_reserved_bytes"] -= cap
                ledger["complete_entity_bytes"] += len(body)
                if packet["http_status"] != 200:
                    attempt["status"] = f"http_{packet['http_status']}"
                    stop_all = packet["http_status"] in (401, 403, 429)
                    break
                try:
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise ValueError("source_object_required")
                except (ValueError, TypeError):
                    attempt["status"] = "malformed_response"
                    break
                attempt["source_keys"] = sorted(payload)
                cursor = payload.get("next_page_token")
                attempt["next_page_token"] = cursor
                if not cursor:
                    attempt["status"] = "complete_bounded_source_response"
                    break
                if cursor in seen_tokens:
                    attempt["status"] = "repeated_page_token_stop"
                    break
                seen_tokens.add(cursor)
                if page == spec["max_pages"]:
                    attempt["status"] = "page_cap_truncated"
                save(path, ledger)
            save(path, ledger)
            if stop_all:
                break
    finally:
        ledger["finished_at"] = utc()
        save(path, ledger)
    return ledger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--admission", type=Path)
    args = parser.parse_args()
    scope = load_scope()
    if not args.execute:
        print(
            json.dumps(
                {
                    "request_objects": len(scope["requests"]),
                    "maximum_requests": 32,
                    "maximum_reserved_entity_bytes": 64 * 1024 * 1024,
                    "network_requests": 0,
                    "credential_initialization": False,
                }
            )
        )
        return
    if args.admission is None:
        raise ValueError("concrete_bound_resource_decision_required")
    limits = check_admission(args.admission, OUT / "implementation-manifest.json")
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (limits["preparation_coreseconds"], limits["preparation_coreseconds"] + 1),
    )
    start = time.process_time()
    from open_composer.adapters.data.alpaca_snapshot import _stock_data_client
    from open_composer.cli import _load_env

    _load_env()
    transport = _stock_data_client()
    try:
        ledger = collect(scope, limits, transport._client, OUT)
    finally:
        transport.close()
        save(
            OUT / "collection-resource.json",
            {
                "CPU_seconds": time.process_time() - start,
                "RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "fits": 0,
                "economic_runs": 0,
                "orders": 0,
            },
        )
    print(
        json.dumps(
            {
                "requests": ledger["requests_used"],
                "entity_bytes": ledger["complete_entity_bytes"],
                "unknown_reserved_bytes": ledger["incomplete_response_reserved_bytes"],
            }
        )
    )


if __name__ == "__main__":
    main()
