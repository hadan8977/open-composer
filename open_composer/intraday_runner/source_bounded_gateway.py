"""Verified-paper DAY-limit transport with the final check at Session.request.

No authority writer or account factory lives here. The complete runtime supplies
an authenticated account, exact Main-installed scope and raising current guard.
The gateway retains one-shot journal semantics through SDK/network latency.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from urllib.parse import urlparse

from open_composer.adapters.broker.alpaca_paper import _require_verified_paper_client
from open_composer.intraday_runner.source_dispatch_journal import _canonical, _hash
from open_composer.intraday_runner.source_method_controls import live_quote_ok, require_window


def plain(value):
    if isinstance(value, dict):
        return json.loads(json.dumps(value, default=str))
    return json.loads(value.model_dump_json())


class SourceBoundedGateway:
    def __init__(
        self,
        client,
        *,
        journal,
        account_hash,
        authorized_at,
        expires_at,
        guard,
        read_guard,
        clock=lambda: datetime.now(UTC),
    ):
        _require_verified_paper_client(client)
        self.client, self.journal = client, journal
        self.account_hash = account_hash
        self.authorized_at, self.expires_at = authorized_at, expires_at
        self.guard, self.clock = guard, clock
        self.read_guard = read_guard
        self._armed = None
        self.last_read_status = None
        self.closed = False
        self._original_request = client._session.request
        # The SDK ignores retry_attempts=0 in its constructor. Set actual field
        # and reject any later drift at the final transport boundary.
        client._retry = 0
        from requests.adapters import HTTPAdapter

        client._session.mount("https://", HTTPAdapter(max_retries=0))
        client._session.request = self._request

    def _check_guard(self, request, *, cancellation=False):
        if self.guard(copy.deepcopy(request), cancellation=cancellation) is not None:
            raise ValueError("runtime guard must raise or return None")
        now = self.clock()
        if now.tzinfo is None or not self.authorized_at <= now < self.expires_at:
            raise ValueError("actual gateway authority expired")
        if not cancellation:
            day = datetime.fromisoformat(request["execution_day"]).date()
            wave = require_window(
                now,
                day,
                request["side"],
                authorized_at=self.authorized_at,
                expires_at=self.expires_at,
                cleanup=request.get("cleanup", False),
                own_exit_allowed=request.get("own_exit_allowed", False),
                killed=request.get("killed", False),
            )
            if request.get("cleanup", False):
                wave = datetime.fromisoformat(request["quote_cutoff"])
            if not live_quote_ok(request["quote"], now, wave):
                raise ValueError("quote expired at real transport boundary")

    def _read_path_allowed(self, path):
        return (
            path
            in {
                "/v2/account",
                "/v2/positions",
                "/v2/orders",
                "/v2/orders:by_client_order_id",
                "/v2/account/activities/FILL",
            }
            or path.startswith("/v2/orders/")
            or path.startswith("/v2/assets/")
        )

    def _request(self, method, url, **kwargs):
        if self.closed:
            raise ValueError("closed one-shot gateway")
        target = urlparse(str(url))
        method = str(method).upper()
        if (
            target.scheme != "https"
            or target.netloc != "paper-api.alpaca.markets"
            or target.query
            or target.fragment
        ):
            raise ValueError("non-paper or noncanonical transport origin")
        if self.client._retry != 0:
            raise ValueError("SDK automatic retries changed")
        adapter = self.client._session.get_adapter(str(url))
        if adapter.max_retries.total != 0:
            raise ValueError("HTTP retry layer changed")
        if method == "GET":
            # Read capture/coverage is handled by the separate runtime receiver.
            if not self._read_path_allowed(target.path):
                raise ValueError("unadmitted GET route")
            if self.read_guard() is not None:
                raise ValueError("read scope guard must raise or return None")
            now = self.clock()
            if now.tzinfo is None or not self.authorized_at <= now < self.expires_at:
                raise ValueError("actual GET authority expired/inactive")
        else:
            armed = self._armed
            if armed is None or armed["used"] or (method, target.path) != armed["route"]:
                raise ValueError("write lacks the single exact armed journal operation")
            if kwargs.get("json") != armed["payload"]:
                raise ValueError("SDK payload differs from journaled operation")
            row = self.journal.receive(armed["cid"])
            if _hash(row["request"]) != armed["request_sha256"]:
                raise ValueError("journal payload drift before HTTP")
            snapshot = row["reservation_snapshot"]
            if snapshot.get("account_hash") != self.account_hash:
                raise ValueError("journaled reservation account differs")
            if method == "POST":
                if row["stage"] != "dispatch_boundary_consumed_ack_unknown":
                    raise ValueError("no durable attempted submit marker")
            elif (
                row.get("cancel_attempt", {}).get("state") != "consumed_ack_unknown"
                or row["cancel_attempt"]["broker_order_id"] != armed["broker_id"]
            ):
                raise ValueError("no exact durable owned cancel marker")
            self._check_guard(armed["request"], cancellation=method == "DELETE")
            armed["used"] = True  # Consumed before any physical request attempt.
        kwargs["allow_redirects"] = False
        kwargs["timeout"] = 10
        response = self._original_request(method, url, **kwargs)
        if method == "GET":
            self.last_read_status = getattr(response, "status_code", None)
        return response

    def submit(self, request):
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest

        if self._armed is not None:
            raise ValueError("nested transport operation")
        self._check_guard(request)
        if request["type"] != "limit" or request["time_in_force"] != "day":
            raise ValueError("only reviewed DAY limit operation")
        order = LimitOrderRequest(
            symbol=request["symbol"],
            qty=request["qty"],
            side=OrderSide(request["side"]),
            time_in_force=TimeInForce.DAY,
            limit_price=request["limit_price"],
            client_order_id=request["client_order_id"],
        )
        payload = json.loads(_canonical(order.to_request_fields()))
        self._armed = dict(
            route=("POST", "/v2/orders"),
            payload=payload,
            request=copy.deepcopy(request),
            request_sha256=_hash(request),
            cid=request["client_order_id"],
            used=False,
        )
        try:
            result = self.client.submit_order(order)
            if not self._armed["used"]:
                raise ValueError("SDK returned without guarded transport")
            return plain(result)
        finally:
            self._armed = None

    def cancel(self, cid, broker_id):
        if self._armed is not None or "/" in broker_id:
            raise ValueError("invalid/nested cancel")
        row = self.journal.receive(cid)
        self._check_guard(row["request"], cancellation=True)
        self._armed = dict(
            route=("DELETE", f"/v2/orders/{broker_id}"),
            payload=None,
            request=copy.deepcopy(row["request"]),
            request_sha256=row["request_sha256"],
            cid=cid,
            broker_id=broker_id,
            used=False,
        )
        try:
            self.client.cancel_order_by_id(broker_id)
            if not self._armed["used"]:
                raise ValueError("SDK cancel returned without guarded transport")
        finally:
            self._armed = None

    def close(self):
        self.closed = True
        self.client._session.close()
