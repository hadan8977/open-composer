"""One received current STATE share-lock transition, without broker transport.

Historical submission remains UNKNOWN. No money/fee reservation is released;
the full original row and consumed identity remain in the native checkpoint.
"""

from __future__ import annotations

import copy
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from open_composer.intraday_runner import state_current_liability as capture

TASK, CID, BOOK = capture.TASK, capture.CID, capture.BOOK
BASE = "reports/paper/diagnostics/next-session-continuity-20261026/"
RESULT_SHA = "e31ef242fc78da528cbd0bb2cf7596622793576b8b26b9b7c892d52e4b4c63b0"
BASIS_REVIEW_SHA = "a8e3e62a36950b8faf14778586c7d3576021438f52a340770c883e8f9c00c6f8"
IMPLEMENTATION_REVIEW = BASE + "independent-current-quantity-lock-transition-M2-review-93af.json"
OUTPUT = BASE + "STATE-current-quantity-lock-transition-01"
DEADLINE = datetime(2026, 10, 26, 0, 20, tzinfo=UTC)
KIND = "received_current_STATE_share_lock_retirement_v1"


def receive(binding):
    path = Path(binding["path"])
    item = path.lstat()
    if path != path.resolve() or not stat.S_ISREG(item.st_mode) or item.st_nlink != 1:
        raise ValueError("exact regular evidence path required")
    if capture.bind(path) != binding:
        raise ValueError("received evidence binding differs")
    return json.loads(path.read_text())


def basis(root):
    """Reuse accepted accounting/quantity reception; do not replay its engine."""
    review_path = root / BASE / "independent-actual-current-reconciliation-review-93af.json"
    review_binding = capture.bind(review_path)
    if review_binding["sha256"] != BASIS_REVIEW_SHA:
        raise ValueError("exact current quantity interpretation absent")
    review = receive(review_binding)
    if not (
        review["independent"] is True
        and review["task_id"] == TASK
        and review["actual_current_capture_result_accepted"] is True
        and review["current_quantity_lock_retirement_definition_accepted"] is True
        and review["target"]["sha256"] == RESULT_SHA
    ):
        raise ValueError("current capture/quantity interpretation unaccepted")
    result = receive(review["target"])
    if result["status"] != "complete_current_capture_no_transition":
        raise ValueError("current capture incomplete")
    # The exact eight chains and typed seven fee rows were independently received.
    # Re-receive their immutable bytes rather than regenerate account arithmetic.
    for row in result["receipts"]:
        receipt = receive(row)
        receive(receipt["intent"])
        receive(receipt["body"])
    captured = receive(result["native_before"])
    return captured, review["target"], review_binding


def implementation(root):
    """Actual same-peer receipt must bind the exact installed candidate files."""
    path = root / IMPLEMENTATION_REVIEW
    binding = capture.bind(path)
    review = receive(binding)
    if not (
        review["task_id"] == TASK
        and review["independent"] is True
        and review["reviewer"] == "93af0483-230a-4632-8b48-c63cd53a01f7"
        and review["implementation_accepted"] is True
        and review["current_quantity_lock_transition_implementation_accepted"] is True
    ):
        raise ValueError("exact quantity transition implementation unaccepted")
    manifest = receive(review["target"])
    if manifest["task_id"] != TASK or manifest["actual_capture_result"]["sha256"] != RESULT_SHA:
        raise ValueError("implementation receives another current source")
    for relative in (
        "open_composer/intraday_runner/six_paper_service.py",
        "open_composer/intraday_runner/state_quantity_lock_transition.py",
        "reports/research/program/paper-launch-20min-20261021/service-config.json",
    ):
        rows = [row for row in manifest["candidate"] if row["path"].endswith("/" + relative)]
        if len(rows) != 1 or capture.bind(root / relative)["sha256"] != rows[0]["sha256"]:
            raise ValueError("loaded candidate predecessor/code/config differs")
    return binding


def orders_prefix(orders):
    return {
        cid: {k: v for k, v in row.items() if k not in {"last_query_failure", "query_error"}}
        for cid, row in orders.items()
    }


def require_same_prefix(current, captured):
    for key in ("books", "baseline", "cycles", "parent_risk"):
        if current.get(key) != captured.get(key):
            raise ValueError("current economic sibling/book/risk prefix changed")
    if orders_prefix(current["orders"]) != orders_prefix(captured["orders"]):
        raise ValueError("current order execution/status prefix changed")
    if (
        current["open_orders"]
        or current["foreign_open_orders"]
        or current["position_mismatch"]
        or current["account"]["account_hash"] != captured["account"]["account_hash"]
        or capture.number(current["account"]["cash"]) != capture.number(captured["account"]["cash"])
        or capture.quantities(list(current["account"]["positions"].values()))
        != capture.quantities(list(captured["account"]["positions"].values()))
    ):
        raise ValueError("current account/order/share liability prefix changed")


def retired(cid, record):
    """An explicit current quantity fact, never a fabricated terminal status."""
    proof = record.get("current_quantity_lock_reconciliation", {})
    if not isinstance(proof, dict):
        return False
    return bool(
        cid == CID
        and record.get("book") == BOOK
        and record.get("symbol") == "AAPL"
        and record.get("side") == "sell"
        and record.get("qty") == 4
        and proof.get("kind") == KIND
        and proof.get("historical_submission_disposition") == "UNKNOWN"
        and proof.get("capture_result", {}).get("sha256") == RESULT_SHA
        and proof.get("quantity_interpretation", {}).get("sha256") == BASIS_REVIEW_SHA
        and proof.get("retired_share_quantity") == 4
        and proof.get("monetary_release_USD") == "0"
    )


def receive_retired_late_order(cid, record, observed):
    """Only full matching zero-fill terminal facts may enter the legacy path."""
    from open_composer.intraday_runner.source_dispatch_journal import classify_own_order

    if not isinstance(observed, dict):
        raise ValueError("late order observation is not an object")
    original = record["current_quantity_lock_reconciliation"]["original_order"]
    for key in ("book", "symbol", "side", "qty", "limit_price"):
        if record[key] != original[key]:
            raise ValueError("retained original request differs from current order")
    request = dict(
        client_order_id=cid,
        symbol=original["symbol"],
        side=original["side"],
        qty=original["qty"],
        limit_price=original["limit_price"],
        type="limit",
        time_in_force="day",
    )
    fact = classify_own_order(request, observed)
    for prior in (original.get("observation"), record.get("observation")):
        if prior is not None and (
            not isinstance(prior, dict) or prior.get("id") != fact["broker_order_id"]
        ):
            raise ValueError("late broker identity differs from received identity")
    if not fact["terminal_observed"] or fact["cumulative_filled"] != 0:
        raise ValueError("late active or executed order conflicts with retired share lock")
    return fact


def successor(current, captured, proof):
    require_same_prefix(current, captured)
    after = copy.deepcopy(current)
    book = after["books"][BOOK]
    row = book["pending"][CID]
    if not (
        row["side"] == "sell"
        and row["symbol"] == "AAPL"
        and row["quantity"] == 4
        and row["filled"] == 0
        and row["limit_price"] == 337.81
        and not row["remaining_funding"]
        and not row["original_funding"]
        and not row["confirmed_fee_funding"]
        and CID in book["consumed_ids"]
        and after["orders"][CID]["status"] == "prepared_unknown_until_queried"
    ):
        raise ValueError("exact unfilled unfunded four-share sell lock required")
    marker = dict(
        proof,
        kind=KIND,
        historical_submission_disposition="UNKNOWN",
        retired_share_quantity=4,
        monetary_release_USD="0",
        original_pending=copy.deepcopy(row),
        original_order=copy.deepcopy(after["orders"][CID]),
        final_fees_or_settlement_certified=False,
    )
    row.update(side="liability_hold", quantity=0)
    book["evidence"].setdefault("service_current_quantity_reconciliations", {})[CID] = marker
    after["orders"][CID]["current_quantity_lock_reconciliation"] = copy.deepcopy(marker)
    if not retired(CID, after["orders"][CID]):
        raise ValueError("received typed quantity marker incomplete")
    return after


def require_current(runtime):
    if runtime.clock() >= DEADLINE or not capture.closed_window(runtime.clock(), 5):
        raise ValueError("received current-prefix transition window ended")
    hold = json.loads(
        (runtime.root / "reports/research/control/owner-compute-hold.json").read_text()
    )
    if not (
        runtime.allowed()
        and not str(hold.get("status", "")).startswith("owner_all_work_paused")
        and hold.get("paper_launch_20min_20261021", {}).get(
            "necessary_current_paper_input_inference_and_repair_allowed"
        )
        is True
    ):
        raise ValueError("current paper maintenance authority unavailable")
    if (
        capture.number(
            next(
                row.split()[1]
                for row in Path("/proc/meminfo").read_text().splitlines()
                if row.startswith("MemAvailable:")
            )
        )
        * 1024
        < 524288000
    ):
        raise ValueError("preserve owner500MiB reserve")
    observed = datetime.fromisoformat(
        runtime.state["account"]["observed_at"].replace("Z", "+00:00")
    )
    if not 0 <= (runtime.clock() - observed).total_seconds() <= 60:
        raise ValueError("current native account prefix not fresh")


def transition_once(runtime):
    if runtime.config.get("current_STATE_quantity_lock_transition") != TASK:
        return
    directory = runtime.root / OUTPUT
    if directory.exists() or retired(CID, runtime.state["orders"].get(CID, {})):
        return  # Preserve every completed/failed/partial prefix without replay.
    if runtime.clock() >= DEADLINE or not capture.closed_window(runtime.clock(), 5):
        return
    require_current(runtime)
    captured, result_binding, basis_review = basis(runtime.root)
    code_review = implementation(runtime.root)
    before = copy.deepcopy(runtime.state)
    proof = dict(
        capture_result=result_binding,
        quantity_interpretation=basis_review,
        implementation_review=code_review,
        applied_at=runtime.clock().isoformat(),
    )
    after = successor(before, captured, proof)
    # Immutable successor/intent precede the existing atomic native checkpoint.
    require_current(runtime)
    capture._ensure_durable_directory(directory.parent.absolute())
    directory.mkdir(exist_ok=False)
    capture.save(directory / "prepared-successor.json", after)
    capture.save(
        directory / "intent.json",
        dict(
            task_id=TASK,
            native_pid=os.getpid(),
            before_books_sha256=capture.digest(before["books"]),
            original_order=before["orders"][CID],
            original_pending=before["books"][BOOK]["pending"][CID],
            proof=proof,
            source_code=capture.bind(Path(__file__)),
            broker_writes=0,
        ),
    )
    # Charge the full fresh named floor plus the atomic native-state allocation.
    handoff = json.loads(
        (runtime.root / "reports/ops/disk-audit-20261015/handoff.json").read_text()
    )
    floor = handoff["current_finite_scope_commitment_snapshot"][
        "current_complete_required_available_bytes"
    ]
    fs = os.statvfs(runtime.root)
    size = len((json.dumps(after, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
    if type(floor) is not int or floor <= 0 or fs.f_bavail * fs.f_frsize < floor + size + 16384:
        raise ValueError("fresh complete atomic checkpoint capacity refused")
    require_current(runtime)
    runtime.state = after
    try:
        runtime.save()
    except Exception:
        # If the atomic publication completed before an error, retain exactly
        # that published successor; never repeat or undo it from a partial log.
        runtime.state = (
            after
            if (runtime.path.exists() and json.loads(runtime.path.read_text()) == after)
            else before
        )
        raise
    result = capture.save(
        directory / "result.json",
        dict(
            task_id=TASK,
            native_pid=os.getpid(),
            completed_at=runtime.clock().isoformat(),
            state_after=capture.bind(runtime.path),
            retired_share_quantity=4,
            monetary_release_USD="0",
            historical_submission_disposition="UNKNOWN",
            actual_quantity_lock_transition=True,
            broker_writes=0,
            proof=proof,
        ),
    )
    runtime.event("STATE_current_quantity_lock_retired", result=result)
