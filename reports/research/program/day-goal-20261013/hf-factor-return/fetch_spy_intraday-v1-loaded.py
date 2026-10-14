"""Read-only streaming capture of the plan's fixed SPY15Min market input.

Run only after independent complete science approval. No economic calculations.
"""

import hashlib
import json
import os
import resource
from datetime import UTC, datetime
from pathlib import Path

from open_composer.adapters.data.alpaca_snapshot import _stock_data_client
from open_composer.cli import _load_env

P = Path(__file__).parent
I = P / "market-input"
MAX_REQUESTS = 15
MAX_BYTES = 12_657_184
PAGE_CAP = 2_000_000


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def main():
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    review = json.loads((P / "independent-plan-review.json").read_text())
    assert review["verdict"] == "approve_deep_plan"
    assert review["reviewer"] != "7b109880-ac40-447e-b2a6-f0ed1266ebac"
    planpath = P / "scientific-plan.json"
    bound = review["bindings"]
    bound = list(bound.values()) if isinstance(bound, dict) else bound
    assert any(
        Path(b["path"]).resolve() == planpath.resolve()
        and b["sha256"] == hashlib.sha256(planpath.read_bytes()).hexdigest()
        for b in bound
    )
    inherited = json.loads(
        (P.parent / "primary-return-breadth/inputs/market-request-ledger.json").read_text()
    )
    assert len(inherited) == 9 and sum(r["bytes"] for r in inherited) == 4_120_032
    ledgerpath = I / "market-request-ledger.json"
    I.mkdir(exist_ok=True)
    ledger = json.loads(ledgerpath.read_text()) if ledgerpath.exists() else []
    # Use the normal app loader/client. Neither credential value nor header is inspected/output.
    _load_env()
    client = _stock_data_client()
    data = {
        "symbols": "SPY",
        "timeframe": "15Min",
        "start": "2016-01-01T05:00:00Z",
        "end": "2021-01-01T05:00:00Z",
        "adjustment": "raw",
        "feed": "sip",
        "limit": 10000,
        "sort": "asc",
        "asof": "-",
    }
    seen = set()
    try:
        for page in range(1, MAX_REQUESTS + 1):
            path = I / f"spy_15min_raw-{page:02}.json"
            previous = next((r for r in ledger if r.get("path") == str(path)), None)
            if previous:
                assert previous["status"] == 200 and previous["body_complete"]
                assert previous["params"] == data
                body = path.read_bytes()
                assert hashlib.sha256(body).hexdigest() == previous["sha256"]
            else:
                used = sum(r.get("bytes", 0) for r in ledger)
                assert len(ledger) < MAX_REQUESTS and used < MAX_BYTES
                row = {
                    "request_path": "/stocks/bars",
                    "params": dict(data),
                    "requested_at_utc": datetime.now(UTC).isoformat(),
                    "path": str(path),
                    "status": "pending",
                    "automatic_retries": 0,
                }
                ledger.append(row)
                save(ledgerpath, ledger)
                bodybuf = bytearray()
                try:
                    # The existing raw app transport's client supports streaming, enforcing caps
                    # before body reception; no separate credentials or trading client.
                    with client._client.stream(
                        "GET",
                        "/stocks/bars",
                        params=data,
                        headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                    ) as response:
                        row["status"] = response.status_code
                        row["response_headers"] = {
                            k: v
                            for k, v in response.headers.items()
                            if k.lower()
                            in {
                                "content-length",
                                "content-type",
                                "content-encoding",
                                "date",
                                "x-request-id",
                            }
                        }
                        assert response.headers.get("content-encoding", "identity") in {
                            "identity",
                            "",
                        }
                        # Reserve one whole transport chunk when Content-Length is unknown.
                        # Actual received surplus is charged below and remains inside totalcap.
                        remaining = min(PAGE_CAP, MAX_BYTES - used - 4096)
                        assert remaining > 0
                        length = response.headers.get("content-length")
                        length = int(length) if length and length.isdigit() else None
                        if length is not None and length > remaining:
                            row["body_rejected_before_read_size_over_cap"] = True
                        else:
                            # <=4KiB rawchunks bound unknown-length responses; stop exactly at cap.
                            for chunk in response.iter_raw(chunk_size=4096):
                                room = remaining - len(bodybuf)
                                if len(chunk) > room:
                                    bodybuf.extend(chunk[:room])
                                    row["over_cap_transport_bytes_received"] = len(chunk) - room
                                    break
                                bodybuf.extend(chunk)
                            else:
                                row["body_complete"] = True
                    body = bytes(bodybuf)
                    assert not path.exists()
                    path.write_bytes(body)
                    row.update(
                        bytes=len(body) + row.get("over_cap_transport_bytes_received", 0),
                        retained_bytes=len(body),
                        sha256=hashlib.sha256(body).hexdigest(),
                        received_at_utc=datetime.now(UTC).isoformat(),
                    )
                    save(ledgerpath, ledger)
                    assert row["status"] == 200 and row.get("body_complete")
                    assert sum(r["bytes"] for r in ledger) <= MAX_BYTES
                except BaseException as error:
                    if not path.exists():
                        path.write_bytes(bodybuf)
                        row.update(bytes=len(bodybuf), sha256=hashlib.sha256(bodybuf).hexdigest())
                    row.update(
                        error_type=type(error).__name__, incomplete_transport_bytes_unknown=True
                    )
                    save(ledgerpath, ledger)
                    raise
            payload = json.loads(body)
            assert isinstance(payload["bars"].get("SPY", []), list)
            token = payload.get("next_page_token")
            print(
                json.dumps(
                    {
                        "page": page,
                        "bytes": len(body),
                        "SPY_rows": len(payload["bars"].get("SPY", [])),
                        "more": bool(token),
                    }
                ),
                flush=True,
            )
            if not token:
                state = json.loads((P / "current-state.json").read_text())
                state.update(
                    new_market_requests=len(ledger),
                    new_market_bytes=sum(r.get("bytes", 0) for r in ledger),
                    market_capture_complete=True,
                    input_ready=False,
                    economic_execution_admitted=False,
                )
                save(P / "current-state.json", state)
                break
            assert token not in seen
            seen.add(token)
            data = dict(data, page_token=token)
        else:
            raise RuntimeError("Incomplete pagination at admitted market request bound")
    finally:
        client.close()


if __name__ == "__main__":
    main()
