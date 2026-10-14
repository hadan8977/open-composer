"""Bounded source-only entry; original transport and cumulative atomic ledger.

All page calls, including failures, are charged first. This is not a scheduler,
source provider, broker write API or an autonomous request-discovery service.
"""

# ruff: noqa: E402
import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

P = Path(__file__).resolve().parents[2]
ROOT = P.parents[4]
sys.path.insert(0, str(P / "code"))
sys.path.insert(0, str(P.parent / "code"))
from acquire_components import bounded_get
from consumer_admission import bind, locked_ledger, receipt, save, verify_bindings
from continuation_admission import claim, current_grant, native_admission, remaining
from gap_source import parse_quotes, validate_pages

SCOPE = P / "economic-results/source-consumer-v3/source-scope.json"
REVIEW = P / "economic-results/source-consumer-v3/independent-review.json"
OUT = P / "economic-results/source-consumer-v3/raw"
PAGE_CAP = 4 * 1024 * 1024


def admitted_scope(job):
    current_grant()
    row = receipt(job)
    assert row["pid"] == os.getpid() and row["status"] == "running"
    proof = json.loads(REVIEW.read_text())
    assert proof["verdict"] in {"approve_implementation", "approve_deep_plan"}
    assert proof["author"] != proof["reviewer"]
    assert proof["actual_source_calls_admitted"] is True
    assert row["binding"]["affected_review"] == bind(REVIEW)
    assert row["current_native"]["status"] == "ok"
    verify_bindings(row["current_native_dossier"])
    verify_bindings(proof["bindings"])
    scope = json.loads(SCOPE.read_text())
    assert proof["bindings"]["source_scope"] == bind(SCOPE)
    assert scope["request_upper"] == 266 and scope["entity_upper"] == 212975794
    return scope, proof


def request_window(job, window_id, *, causal_release):
    scope, proof = admitted_scope(job)
    match = [r for r in scope["requests"] if r["id"] == window_id]
    assert len(match) == 1
    query = match[0]
    assert causal_release["kind"] in {"bootstrap_source_QA", "active_native_risk"}
    if causal_release["kind"] == "bootstrap_source_QA":
        assert window_id in proof["bootstrap_source_ids"]
    else:
        # Consumer—not an arbitrary CLI caller—supplies the frozen active-risk
        # evidence at a strictly earlier native clock for this exact window.
        assert receipt(job)["planned_entry"] == "matched_block"
        assert proof["actual_source_consumer_admitted"] is True
        assert causal_release["symbol"] == query["symbol"]
        assert causal_release["at_ns"] <= query["end_ns"]
        assert causal_release["quantity"] > 0 or causal_release["order_ids"]
    OUT.mkdir(exist_ok=True)
    cached = OUT / (window_id + "-QA.json")
    if cached.exists():
        cache = json.loads(cached.read_text())
        assert cache["query"] == query and cache["complete"] is True
        verify_bindings(cache["pages"])
        return cache
    if query.get("cache_pages"):
        verify_bindings(query["cache_pages"])
        combined = [
            dict(page, body=(ROOT / page["entity"]["path"]).read_bytes())
            for page in query["cache_pages"]
        ]
        _, qa = validate_pages(combined, query["symbol"], query["query_start_ns"], query["end_ns"])
        cache = dict(
            query=query,
            pages=query["cache_pages"],
            complete=True,
            QA=qa,
            release=causal_release,
            reused_historical_source=True,
            new_GET=0,
        )
        save(cached, cache)
        return cache
    ledger_path = OUT / "request-ledger.json"
    pages = []
    token = None
    previous_last_ns = None
    from open_composer.adapters.data.alpaca_snapshot import _stock_data_client
    from open_composer.cli import _load_env

    _load_env()
    transport = _stock_data_client()
    try:
        url = transport._client.base_url
        assert url.scheme == "https" and url.host == "data.alpaca.markets"
        assert url.path.rstrip("/") == "/v2", "transport_outside_fixed_scope"
        for page in range(query["max_pages"]):
            current_grant()
            assert remaining(job) > 20
            params = dict(query["params"])
            if token is not None:
                params["page_token"] = token
            cap = query["page_cap"]
            assert cap == PAGE_CAP
            with locked_ledger():
                account = json.loads((P / "cumulative-accounting.json").read_text())
                total_req = account["original_market_requests_used"] + account.get(
                    "new_market_requests", 0
                )
                total_bytes = account["original_market_entity_bytes_used"] + account.get(
                    "new_market_entity_bytes", 0
                )
                assert total_req + 1 <= 352 and total_bytes + cap <= 268435456
                ledger = (
                    json.loads(ledger_path.read_text())
                    if ledger_path.exists()
                    else dict(attempts=[], wire_bytes=None)
                )
                assert not any(
                    a["window_id"] == window_id and a["page"] == page for a in ledger["attempts"]
                ), "no implicit retry"
                ordinal = len(ledger["attempts"])
                attempt = dict(
                    window_id=window_id,
                    page=page,
                    ordinal=ordinal,
                    job=job,
                    params=params,
                    causal_release=causal_release,
                    status="predebited",
                    requested_at_utc=datetime.now(UTC).isoformat(),
                    reserved_bytes=cap,
                )
                account["new_market_requests"] = account.get("new_market_requests", 0) + 1
                account["new_market_entity_bytes"] = account.get("new_market_entity_bytes", 0) + cap
                account["market_requests_remaining"] = 352 - total_req - 1
                account["market_entity_remaining_B"] = 268435456 - total_bytes - cap
                save(P / "cumulative-accounting.json", account)
                ledger["attempts"].append(attempt)
                save(ledger_path, ledger)
            body, meta = bounded_get(transport._client, query["path"], params, cap)
            entity = OUT / (f"{ordinal:03}-{window_id}-page{page}.bin")
            entity.write_bytes(body)
            metadata = OUT / (entity.name + ".json")
            save(metadata, meta)
            record = dict(
                entity=bind(entity),
                metadata=bind(metadata),
                http_status=meta["http_status"],
                entity_complete=meta["entity_complete"],
                next_page_token=None,
                fetched_at_utc=datetime.now(UTC).isoformat(),
                historical_first_visible=None,
            )
            with locked_ledger():
                ledger = json.loads(ledger_path.read_text())
                attempt = ledger["attempts"][ordinal]
                attempt.update(
                    entity=bind(entity),
                    metadata=bind(metadata),
                    actual_bytes=len(body),
                    status="response_preserved",
                    fetched_at_utc=record["fetched_at_utc"],
                )
                if meta["entity_complete"]:
                    account = json.loads((P / "cumulative-accounting.json").read_text())
                    account["new_market_entity_bytes"] -= cap - len(body)
                    account["market_entity_remaining_B"] = (
                        268435456
                        - account["original_market_entity_bytes_used"]
                        - account["new_market_entity_bytes"]
                    )
                    save(P / "cumulative-accounting.json", account)
                save(ledger_path, ledger)
            pages.append(record)
            partial = dict(
                query=query, pages=pages, complete=False, unresolved="page_or_clock_unresolved"
            )
            save(cached.with_name(window_id + "-partial.json"), partial)
            if not meta["entity_complete"] or meta["http_status"] != 200:
                raise ValueError("incomplete_or_failed_source_no_followup")
            try:
                observations, token = parse_quotes(body, query["symbol"])
                assert all(
                    query["query_start_ns"] <= q.event_ns <= query["end_ns"] for q in observations
                )
                if observations and previous_last_ns is not None:
                    assert observations[0].event_ns >= previous_last_ns, "cross_page_clock_reversed"
                if observations:
                    previous_last_ns = observations[-1].event_ns
                assert token is None or token != params.get("page_token"), "repeated_page_token"
                assert all(
                    a.event_ns <= b.event_ns
                    for a, b in zip(observations, observations[1:], strict=False)
                )
            except Exception:
                partial["unresolved"] = "clock_schema_or_order_no_followup"
                save(cached.with_name(window_id + "-partial.json"), partial)
                raise
            record["next_page_token"] = token
            save(cached.with_name(window_id + "-partial.json"), partial)
            if token is None:
                combined = []
                for p in pages:
                    combined.append(dict(p, body=(ROOT / p["entity"]["path"]).read_bytes()))
                observations, qa = validate_pages(
                    combined, query["symbol"], query["query_start_ns"], query["end_ns"]
                )
                complete = dict(
                    query=query, pages=pages, complete=True, QA=qa, release=causal_release
                )
                save(cached, complete)
                return complete
            assert page + 1 < query["max_pages"], "pagination_cap_preserves_partial_no_retry"
        raise ValueError("unresolved_source")
    finally:
        transport.close()


def main(job, ids):
    claim(job, "source_witness")
    native_admission(job, REVIEW, "actual_source_calls_admitted")
    scope, proof = admitted_scope(job)
    assert ids == proof["bootstrap_source_ids"]
    for window_id in ids:
        request_window(
            job,
            window_id,
            causal_release=dict(
                kind="bootstrap_source_QA", reason="fixed source route qualification, no engine"
            ),
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--job", required=True)
    p.add_argument("--ids", nargs="+", required=True)
    args = p.parse_args()
    main(args.job, args.ids)
