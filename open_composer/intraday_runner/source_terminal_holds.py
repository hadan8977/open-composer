"""Positive local proofs that an October reservation was never submitted.

Used by the six-policy service to end old pre-submit reservations. No amount is
released here and no already consumed order becomes retryable.
"""

from __future__ import annotations

import copy


def receive_not_dispatched_guard_refusal(state, fills, fees, evidence, *, cid, journal):
    """Receive a durable refusal before submit; never release or reuse its ID."""
    import hashlib
    import json
    import stat

    from open_composer.intraday_runner.source_dispatch_journal import _hash

    path = journal._path(cid)
    before = path.lstat()
    if path != path.resolve() or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("aliased guard-refusal journal")
    raw = path.read_bytes()
    record = json.loads(raw)
    after = path.lstat()
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or after.st_nlink != 1
        or path != path.resolve()
    ):
        raise ValueError("guard-refusal journal changed while received")
    witness = evidence.get("dispatch_intents", {}).get(cid)
    row = state.pending.get(cid)
    directory = journal.directory.lstat()
    if (
        record.get("stage") != "not_dispatched_guard_refusal"
        or (
            "transport_evidence" in record
            and record["transport_evidence"].get("physical_call_started") is not False
        )
        or record.get("observations") != []
        or record.get("client_order_id") != cid
        or record.get("request", {}).get("client_order_id") != cid
        or _hash(record["request"]) != record.get("request_sha256")
        or not witness
        or witness.get("attempted") is not True
        or row is None
        or row.get("filled") != 0
        or cid not in state.consumed_ids
        or _hash(row) != witness.get("reservation_sha256")
        or record["request"].get("reservation") != row
        or record.get("reservation_snapshot", {}).get("pending", {}).get(cid) != row
        or any(v.get("client_order_id") == cid for v in (*fills.values(), *fees.values()))
        or str(journal.directory) != witness.get("journal_root")
        or [directory.st_dev, directory.st_ino] != witness.get("journal_identity")
    ):
        raise ValueError("no exact known pre-submit guard-refusal proof")
    return dict(
        journal=dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()),
        client_order_id=cid,
        stage=record["stage"],
        no_physical_submit_in_this_attempt=True,
        broker_terminal_claim=False,
        reservation_released=False,
        consumed_id_reusable=False,
    )


def receive_never_attempted(state, fills, fees, evidence, *, cid, journal):
    """Positive local witness only; a missing journal alone proves nothing."""
    import os
    import stat

    from open_composer.intraday_runner.source_dispatch_journal import _hash

    witness = evidence.get("dispatch_intents", {}).get(cid)
    row = state.pending.get(cid)
    directory = journal.directory.lstat()
    if (
        not witness
        or witness.get("attempted") is not False
        or witness.get("locally_abandoned") is True
        or row is None
        or row.get("filled") != 0
        or cid not in state.consumed_ids
        or _hash(row) != witness.get("reservation_sha256")
        or not stat.S_ISDIR(directory.st_mode)
        or journal.directory != journal.directory.resolve()
        or str(journal.directory) != witness.get("journal_root")
        or [directory.st_dev, directory.st_ino] != witness.get("journal_identity")
        or os.path.lexists(journal._path(cid))
        or any(v.get("client_order_id") == cid for v in (*fills.values(), *fees.values()))
        or row.get("remaining_funding", []) != row.get("original_funding", [])
        or row.get("confirmed_fee_funding")
    ):
        raise ValueError("missing journal is not positive never-attempted evidence")
    return dict(
        client_order_id=cid,
        stage="durable_never_attempted",
        witness=copy.deepcopy(witness),
        no_physical_submit_in_this_attempt=True,
        broker_terminal_claim=False,
        reservation_released=False,
        consumed_id_reusable=False,
    )
