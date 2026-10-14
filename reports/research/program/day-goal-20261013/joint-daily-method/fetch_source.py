"""Bounded unauthenticated source text intake; count redirects and failures."""

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "source-request-ledger.json"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


url, name = sys.argv[1:3]
method = sys.argv[3] if len(sys.argv) > 3 else "GET"
assert method in {"GET", "HEAD"}
assert url.startswith("https://") and "/" not in name
ledger = json.loads(LEDGER.read_text())
assert ledger["units_used"] < 32
allowance = 67108864 - ledger["direct_response_bytes"] - ledger["web_unknown_allowance_bytes"]
limit = min(2097152, allowance)
assert limit > 0
entry = {
    "unit": ledger["units_used"] + 1,
    "url": url,
    "kind": "direct_source_" + method,
    "started_at": datetime.now(UTC).isoformat(),
    "retries": 0,
}
ledger["units_used"] += 1
ledger["requests"].append(entry)
LEDGER.write_text(json.dumps(ledger, indent=2) + "\n")
begin = time.process_time()
headers = {"User-Agent": "OpenComposerResearch/1.0"}
if len(sys.argv) > 4:
    headers["Range"] = sys.argv[4]
    entry["requested_range"] = sys.argv[4]
req = urllib.request.Request(url, headers=headers, method=method)
opener = urllib.request.build_opener(NoRedirect())
try:
    try:
        response = opener.open(req, timeout=35)
    except urllib.error.HTTPError as exc:
        response = exc
    entry["status"] = response.code
    entry["headers"] = {
        k: v for k, v in response.headers.items() if k.lower() not in {"set-cookie", "cookie"}
    }
    destination = ROOT / "sources" / name
    destination.parent.mkdir(exist_ok=True)
    size = 0
    sha = hashlib.sha256()
    with response, destination.open("xb") as out:
        while size < limit:
            block = response.read(min(65536, limit - size))
            if not block:
                break
            size += len(block)
            sha.update(block)
            out.write(block)
    entry.update(
        bytes=size,
        sha256=sha.hexdigest(),
        path=str(destination.relative_to(Path.cwd())),
        reached_local_bound=size == limit,
    )
    ledger["direct_response_bytes"] += size
except Exception as exc:
    entry["failure"] = type(exc).__name__ + ": " + str(exc)
finally:
    entry["CPU_coreseconds"] = time.process_time() - begin
    entry["completed_at"] = datetime.now(UTC).isoformat()
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n")
    print(json.dumps({k: v for k, v in entry.items() if k != "headers"}))
