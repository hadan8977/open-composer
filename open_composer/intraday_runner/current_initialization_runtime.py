"""Scoped current BASE orchestration over existing cash/checkpoint/dispatch code.

No default authority or scheduler. Real entry must bind an accepted native job,
exact implementation, owner scope, scientific reception and isolated account.
"""

from __future__ import annotations

import base64
import copy
import fcntl
import json
import os
import stat
import time
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

from open_composer.adapters.broker.alpaca_paper import (
    _atomic_write_text,
    _require_kill_switch_clear,
)
from open_composer.intraday_runner.current_initialization_account import capture
from open_composer.intraday_runner.current_initialization_controls import (
    ACCOUNT,
    DAY,
    ENV_PATH,
    aware,
    limit_price,
    number,
    receive_observation,
    require_broker_open,
    require_phase,
    risk_transition,
    winddown,
)
from open_composer.intraday_runner.current_initialization_dispatch import (
    CurrentBoundedGateway,
    CurrentDispatchJournal,
)
from open_composer.intraday_runner.source_activity_reception import bind, save
from open_composer.intraday_runner.source_dispatch_journal import (
    _ensure_durable_directory,
    _hash,
    classify_own_order,
)
from open_composer.intraday_runner.source_execution_receipts import apply_bound_fill
from open_composer.intraday_runner.source_method_bindings import bound_bytes, source_module
from open_composer.intraday_runner.source_reservations import SourceReservations
from open_composer.intraday_runner.source_state_checkpoint import (
    SourceStateCheckpoint,
    restore,
    snapshot,
)
from open_composer.intraday_runner.source_terminal_holds import (
    abandon_never_attempted,
    retain_terminal_liability,
)
from open_composer.intraday_runner.validation_account_partition import (
    BASE,
    LSTM,
    SLOTS,
    ValidationAccountPartition,
    allocation,
    receive_partition,
    slot,
)


def secure_identity():
    p = Path(ENV_PATH)
    st = p.lstat()
    if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o600 or p != p.resolve():
        raise ValueError("dedicated regular 0600 secure file required")
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def load_authority(root, binding, now):
    auth = json.loads(bound_bytes(root, binding))
    from open_composer.intraday_runner.current_initialization_episode import receive_day

    receive_day(root, auth)
    task = auth.get("task_id")
    if task not in SLOTS or auth.get("active") is not True:
        raise ValueError("no scoped active authority")
    if (
        auth.get("account_hash") != ACCOUNT
        or auth.get("env_path") != ENV_PATH
        or auth.get("namespace") != slot(root, task)[1]
    ):
        raise ValueError("wrong isolated account/config/namespace")
    partition = receive_partition(root, auth["partition"])
    cap = allocation(root, auth["partition"], task)
    if (
        number(auth.get("capital_usd")) != cap
        or auth.get("gross_multiple") != 1
        or auth.get("long_cash_only") is not True
    ):
        raise ValueError("scope expansion")
    now = aware(now)
    if (
        not aware(auth["authorized_at"])
        <= now
        < aware(auth["expires_at"])
        <= datetime(2026, 11, 14, tzinfo=UTC)
    ):
        raise ValueError("authority inactive or expired")
    main = json.loads(bound_bytes(root, auth["main_scope"]))
    if (
        main.get("owner_account_scope_bound") is not True
        or main.get("account_hash") != ACCOUNT
        or main.get("explicit_env_path") != ENV_PATH
    ):
        raise ValueError("actual Main account purpose binding absent")
    if auth["ledger_root"] != str(slot(root, task)[0]):
        raise ValueError("wrong partitioned isolated ledger")
    for b in auth["code_bindings"]:
        bound_bytes(root, b)
    for key in ("spec", "policy", "model", "scientific_acceptance", "operating_acceptance"):
        bound_bytes(root, auth[key])
    # Prospective owner-authorized paper validation only. No promotion/research
    # pass is synthesized; operational review must explicitly accept this scope.
    op = json.loads(bound_bytes(root, auth["operating_acceptance"]))
    accepted_trial = op.get("accepted_trial_bindings", {}).get(task, {})
    if (
        op.get("accepted_current_runtime") is not True
        or op.get("reviewer") != "66ad4b54-ec62-400b-9a03-a29682cf58e6"
        or op.get("account_hash") != ACCOUNT
        or accepted_trial.get("policy") != auth["policy"]
        or accepted_trial.get("spec") != auth["spec"]
        or op.get("code_bindings") != auth["code_bindings"]
        or accepted_trial.get("scientific_acceptance") != auth["scientific_acceptance"]
        or accepted_trial.get("scientific_consumer") != auth.get("scientific_consumer")
        or op.get("accepted_current_day_continuation") is not True
        or op.get("current_day_selection") != auth["current_day_selection"]
        or accepted_trial.get("application_day") != auth["application_day"]
        or accepted_trial.get("reference_day") != auth["reference_day"]
        or op.get("partition") != auth["partition"]
    ):
        raise ValueError("affected runtime/safety reception missing")
    validation = json.loads(bound_bytes(root, auth["paper_validation"]))
    if (
        accepted_trial.get("paper_validation") != auth["paper_validation"]
        or validation.get("economic_only_exception") is not True
        or validation.get("generic_promotion_or_harness_pass_claimed") is not False
        or validation.get("task_id") != task
        or validation.get("account_hash") != ACCOUNT
        or (
            validation.get("partition") != auth["partition"]
            and not (
                task == BASE
                and partition.get("selected_task") == LSTM
                and validation.get("partition") == partition.get("prior_partition")
            )
        )
        or any(
            validation.get(key) != auth[key]
            for key in (
                "spec",
                "policy",
                "model",
                "scientific_acceptance",
                "ledger_root",
                "capital_usd",
                "application_day",
                "reference_day",
                "current_day_selection",
            )
        )
    ):
        raise ValueError("exact scoped paper-validation admission missing")
    purpose = json.loads(bound_bytes(root, validation["Main_validation"]))
    bound_bytes(root, validation["owner_instruction"])
    if (
        purpose.get("scope_authorized") is not True
        or purpose.get("selected_route") != BASE
        or purpose.get("owner_instruction") != validation["owner_instruction"]
    ):
        raise ValueError("actual owner paper-validation purpose absent")
    initial = json.loads(bound_bytes(root, auth["initial_account_scope"]))
    if auth.get("reconciliation_after") != initial.get("captured_at_utc") or aware(
        auth["reconciliation_after"]
    ) > aware(auth["authorized_at"]):
        raise ValueError("account reconciliation must retain the received baseline interval")
    receive_partition(root, auth["partition"])
    directory, namespace = slot(root, task)
    if auth["ledger_root"] != str(directory) or auth["namespace"] != namespace:
        raise ValueError("partition slot differs")
    winddown(auth["expires_at"])
    return auth


class CurrentInitializationRuntime:
    def __init__(
        self,
        root,
        authority,
        *,
        entry_guard,
        client_factory=None,
        capture_storage=None,
        clock=lambda: datetime.now(UTC),
        monotonic=time.monotonic,
    ):
        self.root, self.authority = Path(root), authority
        self.clock, self.monotonic, self.entry_guard = clock, monotonic, entry_guard
        self.auth = load_authority(self.root, authority, clock())
        self.directory = Path(self.auth["ledger_root"])
        self.task = self.auth["task_id"]
        self.namespace = self.auth["namespace"]
        self.partition = ValidationAccountPartition(
            self.root, self.auth["partition"], write_guard=self.guard_write
        )
        if self.directory != self.directory.resolve() or not self.directory.is_absolute():
            raise ValueError("aliased ledger")
        self.store = SourceStateCheckpoint(
            self.directory / "checkpoints",
            account_hash=ACCOUNT,
            sleeve_id=self.task,
            write_guard=self.guard_write,
        )
        self.journal = CurrentDispatchJournal(
            self.directory / "dispatch",
            namespace=self.namespace,
            write_guard=self.guard_write,
            prospective=self.auth.get("session_id") == "SIX-CURRENT-SESSION-20261020",
        )
        self.journal.batch_checkpoint = lambda: self.store.load()
        self.client_factory = client_factory
        self.gateway = None
        self.observation = None
        self._operation_held = False
        self.transport_bytes = 0
        self.transport_count = 0
        self.trace_directory = None
        self.trace_directory_identity = None
        self.current_request = None
        self.current_response = None
        self.current_phase = None
        self.secure_snapshot = None
        self.required_symbols = set()
        self.capture_storage = capture_storage
        self.capture_slots = None

    def require_phase(self, phase, *, killed=False):
        return require_phase(
            self.clock(),
            phase,
            self.auth["authorized_at"],
            self.auth["expires_at"],
            killed=killed,
            prospective=self.auth.get("session_id") == "SIX-CURRENT-SESSION-20261020",
        )

    @property
    def cap(self):
        return number(self.auth["capital_usd"])

    def read_guard(self, *, preparation_only=False):
        if type(preparation_only) is not bool:
            raise ValueError("unknown read guard mode")
        if not self._operation_held:
            raise ValueError("operation lock absent")
        if self.secure_snapshot is not None and secure_identity() != self.secure_snapshot:
            raise ValueError("secure configuration changed during this account invocation")
        if getattr(self.entry_guard, "receives_authority", False) is True:
            received = self.entry_guard(preparation_only=preparation_only, receive_authority=True)
        else:
            guarded = (
                self.entry_guard(preparation_only=True) if preparation_only else self.entry_guard()
            )
            if guarded is not None:
                raise ValueError("entry guard must raise")
            received = load_authority(self.root, self.authority, self.clock())
        if received != self.auth:
            raise ValueError("scope drift")
        if (
            not aware(self.auth["authorized_at"])
            <= aware(self.clock())
            < aware(self.auth["expires_at"])
        ):
            raise ValueError("scope expired during binding checks")

    @contextmanager
    def operation(self):
        self.ensure_directory(self.directory)
        from open_composer.paper_lock import paper_control_lock, paper_submission_lock

        # These shared production lock files are provisioned by the existing
        # paper system, outside this route's owned roots. Never create them as
        # an unbudgeted side effect of a new sleeve.
        for name in (".submission.lock", ".control.lock"):
            path = self.root / "reports/paper" / name
            st = path.lstat()
            if path != path.resolve() or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise ValueError("existing production lock identity required")
        with ExitStack() as stack:
            stack.enter_context(paper_submission_lock(self.root))
            stack.enter_context(paper_control_lock(self.root))
            stack.enter_context(self.partition.locked())
            self.guard_write(self.directory / ".operation.lock", 0, atomic=False)
            lock = stack.enter_context((self.directory / ".operation.lock").open("a+"))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._operation_held = True
            try:
                self.read_guard()
                yield self
            finally:
                self._operation_held = False
                if self.gateway is not None:
                    self.gateway.close()

    def guard_write(self, path, size, *, atomic=True):
        path = Path(path)
        if not path.is_absolute() or path != path.resolve():
            raise ValueError("aliased runtime mutation path")
        if type(size) is not int or size < 0 or type(atomic) is not bool:
            raise ValueError("invalid runtime mutation bound")
        # Payload blocks plus atomic overlap and directory/lock metadata. The
        # entry checks missing ancestors and all aggregate roots again now.
        extra = (2 if atomic else 1) * ((size + 4095) // 4096) * 4096 + 8192
        if (
            self.entry_guard(extra_write_bytes=extra, write_path=str(path), local_only=True)
            is not None
        ):
            raise ValueError("runtime storage guard must raise")

    def ensure_directory(self, path):
        self.guard_write(Path(path) / ".directory", 0, atomic=False)
        _ensure_durable_directory(path)

    def save_capture(self, path, value):
        encoded = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        slots = getattr(self, "capture_slots", None)
        if slots is not None and Path(path) in slots.files:
            # No authority/kernel/code check is cached. Only allocation traversal
            # is unnecessary for an already allocated, immutable one-use extent.
            self.read_guard(preparation_only=True)
            if len(encoded) > slots.files[Path(path)][2]:
                # Retain the COMPLETE oversized value under the original full
                # allocation/atomic guard. Its returned binding names that exact
                # envelope; the unused slot stays allocated, no truncation/quota.
                overflow = Path(str(path) + ".overflow.json")
                self.guard_write(overflow, len(encoded))
                result = save(overflow, value)
                slots.used.add(Path(path))
                return result
            return slots.publish(path, encoded)
        self.guard_write(path, len(encoded))
        return save(path, value)

    def prepare_capture(self, directory):
        storage = getattr(self, "capture_storage", None)
        if storage is None:
            self.guard_write(directory / ".capture", 0, atomic=False)
            _ensure_durable_directory(directory.parent)
            directory.mkdir(exist_ok=False)
            return
        from open_composer.intraday_runner.current_initialization_storage import CaptureSlots

        self.read_guard()
        self.capture_slots = CaptureSlots(
            storage, directory, self.trace_directory, self.required_symbols, self.transport_count
        )

    def write_text(self, path, payload):
        self.guard_write(path, len(payload.encode()))
        _atomic_write_text(path, payload)

    def prepare_trace_directory(self):
        if self.trace_directory is None or self.trace_directory_identity is not None:
            raise ValueError("missing or already prepared trace directory")
        self.ensure_directory(self.trace_directory)
        path = Path(self.trace_directory)
        identities = []
        for p in (path, *path.parents):
            fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                st = os.fstat(fd)
                os.fsync(fd)  # Bind the actual inode whose barrier completed.
                identities.append((str(p), st.st_dev, st.st_ino))
            finally:
                os.close(fd)
        self.trace_directory_identity = tuple(identities)
        self.check_trace_directory()

    def check_trace_directory(self):
        # Only invariant directory-link identity is retained. Allocation, code,
        # authority and financial observations are still checked at every use.
        if (
            not self.trace_directory_identity
            or str(self.trace_directory) != self.trace_directory_identity[0][0]
            or Path(self.trace_directory) != Path(self.trace_directory).resolve()
        ):
            raise ValueError("trace directory identity absent or aliased")
        for name, device, inode in self.trace_directory_identity:
            st = Path(name).lstat()
            if not stat.S_ISDIR(st.st_mode) or (st.st_dev, st.st_ino) != (device, inode):
                raise ValueError("prepared durable trace directory chain changed")

    def connect(self):
        self.read_guard()
        if self.gateway is not None:
            return
        # All directory-link fsync barriers precede the first captured account
        # response. Later requests validate the exact chain; never recreate it.
        self.prepare_trace_directory()
        from open_composer.book_paper.accounts import make_trading_client

        # Explicit secure path, never the global default/old quant2 credentials.
        self.secure_snapshot = secure_identity()
        client = (
            self.client_factory or (lambda: make_trading_client("quant2", env_path=Path(ENV_PATH)))
        )()
        if secure_identity() != self.secure_snapshot:
            raise ValueError("secure configuration changed during factory loading")
        self.gateway = CurrentBoundedGateway(
            client,
            journal=self.journal,
            account_hash=ACCOUNT,
            authorized_at=aware(self.auth["authorized_at"]),
            expires_at=aware(self.auth["expires_at"]),
            guard=self.order_guard,
            # This callback precedes trace publication, not physical transport.
            # Every publication and the final GET below still performs a fresh
            # full allocation/free-space check. No prior result is cached.
            read_guard=lambda: self.read_guard(preparation_only=True),
            clock=self.clock,
        )
        self.gateway.cancel_window = self.cancel_window
        physical = self.gateway._original_request

        def bounded(method, url, **kwargs):
            # Called only after inherited final journal/account/payload gates.
            # GET has just run this same guard in SourceBoundedGateway._request;
            # its separate final post-publication guard below remains mandatory.
            if method.upper() != "GET":
                self.read_guard(preparation_only=True)
            if method.upper() == "GET":
                params = kwargs.get("params", {}) or {}
                intent = copy.deepcopy(self.current_request)
                if (
                    not isinstance(intent, dict)
                    or self.current_response is not None
                    or urlparse(url).path != "/v2" + intent["endpoint"]
                    or params != intent["params"]
                ):
                    raise ValueError("physical GET differs from the captured request intent")
                if "activities" in url and (
                    params.get("after") != self.auth["reconciliation_after"]
                    or params.get("page_size") != 100
                    or params.get("direction") != "asc"
                ):
                    raise ValueError("activity read outside scoped complete prefix")
            if method.upper() != "GET":
                permitted = {"POST": {"buy", "exit"}, "DELETE": {"cancel", "exit"}}
                if self.current_phase not in permitted.get(method.upper(), set()):
                    raise ValueError("this native phase is GET-only")
                if (
                    self.entry_guard(write_method=method.upper(), phase=self.current_phase)
                    is not None
                ):
                    raise ValueError("native write scope must raise on refusal")
                armed = self.gateway._armed
                if armed is None:
                    raise ValueError("missing final exact armed operation")
            self.check_trace_directory()
            ordinal = self.transport_count
            self.transport_count += 1
            trace = self.trace_directory / f"{ordinal:04d}"
            batch_cid = getattr(self.journal, "batch_active", None)
            batch_write = method.upper() == "POST" and batch_cid is not None
            if batch_write:
                if armed["cid"] != batch_cid:
                    raise ValueError("different prepared batch transport")
                # Exact request/signal/route intent already exists durably in
                # the immutable prepared record and its checkpoint arm. Save
                # actual transport timing together with the eventual ACK.
                prepared = self.journal.prepared_batch["records"][batch_cid]
            else:
                prepared = self.save_capture(
                    trace.with_suffix(".prepared.json"),
                    dict(
                        method=method,
                        url=url,
                        phase=self.current_phase,
                        at=self.clock().isoformat(),
                        monotonic=self.monotonic(),
                        credential_or_header_values_logged=False,
                        physical_send_not_yet_claimed=True,
                        capture_request=intent if method.upper() == "GET" else None,
                    ),
                )
            storage = getattr(self, "capture_storage", None)
            if (
                method.upper() == "GET"
                and storage is not None
                and storage.job.get("capture_partial_slot") is True
            ):
                from open_composer.intraday_runner.current_initialization_storage import (
                    require_partial_room,
                )

                require_partial_room(storage)
            # Trace/capacity work precedes the actual final guard. No I/O after
            # that guard until the bound Session.request call itself.
            self.check_trace_directory()
            if method.upper() == "GET":
                slots = getattr(self, "capture_slots", None)
                if slots is not None and slots.covers_get(intent["name"], prepared):
                    # Native authority/code/kernel/expiry remain fresh. This GET
                    # allocates no files: its reserved body/intent already count
                    # in other writers' full inventories. Large responses and
                    # unknown paths go through the ordinary full write guard.
                    slots.guard_get()
                    # Slot manifest/inode/extent checks can block. Receive the
                    # actual native and authority clocks AFTER that I/O, with
                    # no further filesystem preparation before the GET.
                    self.read_guard(preparation_only=True)
                else:
                    self.read_guard()
                if (
                    self.current_request != intent
                    or (kwargs.get("params", {}) or {}) != intent["params"]
                ):
                    raise ValueError("captured GET request changed after publication")
            else:
                self.gateway._check_guard(armed["request"], cancellation=method.upper() == "DELETE")
            kwargs["stream"] = True
            called_at, called_mono = self.clock(), self.monotonic()
            size = 0
            parts = []
            try:
                if batch_write:
                    self.journal.batch_transport[batch_cid].update(
                        physical_call_started=True,
                        method=method,
                        url=url,
                        client_call_started_at=called_at.isoformat(),
                        client_call_monotonic=called_mono,
                    )
                response = physical(method, url, **kwargs)
                for piece in response.iter_content(chunk_size=16384):
                    size += len(piece)
                    self.transport_bytes += len(piece)
                    parts.append(piece)
                    if size > 1572864 or self.transport_bytes > 6 * 1024 * 1024:
                        response.close()
                        raise ValueError("complete capture exceeds admitted bound; retain prefixes")
                response._content = b"".join(parts)
                response._content_consumed = True
            except Exception as exc:
                if (
                    method.upper() == "GET"
                    and storage is not None
                    and storage.job.get("capture_partial_slot") is True
                ):
                    from open_composer.intraday_runner.current_initialization_storage import (
                        retain_partial,
                    )

                    retain_partial(
                        storage,
                        dict(
                            usable=False,
                            method="GET",
                            request=intent,
                            prepared=prepared,
                            received_bytes=size,
                            received_prefix_base64=base64.b64encode(b"".join(parts)).decode(
                                "ascii"
                            ),
                            error_type=type(exc).__name__,
                            at=self.clock().isoformat(),
                            further_GET_refused=True,
                            credentials_or_headers_recorded=False,
                        ),
                    )
                if batch_write:
                    self.journal.batch_transport[batch_cid].update(
                        error_type=type(exc).__name__,
                        bytes_received=size,
                        at=self.clock().isoformat(),
                        acknowledgment_unknown=True,
                        received_prefix_base64=base64.b64encode(b"".join(parts)).decode("ascii"),
                    )
                else:
                    self.save_capture(
                        trace.with_suffix(".failure.json"),
                        dict(
                            error_type=type(exc).__name__,
                            method=method,
                            bytes_received=size,
                            client_call_started_at=called_at.isoformat(),
                            client_call_monotonic=called_mono,
                            at=self.clock().isoformat(),
                            acknowledgment_unknown=method.upper() != "GET",
                        ),
                    )
                raise
            response_record = dict(
                method=method,
                status=response.status_code,
                entity_bytes=size,
                client_call_started_at=called_at.isoformat(),
                client_call_monotonic=called_mono,
                response_observed_at=self.clock().isoformat(),
                response_monotonic=self.monotonic(),
                wire_send_arrival_and_exchange_clock="UNKNOWN",
            )
            if method.upper() == "GET":
                # capture.get durably seals metadata AND the decoded/sanitized
                # body together before using it. SDK parse/status failures seal
                # this metadata without claiming a usable body. POST/DELETE
                # acknowledgment publication remains unchanged below.
                self.current_response = dict(
                    request=intent, transport_prepared=prepared, response=response_record
                )
            elif batch_write:
                self.journal.batch_transport[batch_cid]["response"] = response_record
            else:
                self.save_capture(trace.with_suffix(".response.json"), response_record)
            return response

        self.gateway._original_request = bounded

    def initialize(self, scientific_package):
        self.read_guard()
        self.partition.register(self.task, self.authority)
        existing = self.store.load()
        if existing is not None:
            if existing["snapshot"]["evidence"].get("scientific_package_sha256") != _hash(
                scientific_package
            ):
                raise ValueError("initial scientific package changed across recovery")
            return
        dated = json.loads(bound_bytes(self.root, self.auth["initial_account_scope"]))
        if dated["account_hash"] != ACCOUNT:
            raise ValueError("dated scope identity")
        state = SourceReservations(source_module(self.root, "cash").CashState(cash=float(self.cap)))
        evidence = dict(
            account_initial_cash=str(dated["broker_reported_cash_equity_nonmarginable_USD"]),
            allocated_capital=str(self.cap),
            actions_current=True,
            actions_observation_day=DAY.isoformat(),
            scientific_package_sha256=_hash(scientific_package),
            unresolved_actual_liabilities=False,
            risk=dict(
                initial_capital=str(self.cap),
                high_water=str(self.cap),
                halted=False,
                killed=False,
                day=None,
                day_open_nav=None,
            ),
            initial_allocation_is_not_broker_cash_certificate=True,
        )
        self.store.commit(snapshot(state, {}, {}, evidence=evidence), expected_head_sha256=None)

    def observe(self, directory, *, risk=True, opening=False):
        self.connect()
        raw = capture(self, directory, clock=self.clock, monotonic=self.monotonic)
        current = self.store.load()
        obs = receive_observation(
            raw["observation"],
            now=self.clock(),
            now_monotonic=self.monotonic(),
            account_hash=ACCOUNT,
            checkpoint_hash=_hash(current),
        )
        if risk:
            require_broker_open(obs, self.clock())
            state, fills, fees, evidence = restore(self.root, current["snapshot"])
            evidence["risk"] = risk_transition(
                evidence["risk"],
                obs,
                now=self.clock(),
                opening=opening,
                capital=self.cap,
                initializing=opening
                and self.auth.get("session_id") == "SIX-CURRENT-SESSION-20261020",
            )
            updated = snapshot(state, fills, fees, evidence=evidence)
            if updated != current["snapshot"]:
                current = self.store.commit(updated, expected_head_sha256=_hash(current))
            obs["checkpoint_hash"] = _hash(current)
        self.observation = obs
        return raw

    def receive_science(self):
        self.read_guard()
        from open_composer.intraday_runner.current_initialization_episode import receive

        result = receive(self.root, self.auth, clock=self.clock)
        self.current_scientific_package = result
        return result

    def decide(self, output):
        self.require_phase("decision")
        package = getattr(self, "current_scientific_package", None)
        if package is None:
            package = self.receive_science()
        self.initialize(package)
        self.required_symbols = {
            s
            for s, w in zip(
                package["forecast"]["symbols"], package["forecast"]["weights"], strict=True
            )
            if w
        }
        raw = self.observe(output / "account", risk=False)
        if raw["positions"] or raw["orders"] or raw["activities"]:
            raise ValueError("initialization requires genuinely empty own sleeve")
        forecast = package["forecast"]
        from numpy import array, zeros

        symbols = forecast["symbols"]
        weights = [number(v) for v in forecast["weights"]]
        tolerance = Decimal(".000000000001") if self.task == LSTM else Decimal(0)
        max_names = 10 if self.task == LSTM else 5
        if (
            len(symbols) != len(set(symbols))
            or len(weights) != len(symbols)
            or any(v > Decimal(".2") + tolerance for v in weights)
            or sum(weights) > 1 + tolerance
            or sum(v > 0 for v in weights) > max_names
        ):
            raise ValueError("current fixed per-name/K/gross policy differs")
        prices = array([forecast["reference_marks"].get(s) or float("nan") for s in symbols])
        qty, budget = source_module(self.root, "cash").target_quantities(
            float(self.cap), zeros(len(symbols)), prices, forecast["weights"], 0.001, True
        )
        requests = []
        for s, q, weight in zip(symbols, qty, forecast["weights"], strict=True):
            if weight and q:
                requests.append(
                    dict(
                        symbol=s,
                        max_quantity=int(q),
                        reference_price=forecast["reference_marks"][s],
                        limit_price=str(limit_price(forecast["reference_marks"][s])),
                        weight=weight,
                    )
                )
        result = dict(
            task_id=self.task,
            account_hash=ACCOUNT,
            package=package,
            requests=requests,
            actual_evaluated_at=self.clock().isoformat(),
            model_reason=forecast["decision_reason"],
            status="evaluated_current_decision" if requests else "evaluated_no_trade",
            planning_fee_root=dict(budget),
            planning_buffer_not_actual_fee=True,
            no_order_calls=True,
            observation=bind(output / "account/capture.json"),
        )
        self.require_phase("decision")
        signal = self.save_capture(self.directory / "initial-decision.json", result)
        return dict(signal=signal, status=result["status"], broker_writes=0)

    def order_guard(self, request, *, cancellation=False):
        if (
            self.auth.get("session_id") == "SIX-CURRENT-SESSION-20261020"
            and self.capture_storage is not None
        ):
            # This predicate reads current state and allocates nothing. All
            # actual revision/head/journal/transport publications retain their
            # separate full allocation guards. No financial observation or
            # authority result is cached across calls.
            self.capture_storage.physical()
            self.read_guard(preparation_only=True)
        else:
            self.read_guard()
        _require_kill_switch_clear(self.root)
        if os.path.lexists(self.directory / "STOP"):
            raise ValueError("local owned sleeve stop marker is present")
        current = self.store.load()
        obs = receive_observation(
            self.observation,
            now=self.clock(),
            now_monotonic=self.monotonic(),
            account_hash=ACCOUNT,
            checkpoint_hash=_hash(current),
            purpose="owned_cancel"
            if cancellation
            else ("owned_exit" if request.get("cleanup") is True else "new_risk"),
        )
        if cancellation:
            self.cancel_window(request)
        require_broker_open(obs, self.clock())
        state, _, _, evidence = restore(self.root, current["snapshot"])
        risk = evidence["risk"]
        if type(risk.get("halted")) is not bool or type(risk.get("killed")) is not bool:
            raise ValueError("unknown risk")
        if not cancellation:
            asset = obs.get("assets", {}).get(request["symbol"], {})
            if asset.get("status") != "active" or asset.get("tradable") is not True:
                raise ValueError("unknown/inactive/nontradable asset")
        if not cancellation and request["side"] == "buy" and (risk["halted"] or risk["killed"]):
            raise ValueError("risk latch")
        cid = request["client_order_id"]
        if evidence.get("dispatch_intents", {}).get(cid, {}).get("attempted") is not True:
            raise ValueError("durable dispatch witness absent")
        if request.get("cleanup") is True and not cancellation:
            if request.get("killed") is not risk["killed"]:
                raise ValueError("exit trigger differs from durable latch")
            holding = next((h for h in obs["holdings"] if h["symbol"] == request["symbol"]), None)
            pending = state.pending[cid]
            other_locks = sum(
                r["quantity"] - r["filled"]
                for k, r in state.pending.items()
                if k != cid and r["side"] == "sell" and r["symbol"] == request["symbol"]
            )
            if (
                holding is None
                or number(request["reference_price"]) != number(holding["current_price"])
                or request["qty"] > holding["quantity"] - other_locks
                or pending["quantity"] != request["qty"]
                or pending["filled"] != 0
            ):
                raise ValueError("exit exceeds current confirmed own free shares/mark")
        if request["side"] == "buy" and not cancellation:
            self.partition.guard_new_risk(obs, self.task)
            decision = json.loads((self.directory / "initial-decision.json").read_text())
            selected = {r["symbol"]: r for r in decision["requests"]}.get(request["symbol"])
            if (
                selected is None
                or request["qty"] > selected["max_quantity"]
                or number(request["limit_price"]) != number(selected["limit_price"])
                or request["reference_price"] != selected["reference_price"]
            ):
                raise ValueError("order differs from logged actual model decision")
            pending = state.pending[cid]
            if pending["quantity"] != request["qty"] or pending["filled"] != 0:
                raise ValueError("reservation changed")
            if (
                number(obs["marked_value"])
                + sum(
                    number(r["quantity"] - r["filled"]) * number(r["limit_price"])
                    for r in state.pending.values()
                    if r["side"] == "buy"
                )
                > self.cap
            ):
                raise ValueError("gross cap")
            if number(state.cash_reserved()) > number(obs["unborrowed_available"]):
                raise ValueError("actual unborrowed funds insufficient")

    def buy(self, output):
        if self.auth.get("session_id") != "SIX-CURRENT-SESSION-20261020":
            return self._buy_legacy(output)
        with self.journal.initial_batch_locked():
            return self._buy_prepared(output)

    def _buy_prepared(self, output):
        self.require_phase("buy")
        if self.capture_storage is None:
            raise ValueError("prepared batch requires exact native storage/job")
        job = self.capture_storage.job
        owner = dict(
            invocation_id=job["invocation_id"], output=job["output"], authority=self.authority
        )
        if job["authority"] != self.authority or job["task_id"] != self.task:
            raise ValueError("batch native/authority mismatch")
        self.read_guard()
        signal = bind(self.directory / "initial-decision.json")
        decision = json.loads(bound_bytes(self.root, signal))
        self.required_symbols = {r["symbol"] for r in decision["requests"]}
        before = self.store.load()
        state, fills, fees, evidence = restore(self.root, before["snapshot"])
        if state.consumed_ids or state.pending or state.cashbook.lots:
            raise ValueError("initial batch already consumed or nonempty")
        requests = []
        for row in decision["requests"]:
            cid = f"{self.namespace}-{DAY:%m%d}-buy-{row['symbol']}"
            fee = float(number(row["max_quantity"]) * number(row["limit_price"]) * Decimal(".001"))
            reservation = state.reserve_buy(
                cid,
                row["symbol"],
                row["max_quantity"],
                float(row["limit_price"]),
                fee,
                DAY.isoformat(),
                "2026-10-20",
            )
            requests.append(
                dict(
                    client_order_id=cid,
                    symbol=row["symbol"],
                    side="buy",
                    qty=row["max_quantity"],
                    type="limit",
                    time_in_force="day",
                    limit_price=float(row["limit_price"]),
                    execution_day=DAY.isoformat(),
                    reference_day="2026-10-19",
                    reference_price=row["reference_price"],
                    reference_valid=True,
                    reservation=reservation,
                    cleanup=False,
                    killed=False,
                )
            )
        if not requests:
            self.observe(output / "account")
            return dict(status="evaluated_no_trade", requests=[])
        self.ensure_directory(self.journal.directory)
        js = self.journal.directory.stat()
        intents = {
            r["client_order_id"]: dict(
                attempted=True,
                attempt_semantics="durable_batch_arm_not_physical_send",
                reservation_sha256=_hash(r["reservation"]),
                journal_root=str(self.journal.directory),
                journal_identity=[js.st_dev, js.st_ino],
            )
            for r in requests
        }
        planned = snapshot(state, fills, fees, evidence=evidence)
        self.journal.batch_checkpoint = lambda: self.store.load()
        arm = self.journal.prepare_initial_batch(
            requests,
            snapshot={**planned, "account_hash": ACCOUNT},
            signal=signal,
            owner=owner,
            clock=self.clock,
        )
        # Only preparation is complete above. The actual book is still unchanged
        # and unreserved while this FULL fresh authenticated capture runs.
        self.observe(output / "account")
        current = self.store.load()
        old, now = copy.deepcopy(before["snapshot"]), copy.deepcopy(current["snapshot"])
        old["evidence"].pop("risk", None)
        now["evidence"].pop("risk", None)
        if old != now:
            raise ValueError("financial state changed during batch preparation/capture")
        evidence = copy.deepcopy(current["snapshot"]["evidence"])
        if evidence["risk"]["halted"] or evidence["risk"]["killed"]:
            return dict(status="risk_halt", requests=[])
        evidence["dispatch_intents"] = intents
        evidence["initial_batch_arm"] = arm
        # One complete atomic reservation/consumption checkpoint. There is no
        # resend after this boundary, including a crash before the first POST.
        current = self.store.commit(
            snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(current)
        )
        self.observation["checkpoint_hash"] = _hash(current)
        outputs = []
        for req in requests:
            outputs.append(
                self.journal.dispatch_prepared_once(
                    req,
                    signal=signal,
                    owner=owner,
                    authorized_at=aware(self.auth["authorized_at"]),
                    expires_at=aware(self.auth["expires_at"]),
                    submit=self.gateway.submit,
                    revalidate=self.order_guard,
                    clock=self.clock,
                )
            )
        return dict(status="actual_attempts_reconciliation_required", orders=outputs)

    def _buy_legacy(self, output):
        self.require_phase("buy")
        signal = bind(self.directory / "initial-decision.json")
        decision = json.loads(bound_bytes(self.root, signal))
        self.required_symbols = {r["symbol"] for r in decision["requests"]}
        self.observe(output / "account")
        current = self.store.load()
        state, fills, fees, evidence = restore(self.root, current["snapshot"])
        if state.consumed_ids or state.pending or state.cashbook.lots:
            raise ValueError("initial batch already consumed or nonempty")
        if evidence["risk"]["halted"] or evidence["risk"]["killed"]:
            return dict(status="risk_halt", requests=[])
        requests = []
        for row in decision["requests"]:
            cid = f"{self.namespace}-{DAY:%m%d}-buy-{row['symbol']}"
            fee = float(number(row["max_quantity"]) * number(row["limit_price"]) * Decimal(".001"))
            reservation = state.reserve_buy(
                cid,
                row["symbol"],
                row["max_quantity"],
                float(row["limit_price"]),
                fee,
                DAY.isoformat(),
                "2026-10-20",
            )
            requests.append(
                dict(
                    client_order_id=cid,
                    symbol=row["symbol"],
                    side="buy",
                    qty=row["max_quantity"],
                    type="limit",
                    time_in_force="day",
                    limit_price=float(row["limit_price"]),
                    execution_day=DAY.isoformat(),
                    reference_day="2026-10-19",
                    reference_price=row["reference_price"],
                    reference_valid=True,
                    reservation=reservation,
                    cleanup=False,
                    killed=False,
                )
            )
        self.ensure_directory(self.journal.directory)
        js = self.journal.directory.stat()
        evidence["dispatch_intents"] = {
            r["client_order_id"]: dict(
                attempted=False,
                reservation_sha256=_hash(r["reservation"]),
                journal_root=str(self.journal.directory),
                journal_identity=[js.st_dev, js.st_ino],
            )
            for r in requests
        }
        current = self.store.commit(
            snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(current)
        )
        self.observation["checkpoint_hash"] = _hash(current)
        outputs = []
        for req in requests:
            evidence["dispatch_intents"][req["client_order_id"]]["attempted"] = True
            current = self.store.commit(
                snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(current)
            )
            self.observation["checkpoint_hash"] = _hash(current)
            value = current["snapshot"]
            outputs.append(
                self.journal.dispatch_once(
                    req,
                    reservation_snapshot={**value, "account_hash": ACCOUNT},
                    signal_binding=signal,
                    execution_day=DAY,
                    authorized_at=aware(self.auth["authorized_at"]),
                    expires_at=aware(self.auth["expires_at"]),
                    submit=self.gateway.submit,
                    revalidate=self.order_guard,
                    clock=self.clock,
                )
            )
        return dict(status="actual_attempts_reconciliation_required", orders=outputs)

    def reconcile(self, output):
        """Retain all raw capture and apply actual FILL deltas before NAV acceptance."""
        self.connect()
        raw = capture(self, output / "account", clock=self.clock, monotonic=self.monotonic)
        current = self.store.load()
        state, fills, fees, evidence = restore(self.root, current["snapshot"])
        orders = raw["orders"]
        if raw.get("known_guard_refusals"):
            evidence.setdefault("known_pre_submit_refusals", {}).update(raw["known_guard_refusals"])
            evidence["initial_dispatch_blocked"] = True
        for cid, order in orders.items():
            journal = self.journal.receive(cid)
            classify_own_order(journal["request"], order)
            journal["observations"].append(order)
            self.write_text(self.journal._path(cid), json.dumps(journal, sort_keys=True) + "\n")
        body = self.save_capture(output / "activities.json", raw["activities"])
        receipt = self.save_capture(
            output / "activities-receipt.json",
            dict(
                method="GET",
                endpoint_kind="account_activities",
                status=200,
                account_hash=ACCOUNT,
                body=body,
                received_at=max(
                    v for k, v in raw["response_clocks"].items() if k.startswith("activities-")
                ),
                source_pages={
                    k: v for k, v in raw["bodies"].items() if k.startswith("activities-")
                },
                capture_basis=(
                    "Own-sleeve projection of SDK-decoded pages; "
                    "all original pages bound, not wire bytes"
                ),
            ),
        )
        order_map = {o["id"]: cid for cid, o in orders.items()}
        for i, item in enumerate(raw["activities"]):
            if item.get("activity_type") != "FILL":
                evidence["unresolved_actual_liabilities"] = True
                continue
            cid = order_map.get(item.get("order_id"))
            if cid is None:
                raise ValueError("unowned execution activity")
            state, fills, _ = apply_bound_fill(
                self.root,
                state,
                fills,
                receipt_binding=receipt,
                ordinal=i,
                journal_record=self.journal.receive(cid),
                expected_account_hash=ACCOUNT,
                observed_now=self.clock(),
            )
        for cid, order in orders.items():
            if (
                cid in state.pending
                and state.pending[cid]["side"] != "liability_hold"
                and classify_own_order(self.journal.receive(cid)["request"], order)[
                    "terminal_observed"
                ]
            ):
                state, evidence = retain_terminal_liability(
                    state,
                    evidence,
                    journal=self.journal.receive(cid),
                    observed_order=order,
                    capture_binding=body,
                )
        evidence["actual_fees_reconciled"] = not fills and not raw["activities"] and not orders
        self.store.commit(
            snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(current)
        )
        from open_composer.book_paper.cost_ledgers import profit_ledgers

        initial_scope = json.loads(bound_bytes(self.root, self.auth["initial_account_scope"]))
        ledgers = profit_ledgers(
            float(number(raw["account"]["equity"])),
            float(number(initial_scope["broker_reported_cash_equity_nonmarginable_USD"])),
            dict(impact=0.0, fees=0.0, borrow=0.0, total=0.0),
            holdings_valuation_complete=False,
        )
        # No friction model is calibrated for this new DAY-limit application.
        # Keep actual equity change, unknown flow/inclusion and no second spread.
        ledgers.pop("legacy_full_shadow")
        ledgers["current_modeled_cost_scenario_defined"] = False
        ledgers["historical_PnL_transferred_to_this_trial"] = False
        ledgers["account_level_only_not_sleeve_attribution"] = True
        # Reconcile the captured aggregate position rows to the newly received
        # fills without issuing another GET or representing old marks as fresh.
        post_view = self.partition.account_view(
            self.partition.books(),
            self.task,
            raw["aggregate_positions"],
            raw["aggregate_orders"],
            raw["aggregate_activities"],
        )
        own_estimate = (
            number(state.cashbook.cash)
            + sum((number(s["amount"]) for s in state.cashbook.sales), Decimal(0))
            - sum((number(p["amount"]) for p in state.cashbook.purchases), Decimal(0))
            + sum((number(p["market_value"]) for p in post_view["holdings"]), Decimal(0))
        )
        scoped_accounting = dict(
            sleeve_id=self.task,
            initial_sleeve_capital=str(number(evidence["risk"]["initial_capital"])),
            net_external_allocation_flows=str(
                number(evidence["risk"].get("net_allocation_flows", 0))
            ),
            funded_sleeve_capital=str(self.cap),
            capital_flows_are_not_profit=True,
            marked_virtual_book_NAV_estimate=str(own_estimate),
            virtual_book_change_estimate=str(number(own_estimate, nonnegative=False) - self.cap),
            captured_aggregate_quantities_match_complete_virtual_books=post_view["units_complete"],
            saved_mark_capture=bind(output / "account/capture.json"),
            marks_are_saved_capture_not_new_observation=True,
            certified_sleeve_PnL=None,
            incremental_only_net=None,
            reason=(
                "Complete current marked book, fees/rights/flows and settlement must reconcile; "
                "broker account equity is not either sleeve PnL."
            ),
            historical_simulation_net_not_current_broker_performance=True,
            no_modeled_spread_or_planning_buffer_debited=True,
        )
        return dict(
            status="actual_receipts_received_valuation_may_remain_incomplete",
            fill_ids=sorted(fills),
            cost_ledgers=ledgers,
            sleeve_accounting=scoped_accounting,
            fees_certified=evidence["actual_fees_reconciled"],
            raw=bind(output / "account/capture.json"),
            no_order_calls=True,
        )

    def cancel_window(self, request):
        # Cancellation of the original BUY keeps its immutable request/CID.
        # Only an exit invocation can use the durable kill or fixed winddown.
        current = self.store.load()
        _, _, _, evidence = restore(self.root, current["snapshot"])
        killed = evidence["risk"]["killed"]
        phase = "exit" if self.current_phase == "exit" else "cancel"
        require_phase(
            self.clock(),
            phase,
            self.auth["authorized_at"],
            self.auth["expires_at"],
            killed=killed,
            prospective=self.auth.get("session_id") == "SIX-CURRENT-SESSION-20261020",
        )

    def cancel_observed(self, raw):
        self.observation = raw["observation"]
        rows = []
        for cid, observed in raw["orders"].items():
            journal = self.journal.receive(cid)
            classified = classify_own_order(journal["request"], observed)
            if not classified["cancel_eligible"] or "cancel_attempt" in journal:
                rows.append(
                    dict(
                        client_order_id=cid,
                        status=classified["status"],
                        cancel_attempted=False,
                        existing_attempt="cancel_attempt" in journal,
                    )
                )
                continue
            rows.append(
                self.journal.cancel_own_remainder_once(
                    cid,
                    authorized_at=aware(self.auth["authorized_at"]),
                    expires_at=aware(self.auth["expires_at"]),
                    cancel=lambda bid, cid=cid: self.gateway.cancel(cid, bid),
                    revalidate=lambda row: self.order_guard(row["request"], cancellation=True),
                    clock=self.clock,
                )
            )
        return rows

    def cancel(self, output):
        self.require_phase("cancel")
        self.reconcile(output / "reconcile")
        raw = capture(self, output / "fresh-orders", clock=self.clock, monotonic=self.monotonic)
        rows = self.cancel_observed(raw)
        return dict(cancel_observations=rows, cancellation_response_is_not_terminal=True)

    def abandon(self, cid):
        self.read_guard()
        self.ensure_directory(self.journal.directory)
        self.guard_write(self.journal.directory / ".dispatch.lock", 0, atomic=False)
        with (self.journal.directory / ".dispatch.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            current = self.store.load()
            state, fills, fees, evidence = restore(self.root, current["snapshot"])
            state, evidence = abandon_never_attempted(
                state,
                fills,
                fees,
                evidence,
                cid=cid,
                journal=self.journal,
                observed_at=self.clock().isoformat(),
            )
            return self.store.commit(
                snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(current)
            )

    def closeout(self, output):
        self.read_guard()
        _require_kill_switch_clear(self.root)
        if os.path.lexists(self.directory / "STOP"):
            raise ValueError("local owned sleeve stop marker is present")
        _, _, _, initial_evidence = restore(self.root, self.store.load()["snapshot"])
        require_phase(
            self.clock(),
            "exit",
            self.auth["authorized_at"],
            self.auth["expires_at"],
            killed=initial_evidence["risk"]["killed"],
            prospective=self.auth.get("session_id") == "SIX-CURRENT-SESSION-20261020",
        )
        self.reconcile(output / "before-cancel")
        raw = capture(self, output / "cancel-orders", clock=self.clock, monotonic=self.monotonic)
        cancellations = self.cancel_observed(raw)
        # One bounded reception, not a cancel-confirmation polling loop. Apply
        # racing fills and terminal quantities before deciding free exit units.
        self.reconcile(output / "after-cancel")
        raw = capture(self, output / "account", clock=self.clock, monotonic=self.monotonic)
        current = self.store.load()
        self.observation = receive_observation(
            raw["observation"],
            now=self.clock(),
            now_monotonic=self.monotonic(),
            account_hash=ACCOUNT,
            checkpoint_hash=_hash(current),
            purpose="owned_exit",
        )
        state, fills, fees, evidence = restore(self.root, current["snapshot"])
        unresolved = [
            cid for cid, pending in state.pending.items() if pending["side"] != "liability_hold"
        ]
        if unresolved or any(
            not classify_own_order(self.journal.receive(cid)["request"], order)["terminal_observed"]
            for cid, order in raw["orders"].items()
        ):
            return dict(
                status="controlled_exit_blocked_unresolved_orders",
                unresolved=unresolved,
                cancel_observations=cancellations,
                orders=[],
                flat_certified=False,
                holds_released=False,
            )
        killed = evidence["risk"]["killed"]
        require_phase(
            self.clock(),
            "exit",
            self.auth["authorized_at"],
            self.auth["expires_at"],
            killed=killed,
            prospective=self.auth.get("session_id") == "SIX-CURRENT-SESSION-20261020",
        )
        day = self.clock().astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).date()
        self.ensure_directory(self.journal.directory)
        js = self.journal.directory.stat()
        rows = []
        for held in self.observation["holdings"]:
            symbol = held["symbol"]
            locked = sum(
                p["quantity"] - p["filled"]
                for p in state.pending.values()
                if p["symbol"] == symbol and p["side"] == "sell"
            )
            funded = sum(
                lot["quantity"]
                for lot in state.cashbook.lots.get(symbol, [])
                if lot["funded"] <= day.isoformat()
            )
            qty = int(min(number(held["quantity"]), number(funded) - number(locked)))
            if qty <= 0:
                continue
            cid = f"{self.namespace}-{day:%m%d}-exit-{symbol}"
            price = float(limit_price(held["current_price"], exit_order=True))
            cal = source_module(self.root, "cash")
            due = cal.cash_due_date(day.isoformat(), cal.settlement_calendar())
            reservation = state.reserve_sell(
                cid, symbol, qty, price, day.isoformat(), due, fee_buffer_rate=0.001
            )
            req = dict(
                client_order_id=cid,
                symbol=symbol,
                side="sell",
                qty=qty,
                type="limit",
                time_in_force="day",
                limit_price=price,
                reference_price=held["current_price"],
                reference_valid=True,
                execution_day=day.isoformat(),
                cleanup=True,
                own_exit_allowed=True,
                killed=killed,
                reservation=reservation,
            )
            evidence.setdefault("dispatch_intents", {})[cid] = dict(
                attempted=True,
                reservation_sha256=_hash(reservation),
                journal_root=str(self.journal.directory),
                journal_identity=[js.st_dev, js.st_ino],
            )
            current = self.store.commit(
                snapshot(state, fills, fees, evidence=evidence), expected_head_sha256=_hash(current)
            )
            self.observation["checkpoint_hash"] = _hash(current)
            signal = self.save_capture(
                output / f"{symbol}.exit-signal.json",
                dict(request=req, observation=self.observation),
            )
            rows.append(
                self.journal.dispatch_once(
                    req,
                    reservation_snapshot={**current["snapshot"], "account_hash": ACCOUNT},
                    signal_binding=signal,
                    execution_day=day,
                    authorized_at=aware(self.auth["authorized_at"]),
                    expires_at=aware(self.auth["expires_at"]),
                    submit=self.gateway.submit,
                    revalidate=self.order_guard,
                    clock=self.clock,
                )
            )
        return dict(
            status="controlled_exit_attempts_require_reconciliation",
            orders=rows,
            flat_certified=False,
        )
