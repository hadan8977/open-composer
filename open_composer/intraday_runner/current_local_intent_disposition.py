"""Proof that an original October tail intent was never reached, never broker release.

The six-policy service uses it to end such old reservations; this module has no
checkpoint writer, transport or command-line apply.
"""

from __future__ import annotations

import copy
import json
import stat

from open_composer.intraday_runner.current_initialization_controls import ACCOUNT
from open_composer.intraday_runner.source_dispatch_journal import _hash
from open_composer.intraday_runner.source_method_bindings import bound_bytes

TAIL_RECEIPT_SHA = "a70cb05424fed6500fa0e97336df85153f96acc85fedb05a096eed4db22277a1"


def receive_original_unreached(root, current, *, receipt_binding, cid, journal):
    """Receive the sealed ORIGINAL invocation proof and unchanged raw intent.

    Original code hashes are historical facts independently received in that
    receipt, not a demand to keep the old production executable installed. The
    current invocation/history closure is a separate exact native-entry binding.
    """
    if not isinstance(receipt_binding, dict):
        raise ValueError("exact independent nonreach binding required")
    receipt = json.loads(bound_bytes(root, receipt_binding))
    if (
        receipt_binding.get("sha256") != TAIL_RECEIPT_SHA
        or receipt.get("reviewer") != "66ad4b54-ec62-400b-9a03-a29682cf58e6"
        or receipt.get("independent") is not True
        or receipt.get("positive_original_unreached_tail_evidence_received") is not True
        or receipt.get("positive_recorded_later_history_no_initial_tail_BUY_dispatch_received")
        is not True
    ):
        raise ValueError("positive original-invocation nonreach receipt absent")
    matches = [
        (book, row)
        for book in receipt["books"].values()
        for row in book["unreached_tail"]
        if row["client_order_id"] == cid
    ]
    if len(matches) != 1:
        raise ValueError("intent is not an independently received original tail")
    book, row = matches[0]
    original = json.loads(bound_bytes(root, book["durable_arm_snapshot"]))
    value = current["snapshot"]
    old = original["snapshot"]
    pending = value["pending"].get(cid)
    witness = value["evidence"].get("dispatch_intents", {}).get(cid)
    for key in (
        "original_job",
        "authority",
        "initial_decision",
        "original_phase_failure",
        "original_completion",
        "original_native_completion",
    ):
        bound_bytes(root, book[key])
    barrier = json.loads(bound_bytes(root, book["barrier"]["journal"]))
    path = journal._path(cid)
    before = path.lstat()
    raw = bound_bytes(root, row["journal"])
    after = path.lstat()
    record = json.loads(raw)
    directory = journal.directory.lstat()
    if (
        current["identity"] != original["identity"]
        or current["identity"]["account_hash"] != ACCOUNT
        or _hash(original) != book["durable_arm_canonical_checkpoint"]
        or pending is None
        or pending != old["pending"].get(cid)
        or cid not in value["consumed_ids"]
        or witness != old["evidence"].get("dispatch_intents", {}).get(cid)
        or not witness
        or witness.get("attempted") is not True
        or str(path) != row["journal"]["path"]
        or path != path.resolve()
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or [after.st_dev, after.st_ino] != row["original_armed_identity"]
        or after.st_nlink != 1
        or str(journal.directory) != witness.get("journal_root")
        or [directory.st_dev, directory.st_ino] != witness.get("journal_identity")
        or journal.directory != journal.directory.resolve()
        or record.get("stage") != "prepared_no_dispatch"
        or record.get("prepared_owner") != book["batch_owner"]
        or record.get("signal_binding") != book["initial_decision"]
        or record.get("observations") != []
        or record.get("request", {}).get("client_order_id") != cid
        or record.get("request_sha256") != _hash(record["request"])
        or record["request"].get("reservation") != pending
        or record.get("reservation_snapshot", {}).get("pending", {}).get(cid) != pending
        or witness.get("reservation_sha256") != _hash(pending)
        or barrier.get("stage") != "not_dispatched_guard_refusal"
        or barrier.get("transport_evidence", {}).get("physical_call_started") is not False
        or barrier.get("observations") != []
        or row["original_order_index"] <= book["barrier"]["ordered_index"]
        or book["ordered_CIDs"][row["original_order_index"]] != cid
        or row.get("per_intent_guard_or_submit_was_not_executed") is not True
    ):
        raise ValueError("original nonreach identity/reservation/journal changed")
    return dict(
        kind="original_invocation_UNREACHED",
        client_order_id=cid,
        factual_receipt=copy.deepcopy(receipt_binding),
        original_job=book["original_job"],
        original_arm=book["durable_arm_snapshot"],
        journal=copy.deepcopy(row["journal"]),
        original_armed_identity=list(row["original_armed_identity"]),
        barrier=copy.deepcopy(book["barrier"]["journal"]),
        per_intent_guard_executed=False,
        per_intent_submit_executed=False,
        broker_terminal_claim=False,
        raw_prepared_stage_changed=False,
        consumed_id_reusable=False,
    )
