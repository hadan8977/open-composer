"""Invented offline current-policy cases; never account/order readiness evidence."""

import ast
import copy
import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import requests

from open_composer.intraday_runner import source_bounded_gateway as old_gateway
from open_composer.intraday_runner.current_initialization_controls import (
    ACCOUNT,
    DAY,
    NAMESPACE,
    limit_price,
    receive_observation,
    require_phase,
    risk_transition,
    winddown,
)
from open_composer.intraday_runner.current_initialization_dispatch import (
    CurrentBoundedGateway,
    CurrentDispatchJournal,
)
from open_composer.intraday_runner.source_activity_reception import bind

START = datetime(2026, 10, 20, tzinfo=UTC)
END = datetime(2026, 11, 14, tzinfo=UTC)
NOW = datetime(2026, 10, 20, 13, 40, tzinfo=UTC)


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("offline rehearsal forbids actual network")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)


@pytest.mark.parametrize("mark", ["1", "10.01", "100.01", "235.789"])
def test_sell_tick_never_violates_50bp(mark):
    p = Decimal(mark)
    value = limit_price(p, exit_order=True)
    assert value >= p * Decimal(".995") and value % Decimal(".01") == 0
    assert limit_price(p) <= p


@pytest.mark.parametrize("mark", [".99", "0", "-1", "nan", "Infinity", None, True])
def test_bad_mark_refuses(mark):
    with pytest.raises(ValueError):
        limit_price(mark, exit_order=True)


@pytest.mark.parametrize(
    "phase,offset,ok",
    [
        ("buy", 0, True),
        ("buy", 59.999, True),
        ("buy", 60, False),
        ("buy", -0.001, False),
        ("cancel", 1200, True),
        ("cancel", 1500, False),
        ("reconcile", 23100, True),
    ],
)
def test_finite_phase_boundary(phase, offset, ok):
    if ok:
        require_phase(NOW + timedelta(seconds=offset), phase, START, END)
    else:
        with pytest.raises(ValueError):
            require_phase(NOW + timedelta(seconds=offset), phase, START, END)


def observation():
    return dict(
        started_at=(NOW - timedelta(seconds=2)).isoformat(),
        oldest_response_at=(NOW - timedelta(seconds=2)).isoformat(),
        last_response_at=(NOW - timedelta(seconds=1)).isoformat(),
        completed_at=NOW.isoformat(),
        started_monotonic=10,
        completed_monotonic=12,
        account_hash=ACCOUNT,
        checkpoint_hash="head",
        currency="USD",
        account_status="ACTIVE",
        trading_blocked=False,
        account_blocked=False,
        trade_suspended=False,
        positions_complete=True,
        orders_complete=True,
        activities_complete=True,
        cash_reconciled=True,
        actions_complete=True,
        fees_complete=True,
        units_reconciled=True,
        holdings=[],
        own_cash="20000",
        trade_receivables="0",
        valued_rights="0",
        purchase_payables="0",
        fee_liabilities="0",
        other_liabilities="0",
        unborrowed_available="20000",
        own_nav="20000",
    )


def test_complete_cash_observation_is_not_exchange_time():
    o = receive_observation(
        observation(), now=NOW, now_monotonic=12, account_hash=ACCOUNT, checkpoint_hash="head"
    )
    assert o["verified_nav"] == "20000"


@pytest.mark.parametrize(
    "field,value",
    [
        ("fees_complete", "unknown"),
        ("units_reconciled", 1),
        ("actions_complete", None),
        ("trade_suspended", None),
        ("own_cash", "NaN"),
        ("account_hash", "b" * 64),
        ("checkpoint_hash", "old"),
        ("completed_monotonic", 30),
        ("oldest_response_at", "2026-10-20T13:39:40+00:00"),
        ("completed_at", "2026-10-20T13:40:01+00:00"),
        ("completed_at", "2026-10-20T13:40:00"),
    ],
)
def test_observation_fail_closed(field, value):
    o = observation()
    o[field] = value
    with pytest.raises((ValueError, TypeError)):
        receive_observation(
            o, now=NOW, now_monotonic=12, account_hash=ACCOUNT, checkpoint_hash="head"
        )


def test_stale_mark_and_missing_holding_block():
    o = observation()
    o["holdings"] = [
        dict(symbol="AAPL", quantity=2, owned=True, current_price="1", market_value="3")
    ]
    with pytest.raises(ValueError):
        receive_observation(
            o, now=NOW, now_monotonic=12, account_hash=ACCOUNT, checkpoint_hash="head"
        )
    with pytest.raises(ValueError):
        receive_observation(
            observation(),
            now=NOW + timedelta(seconds=16),
            now_monotonic=28,
            account_hash=ACCOUNT,
            checkpoint_hash="head",
        )


def risk():
    return dict(
        initial_capital="10000",
        high_water="24000",
        day=NOW.date().isoformat(),
        day_open_nav="22000",
        halted=False,
        killed=False,
    )


def test_separate_daily_highwater_and_initial_capital():
    p = risk()
    o = observation()
    o["verified_nav"] = "20900"
    r = risk_transition(p, o, now=NOW)
    assert r["halted"] and not r["killed"]
    o["verified_nav"] = "18000"
    r = risk_transition(p, o, now=NOW)
    assert r["killed"] and r["high_water"] == "24000" and p == risk()


@pytest.mark.parametrize("latch", [None, "unknown", 0, 1])
def test_unknown_latches_not_cleared(latch):
    p = risk()
    p["killed"] = latch
    with pytest.raises(ValueError):
        risk_transition(p, dict(verified_nav="24000"), now=NOW)


def test_actual_opening_clock_no_reset():
    p = risk()
    p["day"] = "2026-10-16"
    o = observation()
    o.update(
        verified_nav="20000",
        started_at="2026-10-20T13:30:00+00:00",
        completed_at="2026-10-20T13:30:02+00:00",
    )
    r = risk_transition(p, o, now=NOW, opening=True)
    assert r["day_open_nav"] == "20000"
    with pytest.raises(ValueError):
        risk_transition(r, o, now=NOW, opening=True)
    o["completed_at"] = "2026-10-20T13:31:00+00:00"
    with pytest.raises(ValueError):
        risk_transition(p, o, now=NOW, opening=True)


def test_winddown_before_expiry_and_early_close():
    day, a, b = winddown(END)
    assert str(day) == "2026-11-13" and a < b < END
    require_phase(a, "exit", START, END)
    with pytest.raises(ValueError):
        require_phase(END, "exit", START, END)


@pytest.fixture
def transport(tmp_path, monkeypatch):
    monkeypatch.setattr(old_gateway, "_require_verified_paper_client", lambda c: None)
    calls = []
    clock = [NOW]

    class Client:
        def __init__(self):
            self._session = requests.Session()
            self._retry = 5
            self.delay = 0
            self.mutate = False
            self._session.request = lambda method, url, **kw: (
                calls.append((method, url, kw)) or dict(id="invented", status="new")
            )

        def submit_order(self, order):
            clock[0] += timedelta(seconds=self.delay)
            payload = order.to_request_fields()
            if self.mutate:
                payload["qty"] = "999"
            return self._session.request(
                "POST", "https://paper-api.alpaca.markets/v2/orders", json=payload
            )

    client = Client()
    journal = CurrentDispatchJournal(tmp_path / "journal")
    cid = f"{NAMESPACE}-{DAY:%m%d}-buy-AAPL"
    reservation = dict(side="buy", symbol="AAPL", quantity=2, filled=0, limit_price=10.0)
    req = dict(
        client_order_id=cid,
        symbol="AAPL",
        side="buy",
        qty=2,
        type="limit",
        time_in_force="day",
        limit_price=10.0,
        execution_day=DAY.isoformat(),
        reference_day="2026-10-19",
        reference_price=10.009,
        reference_valid=True,
        reservation=reservation,
        cleanup=False,
        killed=False,
    )
    signal = tmp_path / "signal.json"
    signal.write_text('{"invented":true}')
    gw = CurrentBoundedGateway(
        client,
        journal=journal,
        account_hash=ACCOUNT,
        authorized_at=START,
        expires_at=END,
        guard=lambda *a, **k: None,
        read_guard=lambda: None,
        clock=lambda: clock[0],
    )
    args = dict(
        prepared=req,
        reservation_snapshot=dict(
            pending={cid: reservation}, consumed_ids=[cid], account_hash=ACCOUNT
        ),
        signal_binding=bind(signal),
        execution_day=DAY,
        authorized_at=START,
        expires_at=END,
        submit=gw.submit,
        revalidate=lambda r: None,
        clock=lambda: clock[0],
    )
    return client, journal, gw, args, calls, clock


def test_current_journal_gateway_one_write_no_retry(transport):
    client, journal, gw, args, calls, clock = transport
    journal.dispatch_once(**args)
    assert len(calls) == 1 and client._retry == 0
    with pytest.raises(FileExistsError):
        journal.dispatch_once(**args)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "fault", ["latency", "payload", "account", "reference", "unknown", "identity"]
)
def test_final_no_write_boundaries(transport, fault):
    client, journal, gw, args, calls, clock = transport
    if fault == "latency":
        client.delay = 60
    elif fault == "payload":
        client.mutate = True
    elif fault == "account":
        args["reservation_snapshot"]["account_hash"] = "b" * 64
    elif fault == "reference":
        args["prepared"]["limit_price"] = 10.01
    elif fault == "unknown":
        args["prepared"]["reference_valid"] = "unknown"
    else:
        args["prepared"]["client_order_id"] = "dia-base-2026-11-03-buy-AAPL"
    with pytest.raises(ValueError):
        journal.dispatch_once(**args)
    assert not calls


def test_shared_run_body_only_policy_hook_extraction():
    import subprocess

    path = "open_composer/intraday_runner/source_dispatch_journal.py"
    # Freeze the accepted deployed journal, including its durable storage hooks.
    old = ast.parse(subprocess.check_output(["git", "show", "242f3b09:" + path], text=True))
    new = ast.parse(Path(path).read_text())

    def method(tree, name):
        return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)

    for name in ("cancel_own_remainder_once", "receive", "_ensure_durable_directory"):
        assert ast.dump(method(old, name), include_attributes=False) == ast.dump(
            method(new, name), include_attributes=False
        )


def test_generic_execution_refuses_day_limit(fixture_specs_root, tmp_path):
    from open_composer.execution_policy import require_orderable_execution_policy
    from open_composer.models.strategy_spec import ExecutionPolicy, load_strategy_spec

    spec = load_strategy_spec(fixture_specs_root / "fixture_pullback_15m.yaml")
    spec.execution_policy = ExecutionPolicy(
        policy_id="invented-current-day-limit", order_style="day_limit", time_in_force="day"
    )
    with pytest.raises(ValueError, match="unsupported paper order_style: day_limit"):
        require_orderable_execution_policy(spec, tmp_path)


@pytest.mark.parametrize("route", ["BASE", "H5"])
def test_complete_offline_orchestration_no_network(tmp_path, monkeypatch, route):
    """Real cash/checkpoint/journal/gateway with invented client and forecast.

    Native authentication/science acceptance are explicitly stubbed; this
    exercises implementation, not actual admission or broker success.
    """
    import hashlib

    from open_composer.intraday_runner import current_initialization_account as account_module
    from open_composer.intraday_runner import current_initialization_runtime as runtime_module
    from open_composer.intraday_runner.source_state_checkpoint import SourceStateCheckpoint
    from tests.test_current_validation_authority import authority as invented_authority

    synthetic_id = "invented-isolated-test-account"
    synthetic_hash = hashlib.sha256(synthetic_id.encode()).hexdigest()
    monkeypatch.setattr(account_module, "ACCOUNT", synthetic_hash)
    monkeypatch.setattr(runtime_module, "ACCOUNT", synthetic_hash)
    monkeypatch.setattr(runtime_module, "secure_identity", lambda: (1, 2, 3, 4))
    monkeypatch.setattr(runtime_module, "_require_kill_switch_clear", lambda root: None)
    from open_composer.intraday_runner import current_initialization_controls as controls

    monkeypatch.setattr(controls, "ACCOUNT", synthetic_hash)
    monkeypatch.setattr(old_gateway, "_require_verified_paper_client", lambda c: None)
    clock = [datetime(2026, 10, 20, 13, 0, tzinfo=UTC)]
    mono = [100.0]
    calls = []

    class Client:
        def __init__(self):
            self._retry = 0
            self._session = requests.Session()
            self.orders = []
            self._session.request = self.physical

        def physical(self, method, url, **kwargs):
            calls.append((method, url, copy.deepcopy(kwargs)))
            if method == "GET":
                path = url.split("/v2")[-1]
                if path == "/account":
                    body = dict(
                        id=synthetic_id,
                        currency="USD",
                        status="ACTIVE",
                        cash="1000000",
                        non_marginable_buying_power="1000000",
                        equity="1000000",
                        trading_blocked=False,
                        account_blocked=False,
                        trade_suspended_by_user=False,
                    )
                elif path == "/clock":
                    body = dict(timestamp=clock[0].isoformat(), is_open=13 <= clock[0].hour < 20)
                elif path in {"/positions", "/account/activities"}:
                    body = []
                elif path == "/orders":
                    body = copy.deepcopy(self.orders)
                elif path.startswith("/assets/"):
                    body = dict(
                        symbol=path.rsplit("/", 1)[-1],
                        status="active",
                        tradable=True,
                        **{"class": "us_equity"},
                    )
                else:
                    raise AssertionError(path)
            elif method == "POST":
                body = {
                    **kwargs["json"],
                    "id": "invented-" + str(len(self.orders)),
                    "status": "new",
                    "filled_qty": "0",
                }
                self.orders.append(copy.deepcopy(body))
            elif method == "DELETE":
                bid = url.rsplit("/", 1)[-1]
                for order in self.orders:
                    if order["id"] == bid:
                        order["status"] = "canceled"
                body = {}
            else:
                raise AssertionError(method)
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(body).encode()
            response._content_consumed = True
            return response

        def get(self, path, params):
            return self._session.request(
                "GET", "https://paper-api.alpaca.markets/v2" + path, params=params
            ).json()

        def submit_order(self, order):
            return self._session.request(
                "POST", "https://paper-api.alpaca.markets/v2/orders", json=order.to_request_fields()
            ).json()

        def cancel_order_by_id(self, bid):
            self._session.request(
                "DELETE", "https://paper-api.alpaca.markets/v2/orders/" + bid, json=None
            )

    client = Client()
    runtime = runtime_module.CurrentInitializationRuntime.__new__(
        runtime_module.CurrentInitializationRuntime
    )
    runtime.root = Path("/root/codex-test/open-composer")
    runtime.directory = tmp_path / "ledger"
    runtime.clock = lambda: clock[0]
    runtime.monotonic = lambda: mono[0]
    runtime.auth = dict(
        capital_usd=10000,
        account_hash=synthetic_hash,
        authorized_at=START.isoformat(),
        expires_at=END.isoformat(),
        reconciliation_after=START.isoformat(),
    )
    runtime.authority = {}
    runtime.task = (
        runtime_module.BASE if route == "BASE" else "H5-LEARNED-SWING-PAPER-VALIDATION-20261019"
    )
    runtime.namespace = NAMESPACE if route == "BASE" else "h5cur-20261019-fa6147de"
    from open_composer.intraday_runner.validation_account_partition import (
        ValidationAccountPartition,
    )

    _, partition_authority = invented_authority(tmp_path, runtime.task)

    class SyntheticPartition(ValidationAccountPartition):
        def __init__(self):
            self.root = tmp_path
            self.binding = partition_authority["partition"]

        def register(self, task, authority):
            assert task == runtime.task

        def books(self):
            current = runtime.store.load()
            return {
                runtime.task: dict(
                    revision=runtime_module._hash(current),
                    snapshot=current["snapshot"],
                    namespace=runtime.namespace,
                )
            }

    runtime.partition = SyntheticPartition()
    runtime.store = SourceStateCheckpoint(
        runtime.directory / "checkpoints",
        account_hash=synthetic_hash,
        sleeve_id="invented-rehearsal",
    )
    runtime.journal = CurrentDispatchJournal(
        runtime.directory / "dispatch", namespace=runtime.namespace
    )
    runtime.client_factory = lambda: client
    runtime.gateway = None
    runtime.transport_bytes = 0
    runtime.transport_count = 0
    runtime.trace_directory = tmp_path / "transport"
    runtime.trace_directory_identity = None
    runtime.current_request = None
    runtime.current_response = None
    runtime.capture_storage = None
    runtime.capture_slots = None
    runtime.observation = None
    runtime.required_symbols = set()
    runtime.current_phase = "decision"
    runtime.secure_snapshot = None
    runtime.read_guard = lambda **kwargs: None
    runtime.entry_guard = lambda **kwargs: None
    dated = tmp_path / "dated.json"
    dated.write_text(
        json.dumps(
            dict(account_hash=synthetic_hash, broker_reported_cash_equity_nonmarginable_USD=1000000)
        )
    )
    runtime.auth["initial_account_scope"] = bind(dated)
    symbols = (
        ["AAPL", "CRM", "IBM", "INTC", "MSFT"]
        if route == "BASE"
        else ["AAA", "BBB", "CCC", "DDD", "EEE"]
    )
    weights = [0.2] * 5 if route == "BASE" else [0.2, 0.2, 0.2, 0, 0]
    forecast = dict(
        symbols=symbols,
        weights=weights,
        reference_marks={symbol: 100.01 for symbol in symbols},
        decision_reason="invented_supported_prediction",
    )
    expected_count = sum(w > 0 for w in weights)
    runtime.receive_science = lambda: dict(forecast=forecast, synthetic=True)
    out = tmp_path / "decision"
    out.mkdir()
    result = runtime.decide(out)
    assert result["broker_writes"] == 0 and not any(m != "GET" for m, _, _ in calls)
    clock[0] = datetime(2026, 10, 20, 13, 30, tzinfo=UTC)
    mono[0] = 1900
    runtime.observe(tmp_path / "opening", opening=True)
    before = runtime.store.load()
    assert Decimal(before["snapshot"]["evidence"]["risk"]["day_open_nav"]) == Decimal("10000")
    clock[0] = NOW
    mono[0] = 2500
    out = tmp_path / "buy"
    out.mkdir()
    runtime.current_phase = "buy"
    result = runtime.buy(out)
    assert (
        len(result["orders"]) == expected_count
        and sum(m == "POST" for m, _, _ in calls) == expected_count
    )
    current = runtime.store.load()
    assert len(current["snapshot"]["pending"]) == expected_count
    assert all(
        x["attempted"] is True for x in current["snapshot"]["evidence"]["dispatch_intents"].values()
    )
    # A separate ordinary invocation cannot buy the same batch again.
    with pytest.raises(ValueError):
        runtime.buy(tmp_path / "again")
    assert sum(m == "POST" for m, _, _ in calls) == expected_count
    assert current["snapshot"]["cashbook"]["lots"] == {}  # ACK is not a fill.
    assert current["snapshot"]["applied_fill_ids"] == []
    reserved_before = sum(
        p["amount"] for r in current["snapshot"]["pending"].values() for p in r["remaining_funding"]
    )
    clock[0] = datetime(2026, 10, 20, 14, 0, tzinfo=UTC)
    mono[0] = 3700
    runtime.current_phase = "cancel"
    out = tmp_path / "cancel"
    out.mkdir()
    cancelled = runtime.cancel(out)
    assert sum(m == "DELETE" for m, _, _ in calls) == expected_count
    assert cancelled["cancellation_response_is_not_terminal"] is True
    after = runtime.store.load()
    assert (
        sum(
            p["amount"]
            for r in after["snapshot"]["pending"].values()
            for p in r["remaining_funding"]
        )
        == reserved_before
    )
    clock[0] = datetime(2026, 10, 20, 20, 5, tzinfo=UTC)
    mono[0] = 25600
    runtime.current_phase = "reconcile"
    out = tmp_path / "postclose"
    out.mkdir()
    reconciled = runtime.reconcile(out)
    assert reconciled["fees_certified"] is False
    after = runtime.store.load()
    assert all(r["side"] == "liability_hold" for r in after["snapshot"]["pending"].values())
    assert (
        sum(
            p["amount"]
            for r in after["snapshot"]["pending"].values()
            for p in r["remaining_funding"]
        )
        == reserved_before
    )


def test_native_consumed_identity_cannot_change_output(tmp_path, monkeypatch):
    import json

    from open_composer.intraday_runner import current_initialization_storage as storage
    from open_composer.intraday_runner.current_initialization_entry import consume

    monkeypatch.setattr(storage, "capacity", lambda *a: dict(remaining_current=1000000))
    monkeypatch.setattr(storage.NativeStorage, "check", lambda *a, **k: None)
    auth = tmp_path / "authority.json"
    from open_composer.intraday_runner.validation_account_partition import BASE, slot

    auth.write_text(
        json.dumps(
            dict(account_hash=ACCOUNT, task_id=BASE, ledger_root=str(slot(tmp_path, BASE)[0]))
        )
    )
    job = tmp_path / "job.json"
    job.write_text(
        json.dumps(
            dict(
                task_id=BASE,
                authority=bind(auth),
                invocation_id="one",
                output=str(tmp_path / "first"),
            )
        )
    )
    consume(tmp_path, bind(job))
    job.write_text(
        json.dumps(
            dict(
                task_id=BASE,
                authority=bind(auth),
                invocation_id="one",
                output=str(tmp_path / "second"),
            )
        )
    )
    with pytest.raises(FileExistsError):
        consume(tmp_path, bind(job))


def test_policy_hook_old_quote_semantics_still_refuses():
    from open_composer.intraday_runner.source_dispatch_journal import SourceDispatchJournal

    old = SourceDispatchJournal(Path("/not-created"))
    req = dict(
        client_order_id="dia-base-2026-11-03-buy-AAPL",
        symbol="AAPL",
        side="buy",
        qty=2,
        limit_price=1,
        quote=dict(ask=1, ask_shares=1),
    )
    from datetime import date

    with pytest.raises(ValueError):
        old._validate_execution_request(req, date(2026, 11, 3))


def test_owned_exit_preserves_fee_unknown_without_nav_claim():
    o = observation()
    o.update(
        fees_complete=False,
        activities_complete=False,
        cash_reconciled=False,
        holdings=[
            dict(symbol="AAPL", quantity=2, owned=True, current_price="10.01", market_value="20.02")
        ],
    )
    with pytest.raises(ValueError):
        receive_observation(
            o, now=NOW, now_monotonic=12, account_hash=ACCOUNT, checkpoint_hash="head"
        )
    result = receive_observation(
        o,
        now=NOW,
        now_monotonic=12,
        account_hash=ACCOUNT,
        checkpoint_hash="head",
        purpose="owned_exit",
    )
    assert result["verified_nav"] is None and result["fees_complete"] is False
    assert (
        result["liability_or_fee_holds_released"] is False and result["new_risk_permitted"] is False
    )
    o["units_reconciled"] = False
    with pytest.raises(ValueError):
        receive_observation(
            o,
            now=NOW,
            now_monotonic=12,
            account_hash=ACCOUNT,
            checkpoint_hash="head",
            purpose="owned_exit",
        )


def test_existing_global_kill_and_local_stop_refuse_before_state_or_transport(tmp_path):
    from open_composer.intraday_runner.current_initialization_runtime import (
        CurrentInitializationRuntime,
    )
    from open_composer.paper_controls import set_paper_kill_switch

    r = CurrentInitializationRuntime.__new__(CurrentInitializationRuntime)
    r.root = tmp_path
    r.directory = tmp_path / "own"
    r.directory.mkdir()
    r.read_guard = lambda: None
    r.auth = {}
    r.capture_storage = None
    set_paper_kill_switch(
        tmp_path, enabled=True, reason="invented safety fixture", updated_by="test"
    )
    with pytest.raises(Exception, match="kill switch"):
        r.order_guard({})
    set_paper_kill_switch(tmp_path, enabled=False, reason="fixture clear", updated_by="test")
    (r.directory / "STOP").touch()
    with pytest.raises(ValueError, match="stop marker"):
        r.order_guard({})
