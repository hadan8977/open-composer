"""Atomic own-sleeve reservation/receipt checkpoints, without any transport.

One complete snapshot contains cash/lots/rights, pending reservations, consumed
IDs and separately typed fill/fee provenance. Immutable revisions plus the head
retain local history. An interrupted head publication blocks ordinary reads;
explicit recovery can only publish the exact already-written revision, never
recompute a fill, release cash, replay an order or infer broker completeness.
The caller still holds the existing account lock and authenticates/reconciles
all inputs. This local store's lock/CAS is not a cross-strategy capital lock.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from open_composer.adapters.broker.alpaca_paper import _atomic_write_text
from open_composer.intraday_runner.source_dispatch_journal import (
    _canonical,
    _ensure_durable_directory,
    _hash,
    _sync_directory,
)
from open_composer.intraday_runner.source_method_bindings import CODE, source_module
from open_composer.intraday_runner.source_reservations import SourceReservations


def snapshot(state: SourceReservations, fills: dict, fees: dict, *, evidence: dict) -> dict:
    """Copy all state; fee IDs share the legacy applied_fill_ids namespace."""
    if set(vars(state)) != {"cashbook", "pending", "consumed_ids", "applied_fill_ids"}:
        raise ValueError("unhandled reservation state fields")
    value = {
        "cashbook": asdict(state.cashbook),
        "pending": copy.deepcopy(state.pending),
        "consumed_ids": sorted(state.consumed_ids),
        "applied_fill_ids": sorted(state.applied_fill_ids),
        "fills": copy.deepcopy(fills),
        "fees": copy.deepcopy(fees),
        "evidence": copy.deepcopy(evidence),
    }
    _validate(value)
    return json.loads(_canonical(value))


def _validate(value: dict) -> None:
    if set(value) != {
        "cashbook",
        "pending",
        "consumed_ids",
        "applied_fill_ids",
        "fills",
        "fees",
        "evidence",
    }:
        raise ValueError("incomplete checkpoint fields")
    if set(value["cashbook"]) != {"cash", "sales", "purchases", "dividends", "lots", "next_id"}:
        raise ValueError("unhandled cashbook fields")
    for key in ("consumed_ids", "applied_fill_ids"):
        ids = value[key]
        if not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids):
            raise ValueError("invalid checkpoint IDs")
        if ids != sorted(set(ids)):
            raise ValueError("duplicate or noncanonical checkpoint IDs")
    for key in ("pending", "fills", "fees", "evidence"):
        if not isinstance(value[key], dict):
            raise ValueError("invalid checkpoint map")
    fills, fees = value["fills"], value["fees"]
    if set(fills) & set(fees) or set(fills) | set(fees) != set(value["applied_fill_ids"]):
        raise ValueError("typed receipt maps and applied IDs disagree")
    if not set(value["pending"]) <= set(value["consumed_ids"]):
        raise ValueError("pending order lacks consumed ID")
    for row in (*fills.values(), *fees.values()):
        if not isinstance(row, dict) or row.get("client_order_id") not in value["consumed_ids"]:
            raise ValueError("receipt lacks consumed own intent")
    # JSON disallows nonfinite numbers; this is serialization/integrity, not a
    # substitute for the accepted economic transitions or authenticated inputs.
    _canonical(value)


def restore(root: Path, value: dict) -> tuple[SourceReservations, dict, dict, dict]:
    _validate(value)
    v = copy.deepcopy(value)
    return (
        SourceReservations(
            source_module(root, "cash").CashState(**v["cashbook"]),
            pending=v["pending"],
            consumed_ids=set(v["consumed_ids"]),
            applied_fill_ids=set(v["applied_fill_ids"]),
        ),
        v["fills"],
        v["fees"],
        v["evidence"],
    )


class SourceStateCheckpoint:
    def __init__(self, directory: Path, *, account_hash: str, sleeve_id: str, write_guard=None):
        if not re.fullmatch(r"[0-9a-f]{64}", account_hash):
            raise ValueError("exact account hash required, not authentication")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", sleeve_id):
            raise ValueError("invalid sleeve identity")
        self.directory = Path(directory).absolute()
        self.write_guard = write_guard
        self.identity = dict(
            account_hash=account_hash,
            sleeve_id=sleeve_id,
            cash_reader_sha256=CODE["cash"]["sha256"],
        )

    def _before_write(self, path, size, *, atomic=True):
        if self.write_guard is not None:
            if self.write_guard(path, size, atomic=atomic) is not None:
                raise ValueError("checkpoint storage guard must raise or return None")

    @contextmanager
    def _locked(self):
        path = self.directory / "checkpoint.lock"
        if path != path.resolve():
            raise ValueError("checkpoint lock ancestor alias")
        try:
            before = path.lstat()
        except FileNotFoundError:
            self._before_write(path, 0, atomic=False)
            _ensure_durable_directory(self.directory)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        else:
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != 0:
                raise ValueError("invalid existing checkpoint lock")
            # Acquiring an existing empty lock neither allocates nor writes.
            # Financial revision/head publications still take their full guards.
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
            current = os.fstat(fd)
            if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
                os.close(fd)
                raise ValueError("checkpoint lock changed during open")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            identity = os.fstat(fd)
            current = path.lstat()
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_nlink != 1
                or current.st_size != 0
                or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino)
                or path != path.resolve()
            ):
                raise ValueError("checkpoint lock identity changed")
            yield
            current = path.lstat()
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_nlink != 1
                or current.st_size != 0
                or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino)
                or path != path.resolve()
            ):
                raise ValueError("checkpoint lock changed while held")
        finally:
            os.close(fd)

    def _read(self, path: Path) -> dict:
        if path.is_symlink():
            raise ValueError("checkpoint aliases refused")
        data = path.read_text()
        value = json.loads(data)
        if data != _canonical(value) + "\n":
            raise ValueError("noncanonical or torn checkpoint")
        return value

    def _revision(self, generation: int) -> Path:
        return self.directory / f"revision-{generation:08d}.json"

    def _chain(self) -> dict | None:
        head_path = self.directory / "head.json"
        if not head_path.exists():
            if head_path.is_symlink():
                raise ValueError("checkpoint aliases refused")
            return None
        head = self._read(head_path)
        if (
            set(head) != {"generation", "sha256"}
            or type(head["generation"]) is not int
            or head["generation"] < 0
        ):
            raise ValueError("invalid checkpoint head")
        prior = None
        for n in range(head["generation"] + 1):
            current = self._read(self._revision(n))
            self._check_revision(current, prior)
            prior = current
        if _hash(prior) != head["sha256"]:
            raise ValueError("checkpoint head hash mismatch")
        return prior

    def _check_revision(self, current: dict, prior: dict | None) -> None:
        if set(current) != {"schema", "identity", "generation", "previous_sha256", "snapshot"}:
            raise ValueError("invalid checkpoint revision")
        if current["schema"] != 1 or current["identity"] != self.identity:
            raise ValueError("checkpoint reader/account/sleeve mismatch")
        if type(current["generation"]) is not int or current["generation"] != (
            0 if prior is None else prior["generation"] + 1
        ):
            raise ValueError("checkpoint generation mismatch")
        if current["previous_sha256"] != (None if prior is None else _hash(prior)):
            raise ValueError("checkpoint predecessor mismatch")
        v = current["snapshot"]
        _validate(v)
        for row in (*v["fills"].values(), *v["fees"].values()):
            if row.get("account_hash") != self.identity["account_hash"]:
                raise ValueError("receipt account mismatch")
        if prior is not None:
            old = prior["snapshot"]
            if not set(old["consumed_ids"]) <= set(v["consumed_ids"]):
                raise ValueError("consumed ID rollback")
            for kind in ("fills", "fees"):
                if any(v[kind].get(k) != record for k, record in old[kind].items()):
                    raise ValueError("receipt history removed or rewritten")

    def _no_extra_revision(self, prior: dict | None) -> None:
        n = 0 if prior is None else prior["generation"] + 1
        expected = {self._revision(i).name for i in range(n)}
        actual = {p.name for p in self.directory.glob("revision-*.json")}
        if actual != expected:
            raise ValueError("unpublished/missing revision; explicit exact recovery required")

    def load(self) -> dict | None:
        with self._locked():
            prior = self._chain()
            self._no_extra_revision(prior)
            return prior

    def _publish(self, revision: dict) -> None:
        payload = (
            _canonical({"generation": revision["generation"], "sha256": _hash(revision)}) + "\n"
        )
        path = self.directory / "head.json"
        self._before_write(path, len(payload.encode()))
        _atomic_write_text(path, payload)

    def commit(self, value: dict, *, expected_head_sha256: str | None) -> dict:
        # Freeze before locking: no callback may rewrite what is committed.
        value = json.loads(_canonical(value))
        with self._locked():
            prior = self._chain()
            self._no_extra_revision(prior)
            if expected_head_sha256 != (None if prior is None else _hash(prior)):
                raise ValueError("stale checkpoint writer")
            revision = dict(
                schema=1,
                identity=self.identity.copy(),
                generation=0 if prior is None else prior["generation"] + 1,
                previous_sha256=expected_head_sha256,
                snapshot=value,
            )
            self._check_revision(revision, prior)
            path = self._revision(revision["generation"])
            payload = _canonical(revision) + "\n"
            self._before_write(path, len(payload.encode()), atomic=False)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            _sync_directory(self.directory)
            self._publish(revision)
            return revision

    def recover(self, *, exact_revision_sha256: str) -> dict:
        """Finish local publication ONLY. No broker action or state recomputation."""
        with self._locked():
            prior = self._chain()
            if prior is not None and _hash(prior) == exact_revision_sha256:
                self._no_extra_revision(prior)
                self._publish(prior)  # Repeat durability barrier after uncertain fsync.
                return prior
            n = 0 if prior is None else prior["generation"] + 1
            expected = {self._revision(i).name for i in range(n + 1)}
            if {p.name for p in self.directory.glob("revision-*.json")} != expected:
                raise ValueError("recovery requires one exact contiguous unpublished revision")
            revision = self._read(self._revision(n))
            self._check_revision(revision, prior)
            if _hash(revision) != exact_revision_sha256:
                raise ValueError("recovery revision hash mismatch")
            with self._revision(n).open("rb") as stream:
                os.fsync(stream.fileno())
            _sync_directory(self.directory)
            self._publish(revision)
            return revision
