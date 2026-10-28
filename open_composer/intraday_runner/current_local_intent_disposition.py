"""Pure proposals for positively proved local nonexecution, never broker release.

The owning runtime must separately receive the exact disposition plan, current
native history and implementation, hold the account/operation locks, authenticate
a fresh complete capture, and CAS the returned snapshot with after-storage time
checks. This module has no checkpoint writer, transport, or command-line apply.
"""

from __future__ import annotations

import copy
import json
import stat

from open_composer.intraday_runner.current_initialization_controls import (
    ACCOUNT,
    receive_observation,
)
from open_composer.intraday_runner.source_dispatch_journal import _hash
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.source_terminal_holds import (
    receive_never_attempted,
    receive_not_dispatched_guard_refusal,
)

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


def propose_local_disposition(
    root,
    current,
    state,
    fills,
    fees,
    evidence,
    *,
    journal,
    requested_ids,
    capture,
    capture_binding,
    plan_binding,
    tail_receipt,
    now,
    now_monotonic,
    financial_policy=None,
):
    """Return an append-only snapshot proposal, keeping all economic history.

    A fresh source absence is corroboration only. Positive local proof is
    required separately for every selected intent. Other orders/fills, including
    the STATE positions and LSTM SPY, need not be empty and stay untouched.
    """
    plan = json.loads(bound_bytes(root, plan_binding))
    if (
        plan.get("kind") != "prospective_positive_local_intent_disposition"
        or plan.get("task_id") != current["identity"]["sleeve_id"]
        or plan.get("current_checkpoint_sha256") != _hash(current)
        or plan.get("selected_ids") != requested_ids
        or not requested_ids
        or requested_ids != sorted(set(requested_ids))
        or plan.get("new_capital_flow_USD") != 0
        or plan.get("broker_cancellation") is not False
        or plan.get("consumed_id_reuse") is not False
        or plan.get("new_order_authority") is not False
        or current["snapshot"]["pending"] != state.pending
        or current["snapshot"]["fills"] != fills
        or current["snapshot"]["fees"] != fees
        or current["snapshot"]["evidence"] != evidence
    ):
        raise ValueError("exact current local-disposition proposal required")
    receive_observation(
        capture["observation"],
        now=now,
        now_monotonic=now_monotonic,
        account_hash=ACCOUNT,
        checkpoint_hash=_hash(current),
        purpose="owned_cancel",
        financial_policy=financial_policy,
    )
    # The live caller receives all exact authenticated bodies, complete account
    # attribution and current native-history plan before invoking this proposal.
    # Require its saved capture to be the exact argument, never an unbound dict.
    if json.loads(bound_bytes(root, capture_binding)) != capture:
        raise ValueError("current disposition capture changed")
    working, audit = copy.deepcopy(state), copy.deepcopy(evidence)
    for cid in requested_ids:
        row = state.pending.get(cid)
        if (
            row is None
            or row.get("side") != "buy"
            or row.get("filled") != 0
            or cid not in state.consumed_ids
            or row.get("remaining_funding") != row.get("original_funding")
            or row.get("confirmed_fee_funding")
            or any(p["source"] != "cash" for p in row.get("remaining_funding", []))
            or cid in capture["aggregate_orders"]
            or cid in capture["orders"]
            or any(v.get("client_order_id") == cid for v in (*fills.values(), *fees.values()))
            or cid in audit.get("locally_terminalized_intents", {})
        ):
            raise ValueError("selected intent has execution/economic use or unsupported source")
        witness = evidence.get("dispatch_intents", {}).get(cid, {})
        if witness.get("attempted") is False:
            proof = receive_never_attempted(state, fills, fees, evidence, cid=cid, journal=journal)
            kind = "durable_never_attempted"
            if capture.get("known_guard_refusals", {}).get(cid) != proof:
                raise ValueError("fresh local nonattempt proof changed")
        else:
            record = journal.receive(cid)
            if record.get("stage") == "not_dispatched_guard_refusal":
                proof = receive_not_dispatched_guard_refusal(
                    state,
                    fills,
                    fees,
                    evidence,
                    cid=cid,
                    journal=journal,
                )
                kind = "physical_guard_refusal"
                if capture.get("known_guard_refusals", {}).get(cid) != proof:
                    raise ValueError("fresh local guard-refusal proof changed")
            else:
                proof = receive_original_unreached(
                    root,
                    current,
                    receipt_binding=tail_receipt,
                    cid=cid,
                    journal=journal,
                )
                kind = "original_invocation_UNREACHED"
                if (
                    capture.get("unknown_attempts", {}).get(cid, {}).get("journal")
                    != proof["journal"]
                ):
                    raise ValueError("fresh raw unknown prefix differs from original nonreach")
        del working.pending[cid]
        audit.setdefault("locally_terminalized_intents", {})[cid] = dict(
            kind=kind,
            original_reservation=copy.deepcopy(row),
            positive_proof=proof,
            current_capture=copy.deepcopy(capture_binding),
            exact_plan=copy.deepcopy(plan_binding),
            at=now.isoformat(),
            broker_terminal_claim=False,
            broker_cancellation_claim=False,
            raw_journal_changed=False,
            consumed_id_reusable=False,
            replacement_order_authority=False,
        )
    if (
        working.cashbook != state.cashbook
        or working.consumed_ids != state.consumed_ids
        or working.applied_fill_ids != state.applied_fill_ids
        or audit.get("risk") != evidence.get("risk")
        or audit.get("allocation_flows") != evidence.get("allocation_flows")
        or any(
            working.pending[cid] != row
            for cid, row in state.pending.items()
            if cid not in requested_ids
        )
    ):
        raise ValueError("local disposition changed financial history or an unselected hold")
    audit["initial_dispatch_blocked"] = True
    return working, audit
