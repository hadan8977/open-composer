"""Durable one-shot boundary for a source-method transport supplied by its caller.

No broker client, permission, scheduler, signal, fill application or retry lives
here. The eventual reviewed entry must hold the existing account locks and pass
an authenticated, fully guarded submit callable. This journal does not replace
the account reservation ledger: its snapshot is immutable recovery evidence.

An uncertain/torn consumed record blocks resending. A complete broker observation
can be added for reconciliation; neither an acknowledgment nor a cancel response
releases funds. The accepted SourceReservations remains the cash/lot authority.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from open_composer.adapters.broker.alpaca_paper import _atomic_write_text
from open_composer.intraday_runner.source_method_controls import live_quote_ok, require_window


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: dict) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_durable_directory(path: Path) -> None:
    """Persist directory links before dispatch, including a prior partial mkdir.

    Existence is not proof of a successful previous fsync. Repeat the barriers
    through the filesystem root even when the journal already exists, rather
    than remembering only directories created by this invocation. Refuse alias
    paths so the synchronized ancestor chain is the actual journal's chain.
    Any mkdir/open/fsync failure propagates before a transport callback.
    """
    path = path.absolute()
    if path != path.resolve():
        raise ValueError("journal directory must have a canonical nonsymlink path")
    path.mkdir(parents=True, exist_ok=True)
    for directory in (path, *path.parents):
        _sync_directory(directory)


def classify_own_order(request: dict, observed: dict) -> dict:
    """Validate ownership/quantities without treating cumulative qty as a new fill."""
    for field in ("client_order_id", "symbol", "side", "type", "time_in_force"):
        if observed.get(field) != request[field]:
            raise ValueError(f"broker observation does not match own {field}")
    if not isinstance(observed.get("id"), str) or not observed["id"]:
        raise ValueError("missing actual broker order identity")
    try:
        qty = Decimal(str(observed["qty"]))
        filled = Decimal(str(observed["filled_qty"]))
        limit = Decimal(str(observed["limit_price"]))
    except (KeyError, InvalidOperation) as exc:
        raise ValueError("invalid broker quantity/limit fields") from exc
    if not all(v.is_finite() for v in (qty, filled, limit)):
        raise ValueError("nonfinite broker quantity/limit")
    if qty != request["qty"] or limit != Decimal(str(request["limit_price"])):
        raise ValueError("observed quantity or limit differs from own request")
    if filled != filled.to_integral_value() or not 0 <= filled <= qty:
        raise ValueError("unreconciled nonwhole or excessive filled quantity")
    status = observed.get("status")
    terminal = status in {"filled", "canceled", "cancelled", "expired", "rejected"}
    working = status in {"new", "accepted", "pending_new", "partially_filled"}
    if not terminal and not working and status != "pending_cancel":
        raise ValueError("unknown/replaced order requires reconciliation, not new action")
    if status == "filled" and filled != qty:
        raise ValueError("filled status contradicts cumulative quantity")
    return {
        "broker_order_id": observed["id"],
        "status": status,
        "cumulative_filled": int(filled),
        "remaining": int(qty - filled),
        "terminal_observed": terminal,
        "cancel_eligible": working and filled < qty,
        "not_a_new_execution_delta": True,
        "funds_releasable": False,
    }


class SourceDispatchJournal:
    """A private journal directory; callers must not use a shared generic order path."""

    def __init__(self, directory: Path, *, write_guard=None):
        self.directory = Path(directory).absolute()
        self.write_guard = write_guard

    def _before_write(self, path, size, *, atomic=True):
        if self.write_guard is not None:
            if self.write_guard(path, size, atomic=atomic) is not None:
                raise ValueError("journal storage guard must raise or return None")

    def _write_text(self, path, payload):
        self._before_write(path, len(payload.encode()))
        _atomic_write_text(path, payload)

    def _path(self, cid: str) -> Path:
        if not re.fullmatch(r"dia-base-\d{4}-\d\d-\d\d-(buy|sell|exit)-[A-Z][A-Z0-9.]{0,9}", cid):
            raise ValueError("not a canonical source-method intent ID")
        return self.directory / f"{cid}.json"

    def _validate_execution_request(self, request, execution_day):
        cid = request["client_order_id"]
        cleanup = request.get("cleanup", False)
        intent_role = "exit" if cleanup else request["side"]
        if cid != f"dia-base-{execution_day.isoformat()}-{intent_role}-{request['symbol']}":
            raise ValueError("intent identity differs from execution day/side/symbol")
        price_key, size_key = (
            ("ask", "ask_shares") if request["side"] == "buy" else ("bid", "bid_shares")
        )
        if request["limit_price"] != request["quote"][price_key] or (
            type(request["quote"][size_key]) is not int
            or request["qty"] > request["quote"][size_key]
        ):
            raise ValueError("request exceeds frozen quote price/size")

    def _check_execution_window(self, request, now, execution_day, authorized_at, expires_at):
        wave = require_window(
            now,
            execution_day,
            request["side"],
            authorized_at=authorized_at,
            expires_at=expires_at,
            cleanup=request.get("cleanup", False),
            own_exit_allowed=request.get("own_exit_allowed", False),
            killed=request.get("killed", False),
        )
        if request.get("cleanup", False):
            wave = datetime.fromisoformat(request["quote_cutoff"])
        if not live_quote_ok(request["quote"], now, wave):
            raise ValueError("frozen quote expired before actual dispatch")

    def dispatch_once(
        self,
        prepared: dict,
        *,
        reservation_snapshot: dict,
        signal_binding: dict,
        execution_day: Any,
        authorized_at: datetime,
        expires_at: datetime,
        submit: Callable[[dict], dict],
        revalidate: Callable[[dict], None],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> dict:
        """Consume durably, then recheck guards/age and attempt exactly one dispatch.

        `revalidate` must raise on failure and return None on success; it cannot
        be a truthy status substitute. The eventual authenticated submit gateway
        must run the same check at its final broker-write boundary after any
        additional locks/imports/native gates. No live gateway is granted here.
        """
        # Freeze caller objects before either callback; external mutation cannot
        # rewrite what was reserved and journaled.
        request = json.loads(_canonical(prepared))
        snapshot = json.loads(_canonical(reservation_snapshot))
        signal = json.loads(_canonical(signal_binding))
        cid = request["client_order_id"]
        path = self._path(cid)
        if request.get("type") != "limit" or request.get("time_in_force") != "day":
            raise ValueError("only the explicit DAY limit adaptation is supported")
        if type(request.get("qty")) is not int or request["qty"] <= 0:
            raise ValueError("whole positive quantity required")
        cleanup = request.get("cleanup", False)
        if type(cleanup) is not bool or (cleanup and request["side"] != "sell"):
            raise ValueError("cleanup must be an explicit own sell")
        self._validate_execution_request(request, execution_day)
        if snapshot.get("pending", {}).get(cid) != request.get("reservation"):
            raise ValueError("prepared reservation is not in the persisted snapshot")
        if (
            any(
                request["reservation"].get(k) != request[v]
                for k, v in (
                    ("side", "side"),
                    ("symbol", "symbol"),
                    ("quantity", "qty"),
                    ("limit_price", "limit_price"),
                )
            )
            or request["reservation"].get("filled") != 0
        ):
            raise ValueError("reservation is not this fresh submitted intent")
        if cid not in snapshot.get("consumed_ids", []):
            raise ValueError("reservation intent must already be consumed")
        if set(signal) != {"path", "bytes", "sha256"}:
            raise ValueError("actual logged signal binding required")
        payload = Path(signal["path"]).read_bytes()
        if (
            len(payload) != signal["bytes"]
            or hashlib.sha256(payload).hexdigest() != signal["sha256"]
        ):
            raise ValueError("logged signal binding changed")

        def preflight() -> None:
            if revalidate(json.loads(_canonical(request))) is not None:
                raise ValueError("guard must raise on failure, not return an unchecked status")
            current_signal = Path(signal["path"]).read_bytes()
            if len(current_signal) != signal["bytes"] or (
                hashlib.sha256(current_signal).hexdigest() != signal["sha256"]
            ):
                raise ValueError("logged signal changed before actual dispatch")
            self._check_execution_window(request, clock(), execution_day, authorized_at, expires_at)

        preflight()
        self._before_write(self.directory / ".dispatch.lock", 0, atomic=False)
        _ensure_durable_directory(self.directory)
        with (self.directory / ".dispatch.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            record = {
                "schema_version": 1,
                "client_order_id": cid,
                "request": request,
                "request_sha256": _hash(request),
                "signal_binding": signal,
                "reservation_snapshot": snapshot,
                "stage": "consumed_before_dispatch",
                "observations": [],
                "dispatch_created_at": clock().isoformat(),
            }
            # Exclusive create is the durable no-resend marker, including torn
            # writes. Never remove it on exceptions, even before a network call.
            payload = _canonical(record) + "\n"
            self._before_write(path, len(payload.encode()), atomic=False)
            with path.open("x") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            _sync_directory(self.directory)
            try:
                preflight()  # Includes actual lock/journal latency.
            except Exception as exc:
                record.update(stage="not_dispatched_guard_refusal", error_type=type(exc).__name__)
                self._write_text(path, _canonical(record) + "\n")
                raise
            record["stage"] = "dispatch_boundary_consumed_ack_unknown"
            # Commit the attempted state BEFORE calling a transport. A process
            # death between here and the call remains uncertain, never retryable.
            self._write_text(path, _canonical(record) + "\n")
            try:
                preflight()  # The second durable write can also consume time.
            except Exception as exc:
                record.update(stage="not_dispatched_guard_refusal", error_type=type(exc).__name__)
                self._write_text(path, _canonical(record) + "\n")
                raise
            try:
                observed = submit(json.loads(_canonical(request)))
                record["observations"].append(json.loads(_canonical(observed)))
                record["stage"] = "transport_returned_reconciliation_required"
                self._write_text(path, _canonical(record) + "\n")
            except Exception as exc:
                record.update(
                    stage="dispatch_boundary_consumed_ack_unknown", error_type=type(exc).__name__
                )
                self._write_text(path, _canonical(record) + "\n")
                raise
            return record

    def receive(self, cid: str) -> dict:
        """Read only; missing or malformed consumption is never resend permission."""
        row = json.loads(self._path(cid).read_text())
        if row["client_order_id"] != cid or _hash(row["request"]) != row["request_sha256"]:
            raise ValueError("dispatch journal identity or request changed")
        return row

    def cancel_own_remainder_once(
        self,
        cid: str,
        *,
        authorized_at: datetime,
        expires_at: datetime,
        cancel: Callable[[str], None],
        revalidate: Callable[[dict], None],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> dict:
        """One owned cancel attempt; no cancel acknowledgment or automatic release.

        Actual factory/account/authorization validation is a required eventual
        gateway duty. A broker cancel response itself never proves canceled or
        unfilled: fills may race the cancellation and need real reconciliation.
        """
        if authorized_at.tzinfo is None or expires_at.tzinfo is None:
            raise ValueError("unknown cancel authority expiry")
        self._before_write(self.directory / ".dispatch.lock", 0, atomic=False)
        with (self.directory / ".dispatch.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            row = self.receive(cid)
            if "cancel_attempt" in row:
                raise ValueError("cancel already attempted; reconcile only")
            if not row["observations"]:
                raise ValueError("no actual own order observation to cancel")
            order = classify_own_order(row["request"], row["observations"][-1])
            if not order["cancel_eligible"]:
                return {"action": "no_cancel", "order": order}

            def check() -> None:
                if revalidate(json.loads(_canonical(row))) is not None:
                    raise ValueError("cancel guard must raise on refusal")
                now = clock()
                if now.tzinfo is None or not authorized_at <= now < expires_at:
                    raise ValueError("cancel authority expired")

            check()
            row["cancel_attempt"] = {
                "broker_order_id": order["broker_order_id"],
                "state": "consumed_ack_unknown",
            }
            path = self._path(cid)
            self._write_text(path, _canonical(row) + "\n")
            try:
                check()
                cancel(order["broker_order_id"])
                row["cancel_attempt"]["state"] = "request_returned_not_cancel_confirmation"
                self._write_text(path, _canonical(row) + "\n")
            except Exception as exc:
                row["cancel_attempt"]["error_type"] = type(exc).__name__
                self._write_text(path, _canonical(row) + "\n")
                raise
            return {"action": "cancel_requested", "order": order, "funds_releasable": False}
