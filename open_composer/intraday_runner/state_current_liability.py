"""One fixed STATE current-liability capture by the existing native operator.

No client construction, order/hold transition, historical disposition inference,
timer or retry. A later received result is required before proposing a checkpoint
transition; this module never authorizes it from 404 or an empty open-order page.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import signal
import threading
import time
from datetime import datetime
from datetime import time as wall_time
from decimal import Decimal
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import ACCOUNT
from open_composer.intraday_runner.source_activity_reception import bind
from open_composer.intraday_runner.source_activity_reception import save as immutable_save
from open_composer.intraday_runner.source_dispatch_journal import _ensure_durable_directory
from open_composer.market_sessions import NEW_YORK, us_equity_session_close

TASK = "EXISTING-PAPER-NEXT-SESSION-CONTINUITY-20261026"
CID = "six-53ee69b0f53f4186bf6593b7b133ed0a41d1"
BOOK = "BASE_STATE_BUDGET"
AFTER = "2026-10-19T00:00:00Z"
DIRECTORY = (
    "reports/paper/diagnostics/next-session-continuity-20261026/STATE-current-reconciliation-01"
)
CAPTURE_SECONDS = 60
CALL_SECONDS = 10
PREOPEN_MARGIN_SECONDS = 5


def closed_window(at, remaining):
    """Leave the entire remaining capture budget before the next regular open."""
    local = at.astimezone(NEW_YORK)
    close = us_equity_session_close(local.date())
    if close is None or local.time().replace(tzinfo=None) >= close:
        return True
    opening = datetime.combine(local.date(), wall_time(9, 30), tzinfo=NEW_YORK)
    return (opening - local).total_seconds() > remaining + PREOPEN_MARGIN_SECONDS


def bounded_call(runtime, method, args, permission):
    """Only this synchronous capture changes its existing client's transport.

    The alarm bounds limiter/DNS/connect/read/body waits, including a trickling
    response. Requests' timeout alone does not impose a whole-call wall limit.
    The native service uses the main thread. Never borrow an existing alarm.
    """
    budget = min(CALL_SECONDS, permission())
    if threading.current_thread() is not threading.main_thread() or any(
        signal.getitimer(signal.ITIMER_REAL)
    ):
        raise ValueError("scoped capture deadline unavailable")
    client = runtime.client
    session = client._session
    if any(adapter.max_retries.total != 0 for adapter in session.adapters.values()):
        raise ValueError("capture requires zero transport retries")
    original_request, original_retry = session.request, client._retry
    local_request = session.__dict__.get("request")
    had_local_request = "request" in session.__dict__
    previous_handler = signal.getsignal(signal.SIGALRM)

    def expired(signum, frame):
        raise TimeoutError("fixed current-capture call deadline exceeded")

    def request(http_method, url, **kwargs):
        remaining = permission()  # After the existing limiter, before physical I/O.
        if http_method.upper() != "GET":
            raise ValueError("current capture permits reads only")
        kwargs["timeout"] = min(5, budget, remaining)
        return original_request(http_method, url, **kwargs)

    try:
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, budget)
        client._retry = 0  # A 429 is evidence, never an added SDK sleep/retry.
        session.request = request
        return runtime.call(method, *args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        client._retry = original_retry
        if had_local_request:
            session.request = local_request
        else:
            del session.request


def save(path, value):
    """Use the current sole-owner named floor, without allocated-space credit."""
    root = next(p for p in path.parents if (p / "config/memory-budget.json").exists())
    handoff = json.loads((root / "reports/ops/disk-audit-20261015/handoff.json").read_text())
    floor = handoff["current_finite_scope_commitment_snapshot"][
        "current_complete_required_available_bytes"
    ]
    if type(floor) is not int or floor <= 0:
        raise ValueError("complete current named physical floor unavailable")
    fs = os.statvfs(root)
    encoded = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    maximum_next = ((len(encoded) + fs.f_frsize - 1) // fs.f_frsize + 2) * fs.f_frsize
    if fs.f_bavail * fs.f_frsize < floor + maximum_next:
        raise ValueError("fresh full concurrent write guard refused")
    return immutable_save(path, value)


def plain(value):
    if hasattr(value, "model_dump_json"):
        return json.loads(value.model_dump_json())
    if isinstance(value, list):
        return [plain(row) for row in value]
    return copy.deepcopy(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def number(value):
    if isinstance(value, bool):
        raise ValueError("boolean quantity/cash")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("nonfinite quantity/cash")
    return result


def quantities(positions):
    result = {}
    for row in positions:
        symbol = row["symbol"]
        if symbol in result or row.get("asset_class") != "us_equity":
            raise ValueError("unsupported inventory identity")
        result[symbol] = number(row["qty"])
    return {s: q for s, q in result.items() if q}


def assess(root, state, history, activities, final_account, final_positions, final_open):
    """Reuse the existing receipt receiver, not another account/fill engine."""
    from open_composer.intraday_runner.six_paper_service import CHILD_CAPITAL, CHILDREN, POLICIES
    from scripts.reconcile_six_paper_performance import receive_executions

    expected_books = {p for p in POLICIES if p not in CHILD_CAPITAL} | {
        p + "/" + child for p in CHILD_CAPITAL for child in CHILDREN
    }
    if set(state["books"]) != expected_books:
        raise ValueError("complete six-policy book inventory required")

    if len(history) >= 500 or len(final_open) >= 500:
        raise ValueError("saturated order inventory")
    by_cid = {row["client_order_id"]: row for row in history}
    if len(by_cid) != len(history):
        raise ValueError("duplicate history identity")
    target = state["orders"][CID]
    pending = state["books"][BOOK]["pending"][CID]
    if not (
        target["book"] == BOOK
        and target["symbol"] == "AAPL"
        and target["side"] == "sell"
        and number(target["qty"]) == 4
        and target["status"] == "prepared_unknown_until_queried"
        and pending["side"] == "sell"
        and number(pending["quantity"]) == 4
        and pending["symbol"] == "AAPL"
        and number(pending["limit_price"]) == number(target["limit_price"]) == number("337.81")
        and number(pending["filled"]) == 0
        and not pending["remaining_funding"]
        and not pending["original_funding"]
        and not pending["confirmed_fee_funding"]
    ):
        raise ValueError("target prefix differs; no generic retirement route")
    # Cached observations must agree with CURRENT complete history, not merely
    # the current aggregate quantity after potentially offsetting executions.
    for cid, row in state["orders"].items():
        old = row.get("observation")
        if not old:
            continue
        current = by_cid.get(cid)
        if current is None:
            raise ValueError("known native order missing from current history")
        for key in ["id", "client_order_id", "symbol", "side", "status"]:
            if str(current[key]) != str(old[key]):
                raise ValueError("current order identity/status changed")
        for key in ["qty", "filled_qty"]:
            if number(current[key]) != number(old[key]):
                raise ValueError("current order execution prefix differs")
        if number(current["filled_qty"]) and number(current["filled_avg_price"]) != number(
            old["filled_avg_price"]
        ):
            raise ValueError("current order economic prefix differs")
    fills = [row for row in activities if row.get("activity_type") == "FILL"]
    nonfills = [row["id"] for row in activities if row.get("activity_type") != "FILL"]
    consumed = {}
    executions, orders, owners = receive_executions(
        state, dict(account_hash=ACCOUNT, activities=fills), consumed
    )
    unknown_fills = [row["id"] for row in fills if row["order_id"] not in owners]
    supported = not unknown_fills and not any(not row["detail_complete"] for row in orders)
    owned = {}
    per_book = {}
    for name, rows in executions.items():
        current = {}
        if not rows and any(
            number(lot["quantity"])
            for lots in state["books"][name]["cashbook"]["lots"].values()
            for lot in lots
        ):
            supported = False
        for row in sorted(rows, key=lambda x: (x["time"], x["id"])):
            qty = number(row["quantity"])
            if qty <= 0 or qty != qty.to_integral_value() or row["side"] not in {"buy", "sell"}:
                raise ValueError("unsupported execution units")
            symbol = row["symbol"]
            current[symbol] = current.get(symbol, Decimal(0)) + qty * (
                1 if row["side"] == "buy" else -1
            )
            if current[symbol] < 0:
                supported = False  # Missing opening execution is never a zero basis.
        per_book[name] = {s: q for s, q in current.items() if q}
        for symbol, qty in per_book[name].items():
            owned[symbol] = owned.get(symbol, Decimal(0)) + qty
    actual = quantities(final_positions)
    exact = supported and {s: q for s, q in owned.items() if q} == actual
    state_aapl = sum(
        (
            number(lot["quantity"])
            for lot in state["books"][BOOK]["cashbook"]["lots"].get("AAPL", [])
        ),
        Decimal(0),
    )
    own_aapl_exact = per_book[BOOK].get("AAPL", Decimal(0)) == state_aapl
    cash_reserved = sum(
        (
            number(part["amount"])
            for book in state["books"].values()
            for row in book["pending"].values()
            for part in row.get("remaining_funding", [])
            if part["source"] == "cash"
        ),
        Decimal(0),
    )
    cash_cover = number(final_account["cash"]) >= cash_reserved >= 0
    candidate = (
        exact
        and own_aapl_exact
        and cash_cover
        and not nonfills
        and not final_open
        and CID not in by_cid
    )
    return dict(
        current_quantity_lock_retirement_candidate=candidate,
        historical_submission_disposition="UNKNOWN",
        actual_checkpoint_transition=False,
        target_in_current_history=CID in by_cid,
        current_open_order_count=len(final_open),
        complete_FILL_support=supported,
        unmapped_FILL_ids=unknown_fills,
        non_FILL_ids_requiring_separate_current_liability_interpretation=nonfills,
        confirmed_execution_quantities_match_broker_exact=exact,
        target_book_AAPL_units_match_exact=own_aapl_exact,
        actual_account_cash_covers_recorded_cash_reservations=cash_cover,
        observed_account_cash=str(number(final_account["cash"])),
        preserved_cash_reservations=str(cash_reserved),
        monetary_release_USD="0",
        original_pending_fee_buffer_preserved=True,
        fees_income_settlement_or_netPnL_certified=False,
        consumed_saved_seed_receipts=list(consumed.values()),
        next_boundary=(
            "Actual receipt and a narrow prospective checkpoint transition are required. "
            "No release or old-ID resend here."
        ),
    )


def capture_once(runtime):
    if getattr(runtime, "config", {}).get("current_STATE_reconciliation_capture") != TASK:
        return
    directory = runtime.root / DIRECTORY
    if directory.exists():
        return  # Success, failed and partial attempts all survive without replay.
    if not closed_window(runtime.clock(), CAPTURE_SECONDS):
        return  # Also leave the full finite capture budget before regular open.
    if runtime.state["orders"].get(CID, {}).get("status") != "prepared_unknown_until_queried":
        return
    started = runtime.clock()
    monotonic = time.monotonic()
    receipts = []
    _ensure_durable_directory(directory.parent.absolute())
    directory.mkdir(exist_ok=False)
    save(
        directory / "started.json",
        dict(
            task_id=TASK,
            at=started.isoformat(),
            native_pid=os.getpid(),
            code=bind(Path(__file__)),
            historical_CID=CID,
            read_only=True,
        ),
    )
    result = dict(task_id=TASK, broker_writes=0, book_or_hold_transition=False, receipts=receipts)

    def permission():
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
        remaining = CAPTURE_SECONDS - (time.monotonic() - monotonic)
        if not 0 < remaining <= CAPTURE_SECONDS:
            raise ValueError("finite capture duration exceeded; preserve partial")
        if not closed_window(runtime.clock(), remaining):
            raise ValueError("closed-market capture budget unavailable before open")
        available = (
            int(
                next(
                    row.split()[1]
                    for row in Path("/proc/meminfo").read_text().splitlines()
                    if row.startswith("MemAvailable:")
                )
            )
            * 1024
        )
        if available < 524288000:
            raise ValueError("preserve actual owner500MiB reserve")
        return remaining

    def get(name, method, *args):
        permission()
        intent = save(
            directory / (name + ".intent.json"),
            dict(method=method, args=args, at=runtime.clock().isoformat()),
        )
        try:
            value = plain(bounded_call(runtime, method, args, permission))
        except Exception as exc:
            from alpaca.common.exceptions import APIError

            response = exc.response if isinstance(exc, APIError) else None
            content = response.content if response is not None else None
            save(
                directory / (name + ".error.json"),
                dict(
                    intent=intent,
                    error_type=type(exc).__name__,
                    http_status=response.status_code if response is not None else None,
                    received_body_bytes=len(content) if isinstance(content, bytes) else None,
                    received_body_sha256=hashlib.sha256(content).hexdigest()
                    if isinstance(content, bytes)
                    else None,
                    observed_at=runtime.clock().isoformat(),
                ),
            )
            raise
        if method == "get_account":
            actual_hash = hashlib.sha256(str(value.pop("id")).encode()).hexdigest()
            if actual_hash != ACCOUNT:
                raise ValueError("actual account identity changed")
            value = {
                k: value[k]
                for k in [
                    "status",
                    "currency",
                    "cash",
                    "equity",
                    "buying_power",
                    "trading_blocked",
                    "account_blocked",
                    "trade_suspended_by_user",
                ]
            }
            value["account_hash"] = actual_hash
        body = save(directory / (name + ".body.json"), value)
        receipt = save(
            directory / (name + ".receipt.json"),
            dict(
                intent=intent,
                body=body,
                observed_at=runtime.clock().isoformat(),
                capture_basis=(
                    "SDK-decoded JSON; account identity hashed and fields projected. "
                    "Not original wire bytes."
                ),
            ),
        )
        receipts.append(receipt)
        permission()
        return value

    try:
        permission()
        before = copy.deepcopy(runtime.state)
        before_binding = save(directory / "native-before.json", before)
        age = (
            started
            - datetime.fromisoformat(before["account"]["observed_at"].replace("Z", "+00:00"))
        ).total_seconds()
        if not 0 <= age <= 60:
            raise ValueError("beginning native account observation is not current")
        first = get("clock-before", "get_clock")
        first_stamp = datetime.fromisoformat(str(first["timestamp"]).replace("Z", "+00:00"))
        if (
            first["is_open"]
            or first_stamp.tzinfo is None
            or not 0 <= (runtime.clock() - first_stamp).total_seconds() <= 60
        ):
            raise ValueError("market open; no maintenance capture")
        history = get(
            "history",
            "get",
            "/orders",
            dict(status="all", after=AFTER, limit=500, direction="asc", nested=True),
        )
        if not isinstance(history, list) or len(history) >= 500:
            raise ValueError("order history incomplete/saturated")
        for row in history:
            created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            if (
                created.tzinfo is None
                or not datetime.fromisoformat(AFTER.replace("Z", "+00:00"))
                <= created
                <= runtime.clock()
            ):
                raise ValueError("order history timestamp outside current request window")
        activities, token, seen, ids = [], None, set(), set()
        while True:
            params = dict(after=AFTER, direction="asc", page_size=100)
            if token is not None:
                params["page_token"] = token
            page = get("activities-" + str(len(seen)), "get", "/account/activities", params)
            if not isinstance(page, list):
                raise ValueError("activity page schema differs")
            for row in page:
                if not isinstance(row, dict) or not row.get("id") or row["id"] in ids:
                    raise ValueError("incomplete/duplicate activity identity")
                if row.get("activity_type") == "FILL":
                    stamp = datetime.fromisoformat(row["transaction_time"].replace("Z", "+00:00"))
                    if (
                        stamp.tzinfo is None
                        or not datetime.fromisoformat(AFTER.replace("Z", "+00:00"))
                        <= stamp
                        <= runtime.clock()
                    ):
                        raise ValueError("FILL timestamp outside current request window")
                ids.add(row["id"])
            activities.extend(page)
            if len(page) < 100:
                break
            token = page[-1]["id"]
            if token in seen:
                raise ValueError("nonprogressing activity chain")
            seen.add(token)
        account = get("account-after", "get_account")
        positions = get("positions-after", "get_all_positions")
        opened = get(
            "open-after",
            "get",
            "/orders",
            dict(status="open", limit=500, direction="asc", nested=True),
        )
        last = get("clock-after", "get_clock")
        last_stamp = datetime.fromisoformat(str(last["timestamp"]).replace("Z", "+00:00"))
        if (
            not isinstance(opened, list)
            or len(opened) >= 500
            or last["is_open"]
            or last_stamp.tzinfo is None
            or not 0 <= (runtime.clock() - last_stamp).total_seconds() <= 60
        ):
            raise ValueError("current open-order/clock completeness differs")
        if not (
            account["status"] == "ACTIVE"
            and account["currency"] == "USD"
            and not any(
                account[k]
                for k in ["trading_blocked", "account_blocked", "trade_suspended_by_user"]
            )
        ):
            raise ValueError("account is not active/unblocked USD")
        if before["account"]["account_hash"] != ACCOUNT or number(
            before["account"]["cash"]
        ) != number(account["cash"]):
            raise ValueError("cash/account changed during capture")
        if quantities(list(before["account"]["positions"].values())) != quantities(positions):
            raise ValueError("inventory changed during capture")
        if (
            before["open_orders"] != opened
            or before["position_mismatch"]
            or before["foreign_open_orders"]
        ):
            raise ValueError("current order/reconciliation state differs")
        if digest(before["books"]) != digest(runtime.state["books"]) or digest(
            before["orders"]
        ) != digest(runtime.state["orders"]):
            raise ValueError("native book/order prefix changed")
        result.update(
            status="complete_current_capture_no_transition",
            native_before=before_binding,
            history_rows=len(history),
            activity_rows=len(activities),
            activity_pages=len(seen) + 1,
        )
        try:
            result["assessment"] = assess(
                runtime.root, before, history, activities, account, positions, opened
            )
        except (AssertionError, ValueError, KeyError) as exc:
            result["assessment"] = dict(
                current_quantity_lock_retirement_candidate=False,
                actual_checkpoint_transition=False,
                exact_current_reconciliation_dependency=type(exc).__name__,
            )
    except Exception as exc:
        # Do not expose request headers, arbitrary API/error bodies or credentials.
        result.update(
            status="incomplete_current_capture_retained_no_replay", error_type=type(exc).__name__
        )
    result.update(completed_at=runtime.clock().isoformat(), native_pid=os.getpid())
    binding = save(directory / "result.json", result)
    runtime.event("STATE_current_liability_capture_result", result=binding)
