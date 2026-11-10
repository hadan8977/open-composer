"""Task-specific local transfer and shared-write guards for the received Martin scope."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "reports/research/program/martin-decision-loop-model-continuation-20261026"
ITERATION = ROOT / "reports/research/iterations/t20261026_martin_observed_attempt_value"
META = TASK / "modal-migration"
CAPACITY = (
    ROOT
    / "reports/ops/disk-audit-20261015/route-recovery-20261023"
    / "martin-modal-complete-local12GiB-runtime-capacity-reception-20261027.json"
)
CAPACITY_SHA = "544bc2f9a4957bdd3a5fe64c45c07057c7a268720a2024f0ea60800202753a3f"
LIMITS = {"labels": 8 << 30, "tar": 1 << 30, "metadata": 512 << 20, "later": 2560 << 20}
SHARED = {
    ROOT / "reports/research/control" / name
    for name in (
        "modal-data-manifest.json",
        "modal-ledger.jsonl",
        "modal-ledger-actuals.jsonl",
        "modal-ledger.jsonl.lock",
    )
}
ACCOUNTING = {
    META / name
    for name in (
        "storage-baseline.json",
        "storage-highwater.json",
        "storage-highwater.tmp",
        "storage.lock",
    )
}


def rounded(value):
    return (int(value) + 4095) // 4096 * 4096


def category(path):
    path = Path(path).absolute()
    if (
        path in SHARED
        or any(str(path).startswith(str(p) + ".martin.tmp-") for p in SHARED)
        or path.parent == ROOT / "logs"
        and path.name.startswith("modal-martin-")
    ):
        return "metadata"
    if path.is_relative_to(ITERATION):
        return "metadata"
    if not path.is_relative_to(TASK):
        raise ValueError("Unregistered Martin local writer: " + str(path))
    relative = path.relative_to(TASK)
    if not relative.parts:
        return "metadata"
    if "labels" in relative.parts:
        return "labels"
    if path.name.endswith(".tar.part"):
        return "tar"
    if relative.parts[0] in {"runs", "training-v3", "summary-v3-fit01", "tcn-v3-fit01"}:
        return "later"
    return "metadata"


def ancestors(path):
    result, parent = [], Path(path).parent
    while not parent.exists():
        result.append(parent)
        parent = parent.parent
    return result


def inode_key(st):
    return f"{st.st_dev}:{st.st_ino}"


def objects():
    for root in (TASK, ITERATION):
        if root.exists():
            for directory, dirs, files in os.walk(root, followlinks=False):
                yield Path(directory)
                for name in dirs:
                    if (Path(directory) / name).is_symlink():
                        raise ValueError("Owned directory symlink refused")
                for name in files:
                    yield Path(directory) / name
    yield from (ROOT / "logs").glob("modal-martin-*.log")


def growth_snapshot(baseline):
    highest = {key: 0 for key in LIMITS}
    for attempt in range(3):
        current, seen = {key: 0 for key in LIMITS}, set()
        try:
            for item in objects():
                if item in ACCOUNTING:
                    continue
                st = item.lstat()
                if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                    raise ValueError("Owned nonregular writer refused")
                identity = inode_key(st)
                if identity in seen:
                    continue
                seen.add(identity)
                original = baseline.get(identity)
                same_retained_inode = (
                    original is not None and original["ctime_ns"] == st.st_ctime_ns
                )
                growth = max(
                    0, st.st_blocks * 512 - (original["bytes"] if same_retained_inode else 0)
                )
                if not same_retained_inode:
                    growth += 4096
                current[category(item)] += growth
        except FileNotFoundError:
            highest = {key: max(highest[key], current[key]) for key in LIMITS}
            if attempt == 2:
                raise ValueError("Unstable own allocation; retain/refuse") from None
        else:
            return {key: max(highest[key], current[key]) for key in LIMITS}
    raise AssertionError("Unreachable")


class Guard:
    def __init__(self):
        raw = CAPACITY.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == CAPACITY_SHA
        self.schema = json.loads(raw)["accepted_runtime_guard_schema"]
        assert self.schema["capacity_accepted"]
        baseline = META / "storage-baseline.json"
        highwater = META / "storage-highwater.json"
        if not baseline.exists():
            # Freeze once before the first runtime write. Never reset on retry.
            assert not highwater.exists(), "Retained highwater forbids baseline reinitialization"
            self.physical(8 << 20, [baseline, highwater, META / "storage.lock"])
            rows = {}
            for path in objects():
                if path in ACCOUNTING:
                    continue
                st = path.lstat()
                assert stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)
                rows[inode_key(st)] = dict(bytes=st.st_blocks * 512, ctime_ns=st.st_ctime_ns)
            with baseline.open("x") as stream:
                json.dump(dict(capacity_sha256=CAPACITY_SHA, allocated_by_inode=rows), stream)
                stream.flush()
                os.fsync(stream.fileno())
            with highwater.open("x") as stream:
                json.dump(dict(components={key: 0 for key in LIMITS}, shared_own_bytes=0), stream)
                stream.flush()
                os.fsync(stream.fileno())
        self.baseline = json.loads(baseline.read_text())
        assert self.baseline["capacity_sha256"] == CAPACITY_SHA and highwater.exists()

    def physical(self, amount, creators):
        # Main selected only this research lane. A newly assigned positive-growth
        # lane must supply its complete obligation before this consumer proceeds.
        control = json.loads(
            (ROOT / "reports/research/control/owner-compute-hold.json").read_text()
        )
        for key in (
            "session_exposure_allocation_20261026",
            "portfolio_underlying_transfer_20261026",
        ):
            other = control.get(key, {})
            if other.get("new_starts_allowed") is True:
                raise ValueError(
                    "New concurrent assigned obligation requires actual capacity reception"
                )
        fs = os.statvfs(ROOT)
        absent = {str(p) for p in creators if not Path(p).exists()}
        # Received concurrent author/peer metadata creators remain included.
        if fs.f_bavail * fs.f_frsize < self.schema["required_fresh_available_bytes"] + rounded(
            amount
        ):
            raise ValueError("Fresh disk floor plus NEXT allocation refused")
        if fs.f_favail < max(2, len(absent) + 1024):
            raise ValueError("Fresh dynamic inode creators refused")

    def before(self, path, size, *, creators=(), shared=False):
        path = Path(path).absolute()
        purpose = category(path)
        creators = [*ancestors(path), *map(Path, creators)]
        if not path.exists():
            creators.append(path)
        amount = rounded(size) + 8192 * len({str(p) for p in creators if not p.exists()}) + 4096
        self.physical(amount + (8 << 20), creators)
        lock_path = META / "storage.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            high_path = META / "storage-highwater.json"
            previous = json.loads(high_path.read_text())
            current = growth_snapshot(self.baseline["allocated_by_inode"])
            # Shared foreign bytes are never attributed to this task. Charge its
            # own full replacement/append allocation conservatively and durably.
            own_shared = previous["shared_own_bytes"] + (amount if shared else 0)
            current["metadata"] += own_shared + (8 << 20)
            high = {key: max(previous["components"][key], current[key]) for key in LIMITS}
            projected = dict(high)
            if not shared:
                projected[purpose] += amount
            assert all(projected[k] <= LIMITS[k] for k in LIMITS), (purpose, projected)
            assert sum(projected.values()) <= self.schema["whole_remaining_forecast_bytes"]
            # Pending shared attribution survives a partial write or exception.
            record = dict(
                components=projected,
                shared_own_bytes=own_shared,
                conservative_pending_write_upper_attribution_not_measured_usage=True,
                last_next_allocation=amount,
                last_path=str(path),
                capacity_sha256=CAPACITY_SHA,
            )
            raw = (json.dumps(record, indent=2) + "\n").encode()
            assert len(raw) < 1 << 20
            temporary = META / "storage-highwater.tmp"
            with temporary.open("x") as stream:
                stream.write(raw.decode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, high_path)
            fsync_parent(high_path)

    def json(self, path, value):
        path = Path(path)
        raw = (json.dumps(value, ensure_ascii=False, default=str, indent=2) + "\n").encode()
        temporary = path.with_name(path.name + ".tmp")
        self.before(temporary, len(raw), creators=[path])
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_parent(path)


def fsync_parent(path):
    fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def move_verified_directory(source, destination):
    """Only after the caller verifies every returned file; no EXDEV/copy fallback."""
    source, destination = Path(source), Path(destination)
    assert source.is_dir() and not source.is_symlink() and not destination.exists()
    before = source.stat()
    assert before.st_dev == destination.parent.stat().st_dev
    from_env().before(destination.parent, 0)
    os.rename(source, destination)
    fsync_parent(source)
    fsync_parent(destination)
    after = destination.stat()
    assert (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
    return dict(device=after.st_dev, inode=after.st_ino, copy_created=False)


_guard = None


def from_env():
    global _guard
    if os.environ.get("OC_MARTIN_STORAGE_GUARD") != "1":
        return None
    if _guard is None:
        _guard = Guard()
    return _guard


def receive_tar(volume, remote, destination, index):
    """One named partial, bounded writes, pre-sized regular members, no retry."""
    guard = from_env()
    assert guard is not None
    import multiprocessing
    import tempfile

    # Modal1.5.5 read_file prefetches cpu_count() blocks. The local Python3.13
    # driver uses PYTHON_CPU_COUNT=1; reject before the RPC if that is not actual.
    assert multiprocessing.cpu_count() == 1, "Unbounded provider download prefetch refused"

    temporary_root = Path(tempfile.gettempdir()).resolve()
    declared = Path(os.environ["TMPDIR"]).resolve()
    assert temporary_root == declared and temporary_root.is_relative_to(META / "jobs")
    assert temporary_root.stat().st_dev == TASK.stat().st_dev
    path = temporary_root / f"return-shard-{index}.tar.part"
    guard.json(
        temporary_root.parent / f"return-shard-{index}-intent.json",
        dict(
            remote=remote,
            retained_partial_path=str(path),
            shard=index,
            maximum_tar_bytes=LIMITS["tar"],
            received_prefix_bytes_from_actual_file_size=True,
        ),
    )
    guard.before(path, 0)
    destination = Path(destination)
    cursor = 0
    try:
        with path.open("xb") as stream:

            class BoundedWriter:
                def write(self, data):
                    nonlocal cursor
                    if cursor + len(data) > LIMITS["tar"]:
                        raise ValueError("One return tar exceeds received1GiB slot")
                    guard.before(path, len(data))
                    n = stream.write(data)
                    if n != len(data):
                        raise OSError("Short tar write; preserve prefix without retry")
                    cursor += n
                    return n

            writer = BoundedWriter()
            for block in volume.read_file(remote):
                writer.write(block)
            stream.flush()
            os.fsync(stream.fileno())
        with tarfile.open(path, "r:gz") as archive:
            members = []
            for member in archive:
                members.append(member)
                assert len(members) <= 10000, "Unexpected creator set; retain tar and refuse"
            names = set()
            for member in members:
                relative = Path(member.name)
                assert not relative.is_absolute() and ".." not in relative.parts
                assert member.isfile() or member.isdir()
                assert str(relative) not in names
                names.add(str(relative))
            creators = [destination / m.name for m in members]
            guard.before(destination, 0, creators=creators)
            for member in members:
                target = destination / member.name
                if member.isdir():
                    guard.before(target, 0)
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                assert not target.exists(), "Never overwrite a prior return"
                guard.before(target, member.size)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                assert source is not None
                with source, target.open("xb") as output:
                    remaining = member.size
                    while remaining:
                        chunk = source.read(min(1 << 20, remaining))
                        assert chunk, "Truncated member; preserve partial"
                        guard.before(target, len(chunk))
                        assert output.write(chunk) == len(chunk)
                        remaining -= len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
        with path.open("rb") as source:
            tar_sha = hashlib.file_digest(source, "sha256").hexdigest()
        receipt = dict(
            remote=remote,
            bytes=cursor,
            tar_sha256=tar_sha,
            members=len(members),
            complete=True,
            status="returned_and_extracted_hash_verification_pending",
        )
        guard.json(temporary_root.parent / f"return-shard-{index}-transfer.json", receipt)
        # Only the successfully extracted transient tar ends its declared lifetime.
        path.unlink()
        fsync_parent(path)
    except BaseException as error:
        guard.json(
            temporary_root.parent / f"return-shard-{index}-incomplete.json",
            dict(
                remote=remote,
                path=str(path),
                received_prefix_bytes=cursor,
                error=repr(error),
                complete=False,
                cloud_closure="UNKNOWN",
                no_automatic_fetch_or_replay=True,
            ),
        )
        raise


if __name__ == "__main__":
    import sys

    assert sys.argv[1] == "new-json"
    target = Path(sys.argv[2])
    assert not target.exists(), "One-shot event already retained"
    raw = sys.stdin.buffer.read(65537)
    assert len(raw) <= 65536
    from_env().json(target, json.loads(raw))
