"""Bounded official metadata fetch under the inherited8-request/16MiB source ledger."""

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

Q = Path(__file__).resolve().parent
P = Q.parent
ledger_path = P / "source-ledger.json"
url, output = sys.argv[1:3]
ledger = json.loads(ledger_path.read_text())
used = sum(row.get("units", 0) for row in ledger["entries"])
assert used < ledger["request_cap"]
known_bytes = sum(row.get("direct_bytes") or 0 for row in ledger["entries"])
limit = min(2 * 1024**2, ledger["direct_byte_cap"] - known_bytes)
assert limit > 0
row = {
    "id": "audit-correction-" + output,
    "units": 1,
    "url": url,
    "started_at_utc": datetime.now(UTC).isoformat(),
    "status": "started",
    "direct_bytes": 0,
    "automatic_redirects": False,
    "automatic_retries": 0,
    "prior_unknown_web_transfer_preserved": True,
}
ledger["entries"].append(row)
ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
try:
    with requests.get(url, stream=True, allow_redirects=False, timeout=(10, 40)) as response:
        row["HTTP_status"] = response.status_code
        row["headers"] = {
            k: v
            for k, v in response.headers.items()
            if k.lower() in ["content-length", "content-type", "location", "last-modified", "etag"]
        }
        body = bytearray()
        for chunk in response.iter_content(16384):
            if len(body) + len(chunk) > limit:
                row["transferred_unretained_bytes"] = len(chunk)
                raise RuntimeError("Direct body cap reached")
            body.extend(chunk)
        path = Q / output
        path.write_bytes(body)
        row.update(
            status="complete",
            direct_bytes=len(body),
            path=str(path),
            sha256=hashlib.sha256(body).hexdigest(),
        )
except Exception as exc:
    row["error"] = str(exc)
    row["status"] = "failed"
    raise
finally:
    row["finished_at_utc"] = datetime.now(UTC).isoformat()
    ledger["units_used"] = sum(r.get("units", 0) for r in ledger["entries"])
    ledger["direct_bytes_used"] = sum(r.get("direct_bytes") or 0 for r in ledger["entries"])
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
print(json.dumps(row))
