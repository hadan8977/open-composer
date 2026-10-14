"""Bounded public primary-source capture, including actual redirect request units."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import requests

P = Path(__file__).parent
CAP = 32
BYTE_CAP = 64 * 1024 * 1024


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("output")
    parser.add_argument("--method", default="GET", choices=["GET", "HEAD"])
    parser.add_argument("--range")
    parser.add_argument("--max-bytes", type=int, default=4 * 1024 * 1024)
    args = parser.parse_args()
    ledger_path = P / "source-request-ledger.json"
    ledger = json.loads(ledger_path.read_text())
    used = sum(x.get("bytes", 0) for x in ledger if isinstance(x.get("bytes", 0), int))
    assert len(ledger) < CAP and used < BYTE_CAP
    headers = {"User-Agent": "OpenComposerResearch/1.0 public academic source intake"}
    if args.range:
        headers["Range"] = args.range
    url = args.url
    session = requests.Session()
    for _redirect in range(4):
        assert len(ledger) < CAP
        row = {
            "unit": len(ledger) + 1,
            "operation": "direct_public_" + args.method,
            "url": url,
            "range": args.range,
            "started_at_utc": datetime.now(UTC).isoformat(),
            "automatic_retries": 0,
            "status": "pending",
        }
        ledger.append(row)
        save(ledger_path, ledger)
        try:
            response = session.request(
                args.method, url, headers=headers, timeout=(10, 40),
                allow_redirects=False, stream=True,
            )
            row["status"] = response.status_code
            row["response_headers"] = {
                k: v for k, v in response.headers.items()
                if k.lower() in {"content-length", "content-type", "content-range",
                                 "accept-ranges", "location", "last-modified", "etag"}
            }
            data = bytearray()
            limit = min(args.max_bytes, BYTE_CAP - used)
            if args.method != "HEAD":
                for chunk in response.iter_content(chunk_size=65536):
                    if len(data) + len(chunk) > limit:
                        row["stopped_at_local_body_cap"] = True
                        row["unretained_transferred_chunk_bytes"] = len(chunk)
                        break
                    data.extend(chunk)
            response.close()
            target = P / args.output
            target.parent.mkdir(exist_ok=True)
            if args.method == "HEAD":
                row["bytes"] = 0
            else:
                if response.status_code in {301, 302, 303, 307, 308}:
                    target = target.with_name(target.name + f".redirect{_redirect}")
                target.write_bytes(data)
                row.update(bytes=len(data), path=str(target), sha256=hashlib.sha256(data).hexdigest())
            used += len(data)
            row["completed_at_utc"] = datetime.now(UTC).isoformat()
            save(ledger_path, ledger)
            print(json.dumps(row))
            if response.status_code in {301, 302, 303, 307, 308}:
                from urllib.parse import urljoin
                url = urljoin(url, response.headers["Location"])
                continue
            break
        except Exception as exc:
            row.update(status="request_failed", error=type(exc).__name__ + ": " + str(exc),
                       transferred_body_bytes="unknown_if_connection_failed")
            save(ledger_path, ledger)
            print(json.dumps(row))
            raise
    state = json.loads((P / "current-state.json").read_text())
    state.update(new_source_requests=len(ledger), new_source_direct_bytes=used,
                 updated_at_utc=datetime.now(UTC).isoformat())
    save(P / "current-state.json", state)


if __name__ == "__main__":
    main()
