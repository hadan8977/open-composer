"""Private returned-exception fixtures; no broker/client construction or network."""

import copy
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from alpaca.common.exceptions import APIError
from requests import HTTPError, Request, Response

from open_composer.intraday_runner import six_paper_service as service

CID = "six-53ee69b0f53f4186bf6593b7b133ed0a41d1"
NOW = datetime(2026, 10, 24, 7, tzinfo=UTC)
RECORD = dict(
    book="BASE_STATE_BUDGET",
    symbol="AAPL",
    side="sell",
    qty=4,
    limit_price=337.81,
    status="prepared_unknown_until_queried",
    query_error="APIError",
)


def api_error(status=404, *, url=None, body=None, method="GET"):
    response = Response()
    response.status_code = status
    response._content = (
        body if body is not None else b'{"code":40410000,"message":"order not found"}'
    )
    response.request = Request(
        method,
        url
        or "https://paper-api.alpaca.markets/v2/orders:by_client_order_id?client_order_id=" + CID,
        headers={
            "APCA-API-KEY-ID": "private-fixture-key",
            "Authorization": "Bearer fixture-secret",
        },
    ).prepare()
    return APIError(response.text, HTTPError("private unlogged error", response=response))


def receive(error):
    return service.order_lookup_failure(error, CID, RECORD, NOW.isoformat(), NOW.isoformat())


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("No network permitted in evidence fixtures")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.mark.parametrize(
    "status,outcome",
    [
        (404, "provider_http_not_found"),
        (401, "provider_authority_failure"),
        (403, "provider_authority_failure"),
        (429, "provider_transient_failure"),
        (503, "provider_transient_failure"),
        (422, "provider_http_error"),
    ],
)
def test_actual_sdk_error_retains_bound_status_but_never_disposes(status, outcome):
    row = receive(api_error(status))
    assert row["outcome"] == outcome and row["http_status"] == status
    assert row["matching_paper_GET_request"] is True
    assert row["expected_order"]["qty"] == 4
    assert row["terminal_or_never_submitted_proof"] is False
    assert row["disposition_permitted"] is False
    assert row["original_submission_stage"] == "unknown"


@pytest.mark.parametrize(
    "url,method",
    [
        (
            "https://paper-api.alpaca.markets/v2/orders:by_client_order_id?client_order_id=foreign",
            "GET",
        ),
        (
            "https://api.alpaca.markets/v2/orders:by_client_order_id?client_order_id=" + CID,
            "GET",
        ),
        ("https://paper-api.alpaca.markets/v2/orders?client_order_id=" + CID, "GET"),
        (
            "https://paper-api.alpaca.markets/v2/orders:by_client_order_id?client_order_id=" + CID,
            "POST",
        ),
        (
            "https://paper-api.alpaca.markets/v2/orders:by_client_order_id?client_order_id="
            + CID
            + "&client_order_id="
            + CID,
            "GET",
        ),
        (
            "https://paper-api.alpaca.markets/v2/orders:by_client_order_id?client_order_id="
            + CID
            + "&token=secret",
            "GET",
        ),
    ],
)
def test_foreign_request_cannot_become_matching_not_found(url, method):
    row = receive(api_error(url=url, method=method))
    assert row["outcome"] == "unbound_http_error"
    assert row["matching_paper_GET_request"] is False
    assert "secret" not in json.dumps(row)


def test_error_and_response_request_must_be_the_same_received_request():
    error = api_error()
    error._http_error.request = Request(
        "GET",
        "https://paper-api.alpaca.markets/v2/orders:by_client_order_id?client_order_id=" + CID,
    ).prepare()
    assert receive(error)["outcome"] == "unbound_http_error"


@pytest.mark.parametrize(
    "body",
    [
        b'{"code":40410000,"message":"APCA_API_SECRET_KEY=fixture-secret","token":"private-fixture-key"}',
        b'{"code":"private-fixture-key","message":"Bearer fixture-secret"}',
        b"Authorization: Bearer fixture-secret",
        b"[" * 2000 + b"]" * 2000,
        b"fixture-secret" * 6000,
    ],
)
def test_body_is_hash_bound_without_free_form_secrets_or_unsafe_decode(body):
    row = receive(api_error(body=body))
    assert row["response_body_sha256"] == hashlib.sha256(body).hexdigest()
    assert row["response_body_bytes"] == len(body)
    encoded = json.dumps(row)
    assert "fixture-secret" not in encoded and "private-fixture-key" not in encoded
    assert "Authorization" not in encoded and "APCA" not in encoded


@pytest.mark.parametrize(
    "error",
    [
        APIError('{"code":40410000,"message":"order not found"}'),
        ValueError("Bearer fixture-secret"),
        TimeoutError("APCA_API_SECRET_KEY=fixture-secret"),
    ],
)
def test_error_class_or_unbound_text_is_not_a_provider_receipt(error):
    row = receive(error)
    assert row["outcome"] == "lookup_transport_or_local_failure"
    assert row["http_status"] is None and not row["matching_paper_GET_request"]
    assert "fixture-secret" not in json.dumps(row)


def runtime(tmp_path, errors):
    instance = object.__new__(service.SixPaperService)
    instance.root, instance.path = tmp_path, tmp_path / "state.json"
    instance.clock = lambda: NOW
    instance.limiter = SimpleNamespace(acquire=lambda: None)
    calls, events = [], []
    sequence = iter(errors)

    def get_order(cid):
        calls.append(cid)
        raise next(sequence)

    instance.client = SimpleNamespace(get_order_by_client_id=get_order)
    instance.event = lambda kind, **kw: events.append((kind, copy.deepcopy(kw)))
    instance.state = dict(
        orders={CID: copy.deepcopy(RECORD)},
        books={
            "BASE_STATE_BUDGET": dict(
                pending={CID: dict(side="sell", quantity=4, filled=0)},
                consumed_ids=[CID],
                cashbook=dict(cash=20000, lots={"AAPL": [{"quantity": 11}]}),
                evidence=dict(fee_holds="retained", risk={"high_water": 20000}),
            )
        },
    )
    return instance, calls, events


def test_native_query_unchanged_and_error_evidence_durable_without_book_or_hold_change(
    tmp_path,
):
    instance, calls, events = runtime(tmp_path, [api_error(), api_error(), api_error(403)])
    before = copy.deepcopy(instance.state["books"])
    instance.sync_orders()
    assert calls == [CID]
    assert instance.state["books"] == before
    saved = json.loads(instance.path.read_text())
    assert saved["orders"][CID]["last_query_failure"]["outcome"] == "provider_http_not_found"
    assert saved["orders"][CID]["status"] == "prepared_unknown_until_queried"
    instance.sync_orders()
    assert calls == [CID, CID] and len(events) == 1
    assert instance.state["orders"][CID]["last_query_failure"]["matching_observations"] == 2
    instance.sync_orders()
    assert len(events) == 2 and calls == [CID, CID, CID]
    assert events[0][1]["evidence"]["http_status"] == 404
    assert events[1][1]["evidence"]["http_status"] == 403
    assert instance.state["books"] == before
    assert "terminal_disposition" not in instance.state["orders"][CID]


def test_terminal_disposition_is_not_requeried(tmp_path):
    instance, calls, events = runtime(tmp_path, [])
    instance.state["orders"][CID]["terminal_disposition"] = True
    instance.sync_orders()
    assert calls == [] and events == []
