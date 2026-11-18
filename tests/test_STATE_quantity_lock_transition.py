"""The retired October STATE share lock and its late-order facts; no client."""

import copy
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner import six_paper_service as service_module
from open_composer.intraday_runner import state_quantity_lock_transition as module
from open_composer.intraday_runner.six_paper_service import SixPaperService

NOW = datetime(2026, 10, 25, 18, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    monkeypatch.setattr(socket.socket, "connect", lambda *a, **kw: pytest.fail("No transport"))


def retired_state():
    """Native state after the completed 2026-10-26 share-lock retirement."""
    pending = dict(
        side="liability_hold",
        symbol="AAPL",
        quantity=0,
        filled=0,
        limit_price=337.81,
        due="2026-10-22",
        fee_buffer_rate=0.001,
        remaining_funding=[],
        original_funding=[],
        confirmed_fee_funding=[],
    )
    order = dict(
        book=module.BOOK,
        symbol="AAPL",
        side="sell",
        qty=4,
        status="prepared_unknown_until_queried",
        limit_price=337.81,
        last_query_failure={"matching_observations": 7},
    )
    marker = dict(
        kind=module.KIND,
        historical_submission_disposition="UNKNOWN",
        retired_share_quantity=4,
        monetary_release_USD="0",
        original_pending=dict(pending, side="sell", quantity=4),
        original_order=copy.deepcopy(order),
        final_fees_or_settlement_certified=False,
    )
    order["current_quantity_lock_reconciliation"] = copy.deepcopy(marker)
    return dict(
        books={
            module.BOOK: dict(
                pending={module.CID: pending},
                evidence={
                    "risk": {"HWM": "20k"},
                    "service_current_quantity_reconciliations": {module.CID: marker},
                },
                cashbook={"lots": {"AAPL": [{"quantity": 11}]}},
                consumed_ids=[module.CID],
                fills={},
                fees={},
            ),
        },
        orders={module.CID: order},
    )


def test_only_the_marked_order_is_retired():
    state = retired_state()
    record = state["orders"][module.CID]
    assert module.retired(module.CID, record)
    assert not module.retired("some-other-ID", record)
    assert not module.retired(module.CID, dict(record, current_quantity_lock_reconciliation=True))
    assert not module.retired(module.CID, {})


@pytest.mark.parametrize("change", ["working", "fill", "wrong_quantity"])
def test_late_actual_conflict_is_retained_without_fill_or_hold_mutation(change):
    after = retired_state()
    original_books = copy.deepcopy(after["books"])
    observed = dict(
        client_order_id=module.CID,
        symbol="AAPL",
        side="sell",
        qty="4",
        status="expired",
        filled_qty="0",
    )
    observed.update(
        {"status": "new"}
        if change == "working"
        else {"filled_qty": "4"}
        if change == "fill"
        else {"qty": "5"}
    )
    runtime = SimpleNamespace(
        state=after,
        clock=lambda: NOW,
        save=lambda: None,
        call=lambda *a: observed,
        event=lambda *a, **kw: None,
    )
    SixPaperService.sync_orders(runtime)
    blocker = after["orders"][module.CID]["current_quantity_lock_conflict"]
    assert blocker["blocking"] is True
    assert json.loads(blocker["raw_observation_json"]) == observed
    assert after["orders"][module.CID]["status"] == "prepared_unknown_until_queried"
    assert after["books"] == original_books


def test_late_conflict_blocks_STATE_before_risk_or_order_mutation():
    after = retired_state()
    after["orders"][module.CID]["current_quantity_lock_conflict"] = {"status": "new"}
    runtime = SimpleNamespace(state=after, target_books=lambda *a: [(module.BOOK, {}, 20000, 0.25)])
    original = copy.deepcopy(after)
    with pytest.raises(ValueError, match="focused reconciliation"):
        SixPaperService.operate(runtime, module.BOOK, {}, {}, NOW, new_risk=True)
    assert after == original


def matching_late_order():
    return dict(
        id="provider-late",
        client_order_id=module.CID,
        symbol="AAPL",
        side="sell",
        qty="4",
        filled_qty="0",
        limit_price="337.81",
        type="limit",
        time_in_force="day",
        status="expired",
    )


def late_runtime(tmp_path, after, observed):
    path = tmp_path / "private-native.json"
    runtime = SimpleNamespace(
        state=after,
        root=tmp_path,
        clock=lambda: NOW,
        event=lambda *a, **kw: None,
        call=lambda *a: observed,
        target_books=lambda *a: [(module.BOOK, {}, 20000, 0.25)],
    )
    runtime.save = lambda: service_module.write_state(path, runtime.state)
    return runtime, path


@pytest.mark.parametrize(
    "change",
    [
        "limit",
        "type",
        "TIF",
        "filled_zero",
        "missing_id",
        "changed_id",
        "empty",
        "not_object",
        "nonfinite",
    ],
)
def test_full_late_conflicts_are_durable_typed_and_preserve_prior(tmp_path, monkeypatch, change):
    after = retired_state()
    observed = matching_late_order()
    if change == "limit":
        observed["limit_price"] = "337.82"
    elif change == "type":
        observed["type"] = "market"
    elif change == "TIF":
        observed["time_in_force"] = "gtc"
    elif change == "filled_zero":
        observed["status"] = "filled"
    elif change == "missing_id":
        observed.pop("id")
    elif change == "changed_id":
        after["orders"][module.CID]["observation"] = dict(observed, id="first-provider-id")
    elif change == "empty":
        observed = {}
    elif change == "not_object":
        observed = None
    else:
        observed["qty"] = float("nan")
    before = copy.deepcopy(after)
    runtime, path = late_runtime(tmp_path, after, observed)
    SixPaperService.sync_orders(runtime)
    saved = json.loads(path.read_text())
    blocker = saved["orders"][module.CID].pop("current_quantity_lock_conflict")
    assert blocker["blocking"] is True and blocker["kind"] == "retired_STATE_order_conflict_v1"
    assert blocker["raw_observation_json"] == json.dumps(observed, sort_keys=True, default=str)
    assert saved == before  # No prior observation/status/book mutation before classification.
    with pytest.raises(ValueError, match="focused reconciliation"):
        SixPaperService.operate(runtime, module.BOOK, {}, {}, NOW, new_risk=True)


def test_full_matching_zero_terminal_follows_unchanged_path_without_money_release(
    tmp_path, monkeypatch
):
    after = retired_state()
    original_books = copy.deepcopy(after["books"])
    observed = matching_late_order()
    runtime, path = late_runtime(tmp_path, after, observed)
    monkeypatch.setattr(
        service_module,
        "restore",
        lambda *a: (
            SimpleNamespace(pending=after["books"][module.BOOK]["pending"]),
            {},
            {},
            after["books"][module.BOOK]["evidence"],
        ),
    )
    monkeypatch.setattr(
        service_module,
        "snapshot",
        lambda *a, **kw: copy.deepcopy(original_books[module.BOOK]),
    )
    SixPaperService.sync_orders(runtime)
    saved = json.loads(path.read_text())
    assert saved["orders"][module.CID]["status"] == "expired"
    assert saved["orders"][module.CID]["observation"] == observed
    assert "current_quantity_lock_conflict" not in saved["orders"][module.CID]
    assert saved["books"] == original_books
