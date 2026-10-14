"""Exact public-source metadata requests; no credentials, redirects or retries."""

from __future__ import annotations

import hashlib
import json
import os
import resource
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "public-decision-replay/sources"
REQUESTS = [
    (
        "author_linked_playlist",
        "https://www.youtube.com/playlist?list=PLIBNPtE5hHTCWVxdLtFjpYIsf0m94YYVZ",
        8388608,
    ),
    ("dec15_anchor_watch", "https://www.youtube.com/watch?v=O1LZJYaMqnQ", 8388608),
    (
        "dec15_anchor_oembed",
        "https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DO1LZJYaMqnQ&format=json",
        65536,
    ),
]


def now():
    return datetime.now(UTC).isoformat()


def text_field(obj):
    return obj.get("simpleText", "") or "".join(r.get("text", "") for r in obj.get("runs", []))


def main():
    assert os.sched_getaffinity(0) == {0}
    resource.setrlimit(resource.RLIMIT_CPU, (60, 61))
    assert not OUT.exists(), "preserve_consumed_source_slot"
    OUT.mkdir()
    ledger = {
        "started_UTC": now(),
        "attempts": [],
        "allocated_requests": len(REQUESTS),
        "allocated_direct_bytes": sum(cap for _, _, cap in REQUESTS),
        "charged_original_pool": "comparison64",
        "unknown_wire_bytes": None,
        "retry_redirect_or_credentials": False,
    }
    target = OUT / "direct-request-ledger.json"

    def save_ledger():
        target.write_text(json.dumps(ledger, indent=2) + "\n")

    with httpx.Client(
        timeout=30,
        follow_redirects=False,
        headers={
            "User-Agent": "OpenComposerResearch/USIC-PublicRecords-20261013",
            "Accept-Encoding": "identity",
        },
    ) as client:
        for name, url, cap in REQUESTS:
            row = {
                "id": name,
                "url": url,
                "reserved_before_call_UTC": now(),
                "reserved_bytes": cap,
                "complete": False,
                "unknown_wire_bytes": None,
            }
            ledger["attempts"].append(row)
            save_ledger()
            body = bytearray()
            try:
                with client.stream("GET", url) as response:
                    row["status"] = response.status_code
                    row["response_headers"] = {
                        k: v
                        for k, v in response.headers.items()
                        if k.lower()
                        in {"date", "content-type", "content-length", "content-encoding"}
                    }
                    for chunk in response.iter_bytes(chunk_size=65536):
                        if len(body) + len(chunk) > cap:
                            body.extend(chunk[: cap - len(body)])
                            row["stop_reason"] = "entity_cap_no_redirect_no_retry"
                            break
                        body.extend(chunk)
                    else:
                        row["complete"] = True
            except Exception as exc:
                row["transport_error_type"] = type(exc).__name__
                row["stop_reason"] = "single_transport_attempt_stop"
            path = OUT / f"{name}.bin"
            path.write_bytes(body)
            row.update(
                {
                    "retained_bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "path": str(path.relative_to(BASE)),
                    "finished_UTC": now(),
                }
            )
            row["direct_byte_charge"] = len(body) if row["complete"] else cap
            if row.get("status") != 200:
                row["source_result"] = "non200_preserved_no_bypass"
            save_ledger()
            print(
                json.dumps(
                    {
                        k: row.get(k)
                        for k in ["id", "status", "complete", "retained_bytes", "stop_reason"]
                    }
                ),
                flush=True,
            )
    ledger["finished_UTC"] = now()
    ledger["requests_used"] = len(ledger["attempts"])
    ledger["direct_byte_charge"] = sum(r["direct_byte_charge"] for r in ledger["attempts"])
    save_ledger()
    metadata = []
    for row in ledger["attempts"]:
        if row.get("status") != 200 or not row["complete"]:
            continue
        content = (BASE / row["path"]).read_text(errors="replace")
        if row["id"].endswith("oembed"):
            try:
                metadata.append(
                    {
                        "request_id": row["id"],
                        "source_sha256": row["sha256"],
                        "oembed": json.loads(content),
                    }
                )
            except ValueError:
                pass
            continue
        objects = {}
        for key in ["ytInitialData", "ytInitialPlayerResponse"]:
            for marker in [f"var {key} =", f"{key} ="]:
                if marker in content:
                    try:
                        objects[key] = json.JSONDecoder().raw_decode(
                            content.split(marker, 1)[1].lstrip()
                        )[0]
                    except ValueError:
                        pass
                    break
        entries = []

        def walk(obj, destination=entries):
            if isinstance(obj, dict):
                for kind in ["playlistVideoRenderer", "videoRenderer"]:
                    if kind in obj:
                        item = obj[kind]
                        destination.append(
                            {
                                "videoId": item.get("videoId"),
                                "title": text_field(item.get("title", {})),
                                "length": text_field(item.get("lengthText", {})),
                                "author": text_field(item.get("shortBylineText", {})),
                                "published": text_field(item.get("publishedTimeText", {})),
                                "isPlayable": item.get("isPlayable"),
                            }
                        )
                for value in obj.values():
                    walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value)

        walk(objects.get("ytInitialData", {}))
        player = objects.get("ytInitialPlayerResponse", {})
        summary = {
            "request_id": row["id"],
            "source_sha256": row["sha256"],
            "public_page_entries": entries,
            "player_status": player.get("playabilityStatus"),
            "videoDetails": player.get("videoDetails"),
            "microformat": player.get("microformat"),
            "caption_metadata": player.get("captions"),
            "available_stream_formats": player.get("streamingData"),
            "storyboard_metadata": player.get("storyboards"),
        }
        metadata.append(summary)
    (OUT / "parsed-public-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
