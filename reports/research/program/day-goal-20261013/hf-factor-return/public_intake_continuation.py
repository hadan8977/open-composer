"""Use the explicit continuation grant; preserve original source ledger/archives."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import requests

P = Path(__file__).parent


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("output")
    parser.add_argument("--method", choices=["GET", "HEAD"], default="GET")
    parser.add_argument("--range")
    parser.add_argument("--max-bytes", type=int, default=1_048_576)
    parser.add_argument("--stage", choices=["resolution", "complete_input"], default="resolution")
    args = parser.parse_args()
    grant = json.loads((P / "root-source-continuation-decision.json").read_text())
    unit_cap, byte_cap = 32, 8_388_608
    if args.stage == "complete_input":
        acceptance = json.loads((P / "independent-complete-input-scope-review.json").read_text())
        assert acceptance["verdict"] == "approve_complete_input_scope"
        assert acceptance["reviewer"] != "7b109880-ac40-447e-b2a6-f0ed1266ebac"
        spec = acceptance["bindings"]["request_manifest"]
        raw = Path(spec["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
        manifest = json.loads(raw)
        assert args.url in [row["url"] for row in manifest["files"]]
        unit_cap = grant["conditional_complete_input_scope_inclusive_of_resolution"]["public_requests_cap"]
        byte_cap = grant["conditional_complete_input_scope_inclusive_of_resolution"]["actual_response_bytes_cap"]
    ledger_path = P / "continuation-source-request-ledger.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    used = sum(row.get("bytes", 0) for row in ledger)
    assert len(ledger) < unit_cap and used < byte_cap
    session = requests.Session()
    url = args.url
    for redirect in range(4):
        assert len(ledger) < unit_cap and used < byte_cap
        row = {"unit": len(ledger) + 1, "stage": args.stage, "url": url,
               "method": args.method, "range": args.range, "status": "pending",
               "started_at_utc": datetime.now(UTC).isoformat(), "automatic_retries": 0}
        ledger.append(row)
        save(ledger_path, ledger)
        data = bytearray()
        response = None
        try:
            headers = {"User-Agent": "OpenComposerResearch/1.0 public academic source intake",
                       "Accept-Encoding": "identity"}
            if args.range:
                headers["Range"] = args.range
            response = session.request(args.method, url, headers=headers,
                                       allow_redirects=False, timeout=(10, 40), stream=True)
            row["status"] = response.status_code
            row["headers"] = {k: v for k, v in response.headers.items() if k.lower() in {
                "content-length", "content-type", "content-range", "accept-ranges",
                "location", "etag", "last-modified", "content-encoding"}}
            limit = min(args.max_bytes, byte_cap - used)
            content_length = response.headers.get("Content-Length")
            content_length = int(content_length) if content_length and content_length.isdigit() else None
            row["range_ignored"] = bool(args.range and response.status_code == 200)
            if args.method != "HEAD":
                if content_length is not None and content_length > limit:
                    row["body_rejected_before_read_size_over_cap"] = True
                else:
                    while len(data) < limit:
                        chunk = response.raw.read(min(65_536, limit - len(data)), decode_content=False)
                        if not chunk:
                            row["body_complete"] = True
                            break
                        data.extend(chunk)
                    if content_length is not None and len(data) == content_length:
                        row["body_complete"] = True
                    if len(data) == limit and not row.get("body_complete"):
                        row["stopped_at_actual_body_cap"] = True
            response.close()
            target = P / args.output
            if response.status_code in {301, 302, 303, 307, 308}:
                target = target.with_name(target.name + f".redirect{redirect}")
            target.parent.mkdir(parents=True, exist_ok=True)
            assert not target.exists(), "Never overwrite retained responses"
            target.write_bytes(data)
            row.update(bytes=len(data), path=str(target), sha256=hashlib.sha256(data).hexdigest(),
                       completed_at_utc=datetime.now(UTC).isoformat())
            used += len(data)
            assert used <= byte_cap
            save(ledger_path, ledger)
            print(json.dumps({k: row[k] for k in ["unit", "url", "status", "bytes", "path", "sha256"]}))
            if response.status_code in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.headers["Location"])
                continue
            break
        except Exception as exc:
            if response is not None:
                response.close()
            target = P / (args.output + ".partial")
            target.parent.mkdir(parents=True, exist_ok=True)
            assert not target.exists()
            target.write_bytes(data)
            row.update(status="request_failed", bytes=len(data), path=str(target),
                       sha256=hashlib.sha256(data).hexdigest(), error=type(exc).__name__ + ": " + str(exc),
                       incomplete_transport_bytes_unknown=True)
            save(ledger_path, ledger)
            raise
    state_path = P / "current-state.json"
    state = json.loads(state_path.read_text())
    state.update(continuation_source_units_used=len(ledger), continuation_direct_bytes=used,
                 HF_cumulative_source_units=32 + len(ledger), HF_cumulative_known_direct_bytes=37_252_859 + used,
                 updated_at_utc=datetime.now(UTC).isoformat())
    save(state_path, state)


if __name__ == "__main__":
    main()
