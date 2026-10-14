"""Execute only the independently accepted fixed read-only entity manifest."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("/root/codex-test/open-composer")
OUT = Path(__file__).resolve().parent
MANIFEST_SHA = "4451c2041084b3eb7c81661c08905a77483dcbd7ae1a25967e5ae6385af1b432"
SCOPE_SHA = "3b2c36d0a43cce072a4b33b97b16d35399de63294e5e00d66875cc43dbd8b005"
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$")


def utc():
    return datetime.now(UTC).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def ns(value):
    match = STAMP.fullmatch(value)
    if match is None:
        raise ValueError("timestamp_format")
    base, fraction, offset = match.groups()
    dt = datetime.fromisoformat(base + ("+00:00" if offset == "Z" else offset))
    delta = dt - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 1_000_000_000 + int(
        (fraction or "").ljust(9, "0")
    )


def eligible_quote(row, params):
    try:
        tick = ns(row["t"])
        values = [float(row[key]) for key in ("bp", "ap", "bs", "as")]
        return (
            ns(params["start"]) <= tick <= ns(params["end"])
            and all(math.isfinite(val) and val > 0 for val in values)
            and values[0] <= values[1]
        )
    except (KeyError, TypeError, ValueError):
        return False


def main():
    cpu0, wall0 = time.process_time(), time.monotonic()
    resource.setrlimit(resource.RLIMIT_CPU, (6800, 6801))
    assert Path.cwd() == ROOT
    assert sha(OUT / "request-manifest.json") == MANIFEST_SHA
    assert sha(OUT / "request-scope-acceptance.json") == SCOPE_SHA
    manifest = json.loads((OUT / "request-manifest.json").read_text())
    scope = json.loads((OUT / "request-scope-acceptance.json").read_text())
    assert scope["verdict"] == "approve"
    assert scope["bindings"]["request_manifest"]["sha256"] == MANIFEST_SHA
    for binding in manifest["implementation_bindings"]:
        assert sha(ROOT / binding["path"]) == binding["sha256"]
    assert len(manifest["requests"]) == 13
    assert not (OUT / "data-request-ledger.json").exists(), "No implicit rerun or quota reset"
    caps = manifest["caps"]
    entity_dir = OUT / "entities"
    entity_dir.mkdir(exist_ok=True)
    ledger = {
        "schema_version": 1,
        "request_manifest_sha256": MANIFEST_SHA,
        "scope_acceptance_sha256": SCOPE_SHA,
        "started_at_utc": utc(),
        "attempts": [],
        "inputs": [],
        "data_requests_used": 0,
        "actual_entity_bytes": 0,
        "unknown_entity_byte_allowance": 0,
        "stopped_routes": {},
        "automatic_retries": 0,
        "first_seen_probe_complete": True,
        "historical_first_visible": None,
        "strict_APP_input_ready": False,
    }
    save(OUT / "data-request-ledger.json", ledger)
    transport = None
    try:
        sys.path.insert(0, str(ROOT))
        from open_composer.adapters.data.alpaca_snapshot import _stock_data_client
        from open_composer.cli import _load_env
        from open_composer.config import project_root

        assert project_root() == ROOT
        _load_env()
        assert project_root() == ROOT and Path.cwd() == ROOT
        transport = _stock_data_client()
        for spec in manifest["requests"]:
            assert urlparse(spec["endpoint"]).hostname == "data.alpaca.markets"
            item = {"id": spec["id"], "pages": [], "status": "not_started"}
            ledger["inputs"].append(item)
            route = spec["route"]
            if route in ledger["stopped_routes"]:
                item.update(status="skipped_route_stopped", reason=ledger["stopped_routes"][route])
                save(OUT / "data-request-ledger.json", ledger)
                continue
            cursor = None
            for page in range(1, caps["pages_per_input_max"] + 1):
                charged = ledger["actual_entity_bytes"] + ledger["unknown_entity_byte_allowance"]
                if ledger["data_requests_used"] >= caps["data_requests_total"]:
                    item["status"] = "request_cap_stop"
                    break
                if charged + caps["per_response_bytes_max"] > caps["data_response_bytes_total"]:
                    item["status"] = "byte_reservation_cap_stop"
                    break
                params = dict(spec["params"])
                if cursor:
                    params["page_token"] = cursor
                attempt = {
                    "input_id": spec["id"],
                    "page": page,
                    "endpoint": spec["endpoint"],
                    "params": params,
                    "requested_at_utc": utc(),
                    "status": "started",
                    "response_bytes": None,
                    "entity_path": None,
                    "historical_first_published_at": None,
                    "historical_first_visible_at": None,
                }
                ledger["attempts"].append(attempt)
                item["pages"].append(len(ledger["attempts"]) - 1)
                ledger["data_requests_used"] += 1
                ledger["unknown_entity_byte_allowance"] += caps["per_response_bytes_max"]
                save(OUT / "data-request-ledger.json", ledger)
                try:
                    response = transport.get_raw(path=spec["factory_path"], data=params, headers={})
                except Exception as exc:
                    attempt.update(
                        status="transport_failure",
                        exception_type=type(exc).__name__,
                        finished_at_utc=utc(),
                    )
                    item["status"] = "transport_failure"
                    save(OUT / "data-request-ledger.json", ledger)
                    break
                fetched = utc()
                body = response.entity_bytes
                path = entity_dir / f"{spec['id']}-p{page:02d}.json"
                with path.open("xb") as handle:
                    handle.write(body)
                ledger["unknown_entity_byte_allowance"] -= caps["per_response_bytes_max"]
                ledger["actual_entity_bytes"] += len(body)
                allowed_headers = {
                    "date",
                    "content-type",
                    "x-request-id",
                    "request-id",
                    "x-ratelimit-limit",
                    "x-ratelimit-remaining",
                    "x-ratelimit-reset",
                    "last-modified",
                    "etag",
                }
                attempt.update(
                    status="http_response",
                    http_status=response.status_code,
                    actual_fetched_at=fetched,
                    first_observed_by_us=fetched,
                    response_bytes=len(body),
                    entity_path=str(path.relative_to(ROOT)),
                    entity_sha256=hashlib.sha256(body).hexdigest(),
                    response_headers={
                        k: v for k, v in response.headers.items() if k.lower() in allowed_headers
                    },
                )
                save(OUT / "data-request-ledger.json", ledger)
                if len(body) > caps["per_response_bytes_max"]:
                    item["status"] = "oversized_entity_stop"
                    ledger["stopped_routes"][route] = "oversized_entity"
                    break
                if response.status_code != 200:
                    item["status"] = f"http_{response.status_code}"
                    if response.status_code in (401, 403, 429):
                        ledger["stopped_routes"][route] = item["status"]
                    break
                try:
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise ValueError("object_required")
                except (ValueError, TypeError):
                    item["status"] = "malformed_response"
                    break
                cursor = payload.get("next_page_token")
                attempt["top_level_keys"] = sorted(payload)
                attempt["next_page_token"] = cursor
                if spec["kind"] in ("bars", "quotes"):
                    rows = payload.get(spec["kind"], {}).get(params["symbols"], [])
                    attempt["record_count"] = len(rows)
                    attempt["record_keys"] = sorted({k for row in rows for k in row})
                    if spec["kind"] == "quotes" and any(eligible_quote(r, params) for r in rows):
                        item["status"] = "first_eligible_prefix_retained"
                        item["full_window_history_complete"] = not bool(cursor)
                        break
                if not cursor:
                    item["status"] = "complete_bounded_response"
                    break
            else:
                item["status"] = "page_cap_truncated"
            save(OUT / "data-request-ledger.json", ledger)
            print(
                json.dumps(
                    {
                        "id": spec["id"],
                        "status": item["status"],
                        "requests": ledger["data_requests_used"],
                        "bytes": ledger["actual_entity_bytes"],
                    }
                ),
                flush=True,
            )
    except Exception as exc:
        ledger["execution_error_type"] = type(exc).__name__
        raise
    finally:
        if transport is not None:
            transport.close()
        ledger["finished_at_utc"] = utc()
        save(OUT / "data-request-ledger.json", ledger)
        receipt = {
            "cpu_seconds": time.process_time() - cpu0,
            "wall_seconds": time.monotonic() - wall0,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "prior_conservative_CPU_remaining_seconds": 6875.075568,
            "one_cpu_thread_environment": True,
            "memory_cap_mib": 900,
            "new_model_fits": 0,
            "new_optimizer_updates": 0,
            "new_orders": 0,
            "data_requests_used": ledger["data_requests_used"],
            "actual_entity_bytes": ledger["actual_entity_bytes"],
            "unknown_entity_byte_allowance": ledger["unknown_entity_byte_allowance"],
        }
        save(OUT / "acquisition-resource-receipt.json", receipt)
        print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
