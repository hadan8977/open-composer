"""DAY-reference policy adapters over the accepted journal and guarded gateway.

Only policy/identity/window checks differ. Durable attempt markers, final exact
payload/account validation, no retries and cancellation ownership are inherited.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import (
    DAY,
    NAMESPACE,
    aware,
    identity,
    limit_price,
    number,
    require_phase,
)
from open_composer.intraday_runner.source_bounded_gateway import SourceBoundedGateway
from open_composer.intraday_runner.source_dispatch_journal import (
    SourceDispatchJournal,
    _canonical,
    _hash,
    _sync_directory,
)
from open_composer.intraday_runner.validation_account_partition import SLOTS


def validate_request(request, execution_day, namespace=NAMESPACE):
    cleanup = request.get("cleanup", False)
    identity(
        request["client_order_id"],
        request["symbol"],
        request["side"],
        execution_day,
        cleanup=cleanup,
        namespace=namespace,
    )
    if request.get("execution_day") != execution_day.isoformat():
        raise ValueError("request day mismatch")
    if not cleanup and (execution_day != DAY or request.get("reference_day") != "2026-10-19"):
        raise ValueError("not the fixed initial reference/session")
    if request.get("reference_valid") is not True:
        raise ValueError("unreceived action/unit/reference")
    if number(request["limit_price"]) != limit_price(
        request["reference_price"], exit_order=cleanup
    ):
        raise ValueError("changed protected limit")
    if cleanup and request.get("own_exit_allowed") is not True:
        raise ValueError("unowned exit")


def check_window(
    request,
    now,
    execution_day,
    authorized_at,
    expires_at,
    namespace=NAMESPACE,
    *,
    prospective=False,
):
    validate_request(request, execution_day, namespace)
    require_phase(
        now,
        "exit" if request.get("cleanup", False) else "buy",
        authorized_at,
        expires_at,
        killed=request.get("killed", False),
        prospective=prospective,
    )


class CurrentDispatchJournal(SourceDispatchJournal):
    def __init__(self, directory, *, namespace=NAMESPACE, write_guard=None, prospective=False):
        if namespace not in {row[1] for row in SLOTS.values()}:
            raise ValueError("unselected dispatch namespace")
        super().__init__(directory, write_guard=write_guard)
        self.namespace = namespace
        if type(prospective) is not bool:
            raise ValueError("unknown prospective journal scope")
        self.prospective = prospective

    @contextmanager
    def initial_batch_locked(self):
        path = self.directory / ".dispatch.lock"
        self._before_write(path, 0, atomic=False)
        from open_composer.intraday_runner.source_dispatch_journal import _ensure_durable_directory

        _ensure_durable_directory(self.directory)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size != 0:
                raise ValueError("invalid batch dispatch lock")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.batch_lock_identity = (st.st_dev, st.st_ino)
            yield
        finally:
            self.batch_lock_identity = None
            os.close(fd)

    def prepare_initial_batch(self, requests, *, snapshot, signal, owner, clock):
        """Persist intent evidence before the account clock; no reservation is armed.

        A prepared record cannot submit. The later single checkpoint CAS binds
        these exact bytes and the native owner before any gateway can receive an
        attempted stage. Torn preparations are retained, never overwritten.
        """
        if (
            not self.prospective
            or not owner
            or getattr(self, "batch_owner", None)
            or not getattr(self, "batch_lock_identity", None)
        ):
            raise ValueError("invalid/repeated initial batch preparation")
        if not requests or len({r["client_order_id"] for r in requests}) != len(requests):
            raise ValueError("empty/duplicate batch")
        self.batch_owner = copy.deepcopy(owner)
        self.batch_used = set()
        self.batch_transport = {}
        rows = {}
        for request in requests:
            request = json.loads(_canonical(request))
            cid = request["client_order_id"]
            self._validate_execution_request(request, DAY)
            if (
                (request.get("type"), request.get("time_in_force"), request.get("side"))
                != ("limit", "day", "buy")
                or type(request.get("qty")) is not int
                or request["qty"] <= 0
            ):
                raise ValueError("initial batch is whole-share DAY buy only")
            if (
                snapshot["pending"].get(cid) != request["reservation"]
                or cid not in snapshot["consumed_ids"]
            ):
                raise ValueError("planned reservation mismatch")
            payload = Path(signal["path"]).read_bytes()
            if (
                len(payload) != signal["bytes"]
                or hashlib.sha256(payload).hexdigest() != signal["sha256"]
            ):
                raise ValueError("initial batch signal changed")
            record = dict(
                schema_version=2,
                client_order_id=cid,
                request=request,
                request_sha256=_hash(request),
                signal_binding=signal,
                reservation_snapshot=snapshot,
                stage="prepared_no_dispatch",
                observations=[],
                prepared_owner=owner,
                dispatch_created_at=clock().isoformat(),
                preparation_is_not_account_or_submit_permission=True,
            )
            payload = (_canonical(record) + "\n").encode()
            path = self._path(cid)
            self._before_write(path, len(payload), atomic=False)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(fd)
            finally:
                os.close(fd)
            _sync_directory(self.directory)
            st = path.lstat()
            rows[cid] = dict(
                path=str(path),
                bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                identity=[st.st_dev, st.st_ino],
            )
        self.prepared_batch = dict(owner=copy.deepcopy(owner), records=rows)
        return copy.deepcopy(self.prepared_batch)

    def receive(self, cid):
        path = self._path(cid)
        before = path.lstat()
        if path != path.resolve() or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("aliased dispatch journal")
        payload = path.read_bytes()
        after = path.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("journal changed during reception")
        row = json.loads(payload)
        if row["client_order_id"] != cid or _hash(row["request"]) != row["request_sha256"]:
            raise ValueError("dispatch journal identity/request changed")
        if row.get("stage") == "prepared_no_dispatch":
            reader = getattr(self, "batch_checkpoint", None)
            if reader is None:
                return row
            checkpoint = reader()
            arm = checkpoint["snapshot"]["evidence"].get("initial_batch_arm")
            if arm is None:
                return row
            binding = arm.get("records", {}).get(cid)
            actual = dict(
                path=str(path),
                bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                identity=[after.st_dev, after.st_ino],
            )
            snapshot = checkpoint["snapshot"]
            if (
                binding != actual
                or arm.get("owner") != row["prepared_owner"]
                or snapshot["pending"].get(cid) != row["request"]["reservation"]
                or cid not in snapshot["consumed_ids"]
            ):
                raise ValueError("prepared journal lacks exact durable reservation arm")
            # Derived from the current durable arm, never written/backdated as
            # a physical submit. A crash is uncertain and holds every arm.
            row["stage"] = "dispatch_boundary_consumed_ack_unknown"
            row["batch_arm"] = copy.deepcopy(arm)
            row["batch_arm_checkpoint_sha256"] = _hash(checkpoint)
        return row

    def dispatch_prepared_once(
        self, request, *, signal, owner, authorized_at, expires_at, submit, revalidate, clock
    ):
        cid = request["client_order_id"]
        lock = (self.directory / ".dispatch.lock").lstat()
        if (self.directory / ".dispatch.lock").is_symlink() or (
            lock.st_dev,
            lock.st_ino,
        ) != self.batch_lock_identity:
            raise ValueError("batch dispatch lock changed")
        if (
            owner != getattr(self, "batch_owner", None)
            or cid in self.batch_used
            or cid not in self.prepared_batch["records"]
        ):
            raise ValueError("batch belongs to another invocation or was consumed")
        row = self.receive(cid)
        if (
            row["stage"] != "dispatch_boundary_consumed_ack_unknown"
            or row.get("batch_arm") != self.prepared_batch
            or row["request"] != request
            or row["signal_binding"] != signal
        ):
            raise ValueError("unarmed/replaced batch request")
        self.batch_used.add(cid)  # Never retry even a positively local refusal.
        self.batch_active = cid
        self.batch_transport[cid] = dict(physical_call_started=False)
        try:
            payload = Path(signal["path"]).read_bytes()
            if (
                len(payload) != signal["bytes"]
                or hashlib.sha256(payload).hexdigest() != signal["sha256"]
            ):
                raise ValueError("batch signal changed")
            if revalidate(copy.deepcopy(request)) is not None:
                raise ValueError("guard must raise")
            self._check_execution_window(request, clock(), DAY, authorized_at, expires_at)
            observed = submit(copy.deepcopy(request))
            row["observations"].append(json.loads(_canonical(observed)))
            row["stage"] = "transport_returned_reconciliation_required"
        except Exception as exc:
            row.update(
                stage=(
                    "dispatch_boundary_consumed_ack_unknown"
                    if self.batch_transport[cid]["physical_call_started"]
                    else "not_dispatched_guard_refusal"
                ),
                error_type=type(exc).__name__,
            )
            raise
        finally:
            row["transport_evidence"] = copy.deepcopy(self.batch_transport[cid])
            self.batch_active = None
            # ACK, error, or positive pre-submit refusal plus actual physical
            # metadata share ONE guarded atomic publication. If it fails, the
            # unchanged prepared record + durable arm remains unknown/held.
            self._write_text(self._path(cid), _canonical(row) + "\n")
        return row

    def _path(self, cid):
        if not re.fullmatch(
            re.escape(self.namespace) + r"-\d{4}-(buy|exit)-[A-Z][A-Z0-9.]{0,9}", cid
        ):
            raise ValueError("not a scoped current-initialization CID")
        return self.directory / f"{cid}.json"

    def _validate_execution_request(self, request, execution_day):
        validate_request(request, execution_day, self.namespace)

    def _check_execution_window(self, request, now, execution_day, authorized_at, expires_at):
        check_window(
            request,
            now,
            execution_day,
            authorized_at,
            expires_at,
            self.namespace,
            prospective=self.prospective,
        )


class CurrentBoundedGateway(SourceBoundedGateway):
    def _read_path_allowed(self, path):
        # The receiver validates exact parameters and complete pagination.
        return super()._read_path_allowed(path) or path in {"/v2/account/activities", "/v2/clock"}

    def _check_guard(self, request, *, cancellation=False):
        # Must include fresh authenticated observation, persistent risk, state,
        # code and scope checks again after journal/SDK latency.
        if self.guard(request.copy(), cancellation=cancellation) is not None:
            raise ValueError("runtime guard must raise or return None")
        now = aware(self.clock())
        if not aware(self.authorized_at) <= now < aware(self.expires_at):
            raise ValueError("actual gateway authority expired")
        if cancellation and getattr(self, "cancel_window", None) is not None:
            if self.cancel_window(request.copy()) is not None:
                raise ValueError("cancel window guard must raise")
        elif cancellation:
            require_phase(
                now,
                "exit" if request.get("cleanup") else "cancel",
                self.authorized_at,
                self.expires_at,
                killed=request.get("killed", False),
            )
        else:
            check_window(
                request,
                now,
                datetime.fromisoformat(request["execution_day"]).date(),
                self.authorized_at,
                self.expires_at,
                self.journal.namespace,
                prospective=getattr(self.journal, "prospective", False),
            )


def fresh_clock():
    return datetime.now(UTC)
