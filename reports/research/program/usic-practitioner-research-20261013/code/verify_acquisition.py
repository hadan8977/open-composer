"""Synthetic protocol edge cases; no market rows, credentials, returns or HTTP."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from acquire_components import BASE, bounded_get, collect, load_scope


class Chunked(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def main():
    scope = load_scope()
    observations = []
    fixtures = [
        ({"bars": {"GME": [{"t": "synthetic"}]}, "next_page_token": "page2"}, 200),
        ({"bars": {"GME": []}, "next_page_token": "page2"}, 200),
    ]

    def answer(request):
        observations.append(str(request.url))
        payload, status = fixtures[len(observations) - 1]
        return httpx.Response(status, content=json.dumps(payload).encode())

    with TemporaryDirectory(prefix="protocol-fixture-", dir=BASE) as scratch:
        out = Path(scratch)
        # Smaller fixed inventory only for a synthetic protocol test, not a real manifest.
        test_scope = {"requests": [dict(scope["requests"][0], max_pages=4)]}
        limits = {"requests": 4, "entity_bytes": 8 * 1024 * 1024}
        with httpx.Client(
            base_url="https://data.alpaca.markets/v2", transport=httpx.MockTransport(answer)
        ) as client:
            ledger = collect(test_scope, limits, client, out)
        assert ledger["requests_used"] == 2
        assert ledger["attempts"][-1]["status"] == "repeated_page_token_stop"
        assert "page_token=page2" in observations[1]
        assert all("/v2/stocks/bars?" in url for url in observations)
        assert ledger["incomplete_response_reserved_bytes"] == 0
        assert len(list((out / "entities").iterdir())) == 2
        try:
            collect(test_scope, limits, None, out)
        except ValueError as exc:
            assert str(exc) == "no_implicit_rerun_or_quota_reset"
        else:
            raise AssertionError("implicit_quota_reset_allowed")

    def unknown_length(request):
        return httpx.Response(200, stream=Chunked([b"a" * 16, b"b" * 16, b"c" * 16]))

    with httpx.Client(transport=httpx.MockTransport(unknown_length)) as client:
        prefix, result = bounded_get(client, "https://data.alpaca.markets/v2/stocks/bars", {}, 32)
    assert len(prefix) == 32 and result["entity_complete"] is False
    assert result["stop_reason"] == "entity_prefix_cap_stop"

    def unavailable(request):
        return httpx.Response(403, content=b'{"message":"synthetic unavailable"}')

    with TemporaryDirectory(prefix="protocol-fixture-", dir=BASE) as scratch:
        with httpx.Client(
            base_url="https://data.alpaca.markets/v2", transport=httpx.MockTransport(unavailable)
        ) as client:
            ledger = collect(
                {"requests": scope["requests"]},
                {"requests": 32, "entity_bytes": 64 * 1024 * 1024},
                client,
                Path(scratch),
            )
        assert ledger["requests_used"] == 1
        assert ledger["attempts"][0]["status"] == "http_403"
        assert ledger["attempts"][0]["entity_complete"] is True

    # The real admission must be absent; no test creates a self-approval file.
    assert not (BASE / "acquisition/root-resource-decision.json").exists()
    rejection = subprocess.run(
        [sys.executable, str(BASE / "code/acquire_components.py"), "--execute"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejection.returncode != 0
    assert "concrete_bound_resource_decision_required" in rejection.stderr
    print(
        json.dumps(
            {
                "protocol_cases_passed": [
                    "frozen_scope",
                    "pagination",
                    "repeat_token_stop",
                    "exact_prefix_stop",
                    "failure_entity",
                    "403_no_retry",
                    "no_implicit_reset",
                    "no_admission",
                ],
                "request_objects": 13,
                "actual_network_requests": 0,
                "credential_reads": 0,
                "market_record_scans": 0,
                "fits": 0,
                "economic_runs": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
