"""Invented native-capture/receipt fixtures; no real client, account or order."""

import copy
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner import state_current_liability as module
from open_composer.intraday_runner.six_paper_service import CHILD_CAPITAL, CHILDREN, POLICIES

NOW = datetime(2026, 10, 25, 17, tzinfo=UTC)


def fixture():
    names = {p for p in POLICIES if p not in CHILD_CAPITAL} | {
        p + "/" + c for p in CHILD_CAPITAL for c in CHILDREN
    }
    books = {
        n: dict(
            pending={},
            consumed_ids=[],
            fills={},
            fees={},
            cashbook=dict(cash=20000, lots={}),
            evidence={},
        )
        for n in names
    }
    books[module.BOOK].update(
        pending={
            module.CID: dict(
                side="sell",
                symbol="AAPL",
                quantity=4,
                filled=0,
                limit_price=337.81,
                remaining_funding=[],
                original_funding=[],
                confirmed_fee_funding=[],
                fee_buffer_rate=0.001,
            )
        },
        consumed_ids=[module.CID, "new-buy"],
        fills={
            "receipt1": dict(
                client_order_id="new-buy", order_id="provider-buy", quantity=11, price=100
            )
        },
        cashbook=dict(cash=18900, lots={"AAPL": [dict(quantity=11, funded="2026-10-20")]}),
    )
    observation = dict(
        id="provider-buy",
        client_order_id="new-buy",
        symbol="AAPL",
        side="buy",
        qty="11",
        filled_qty="11",
        filled_avg_price="100",
        status="filled",
        filled_at="2026-10-21T14:00:00Z",
        created_at="2026-10-21T13:59:00Z",
    )
    positions = [dict(symbol="AAPL", qty="11", asset_class="us_equity")]
    state = dict(
        books=books,
        orders={
            module.CID: dict(
                book=module.BOOK,
                symbol="AAPL",
                side="sell",
                qty=4,
                limit_price=337.81,
                status="prepared_unknown_until_queried",
            ),
            "new-buy": dict(
                book=module.BOOK,
                symbol="AAPL",
                side="buy",
                qty=11,
                limit_price=100,
                status="filled",
                observation=observation,
            ),
        },
        account=dict(
            account_hash=module.ACCOUNT,
            cash="900000",
            observed_at=NOW.isoformat(),
            positions={"AAPL": positions[0]},
        ),
        open_orders=[],
        foreign_open_orders=[],
        position_mismatch={},
    )
    activities = [
        dict(
            id="activity1",
            activity_type="FILL",
            order_id="provider-buy",
            symbol="AAPL",
            side="buy",
            qty="11",
            price="100",
            transaction_time="2026-10-21T14:00:00Z",
        )
    ]
    account = dict(
        id="actual-fixture-account",
        status="ACTIVE",
        currency="USD",
        cash="900000",
        equity="901100",
        buying_power="900000",
        trading_blocked=False,
        account_blocked=False,
        trade_suspended_by_user=False,
    )
    return state, [observation], activities, account, positions


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    import socket

    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail("No real sockets"))


def assessment(values):
    state, history, activities, account, positions = values
    return module.assess(None, state, history, activities, account, positions, [])


def test_complete_current_prefix_can_support_proposal_without_mutating_unknown_history():
    values = fixture()
    before = copy.deepcopy(values)
    result = assessment(values)
    assert result["current_quantity_lock_retirement_candidate"] is True
    assert result["historical_submission_disposition"] == "UNKNOWN"
    assert not result["actual_checkpoint_transition"]
    assert result["monetary_release_USD"] == "0"
    assert values == before


@pytest.mark.parametrize(
    "change", ["unapplied_fill", "missing_detail", "non_fill", "position", "cash", "target_history"]
)
def test_incomplete_or_conflicting_current_evidence_never_supports_retirement(change):
    values = fixture()
    state, history, activities, account, positions = values
    if change == "unapplied_fill":
        activities.append(dict(activities[0], id="foreign", order_id="unmapped"))
    elif change == "missing_detail":
        activities.clear()
    elif change == "non_fill":
        activities.append(dict(id="fee-unknown", activity_type="FEE"))
    elif change == "position":
        positions[0]["qty"] = "10"
    elif change == "cash":
        account["cash"] = "-1"
    else:
        history.append(dict(history[0], client_order_id=module.CID))
    result = assessment(values)
    assert result["current_quantity_lock_retirement_candidate"] is False
    assert result["actual_checkpoint_transition"] is False


@pytest.mark.parametrize(
    "change", ["filled", "pending_symbol", "money", "missing_book", "history_changed"]
)
def test_wrong_target_or_incomplete_book_prefix_refuses(change):
    values = fixture()
    state, history, *_ = values
    pending = state["books"][module.BOOK]["pending"][module.CID]
    if change == "filled":
        pending["filled"] = 1
    elif change == "pending_symbol":
        pending["symbol"] = "MSFT"
    elif change == "money":
        pending["remaining_funding"] = [dict(source="cash", amount=1)]
    elif change == "missing_book":
        state["books"].pop("H5")
    else:
        history[0] = dict(history[0], filled_qty="10")
    with pytest.raises(ValueError):
        assessment(values)


def native(tmp_path, monkeypatch, *, bad_page=False):
    state, history, acts, account, positions = fixture()
    # Only a private configured label is patched; not an actual account grant.
    monkeypatch.setattr(module, "ACCOUNT", hashlib.sha256(account["id"].encode()).hexdigest())
    state["account"]["account_hash"] = module.ACCOUNT
    hold = tmp_path / "reports/research/control/owner-compute-hold.json"
    hold.parent.mkdir(parents=True)
    hold.write_text(
        json.dumps(
            dict(
                status="research_paused_paper_allowed",
                paper_launch_20min_20261021=dict(
                    necessary_current_paper_input_inference_and_repair_allowed=True
                ),
            )
        )
    )

    # Private writer bypasses only physical admission; production save is tested separately.
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as f:
            json.dump(value, f, default=str)
        return dict(
            path=str(path),
            bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    monkeypatch.setattr(module, "save", save)
    calls = []
    events = []

    def call(method, *args):
        calls.append((method, args))
        if method == "get_clock":
            return dict(is_open=False, timestamp=NOW.isoformat())
        if method == "get_account":
            return copy.deepcopy(account)
        if method == "get_all_positions":
            return copy.deepcopy(positions)
        assert method == "get"
        if args[0] == "/orders":
            return copy.deepcopy(history if args[1]["status"] == "all" else [])
        assert args[0] == "/account/activities"
        return dict(unusable=True) if bad_page else copy.deepcopy(acts)

    return (
        SimpleNamespace(
            config=dict(current_STATE_reconciliation_capture=module.TASK),
            root=tmp_path,
            state=state,
            clock=lambda: NOW,
            allowed=lambda: True,
            client=SimpleNamespace(
                _retry=3,
                _session=SimpleNamespace(adapters={}, request=lambda *a, **kw: None),
            ),
            call=call,
            event=lambda *a, **k: events.append((a, k)),
        ),
        calls,
        events,
    )


def test_one_native_capture_reuses_client_and_leaves_all_books_and_orders_exact(
    tmp_path, monkeypatch
):
    runtime, calls, events = native(tmp_path, monkeypatch)
    before = copy.deepcopy(runtime.state)
    module.capture_once(runtime)
    result = json.loads((tmp_path / module.DIRECTORY / "result.json").read_text())
    assert result["status"] == "complete_current_capture_no_transition"
    assert result["assessment"]["current_quantity_lock_retirement_candidate"] is True
    assert runtime.state == before and len(events) == 1
    count = len(calls)
    module.capture_once(runtime)
    assert len(calls) == count
    assert all(
        name in {"get_clock", "get", "get_account", "get_all_positions"} for name, _ in calls
    )
    assert not any("by_client" in str(args) for _, args in calls)


def test_failed_capture_stays_partial_and_does_not_replay(tmp_path, monkeypatch):
    runtime, calls, _ = native(tmp_path, monkeypatch, bad_page=True)
    before = copy.deepcopy(runtime.state)
    module.capture_once(runtime)
    result = json.loads((tmp_path / module.DIRECTORY / "result.json").read_text())
    assert result["status"] == "incomplete_current_capture_retained_no_replay"
    count = len(calls)
    module.capture_once(runtime)
    assert len(calls) == count
    assert runtime.state == before


def test_current_pause_refuses_before_any_native_GET(tmp_path, monkeypatch):
    runtime, calls, _ = native(tmp_path, monkeypatch)
    p = tmp_path / "reports/research/control/owner-compute-hold.json"
    d = json.loads(p.read_text())
    d["status"] = "owner_all_work_paused_including_paper"
    p.write_text(json.dumps(d))
    module.capture_once(runtime)
    assert calls == []


def test_production_writer_refuses_incomplete_physical_headroom(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/memory-budget.json").write_text("{}")
    p = tmp_path / "reports/ops/disk-audit-20261015/handoff.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(
            dict(
                current_finite_scope_commitment_snapshot=dict(
                    current_complete_required_available_bytes=10000
                )
            )
        )
    )
    monkeypatch.setattr(
        module.os, "statvfs", lambda root: SimpleNamespace(f_frsize=4096, f_bavail=0)
    )
    dest = tmp_path / "reports/refused.json"
    with pytest.raises(ValueError, match="full concurrent"):
        module.save(dest, dict(payload="private"))
    assert not dest.exists()


def test_already_resolved_native_identity_needs_no_extra_capture(tmp_path, monkeypatch):
    runtime, calls, _ = native(tmp_path, monkeypatch)
    runtime.state["orders"][module.CID]["status"] = "expired"
    module.capture_once(runtime)
    assert calls == [] and not (tmp_path / module.DIRECTORY).exists()


def test_owner_memory_reserve_refuses_before_native_GET(tmp_path, monkeypatch):
    from pathlib import Path

    runtime, calls, _ = native(tmp_path, monkeypatch)
    original = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, *a, **kw: (
            "MemAvailable: 1 kB\n" if str(path) == "/proc/meminfo" else original(path, *a, **kw)
        ),
    )
    module.capture_once(runtime)
    assert calls == []
    result = json.loads((tmp_path / module.DIRECTORY / "result.json").read_text())
    assert result["status"] == "incomplete_current_capture_retained_no_replay"


@pytest.mark.parametrize("second", [55, 115])
def test_preopen_budget_skips_without_an_attempt(tmp_path, monkeypatch, second):
    from datetime import timedelta

    runtime, calls, _ = native(tmp_path, monkeypatch)
    # 09:28:55 and 09:29:55 New York: not enough for 60s plus margin.
    runtime.clock = lambda: datetime(2026, 10, 26, 13, 28, tzinfo=UTC) + timedelta(seconds=second)
    module.capture_once(runtime)
    assert calls == [] and not (tmp_path / module.DIRECTORY).exists()


def test_market_guard_after_limiter_refuses_before_physical_IO(tmp_path, monkeypatch):
    runtime, calls, _ = native(tmp_path, monkeypatch)
    wall = [datetime(2026, 10, 26, 13, 28, 50, tzinfo=UTC)]
    runtime.clock = lambda: wall[0]
    runtime.state["account"]["observed_at"] = wall[0].isoformat()
    physical = []
    runtime.client._session.request = lambda *a, **kw: physical.append((a, kw))

    def delayed_limiter(method, *args):
        calls.append((method, args))
        wall[0] = datetime(2026, 10, 26, 13, 30, 1, tzinfo=UTC)
        return runtime.client._session.request("GET", "https://private.invalid/v2/clock")

    runtime.call = delayed_limiter
    module.capture_once(runtime)
    assert [name for name, _ in calls] == ["get_clock"] and physical == []
    result = json.loads((tmp_path / module.DIRECTORY / "result.json").read_text())
    assert result["status"] == "incomplete_current_capture_retained_no_replay"
    count = len(calls)
    module.capture_once(runtime)
    assert len(calls) == count  # Failed one-use prefix remains final.


def test_stale_closed_clock_cannot_start_history_after_open(tmp_path, monkeypatch):
    runtime, calls, _ = native(tmp_path, monkeypatch)
    wall = [datetime(2026, 10, 26, 13, 28, 50, tzinfo=UTC)]
    runtime.clock = lambda: wall[0]
    runtime.state["account"]["observed_at"] = wall[0].isoformat()

    def slow_clock(method, *args):
        calls.append((method, args))
        wall[0] = datetime(2026, 10, 26, 13, 30, 5, tzinfo=UTC)
        return dict(is_open=False, timestamp="2026-10-26T13:29:55Z")

    runtime.call = slow_clock
    before = copy.deepcopy(runtime.state)
    module.capture_once(runtime)
    assert [name for name, _ in calls] == ["get_clock"]
    assert runtime.state == before


def test_real_alarm_bounds_blocked_wait_and_restores_same_client(monkeypatch):
    import signal
    import threading
    import time

    session = SimpleNamespace(adapters={}, request=lambda *a, **kw: None)
    client = SimpleNamespace(_session=session, _retry=3)
    original = session.request
    handler = signal.getsignal(signal.SIGALRM)
    runtime = SimpleNamespace(client=client, call=lambda *a: threading.Event().wait(2))
    monkeypatch.setattr(module, "CALL_SECONDS", 0.03)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="deadline exceeded"):
        module.bounded_call(runtime, "get_clock", (), lambda: 60)
    assert time.monotonic() - started < 1
    assert client._retry == 3 and session.request is original
    assert signal.getsignal(signal.SIGALRM) == handler
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)


@pytest.mark.parametrize("status", [200, 429])
def test_actual_SDK_request_tail_gets_timeout_zero_retries_then_restores(monkeypatch, status):
    from types import MethodType

    import requests
    from alpaca.common.exceptions import APIError
    from alpaca.common.rest import RESTClient

    physical = []
    response = requests.Response()
    response.status_code = status
    response._content = b'{"private":true}'
    session = SimpleNamespace(adapters={})
    client = SimpleNamespace(
        _session=session,
        _retry=3,
        _retry_wait=3,
        _retry_codes=[429],
        _base_url="https://paper-api.alpaca.markets",
        _api_version="v2",
        _get_default_headers=lambda: {},
    )

    def request(method, url, **kwargs):
        physical.append((method, kwargs["timeout"], client._retry))
        return response

    session.request = request
    # Actual installed methods; no SDK client constructor or network transport.
    client._request = MethodType(RESTClient._request, client)
    client._one_request = MethodType(RESTClient._one_request, client)
    runtime = SimpleNamespace(client=client, call=lambda *a: client._request("GET", "/clock"))
    if status == 200:
        assert module.bounded_call(runtime, "get_clock", (), lambda: 60) == {"private": True}
    else:
        with pytest.raises(APIError):
            module.bounded_call(runtime, "get_clock", (), lambda: 60)
    assert physical == [("GET", 5, 0)]
    assert client._retry == 3 and session.request is request
