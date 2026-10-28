"""Remove terminal quantity locks while retaining EVERY unreconciled cash liability.

No amount is released, no fee is assumed zero, and no already consumed order
becomes retryable. Raw order/fill provenance remains attached to the hold.
"""

from __future__ import annotations

import copy

from open_composer.intraday_runner.source_dispatch_journal import classify_own_order


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


def retain_terminal_liability(state, evidence, *, journal, observed_order, capture_binding):
    request = journal["request"]
    cid = request["client_order_id"]
    observed = classify_own_order(request, observed_order)
    if not observed["terminal_observed"]:
        raise ValueError("cancel-pending/unknown is not terminal")
    if not journal["observations"] or any(
        row.get("id") != observed["broker_order_id"] for row in journal["observations"]
    ):
        raise ValueError("terminal broker identity differs from original owned order")
    if cid not in state.pending:
        raise ValueError("original pending reservation absent; no speculative closeout")
    old = state.pending[cid]
    if old["filled"] != observed["cumulative_filled"] or old["quantity"] != request["qty"]:
        raise ValueError("actual fill prefix must be applied before terminal processing")
    working = copy.deepcopy(state)
    audit = copy.deepcopy(evidence)
    hold_id = "liability-" + cid
    if hold_id in working.consumed_ids:
        raise ValueError("terminal liability transition already consumed")
    hold = working.pending.pop(cid)
    original = copy.deepcopy(hold)
    hold.update(side="liability_hold", quantity=0, filled=0)
    working.pending[hold_id] = hold
    working.consumed_ids.add(hold_id)
    audit.setdefault("terminal_liability_holds", {})[hold_id] = dict(
        original_client_order_id=cid,
        original_reservation=original,
        journal_snapshot=copy.deepcopy(journal),
        actual_terminal_order=copy.deepcopy(observed_order),
        capture=copy.deepcopy(capture_binding),
        fees_reconciled=False,
        cash_released=0,
    )
    if working.cash_reserved() != state.cash_reserved() or working.cashbook != state.cashbook:
        raise ValueError("terminal processing changed money or positions")
    return working, audit


def abandon_never_attempted(state, fills, fees, evidence, *, cid, journal, observed_at):
    """Release only a positively witnessed pre-dispatch reservation, never an ACK guess."""
    import os

    from open_composer.intraday_runner.source_dispatch_journal import _hash

    witness = evidence.get("dispatch_intents", {}).get(cid)
    row = state.pending.get(cid)
    if (
        not witness
        or witness.get("attempted") is not False
        or row is None
        or witness.get("locally_abandoned") is True
        or row.get("filled") != 0
        or _hash(row) != witness.get("reservation_sha256")
        or any(r.get("client_order_id") == cid for r in (*fills.values(), *fees.values()))
    ):
        raise ValueError("no positive never-attempted unchanged-reservation proof")
    stat = journal.directory.stat()
    if (
        str(journal.directory) != witness["journal_root"]
        or journal.directory.is_symlink()
        or [stat.st_dev, stat.st_ino] != witness["journal_identity"]
        or os.path.lexists(journal._path(cid))
    ):
        raise ValueError("journal identity/attempt unknown; preserve all liabilities")
    if row.get("remaining_funding", []) != row.get("original_funding", []) or row.get(
        "confirmed_fee_funding"
    ):
        raise ValueError("reservation has actual economic use; no local abandonment")
    working, audit = copy.deepcopy(state), copy.deepcopy(evidence)
    sales = {s["id"]: s for s in working.cashbook.sales}
    for part in row.get("remaining_funding", []):
        if part["source"] != "cash":
            sales[part["source"]]["unreserved"] += part["amount"]
    del working.pending[cid]
    # Keep consumed intent forever: abandonment is not permission to retry it.
    audit["dispatch_intents"][cid]["locally_abandoned"] = True
    audit.setdefault("abandoned_local_intents", {})[cid] = dict(
        original_reservation=copy.deepcopy(row),
        proof=copy.deepcopy(witness),
        observed_at=observed_at,
        basis="durable attempted=false plus same retained journal under own locks",
        broker_terminal_claim=False,
        fee_reconciliation_claim=False,
    )
    return working, audit
