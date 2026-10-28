"""Finite current-job storage guards and preallocated terminal/log slots.

The complete BASE/H5 aggregate is checked before allocating; fixed slots never
extend after admission. Torn terminal JSON is failure evidence, not completion.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from open_composer.intraday_runner.source_activity_reception import save
from open_composer.intraday_runner.source_dispatch_journal import (
    _ensure_durable_directory,
    _sync_directory,
)
from open_composer.intraday_runner.source_method_bindings import bound_bytes


def capacity(root, job):
    receipt = json.loads(bound_bytes(root, job["capacity_receipt"]))
    outside_uncredited_reserve = 0
    # The exact independently accepted receipt is supplied by native acceptance;
    # never reinterpret the complete upstream forecast as this route footprint.
    if (
        type(job["whole_route_bytes"]) is not int
        or job["whole_route_bytes"] <= 0
        or type(job["protected_normal_bytes"]) is not int
        or job["protected_normal_bytes"] < 10918819017
        or job["terminal_bytes"] != 65536
    ):
        raise ValueError("storage scope drift")
    if (
        receipt.get("admitted") is not True
        or receipt.get("capacity_only") is not True
        or receipt.get("task_id")
        not in {
            "BASE-H5-TWO-LEARNED-PAPER-VALIDATION-20261019",
            "BASE-H5-LSTM-THREE-LEARNED-PAPER-VALIDATION-20261019",
            "SIX-CANDIDATE-PAPER-VALIDATION-20261019",
            "CURRENT-PAPER-CONTINUITY-AND-INITIALIZATION-20261020",
            "SIX-PAPER-CURRENT-SESSION-COMPLETION-20261020",
        }
        or type(receipt.get("accepted_whole_route_peak_bytes")) is not int
        or receipt.get("accepted_whole_route_peak_bytes") != job["whole_route_bytes"]
    ):
        raise ValueError("storage scope drift: actual capacity receipt does not admit this route")
    full_physical = receipt["task_id"] == "SIX-PAPER-CURRENT-SESSION-COMPLETION-20261020"
    if receipt["task_id"] in {
        "CURRENT-PAPER-CONTINUITY-AND-INITIALIZATION-20261020",
        "SIX-PAPER-CURRENT-SESSION-COMPLETION-20261020",
    }:
        complete_versions = {
            268435456: (
                "9a140d061cbb7347a93f8bbe5f3596f31cc36e9a31d3856987cde50afca48b88",
                "82fe95761b226b0efe5239c82eda715670d0d7c6d4d61615185251bd65f5017e",
                10919240084,
            ),
            335544320: (
                "49f69733d03f50408664971425219370f9c4a1e02d38c6f521d0ed04324842cb",
                "6cb034f08199f73a29e57d19ee16303a353ce7c9d1c8fbdffb3bc4ba8c4e9b66",
                10919249663,
            ),
            402653184: (
                "46ae769194f5131e5f299031e4077cbd9e26210c48c2d381c7aa775ec61efe01",
                "f91c5438919c7fe08e62da5d9cfde345d5f2bffca2e45462087a1b0bbc15c3bc",
                10919282270,
            ),
        }
        version = complete_versions.get(job["whole_route_bytes"]) if full_physical else None
        if full_physical and version is None:
            raise ValueError("unknown complete-session capacity version")
        expected_receipt = (
            version[0]
            if full_physical
            else ("cc8d60c8f3b39fabcfd1c6987baa025d7810a6df345222dbf9c8325243fbbede")
        )
        if job["capacity_receipt"].get("sha256") != expected_receipt:
            raise ValueError("unreceived current-day capacity revision")
        proposal_binding = receipt["request_bindings"][
            "actual_six_route_current_session_whole_route_proposal"
            if full_physical
            else "actual_f9_current_day_whole_route_proposal"
        ]
        if job["whole_route_bytes"] == 402653184:
            # The final384 receipt has its own real schema; historical320/352
            # references are provenance, never operative allowance or credit.
            bindings = receipt["request_bindings"]
            bound_bytes(root, bindings["postpublication_normal_context"])
            normal_binding = bindings["postpublication_complete_normal"]
            normal_floor = receipt["complete_paper_forecast"]["required_available_bytes"]
            physical = receipt["current_physical_fact"]
            other_remaining = physical["Astra_once_bytes"]
            terminal_once = physical["terminal_once_bytes"]
            outside_once = receipt["whole_route_accounting"][
                "outside_uncredited_future_reserve_inside_whole_once_bytes"
            ]
            scientific = receipt["accepted_scientific_component"]
            bound_bytes(root, scientific["proposal"])
            if (
                scientific["proposal"] != bindings["actual_complete_scientific_completion_proposal"]
                or scientific["proposal"]["sha256"]
                != "4b7a2180ff708ef0306a967772640cacd675e94e2b7606c506b739f95dc783c8"
                or scientific["accepted_whole_route_peak_bytes"] != 20971520
                or receipt["guard_contract"]["scientific_peak_bytes"] != 20971520
                or scientific["outside_science1MiB_once_inside_component20_and_aggregate3"]
                is not True
                or receipt["guard_contract"]["aggregate_outside3MiB_inside_aggregate_once"]
                is not True
            ):
                raise ValueError("unreceived component inside aggregate capacity")
        else:
            concurrent = receipt["concurrent_protected_commitments"]
            normal_binding = concurrent["complete_normal"]["receipt"]
            normal_floor = concurrent["complete_normal"]["required_available_bytes"]
            other_remaining = concurrent["single_synthesis"][
                "current_finite_remaining_future_peak_bytes"
            ]
            terminal_once = concurrent["terminal_once_bytes"]
            outside_once = receipt["guard_contract"].get(
                "outside_uncredited_reserve_inside_whole_once_bytes", 3 * 1024**2
            )
        bound_bytes(root, normal_binding)
        normal = json.loads(bound_bytes(root, job["current_normal_forecast"]))
        cash = json.loads(bound_bytes(root, job["concurrent_CASH_capacity"]))
        sip = json.loads(bound_bytes(root, job["concurrent_SIP_capacity"]))
        if (
            job["concurrent_CASH_capacity"].get("sha256")
            != "294b41194d6f8dacac8123182fbd44637e048770f1827f8580e5aed637cbfdcf"
            or job["concurrent_SIP_capacity"].get("sha256")
            != "190b64adcfe83f94a2cf8a42d4a5bf5efc7b438659b621a2552459572290ccb0"
            or cash.get("admitted") is not True
            or sip.get("admitted") is not True
            or cash.get("capacity_only") is not True
            or sip.get("capacity_only") is not True
            or cash.get("accepted_whole_route_peak_bytes") != 12582912
            or sip.get("accepted_incremental_stage_peak_bytes") != 1073741824
            or other_remaining != 12288
            or type(normal.get("required_available_bytes")) is not int
            or normal["required_available_bytes"] != job["protected_normal_bytes"]
            or normal.get("spill_and_service_already_included_once") is not True
            or len(normal.get("enabled_upstream_tables", [])) != 11
            or len(normal.get("live_stages", [])) != 7
            or terminal_once != job["terminal_bytes"]
            or job["owned_roots"] != receipt["guard_contract"]["required_roots"]
        ):
            raise ValueError("current concurrent obligations differ")
        # Conservative FULL concurrent maxima: never credit SIP growth in both
        # its own increment and this paper-root inventory, or reuse CASH credit.
        other_remaining += 12582912 + 1073741824
        # The bound proposal includes science's outside native/index1MiB and
        # common code/worktree/git growth inside2MiB. These are NOT measured
        # allocation credit. Keep their full maxima unavailable for root writes,
        # while still protecting them as future physical demand below.
        outside_uncredited_reserve = 3 * 1024**2
        if full_physical and (
            proposal_binding.get("sha256") != version[1]
            or job["protected_normal_bytes"] < version[2]
            or job["protected_normal_bytes"] < normal_floor
            or outside_once != outside_uncredited_reserve
        ):
            raise ValueError("unreceived complete-six accounting contract")
    elif receipt["task_id"] == "SIX-CANDIDATE-PAPER-VALIDATION-20261019":
        proposal_binding = receipt["request_bindings"]["actual_six_candidate_whole_route_proposal"]
        other_remaining = receipt["concurrent_protected_commitments"]["single_synthesis"][
            "current_finite_remaining_future_peak_bytes"
        ]
        if type(other_remaining) is not int or other_remaining < 0:
            raise ValueError("unknown other admitted remaining storage obligation")
    elif receipt["task_id"] == "BASE-H5-LSTM-THREE-LEARNED-PAPER-VALIDATION-20261019":
        proposal_binding = receipt["request_bindings"]["actual_conditional_three_trial_proposal"]
        other_remaining = receipt["concurrent_protected_commitments"]["single_synthesis"][
            "current_finite_remaining_future_peak_bytes"
        ]
        if type(other_remaining) is not int or other_remaining < 0:
            raise ValueError("unknown other admitted remaining storage obligation")
    elif "proposal" in receipt:  # Original independently received22MiB schema.
        proposal_binding = receipt["proposal"]
        other_remaining = 0
    else:  # Actual replacement33MiB receipt, not a rewritten historical receipt.
        proposal_binding = receipt["request_bindings"]["actual_remaining_two_session_proposal"]
        other_remaining = receipt["concurrent_protected_commitments"]["single_synthesis"][
            "current_finite_remaining_future_peak_bytes"
        ]
        if type(other_remaining) is not int or other_remaining < 0:
            raise ValueError("unknown other admitted remaining storage obligation")
    proposal = json.loads(bound_bytes(root, proposal_binding))
    if (
        receipt["task_id"]
        not in {
            "CURRENT-PAPER-CONTINUITY-AND-INITIALIZATION-20261020",
            "SIX-PAPER-CURRENT-SESSION-COMPLETION-20261020",
        }
        and job["protected_normal_bytes"] != 10918819017
    ):
        raise ValueError("historical normal footprint must remain exact")
    if (
        type(proposal.get("total_whole_route_peak_bytes")) is not int
        or proposal["total_whole_route_peak_bytes"] != job["whole_route_bytes"]
    ):
        raise ValueError("native peak differs from the bound admitted proposal")
    roots_key = "current_root_allocation"
    if job["owned_roots"] != [r["root"] for r in proposal[roots_key]]:
        raise ValueError("capacity roots differ from the single whole-route proposal")
    allocated = allocated_bytes(job["owned_roots"])
    if allocated + outside_uncredited_reserve > job["whole_route_bytes"]:
        raise ValueError("whole-route allocation overflow")
    physical_remaining = job["whole_route_bytes"] - allocated
    remaining = physical_remaining - outside_uncredited_reserve
    disk = os.statvfs(root)
    free = disk.f_bavail * disk.f_frsize
    if free < (
        job["protected_normal_bytes"]
        + job["terminal_bytes"]
        + (job["whole_route_bytes"] if full_physical else physical_remaining)
        + other_remaining
    ):
        raise ValueError("protected normal refresh or current route unsupported")
    return dict(
        free_bytes=free,
        owned_allocated=allocated,
        remaining_current=remaining,
        remaining_physical_demand=physical_remaining,
        outside_uncredited_reserve=outside_uncredited_reserve,
        full_uncredited_physical_guard=full_physical,
    )


def allocated_bytes(roots):
    """Fresh full inventory; same unique directory/exclusive-file allocation.

    DirEntry/fstat avoids constructing a Path for every file and the duplicated
    traversal metadata in os.walk. No previous allocation or file stat is reused.
    Directory descriptors do not follow a replaced leaf symlink. An unstable or
    unreadable tree refuses admission rather than granting a cached allowance.
    """
    allocated, seen = 0, set()
    stack = []
    for name in roots:
        path = Path(name)
        if not path.is_absolute() or path != path.resolve():
            raise ValueError("owned-root alias")
        if path.exists():
            stack.append(str(path))
    while stack:
        directory = stack.pop()
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            current = os.fstat(fd)
            key = (current.st_dev, current.st_ino)
            if key in seen:
                continue
            seen.add(key)
            allocated += current.st_blocks * 512
            with os.scandir(fd) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(os.path.join(directory, entry.name))
                        continue
                    item = entry.stat(follow_symlinks=False)
                    key = (item.st_dev, item.st_ino)
                    if key in seen:
                        continue
                    seen.add(key)
                    if stat.S_ISREG(item.st_mode) and item.st_nlink == 1:
                        allocated += item.st_blocks * 512
        finally:
            os.close(fd)
    return allocated


SLOTS = {
    "prepared.json": 16384,
    "entry-emergency.json": 16384,
    "worker.json": 16384,
    "memory.log": 16384,
    "scope.log": 65536,
    "run.log": 262144,
    "delivery.json": 16384,
    "resource.json": 16384,
    "native-completion.json": 16384,
    "completion.json": 16384,
    "capture-partial.json": 2621440,
}

SLOTS.update(
    {
        name + ".resource.json": 16384
        for name in ("memory.log", "scope.log", "run.log", "delivery.json")
    }
)


class NativeStorage:
    def __init__(self, root, job):
        self.root, self.job = Path(root), job

    def physical(self):
        """Fresh FULL reserve check for an operation that allocates no bytes.

        The caller separately receives actual native/authority/code/kernel
        permission. This does not authorize a file write or replace check().
        """
        required = (
            self.job["protected_normal_bytes"]
            + self.job["whole_route_bytes"]
            + 12582912
            + 1073741824
            + 65536
            + 12288
        )
        disk = os.statvfs(self.root)
        if disk.f_bavail * disk.f_frsize < required:
            raise ValueError("full concurrent physical reserve exhausted")

    def check(self, extra=0, *, path=None):
        if type(extra) is not int or extra < 0:
            raise ValueError("invalid storage request")
        if path is not None:
            path = Path(path)
            if not path.is_absolute() or path != path.resolve():
                raise ValueError("aliased native output")
            roots = [Path(r) for r in self.job["owned_roots"]]
            if not any(path == r or r in path.parents for r in roots):
                raise ValueError("output outside active aggregate")
            # Worst-case blocks for every missing ancestor, counted before mkdir.
            parent = path.parent
            while not parent.exists():
                extra += 8192
                parent = parent.parent
        result = capacity(self.root, self.job)
        if extra > result["remaining_current"]:
            raise ValueError("next native write exceeds aggregate remaining peak")
        return result

    def mkdir(self, path):
        self.check(8192, path=path)
        _ensure_durable_directory(Path(path))

    def save(self, path, value):
        size = len(json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode()) + 1
        self.check(2 * ((size + 4095) // 4096) * 4096 + 8192, path=path)
        return save(Path(path), value)

    def prepare(self, output, binding):
        directory = Path(str(output) + ".launcher")
        self.check(sum(SLOTS.values()) + 32768, path=directory / "prepared.json")
        _ensure_durable_directory(directory.parent)
        directory.mkdir()  # Exclusive one-shot launcher, including failed admission.
        _sync_directory(directory.parent)
        for name, size in SLOTS.items():
            fd = os.open(
                directory / name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            try:
                os.posix_fallocate(fd, 0, size)
                offset = 0
                while offset < size:
                    n = os.pwrite(fd, b"\0" * min(65536, size - offset), offset)
                    if n <= 0:
                        raise OSError("short native slot initialization")
                    offset += n
                os.fsync(fd)
            finally:
                os.close(fd)
        _sync_directory(directory)
        fixed_record(
            directory,
            "prepared.json",
            dict(
                job=binding,
                invocation_id=self.job["invocation_id"],
                output=str(output),
                slots=SLOTS,
            ),
        )
        return directory


class FixedSlot:
    def __init__(self, directory, name):
        directory = Path(directory)
        if not directory.is_absolute() or directory != directory.resolve():
            raise ValueError("aliased preallocated native directory")
        self.path, self.limit = directory / name, SLOTS[name]
        self.fd = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW)
        s = os.fstat(self.fd)
        if (
            not stat.S_ISREG(s.st_mode)
            or s.st_nlink != 1
            or s.st_size != self.limit
            or s.st_blocks * 512 < self.limit
        ):
            os.close(self.fd)
            raise ValueError("preallocated native slot differs")
        self.offset = 0

    def append(self, data):
        if self.offset + len(data) > self.limit:
            raise ValueError("bounded native log overflow; child must stop")
        while data:
            n = os.pwrite(self.fd, data, self.offset)
            if n <= 0:
                raise OSError("short fixed-slot write")
            self.offset += n
            data = data[n:]
        os.fsync(self.fd)

    def close(self):
        os.close(self.fd)


def fixed_record(directory, name, value):
    raw = json.dumps(value, sort_keys=True, allow_nan=False).encode() + b"\n"
    slot = FixedSlot(directory, name)
    try:
        if len(raw) > slot.limit:
            raise ValueError("fixed finalizer overflow")
        slot.append(raw + b" " * (slot.limit - len(raw)))
    finally:
        slot.close()


def require_prepared(output, binding, invocation):
    directory = Path(str(output) + ".launcher")
    # Open with the same no-symlink/size checks as the eventual overwrite.
    slot = FixedSlot(directory, "prepared.json")
    try:
        value = json.loads(os.pread(slot.fd, slot.limit, 0))
    finally:
        slot.close()
    if value != dict(job=binding, invocation_id=invocation, output=str(output), slots=SLOTS):
        raise ValueError("launcher preparation does not bind this invocation")
    return directory


def require_partial_room(storage):
    """No further account GET after this invocation has retained an unusable prefix."""
    slot = FixedSlot(Path(str(storage.job["output"]) + ".launcher"), "capture-partial.json")
    try:
        if os.pread(slot.fd, 1, 0) != b"\0":
            raise ValueError("retained partial requires explicit successor, no more GET")
    finally:
        slot.close()


def retain_partial(storage, value):
    require_partial_room(storage)
    fixed_record(Path(str(storage.job["output"]) + ".launcher"), "capture-partial.json", value)


class CaptureSlots:
    """One-use, physically allocated JSON files; never a cached allocation credit.

    Existing full inventories count these files before another writer allocates.
    Unused or failed slots remain allocated. A binding is returned only after
    complete publication, fsync and readback; prepared/torn files are not receipts.
    Covered read-only GETs use fresh physical guards. Every allocation and
    financial mutation retains the ordinary full inventory guard.
    """

    def __init__(self, storage, directory, trace, symbols, ordinal):
        self.storage = storage
        self.files = {}
        self.used = set()
        directory, trace = Path(directory), Path(trace)
        sizes = {
            "account": 16384,
            "market-clock": 16384,
            "positions": 65536,
            "orders": 65536,
            "open-orders": 65536,
            "activities-000": 65536,
        }
        # Only the admitted fast-path storage subset is preallocated. The
        # account receiver still fetches EVERY additional asset via its full guard.
        for symbol in sorted(symbols)[:10]:
            if not isinstance(symbol, str) or not symbol.replace(".", "").isalnum():
                raise ValueError("invalid capture asset path")
            sizes["asset-" + symbol] = 16384
        paths = {directory / (name + ".json"): size for name, size in sizes.items()}
        self.directory = directory
        for index in range(ordinal, ordinal + len(sizes)):
            paths[trace / f"{index:04d}.prepared.json"] = 16384
        # Before any mkdir or fallocate, protect all payload and directory growth.
        storage.check(sum(paths.values()) + 65536, path=directory / "capture.json")
        if directory.exists():
            raise ValueError("capture directory already exists")
        _ensure_durable_directory(directory.parent)
        directory.mkdir()
        _sync_directory(directory.parent)
        if not trace.is_dir() or trace != trace.resolve():
            raise ValueError("prepared trace directory required")
        for path, size in paths.items():
            if path != path.resolve():
                raise ValueError("aliased capture slot")
            storage.check(size + 8192, path=path)
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.posix_fallocate(fd, 0, size)
                # Materialize written extents before timing: converting ext4
                # unwritten extents piecemeal can itself allocate extent metadata.
                offset = 0
                while offset < size:
                    n = os.pwrite(fd, b"\0" * min(65536, size - offset), offset)
                    if n <= 0:
                        raise OSError("short capture preparation")
                    offset += n
                os.fsync(fd)
                s = os.fstat(fd)
                if s.st_blocks * 512 < size or s.st_nlink != 1:
                    raise ValueError("capture slot is not exclusively allocated")
                self.files[path] = (s.st_dev, s.st_ino, size, s.st_blocks)
            finally:
                os.close(fd)
        _sync_directory(directory)
        _sync_directory(trace)
        self.ancestors = {}
        for parent in (directory, trace):
            for path in (parent, *parent.parents):
                s = path.lstat()
                if not stat.S_ISDIR(s.st_mode) or path != path.resolve():
                    raise ValueError("aliased capture ancestor")
                self.ancestors[path] = (s.st_dev, s.st_ino)
        manifest = dict(
            invocation_id=storage.job.get("invocation_id"),
            files=[
                dict(path=str(p), device=v[0], inode=v[1], bytes=v[2], blocks=v[3])
                for p, v in self.files.items()
            ],
            single_use=True,
            prepared_not_received=True,
            no_allocation_credit_in_physical_guard=True,
            overflow_uses_original_full_guard=True,
        )
        self.manifest = storage.save(directory / "preallocation.json", manifest)
        if json.loads(bound_bytes(storage.root, self.manifest)) != manifest:
            raise ValueError("preallocation manifest readback differs")
        # Reconcile actual allocation (including metadata) before starting clock.
        storage.check()

    def physical(self):
        # FULL concurrent maxima, no allocated-byte credit at all. The actual
        # job's independently received current normal forecast remains binding.
        self.storage.physical()

    def publish(self, path, raw):
        path = Path(path)
        if path not in self.files or path in self.used:
            raise ValueError("unknown or consumed capture slot")
        device, inode, size, blocks = self.files[path]
        if len(raw) > size:
            raise ValueError("capture slot overflow")
        self.physical()
        bound_bytes(self.storage.root, self.manifest)
        for parent, identity in self.ancestors.items():
            s = parent.lstat()
            if not stat.S_ISDIR(s.st_mode) or (s.st_dev, s.st_ino) != identity:
                raise ValueError("capture ancestor changed")
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        try:

            def verify():
                s, p = os.fstat(fd), path.lstat()
                if (
                    not stat.S_ISREG(s.st_mode)
                    or s.st_nlink != 1
                    or (s.st_dev, s.st_ino, s.st_size, s.st_blocks) != (device, inode, size, blocks)
                    or (p.st_dev, p.st_ino) != (device, inode)
                ):
                    raise ValueError("capture slot allocation or identity changed")

            verify()
            self.used.add(path)  # Failed/torn attempts cannot be replayed.
            payload = raw + b" " * (size - len(raw))
            offset = 0
            while offset < size:
                self.physical()
                n = os.pwrite(fd, payload[offset : offset + 65536], offset)
                if n <= 0:
                    raise OSError("short capture slot write")
                offset += n
            os.fsync(fd)
            verify()
            if os.pread(fd, size, 0) != payload:
                raise ValueError("capture slot readback differs")
            return dict(path=str(path), bytes=size, sha256=hashlib.sha256(payload).hexdigest())
        finally:
            os.close(fd)

    def covers_get(self, name, prepared):
        """Only an exact prepared GET whose body has a retained slot is covered."""
        return (
            self.directory / (name + ".json") in self.files and Path(prepared["path"]) in self.used
        )

    def guard_get(self):
        self.physical()
        bound_bytes(self.storage.root, self.manifest)
        for parent, identity in self.ancestors.items():
            s = parent.lstat()
            if not stat.S_ISDIR(s.st_mode) or (s.st_dev, s.st_ino) != identity:
                raise ValueError("capture ancestor changed")
        for path, identity in self.files.items():
            s = path.lstat()
            if (
                not stat.S_ISREG(s.st_mode)
                or s.st_nlink != 1
                or (s.st_dev, s.st_ino, s.st_size, s.st_blocks) != identity
            ):
                raise ValueError("reserved capture extent changed before GET")
